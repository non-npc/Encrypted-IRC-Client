"""
Preferences dialog for application settings.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QFormLayout, QLineEdit, QSpinBox, QCheckBox, QPushButton,
    QFileDialog, QDialogButtonBox, QLabel, QComboBox
)
from PyQt6.QtCore import Qt
from typing import Optional


class PreferencesDialog(QDialog):
    """Dialog for application preferences."""
    
    def __init__(self, settings_manager, parent=None):
        """Initialize preferences dialog."""
        super().__init__(parent)
        self.settings_manager = settings_manager
        self._init_ui()
        self._load_settings()
    
    def _init_ui(self):
        """Initialize UI components."""
        self.setWindowTitle("Preferences")
        self.setMinimumSize(500, 400)
        
        layout = QVBoxLayout()
        
        # Tab widget
        tabs = QTabWidget()
        
        # Appearance tab
        appearance_tab = self._create_appearance_tab()
        tabs.addTab(appearance_tab, "Appearance")
        
        # Logging tab
        logging_tab = self._create_logging_tab()
        tabs.addTab(logging_tab, "Logging")
        
        # Connection tab
        connection_tab = self._create_connection_tab()
        tabs.addTab(connection_tab, "Connection")
        
        layout.addWidget(tabs)
        
        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
    
    def _create_appearance_tab(self):
        """Create appearance settings tab."""
        widget = QWidget()
        layout = QFormLayout()
        
        # Font family
        self.font_family_edit = QLineEdit()
        layout.addRow("Font Family:", self.font_family_edit)
        
        # Font size
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 24)
        layout.addRow("Font Size:", self.font_size_spin)
        
        # Theme
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["light", "dark"])
        layout.addRow("Theme:", self.theme_combo)
        
        # Show timestamps
        self.show_timestamps_check = QCheckBox()
        layout.addRow("Show Timestamps:", self.show_timestamps_check)
        
        # Timestamp format
        self.timestamp_format_edit = QLineEdit()
        self.timestamp_format_edit.setPlaceholderText("%H:%M:%S")
        layout.addRow("Timestamp Format:", self.timestamp_format_edit)
        
        widget.setLayout(layout)
        return widget
    
    def _create_logging_tab(self):
        """Create logging settings tab."""
        widget = QWidget()
        layout = QFormLayout()
        
        # Enable logging
        self.log_enabled_check = QCheckBox()
        layout.addRow("Enable Logging:", self.log_enabled_check)
        
        # Log directory
        log_dir_layout = QHBoxLayout()
        self.log_directory_edit = QLineEdit()
        self.log_directory_button = QPushButton("Browse...")
        self.log_directory_button.clicked.connect(self._browse_log_directory)
        log_dir_layout.addWidget(self.log_directory_edit)
        log_dir_layout.addWidget(self.log_directory_button)
        layout.addRow("Log Directory:", log_dir_layout)
        
        widget.setLayout(layout)
        return widget
    
    def _create_connection_tab(self):
        """Create connection settings tab."""
        widget = QWidget()
        layout = QFormLayout()
        
        # Auto-reconnect
        self.auto_reconnect_check = QCheckBox()
        layout.addRow("Auto-reconnect on disconnect:", self.auto_reconnect_check)
        
        # Reconnect delay
        self.reconnect_delay_spin = QSpinBox()
        self.reconnect_delay_spin.setRange(1, 60)
        self.reconnect_delay_spin.setSuffix(" seconds")
        layout.addRow("Reconnect Delay:", self.reconnect_delay_spin)
        
        # Channel list expiration
        self.channel_list_expiration_combo = QComboBox()
        self.channel_list_expiration_combo.addItems(["10 minutes", "30 minutes", "1 hour"])
        layout.addRow("Channel List Cache Expiration:", self.channel_list_expiration_combo)
        
        widget.setLayout(layout)
        return widget
    
    def _browse_log_directory(self):
        """Browse for log directory."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Log Directory", self.log_directory_edit.text()
        )
        if directory:
            self.log_directory_edit.setText(directory)
    
    def _load_settings(self):
        """Load settings into form."""
        self.font_family_edit.setText(
            self.settings_manager.get_setting('font_family', 'Consolas')
        )
        self.font_size_spin.setValue(
            int(self.settings_manager.get_setting('font_size', '10'))
        )
        theme = self.settings_manager.get_setting('theme', 'light')
        index = self.theme_combo.findText(theme)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)
        
        self.show_timestamps_check.setChecked(
            self.settings_manager.get_setting('show_timestamps', '1') == '1'
        )
        self.timestamp_format_edit.setText(
            self.settings_manager.get_setting('timestamp_format', '%H:%M:%S')
        )
        
        self.log_enabled_check.setChecked(
            self.settings_manager.get_setting('log_enabled', '1') == '1'
        )
        self.log_directory_edit.setText(
            self.settings_manager.get_setting('log_directory', 'logs')
        )
        
        self.auto_reconnect_check.setChecked(
            self.settings_manager.get_setting('auto_reconnect', '0') == '1'
        )
        self.reconnect_delay_spin.setValue(
            int(self.settings_manager.get_setting('reconnect_delay', '5'))
        )
        
        # Channel list expiration (default: 1 hour = 3600 seconds)
        channel_list_expiration = int(self.settings_manager.get_setting('channel_list_expiration', '3600'))
        # Map seconds to combo box index: 600 (10 min) = 0, 1800 (30 min) = 1, 3600 (1 hour) = 2
        if channel_list_expiration == 600:
            self.channel_list_expiration_combo.setCurrentIndex(0)
        elif channel_list_expiration == 1800:
            self.channel_list_expiration_combo.setCurrentIndex(1)
        else:  # Default to 1 hour (3600)
            self.channel_list_expiration_combo.setCurrentIndex(2)
    
    def _save_and_accept(self):
        """Save settings and accept dialog."""
        self.settings_manager.set_setting('font_family', self.font_family_edit.text())
        self.settings_manager.set_setting('font_size', str(self.font_size_spin.value()))
        self.settings_manager.set_setting('theme', self.theme_combo.currentText())
        self.settings_manager.set_setting(
            'show_timestamps', '1' if self.show_timestamps_check.isChecked() else '0'
        )
        self.settings_manager.set_setting('timestamp_format', self.timestamp_format_edit.text())
        
        self.settings_manager.set_setting(
            'log_enabled', '1' if self.log_enabled_check.isChecked() else '0'
        )
        self.settings_manager.set_setting('log_directory', self.log_directory_edit.text())
        
        self.settings_manager.set_setting(
            'auto_reconnect', '1' if self.auto_reconnect_check.isChecked() else '0'
        )
        self.settings_manager.set_setting('reconnect_delay', str(self.reconnect_delay_spin.value()))
        
        # Channel list expiration: map combo box selection to seconds
        expiration_index = self.channel_list_expiration_combo.currentIndex()
        expiration_seconds = [600, 1800, 3600][expiration_index]  # 10 min, 30 min, 1 hour
        self.settings_manager.set_setting('channel_list_expiration', str(expiration_seconds))
        
        self.accept()

