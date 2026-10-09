import os
import re

from core.templates import TEMPLATE_DIRS
from jinja2 import Environment, FileSystemLoader, TemplateSyntaxError

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))



# URLs the app serves from disk, mapped to the directory that backs them
# Ordered most specific first - the first matching prefix wins, so a feature's
# own static folder has to precede the broader /static/ mount.
MOUNTS = {
    "/static/calendar/": "features/calendar/static",
    "/static/audio/": "features/audio/static",
    "/static/": "static",
    "/media/": "media",
    "/favicon/": "favicon",
}

ASSET_RE = re.compile(r'(?:src|href)\s*=\s*["\'](/[^"\']+)["\']', re.I)
INCLUDE_RE = re.compile(r'{%\s*include\s*["\']([^"\']+)["\']', re.I)


def _template_files():
    for template_dir in TEMPLATE_DIRS:
        template_root = os.path.join(BASE_DIR, template_dir)

        for root, _, files in os.walk(template_root):
            for file in files:
                if file.endswith(".html"):
                    full = os.path.join(root, file)
                    yield full, os.path.relpath(full, template_root).replace(os.sep, "/")


def verify_app():
    """Check the app still holds together after an edit.

    Compiles every template, resolves {% include %} targets, checks that
    referenced /static, /media and /favicon files exist, and imports the app.
    """
    problems = []
    checked_templates = 0
    checked_assets = 0

    env = Environment(loader=FileSystemLoader([os.path.join(BASE_DIR, d) for d in TEMPLATE_DIRS]))

    for full_path, rel_name in _template_files():
        checked_templates += 1

        try:
            env.get_template(rel_name)
        except TemplateSyntaxError as e:
            problems.append(f"{rel_name}: template syntax error line {e.lineno}: {e.message}")
            continue
        except Exception as e:
            problems.append(f"{rel_name}: {e}")
            continue

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        for include in INCLUDE_RE.findall(content):
            if not any(os.path.exists(os.path.join(BASE_DIR, d, include)) for d in TEMPLATE_DIRS):
                problems.append(f"{rel_name}: includes missing template '{include}'")

        for url in ASSET_RE.findall(content):
            for prefix, directory in MOUNTS.items():
                if url.startswith(prefix):
                    checked_assets += 1
                    asset = os.path.join(BASE_DIR, directory, url[len(prefix):])
                    if not os.path.exists(asset):
                        problems.append(f"{rel_name}: references missing file '{url}'")
                    break

    try:
        import importlib

        import core.ui

        importlib.reload(core.ui)
    except Exception as e:
        problems.append(f"core/ui.py failed to import: {type(e).__name__}: {e}")

    if problems:
        return "FAILED - " + f"{len(problems)} problem(s):\n" + "\n".join(f"- {p}" for p in problems)

    return (
        f"OK - {checked_templates} template(s) compile, {checked_assets} referenced asset(s) exist, "
        "app imports cleanly."
    )
