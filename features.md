# Encrypted IRC Client - Features

A comprehensive list of all features implemented in the Encrypted IRC Client application.

## Core IRC Functionality

### Server Management
- **Multiple Server Connections**: Connect to multiple IRC servers simultaneously
- **Server Configuration**: Add, edit, and remove server configurations with:
  - Display name
  - Hostname and port
  - SSL/TLS support
  - Nickname and alternative nickname
  - Username and realname
  - Auto-join channels (comma-separated list)
  - Default encoding
- **Auto-Connect**: Configure one server to automatically connect on startup
- **Auto-Join Channels**: Automatically join specified channels after MOTD (Message of the Day) is received
- **Connection Status**: Visual indicators for server connection status (connected/disconnected)
- **Server List Tree View**: Hierarchical display of all servers and their channels in the left sidebar

### IRC Protocol Support
- **Full IRC Protocol Implementation**: Full support for standard IRC commands and messages
- **Supported Commands**:
  - `/join #channel` - Join a channel
  - `/part #channel [reason]` - Leave a channel
  - `/nick newnick` - Change nickname
  - `/msg nickname message` - Send private message
  - `/query nickname message` - Open private message window
  - `/whois nickname` - Get user information
  - `/topic #channel [topic]` - View or set channel topic
  - `/mode #channel [modes]` - Set channel modes
  - `/kick #channel nickname [reason]` - Kick user from channel
  - `/quit [message]` - Disconnect from server
  - `/list` - List available channels on server
- **Numeric Replies**: Proper handling of all IRC numeric replies (001, 322, 323, 353, 366, 372, 375, 376, 422, 433, etc.)
- **PING/PONG**: Automatic keep-alive handling
- **Message Buffering**: Handles incomplete IRC lines received over the network

### Channel Management
- **Tabbed Interface**: Each channel opens in its own tab
- **Channel List Dialog**: Browse and join channels from a searchable, sortable list
- **Channel Topic Display**: Shows channel topic in a dedicated bar at the top
- **Nicklist**: Displays all users in the channel with proper prefix handling (@, +, %, &, ~)
- **User Prefix Management**: Correctly handles and displays user privileges (operators, voiced users, etc.)
- **Duplicate Prevention**: Prevents duplicate entries when users have prefixes (e.g., @Jimb0z and Jimb0z)
- **Channel Status Messages**: Displays join, part, quit, kick, and mode change events
- **User List Context Menu**: Right-click on any user in the nicklist to:
  - Send a private message (opens PM tab)

### Private Messages
- **Private Message Windows**: Separate tabs for private message conversations
- **PM from Commands**: `/msg` and `/query` commands open PM windows
- **PM Routing**: Messages are correctly routed to the appropriate PM window
- **PM from User List**: Right-click on any user in the channel nicklist to send a private message
- **Automatic PM Tab Creation**: PM tabs automatically open when receiving messages from other users

## Encryption Features

### Per-Room Client-Side Encryption
- **AES-256-GCM Encryption**: Industry-standard authenticated encryption
- **Per-Channel Keys**: Each channel can have its own encryption key (passphrase)
- **Per-Conversation Keys**: Private message conversations can also have encryption keys
- **Deterministic Key Derivation**: Uses PBKDF2-HMAC-SHA256 with deterministic salt based on:
  - Server hostname and channel name (for channels)
  - Server hostname and sorted user nicks (for private messages)
- **Transparent Encryption**: Messages are automatically encrypted before sending and decrypted after receiving
- **No Prefix Required**: All messages in encrypted channels/conversations are assumed to be encrypted
- **Backward Compatibility**: Still supports old prefix format for existing encrypted messages

### Encryption Management
- **Encryption Key Dialog**: Set, change, or remove encryption keys per channel or private message conversation
- **PM Encryption Support**: Private messages can be encrypted with shared passphrases between two users
- **Visual Indicators**: Lock icon (🔒) appears in:
  - Channel/PM tab title
  - Input area lock button
- **Key Storage**: Derived keys and salts stored securely in SQLite database (not plaintext passphrases)
- **Decryption Failure Handling**: Shows ⚠️ (warning icon) for messages that cannot be decrypted or are not encrypted
- **Canonical Server ID**: Uses server hostname for consistent key derivation across clients
- **Consistent PM Keys**: Both users in a PM conversation derive the same key from the same passphrase using sorted nicknames

## User Interface

### Main Window Layout
- **Traditional IRC Layout**: Familiar three-pane layout:
  - Left: Server and channel tree view
  - Center: Tabbed message windows
  - Right: Nicklist (in channel windows)
- **Tabbed Windows**: Multiple channels and PMs in tabs
- **Server Status Tab**: Dedicated tab per server showing:
  - Connection progress messages
  - Server MOTD
  - Server messages and events
  - Command input for IRC commands
- **Status Bar**: Shows current connection status

### Message Display
- **Message Formatting**: 
  - Timestamps (configurable format, can be toggled)
  - Nickname highlighting with deterministic colors
  - Color-coded message types:
    - Green for joins
    - Red for parts/quits/kicks
    - Blue for status messages
    - Yellow for nick changes
    - Gray for notices
- **Clickable Links**: URLs in messages are automatically detected and made clickable
  - Clicking a link opens it in your default web browser
  - Links are visually distinct with hover effects
  - Supports http://, https://, and other URL formats
- **Mention Highlighting**: Highlights messages that mention your nickname
- **Auto-Scroll**: Automatically scrolls to bottom for new messages (unless user has scrolled up)
- **Message Echo**: Sent messages appear immediately in your own chat window

