"""
Main application window.
Manages server connections, channel windows, and UI layout.
"""

import logging
import os
from datetime import datetime
from typing import Optional, Dict
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget,
    QTreeWidgetItem, QTabWidget, QMenuBar, QMenu, QStatusBar,
    QMessageBox, QSystemTrayIcon, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QAction, QIcon, QPixmap, QColor

from core.irc_client import IRCClient
from core.encryption_manager import EncryptionManager
from core.alias_manager import AliasManager
from core.irc_parser import IRCMessage
from ui.channel_widget import ChannelWidget
from ui.server_list_dialog import ServerListDialog
from ui.room_key_dialog import RoomKeyDialog
from ui.preferences_dialog import PreferencesDialog
from ui.channel_list_dialog import ChannelListDialog

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self, settings_manager, encryption_manager, alias_manager):
        """Initialize main window."""
        super().__init__()
        self.settings_manager = settings_manager
        self.encryption_manager = encryption_manager
        self.alias_manager = alias_manager
        
        # Data structures
        self.irc_clients: Dict[str, IRCClient] = {}  # server_name -> IRCClient
        self.channel_widgets: Dict[str, ChannelWidget] = {}  # key -> ChannelWidget
        self.server_items: Dict[str, QTreeWidgetItem] = {}  # server_name -> tree item
        self.motd_queues: Dict[str, list] = {}  # server_name -> list of pending MOTD messages
        self.motd_timers: Dict[str, QTimer] = {}  # server_name -> QTimer for MOTD display
        self.motd_complete_timers: Dict[str, QTimer] = {}  # server_name -> QTimer for MOTD completion message
        self.motd_complete_pending: Dict[str, bool] = {}  # server_name -> whether MOTD completion is pending
        self.last_motd_lines: Dict[str, str] = {}  # server_name -> last displayed MOTD line for combining
        
        self._init_ui()
        self._init_tray()
        self._setup_logging()
        
        # Load all servers into the tree view
        self._load_all_servers()
        
        # Auto-connect to servers
        self._auto_connect_servers()
    
    def _init_ui(self):
        """Initialize UI components."""
        self.setWindowTitle("Encrypted IRC Client")
        self.setMinimumSize(800, 600)
        
        # Central widget
        central = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Server/channel tree (left sidebar)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Servers & Channels")
        self.tree.setMaximumWidth(250)
        self.tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        layout.addWidget(self.tree)
        
        # Tab widget for channel windows (center)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs, 1)
        
        central.setLayout(layout)
        self.setCentralWidget(central)
        
        # Menu bar
        self._create_menu_bar()
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        
        # Keyboard shortcuts
        self._setup_shortcuts()
    
    def _create_menu_bar(self):
        """Create menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        preferences_action = QAction("&Preferences", self)
        preferences_action.setShortcut("Ctrl+P")
        preferences_action.triggered.connect(self._show_preferences)
        file_menu.addAction(preferences_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Server menu
        server_menu = menubar.addMenu("&Server")
        
        server_list_action = QAction("&Server List", self)
        server_list_action.setShortcut("Ctrl+N")
        server_list_action.triggered.connect(self._show_server_list)
        server_menu.addAction(server_list_action)
        
        server_menu.addSeparator()
        
        disconnect_action = QAction("&Disconnect All", self)
        disconnect_action.triggered.connect(self._disconnect_all)
        server_menu.addAction(disconnect_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        
        channel_list_action = QAction("&Channel List", self)
        channel_list_action.setShortcut("Ctrl+J")
        channel_list_action.triggered.connect(self._show_channel_list)
        tools_menu.addAction(channel_list_action)
        
        tools_menu.addSeparator()
        
        aliases_action = QAction("&Aliases", self)
        aliases_action.triggered.connect(self._show_aliases)
        tools_menu.addAction(aliases_action)
        
        logs_action = QAction("&Open Logs Folder", self)
        logs_action.setShortcut("Ctrl+L")
        logs_action.triggered.connect(self._open_logs_folder)
        tools_menu.addAction(logs_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Ctrl+K for encryption key
        encrypt_action = QAction(self)
        encrypt_action.setShortcut("Ctrl+K")
        encrypt_action.triggered.connect(self._show_room_key_dialog)
        self.addAction(encrypt_action)
    
    def _init_tray(self):
        """Initialize system tray icon."""
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self)
            # Create a simple 16x16 icon to avoid the warning
            # In a real app, you'd load an actual icon file here
            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.GlobalColor.blue)  # Simple colored square
            self.tray_icon.setIcon(QIcon(pixmap))
            self.tray_icon.setToolTip("Encrypted IRC Client")
            self.tray_icon.activated.connect(self._on_tray_activated)
            
            # Create context menu
            tray_menu = QMenu(self)
            close_action = QAction("Close", self)
            close_action.triggered.connect(self.close)
            tray_menu.addAction(close_action)
            self.tray_icon.setContextMenu(tray_menu)
            
            self.tray_icon.show()
        else:
            self.tray_icon = None
    
    def _on_tray_activated(self, reason):
        """Handle system tray activation."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
            self.raise_()
            self.activateWindow()
    
    def _setup_logging(self):
        """Setup message logging to files."""
        log_dir = self.settings_manager.get_setting('log_directory', 'logs')
        Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    def _log_message(self, server_name: str, channel_name: str, message: str):
        """Log a message to file."""
        if self.settings_manager.get_setting('log_enabled', '1') != '1':
            return
        
        log_dir = self.settings_manager.get_setting('log_directory', 'logs')
        log_file = Path(log_dir) / f"{server_name}_{channel_name.replace('#', '')}.log"
        
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"[{timestamp}] {message}\n")
        except Exception as e:
            logger.error(f"Error logging message: {e}")
    
    def _load_all_servers(self):
        """Load all servers into the tree view (disconnected state)."""
        servers = self.settings_manager.get_servers()
        for server in servers:
            server_name = server.get('name', server.get('hostname'))
            # Only add if not already in tree (avoid duplicates)
            if server_name not in self.server_items:
                server_item = QTreeWidgetItem(self.tree)
                server_item.setText(0, f"🔌 {server_name}")
                server_item.setData(0, Qt.ItemDataRole.UserRole, ('server', server_name))
                self.server_items[server_name] = server_item
    
    def _auto_connect_servers(self):
        """Auto-connect to the first server marked for auto-connect (only one allowed)."""
        servers = self.settings_manager.get_servers()
        for server in servers:
            if server.get('auto_connect'):
                # Only connect to the first server with auto_connect enabled
                QTimer.singleShot(1000, lambda s=server: self._connect_to_server(s))
                break
    
    def _show_server_list(self):
        """Show server list dialog."""
        dialog = ServerListDialog(self.settings_manager, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            # User may have added/edited servers, reload the tree
            self._reload_server_list()
    
    def _reload_server_list(self):
        """Reload the server list in the tree view."""
        # Get current servers from database
        current_servers = {s.get('name', s.get('hostname')): s for s in self.settings_manager.get_servers()}
        
        # Remove servers that no longer exist (only if not connected)
        to_remove = []
        for server_name, server_item in self.server_items.items():
            if server_name not in current_servers:
                # Only remove if not connected
                if server_name not in self.irc_clients:
                    self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(server_item))
                    to_remove.append(server_name)
        
        for server_name in to_remove:
            del self.server_items[server_name]
        
        # Add new servers
        for server in current_servers.values():
            server_name = server.get('name', server.get('hostname'))
            if server_name not in self.server_items:
                server_item = QTreeWidgetItem(self.tree)
                server_item.setText(0, f"🔌 {server_name}")
                server_item.setData(0, Qt.ItemDataRole.UserRole, ('server', server_name))
                self.server_items[server_name] = server_item
    
    def _connect_to_server(self, server_config: Dict):
        """Connect to an IRC server."""
        server_name = server_config.get('name', server_config.get('hostname'))
        
        if server_name in self.irc_clients:
            QMessageBox.warning(self, "Already Connected", 
                              f"Already connected to {server_name}")
            return
        
        # Create IRC client
        irc_client = IRCClient(server_config, self.encryption_manager)
        irc_client.connected.connect(self._on_server_connected)
        irc_client.disconnected.connect(self._on_server_disconnected)
        irc_client.message_received.connect(self._on_irc_message)
        irc_client.error_occurred.connect(self._on_irc_error)
        
        self.irc_clients[server_name] = irc_client
        
        # Add to tree if not already there (may already exist from _load_all_servers)
        if server_name not in self.server_items:
            server_item = QTreeWidgetItem(self.tree)
            server_item.setText(0, f"🔌 {server_name}")
            server_item.setData(0, Qt.ItemDataRole.UserRole, ('server', server_name))
            self.server_items[server_name] = server_item
        else:
            # Update existing item to show connecting state
            server_item = self.server_items[server_name]
            server_item.setText(0, f"🔌 {server_name}")
        
        # Create status window (always first tab)
        status_key = f"{server_name}:STATUS"
        status_widget = self._get_or_create_channel_widget(
            server_name, "STATUS", is_pm=False
        )
        # Insert status tab at the beginning (index 0)
        self.tabs.insertTab(0, status_widget, f"{server_name} - Status")
        self.tabs.setCurrentIndex(0)
        
        # Add initial connection status message
        hostname = server_config.get('hostname', server_name)
        port = server_config.get('port', 6667)
        use_ssl = server_config.get('ssl', False)
        ssl_text = " (SSL)" if use_ssl else ""
        status_widget.add_status_message(
            f"Attempting to connect to {hostname}:{port}{ssl_text}...",
            QColor(0, 128, 255)  # Light blue for connection status
        )
        
        # Connect
        irc_client.connect_to_server()
        self.status_bar.showMessage(f"Connecting to {server_name}...")
    
    def _on_server_connected(self, server_name: str):
        """Handle server connection."""
        self.status_bar.showMessage(f"Connected to {server_name}")
        server_item = self.server_items.get(server_name)
        if server_item:
            server_item.setText(0, f"✓ {server_name}")
            # Expand the server item to show channels when connected
            server_item.setExpanded(True)
        
        # Add status message to status tab
        status_widget = self._get_or_create_channel_widget(server_name, "STATUS", is_pm=False)
        status_widget.add_status_message(
            f"Connected to {server_name}. Getting MOTD...",
            QColor(0, 200, 0)  # Green for success
        )
    
    def _on_server_disconnected(self, server_name: str):
        """Handle server disconnection."""
        self.status_bar.showMessage(f"Disconnected from {server_name}")
        server_item = self.server_items.get(server_name)
        if server_item:
            server_item.setText(0, f"🔌 {server_name}")
            # Remove all channel items from the tree
            while server_item.childCount() > 0:
                child = server_item.child(0)
                server_item.removeChild(child)
        
        # Clean up MOTD timers and queues
        if server_name in self.motd_timers:
            self.motd_timers[server_name].stop()
            del self.motd_timers[server_name]
        if server_name in self.motd_complete_timers:
            self.motd_complete_timers[server_name].stop()
            del self.motd_complete_timers[server_name]
        if server_name in self.motd_queues:
            del self.motd_queues[server_name]
        if server_name in self.motd_complete_pending:
            del self.motd_complete_pending[server_name]
        if server_name in self.last_motd_lines:
            del self.last_motd_lines[server_name]
        
        # Close all tabs for this server (except status tab)
        tabs_to_remove = []
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if isinstance(widget, ChannelWidget):
                if widget.server_name == server_name and widget.channel_name != "STATUS":
                    tabs_to_remove.append(i)
        
        # Remove tabs in reverse order to maintain indices
        for i in reversed(tabs_to_remove):
            self.tabs.removeTab(i)
        
        # Remove channel widgets from memory (except status)
        keys_to_remove = []
        for key, widget in self.channel_widgets.items():
            if widget.server_name == server_name and widget.channel_name != "STATUS":
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            widget = self.channel_widgets.pop(key)
            # Disconnect signals and clean up
            widget.deleteLater()
        
        # Add status message to status tab
        try:
            status_widget = self._get_or_create_channel_widget(server_name, "STATUS", is_pm=False)
            # Get hostname from server config (try irc_client first, then database, then fallback)
            hostname = server_name  # Default to server name
            irc_client = self.irc_clients.get(server_name)
            if irc_client and hasattr(irc_client, 'server_config'):
                hostname = irc_client.server_config.get('hostname', server_name)
            elif self.settings_manager and self.settings_manager.conn:
                # Try database if connection is available
                try:
                    servers = self.settings_manager.get_servers()
                    for server in servers:
                        if server.get('name') == server_name:
                            hostname = server.get('hostname', server_name)
                            break
                except Exception as e:
                    logger.warning(f"Could not get hostname from database: {e}")
            
            status_widget.add_status_message(
                f"Disconnected from {hostname}",
                QColor(255, 128, 0)  # Orange for disconnection
            )
        except Exception as e:
            # Database might be closed during shutdown - just log and continue
            logger.debug(f"Could not add disconnect message (app may be shutting down): {e}")
    
    def _on_irc_message(self, server_name: str, message: IRCMessage):
        """Handle incoming IRC message."""
        irc_client = self.irc_clients.get(server_name)
        if not irc_client:
            return
        
        own_nick = irc_client.nickname
        
        # Handle MOTD messages (372) - queue them for delayed display
        if message.command == '372':  # RPL_MOTD
            # If MOTD completion is already pending, display this line immediately
            # (it arrived after the 376 message)
            if server_name in self.motd_complete_pending and self.motd_complete_pending[server_name]:
                # Display immediately and reset the completion timer
                status_widget = self._get_or_create_channel_widget(server_name, "STATUS", is_pm=False)
                status_widget.add_message(message, own_nick)
                # Reset completion timer to give time for this line to be displayed
                if server_name in self.motd_complete_timers:
                    self.motd_complete_timers[server_name].stop()
                    self.motd_complete_timers[server_name].start(150)
                return
            
            if server_name not in self.motd_queues:
                self.motd_queues[server_name] = []
            self.motd_queues[server_name].append(message)
            # Start timer if not already running
            if server_name not in self.motd_timers:
                timer = QTimer(self)
                timer.timeout.connect(lambda: self._process_motd_queue(server_name))
                self.motd_timers[server_name] = timer
                timer.start(100)  # Process one MOTD line every 100ms
            return  # Don't process immediately
        
        # Filter out messages we don't want to display in status
        # Skip end-of-list messages and other noise
        if message.command == '366':  # RPL_ENDOFNAMES - End of /NAMES list
            # Still process for channel widget if needed, but don't display in status
            if len(message.params) >= 2:
                channel = message.params[1] if len(message.params) > 1 else None
                if channel:
                    widget = self._get_or_create_channel_widget(server_name, channel, is_pm=False)
                    # Don't display this message
            return
        
        if message.command == '376':  # RPL_ENDOFMOTD - End of /MOTD command
            # Stop MOTD timer and flush remaining queue
            if server_name in self.motd_timers:
                self.motd_timers[server_name].stop()
                # Process any remaining MOTD messages immediately
                self._flush_motd_queue(server_name)
                del self.motd_timers[server_name]
            if server_name in self.motd_queues:
                del self.motd_queues[server_name]
            if server_name in self.last_motd_lines:
                del self.last_motd_lines[server_name]
            
            # Mark that MOTD completion is pending (in case a late 372 arrives)
            self.motd_complete_pending[server_name] = True
            
            # Delay the completion message slightly to ensure all MOTD lines are displayed first
            # Use a timer to show the completion message after a short delay (150ms)
            def show_completion():
                status_widget = self._get_or_create_channel_widget(server_name, "STATUS", is_pm=False)
                # Check if auto-join is configured
                server_config = irc_client.server_config if hasattr(irc_client, 'server_config') else {}
                auto_join = server_config.get('auto_join_channels', '')
                if auto_join:
                    channels = [ch.strip() for ch in auto_join.split(',') if ch.strip()]
                    if channels:
                        status_widget.add_status_message(
                            f"MOTD complete. Auto-joining {len(channels)} channel(s)...",
                            QColor(0, 200, 0)  # Green
                        )
                else:
                    status_widget.add_status_message(
                        "MOTD complete. Ready.",
                        QColor(0, 200, 0)  # Green
                    )
                # Clean up timer and pending flag
                if server_name in self.motd_complete_timers:
                    del self.motd_complete_timers[server_name]
                if server_name in self.motd_complete_pending:
                    del self.motd_complete_pending[server_name]
            
            # Schedule completion message after a delay to ensure all MOTD lines are shown
            complete_timer = QTimer(self)
            complete_timer.setSingleShot(True)
            complete_timer.timeout.connect(show_completion)
            self.motd_complete_timers[server_name] = complete_timer
            complete_timer.start(150)  # 150ms delay to ensure all MOTD lines are displayed
            return
        
        if message.command == '422':  # ERR_NOMOTD - No MOTD configured
            # Add status message for no MOTD
            status_widget = self._get_or_create_channel_widget(server_name, "STATUS", is_pm=False)
            server_config = irc_client.server_config if hasattr(irc_client, 'server_config') else {}
            auto_join = server_config.get('auto_join_channels', '')
            if auto_join:
                channels = [ch.strip() for ch in auto_join.split(',') if ch.strip()]
                if channels:
                    status_widget.add_status_message(
                        f"No MOTD configured. Auto-joining {len(channels)} channel(s)...",
                        QColor(0, 200, 0)  # Green
                    )
            else:
                status_widget.add_status_message(
                    "No MOTD configured. Ready.",
                    QColor(0, 200, 0)  # Green
                )
            # Still display the message in status
            target = "STATUS"
        
        elif message.command == '353':  # RPL_NAMREPLY
            # Format: :server 353 nick = #channel :nick1 nick2 nick3
            # Process nicks but don't display the message itself in status
            if len(message.params) >= 3:
                channel = message.params[2]
                nicks_str = message.params[3] if len(message.params) > 3 else ""
                if nicks_str:
                    widget = self._get_or_create_channel_widget(server_name, channel, is_pm=False)
                    # Parse and add nicks to the widget
                    nicks = nicks_str.split()
                    for nick in nicks:
                        widget.add_nick(nick)
            # Don't display this message in status
            return
        
        # Handle special numeric replies (but still display them in status)
        if message.command == '322':  # RPL_LIST - channel list entry
            # Format: :server 322 nick #channel user_count :topic
            if len(message.params) >= 3:
                channel = message.params[1]
                user_count = message.params[2]
                topic = message.params[3] if len(message.params) > 3 else ""
                # Forward to channel list dialog if open
                if hasattr(self, '_channel_list_dialog') and self._channel_list_dialog:
                    self._channel_list_dialog.add_channel(channel, user_count, topic)
            # Still display in status window
            target = "STATUS"
        elif message.command == '323':  # RPL_LISTEND - end of channel list
            if hasattr(self, '_channel_list_dialog') and self._channel_list_dialog:
                self._channel_list_dialog.set_list_complete()
            # Still display in status window
            target = "STATUS"
        elif message.command == 'PART':
            # PART messages: channel is in params[0]
            if message.params and len(message.params) > 0:
                target = message.params[0].lstrip(':')  # Remove leading colon if present
            else:
                target = message.target or "STATUS"
        elif message.command == 'QUIT':
            # QUIT messages: broadcast to all channels the user is in
            # Get all channel widgets for this server
            quit_nick = message.nick
            if quit_nick:
                # Find all channels this user is in and broadcast the QUIT message
                for key, widget in self.channel_widgets.items():
                    if widget.server_name == server_name and widget.channel_name != "STATUS" and not widget.is_pm:
                        # Check if this nick is in the channel's nicklist
                        base_nick = quit_nick.lstrip('@+%&~')
                        nick_in_channel = any(
                            n.lstrip('@+%&~').lower() == base_nick.lower() 
                            for n in widget.nicks
                        )
                        if nick_in_channel:
                            widget.add_message(message, own_nick)
                            widget.remove_nick(quit_nick)
                # Don't process QUIT further - we've already handled it
                return
            else:
                target = "STATUS"
        else:
            # Determine target channel/widget
            target = message.target
            
            # For numeric replies (server messages), route to STATUS
            # Numeric replies typically have the nickname as first param, not a channel
            if message.command.isdigit():
                # Check if the target is actually a channel (starts with # or &)
                if target and (target.startswith('#') or target.startswith('&')):
                    # It's a channel-specific numeric reply, route to that channel
                    pass  # Keep target as is
                else:
                    # Server message (MOTD, welcome, etc.), route to STATUS
                    target = "STATUS"
            elif message.command == 'PRIVMSG':
                # PRIVMSG: target is the channel or user
                if not target:
                    target = "STATUS"  # Fallback
                elif target == own_nick:
                    # Private message to us - route to sender
                    sender = message.nick or "Unknown"
                    target = sender
                # For channel PRIVMSG, target is already the channel name, so keep it
            elif not target:
                # Status message or server message
                target = "STATUS"
            elif target == own_nick:
                # Private message
                sender = message.nick or "Unknown"
                target = sender
        
        # Get or create channel widget
        widget = self._get_or_create_channel_widget(
            server_name, target,
            is_pm=(target != "STATUS" and not target.startswith('#'))
        )
        
        # If this is a JOIN message for our own nick, switch to the channel
        if message.command == 'JOIN' and message.nick == own_nick and target != "STATUS":
            # Add status message to status tab
            status_widget = self._get_or_create_channel_widget(server_name, "STATUS", is_pm=False)
            channel_name = message.params[0] if message.params else target
            if channel_name:
                # Remove any leading colon if present
                channel_name = channel_name.lstrip(':')
                status_widget.add_status_message(
                    f"Joined channel: {channel_name}",
                    QColor(0, 200, 0)  # Green for success
                )
            self._add_or_show_tab(widget, self._get_tab_title(widget))
            widget.focus_input()
        
        # If this is a PRIVMSG for a private message (PM), ensure the tab is shown
        elif message.command == 'PRIVMSG' and widget.is_pm:
            # Private message received - show the tab if it's not already visible
            self._add_or_show_tab(widget, self._get_tab_title(widget))
        
        # If this is a PART message for our own nick, remove channel from tree and close tab
        if message.command == 'PART' and message.nick == own_nick and target != "STATUS":
            channel_name = message.params[0] if message.params else target
            if channel_name:
                # Remove any leading colon if present
                channel_name = channel_name.lstrip(':')
                
                # Add status message to status tab
                status_widget = self._get_or_create_channel_widget(server_name, "STATUS", is_pm=False)
                status_widget.add_status_message(
                    f"Left channel: {channel_name}",
                    QColor(255, 128, 0)  # Orange for leaving
                )
                
                # Remove channel from tree
                server_item = self.server_items.get(server_name)
                if server_item:
                    for i in range(server_item.childCount()):
                        child = server_item.child(i)
                        child_data = child.data(0, Qt.ItemDataRole.UserRole)
                        if child_data and len(child_data) > 2 and child_data[2] == channel_name:
                            server_item.removeChild(child)
                            break
                
                # Close the tab if it's still open
                key = f"{server_name}:{channel_name}"
                channel_widget = self.channel_widgets.get(key)
                if channel_widget:
                    for i in range(self.tabs.count()):
                        if self.tabs.widget(i) == channel_widget:
                            self.tabs.removeTab(i)
                            break
                    
                    # Remove widget from memory (but keep it in channel_widgets for now)
                    # The widget will be cleaned up when the server disconnects
        
        # Add message to widget
        widget.add_message(message, own_nick)
        
        # Update tab title if widget is in a tab (for unread count, etc.)
        self._update_tab_title(widget)
        
        # Log message
        if message.command == 'PRIVMSG':
            self._log_message(server_name, target, f"<{message.nick}> {message.text}")
    
    def _process_motd_queue(self, server_name: str):
        """Process one MOTD message from the queue with delay."""
        if server_name not in self.motd_queues or not self.motd_queues[server_name]:
            # Queue is empty, stop timer
            if server_name in self.motd_timers:
                self.motd_timers[server_name].stop()
                del self.motd_timers[server_name]
            # Clear last line tracking
            if server_name in self.last_motd_lines:
                del self.last_motd_lines[server_name]
            # Note: Don't show completion message here - it's handled when 376 is received
            return
        
        # Get the next message from queue
        message = self.motd_queues[server_name].pop(0)
        text = message.text or ""
        
        # Check if this is a continuation line (like "are supported by this server")
        # and combine with previous line if it was short (likely a split line)
        if text.strip() == "are supported by this server" and server_name in self.last_motd_lines:
            last_line = self.last_motd_lines[server_name]
            # If last line was short (like "BEFIJLWXYZbdefhjklovw"), combine them
            if len(last_line) < 50 and not last_line.endswith("are supported by this server"):
                # Combine: remove the last displayed line and show combined version
                combined_text = last_line + " " + text.strip()
                # We can't easily remove the last line, so we'll just display the combined version
                # and update tracking
                text = combined_text
                self.last_motd_lines[server_name] = combined_text
            else:
                # Just update tracking
                self.last_motd_lines[server_name] = text
        else:
            # Update tracking with current line
            self.last_motd_lines[server_name] = text
        
        # Display the message
        status_widget = self._get_or_create_channel_widget(server_name, "STATUS", is_pm=False)
        irc_client = self.irc_clients.get(server_name)
        own_nick = irc_client.nickname if irc_client else ""
        
        # Create a modified message with combined text if needed
        if text != (message.text or ""):
            from core.irc_parser import IRCMessage
            modified_message = IRCMessage(
                prefix=message.prefix,
                command=message.command,
                params=message.params[:-1] + [text] if message.params else [text],
                raw=message.raw
            )
            status_widget.add_message(modified_message, own_nick)
        else:
            status_widget.add_message(message, own_nick)
    
    def _flush_motd_queue(self, server_name: str):
        """Flush all remaining MOTD messages from the queue immediately."""
        if server_name not in self.motd_queues:
            return
        
        status_widget = self._get_or_create_channel_widget(server_name, "STATUS", is_pm=False)
        irc_client = self.irc_clients.get(server_name)
        own_nick = irc_client.nickname if irc_client else ""
        
        # Process all remaining messages
        while self.motd_queues[server_name]:
            message = self.motd_queues[server_name].pop(0)
            status_widget.add_message(message, own_nick)
    
    def _on_irc_error(self, server_name: str, error_message: str):
        """Handle IRC error."""
        # Add error message to status tab
        status_widget = self._get_or_create_channel_widget(server_name, "STATUS", is_pm=False)
        status_widget.add_status_message(
            f"Connection error: {error_message}",
            QColor(255, 0, 0)  # Red for errors
        )
        QMessageBox.warning(self, "Connection Error", 
                          f"Error on {server_name}:\n{error_message}")
    
    def _get_or_create_channel_widget(self, server_name: str, channel_name: str,
                                      is_pm: bool = False) -> ChannelWidget:
        """Get or create a channel widget."""
        key = f"{server_name}:{channel_name}"
        
        if key in self.channel_widgets:
            return self.channel_widgets[key]
        
        # Create new widget
        widget = ChannelWidget(
            server_name, channel_name, is_pm=is_pm,
            encryption_manager=self.encryption_manager,
            settings_manager=self.settings_manager
        )
        widget.message_sent.connect(
            lambda msg, s=server_name, c=channel_name: self._send_message(s, c, msg)
        )
        widget.command_sent.connect(
            lambda cmd, s=server_name: self._handle_command(s, cmd)
        )
        widget.encrypt_key_requested.connect(self._show_room_key_dialog)
        widget.pm_requested.connect(
            lambda nick, s=server_name: self._open_pm(s, nick)
        )
        
        self.channel_widgets[key] = widget
        
        # Check encryption status after widget creation (using canonical ID)
        if channel_name != "STATUS":
            irc_client = self.irc_clients.get(server_name)
            if irc_client:
                server_config = irc_client.server_config
                own_nick = irc_client.nickname
                # Use encryption manager's get_room_key_data which handles PMs correctly
                key = self.encryption_manager.get_room_key_data(
                    server_name, channel_name, server_config,
                    own_nick=own_nick if is_pm else None,
                    is_pm=is_pm
                )
                widget.set_encrypted(key is not None)
        
        # Add to tree if it's a channel
        if channel_name != "STATUS" and not is_pm:
            server_item = self.server_items.get(server_name)
            if server_item:
                # Check if channel item already exists
                channel_exists = False
                for i in range(server_item.childCount()):
                    child = server_item.child(i)
                    child_data = child.data(0, Qt.ItemDataRole.UserRole)
                    if child_data and len(child_data) > 2 and child_data[2] == channel_name:
                        channel_exists = True
                        break
                
                if not channel_exists:
                    channel_item = QTreeWidgetItem(server_item)
                    channel_item.setText(0, channel_name)
                    channel_item.setData(0, Qt.ItemDataRole.UserRole, ('channel', server_name, channel_name))
                    # Expand the server item to show channels
                    server_item.setExpanded(True)
        
        return widget
    
    def _get_tab_title(self, widget: ChannelWidget) -> str:
        """Get the tab title for a channel widget."""
        if widget.channel_name == "STATUS":
            return f"{widget.server_name} - Status"
        
        title = widget.channel_name
        if widget.encrypted:
            title += " 🔒"
        if widget.unread_count > 0:
            title += f" ({widget.unread_count})"
        
        return title
    
    def _add_or_show_tab(self, widget: ChannelWidget, title: str):
        """Add widget as a tab or show existing tab."""
        # Check if widget is already in a tab
        for i in range(self.tabs.count()):
            if self.tabs.widget(i) == widget:
                # Tab exists, just switch to it
                self.tabs.setCurrentIndex(i)
                self._update_tab_title(widget)
                return
        
        # For status widgets, insert at the beginning
        # For other widgets, add after status tabs
        if widget.channel_name == "STATUS":
            index = self.tabs.insertTab(0, widget, title)
        else:
            # Find the position after all status tabs
            insert_index = 0
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                if isinstance(w, ChannelWidget) and w.channel_name == "STATUS":
                    insert_index = i + 1
            index = self.tabs.insertTab(insert_index, widget, title)
        
        self.tabs.setCurrentIndex(index)
    
    def _update_tab_title(self, widget: ChannelWidget):
        """Update the tab title for a widget."""
        for i in range(self.tabs.count()):
            if self.tabs.widget(i) == widget:
                title = self._get_tab_title(widget)
                self.tabs.setTabText(i, title)
                break
    
    def _on_tab_close_requested(self, index: int):
        """Handle tab close request."""
        widget = self.tabs.widget(index)
        if isinstance(widget, ChannelWidget):
            # Prevent closing status tabs
            if widget.channel_name == "STATUS":
                QMessageBox.information(
                    self, "Cannot Close",
                    "The server status tab cannot be closed. It displays all server messages."
                )
                return
            
            # For channel tabs, part from the channel
            server_name = widget.server_name
            channel_name = widget.channel_name
            
            # Only part if it's a channel (starts with #) and we're connected
            if channel_name.startswith('#') and server_name in self.irc_clients:
                irc_client = self.irc_clients[server_name]
                if irc_client:
                    # Send PART command to leave the channel
                    irc_client.part_channel(channel_name)
            
            # Remove the tab
            self.tabs.removeTab(index)
    
    def _on_tab_changed(self, index: int):
        """Handle tab change."""
        widget = self.tabs.widget(index)
        if isinstance(widget, ChannelWidget):
            # Clear unread count when switching to a tab
            widget.clear_unread()
            widget.focus_input()
    
    def _send_message(self, server_name: str, channel_name: str, message: str):
        """Send a message to a channel or user."""
        irc_client = self.irc_clients.get(server_name)
        if not irc_client:
            return
        
        if channel_name == "STATUS":
            # Commands go to status
            self._handle_command(server_name, message)
            return
        
        # Determine if this is a PM (not a channel - channels start with #)
        is_pm = channel_name != "STATUS" and not channel_name.startswith('#')
        
        # Check if encryption is enabled (verify in database using canonical ID)
        server_config = irc_client.server_config if irc_client else None
        own_nick = irc_client.nickname
        
        # Use encryption manager's get_room_key_data which handles PMs correctly
        key = self.encryption_manager.get_room_key_data(
            server_name, channel_name, server_config,
            own_nick=own_nick if is_pm else None,
            is_pm=is_pm
        )
        encrypted = key is not None
        
        # Echo the message immediately in the channel widget
        widget = self._get_or_create_channel_widget(server_name, channel_name, is_pm=is_pm)
        
        # Add icon based on encryption status
        if encrypted:
            display_message = f"🔒 {message}"
        else:
            display_message = f"⚠️ {message}"
        
        # Create a fake IRCMessage for immediate echo
        from core.irc_parser import IRCMessage
        echo_message = IRCMessage(
            prefix=f"{own_nick}!{irc_client.username}@{irc_client.server_config.get('hostname', 'unknown')}",
            command="PRIVMSG",
            params=[channel_name, display_message],
            raw=f":{own_nick}!{irc_client.username}@{irc_client.server_config.get('hostname', 'unknown')} PRIVMSG {channel_name} :{display_message}"
        )
        widget.add_message(echo_message, own_nick)
        
        # Send the actual message
        irc_client.send_message(channel_name, message, encrypted=encrypted)
    
    def _handle_command(self, server_name: str, command_line: str):
        """Handle IRC command."""
        irc_client = self.irc_clients.get(server_name)
        if not irc_client:
            return
        
        # Expand aliases
        expanded = self.alias_manager.expand_alias(command_line)
        
        # Parse command
        parts = expanded[1:].split(None, 1) if expanded.startswith('/') else []
        if not parts:
            return
        
        command = parts[0].upper()
        args = parts[1].split() if len(parts) > 1 else []
        
        # Handle commands
        if command == 'JOIN':
            channel = args[0] if args else None
            if channel:
                irc_client.join_channel(channel)
        
        elif command == 'PART':
            channel = args[0] if args else None
            reason = ' '.join(args[1:]) if len(args) > 1 else ""
            if channel:
                irc_client.part_channel(channel, reason)
        
        elif command == 'NICK':
            new_nick = args[0] if args else None
            if new_nick:
                irc_client.change_nick(new_nick)
        
        elif command == 'MSG' or command == 'QUERY':
            target = args[0] if args else None
            message = ' '.join(args[1:]) if len(args) > 1 else ""
            if target and message:
                irc_client.send_message(target, message)
                # Open PM window
                self._get_or_create_channel_widget(server_name, target, is_pm=True)
        
        elif command == 'QUIT':
            reason = ' '.join(args) if args else "Client quit"
            irc_client.disconnect_from_server(reason)
            del self.irc_clients[server_name]
            server_item = self.server_items.get(server_name)
            if server_item:
                self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(server_item))
                del self.server_items[server_name]
        
        else:
            # Generic command - send as-is
            if expanded.startswith('/'):
                cmd_parts = expanded[1:].split(None, 1)
                if len(cmd_parts) == 1:
                    irc_client.send_command(cmd_parts[0])
                else:
                    irc_client.send_command(cmd_parts[0], cmd_parts[1])
    
    def _on_tree_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle tree item double-click."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        item_type = data[0]
        if item_type == 'server':
            server_name = data[1]
            # Show status window
            widget = self._get_or_create_channel_widget(server_name, "STATUS")
            self._add_or_show_tab(widget, f"{server_name} - Status")
        elif item_type == 'channel':
            server_name = data[1]
            channel_name = data[2]
            widget = self._get_or_create_channel_widget(server_name, channel_name)
            self._add_or_show_tab(widget, self._get_tab_title(widget))
    
    def _on_tree_context_menu(self, position):
        """Handle tree context menu."""
        item = self.tree.itemAt(position)
        if not item:
            return
        
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        
        item_type = data[0]
        if item_type == 'server':
            server_name = data[1]
            
            connect_action = QAction("Connect", self)
            connect_action.triggered.connect(
                lambda: self._connect_to_server_by_name(server_name)
            )
            menu.addAction(connect_action)
            
            disconnect_action = QAction("Disconnect", self)
            disconnect_action.triggered.connect(
                lambda: self._disconnect_server(server_name)
            )
            menu.addAction(disconnect_action)
            
            menu.addSeparator()
            
            join_action = QAction("Join Channel", self)
            join_action.triggered.connect(
                lambda: self._prompt_join_channel(server_name)
            )
            menu.addAction(join_action)
        
        elif item_type == 'channel':
            server_name = data[1]
            channel_name = data[2]
            
            part_action = QAction("Part Channel", self)
            part_action.triggered.connect(
                lambda: self._part_channel(server_name, channel_name)
            )
            menu.addAction(part_action)
        
        menu.exec(self.tree.mapToGlobal(position))
    
    def _connect_to_server_by_name(self, server_name: str):
        """Connect to server by name."""
        servers = self.settings_manager.get_servers()
        for server in servers:
            if server.get('name') == server_name:
                self._connect_to_server(server)
                break
    
    def _disconnect_server(self, server_name: str):
        """Disconnect from a server."""
        irc_client = self.irc_clients.get(server_name)
        if irc_client:
            irc_client.disconnect_from_server()
            del self.irc_clients[server_name]
    
    def _disconnect_all(self):
        """Disconnect from all servers."""
        for server_name in list(self.irc_clients.keys()):
            self._disconnect_server(server_name)
    
    def _prompt_join_channel(self, server_name: str):
        """Prompt user to join a channel."""
        from PyQt6.QtWidgets import QInputDialog
        channel, ok = QInputDialog.getText(self, "Join Channel", "Channel name:")
        if ok and channel:
            irc_client = self.irc_clients.get(server_name)
            if irc_client:
                irc_client.join_channel(channel)
    
    def _part_channel(self, server_name: str, channel_name: str):
        """Part from a channel."""
        irc_client = self.irc_clients.get(server_name)
        if irc_client:
            irc_client.part_channel(channel_name)
    
    def _open_pm(self, server_name: str, nickname: str):
        """Open a private message window with a user."""
        # Create or get the PM widget
        widget = self._get_or_create_channel_widget(server_name, nickname, is_pm=True)
        
        # Show the tab
        title = self._get_tab_title(widget)
        self._add_or_show_tab(widget, title)
        
        # Focus the input
        widget.focus_input()
    
    def _show_room_key_dialog(self):
        """Show room key dialog for current channel or PM."""
        current_widget = self.tabs.currentWidget()
        if not isinstance(current_widget, ChannelWidget):
            return
        
        if current_widget.channel_name == "STATUS":
            QMessageBox.information(self, "Info", "Cannot set encryption key for status window.")
            return
        
        # Get server config for canonical hostname
        irc_client = self.irc_clients.get(current_widget.server_name)
        server_config = irc_client.server_config if irc_client else None
        own_nick = irc_client.nickname if irc_client else None
        
        dialog = RoomKeyDialog(
            current_widget.server_name,
            current_widget.channel_name,
            self.encryption_manager,
            self,
            server_config,
            is_pm=current_widget.is_pm,
            own_nick=own_nick
        )
        if dialog.exec() == dialog.DialogCode.Accepted:
            # Refresh encryption status using encryption manager (handles PMs correctly)
            own_nick = irc_client.nickname if irc_client else None
            key = self.encryption_manager.get_room_key_data(
                current_widget.server_name, current_widget.channel_name, server_config,
                own_nick=own_nick if current_widget.is_pm else None,
                is_pm=current_widget.is_pm
            )
            current_widget.set_encrypted(key is not None)
            # Update tab title
            self._update_tab_title(current_widget)
    
    def _show_preferences(self):
        """Show preferences dialog."""
        dialog = PreferencesDialog(self.settings_manager, self)
        dialog.exec()
    
    def _show_channel_list(self):
        """Show channel list dialog."""
        # Get current server (first connected server, or prompt user)
        current_widget = self.tabs.currentWidget()
        if isinstance(current_widget, ChannelWidget):
            server_name = current_widget.server_name
        else:
            # Get first connected server
            if not self.irc_clients:
                QMessageBox.information(self, "No Connection", 
                                      "Please connect to a server first.")
                return
            server_name = list(self.irc_clients.keys())[0]
        
        irc_client = self.irc_clients.get(server_name)
        if not irc_client:
            QMessageBox.information(self, "Not Connected", 
                                  f"Not connected to {server_name}.")
            return
        
        # Create or reuse channel list dialog
        if hasattr(self, '_channel_list_dialog') and self._channel_list_dialog:
            self._channel_list_dialog.close()
        
        self._channel_list_dialog = ChannelListDialog(server_name, irc_client, self)
        self._channel_list_dialog.exec()
        self._channel_list_dialog = None
    
    def _show_aliases(self):
        """Show aliases management dialog."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QDialogButtonBox, QInputDialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Aliases")
        dialog.setMinimumSize(500, 300)
        
        layout = QVBoxLayout()
        
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Alias", "Expansion"])
        table.horizontalHeader().setStretchLastSection(True)
        
        aliases = self.alias_manager.get_aliases()
        table.setRowCount(len(aliases))
        for row, alias in enumerate(aliases):
            table.setItem(row, 0, QTableWidgetItem(alias['alias_name']))
            table.setItem(row, 1, QTableWidgetItem(alias['expansion']))
        
        layout.addWidget(table)
        
        button_layout = QHBoxLayout()
        add_button = QPushButton("Add")
        add_button.clicked.connect(lambda: self._add_alias_dialog(dialog, table))
        button_layout.addWidget(add_button)
        
        remove_button = QPushButton("Remove")
        remove_button.clicked.connect(lambda: self._remove_alias(table))
        button_layout.addWidget(remove_button)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        dialog.setLayout(layout)
        dialog.exec()
    
    def _add_alias_dialog(self, parent, table):
        """Add alias dialog."""
        from PyQt6.QtWidgets import QInputDialog
        alias_name, ok1 = QInputDialog.getText(parent, "Add Alias", "Alias name (without /):")
        if not ok1 or not alias_name:
            return
        
        expansion, ok2 = QInputDialog.getText(parent, "Add Alias", "Expansion (use $1, $2, etc. for arguments):")
        if not ok2:
            return
        
        self.alias_manager.add_alias(alias_name, expansion)
        
        # Refresh table
        aliases = self.alias_manager.get_aliases()
        table.setRowCount(len(aliases))
        for row, alias in enumerate(aliases):
            table.setItem(row, 0, QTableWidgetItem(alias['alias_name']))
            table.setItem(row, 1, QTableWidgetItem(alias['expansion']))
    
    def _remove_alias(self, table):
        """Remove selected alias."""
        row = table.currentRow()
        if row < 0:
            return
        
        alias_name = table.item(row, 0).text()
        self.alias_manager.delete_alias(alias_name)
        
        # Refresh table
        aliases = self.alias_manager.get_aliases()
        table.setRowCount(len(aliases))
        for row, alias in enumerate(aliases):
            table.setItem(row, 0, QTableWidgetItem(alias['alias_name']))
            table.setItem(row, 1, QTableWidgetItem(alias['expansion']))
    
    def _open_logs_folder(self):
        """Open logs folder."""
        import subprocess
        import platform
        log_dir = self.settings_manager.get_setting('log_directory', 'logs')
        path = Path(log_dir).absolute()
        
        if platform.system() == 'Windows':
            os.startfile(path)
        elif platform.system() == 'Darwin':
            subprocess.Popen(['open', str(path)])
        else:
            subprocess.Popen(['xdg-open', str(path)])
    
    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self, "About",
            "Encrypted IRC Client\n\n"
            "A basic IRC client with per-room client-side encryption.\n\n"
            "Built with Python 3.12+ and PyQt6 v6.8+"
        )
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Disconnect all servers
        self._disconnect_all()
        event.accept()

