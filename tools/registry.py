# "parameters" is the JSON schema Ollama's built-in tool calling shows the
# model (see agent.tool_schemas). The functions accept a few more argument
# spellings than the schema lists; the schema names the canonical ones.
# "external": 1 marks tools that send data off the machine - they ask for
# approval once per login session (core/permission.py).


def _params(properties=None, required=()):
    return {"type": "object", "properties": properties or {}, "required": list(required)}


_STRING = {"type": "string"}

TOOLS = {
    "get_project_structure": {
        "func": "tools.files.get_project_structure",
        "description": "Get a list of files in the project",
        "risk": "medium",
        "parameters": _params(),
    },
    "search_files": {
        "func": "tools.files.search_files",
        "description": "Search project files by keyword. Returns matching files with the line number and text of the first matches, so you can read just that section with read_files start_line/end_line",
        "risk": "medium",
        "parameters": _params({"keyword": {"type": "string", "description": "Word or phrase to search for"}}, ["keyword"]),
    },
    "read_files": {
        "func": "tools.files.read_files",
        "description": "Read file contents from the project. For a large file, read only the section you need with start_line/end_line",
        "risk": "medium",
        "parameters": _params({
            "path": {"type": "string", "description": "Project-relative file path"},
            "paths": {"type": "array", "items": _STRING, "description": "Several project-relative paths"},
            "start_line": {"type": "integer", "description": "First line to read (1-based, inclusive)"},
            "end_line": {"type": "integer", "description": "Last line to read (inclusive)"},
        }),
    },
    "write_file": {
        "func": "tools.files.write_file",
        "description": "Write content to a file in the project (replaces the whole file - needs the full new content)",
        "risk": "high",
        "parameters": _params({
            "path": {"type": "string", "description": "Project-relative file path"},
            "content": {"type": "string", "description": "The complete new file content"},
        }, ["path", "content"]),
    },
    "edit_file": {
        "func": "tools.files.edit_file",
        "description": "Replace an exact snippet in a file. Prefer this over write_file when changing part of a file",
        "risk": "high",
        "parameters": _params({
            "path": {"type": "string", "description": "Project-relative file path"},
            "old_text": {"type": "string", "description": "Exact text copied from read_files output; must be unique in the file"},
            "new_text": {"type": "string", "description": "Replacement text"},
        }, ["path", "old_text", "new_text"]),
    },
    "extract_inline_scripts": {
        "func": "tools.files.extract_inline_scripts",
        "description": "Move inline <script> code out of an HTML file into a .js file and link it with <script src>. Use this for 'no scripts defined in the html' requests - it moves the code instead of deleting it",
        "risk": "high",
        "parameters": _params({
            "path": {"type": "string", "description": "Project-relative HTML file"},
            "dest": {"type": "string", "description": "Destination .js file (defaults to static/<name>.js)"},
            "overwrite": {"type": "boolean", "description": "Replace dest if it already exists"},
        }, ["path"]),
    },
    "verify_app": {
        "func": "tools.verify.verify_app",
        "description": "Check nothing is broken after editing: compiles templates, resolves includes, checks referenced /static and /media files exist, imports the app. Takes no arguments. Run this after changing templates or static files",
        "risk": "low",
        "parameters": _params(),
    },

    "get_news": {
        "func": "tools.web.get_news",
        "description": "Get latest news headlines for a country",
        "risk": "low",
        "external": 1,
        "parameters": _params({"country": {"type": "string", "description": "Country name, e.g. Norway"}}, ["country"]),
    },
    "search_web": {
        "func": "tools.web.search_web",
        "description": "Search the web for information",
        "risk": "medium",
        "external": 1,
        "parameters": _params({"query": {"type": "string", "description": "Search query"}}, ["query"]),
    },
    "read_web_content": {
        "func": "tools.web.read_web_content",
        "description": "Read and extract textual content from web pages",
        "risk": "medium",
        "external": 1,
        "parameters": _params({"urls": {"type": "array", "items": _STRING, "description": "Page URLs to read"}}, ["urls"]),
    },
    "create_calendar_event": {
        "func": "features.calendar.calendar.create_event",
        "description": "Create a calendar event with title, start, and optional end time",
        "risk": "medium",
        "parameters": _params({
            "title": {"type": "string"},
            "start": {"type": "string", "description": "Start as YYYY-MM-DD HH:MM"},
            "end": {"type": "string", "description": "Optional end as YYYY-MM-DD HH:MM"},
            "description": {"type": "string"},
        }, ["title", "start"]),
    },
    "read_calendar": {
        "func": "features.calendar.calendar.read_calendar",
        "description": "Read local calendar events. Takes no arguments",
        "risk": "low",
        "parameters": _params(),
    },
    "play_audio_file": {
        "func": "features.audio.player.play_audio_file",
        "description": "Find and play a saved audio file from local_storage/audio by (partial) filename - e.g. 'my-music' matches 'my-holiday-music.mp3'. Pass number to pick from the candidates a previous call returned (e.g. after several files matched). Never guess a filename - call this to search.",
        "risk": "low",
        "parameters": _params({
            "query": {"type": "string", "description": "Part of the file name"},
            "number": {"type": "integer", "description": "Candidate number from a previous call"},
        }),
    },
    "save_note": {
        "func": "tools.notes.save_note",
        "description": "Save a note for the user in local storage",
        "risk": "low",
        "parameters": _params({"text": {"type": "string", "description": "The note text"}}, ["text"]),
    },
    "list_notes": {
        "func": "tools.notes.list_notes",
        "description": "List the user's saved notes, newest first, optionally only those containing a search term",
        "risk": "low",
        "parameters": _params({
            "query": {"type": "string", "description": "Only notes containing this text"},
            "limit": {"type": "integer", "description": "Maximum number of notes (default 10)"},
        }),
    },
    "search_history": {
        "func": "core.conversations.search_history",
        "description": "Look up earlier conversations with the user, including previous sessions: what they asked, what you answered and which tools you used. Use it when the user refers to something from before that is not in this conversation (\"what did we change yesterday?\")",
        "risk": "low",
        "parameters": _params({
            "query": {"type": "string", "description": "Text to look for in the questions, answers or tools used; leave out for the most recent turns"},
            "days": {"type": "integer", "description": "Only the last N days"},
            "limit": {"type": "integer", "description": "Maximum number of turns (default 10)"},
        }),
    },
}
