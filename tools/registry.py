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
        "description": "Write content to a file in the project",
        "risk": "high"
    },

    "get_news": {
        "func": "tools.web.get_news",
        "description": "Get latest news headlines",
        "risk": "low"
    },
    "search_web": {
        "func": "tools.web.search_web",
        "description": "Search the web for information",
        "risk": "medium"
    },
    "read_web_content": {
        "func": "tools.web.read_web_content",
        "description": "Read and extract textual content from web pages (list of URLs)",
        "risk": "medium"
    },
    "read_email": {
        "func": "tools.email.read_email",
        "description": "Read latest emails",
        "risk": "high"
    },
    "create_calendar_event": {
        "func": "tools.calendar.create_event",
        "description": "Create calendar event",
        "risk": "medium"
    },
    "read_calendar": {
        "func": "tools.calendar.read_calendar",
        "description": "Read local calendar events",
        "risk": "low"
    }
}