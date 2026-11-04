import os
import re
from datetime import datetime
from config.settings import env_int
from core.diff import generate_diff

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Directories that would flood the LLM context with irrelevant files
SKIP_DIRS = {"venv", ".venv", "env", ".git", "__pycache__", "node_modules", "dist", "build", ".pytest_cache", "local_storage", "models"}

MAX_READ_CHARS = 100000
MAX_SEARCH_RESULTS = 20
MAX_MATCHES_PER_FILE = 3
MAX_MATCH_CHARS = 120


# Files the agent must never read, search, write or list: secrets and
# credentials. Reading one would put it into the model's context and into the
# event log (local_storage/logs.txt keeps the start of every tool result).
SENSITIVE_NAME_RE = re.compile(
    r"^(\.env(\..*)?|\.envrc|.*\.(pem|key|p12|pfx|kdbx)|id_(rsa|dsa|ecdsa|ed25519)(\.pub)?"
    r"|\.netrc|\.pgpass|\.npmrc|\.pypirc|credentials(\..*)?|secrets?(\..*)?)$",
    re.I,
)
SENSITIVE_DIRS = {".git"}
SENSITIVE_PROJECT_PATHS = ("local_storage/logs.txt", "local_storage/agent0.db")


def _is_sensitive(path):
    """True for a path (absolute or project-relative) that holds secrets or credentials."""
    rel = os.path.relpath(path, BASE_DIR) if os.path.isabs(path) else path
    rel = rel.replace(os.sep, "/")
    parts = rel.split("/")
    return (
        bool(SENSITIVE_NAME_RE.match(parts[-1]))
        or any(part in SENSITIVE_DIRS for part in parts[:-1])
        or rel.startswith(SENSITIVE_PROJECT_PATHS)
    )


def _safe_path(path):
    """Resolve path inside the project. Returns (full_path, error)."""
    if not path:
        return None, "No path provided"

    full_path = os.path.abspath(os.path.join(BASE_DIR, str(path)))

    # Prevent escaping the project folder (also blocks sibling dirs like <base>-evil)
    if full_path != BASE_DIR and not full_path.startswith(BASE_DIR + os.sep):
        return None, "Access denied"

    # Checked on the resolved target too, so a link with an innocent name can't reach a secret
    real_path = os.path.realpath(full_path)
    if _is_sensitive(full_path) or (real_path.startswith(BASE_DIR + os.sep) and _is_sensitive(real_path)):
        return None, f"Access denied: {path} holds secrets or credentials, so the agent cannot read or change it."

    return full_path, None


def _walk_project():
    for root, dirs, files in os.walk(BASE_DIR):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        yield root, [f for f in files if not _is_sensitive(os.path.join(root, f))]


def _first_arg(*values):
    for value in values:
        if value:
            return value
    return None


def get_project_structure():
    structure = {}

    for root, files in _walk_project():
        rel_root = os.path.relpath(root, BASE_DIR)
        structure[rel_root] = files

    return structure

def _search_terms(*values):
    """Flatten LLM-supplied search arguments into individual lowercase terms.

    A list must not be joined into one phrase - "calendar template" as a single
    string matches nothing, so each word is treated as its own term.
    """
    terms = []

    for value in values:
        if not value:
            continue
        if isinstance(value, (list, tuple)):
            parts = [str(v) for v in value if v]
        else:
            parts = [str(value)]

        for part in parts:
            for word in part.replace(",", " ").split():
                word = word.strip().lower()
                if word and word not in terms:
                    terms.append(word)

    return terms


def search_files(keyword=None, query=None, keywords=None, **kwargs):
    # Accept multiple possible parameter names from LLM-decided arguments
    terms = _search_terms(
        keywords, keyword, query,
        kwargs.get("term"), kwargs.get("text"), kwargs.get("pattern"),
        kwargs.get("name"), kwargs.get("filename"), kwargs.get("file"),
    )

    if not terms:
        return "No search term provided"

    scored = []

    for root, files in _walk_project():
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, BASE_DIR)

            haystack = rel_path.lower()
            matches = []
            try:
                if os.path.getsize(full_path) <= MAX_READ_CHARS:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    haystack += "\n" + content.lower()
                    for number, line in enumerate(content.splitlines(), start=1):
                        if any(term in line.lower() for term in terms):
                            matches.append(f"{number}: {line.strip()[:MAX_MATCH_CHARS]}")
                            if len(matches) == MAX_MATCHES_PER_FILE:
                                break
            except (OSError, UnicodeDecodeError):
                pass

            hits = sum(1 for term in terms if term in haystack)
            if hits:
                scored.append((hits, rel_path, matches))

    if not scored:
        # A bare [] reads like a transient failure and the model just retries
        return f"No files matched {terms}. Try a single simpler term, or use get_project_structure."

    scored.sort(key=lambda item: (-item[0], item[1]))

    # Line numbers let the model read just the section it needs (read_files
    # start_line/end_line) instead of the whole file.
    return [
        {"path": rel_path, "matches": matches} if matches else {"path": rel_path}
        for _, rel_path, matches in scored[:MAX_SEARCH_RESULTS]
    ]

