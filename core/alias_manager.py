"""
Alias manager for custom command aliases.
Handles alias expansion and variable substitution.
"""

import re
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class AliasManager:
    """Manages command aliases and expansion."""
    
    def __init__(self, settings_manager):
        """Initialize the alias manager."""
        self.settings_manager = settings_manager
        self._aliases_cache: Optional[Dict[str, str]] = None
    
    def _load_aliases(self):
        """Load aliases from database into cache."""
        if self._aliases_cache is None:
            self._aliases_cache = {}
            aliases = self.settings_manager.get_aliases()
            for alias in aliases:
                self._aliases_cache[alias['alias_name']] = alias['expansion']
    
    def _clear_cache(self):
        """Clear the aliases cache."""
        self._aliases_cache = None
    
    def expand_alias(self, command_line: str) -> str:
        """
        Expand aliases in a command line.
        
        Args:
            command_line: The command line (e.g., "/j #channel")
        
        Returns:
            Expanded command line
        """
        if not command_line.startswith('/'):
            return command_line
        
        # Extract command and arguments
        parts = command_line[1:].split(None, 1)
        if not parts:
            return command_line
        
        alias_name = parts[0].lower()
        args_str = parts[1] if len(parts) > 1 else ""
        
        # Load aliases if needed
        self._load_aliases()
        
        # Check if alias exists
        if alias_name not in self._aliases_cache:
            return command_line
        
        expansion = self._aliases_cache[alias_name]
        
        # Replace variables: $1, $2, etc. with arguments
        # Split arguments by spaces, but preserve quoted strings
        args = self._parse_arguments(args_str)
        
        # Replace $1, $2, etc.
        result = expansion
        for i, arg in enumerate(args, 1):
            result = result.replace(f'${i}', arg)
        
        # Replace $* with all arguments
        if '$*' in result:
            result = result.replace('$*', args_str)
        
        # Replace $1- with all arguments from $1 onwards
        if '$1-' in result:
            remaining = ' '.join(args) if args else ''
            result = result.replace('$1-', remaining)
        
        # Replace $2- with all arguments from $2 onwards, etc.
        for i in range(2, len(args) + 1):
            pattern = f'${i}-'
            if pattern in result:
                remaining = ' '.join(args[i-1:]) if len(args) >= i else ''
                result = result.replace(pattern, remaining)
        
        return result
    
    def _parse_arguments(self, args_str: str) -> List[str]:
        """
        Parse command arguments, handling quoted strings.
        
        Args:
            args_str: Arguments string
        
        Returns:
            List of parsed arguments
        """
        if not args_str.strip():
            return []
        
        args = []
        current = []
        in_quotes = False
        quote_char = None
        
        i = 0
        while i < len(args_str):
            char = args_str[i]
            
            if char in ('"', "'") and (i == 0 or args_str[i-1] != '\\'):
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif char == quote_char:
                    in_quotes = False
                    quote_char = None
                else:
                    current.append(char)
            elif char == ' ' and not in_quotes:
                if current:
                    args.append(''.join(current))
                    current = []
            else:
                if char == '\\' and i + 1 < len(args_str) and args_str[i+1] in ('"', "'", '\\'):
                    i += 1
                    current.append(args_str[i])
                else:
                    current.append(char)
            
            i += 1
        
        if current:
            args.append(''.join(current))
        
        return args
    
    def add_alias(self, alias_name: str, expansion: str):
        """Add or update an alias."""
        self.settings_manager.add_alias(alias_name, expansion)
        self._clear_cache()
    
    def delete_alias(self, alias_name: str):
        """Delete an alias."""
        self.settings_manager.delete_alias(alias_name)
        self._clear_cache()
    
    def get_aliases(self) -> List[Dict[str, Any]]:
        """Get all aliases."""
        return self.settings_manager.get_aliases()

