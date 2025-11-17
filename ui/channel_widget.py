"""
Channel and private message window widget.
Displays messages, nicklist, and input for a channel or PM.
"""

import logging
import re
import webbrowser
from datetime import datetime
from typing import Optional, Dict, Set
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
    QListWidget, QLabel, QPushButton, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QTextCharFormat, QColor, QFont

from core.irc_parser import IRCMessage

logger = logging.getLogger(__name__)


class ClickableTextEdit(QTextEdit):
    """QTextEdit with clickable link support."""
    
    # Signal must be defined as a class attribute
    link_clicked = pyqtSignal(QUrl)
    
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def mousePressEvent(self, event):
        """Handle mouse press events to detect link clicks."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Get the anchor at the click position
            anchor = self.anchorAt(event.position().toPoint())
            if anchor:
                # Link was clicked
                url = QUrl(anchor)
                self.link_clicked.emit(url)
                return
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Change cursor when hovering over links."""
        anchor = self.anchorAt(event.position().toPoint())
        if anchor:
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        super().mouseMoveEvent(event)


class ChannelWidget(QWidget):
    """Widget representing a channel or private message window."""
    
    # Signals
    message_sent = pyqtSignal(str)  # message text
    command_sent = pyqtSignal(str)  # command line
    encrypt_key_requested = pyqtSignal()  # encryption key dialog requested
    pm_requested = pyqtSignal(str)  # nickname for private message
    
    def __init__(self, server_name: str, channel_name: str, is_pm: bool = False,
                 encryption_manager=None, settings_manager=None):
        """
        Initialize channel widget.
        
        Args:
            server_name: Name of the server
            channel_name: Name of the channel or PM target
            is_pm: Whether this is a private message window
            encryption_manager: Encryption manager instance
            settings_manager: Settings manager instance
        """
        super().__init__()
        self.server_name = server_name
        self.channel_name = channel_name
        self.is_pm = is_pm
        self.encryption_manager = encryption_manager
        self.settings_manager = settings_manager
        
        self.encrypted = False
        self.topic = ""
        self.nicks: Set[str] = set()
        self.unread_count = 0
        self.scrolled_up = False
        
        self._init_ui()
        self._load_settings()
    
    def _init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Topic bar (only show for channels, not status)
        self.topic_label = QLabel()
        self.topic_label.setWordWrap(True)
        self.topic_label.setStyleSheet("background-color: #f0f0f0; padding: 4px; border-bottom: 1px solid #ccc;")
        if self.channel_name == "STATUS":
            self.topic_label.hide()
        layout.addWidget(self.topic_label)
        
        # Main content area (messages and nicklist)
        content_layout = QHBoxLayout()
        content_layout.setSpacing(0)
        
        # Message display
        self.message_display = ClickableTextEdit()
        self.message_display.setReadOnly(True)
        self.message_display.setFont(QFont("Consolas", 10))
        self.message_display.link_clicked.connect(self._on_link_clicked)
        self.message_display.verticalScrollBar().valueChanged.connect(self._on_scroll)
        content_layout.addWidget(self.message_display, 3)
        
        # Nicklist (only show for channels, not status or PMs)
        self.nicklist = QListWidget()
        self.nicklist.setMaximumWidth(150)
        self.nicklist.setStyleSheet("border-left: 1px solid #ccc;")
        self.nicklist.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.nicklist.customContextMenuRequested.connect(self._on_nicklist_context_menu)
        # Show nicklist for channels (channels start with # or &), hide for STATUS and PMs
        if self.channel_name == "STATUS" or (not self.channel_name.startswith('#') and not self.channel_name.startswith('&')):
            self.nicklist.hide()
        else:
            self.nicklist.show()
        content_layout.addWidget(self.nicklist, 1)
        
        layout.addLayout(content_layout, 2)
        
        # Input area
        input_layout = QHBoxLayout()
        self.input_line = QLineEdit()
        self.input_line.returnPressed.connect(self._on_input_return)
        # Set placeholder text based on widget type
        if self.channel_name == "STATUS":
            self.input_line.setPlaceholderText("Enter IRC command (e.g., /join #channel, /msg user message)")
        elif self.is_pm:
            self.input_line.setPlaceholderText("Type message...")
        else:
            self.input_line.setPlaceholderText("Type message or command...")
        
        # Encryption indicator button (only show for channels, not status)
        self.encrypt_button = QPushButton("🔓")
        self.encrypt_button.setMaximumWidth(40)
        self.encrypt_button.setToolTip("Set encryption key (Ctrl+K)")
        self.encrypt_button.clicked.connect(self._on_encrypt_clicked)
        if self.channel_name == "STATUS":
            self.encrypt_button.hide()
        
        input_layout.addWidget(self.encrypt_button)
        input_layout.addWidget(self.input_line)
        layout.addLayout(input_layout)
        
        self.setLayout(layout)
        
        # Set window title
        self._update_title()
    
    def _load_settings(self):
        """Load settings from settings manager."""
        if not self.settings_manager:
            return
        
        font_family = self.settings_manager.get_setting('font_family', 'Consolas')
        font_size = int(self.settings_manager.get_setting('font_size', '10'))
        self.message_display.setFont(QFont(font_family, font_size))
        
        # Check if encryption is enabled for this room
        # Try both server_name and canonical ID (if available)
        if self.encryption_manager:
            key_data = self.encryption_manager.settings_manager.get_room_key(
                self.server_name, self.channel_name
            )
            # Also try to get canonical ID if we can (for backward compatibility)
            if not key_data:
                # Try to get canonical ID from encryption manager
                # This will use server_name as fallback if no config available
                canonical_id = self.encryption_manager._get_canonical_server_id(self.server_name)
                if canonical_id != self.server_name:
                    key_data = self.encryption_manager.settings_manager.get_room_key(
                        canonical_id, self.channel_name
                    )
            if key_data:
                self.encrypted = True
                self.encrypt_button.setText("🔒")
                self.encrypt_button.setToolTip("Encryption enabled - Click to change key")
    
    def _update_title(self):
        """Update the window/tab title."""
        title = self.channel_name
        if self.encrypted:
            title += " 🔒"
        if self.unread_count > 0:
            title += f" ({self.unread_count})"
        self.setWindowTitle(title)
    
    def _on_scroll(self, value):
        """Handle scrollbar movement."""
        scrollbar = self.message_display.verticalScrollBar()
        max_value = scrollbar.maximum()
        self.scrolled_up = value < max_value - 10
    
    def _on_input_return(self):
        """Handle Enter key in input line."""
        text = self.input_line.text().strip()
        if not text:
            return
        
        self.input_line.clear()
        
        if text.startswith('/'):
            self.command_sent.emit(text)
        else:
            self.message_sent.emit(text)
    
    def _on_encrypt_clicked(self):
        """Handle encryption button click."""
        # Emit signal to request encryption key dialog
        self.encrypt_key_requested.emit()
    
    def _on_nicklist_context_menu(self, position):
        """Handle right-click context menu on nicklist."""
        item = self.nicklist.itemAt(position)
        if not item:
            return
        
        # Get the nickname (strip any prefixes like @, +, etc. for the actual nick)
        nick_with_prefix = item.text()
        # Remove IRC prefixes to get base nickname
        base_nick = nick_with_prefix.lstrip('@+%&~')
        
        # Don't show menu for empty nick
        if not base_nick:
            return
        
        menu = QMenu(self)
        
        # Add "Send Message" action
        send_msg_action = menu.addAction("Send Message")
        send_msg_action.triggered.connect(
            lambda: self.pm_requested.emit(base_nick)
        )
        
        # Show menu at cursor position
        menu.exec(self.nicklist.mapToGlobal(position))
    
    def add_message(self, message: IRCMessage, own_nick: str = ""):
        """
        Add a message to the display.
        
        Args:
            message: IRC message object
            own_nick: User's own nickname for highlighting
        """
        timestamp_format = "%H:%M:%S"
        if self.settings_manager:
            show_timestamps = self.settings_manager.get_setting('show_timestamps', '1') == '1'
            timestamp_format = self.settings_manager.get_setting('timestamp_format', '%H:%M:%S')
        else:
            show_timestamps = True
        
        timestamp = datetime.now().strftime(timestamp_format) if show_timestamps else ""
        
        # Format message based on type
        if message.command == 'PRIVMSG':
            nick = message.nick or "Unknown"
            text = message.text or ""
            
            # Check if message mentions own nick
            is_mention = own_nick and own_nick.lower() in text.lower()
            
            # Format: [timestamp] <nick> message
            if show_timestamps:
                formatted = f"[{timestamp}] <{nick}> {text}"
            else:
                formatted = f"<{nick}> {text}"
            
            self._append_text(formatted, nick_color=self._get_nick_color(nick), 
                            is_mention=is_mention)
        
        elif message.command == 'NOTICE':
            text = message.text or ""
            formatted = f"[{timestamp}] -{message.nick or 'Server'}- {text}" if show_timestamps else f"-{message.nick or 'Server'}- {text}"
            self._append_text(formatted, color=QColor(128, 128, 128))
        
        elif message.command == 'JOIN':
            nick = message.nick or "Unknown"
            formatted = f"[{timestamp}] *** {nick} joined {self.channel_name}" if show_timestamps else f"*** {nick} joined {self.channel_name}"
            self._append_text(formatted, color=QColor(0, 128, 0))
            # Use add_nick to handle duplicates properly
            self.add_nick(nick)
        
        elif message.command == 'PART':
            nick = message.nick or "Unknown"
            reason = message.text or ""
            if reason:
                formatted = f"[{timestamp}] *** {nick} left {self.channel_name} ({reason})" if show_timestamps else f"*** {nick} left {self.channel_name} ({reason})"
            else:
                formatted = f"[{timestamp}] *** {nick} left {self.channel_name}" if show_timestamps else f"*** {nick} left {self.channel_name}"
            self._append_text(formatted, color=QColor(128, 0, 0))
            # Use remove_nick to handle all prefix variants
            self.remove_nick(nick)
        
        elif message.command == 'QUIT':
            nick = message.nick or "Unknown"
            reason = message.text or ""
            formatted = f"[{timestamp}] *** {nick} quit ({reason})" if show_timestamps else f"*** {nick} quit ({reason})"
            self._append_text(formatted, color=QColor(128, 0, 0))
            # Use remove_nick to handle all prefix variants
            self.remove_nick(nick)
        
        elif message.command == 'NICK':
            old_nick = message.nick or "Unknown"
            new_nick = message.params[0] if message.params else "Unknown"
            formatted = f"[{timestamp}] *** {old_nick} is now known as {new_nick}" if show_timestamps else f"*** {old_nick} is now known as {new_nick}"
            self._append_text(formatted, color=QColor(128, 128, 0))
            # Remove all forms of the old nick (with any prefix)
            old_base = old_nick.lstrip('@+%&~')
            to_remove = [n for n in self.nicks if n.lstrip('@+%&~').lower() == old_base.lower()]
            for n in to_remove:
                self.nicks.discard(n)
            # Add the new nick (use add_nick to handle prefixes)
            self.add_nick(new_nick)
        
        elif message.command == 'TOPIC':
            topic = message.text or ""
            self.topic = topic
            self.topic_label.setText(f"Topic: {topic}")
            nick = message.nick or "Server"
            formatted = f"[{timestamp}] *** {nick} changed topic to: {topic}" if show_timestamps else f"*** {nick} changed topic to: {topic}"
            self._append_text(formatted, color=QColor(0, 0, 255))
        
        elif message.command == 'KICK':
            channel = message.params[0] if message.params else ""
            kicked = message.params[1] if len(message.params) > 1 else "Unknown"
            reason = message.params[2] if len(message.params) > 2 else ""
            formatted = f"[{timestamp}] *** {kicked} was kicked by {message.nick} ({reason})" if show_timestamps else f"*** {kicked} was kicked by {message.nick} ({reason})"
            self._append_text(formatted, color=QColor(255, 0, 0))
            # Use remove_nick to handle all prefix variants
            self.remove_nick(kicked)
        
        elif message.command == 'MODE':
            # Handle channel mode changes that affect user prefixes
            # Format: MODE #channel +o nick  or  MODE #channel -o nick
            if len(message.params) >= 3:
                channel = message.params[0]
                modes = message.params[1]  # e.g., "+o", "-o", "+v", "-v"
                target_nick = message.params[2] if len(message.params) > 2 else None
                
                if target_nick and channel == self.channel_name:
                    # Map IRC mode letters to prefixes
                    # o = @ (op), v = + (voice), h = % (halfop), a = & (admin), q = ~ (founder)
                    mode_to_prefix = {'o': '@', 'v': '+', 'h': '%', 'a': '&', 'q': '~'}
                    
                    # Parse mode string (e.g., "+o", "-o", "+ov", "-o+v")
                    current_op = None  # '+' or '-'
                    for char in modes:
                        if char in '+-':
                            current_op = char
                        elif char in mode_to_prefix:
                            prefix = mode_to_prefix[char]
                            is_add = (current_op == '+')
                            
                            # Find existing nick (with or without prefix)
                            base_nick = target_nick.lstrip('@+%&~')
                            existing_nick = None
                            for existing in self.nicks:
                                if existing.lstrip('@+%&~').lower() == base_nick.lower():
                                    existing_nick = existing
                                    break
                            
                            if existing_nick:
                                if is_add:
                                    # Add prefix: use add_nick which handles priority
                                    self.nicks.discard(existing_nick)
                                    self.add_nick(prefix + base_nick)
                                else:
                                    # Remove prefix: if it's the same prefix, remove it
                                    if existing_nick.startswith(prefix):
                                        self.nicks.discard(existing_nick)
                                        # Add without prefix if it's not already there
                                        if base_nick not in self.nicks:
                                            self.nicks.add(base_nick)
                                        self._update_nicklist()
                            else:
                                # Nick not in list, add it with prefix if adding mode
                                if is_add:
                                    self.add_nick(prefix + target_nick)
        
        elif message.command.isdigit():
            # Numeric reply - format appropriately
            text = message.text or ""
            # Filter out noise messages
            if text:
                text_lower = text.lower()
                # Skip common end-of-list messages
                if any(phrase in text_lower for phrase in [
                    'end of /motd command',
                    'end of /names list',
                    'end of /list'
                ]):
                    return  # Don't display these
                
                # Skip messages that are just a nickname (common in NAMES replies)
                # Check if text is just a nickname (might have @ or + prefix)
                stripped_text = text.strip().lstrip('@+')
                if stripped_text and len(stripped_text) < 20 and not ' ' in stripped_text:
                    # Might be just a nickname, but check if it's actually meaningful
                    # If it's in a numeric reply context and looks like just a nick, skip it
                    if message.command in ['353', '366']:  # NAMES replies
                        return  # Don't display individual nicknames from NAMES list
            
            # Format numeric reply
            if text:
                formatted = f"[{timestamp}] {text}" if show_timestamps else text
            else:
                # Fallback to raw if no text
                formatted = f"[{timestamp}] {message.raw}" if show_timestamps else message.raw
            self._append_text(formatted, color=QColor(128, 128, 128))
        else:
            # Generic message
            text = message.text or message.raw
            formatted = f"[{timestamp}] {text}" if show_timestamps else text
            self._append_text(formatted, color=QColor(128, 128, 128))
        
        # Auto-scroll if user hasn't scrolled up
        if not self.scrolled_up:
            scrollbar = self.message_display.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        else:
            self.unread_count += 1
            self._update_title()
            # Note: Main window will update tab title via _update_tab_title
    
    def _append_text(self, text: str, color: Optional[QColor] = None, 
                    nick_color: Optional[QColor] = None, is_mention: bool = False):
        """Append text to the message display with formatting and clickable links."""
        cursor = self.message_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        
        # URL pattern: matches http://, https://, www., and common TLDs
        url_pattern = re.compile(
            r'(https?://[^\s<>"{}|\\^`\[\]]+|www\.[^\s<>"{}|\\^`\[\]]+|[a-zA-Z0-9-]+\.[a-zA-Z]{2,}[^\s<>"{}|\\^`\[\]]*)',
            re.IGNORECASE
        )
        
        # Find all URLs in the text
        urls = list(url_pattern.finditer(text))
        
        if not urls:
            # No URLs found, just insert text normally
            format = QTextCharFormat()
            if is_mention:
                format.setForeground(QColor(255, 0, 0))  # Red for mentions
                format.setFontWeight(QFont.Weight.Bold)
            elif nick_color:
                format.setForeground(nick_color)
            elif color:
                format.setForeground(color)
            
            cursor.setCharFormat(format)
            cursor.insertText(text + "\n")
        else:
            # URLs found - insert text with clickable links
            last_pos = 0
            for match in urls:
                # Insert text before the URL
                if match.start() > last_pos:
                    format = QTextCharFormat()
                    if is_mention:
                        format.setForeground(QColor(255, 0, 0))
                        format.setFontWeight(QFont.Weight.Bold)
                    elif nick_color:
                        format.setForeground(nick_color)
                    elif color:
                        format.setForeground(color)
                    cursor.setCharFormat(format)
                    cursor.insertText(text[last_pos:match.start()])
                
                # Insert the URL as a clickable link
                url = match.group(0)
                # Ensure URL has a protocol
                if not url.startswith(('http://', 'https://')):
                    if url.startswith('www.'):
                        url = 'https://' + url
                    else:
                        url = 'https://' + url
                
                link_format = QTextCharFormat()
                link_format.setForeground(QColor(0, 0, 255))  # Blue for links
                link_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
                link_format.setAnchor(True)
                link_format.setAnchorHref(url)
                cursor.setCharFormat(link_format)
                cursor.insertText(match.group(0))
                
                last_pos = match.end()
            
            # Insert remaining text after last URL
            if last_pos < len(text):
                format = QTextCharFormat()
                if is_mention:
                    format.setForeground(QColor(255, 0, 0))
                    format.setFontWeight(QFont.Weight.Bold)
                elif nick_color:
                    format.setForeground(nick_color)
                elif color:
                    format.setForeground(color)
                cursor.setCharFormat(format)
                cursor.insertText(text[last_pos:])
            
            # Insert newline
            format = QTextCharFormat()
            if color:
                format.setForeground(color)
            cursor.setCharFormat(format)
            cursor.insertText("\n")
    
    def _on_link_clicked(self, url: QUrl):
        """Handle link click - open URL in default browser."""
        url_str = url.toString()
        try:
            webbrowser.open(url_str)
        except Exception as e:
            logger.error(f"Failed to open URL {url_str}: {e}")
    
    def _get_nick_color(self, nick: str) -> QColor:
        """Get a deterministic color for a nickname."""
        # Simple hash-based color assignment
        hash_val = hash(nick)
        hue = hash_val % 360
        return QColor.fromHsv(hue, 200, 150)
    
    def _update_nicklist(self):
        """Update the nicklist display."""
        self.nicklist.clear()
        
        # Sort nicks (ops first, then voiced, then regular)
        sorted_nicks = sorted(self.nicks, key=lambda n: (
            0 if n.startswith('@') else 1 if n.startswith('+') else 2,
            n.lstrip('@+').lower()
        ))
        
        for nick in sorted_nicks:
            self.nicklist.addItem(nick)
    
    def set_topic(self, topic: str):
        """Set the channel topic."""
        self.topic = topic
        self.topic_label.setText(f"Topic: {topic}")
    
    def add_nick(self, nick: str):
        """Add a nickname to the list, handling prefixes to avoid duplicates."""
        if not nick:
            return
        
        # Ensure nicklist is visible for channels (not STATUS and not PMs)
        # Check channel name directly (channels start with #) rather than is_pm flag
        # to handle cases where widget might have been created with wrong is_pm flag
        if self.channel_name != "STATUS" and (self.channel_name.startswith('#') or self.channel_name.startswith('&')):
            self.nicklist.show()
        
        # Get the base nickname (without prefix)
        base_nick = nick.lstrip('@+%&~')
        
        # Check if this nick already exists in any form
        existing_nick = None
        for existing in self.nicks:
            if existing.lstrip('@+%&~').lower() == base_nick.lower():
                existing_nick = existing
                break
        
        if existing_nick:
            # Nick already exists - determine which version to keep
            existing_prefix = existing_nick[0] if existing_nick and existing_nick[0] in '@+%&~' else ''
            new_prefix = nick[0] if nick[0] in '@+%&~' else ''
            
            # Priority: @ (op) > % (halfop) > + (voice) > & (admin) > ~ (founder) > regular
            prefix_priority = {'@': 5, '%': 4, '+': 3, '&': 2, '~': 1, '': 0}
            existing_priority = prefix_priority.get(existing_prefix, 0)
            new_priority = prefix_priority.get(new_prefix, 0)
            
            if new_priority > existing_priority:
                # New version has higher priority, replace
                self.nicks.discard(existing_nick)
                self.nicks.add(nick)
            # Otherwise, keep the existing version (don't add the new one)
        else:
            # New nick, just add it
            self.nicks.add(nick)
        
        self._update_nicklist()
    
    def remove_nick(self, nick: str):
        """Remove a nickname from the list (removes all prefix variants)."""
        if not nick:
            return
        
        # Get the base nickname (without prefix)
        base_nick = nick.lstrip('@+%&~')
        
        # Remove all forms of this nick (with any prefix)
        to_remove = [n for n in self.nicks if n.lstrip('@+%&~').lower() == base_nick.lower()]
        for n in to_remove:
            self.nicks.discard(n)
        
        self._update_nicklist()
    
    def set_encrypted(self, encrypted: bool):
        """Set encryption status."""
        self.encrypted = encrypted
        if encrypted:
            self.encrypt_button.setText("🔒")
            self.encrypt_button.setToolTip("Encryption enabled - Click to change key")
        else:
            self.encrypt_button.setText("🔓")
            self.encrypt_button.setToolTip("Set encryption key (Ctrl+K)")
        self._update_title()
    
    def clear_unread(self):
        """Clear unread message count."""
        self.unread_count = 0
        self._update_title()
        # Emit signal to update tab title in main window
        # The main window will handle this via a callback
    
    def focus_input(self):
        """Focus the input line."""
        self.input_line.setFocus()
    
    def add_status_message(self, message: str, color: Optional[QColor] = None):
        """
        Add a status/system message to the display.
        
        Args:
            message: Status message text
            color: Optional color for the message (defaults to blue for status)
        """
        timestamp_format = "%H:%M:%S"
        if self.settings_manager:
            show_timestamps = self.settings_manager.get_setting('show_timestamps', '1') == '1'
            timestamp_format = self.settings_manager.get_setting('timestamp_format', '%H:%M:%S')
        else:
            show_timestamps = True
        
        timestamp = datetime.now().strftime(timestamp_format) if show_timestamps else ""
        
        if show_timestamps:
            formatted = f"[{timestamp}] *** {message}"
        else:
            formatted = f"*** {message}"
        
        # Default to blue for status messages
        status_color = color or QColor(0, 0, 255)
        self._append_text(formatted, color=status_color)
        
        # Auto-scroll if user hasn't scrolled up
        if not self.scrolled_up:
            scrollbar = self.message_display.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

