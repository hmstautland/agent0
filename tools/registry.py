TOOLS = {
    "get_project_structure": {
        "func": "tools.files.get_project_structure",
        "risk": "medium"
    },
    "search_files": {
        "func": "tools.files.search_files",
        "risk": "medium"
    },
    "read_files": {
        "func": "tools.files.read_files",
        "risk": "medium"
    },
    "write_file": {
        "func": "tools.files.write_file",
        "risk": "high"
    },

    "get_news": {
        "func": "tools.web.get_news",
        "risk": "low"
    },
    "search_web": {
        "func": "tools.web.search_web",
        "risk": "medium"
    },
    "read_email": {
        "func": "tools.email.read_email",
        "risk": "high"
    },
    "create_calendar_event": {
        "func": "tools.calendar.create_event",
        "risk": "high"
    }
}