"""
Settings and database management for the IRC client.
Handles SQLite database operations for servers, settings, room keys, and aliases.
"""

import sqlite3
import os
import logging
from typing import Optional, Dict, List, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class SettingsManager:
    """Manages application settings and persistent data storage."""
    
    def __init__(self, db_path: str = "irc_client.db"):
        """Initialize the settings manager with a database path."""
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._init_database()
    
    def _init_database(self):
        """Initialize the SQLite database with required tables."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        cursor = self.conn.cursor()
        
        # Servers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                hostname TEXT NOT NULL,
                port INTEGER NOT NULL DEFAULT 6667,
                ssl INTEGER NOT NULL DEFAULT 0,
                nickname TEXT NOT NULL,
                alt_nickname TEXT,
                username TEXT NOT NULL,
                realname TEXT NOT NULL,
                auto_join_channels TEXT,
                default_encoding TEXT DEFAULT 'UTF-8',
                auto_connect INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Settings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        # Room keys table (stores derived keys and salts, not plaintext passphrases)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS room_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_name TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                salt BLOB NOT NULL,
                derived_key BLOB NOT NULL,
                iterations INTEGER NOT NULL DEFAULT 100000,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(server_name, channel_name)
            )
        """)
        
        # Aliases table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias_name TEXT NOT NULL UNIQUE,
                expansion TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert default settings if they don't exist
        default_settings = {
            'font_family': 'Consolas',
            'font_size': '10',
            'timestamp_format': '%H:%M:%S',
            'show_timestamps': '1',
            'log_directory': 'logs',
            'log_enabled': '1',
            'theme': 'light',
            'auto_reconnect': '0',
            'reconnect_delay': '5'
        }
        
        for key, value in default_settings.items():
            cursor.execute("""
                INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)
            """, (key, value))
        
        self.conn.commit()
        logger.info("Database initialized successfully")
    
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a setting value by key."""
        if self.conn is None:
            return default
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else default
        except Exception:
            # Connection might be closed during shutdown
            return default
    
    def set_setting(self, key: str, value: str):
        """Set a setting value."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)
        """, (key, value))
        self.conn.commit()
    
    def get_servers(self) -> List[Dict[str, Any]]:
        """Get all configured servers."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM servers ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]
    
    def get_server(self, server_id: int) -> Optional[Dict[str, Any]]:
        """Get a server by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM servers WHERE id = ?", (server_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def add_server(self, server_data: Dict[str, Any]) -> int:
        """Add a new server and return its ID."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO servers (
                name, hostname, port, ssl, nickname, alt_nickname,
                username, realname, auto_join_channels, default_encoding, auto_connect
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            server_data.get('name'),
            server_data.get('hostname'),
            server_data.get('port', 6667),
            1 if server_data.get('ssl', False) else 0,
            server_data.get('nickname'),
            server_data.get('alt_nickname'),
            server_data.get('username'),
            server_data.get('realname'),
            server_data.get('auto_join_channels', ''),
            server_data.get('default_encoding', 'UTF-8'),
            1 if server_data.get('auto_connect', False) else 0
        ))
        self.conn.commit()
        return cursor.lastrowid
    
    def update_server(self, server_id: int, server_data: Dict[str, Any]):
        """Update an existing server."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE servers SET
                name = ?, hostname = ?, port = ?, ssl = ?, nickname = ?,
                alt_nickname = ?, username = ?, realname = ?,
                auto_join_channels = ?, default_encoding = ?, auto_connect = ?
            WHERE id = ?
        """, (
            server_data.get('name'),
            server_data.get('hostname'),
            server_data.get('port', 6667),
            1 if server_data.get('ssl', False) else 0,
            server_data.get('nickname'),
            server_data.get('alt_nickname'),
            server_data.get('username'),
            server_data.get('realname'),
            server_data.get('auto_join_channels', ''),
            server_data.get('default_encoding', 'UTF-8'),
            1 if server_data.get('auto_connect', False) else 0,
            server_id
        ))
        self.conn.commit()
    
    def delete_server(self, server_id: int):
        """Delete a server."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM servers WHERE id = ?", (server_id,))
        self.conn.commit()
    
    def get_room_key(self, server_name: str, channel_name: str) -> Optional[Dict[str, Any]]:
        """Get encryption key data for a room."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT salt, derived_key, iterations
            FROM room_keys
            WHERE server_name = ? AND channel_name = ?
        """, (server_name, channel_name))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def set_room_key(self, server_name: str, channel_name: str,
                     salt: bytes, derived_key: bytes, iterations: int = 100000):
        """Store encryption key data for a room."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO room_keys
            (server_name, channel_name, salt, derived_key, iterations)
            VALUES (?, ?, ?, ?, ?)
        """, (server_name, channel_name, salt, derived_key, iterations))
        self.conn.commit()
    
    def remove_room_key(self, server_name: str, channel_name: str):
        """Remove encryption key for a room."""
        cursor = self.conn.cursor()
        cursor.execute("""
            DELETE FROM room_keys
            WHERE server_name = ? AND channel_name = ?
        """, (server_name, channel_name))
        self.conn.commit()
    
    def get_aliases(self) -> List[Dict[str, Any]]:
        """Get all aliases."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM aliases ORDER BY alias_name")
        return [dict(row) for row in cursor.fetchall()]
    
    def add_alias(self, alias_name: str, expansion: str):
        """Add or update an alias."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO aliases (alias_name, expansion)
            VALUES (?, ?)
        """, (alias_name, expansion))
        self.conn.commit()
    
    def delete_alias(self, alias_name: str):
        """Delete an alias."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM aliases WHERE alias_name = ?", (alias_name,))
        self.conn.commit()
    
    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

