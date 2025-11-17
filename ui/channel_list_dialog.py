"""
Channel list dialog showing available channels on the server.
"""

import logging
import time
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QDialogButtonBox, QLabel, QHeaderView, QLineEdit
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

logger = logging.getLogger(__name__)


class ChannelListDialog(QDialog):
    """Dialog for displaying and joining channels from the server."""
    
    def __init__(self, server_name: str, irc_client, main_window=None, parent=None):
        """Initialize channel list dialog."""
        super().__init__(parent)
        self.server_name = server_name
        self.irc_client = irc_client
        self.main_window = main_window  # Reference to main window for cache access
        self.channels = []  # List of (name, user_count, topic) tuples
        self.pending_update = False  # Flag to track if update is pending
        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self._update_table)
        self.update_interval = 100  # Update every 100ms
        self._init_ui()
    
    def _init_ui(self):
        """Initialize UI components."""
        self.setWindowTitle(f"Channel List - {self.server_name}")
        self.setMinimumSize(600, 400)
        
        layout = QVBoxLayout()
        
        # Info label
        info_label = QLabel("Requesting channel list from server...")
        layout.addWidget(info_label)
        self.info_label = info_label
        
        # Filter input
        filter_layout = QHBoxLayout()
        filter_label = QLabel("Filter:")
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter channels...")
        self.filter_edit.textChanged.connect(self._filter_channels)
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.filter_edit)
        layout.addLayout(filter_layout)
        
        # Channel table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Channel", "Users", "Topic"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(False)  # We sort manually for better performance
        self.table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(lambda: self._refresh_list(force_refresh=True))
        button_layout.addWidget(self.refresh_button)
        
        self.join_button = QPushButton("Join")
        self.join_button.clicked.connect(self._join_selected)
        button_layout.addWidget(self.join_button)
        
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # Dialog buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
        
        # Request channel list
        self._refresh_list()
    
    def _refresh_list(self, force_refresh=False):
        """Request channel list from server or use cache if available."""
        self.channels = []
        self.table.setRowCount(0)
        self.refresh_button.setEnabled(False)
        
        # Check persistent cache from disk if available and not forcing refresh
        cache_valid = False
        if not force_refresh and self.main_window:
            # Get cache expiration from settings (default: 1 hour = 3600 seconds)
            cache_max_age = int(self.main_window.settings_manager.get_setting('channel_list_expiration', '3600'))
            # Try to load from persistent cache (disk)
            cache_entry = self.main_window.settings_manager.get_channel_list_cache(self.server_name, cache_max_age)
            if cache_entry:
                # Cache is valid, use it
                self.channels = cache_entry['channels'].copy()
                # Also update in-memory cache
                self.main_window.channel_list_cache[self.server_name] = cache_entry
                cache_age = time.time() - cache_entry['timestamp']
                self.info_label.setText(f"Using cached channel list ({len(self.channels)} channels, {int(cache_age)}s old)")
                self._update_table()
                self.info_label.setText(f"Found {len(self.channels)} channels (cached)")
                self.refresh_button.setEnabled(True)
                cache_valid = True
        
        if not cache_valid:
            # Request from server
            self.info_label.setText("Requesting channel list from server...")
            # Show summary message in status window if main_window is available
            if self.main_window:
                self.main_window.channel_list_requested[self.server_name] = True
                # Clear cache for new request
                if self.server_name in self.main_window.channel_list_cache:
                    self.main_window.channel_list_cache[self.server_name] = {'channels': [], 'timestamp': None}
                status_widget = self.main_window._get_or_create_channel_widget(self.server_name, "STATUS", is_pm=False)
                status_widget.add_status_message(
                    "Requesting channel list from server...",
                    QColor(0, 0, 255)
                )
            
            if self.irc_client:
                self.irc_client.send_command("LIST")
    
    def add_channel(self, channel_name: str, user_count: str, topic: str):
        """Add a channel to the list."""
        # Check if channel already exists
        for i, (name, count, top) in enumerate(self.channels):
            if name == channel_name:
                # Update existing entry
                self.channels[i] = (channel_name, user_count, topic)
                self._schedule_update()
                return
        
        # Add new channel
        self.channels.append((channel_name, user_count, topic))
        self._schedule_update()
    
    def _schedule_update(self):
        """Schedule a table update (batched to avoid UI freezing)."""
        if not self.pending_update:
            self.pending_update = True
            self.update_timer.start(self.update_interval)
    
    def set_list_complete(self):
        """Called when LIST command is complete."""
        # Force immediate update when list is complete
        if self.update_timer.isActive():
            self.update_timer.stop()
        self.pending_update = False
        self._update_table()
        self.info_label.setText(f"Found {len(self.channels)} channels")
        self.refresh_button.setEnabled(True)
    
    def _update_table(self):
        """Update the table with current channels."""
        self.pending_update = False
        
        # Apply filter
        filter_text = self.filter_edit.text().lower()
        filtered = [
            (name, count, topic) for name, count, topic in self.channels
            if filter_text in name.lower() or filter_text in topic.lower()
        ]
        
        # Sort by user count (descending) then by name
        filtered.sort(key=lambda x: (int(x[1]) if x[1].isdigit() else 0, x[0].lower()), reverse=True)
        
        # Update row count only if changed
        new_row_count = len(filtered)
        if new_row_count != self.table.rowCount():
            self.table.setRowCount(new_row_count)
        
        # Batch update: only create/update items that changed
        # This is much faster than recreating all items
        for row, (channel_name, user_count, topic) in enumerate(filtered):
            # Check and update channel name
            item0 = self.table.item(row, 0)
            if item0 is None:
                self.table.setItem(row, 0, QTableWidgetItem(channel_name))
            elif item0.text() != channel_name:
                item0.setText(channel_name)
            
            # Check and update user count
            item1 = self.table.item(row, 1)
            if item1 is None:
                self.table.setItem(row, 1, QTableWidgetItem(user_count))
            elif item1.text() != user_count:
                item1.setText(user_count)
            
            # Check and update topic
            item2 = self.table.item(row, 2)
            if item2 is None:
                self.table.setItem(row, 2, QTableWidgetItem(topic))
            elif item2.text() != topic:
                item2.setText(topic)
        
        # Update info label periodically (every 50 channels or if less than 50)
        if len(self.channels) % 50 == 0 or len(self.channels) < 50:
            self.info_label.setText(f"Loading... {len(self.channels)} channels found")
    
    def _filter_channels(self):
        """Filter channels based on filter text."""
        # Use immediate update for filtering (user expects responsive filtering)
        # But we can still batch if typing quickly
        if self.update_timer.isActive():
            self.update_timer.stop()
        self.pending_update = False
        self._update_table()
    
    def _on_double_click(self, index):
        """Handle double-click on channel."""
        self._join_selected()
    
    def _join_selected(self):
        """Join the selected channel."""
        row = self.table.currentRow()
        if row < 0:
            return
        
        channel_name = self.table.item(row, 0).text()
        if channel_name:
            if self.irc_client and self.main_window:
                # Create the channel widget immediately (before server response)
                # This ensures the tab is ready when the JOIN response arrives
                widget = self.main_window._get_or_create_channel_widget(
                    self.server_name, channel_name, is_pm=False
                )
                # Show the tab immediately
                title = self.main_window._get_tab_title(widget)
                self.main_window._add_or_show_tab(widget, title)
                # Send the join command
                self.irc_client.join_channel(channel_name)
            self.accept()

