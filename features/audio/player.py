"""Find and 'play' a saved file from local_storage/audio/.

Registered as a real tool (tools/registry.py) so the LLM can call it, but
also recognised directly via parse_play_command() the same way calendar
creation and note-taking are - the local model isn't reliable at recognizing
"play ..." needs this tool rather than answering "I can't play audio".

"Playing" a file from a backend tool call can't itself make sound - the
result just tells the web UI which /audio/<file> to load into a player (see
core/agent_routes.py's audio_play_result() and features/audio/static/audio-player.js).
"""

import re
from pathlib import Path

from features.audio.text_to_speech import AUDIO_DIR

AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg"}

# The most recent set of ambiguous matches shown to the user, so a follow-up
# like "play number 2" resolves without repeating the search. This is a
# single-process, single-user app (same tradeoff core/speech_to_text.py's
# module-level recording state makes) - it isn't request- or session-scoped,
# so it doesn't survive a server restart and isn't safe for concurrent users.
_last_candidates = []


def _list_audio_files():
    """All saved audio files, newest first."""
    if not AUDIO_DIR.exists():
        return []

    files = [p for p in AUDIO_DIR.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _matches(query, files):
    query = query.strip().lower()
    query_stem = Path(query).stem.lower() if "." in query else query

    return [
        f for f in files
        if query in f.name.lower() or query_stem in f.stem.lower()
    ]


def find_audio_files(query=None):
    """Files in local_storage/audio matching `query` (substring, case-insensitive).

    A query missing its extension still matches (e.g. "my-music" matches
    "my-holiday-music.mp3"). No query returns every saved file, newest first.
    """
    files = _list_audio_files()

    if query is None or not str(query).strip():
        return files

    return _matches(str(query), files)


def _candidate_list(files):
    return [{"number": i + 1, "filename": f.name, "audio_url": f"/audio/{f.name}"} for i, f in enumerate(files)]


def _first_nonempty(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def play_audio_file(query=None, number=None, name=None, file=None, filename=None, **kwargs):
    """Find and 'play' a saved audio file.

    A bare number ("2"), or an explicit `number` argument, resolves against
    the candidate list most recently returned by this same function. Anything
    else is matched by substring against filenames under local_storage/audio.

    Returns one of:
    - {"status": "play", "filename", "audio_url"} - exactly one match
    - {"status": "choose", "candidates": [...]} - several matches (or no
      query at all, to browse everything); each candidate carries the
      "number" a follow-up call can use to pick it
    - {"status": "error", "message"}
    """
    global _last_candidates

    query = _first_nonempty(query, name, file, filename, kwargs.get("text"))

    resolved_number = number
    if resolved_number is None and query is not None and re.fullmatch(r"\s*#?\s*\d+\s*", str(query)):
        resolved_number = query

    if resolved_number is not None:
        try:
            index = int(str(resolved_number).strip().lstrip("#")) - 1
        except ValueError:
            return {"status": "error", "message": f"'{resolved_number}' isn't a valid number."}

        if not _last_candidates:
            return {"status": "error", "message": "There's no previous list to pick a number from - search by name first."}

        if not (0 <= index < len(_last_candidates)):
            return {"status": "error", "message": f"There's no option {resolved_number} - there are only {len(_last_candidates)}."}

        chosen = _last_candidates[index]
        _last_candidates = []
        return {"status": "play", "filename": chosen.name, "audio_url": f"/audio/{chosen.name}"}

    matches = find_audio_files(query)

    if not matches:
        _last_candidates = []
        message = f"No saved audio file matches '{query}'." if query else "There are no saved audio files yet."
        return {"status": "error", "message": message}

    if len(matches) == 1:
        _last_candidates = []
        return {"status": "play", "filename": matches[0].name, "audio_url": f"/audio/{matches[0].name}"}

    _last_candidates = matches
    return {"status": "choose", "candidates": _candidate_list(matches)}


def describe_play_result(result):
    """One-line natural-language summary of a play_audio_file() result."""
    status = result.get("status")

    if status == "play":
        return f"Playing {result['filename']}."

    if status == "choose":
        count = len(result.get("candidates", []))
        return f"Found {count} matching files - pick one below, or say \"play number 1\"."

    return result.get("message", "Couldn't find that file.")


_PLAY_RE = re.compile(
    r"^\s*play\b(?:\s+(?:me\s+)?(?:the\s+)?(?:file\s+|track\s+|number\s+|saved\s+)*(.*))?$",
    re.IGNORECASE,
)


def parse_play_command(text):
    """Detect "play ...", "play number 2", bare "play" style requests.

    Returns kwargs for play_audio_file(), or None if text isn't a play
    request. Anchored to the start of the message, same as
    tools/notes.py's parse_note_command, to avoid firing on unrelated
    sentences that merely contain the word "play".
    """
    if not text:
        return None

    match = _PLAY_RE.match(text.strip())
    if not match:
        return None

    remainder = (match.group(1) or "").strip().strip("\"'")
    return {"query": remainder or None}
