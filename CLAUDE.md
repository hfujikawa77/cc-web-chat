# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Chat-based Web UI for Claude Code CLI that enables smartphone control of Claude Code running on WSL environments. The system consists of a simple HTTP chat server with direct Claude Code CLI integration.

## Architecture

```
[Smartphone Browser] ←→ [HTML Chat UI] ←→ [HTTP Server] ←→ [Claude Code CLI]
                                                    ↓
                                              [Session Storage]
```

## Core Files

- `claude_chat_server.py` - HTTP server with chat API, streaming, and session management
- `claude_chat.html` - Modern chat interface with Japanese support and streaming UI
- `requirements.txt` - Python dependencies including FastAPI and SQLAlchemy
- `logs/` - Directory for conversation logs and outputs
- `README.md` - Project documentation and setup instructions
- `REQUIREMENTS.md` - Detailed requirements and specifications

## Dependencies

The project uses several Python packages for enhanced functionality:

### Core Dependencies
- **FastAPI**: Modern web framework for building APIs
- **Uvicorn**: ASGI server for running FastAPI applications
- **WebSockets**: Real-time communication support
- **SQLAlchemy**: Database ORM with async support
- **Python-Dotenv**: Environment variable management
- **Pydantic**: Data validation and settings management

### Additional Features
- **StructLog**: Structured logging
- **Rich**: Terminal formatting and progress bars
- **PSUtil**: System and process utilities
- **Watchdog**: File system monitoring
- **PassLib**: Password hashing utilities
- **Python-Jose**: JWT token handling
- **SlowAPI**: Rate limiting support

### Installation
```bash
# Install dependencies
pip install -r requirements.txt
```

## Development Commands

### Chat Server Setup
```bash
# Start chat server
python claude_chat_server.py

# Open browser
# Navigate to http://127.0.0.1:8081/claude_chat.html
```

### Environment Configuration
```bash
# Create .env file for configuration
cp .env.example .env

# Configure settings:
# PORT=8081
# MAX_MESSAGES_PER_SESSION=50
# CONTEXT_WINDOW_SIZE=5
# CLAUDE_STREAM_TIMEOUT=180
```

## Core Components

### Chat Communication
- **Standard Endpoint**: `POST /api/chat`
- **Streaming Endpoint**: `GET /api/chat/stream` (Server-Sent Events)
- **Port**: 8081
- **Methods**: HTTP POST with JSON, SSE for streaming
- **Session Management**: UUID-based session tracking with conversation history
- **Real-time Updates**: Progress indicators, cost tracking, duration display

### Claude Code Integration
- **Standard Command**: `claude --print --dangerously-skip-permissions [prompt]`
- **Streaming Command**: `claude --print --stream-json --dangerously-skip-permissions [prompt]`
- **Permission Bypass**: Uses `--dangerously-skip-permissions` flag to enable file creation
- **Timeout**: 180 seconds (3 minutes) per request
- **Context**: Maintains conversation history (last 10 messages)
- **Fallback**: Automatic fallback to standard mode if streaming fails

### Message Format
```json
{
  "message": "ユーザーメッセージ",
  "session_id": "session_uuid"
}
```

### Response Format
```json
{
  "response": "Claude Codeの応答",
  "session_id": "session_uuid",
  "timestamp": "2024-01-01T00:00:00"
}
```

## Features

### Chat Interface
- **Japanese Support**: Full UTF-8 encoding with proper charset headers
- **Modern UI**: Clean, responsive design with streaming progress indicators
- **Session Persistence**: Conversation history maintained across page reloads
- **Real-time Feedback**: Progress indicators (🔄⚙️💭✅), cost tracking, duration display
- **Example Commands**: Quick-start buttons for common file creation tasks
- **Conditional Markdown**: Advanced rendering for .md files with Prism.js syntax highlighting
- **Code Features**: Copy buttons, language detection, responsive code blocks
- **Request Management**: Cancellation support, request batching, memory optimization

### Session Management
- **Storage**: In-memory dictionary with session UUIDs
- **History Limit**: 50 messages per session, 5 messages context window
- **Persistence**: Browser localStorage for session ID continuity
- **Environment Configuration**: Configurable via environment variables

### Error Handling
- **Timeout Protection**: 180-second (3 minutes) timeout for streaming, 60-second for standard
- **Fallback Mechanism**: Automatic fallback from streaming to standard mode
- **Error Messages**: User-friendly Japanese error messages
- **CORS Support**: Proper headers for cross-origin requests
- **Request Cancellation**: ESC key support with AbortController

## Development Notes

### File Creation Capability
- Claude Code CLI can create files directly using `--dangerously-skip-permissions`
- No additional file handling needed in the server
- Claude Code handles all file operations internally

### Streaming Architecture

#### Server-Sent Events (SSE) Flow
1. Client requests streaming via `/api/chat/stream`
2. Server establishes SSE connection
3. Real-time progress updates sent to client:
   - `init`: Processing started
   - `progress`: Step-by-step updates with indicators
   - `response`: Partial content chunks
   - `complete`: Final response with cost/duration
   - `error`: Error states with fallback

#### Progress Indicators
- 🔄 **Processing**: Initial request handling
- ⚙️ **Working**: Claude Code CLI execution  
- 💭 **Thinking**: Response generation
- ✅ **Complete**: Finished with metrics

#### Standard Conversation Flow
1. User types message in HTML interface
2. JavaScript sends POST to `/api/chat` or streams via `/api/chat/stream`
3. Server builds context from session history
4. Server calls Claude Code CLI with streaming or standard mode
5. Progress updates sent via SSE (streaming) or final response (standard)
6. Session history updated with exchange

#### Conditional Markdown Processing
- **Detection**: Automatically identifies .md file requests
- **Enhanced Rendering**: Prism.js syntax highlighting for code blocks
- **Features**: Copy buttons, language detection, responsive design
- **Fallback**: Standard text rendering for non-markdown content

### Character Encoding
- All responses use `charset=utf-8` headers
- HTML includes `<meta charset="UTF-8">`
- Proper Japanese text display without mojibake

### Security Notes
- Uses `--dangerously-skip-permissions` for file creation capabilities
- Server runs on localhost only (127.0.0.1)
- No authentication implemented (local development only)
- Environment-based configuration for security settings
- CORS protection configurable via environment variables
- Rate limiting support via SlowAPI integration

## Development Commands

### Start Chat System
```bash
# Start the chat server
python claude_chat_server.py

# Server runs on http://127.0.0.1:8081
# Access UI at http://127.0.0.1:8081/claude_chat.html
```

### Testing
```bash
# Test basic file creation
# Open browser → type "test.py ファイルを作って"

# Test streaming functionality
# Open browser → send message and observe real-time progress indicators

# Test conversation continuity
# Send multiple related messages to verify context preservation

# Test markdown rendering
# Request creation or reading of .md files to verify Prism.js integration

# Test fallback mechanism
# Interrupt streaming to verify automatic fallback to standard mode

# Test environment configuration
# Modify .env values and restart server to verify configuration loading
```