def _line_number(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# A file longer than this is not returned whole unless a line range is given:
# the model gets an outline and asks for the section it needs. Sending whole
# large files was where the time went (prompt processing grows with tokens).
WHOLE_FILE_LINE_LIMIT = env_int("READ_WHOLE_FILE_MAX_LINES", 400)
OUTLINE_FALLBACK_LINES = 60
MAX_OUTLINE_LINES = 150
# Also the module-level constants (MAX_STEPS = 8): that's where settings live,
# and they were missing from the outline, so the model guessed at line ranges.
_OUTLINE_RE = re.compile(
    r"^\s*(?:(?:async\s+)?def |class |function |export |const \w+ = (?:async )?\(|#{1,6}\s)"
    r"|^(?:(?:const|let|var) )?[A-Z_][A-Z0-9_]*\s*[:=]"
)


def _outline(path, lines):
    """Where things are in a long file: def/class/function/heading lines with their numbers (or the head, if there are none)."""
    entries = [f"{n}: {line.strip()[:MAX_MATCH_CHARS]}" for n, line in enumerate(lines, start=1) if _OUTLINE_RE.match(line)]
    if len(entries) < 3:
        entries = [f"{n}: {line.rstrip()[:MAX_MATCH_CHARS]}" for n, line in enumerate(lines[:OUTLINE_FALLBACK_LINES], start=1)]
    omitted = len(entries) - MAX_OUTLINE_LINES
    if omitted > 0:
        entries = entries[:MAX_OUTLINE_LINES] + [f"... {omitted} more"]
    return (
        f"[{path} has {len(lines)} lines, too many to return at once. Outline below - call read_files "
        f"again with start_line and end_line for the section you need; to read it all, pass "
        f"start_line=1 and end_line={len(lines)}.]\n" + "\n".join(entries)
    )


def read_files(path=None, paths=None, file=None, files=None, filename=None, start_line=None, end_line=None, **kwargs):
    # LLM-decided arguments arrive under various names
    path = _first_arg(path, paths, file, files, filename, kwargs.get("file_path"), kwargs.get("file_paths"))

    # A list of paths sometimes comes back instead of a single one
    if isinstance(path, (list, tuple)):
        return {p: read_files(p, start_line=start_line, end_line=end_line) for p in path}

    full_path, error = _safe_path(path)
    if error:
        return error

    if not os.path.exists(full_path):
        return "File not found"

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return str(e)

    if start_line is not None or end_line is not None:
        # 1-based, inclusive. No line numbers are added to the text itself, so
        # it can still be copied exactly into edit_file's old_text.
        lines = content.splitlines(keepends=True)
        total = len(lines)
        first = max(1, _line_number(start_line, 1))
        last = min(total, _line_number(end_line, total))
        if first > last:
            return f"No lines {first}-{last}: {path} has {total} lines"
        content = f"[lines {first}-{last} of {total}]\n" + "".join(lines[first - 1:last])

    if start_line is None and end_line is None and content.count("\n") >= WHOLE_FILE_LINE_LIMIT:
        return _outline(path, content.splitlines())

    if len(content) > MAX_READ_CHARS:
        # Be explicit - otherwise the model may rewrite the file from a partial copy
        return (
            content[:MAX_READ_CHARS]
            + f"\n\n[TRUNCATED after {MAX_READ_CHARS} characters - do NOT write this back as the full file. "
            "Pass start_line and end_line to read the rest.]"
        )

    return content

INLINE_SCRIPT_RE = re.compile(r"[ \t]*<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>[ \t]*\n?", re.S | re.I)


def _dedent_block(text):
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return text.strip()

    indent = min(len(line) - len(line.lstrip()) for line in lines)

    return "\n".join(line[indent:] if line.strip() else "" for line in text.splitlines()).strip() + "\n"


def extract_inline_scripts(path=None, dest=None, destination=None, overwrite=False, **kwargs):
    """Move inline <script> code out of an HTML file into a .js file and link it.

    Removing the tags alone would delete the code, so the body is written to
    dest first and the block is replaced with a <script src=...> tag.
    dest defaults to static/<name>.js.
    """
    path = _first_arg(path, kwargs.get("file"), kwargs.get("filename"), kwargs.get("file_path"))
    dest = _first_arg(dest, destination, kwargs.get("target"), kwargs.get("new_file"))

    full_path, error = _safe_path(path)
    if error:
        return error

    if not os.path.exists(full_path):
        return "File not found"

    with open(full_path, "r", encoding="utf-8") as f:
        old_content = f.read()

    blocks = INLINE_SCRIPT_RE.findall(old_content)

    if not blocks:
        return f"No inline <script> blocks found in {path} - nothing to move"

    for block in blocks:
        if "{{" in block or "{%" in block:
            return (
                "This script uses Jinja template syntax, so it cannot be moved to a static "
                ".js file without breaking it. Leave it inline, or pass the values in via "
                "data attributes first."
            )

    # Guess a destination that matches how the project already loads scripts
    if not dest:
        stem = os.path.splitext(os.path.basename(full_path))[0]
        dest = f"static/{stem}.js"

    dest_full, error = _safe_path(dest)
    if error:
        return error

    if os.path.exists(dest_full) and os.path.getsize(dest_full) > 0 and not overwrite:
        return (
            f"{dest} already exists. Pass a different dest, or overwrite=true to replace it."
        )

    script_body = "\n\n".join(_dedent_block(block) for block in blocks)

    rel_dest = os.path.relpath(dest_full, BASE_DIR).replace(os.sep, "/")
    tag = f'    <script src="/{rel_dest}"></script>\n'

    # First block becomes the link tag, any others are just removed
    replaced = {"done": False}

    def _replace(match):
        if replaced["done"]:
            return ""
        replaced["done"] = True
        return tag

    content = INLINE_SCRIPT_RE.sub(_replace, old_content)

    try:
        dest_old = open(dest_full, "r", encoding="utf-8").read()
    except (FileNotFoundError, UnicodeDecodeError):
        dest_old = ""

    _backup_and_write(dest_full, dest_old, script_body)
    backup = _backup_and_write(full_path, old_content, content)

    return (
        f"Moved {len(blocks)} inline script block(s) ({len(script_body)} chars) from {path} "
        f"to {rel_dest}, and linked it with <script src=\"/{rel_dest}\"></script>. "
        f"Previous {path} saved as {backup}. Run verify_app to confirm nothing broke."
    )


def _script_edit_guard(old_content, content, new_text):
    """Block edits that would orphan or silently delete inline script code.

    Stripping just the <script> tag leaves the JavaScript sitting loose in the
    HTML, and deleting a whole block throws the code away. Both need
    extract_inline_scripts instead.
    """
    opens = len(re.findall(r"<script\b", content, re.I))
    closes = len(re.findall(r"</script\s*>", content, re.I))

    if opens != closes:
        return (
            "Refused: that edit leaves unbalanced <script> tags, so the JavaScript would "
            "be orphaned in the HTML. Use extract_inline_scripts to move the code into a "
            ".js file and link it."
        )

    removed_blocks = INLINE_SCRIPT_RE.findall(old_content)
    kept_blocks = INLINE_SCRIPT_RE.findall(content)

    if len(kept_blocks) < len(removed_blocks) and "src=" not in new_text.lower():
        lost = sum(len(b.strip()) for b in removed_blocks) - sum(len(b.strip()) for b in kept_blocks)
        if lost > 40:
            return (
                f"Refused: that edit would delete {lost} characters of inline script without "
                "putting the code anywhere. Use extract_inline_scripts to move it into a .js "
                "file and link it."
            )

    return None


def parse_script_refactor_command(text):
    """Detect "no inline scripts in <file>.html" style requests.

    The small local model reliably reaches for edit_file and strips the tags,
    so this intent is recognised up front and routed to the right tool.
    """
    if not text:
        return None

    lowered = text.lower()

    if "script" not in lowered:
        return None

    intent = any(
        phrase in lowered
        for phrase in (
            "no script", "not defined", "only loaded", "only load", "external",
            "move", "extract", "separate", "out of", "own file", "no inline",
        )
    )
    if not intent:
        return None

    match = re.search(r"\b([\w./-]+\.html)\b", text, re.I)
    if not match:
        return None

    return {"path": _resolve_project_file(match.group(1))}


def _resolve_project_file(name):
    """Find a file by path or bare name, e.g. 'index.html' -> templates/index.html."""
    candidate, error = _safe_path(name)
    if not error and candidate and os.path.exists(candidate):
        return os.path.relpath(candidate, BASE_DIR).replace(os.sep, "/")

    basename = os.path.basename(name)
    for root, files in _walk_project():
        if basename in files:
            full = os.path.join(root, basename)
            return os.path.relpath(full, BASE_DIR).replace(os.sep, "/")

    return name


def _lenient_pattern(old_text):
    """Match old_text.strip() ignoring quote style and exact whitespace runs.

    Whitespace never crosses line boundaries it didn't cross in old_text, so a
    retyped indent or trailing newline can't merge lines. If old_text started
    with whitespace (an indent), the match is anchored to a line start; group
    "body" is the stripped snippet, excluding that indent.
    """
    parts = []

    for chunk in re.split(r"(\s+|['\"])", old_text.strip()):
        if not chunk:
            continue
        if chunk.isspace():
            parts.append(r"[ \t]*(?:\r?\n[ \t]*)+" if "\n" in chunk else r"[ \t]+")
        elif chunk in ("'", '"'):
            parts.append(r"['\"]")
        else:
            parts.append(re.escape(chunk))

    body = "(?P<body>" + "".join(parts) + ")"
    if old_text[:1].isspace():
        return r"(?m)^[ \t]*" + body
    return body


BACKUP_DIR = os.path.join("local_storage", "backups")


def _backup_path(full_path):
    """Where the previous version of full_path is kept: local_storage/backups/<timestamp>/<path in project>."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return os.path.join(BASE_DIR, BACKUP_DIR, stamp, os.path.relpath(full_path, BASE_DIR))


def _backup_and_write(full_path, old_content, content):
    """Write content, first saving old_content as a timestamped backup. Returns the backup's project-relative path (None for a new file)."""
    backup = None
    if old_content:
        backup_full = _backup_path(full_path)
        os.makedirs(os.path.dirname(backup_full), exist_ok=True)
        with open(backup_full, "w", encoding="utf-8") as f:
            f.write(old_content)
        backup = os.path.relpath(backup_full, BASE_DIR)

    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

    return backup


def write_file(path=None, content=None, paths=None, file=None, filename=None, text=None, **kwargs):
    path = _first_arg(path, paths, file, filename, kwargs.get("files"), kwargs.get("file_path"))
    content = _first_arg(content, text, kwargs.get("contents"), kwargs.get("data"))

    full_path, error = _safe_path(path)
    if error:
        return error

    if content is None:
        return "No content provided"

    # read old content
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            old_content = f.read()
    except FileNotFoundError:
        old_content = ""

    diff = generate_diff(old_content, content)

    print("\n--- FILE CHANGE PREVIEW ---")
    print(diff[:2000])  # limit output

    backup = _backup_and_write(full_path, old_content, content)

    if old_content:
        return f"File updated: {path} (previous version saved as {backup})"

    return f"File created: {path}"


def edit_file(path=None, old_text=None, new_text=None, old_string=None, new_string=None, old=None, new=None, **kwargs):
    """Replace an exact snippet in a file.

    Lets the model move/change a block without re-emitting the whole file,
    which it cannot do reliably for large files.
    """
    path = _first_arg(path, kwargs.get("file"), kwargs.get("files"), kwargs.get("filename"), kwargs.get("file_path"))
    old_text = _first_arg(old_text, old_string, old)
    new_text = new_text if new_text is not None else _first_arg(new_string, new)

    full_path, error = _safe_path(path)
    if error:
        return error

    if not old_text:
        return "No old_text provided"

    if new_text is None:
        new_text = ""

    if not os.path.exists(full_path):
        return "File not found"

    with open(full_path, "r", encoding="utf-8") as f:
        old_content = f.read()

    occurrences = old_content.count(old_text)

    if occurrences > 1:
        return f"old_text appears {occurrences} times - include more surrounding context to make it unique"

    if occurrences == 1:
        content = old_content.replace(old_text, new_text)
    else:
        # The model usually gets the snippet semantically right but retypes
        # quotes or indentation differently, so retry ignoring those - still
        # only accepted when the match is unambiguous.
        matches = list(re.finditer(_lenient_pattern(old_text), old_content))

        if not matches:
            return "old_text not found in file - read the file again and copy the exact text"

        if len(matches) > 1:
            return (
                f"old_text matches {len(matches)} places once quotes/spacing are ignored"
                " - include more surrounding context to make it unique"
            )

        # Only the stripped snippet was matched, so keep the file's own
        # indent/newlines around it and drop new_text's retyped ones.
        start, end = matches[0].span("body")
        replacement = new_text.strip()
        if not replacement:
            # Deleting: take the whole line(s) if nothing else is on them.
            line_start = old_content.rfind("\n", 0, start) + 1
            line_end = old_content.find("\n", end)
            line_end = len(old_content) if line_end == -1 else line_end + 1
            if not old_content[line_start:start].strip() and not old_content[end:line_end].strip():
                start, end = line_start, line_end
        content = old_content[:start] + replacement + old_content[end:]

    guard = _script_edit_guard(old_content, content, new_text)
    if guard:
        return guard

    print("\n--- FILE CHANGE PREVIEW ---")
    print(generate_diff(old_content, content)[:2000])

    backup = _backup_and_write(full_path, old_content, content)

    return f"File edited: {path} (previous version saved as {backup})"
