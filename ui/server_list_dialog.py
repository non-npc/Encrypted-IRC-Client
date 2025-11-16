"""
Server list and configuration dialog.
Allows adding, editing, and removing IRC server configurations.
"""

import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QDialogButtonBox, QMessageBox, QHeaderView
)
from PyQt6.QtCore import Qt

from ui.server_edit_dialog import ServerEditDialog

logger = logging.getLogger(__name__)


class ServerListDialog(QDialog):
    """Dialog for managing server list."""
    
    def __init__(self, settings_manager, parent=None):
        """Initialize server list dialog."""
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.servers = []
        self._init_ui()
        self._load_servers()
    
    def _init_ui(self):
        """Initialize UI components."""
        self.setWindowTitle("Server List")
        self.setMinimumSize(700, 400)
        
        layout = QVBoxLayout()
        
        # Server table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Name", "Hostname", "Port", "SSL", "Nickname", "Auto-join"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.add_button = QPushButton("Add")
        self.add_button.clicked.connect(self._add_server)
        button_layout.addWidget(self.add_button)
        
        self.edit_button = QPushButton("Edit")
        self.edit_button.clicked.connect(self._edit_server)
        button_layout.addWidget(self.edit_button)
        
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self._remove_server)
        button_layout.addWidget(self.remove_button)
        
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
    
    def _load_servers(self):
        """Load servers from database."""
        self.servers = self.settings_manager.get_servers()
        self.table.setRowCount(len(self.servers))
        
        for row, server in enumerate(self.servers):
            self.table.setItem(row, 0, QTableWidgetItem(server.get('name', '')))
            self.table.setItem(row, 1, QTableWidgetItem(server.get('hostname', '')))
            self.table.setItem(row, 2, QTableWidgetItem(str(server.get('port', 6667))))
            self.table.setItem(row, 3, QTableWidgetItem("Yes" if server.get('ssl') else "No"))
            self.table.setItem(row, 4, QTableWidgetItem(server.get('nickname', '')))
            self.table.setItem(row, 5, QTableWidgetItem(server.get('auto_join_channels', '')))
    
    def _add_server(self):
        """Add a new server."""
        dialog = ServerEditDialog(self, settings_manager=self.settings_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            server_data = dialog.get_server_data()
            self.settings_manager.add_server(server_data)
            self._load_servers()
    
    def _edit_server(self):
        """Edit selected server."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a server to edit.")
            return
        
        server = self.servers[row]
        dialog = ServerEditDialog(self, server, settings_manager=self.settings_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            server_data = dialog.get_server_data()
            self.settings_manager.update_server(server['id'], server_data)
            self._load_servers()
    
    def _remove_server(self):
        """Remove selected server."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a server to remove.")
            return
        
        server = self.servers[row]
        reply = QMessageBox.question(
            self, "Confirm Removal",
            f"Are you sure you want to remove server '{server.get('name')}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.settings_manager.delete_server(server['id'])
            self._load_servers()
    
    def get_selected_server(self):
        """Get the currently selected server."""
        row = self.table.currentRow()
        if row >= 0 and row < len(self.servers):
            return self.servers[row]
        return None

