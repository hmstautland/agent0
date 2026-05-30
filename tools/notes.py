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
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"note_{timestamp}.txt"
    file_path = NOTE_FOLDER / filename
    content = f"Saved: {datetime.now().isoformat()}\nSource: {source}\n\n{note_text}\n"
    with file_path.open("w", encoding="utf-8") as f:
        f.write(content)
    return str(file_path)
