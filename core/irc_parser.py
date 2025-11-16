"""
IRC protocol message parser.
Parses raw IRC lines into structured message objects.
"""

import re
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class IRCMessage:
    """Represents a parsed IRC message."""
    prefix: Optional[str] = None
    command: str = ""
    params: list = None
    raw: str = ""
    
    def __post_init__(self):
        if self.params is None:
            self.params = []
    
    @property
    def nick(self) -> Optional[str]:
        """Extract nickname from prefix."""
        if not self.prefix:
            return None
        # Prefix format: nick!user@host or server
        match = re.match(r'([^!]+)', self.prefix)
        return match.group(1) if match else None
    
    @property
    def user(self) -> Optional[str]:
        """Extract username from prefix."""
        if not self.prefix:
            return None
        match = re.match(r'[^!]+!([^@]+)', self.prefix)
        return match.group(1) if match else None
    
    @property
    def host(self) -> Optional[str]:
        """Extract hostname from prefix."""
        if not self.prefix:
            return None
        match = re.match(r'[^!]+![^@]+@(.+)', self.prefix)
        return match.group(1) if match else None
    
    @property
    def target(self) -> Optional[str]:
        """Get the target (channel or nick) from params."""
        if self.params:
            return self.params[0]
        return None
    
    @property
    def text(self) -> Optional[str]:
        """Get the message text (usually the last param, or first if only one param for numeric replies)."""
        if not self.params:
            return None
        # For numeric replies like 001, the text is usually the last param
        # For commands like PRIVMSG, the text is also the last param
        return self.params[-1] if self.params else None


class IRCParser:
    """Parses IRC protocol messages."""
    
    # IRC message pattern: [:prefix] COMMAND [params] [:trailing]
    # More robust pattern that handles various IRC message formats
    # Format: :prefix COMMAND param1 param2 :trailing text
    IRC_PATTERN = re.compile(
        r'^(?::([^\s]+)\s+)?'  # Optional prefix with space
        r'([A-Z]+|[0-9]{3})'   # Command (word or 3 digits)
        r'(?:\s+([^:]+))?'     # Optional middle params (everything before :)
        r'(?:\s+:(.+))?$'      # Optional trailing param (after :)
    )
    
    def parse(self, line: str) -> Optional[IRCMessage]:
        """
        Parse a raw IRC line into an IRCMessage object.
        
        Args:
            line: Raw IRC line (without CRLF)
        
        Returns:
            IRCMessage object, or None if parsing fails
        """
        line = line.strip()
        if not line:
            return None
        
        try:
            # Manual parsing to handle : in middle params correctly
            # IRC format: [:prefix] COMMAND [params] [:trailing]
            # Trailing param starts with " :" (space + colon)
            
            original_line = line  # Keep original for raw field
            prefix = None
            command = None
            params = []
            
            # Check for prefix
            if line.startswith(':'):
                # Extract prefix (everything up to first space)
                space_idx = line.find(' ', 1)
                if space_idx > 0:
                    prefix = line[1:space_idx]
                    line = line[space_idx + 1:].lstrip()
                else:
                    # No space after prefix? Invalid format
                    logger.warning(f"Invalid IRC line format: {original_line}")
                    return None
            
            # Extract command (first word)
            parts = line.split(None, 1)
            if not parts:
                logger.warning(f"No command found in IRC line: {line}")
                return None
            
            command = parts[0]
            
            # Remaining part (params)
            if len(parts) > 1:
                remaining = parts[1]
                
                # Check for trailing param (starts with " :")
                trailing_idx = remaining.find(' :')
                if trailing_idx >= 0:
                    # Split into middle params and trailing param
                    middle_params = remaining[:trailing_idx].strip()
                    trailing = remaining[trailing_idx + 2:]  # Skip " :"
                    
                    # Parse middle params
                    if middle_params:
                        params.extend(middle_params.split())
                    
                    # Add trailing param (can be empty)
                    params.append(trailing)
                else:
                    # No trailing param, just split all params
                    if remaining:
                        params.extend(remaining.split())
            
            return IRCMessage(
                prefix=prefix,
                command=command,
                params=params,
                raw=original_line
            )
        except Exception as e:
            logger.error(f"Error parsing IRC line '{original_line}': {e}")
            return None
    
    def build_message(self, command: str, *params: str, prefix: Optional[str] = None) -> str:
        """
        Build an IRC message string from components.
        
        Args:
            command: IRC command
            *params: Command parameters
            prefix: Optional prefix (usually not needed for client messages)
        
        Returns:
            Formatted IRC message line
        """
        parts = []
        if prefix:
            parts.append(f":{prefix}")
        
        parts.append(command)
        
        if params:
            # Last param with spaces goes after :
            if len(params) > 1 and ' ' in params[-1]:
                regular_params = params[:-1]
                trailing = params[-1]
                if regular_params:
                    parts.extend(regular_params)
                parts.append(f":{trailing}")
            else:
                parts.extend(params)
        
        return ' '.join(parts)

