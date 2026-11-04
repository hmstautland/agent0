import re
from datetime import datetime
from pathlib import Path

NOTE_FOLDER = Path("local_storage")
NOTE_FOLDER.mkdir(exist_ok=True)


def sanitize_note_content(text: str) -> str:
    if text is None:
        return ""
    cleaned = str(text).strip()
    # Remove script tags and any HTML tags for low-risk storage
    cleaned = re.sub(r"(?is)<script.*?>.*?</script>", "", cleaned)
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    cleaned = cleaned.replace("\r", "")
    return cleaned.strip()


def parse_note_command(text: str) -> str | None:
    if not text:
        return None
    cleaned = str(text).strip()
    match = re.match(r"^\s*(?:take note|note)\b[:\-]?\s*(.*)$", cleaned, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    note_content = match.group(1).strip()
    note_content = sanitize_note_content(note_content)
    return note_content or None


def save_note_text(note_text: str, source: str = "text") -> str:
    note_text = sanitize_note_content(note_text)
    now = datetime.now()
    # Microseconds so two notes saved in the same second don't overwrite each other
    filename = f"note_{now:%Y%m%d_%H%M%S_%f}.txt"
    file_path = NOTE_FOLDER / filename
    content = f"Saved: {now.isoformat()}\nSource: {source}\n\n{note_text}\n"
    with file_path.open("w", encoding="utf-8") as f:
        f.write(content)
    return str(file_path)


def save_note(text=None, note=None, content=None, **kwargs):
    """Tool: save a note the LLM was asked to remember."""
    text = text or note or content
    if not text or not sanitize_note_content(text):
        return "Nothing to save: pass the note as text."
    return f"Note saved to {save_note_text(text, source='agent')}"


def _read_note(path: Path) -> dict:
    header, _, body = path.read_text(encoding="utf-8").partition("\n\n")
    saved = next((line[len("Saved: "):] for line in header.splitlines() if line.startswith("Saved: ")), "")
    return {"file": str(path), "saved": saved, "text": body.strip()}


def list_notes(query=None, limit=10, **kwargs):
    """Tool: saved notes, newest first, optionally only those containing query."""
    try:
        limit = max(1, int(limit))
    except (TypeError, ValueError):
        limit = 10

    notes = []
    for path in sorted(NOTE_FOLDER.glob("note_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True):
        note = _read_note(path)
        if query and str(query).lower() not in note["text"].lower():
            continue
        notes.append(note)
        if len(notes) >= limit:
            break

    if notes:
        return notes
    return f"No notes contain '{query}'." if query else "No notes saved yet."
