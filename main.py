"""
Main entry point for the Encrypted IRC Client application.
"""

import sys
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, qInstallMessageHandler, QtMsgType

from core.settings_manager import SettingsManager
from core.encryption_manager import EncryptionManager
from core.alias_manager import AliasManager
from ui.main_window import MainWindow

# Application version
VERSION = "0.2"


def qt_message_handler(msg_type, context, message):
    """Handle Qt log messages and filter out font warnings."""
    # Filter out OpenType font support warnings (harmless)
    if "OpenType support missing" in message:
        return
    
    # Use default Qt message handler for other messages
    if msg_type >= QtMsgType.QtWarningMsg:
        # Only show warnings and above (not debug/info)
        # Format message manually since qFormatLogMessage is not available in PyQt6
        msg_type_str = {
            QtMsgType.QtDebugMsg: "Debug",
            QtMsgType.QtWarningMsg: "Warning",
            QtMsgType.QtCriticalMsg: "Critical",
            QtMsgType.QtFatalMsg: "Fatal",
            QtMsgType.QtInfoMsg: "Info"
        }.get(msg_type, "Unknown")
        formatted = f"Qt {msg_type_str}: {message}"
        if context.file:
            formatted = f"{context.file}:{context.line} - {formatted}"
        print(formatted)


def setup_logging():
    """Setup application logging."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / "irc_client.log"
    
    # Create rotating file handler
    handler = RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, backupCount=5
    )
    handler.setLevel(logging.DEBUG)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(handler)
    root_logger.addHandler(console_handler)


def add_sample_servers(settings_manager: SettingsManager):
    """Add sample IRC servers if none exist."""
    existing_servers = settings_manager.get_servers()
    if existing_servers:
        return
    
    # Add some popular IRC networks as samples
    sample_servers = [
        {
            'name': 'Libera Chat',
            'hostname': 'irc.libera.chat',
            'port': 6667,
            'ssl': False,
            'nickname': 'IRCUser',
            'alt_nickname': 'IRCUser_',
            'username': 'ircuser',
            'realname': 'IRC User',
            'auto_join_channels': '',
            'default_encoding': 'UTF-8',
            'auto_connect': False
        },
        {
            'name': 'Libera Chat (SSL)',
            'hostname': 'irc.libera.chat',
            'port': 6697,
            'ssl': True,
            'nickname': 'IRCUser',
            'alt_nickname': 'IRCUser_',
            'username': 'ircuser',
            'realname': 'IRC User',
            'auto_join_channels': '',
            'default_encoding': 'UTF-8',
            'auto_connect': False
        },
        {
            'name': 'Freenode',
            'hostname': 'chat.freenode.net',
            'port': 6667,
            'ssl': False,
            'nickname': 'IRCUser',
            'alt_nickname': 'IRCUser_',
            'username': 'ircuser',
            'realname': 'IRC User',
            'auto_join_channels': '',
            'default_encoding': 'UTF-8',
            'auto_connect': False
        }
    ]
    
    for server in sample_servers:
        settings_manager.add_server(server)
    
    logging.info("Added sample IRC servers")


def main():
    """Main application entry point."""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Encrypted IRC Client")
    
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Encrypted IRC Client")
    app.setOrganizationName("IRC Client")
    
    # Install Qt message handler to filter font warnings (must be after QApplication creation)
    qInstallMessageHandler(qt_message_handler)
    
    # Initialize core components
    settings_manager = SettingsManager()
    encryption_manager = EncryptionManager(settings_manager)
    alias_manager = AliasManager(settings_manager)
    
    # Add sample servers if database is empty
    add_sample_servers(settings_manager)
    
    # Create and show main window
    window = MainWindow(settings_manager, encryption_manager, alias_manager, version=VERSION)
    window.show()
    
    # Run application
    exit_code = app.exec()
    
    # Cleanup
    settings_manager.close()
    logger.info("Application exited")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

