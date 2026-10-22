# Agent.py Summary

This is a sophisticated local-first AI agent built with FastAPI that operates entirely offline using local AI models. It features a multi-step execution flow with permission gating for safety.

## Core Architecture

The agent follows a structured execution loop:
1. Try to answer directly from the local LLM (no tools)
2. If insufficient, use Ollama's built-in tool calling
3. Permission check - calls requiring approval are parked until user answers
4. Tool execution with error handling
5. Results fed back to the LLM
6. Repeat until the model answers without calling tools

## Key Features

### Safety & Permissions
- Permission-gated tools with safety measures like diff previews before file writes
- Project-sandboxed access controls
- All actions logged to local storage
- Local-first approach that tries to answer without tools when possible

### Tool Capabilities
The agent has extensive tool schemas for:
- File operations (read_files, write_file, edit_file)
- Web browsing (search_web, read_web_content) 
- Calendar management (create_calendar_event, read_calendar)
- Audio handling (play_audio_file, save_note, list_notes)
- System commands and configuration

### Execution Modes
Supports both interactive CLI mode and streaming web interface with:
- Streaming responses
- Error recovery mechanisms
- XML parsing fallbacks for tool calls
- Failure detection and model correction

### Configuration
Uses environment variables extensively for:
- MAX_STEPS setting (default 8)
- Ollama settings and text-to-speech capabilities
- Multiple voices and audio formats support