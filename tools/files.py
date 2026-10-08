import os
import re
from core.diff import generate_diff

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Directories that would flood the LLM context with irrelevant files
SKIP_DIRS = {"venv", ".venv", "env", ".git", "__pycache__", "node_modules", "dist", "build", ".pytest_cache"}

MAX_READ_CHARS = 100000
MAX_SEARCH_RESULTS = 20


def _safe_path(path):
    """Resolve path inside the project. Returns (full_path, error)."""
    if not path:
        return None, "No path provided"

    full_path = os.path.abspath(os.path.join(BASE_DIR, str(path)))

    # Prevent escaping the project folder (also blocks sibling dirs like <base>-evil)
    if full_path != BASE_DIR and not full_path.startswith(BASE_DIR + os.sep):
        return None, "Access denied"

    return full_path, None


def _walk_project():
    for root, dirs, files in os.walk(BASE_DIR):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        yield root, files


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
            try:
                if os.path.getsize(full_path) <= MAX_READ_CHARS:
                    with open(full_path, "r", encoding="utf-8") as f:
                        haystack += "\n" + f.read().lower()
            except (OSError, UnicodeDecodeError):
                pass

            hits = sum(1 for term in terms if term in haystack)
            if hits:
                scored.append((hits, rel_path))

    if not scored:
        # A bare [] reads like a transient failure and the model just retries
        return f"No files matched {terms}. Try a single simpler term, or use get_project_structure."

    scored.sort(key=lambda item: (-item[0], item[1]))

    return [rel_path for _, rel_path in scored[:MAX_SEARCH_RESULTS]]

def read_files(path=None, paths=None, file=None, files=None, filename=None, **kwargs):
    # LLM-decided arguments arrive under various names
    path = _first_arg(path, paths, file, files, filename, kwargs.get("file_path"), kwargs.get("file_paths"))

    # A list of paths sometimes comes back instead of a single one
    if isinstance(path, (list, tuple)):
        return {p: read_files(p) for p in path}

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

    if len(content) > MAX_READ_CHARS:
        # Be explicit - otherwise the model may rewrite the file from a partial copy
        return (
            content[:MAX_READ_CHARS]
            + f"\n\n[TRUNCATED after {MAX_READ_CHARS} characters - do NOT write this back as the full file]"
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
    _backup_and_write(full_path, old_content, content)

    return (
        f"Moved {len(blocks)} inline script block(s) ({len(script_body)} chars) from {path} "
        f"to {rel_dest}, and linked it with <script src=\"/{rel_dest}\"></script>. "
        f"Previous {path} saved as {path}.bak. Run verify_app to confirm nothing broke."
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
    """Match old_text ignoring quote style and exact whitespace runs."""
    parts = []

    for chunk in re.split(r"(\s+|['\"])", old_text):
        if not chunk:
            continue
        if chunk.isspace():
            parts.append(r"\s+")
        elif chunk in ("'", '"'):
            parts.append(r"['\"]")
        else:
            parts.append(re.escape(chunk))

    return "".join(parts)


def _backup_and_write(full_path, old_content, content):
    if old_content:
        with open(full_path + ".bak", "w", encoding="utf-8") as f:
            f.write(old_content)

    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)


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

    _backup_and_write(full_path, old_content, content)

    if old_content:
        return f"File updated: {path} (previous version saved as {path}.bak)"

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

        match = matches[0]
        content = old_content[: match.start()] + new_text + old_content[match.end():]

    guard = _script_edit_guard(old_content, content, new_text)
    if guard:
        return guard

    print("\n--- FILE CHANGE PREVIEW ---")
    print(generate_diff(old_content, content)[:2000])

    _backup_and_write(full_path, old_content, content)

    return f"File edited: {path} (previous version saved as {path}.bak)"
