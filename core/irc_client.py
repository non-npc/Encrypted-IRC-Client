"""
IRC client implementation using QTcpSocket and QSslSocket.
Handles IRC protocol communication and message routing.
Supports both plain and SSL/TLS encrypted connections.
"""

import logging
from typing import Optional, Dict, Callable, Set
from PyQt6.QtNetwork import QTcpSocket, QAbstractSocket, QSslSocket, QSslConfiguration
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from core.irc_parser import IRCParser, IRCMessage
from core.encryption_manager import EncryptionManager

logger = logging.getLogger(__name__)


class IRCClient(QObject):
    """Manages an IRC server connection."""
    
    # Signals
    connected = pyqtSignal(str)  # server_name
    disconnected = pyqtSignal(str)  # server_name
    message_received = pyqtSignal(str, IRCMessage)  # server_name, message
    error_occurred = pyqtSignal(str, str)  # server_name, error_message
    
    def __init__(self, server_config: Dict, encryption_manager: EncryptionManager):
        """
        Initialize IRC client.
        
        Args:
            server_config: Server configuration dictionary
            encryption_manager: Encryption manager instance
        """
        super().__init__()
        self.server_config = server_config
        self.server_name = server_config.get('name', server_config.get('hostname', 'Unknown'))
        self.encryption_manager = encryption_manager
        
        self.socket: Optional[QAbstractSocket] = None  # Can be QTcpSocket or QSslSocket
        self.parser = IRCParser()
        self.connected_to_server = False
        self.nickname = server_config.get('nickname', 'User')
        self.alt_nickname = server_config.get('alt_nickname', 'User_')
        self.username = server_config.get('username', 'user')
        self.realname = server_config.get('realname', 'IRC User')
        
        self.joined_channels: Set[str] = set()
        self.receive_buffer: str = ""  # Buffer for incomplete lines
        self.use_ssl = server_config.get('ssl', False)
        self.motd_complete = False  # Track if MOTD has been received
        self.auto_join_pending = False  # Track if auto-join is waiting for MOTD
        self.message_handlers: Dict[str, Callable] = {
            'PING': self._handle_ping,
            '001': self._handle_welcome,  # RPL_WELCOME
            '322': self._handle_list_reply,  # RPL_LIST
            '323': self._handle_list_end,  # RPL_LISTEND
            '353': self._handle_names,  # RPL_NAMREPLY
            '366': self._handle_end_of_names,  # RPL_ENDOFNAMES
            '372': self._handle_motd,  # RPL_MOTD
            '375': self._handle_motd_start,  # RPL_MOTDSTART
            '376': self._handle_motd_end,  # RPL_ENDOFMOTD
            '422': self._handle_no_motd,  # ERR_NOMOTD
            '433': self._handle_nick_in_use,  # ERR_NICKNAMEINUSE
            'JOIN': self._handle_join,
            'PART': self._handle_part,
            'QUIT': self._handle_quit,
            'PRIVMSG': self._handle_privmsg,
            'NOTICE': self._handle_notice,
            'NICK': self._handle_nick,
            'MODE': self._handle_mode,
            'TOPIC': self._handle_topic,
            'KICK': self._handle_kick,
        }
    
    def connect_to_server(self):
        """Connect to the IRC server."""
        if self.socket:
            self.disconnect_from_server()
        
        hostname = self.server_config.get('hostname')
        port = self.server_config.get('port', 6667)
        use_ssl = self.server_config.get('ssl', False)
        
        logger.info(f"Connecting to {hostname}:{port} (SSL: {use_ssl})")
        
        if use_ssl:
            # Use QSslSocket for SSL/TLS connections
            self.socket = QSslSocket()
            
            # Configure SSL
            ssl_config = QSslConfiguration.defaultConfiguration()
            # Allow self-signed certificates (common for IRC servers)
            # In production, you might want to make this configurable
            ssl_config.setPeerVerifyMode(QSslSocket.PeerVerifyMode.VerifyNone)
            self.socket.setSslConfiguration(ssl_config)
            
            # Connect SSL-specific signals
            self.socket.sslErrors.connect(self._on_ssl_errors)
            self.socket.encrypted.connect(self._on_ssl_encrypted)
        else:
            # Use regular QTcpSocket for non-SSL connections
            self.socket = QTcpSocket()
        
        # Connect common signals
        self.socket.connected.connect(self._on_connected)
        self.socket.disconnected.connect(self._on_disconnected)
        self.socket.readyRead.connect(self._on_data_received)
        self.socket.errorOccurred.connect(self._on_error)
        
        # Connect to host
        if use_ssl:
            # For SSL, we need to start the SSL handshake after TCP connection
            self.socket.connectToHostEncrypted(hostname, port)
        else:
            # Regular TCP connection
            self.socket.connectToHost(hostname, port)
    
    def disconnect_from_server(self, message: str = "Client quit"):
        """Disconnect from the IRC server."""
        if self.socket and self.socket.state() == QAbstractSocket.SocketState.ConnectedState:
            self.send_command("QUIT", message)
            QTimer.singleShot(500, self.socket.close)
        elif self.socket:
            self.socket.close()
        self.connected_to_server = False
    
    def send_command(self, command: str, *params: str):
        """Send an IRC command to the server."""
        if not self.socket:
            logger.warning(f"Cannot send command {command}: socket not initialized")
            return
        
        if self.socket.state() != QAbstractSocket.SocketState.ConnectedState:
            logger.warning(f"Cannot send command {command}: not connected (state: {self.socket.state()})")
            return
        
        if not self.socket.isOpen() or not self.socket.isWritable():
            logger.warning(f"Cannot send command {command}: socket not open or writable")
            return
        
        try:
            message = self.parser.build_message(command, *params)
            logger.debug(f"Sending: {message}")
            data = f"{message}\r\n".encode('utf-8')
            bytes_written = self.socket.write(data)
            if bytes_written > 0:
                self.socket.flush()
            else:
                logger.warning(f"Failed to write command {command} to socket")
        except Exception as e:
            logger.error(f"Error sending command {command}: {e}")
    
    def send_message(self, target: str, message: str, encrypted: bool = False):
        """
        Send a PRIVMSG to a target (channel or user).
        
        Args:
            target: Channel or nickname
            message: Message text
            encrypted: Whether to encrypt the message
        """
        if encrypted:
            # Determine if this is a PM (not a channel - channels start with #)
            is_pm = not target.startswith('#')
            
            # Get encryption key for this room/PM using canonical server ID
            key = self.encryption_manager.get_room_key_data(
                self.server_name, target, self.server_config,
                own_nick=self.nickname if is_pm else None,
                is_pm=is_pm
            )
            if key:
                encrypted_msg = self.encryption_manager.encrypt_message(message, key)
                logger.debug(f"Encrypting message for {target}, original length: {len(message)}, encrypted length: {len(encrypted_msg)}")
                message = encrypted_msg
            else:
                logger.warning(f"No encryption key for {target} on {self.server_name}, sending plaintext")
        
        self.send_command("PRIVMSG", target, message)
    
    def join_channel(self, channel: str):
        """Join an IRC channel."""
        if not channel.startswith('#'):
            channel = '#' + channel
        self.send_command("JOIN", channel)
    
    def part_channel(self, channel: str, message: str = ""):
        """Leave an IRC channel."""
        if not channel.startswith('#'):
            channel = '#' + channel
        if message:
            self.send_command("PART", channel, message)
        else:
            self.send_command("PART", channel)
    
    def change_nick(self, new_nick: str):
        """Change nickname."""
        self.nickname = new_nick
        self.send_command("NICK", new_nick)
    
    def _on_connected(self):
        """Handle socket connection (TCP layer)."""
        logger.info(f"TCP connection established to {self.server_config.get('hostname')}")
        
        # For SSL connections, wait for encryption to complete
        # For non-SSL, proceed immediately
        if not self.use_ssl:
            # Wait a moment to ensure socket is fully ready
            QTimer.singleShot(100, self._send_registration)
            self.connected.emit(self.server_name)
    
    def _on_ssl_encrypted(self):
        """Handle SSL encryption completion."""
        logger.info(f"SSL encryption established to {self.server_config.get('hostname')}")
        # Now that SSL is encrypted, we can send registration
        QTimer.singleShot(100, self._send_registration)
        self.connected.emit(self.server_name)
    
    def _on_ssl_errors(self, errors):
        """Handle SSL errors (e.g., self-signed certificates)."""
        logger.warning(f"SSL errors occurred: {[str(e) for e in errors]}")
        # For now, we continue anyway (VerifyNone mode)
        # In production, you might want to show a dialog to the user
        # and let them decide whether to proceed
        if self.socket:
            # Continue despite errors (since we set VerifyNone)
            self.socket.ignoreSslErrors()
    
    def _send_registration(self):
        """Send registration commands after connection is established."""
        if not self.socket or self.socket.state() != QAbstractSocket.SocketState.ConnectedState:
            logger.warning("Socket not ready for registration")
            return
        
        self.connected_to_server = True
        self.motd_complete = False  # Reset MOTD flag
        
        # Send registration commands
        self.send_command("NICK", self.nickname)
        self.send_command("USER", self.username, "0", "*", self.realname)
        
        # Check if auto-join is configured
        auto_join = self.server_config.get('auto_join_channels', '')
        if auto_join:
            self.auto_join_pending = True
            # Auto-join will be triggered after MOTD is complete
            # Set a timeout fallback (10 seconds) in case server doesn't send MOTD
            QTimer.singleShot(10000, self._auto_join_timeout)
    
    def _on_disconnected(self):
        """Handle socket disconnection."""
        logger.info(f"Disconnected from {self.server_config.get('hostname')}")
        self.connected_to_server = False
        self.motd_complete = False
        self.auto_join_pending = False
        self.joined_channels.clear()
        self.receive_buffer = ""  # Clear receive buffer
        self.disconnected.emit(self.server_name)
    
    def _on_data_received(self):
        """Handle incoming data from the server."""
        if not self.socket:
            return
        
        data = self.socket.readAll().data()
        # Add new data to buffer
        self.receive_buffer += data.decode('utf-8', errors='replace')
        
        # Process complete lines (IRC messages end with \r\n)
        while '\n' in self.receive_buffer:
            # Split on \n, but keep the last incomplete line in buffer
            lines = self.receive_buffer.split('\n')
            # Keep the last (potentially incomplete) line in buffer
            self.receive_buffer = lines[-1]
            
            # Process all complete lines
            for line in lines[:-1]:
                # Remove CR if present (IRC lines end with \r\n)
                line = line.rstrip('\r')
                line = line.strip()
                
                if not line:
                    continue
                
                message = self.parser.parse(line)
                if message:
                    self._handle_message(message)
    
    def _on_error(self, error: QAbstractSocket.SocketError):
        """Handle socket errors."""
        error_msg = self.socket.errorString() if self.socket else "Unknown error"
        logger.error(f"Socket error: {error_msg}")
        self.error_occurred.emit(self.server_name, error_msg)
    
    def _handle_message(self, message: IRCMessage):
        """Route IRC messages to appropriate handlers."""
        command = message.command
        
        # Handle numeric replies
        if command.isdigit():
            handler = self.message_handlers.get(command)
            if handler:
                handler(message)
            else:
                # Emit all numeric replies for status window
                self.message_received.emit(self.server_name, message)
        else:
            # Handle named commands
            handler = self.message_handlers.get(command)
            if handler:
                handler(message)
            else:
                # Emit unknown commands for status window
                self.message_received.emit(self.server_name, message)
    
    def _handle_ping(self, message: IRCMessage):
        """Handle PING command."""
        if message.params:
            self.send_command("PONG", message.params[0])
    
    def _handle_welcome(self, message: IRCMessage):
        """Handle RPL_WELCOME (001)."""
        logger.info(f"Welcome message: {message.text}")
        self.message_received.emit(self.server_name, message)
    
    def _handle_motd_start(self, message: IRCMessage):
        """Handle RPL_MOTDSTART (375)."""
        self.message_received.emit(self.server_name, message)
    
    def _handle_motd(self, message: IRCMessage):
        """Handle RPL_MOTD (372)."""
        self.message_received.emit(self.server_name, message)
    
    def _handle_motd_end(self, message: IRCMessage):
        """Handle RPL_ENDOFMOTD (376) - MOTD complete."""
        logger.info("MOTD complete")
        self.motd_complete = True
        self.message_received.emit(self.server_name, message)
        # Trigger auto-join if pending
        if self.auto_join_pending:
            self._do_auto_join()
    
    def _handle_no_motd(self, message: IRCMessage):
        """Handle ERR_NOMOTD (422) - No MOTD configured."""
        logger.info("No MOTD configured")
        self.motd_complete = True
        self.message_received.emit(self.server_name, message)
        # Trigger auto-join if pending (some servers don't send MOTD)
        if self.auto_join_pending:
            self._do_auto_join()
    
    def _auto_join_timeout(self):
        """Fallback timeout for auto-join if MOTD never completes."""
        if self.auto_join_pending and not self.motd_complete:
            logger.warning("MOTD timeout - proceeding with auto-join anyway")
            self._do_auto_join()
    
    def _do_auto_join(self):
        """Perform auto-join of configured channels."""
        if not self.auto_join_pending:
            return
        
        self.auto_join_pending = False
        auto_join = self.server_config.get('auto_join_channels', '')
        if not auto_join:
            return
        
        channels = [ch.strip() for ch in auto_join.split(',') if ch.strip()]
        if not channels:
            return
        
        logger.info(f"Auto-joining {len(channels)} channel(s) after MOTD")
        
        # Join channels with a small delay between each
        for i, channel in enumerate(channels):
            if not channel.startswith('#'):
                channel = '#' + channel
            # Delay each join slightly to avoid rate limiting
            QTimer.singleShot(500 + (i * 300), lambda ch=channel: self.join_channel(ch))
    
    def _handle_list_reply(self, message: IRCMessage):
        """Handle RPL_LIST (322) - channel list entry."""
        # Format: :server 322 nick #channel user_count :topic
        if len(message.params) >= 3:
            channel = message.params[1]
            user_count = message.params[2]
            topic = message.params[3] if len(message.params) > 3 else ""
            self.message_received.emit(self.server_name, message)
    
    def _handle_list_end(self, message: IRCMessage):
        """Handle RPL_LISTEND (323) - end of channel list."""
        self.message_received.emit(self.server_name, message)
    
    def _handle_nick_in_use(self, message: IRCMessage):
        """Handle ERR_NICKNAMEINUSE (433)."""
        logger.warning("Nickname in use, trying alternate")
        if self.nickname == self.server_config.get('nickname'):
            self.change_nick(self.alt_nickname)
        self.message_received.emit(self.server_name, message)
    
    def _handle_join(self, message: IRCMessage):
        """Handle JOIN command."""
        nick = message.nick
        channel = message.params[0] if message.params else None
        
        if channel:
            # Remove any leading colon if present (shouldn't be, but just in case)
            channel = channel.lstrip(':')
            if nick == self.nickname:
                self.joined_channels.add(channel)
                logger.info(f"Joined channel: {channel}")
                # Request names list for the channel
                self.send_command("NAMES", channel)
            self.message_received.emit(self.server_name, message)
    
    def _handle_names(self, message: IRCMessage):
        """Handle RPL_NAMREPLY (353) - channel names list."""
        # Format: :server 353 nick = #channel :nick1 nick2 nick3
        if len(message.params) >= 3:
            channel = message.params[2]  # Channel name
            nicks_str = message.params[3] if len(message.params) > 3 else ""
            if nicks_str:
                # Parse nicks (may have @ for ops, + for voiced)
                nicks = nicks_str.split()
                # Emit a special signal or add to message for UI to handle
                # For now, just emit the message and let UI handle it
                self.message_received.emit(self.server_name, message)
    
    def _handle_end_of_names(self, message: IRCMessage):
        """Handle RPL_ENDOFNAMES (366) - end of names list."""
        self.message_received.emit(self.server_name, message)
    
    def _handle_part(self, message: IRCMessage):
        """Handle PART command."""
        nick = message.nick
        channel = message.params[0] if message.params else None
        
        if channel:
            if nick == self.nickname:
                self.joined_channels.discard(channel)
                logger.info(f"Parted channel: {channel}")
            self.message_received.emit(self.server_name, message)
    
    def _handle_quit(self, message: IRCMessage):
        """Handle QUIT command."""
        self.message_received.emit(self.server_name, message)
    
    def _handle_privmsg(self, message: IRCMessage):
        """Handle PRIVMSG command."""
        target = message.target
        text = message.text
        
        if text and target:
            # Determine if this is a PM (not a channel - channels start with #)
            # Also check if target is our own nick (which means it's a PM to us)
            is_pm = not target.startswith('#') or target == self.nickname
            
            # For PMs, we need to determine the other user's nick
            # If target is our nick, the sender is the other user
            # If target is not our nick and not a channel, target is the other user
            if is_pm:
                if target == self.nickname:
                    # PM to us - the sender is the other user
                    other_nick = message.nick or "Unknown"
                else:
                    # PM from us to someone else - target is the other user
                    other_nick = target
            else:
                other_nick = None
            
            # Check if encryption is enabled for this channel/PM
            key = self.encryption_manager.get_room_key_data(
                self.server_name, 
                other_nick if is_pm else target, 
                self.server_config,
                own_nick=self.nickname if is_pm else None,
                is_pm=is_pm
            )
            if key:
                # Encryption is enabled - attempt to decrypt all messages
                logger.debug(f"Attempting to decrypt message in {target} on {self.server_name}, key length: {len(key)}")
                decrypted = self.encryption_manager.decrypt_message(text, key)
                if decrypted:
                    # Successfully decrypted - replace text with decrypted version and add lock icon
                    message.params[-1] = f"🔒 {decrypted}"
                else:
                    # Decryption failed - message might be plaintext from user without encryption
                    # or corrupted. Show as-is but indicate it couldn't be decrypted
                    logger.debug(f"Could not decrypt message in {target} on {self.server_name} (may be plaintext or wrong key)")
                    message.params[-1] = f"⚠️ {text}"
            else:
                # No encryption key set - check if message appears to be encrypted
                if self.encryption_manager.is_encrypted_message(text):
                    # Message is encrypted but we don't have the key - show lock icon
                    message.params[-1] = f"🔒 {text}"
                else:
                    # Message is plaintext - show warning icon
                    message.params[-1] = f"⚠️ {text}"
        
        self.message_received.emit(self.server_name, message)
    
    def _handle_notice(self, message: IRCMessage):
        """Handle NOTICE command."""
        self.message_received.emit(self.server_name, message)
    
    def _handle_nick(self, message: IRCMessage):
        """Handle NICK change."""
        if message.nick == self.nickname:
            new_nick = message.params[0] if message.params else None
            if new_nick:
                self.nickname = new_nick
        self.message_received.emit(self.server_name, message)
    
    def _handle_mode(self, message: IRCMessage):
        """Handle MODE command."""
        self.message_received.emit(self.server_name, message)
    
    def _handle_topic(self, message: IRCMessage):
        """Handle TOPIC command."""
        self.message_received.emit(self.server_name, message)
    
    def _handle_kick(self, message: IRCMessage):
        """Handle KICK command."""
        channel = message.params[0] if message.params else None
        kicked_nick = message.params[1] if len(message.params) > 1 else None
        
        if channel and kicked_nick == self.nickname:
            self.joined_channels.discard(channel)
            logger.info(f"Kicked from channel: {channel}")
        
        self.message_received.emit(self.server_name, message)

