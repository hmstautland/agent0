# rules, flags, constants

# Per-action override on top of the tool's risk level: "auto" skips the
# permission prompt even when the tool's risk is medium/high, "ask" always
# prompts. Actions not listed fall back to the tool's risk level.
# Tools marked "external" in tools/registry.py ignore "auto": they ask once
# per login session (see core/permission.py).
RULES = {
    "create_calendar_event": "ask",
    "get_project_structure": "auto",
    "write_file": "ask",
    "edit_file": "ask",
    "extract_inline_scripts": "ask",
    "verify_app": "auto",
    "read_files": "auto",
    "search_files": "auto",
}

MAX_RESULTS = 5
