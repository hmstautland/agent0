TOOLS = {
    "get_project_structure": {
        "func": "tools.files.get_project_structure",
        "description": "Get a list of files in the project",
        "risk": "medium"
    },
    "search_files": {
        "func": "tools.files.search_files",
        "description": "Search project files by keyword",
        "risk": "medium"
    },
    "read_files": {
        "func": "tools.files.read_files",
        "description": "Read file contents from the project",
        "risk": "medium"
    },
    "write_file": {
        "func": "tools.files.write_file",
        "description": "Write content to a file in the project (replaces the whole file - needs the full new content)",
        "risk": "high"
    },
    "edit_file": {
        "func": "tools.files.edit_file",
        "description": "Replace an exact snippet in a file, arguments: path, old_text, new_text. Prefer this over write_file when changing part of a file",
        "risk": "high"
    },
    "extract_inline_scripts": {
        "func": "tools.files.extract_inline_scripts",
        "description": "Move inline <script> code out of an HTML file into a .js file and link it with <script src>. Arguments: path, optional dest (defaults to static/<name>.js). Use this for 'no scripts defined in the html' requests - it moves the code instead of deleting it",
        "risk": "high"
    },
    "verify_app": {
        "func": "tools.verify.verify_app",
        "description": "Check nothing is broken after editing: compiles templates, resolves includes, checks referenced /static and /media files exist, imports the app. Takes no arguments. Run this after changing templates or static files",
        "risk": "low"
    },

    "get_news": {
        "func": "tools.web.get_news",
        "description": "Get latest news headlines",
        "risk": "low",
        "external": 1
    },
    "search_web": {
        "func": "tools.web.search_web",
        "description": "Search the web for information",
        "risk": "medium",
        "external": 1
    },
    "read_web_content": {
        "func": "tools.web.read_web_content",
        "description": "Read and extract textual content from web pages (list of URLs)",
        "risk": "medium",
        "external": 1
    },
    "create_calendar_event": {
        "func": "features.calendar.calendar.create_event",
        "description": "Create a calendar event with title, start, and optional end time",
        "risk": "medium"
    },
    "read_calendar": {
        "func": "features.calendar.calendar.read_calendar",
        "description": "Read local calendar events",
        "risk": "low"
    },
    "play_audio_file": {
        "func": "features.audio.player.play_audio_file",
        "description": "Find and play a saved audio file from local_storage/audio by (partial) filename - e.g. 'my-music' matches 'my-holiday-music.mp3'. Pass a bare number to pick from the candidates a previous call returned (e.g. after several files matched). Never guess a filename - call this to search.",
        "risk": "low"
    }
}