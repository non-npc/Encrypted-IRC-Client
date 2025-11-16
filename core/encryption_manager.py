"""
Encryption manager for per-room client-side encryption.
Uses AES-256-GCM with PBKDF2 key derivation.
"""

import base64
import os
import hashlib
import logging
from typing import Optional, Tuple, Dict
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)

# Encryption envelope prefix
ENCRYPTION_PREFIX = "+++ENCV1:"
PBKDF2_ITERATIONS = 100000
NONCE_SIZE = 12  # 96 bits for GCM
TAG_SIZE = 16  # 128 bits for GCM tag


class EncryptionManager:
    """Manages encryption and decryption for room messages."""
    
    def __init__(self, settings_manager):
        """Initialize the encryption manager."""
        self.settings_manager = settings_manager
        self.backend = default_backend()
    
    def derive_key(self, passphrase: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
        """
        Derive an encryption key from a passphrase using PBKDF2.
        
        Args:
            passphrase: The user-provided passphrase
            salt: Optional salt (if None, generates a new one)
        
        Returns:
            Tuple of (derived_key, salt)
        """
        if salt is None:
            salt = os.urandom(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 256 bits for AES-256
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
            backend=self.backend
        )
        
        key = kdf.derive(passphrase.encode('utf-8'))
        return key, salt
    
    def encrypt_message(self, plaintext: str, key: bytes) -> str:
        """
        Encrypt a message using AES-256-GCM.
        
        Args:
            plaintext: The message to encrypt
            key: The encryption key (32 bytes)
        
        Returns:
            Base64-encoded encrypted message (no prefix - all messages in encrypted channels are encrypted)
        """
        try:
            # Generate random nonce
            nonce = os.urandom(NONCE_SIZE)
            
            # Encrypt using AES-GCM
            aesgcm = AESGCM(key)
            ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
            
            # Combine nonce + ciphertext
            # ciphertext already includes the authentication tag at the end
            encrypted_data = nonce + ciphertext
            
            # Encode as Base64 (no prefix - cleaner display)
            encoded = base64.b64encode(encrypted_data).decode('ascii')
            
            return encoded
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            raise
    
    def decrypt_message(self, encrypted_message: str, key: bytes) -> Optional[str]:
        """
        Decrypt a message using AES-256-GCM.
        
        Args:
            encrypted_message: The encrypted message (Base64-encoded, no prefix)
            key: The decryption key (32 bytes)
        
        Returns:
            Decrypted plaintext, or None if decryption fails
        """
        try:
            # Validate key
            if not isinstance(key, bytes):
                logger.error(f"Key is not bytes, got type: {type(key)}")
                return None
            if len(key) != 32:
                logger.error(f"Key has wrong length: {len(key)} bytes, expected 32")
                return None
            
            # Try to remove old prefix format for backward compatibility
            if encrypted_message.startswith(ENCRYPTION_PREFIX):
                encrypted_message = encrypted_message[len(ENCRYPTION_PREFIX):]
            
            # Base64 decode
            try:
                encrypted_data = base64.b64decode(encrypted_message)
            except Exception as e:
                logger.debug(f"Base64 decode error (message may be plaintext): {e}")
                return None
            
            # Extract nonce and ciphertext
            if len(encrypted_data) < NONCE_SIZE + TAG_SIZE:
                logger.debug(f"Encrypted data too short (message may be plaintext): {len(encrypted_data)} bytes, need at least {NONCE_SIZE + TAG_SIZE}")
                return None
            
            nonce = encrypted_data[:NONCE_SIZE]
            ciphertext = encrypted_data[NONCE_SIZE:]
            
            # Decrypt using AES-GCM
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            
            return plaintext.decode('utf-8')
        except Exception as e:
            # Decryption failed - message might be plaintext or wrong key
            error_msg = str(e) if str(e) else repr(e)
            logger.debug(f"Decryption error (message may be plaintext): {error_msg} (type: {type(e).__name__})")
            return None
    
    def is_encrypted_message(self, message: str) -> bool:
        """Check if a message appears to be encrypted (Base64-encoded format)."""
        if not message:
            return False
        
        # Try to remove old prefix format for backward compatibility
        if message.startswith(ENCRYPTION_PREFIX):
            message = message[len(ENCRYPTION_PREFIX):]
        
        # Check if message looks like Base64-encoded encrypted data
        # Encrypted messages will be Base64 and have a minimum length
        # (nonce + minimum ciphertext + tag = at least 28 bytes = ~38 Base64 chars)
        try:
            # Check if it's valid Base64
            decoded = base64.b64decode(message, validate=True)
            # Check if it's long enough to be encrypted data (nonce + tag minimum)
            if len(decoded) >= NONCE_SIZE + TAG_SIZE:
                return True
        except Exception:
            # Not valid Base64 or too short
            pass
        
        return False
    
    def _get_canonical_server_id(self, server_name: str, server_config: Optional[Dict] = None) -> str:
        """
        Get a canonical server identifier for key derivation.
        Uses hostname if available, otherwise falls back to server_name.
        This ensures all users connecting to the same server get the same salt.
        """
        if server_config and 'hostname' in server_config:
            return server_config['hostname']
        return server_name
    
    def _get_pm_identifier(self, own_nick: str, other_nick: str) -> str:
        """
        Get a deterministic identifier for a private message conversation.
        Sorts nicks alphabetically to ensure both users get the same identifier.
        
        Args:
            own_nick: Our nickname
            other_nick: The other user's nickname
        
        Returns:
            A deterministic PM identifier (sorted nicks joined by ':')
        """
        # Sort nicks alphabetically (case-insensitive) to ensure consistency
        nicks = sorted([own_nick.lower(), other_nick.lower()])
        return f"{nicks[0]}:{nicks[1]}"
    
    def get_room_key_data(self, server_name: str, channel_name: str, 
                          server_config: Optional[Dict] = None,
                          own_nick: Optional[str] = None,
                          is_pm: bool = False) -> Optional[bytes]:
        """
        Get the derived key for a room or PM from the database.
        
        Args:
            server_name: Display name of the server
            channel_name: Channel name (or other user's nick for PMs)
            server_config: Optional server config dict to get canonical hostname
            own_nick: Our own nickname (required for PMs)
            is_pm: Whether this is a private message
        
        Returns:
            The derived key bytes, or None if no key is configured
        """
        # Use canonical server ID (hostname) for lookup
        canonical_id = self._get_canonical_server_id(server_name, server_config)
        
        # For PMs, create a deterministic identifier from both users
        if is_pm and own_nick:
            pm_id = self._get_pm_identifier(own_nick, channel_name)
            # Try lookup with canonical ID first
            key_data = self.settings_manager.get_room_key(canonical_id, pm_id)
            if not key_data:
                key_data = self.settings_manager.get_room_key(server_name, pm_id)
        else:
            # For channels, use channel name directly
            key_data = self.settings_manager.get_room_key(canonical_id, channel_name)
            if not key_data:
                key_data = self.settings_manager.get_room_key(server_name, channel_name)
        
        if key_data:
            derived_key = key_data.get('derived_key')
            if derived_key:
                # Ensure it's bytes (SQLite BLOB should already be bytes, but verify)
                if isinstance(derived_key, bytes):
                    return derived_key
                elif isinstance(derived_key, str):
                    # If somehow it's a string, try to decode it
                    lookup_id = pm_id if (is_pm and own_nick) else channel_name
                    logger.warning(f"Key is string, attempting to decode: {canonical_id}:{lookup_id}")
                    return derived_key.encode('latin-1')
                else:
                    lookup_id = pm_id if (is_pm and own_nick) else channel_name
                    logger.error(f"Key has unexpected type: {type(derived_key)} for {canonical_id}:{lookup_id}")
            else:
                lookup_id = pm_id if (is_pm and own_nick) else channel_name
                logger.warning(f"No derived_key in key_data for {canonical_id}:{lookup_id}")
        return None
    
    def set_room_key_from_passphrase(self, server_name: str, channel_name: str,
                                     passphrase: str, server_config: Optional[Dict] = None,
                                     own_nick: Optional[str] = None,
                                     is_pm: bool = False) -> Tuple[bytes, bytes]:
        """
        Derive and store a key for a room or PM from a passphrase.
        
        Uses a deterministic salt based on canonical server ID (hostname) and channel/PM identifier
        so that all users in the same channel/PM with the same passphrase derive the same key.
        
        Args:
            server_name: Display name of the server
            channel_name: Channel name (or other user's nick for PMs)
            passphrase: User passphrase
            server_config: Optional server config dict to get canonical hostname
            own_nick: Our own nickname (required for PMs)
            is_pm: Whether this is a private message
        
        Returns:
            Tuple of (derived_key, salt)
        """
        # Use canonical server ID (hostname) for salt derivation
        canonical_id = self._get_canonical_server_id(server_name, server_config)
        
        # For PMs, create a deterministic identifier from both users
        if is_pm and own_nick:
            pm_id = self._get_pm_identifier(own_nick, channel_name)
            # Generate deterministic salt from canonical server ID and PM identifier
            salt_input = f"{canonical_id}:{pm_id}".encode('utf-8')
            storage_id = pm_id
        else:
            # For channels, use channel name directly
            salt_input = f"{canonical_id}:{channel_name}".encode('utf-8')
            storage_id = channel_name
        
        salt = hashlib.sha256(salt_input).digest()[:16]  # Use first 16 bytes
        
        logger.info(f"Deriving key for {canonical_id}:{storage_id} (display: {server_name}) with salt hash: {salt.hex()[:16]}...")
        
        key, salt = self.derive_key(passphrase, salt=salt)
        
        # Store using canonical ID for consistency
        self.settings_manager.set_room_key(
            canonical_id, storage_id, salt, key, PBKDF2_ITERATIONS
        )
        
        logger.info(f"Key derived and stored for {canonical_id}:{storage_id}, key length: {len(key)} bytes")
        return key, salt
    
    def remove_room_key(self, server_name: str, channel_name: str):
        """Remove the encryption key for a room."""
        self.settings_manager.remove_room_key(server_name, channel_name)

