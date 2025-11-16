"""
Dialog for managing per-room encryption keys.
"""

import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QDialogButtonBox, QMessageBox, QCheckBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

logger = logging.getLogger(__name__)


class RoomKeyDialog(QDialog):
    """Dialog for setting/removing room encryption keys."""
    
    def __init__(self, server_name: str, channel_name: str,
                 encryption_manager, parent=None, server_config=None,
                 is_pm: bool = False, own_nick: str = None):
        """Initialize room key dialog."""
        super().__init__(parent)
        self.server_name = server_name
        self.channel_name = channel_name
        self.encryption_manager = encryption_manager
        self.server_config = server_config
        self.is_pm = is_pm
        self.own_nick = own_nick
        self.key_set = False
        self._init_ui()
        self._check_existing_key()
    
    def _init_ui(self):
        """Initialize UI components."""
        title = f"Encryption Key - {self.channel_name}"
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        
        # Info label
        if self.is_pm:
            info_text = (
                f"Set an encryption key for private messages with {self.channel_name} on {self.server_name}.\n\n"
                "Messages between you and this user will be encrypted before sending.\n"
                "You must share the passphrase out-of-band with the other user to decrypt messages.\n\n"
                "⚠️ Warning: If you forget the key, you cannot decrypt previous messages!"
            )
        else:
            info_text = (
                f"Set an encryption key for {self.channel_name} on {self.server_name}.\n\n"
                "Messages in this room will be encrypted before sending.\n"
                "Users must share the passphrase out-of-band to decrypt messages.\n\n"
                "⚠️ Warning: If you forget the key, you cannot decrypt previous messages!"
            )
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #d00; padding: 10px;")
        layout.addWidget(info_label)
        
        # Passphrase input
        passphrase_layout = QHBoxLayout()
        passphrase_label = QLabel("Passphrase:")
        self.passphrase_edit = QLineEdit()
        self.passphrase_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.passphrase_edit.setPlaceholderText("Enter encryption passphrase")
        
        self.show_password_button = QPushButton("👁")
        self.show_password_button.setMaximumWidth(40)
        self.show_password_button.setCheckable(True)
        self.show_password_button.toggled.connect(self._toggle_password_visibility)
        
        passphrase_layout.addWidget(passphrase_label)
        passphrase_layout.addWidget(self.passphrase_edit)
        passphrase_layout.addWidget(self.show_password_button)
        layout.addLayout(passphrase_layout)
        
        # Confirm passphrase
        confirm_layout = QHBoxLayout()
        confirm_label = QLabel("Confirm:")
        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_edit.setPlaceholderText("Confirm passphrase")
        
        confirm_layout.addWidget(confirm_label)
        confirm_layout.addWidget(self.confirm_edit)
        layout.addLayout(confirm_layout)
        
        # Status label
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        
        # Remove key button
        self.remove_button = QPushButton("Remove Encryption Key")
        self.remove_button.setStyleSheet("background-color: #f44; color: white;")
        self.remove_button.clicked.connect(self._remove_key)
        layout.addWidget(self.remove_button)
        
        layout.addStretch()
        
        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
    
    def _check_existing_key(self):
        """Check if a key already exists for this room/PM."""
        # Use encryption manager's get_room_key_data which handles PMs correctly
        key = self.encryption_manager.get_room_key_data(
            self.server_name, self.channel_name, self.server_config,
            own_nick=self.own_nick if self.is_pm else None,
            is_pm=self.is_pm
        )
        if key:
            if self.is_pm:
                self.status_label.setText("⚠️ Encryption key is already set for this private message conversation.")
            else:
                self.status_label.setText("⚠️ Encryption key is already set for this room.")
            self.status_label.setStyleSheet("color: orange;")
            self.remove_button.setEnabled(True)
        else:
            if self.is_pm:
                self.status_label.setText("No encryption key set. Enter a passphrase to enable encryption for private messages.")
            else:
                self.status_label.setText("No encryption key set. Enter a passphrase to enable encryption.")
            self.status_label.setStyleSheet("color: gray;")
            self.remove_button.setEnabled(False)
    
    def _toggle_password_visibility(self, checked: bool):
        """Toggle password visibility."""
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.passphrase_edit.setEchoMode(mode)
        self.confirm_edit.setEchoMode(mode)
    
    def _validate_and_accept(self):
        """Validate passphrase and set key."""
        passphrase = self.passphrase_edit.text()
        confirm = self.confirm_edit.text()
        
        if not passphrase:
            # If empty, just close (user might want to remove key instead)
            self.accept()
            return
        
        if passphrase != confirm:
            QMessageBox.warning(self, "Validation Error", "Passphrases do not match!")
            return
        
        if len(passphrase) < 8:
            reply = QMessageBox.question(
                self, "Weak Passphrase",
                "Passphrase is less than 8 characters. This is not recommended.\n"
                "Continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        # Derive and store key
        try:
            self.encryption_manager.set_room_key_from_passphrase(
                self.server_name, self.channel_name, passphrase, self.server_config,
                own_nick=self.own_nick if self.is_pm else None,
                is_pm=self.is_pm
            )
            self.key_set = True
            QMessageBox.information(
                self, "Key Set",
                "Encryption key has been set successfully.\n\n"
                "Remember: Share this passphrase with other users out-of-band!"
            )
            self.accept()
        except Exception as e:
            logger.error(f"Error setting encryption key: {e}")
            QMessageBox.critical(self, "Error", f"Failed to set encryption key: {e}")
    
    def _remove_key(self):
        """Remove encryption key for this room/PM."""
        if self.is_pm:
            message = "Are you sure you want to remove the encryption key?\n\n" \
                     "You will no longer be able to decrypt messages in this private conversation!"
        else:
            message = "Are you sure you want to remove the encryption key?\n\n" \
                     "You will no longer be able to decrypt messages in this room!"
        
        reply = QMessageBox.question(
            self, "Confirm Removal", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # For PMs, we need to use the PM identifier
            if self.is_pm and self.own_nick:
                pm_id = self.encryption_manager._get_pm_identifier(self.own_nick, self.channel_name)
                # Remove using canonical ID
                canonical_id = self.encryption_manager._get_canonical_server_id(
                    self.server_name, self.server_config
                )
                self.encryption_manager.remove_room_key(canonical_id, pm_id)
                # Also try removing with server_name for backward compatibility
                self.encryption_manager.remove_room_key(self.server_name, pm_id)
            else:
                # For channels, use channel name directly
                canonical_id = self.encryption_manager._get_canonical_server_id(
                    self.server_name, self.server_config
                )
                self.encryption_manager.remove_room_key(canonical_id, self.channel_name)
                # Also try removing with server_name for backward compatibility
                self.encryption_manager.remove_room_key(self.server_name, self.channel_name)
            QMessageBox.information(self, "Key Removed", "Encryption key has been removed.")
            self.accept()

