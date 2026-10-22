"""Skills: markdown instructions for one kind of task, loaded on demand.

Only a one-line index (name + when to use it) goes in the system prompt; the
model fetches the full text with the load_skill tool, so unused skills cost
no context. Each skill is skills/<name>.md starting with a frontmatter block:

    ---
    name: weekly-report
    description: when to use it
    ---
"""
import re
from pathlib import Path

# Next to the code, not the cwd: skills must still be found when the server is started from elsewhere
SKILL_FOLDER = Path(__file__).resolve().parent.parent / "skills"

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n(.*))?\Z", re.S)


def _parse(path):
    """(name, description, body) of one skill file, or None when it is unreadable, has no frontmatter or no body."""
    try:
        match = _FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None
    if not match:
        return None
    fields = dict(line.split(":", 1) for line in match.group(1).splitlines() if ":" in line)
    body = (match.group(2) or "").strip()
    if not body:
        return None
    return fields.get("name", path.stem).strip(), fields.get("description", "").strip(), body


def _skills():
    """name -> (name, description, body). A bad file is skipped, and the first file wins a duplicate name."""
    found = {}
    for path in sorted(SKILL_FOLDER.glob("*.md")):
        parsed = _parse(path)
        if parsed and parsed[0] not in found:
            found[parsed[0]] = parsed
    return found


def skill_lines():
    """One "- name: when to use it" line per skill, or "" when there are none."""
    return "\n".join(f"- {name}: {description}" for name, description, _ in _skills().values())


def skills_index():
    """Lines for the system prompt, or "" when there are no skills."""
    lines = skill_lines()
    if not lines:
        return ""
    return "SKILLS (call load_skill(name) first when a request matches one, then follow it):\n" + lines + "\n"


def load_skill(name: str = "", **_):
    skills = _skills()
    skill = skills.get(str(name).strip())
    if not skill:
        return f"ERROR: no skill named '{name}'. Available: {', '.join(skills) or 'none'}."
    return skill[2]
