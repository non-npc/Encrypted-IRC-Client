"""
Server edit dialog for adding/editing server configurations.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QCheckBox, QDialogButtonBox, QLabel, QMessageBox
)
from PyQt6.QtCore import Qt
from typing import Dict, Any, Optional


class ServerEditDialog(QDialog):
    """Dialog for editing server configuration."""
    
    def __init__(self, parent=None, server_data: Optional[Dict[str, Any]] = None, settings_manager=None):
        """Initialize server edit dialog."""
        super().__init__(parent)
        self.server_data = server_data or {}
        self.settings_manager = settings_manager
        self._init_ui()
        self._load_data()
        self._setup_auto_connect_handler()
    
    def _init_ui(self):
        """Initialize UI components."""
        self.setWindowTitle("Edit Server" if self.server_data else "Add Server")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        
        form = QFormLayout()
        
        # Name
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("My IRC Server")
        form.addRow("Name:", self.name_edit)
        
        # Hostname
        self.hostname_edit = QLineEdit()
        self.hostname_edit.setPlaceholderText("irc.example.com")
        form.addRow("Hostname:", self.hostname_edit)
        
        # Port
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(6667)
        form.addRow("Port:", self.port_spin)
        
        # SSL
        self.ssl_check = QCheckBox()
        form.addRow("SSL/TLS:", self.ssl_check)
        
        # Nickname
        self.nickname_edit = QLineEdit()
        self.nickname_edit.setPlaceholderText("MyNick")
        form.addRow("Nickname:", self.nickname_edit)
        
        # Alternative nickname
        self.alt_nickname_edit = QLineEdit()
        self.alt_nickname_edit.setPlaceholderText("MyNick_")
        form.addRow("Alt. Nickname:", self.alt_nickname_edit)
        
        # Username
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("username")
        form.addRow("Username:", self.username_edit)
        
        # Realname
        self.realname_edit = QLineEdit()
        self.realname_edit.setPlaceholderText("Real Name")
        form.addRow("Real Name:", self.realname_edit)
        
        # Auto-join channels
        self.auto_join_edit = QLineEdit()
        self.auto_join_edit.setPlaceholderText("#channel1, #channel2")
        form.addRow("Auto-join Channels:", self.auto_join_edit)
        
        # Encoding
        self.encoding_edit = QLineEdit()
        self.encoding_edit.setText("UTF-8")
        form.addRow("Encoding:", self.encoding_edit)
        
        # Auto-connect
        self.auto_connect_check = QCheckBox()
        self.auto_connect_check.setToolTip("Only one server can be set to auto-connect. Enabling this will disable auto-connect on other servers.")
        form.addRow("Auto-connect on startup:", self.auto_connect_check)
        
        layout.addLayout(form)
        
        # Info label
        info_label = QLabel("Note: SSL/TLS connections are encrypted. Self-signed certificates are accepted.")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(info_label)
        
        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
    
    def _setup_auto_connect_handler(self):
        """Setup handler for auto-connect checkbox."""
        # Note: We enforce single auto-connect in _validate_and_accept, not here
        # This way changes only apply when the user actually saves
        pass
    
    def _load_data(self):
        """Load existing server data into form."""
        if not self.server_data:
            return
        
        self.name_edit.setText(self.server_data.get('name', ''))
        self.hostname_edit.setText(self.server_data.get('hostname', ''))
        self.port_spin.setValue(self.server_data.get('port', 6667))
        self.ssl_check.setChecked(bool(self.server_data.get('ssl')))
        self.nickname_edit.setText(self.server_data.get('nickname', ''))
        self.alt_nickname_edit.setText(self.server_data.get('alt_nickname', ''))
        self.username_edit.setText(self.server_data.get('username', ''))
        self.realname_edit.setText(self.server_data.get('realname', ''))
        self.auto_join_edit.setText(self.server_data.get('auto_join_channels', ''))
        self.encoding_edit.setText(self.server_data.get('default_encoding', 'UTF-8'))
        self.auto_connect_check.setChecked(bool(self.server_data.get('auto_connect')))
    
    def _validate_and_accept(self):
        """Validate form data and accept if valid."""
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation Error", "Server name is required.")
            return
        
        if not self.hostname_edit.text().strip():
            QMessageBox.warning(self, "Validation Error", "Hostname is required.")
            return
        
        if not self.nickname_edit.text().strip():
            QMessageBox.warning(self, "Validation Error", "Nickname is required.")
            return
        
        # If auto-connect is being enabled, disable it on all other servers
        if self.auto_connect_check.isChecked() and self.settings_manager:
            servers = self.settings_manager.get_servers()
            current_server_id = self.server_data.get('id') if self.server_data else None
            
            for server in servers:
                server_id = server.get('id')
                # Skip the current server being edited
                if server_id and server_id == current_server_id:
                    continue
                
                # If another server has auto_connect enabled, disable it
                if server.get('auto_connect'):
                    server['auto_connect'] = False
                    self.settings_manager.update_server(server_id, server)
        
        self.accept()
    
    def get_server_data(self) -> Dict[str, Any]:
        """Get server data from form."""
        return {
            'name': self.name_edit.text().strip(),
            'hostname': self.hostname_edit.text().strip(),
            'port': self.port_spin.value(),
            'ssl': self.ssl_check.isChecked(),
            'nickname': self.nickname_edit.text().strip(),
            'alt_nickname': self.alt_nickname_edit.text().strip(),
            'username': self.username_edit.text().strip() or self.nickname_edit.text().strip(),
            'realname': self.realname_edit.text().strip() or self.nickname_edit.text().strip(),
            'auto_join_channels': self.auto_join_edit.text().strip(),
            'default_encoding': self.encoding_edit.text().strip() or 'UTF-8',
            'auto_connect': self.auto_connect_check.isChecked()
        }