### Tree View
- **Server List**: Shows all configured servers (not just auto-connect ones)
- **Channel Hierarchy**: Channels displayed under their parent server
- **Visual Status**: Connection status indicators (🔌 for disconnected, ✓ for connected)
- **Expandable**: Servers expand to show their channels when connected
- **Double-Click Navigation**: Double-click servers or channels to open their windows
- **Context Menu**: Right-click menu for server and channel actions

### Input and Commands
- **Command Input**: Enter IRC commands directly in the status tab
- **Message Input**: Separate input field for each channel/PM window
- **Keyboard Shortcuts**:
  - `Ctrl+N`: Open server list dialog
  - `Ctrl+K`: Open encryption key dialog for current channel
  - `Ctrl+L`: Open logs folder
- **Command Expansion**: Aliases expand before sending commands

## Aliases System

### Custom Commands
- **Alias Management**: Create custom command aliases
- **Variable Substitution**: Use `$1`, `$2`, etc. for arguments in aliases
- **Alias Dialog**: Manage aliases through Tools → Aliases menu
- **Persistent Storage**: Aliases stored in SQLite database
- **Example**: Define `/j` as `/join $1` to quickly join channels

## Preferences and Settings

### Appearance Settings
- **Font Configuration**: Customizable font family and size
- **Theme Selection**: Light or dark theme
- **Timestamp Options**: 
  - Toggle timestamps on/off
  - Custom timestamp format
- **Color Schemes**: Color-coded messages for different event types

### Connection Settings
- **Auto-Reconnect**: Option to automatically reconnect on disconnect
- **Reconnect Delay**: Configurable delay before reconnecting

### Logging Settings
- **Enable/Disable Logging**: Toggle message logging
- **Log Directory**: Customizable log file location
- **Automatic Logging**: Messages automatically logged to files organized by server/channel/date

## SSL/TLS Support

- **SSL/TLS Connections**: Full support for encrypted IRC connections
- **Self-Signed Certificates**: Option to accept self-signed certificates
- **Secure by Default**: SSL checkbox in server configuration
- **Port Detection**: Common SSL ports (6697) supported

## Advanced Features

### Message Filtering
- **Status Tab Filtering**: Filters out noise messages like:
  - "End of /MOTD command"
  - "End of /NAMES list"
  - Individual nicknames from NAMES replies
- **Smart Routing**: Messages correctly routed to appropriate windows

### Connection Management
- **Connection Progress**: Status messages show:
  - "Attempting to connect to server..."
  - "Connected... Getting MOTD..."
  - "MOTD complete. Auto-joining..."
  - "Disconnected from host..."
- **Error Handling**: Graceful handling of connection errors with user-friendly messages
- **Disconnect Cleanup**: Properly removes channel tabs and cleans up memory on disconnect

### Channel List
- **Channel Browser**: Browse all available channels on a server
- **Filtering**: Search and filter channels by name
- **Sorting**: Sort channels by name or user count
- **Join from List**: Join channels directly from the list dialog
- **Performance**: Optimized for large channel lists with batched updates

### System Tray
- **Tray Icon**: Minimize to system tray
- **Tray Activation**: Double-click to restore window
- **Always Available**: Application remains accessible from system tray

## Data Persistence

### SQLite Database
- **Server Configurations**: All server settings persisted
- **Global Settings**: Application preferences stored
- **Room Keys**: Encryption keys and salts stored securely
- **Aliases**: Custom command aliases persisted
- **Automatic Initialization**: Database and tables created automatically

## Error Handling

### Robust Error Handling
- **Network Errors**: Graceful handling of connection failures
- **Parsing Errors**: Handles malformed IRC messages
- **Decryption Errors**: Clear indication when decryption fails
- **UI Responsiveness**: Non-blocking operations prevent UI freezing
- **Memory Management**: Proper cleanup of widgets and connections

## User Experience

### User-Friendly Behavior
- **Familiar Workflow**: Traditional IRC client interface and behavior
- **Immediate Feedback**: Messages echo immediately when sent
- **Visual Feedback**: Clear indicators for connection status, encryption status
- **Unread Counts**: Tab titles show unread message counts
- **Focus Management**: Input field automatically focused when switching tabs

### Accessibility
- **Keyboard Navigation**: Full keyboard support for common actions
- **Tooltips**: Helpful tooltips on buttons and controls
- **Clear Labels**: Descriptive labels and messages throughout

## Technical Features

### Architecture
- **Modular Design**: Clean separation between core logic and UI
- **Event-Driven**: Asynchronous networking using Qt's event loop
- **Thread-Safe**: Proper handling of cross-thread operations
- **Extensible**: Easy to add new features and commands

### Performance
- **Efficient Updates**: Batched updates for large channel lists
- **Memory Efficient**: Proper cleanup of disconnected servers and channels
- **Non-Blocking**: All network operations are asynchronous

## Security Features

### Encryption Security
- **Strong Cryptography**: AES-256-GCM with PBKDF2 key derivation
- **No Key Transmission**: Keys never sent over the network
- **Local Storage Only**: Keys stored only in local SQLite database
- **Deterministic Salts**: Ensures consistent key derivation across clients

### Data Protection
- **No Plaintext Passphrases**: Only derived keys stored in database
- **Secure Key Management**: Keys managed through secure dialog
- **User Warnings**: Clear warnings about key loss and recovery

## Logging and Debugging

### Message Logging
- **Automatic Logging**: All messages logged to files
- **Organized Structure**: Logs organized by server/channel/date
- **Configurable**: Enable/disable and customize log location
- **Application Logs**: Separate application log for debugging

### Debug Features
- **Connection Status**: Detailed connection progress messages
- **Error Messages**: Clear error messages for troubleshooting
- **Status Window**: View all server messages and events

