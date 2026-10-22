"""Build docs/html/: the README and everything under docs/ as plain HTML pages.

The markdown stays the source; this folder is generated (and gitignored), so
rebuild after editing a doc. Open docs/html/index.html in a browser, or zip
the folder to share it - it needs no server. Pages with mermaid diagrams load
mermaid from a CDN; offline they show the diagram source instead.

    python docs/build_html.py
"""
import html
import os
import re
import shutil
import sys
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = DOCS / "html"

MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"

NAV = [
    ("Home", "README.md"),
    ("Features", "docs/features/README.md"),
    ("Build your own agent", "docs/BUILD_YOUR_OWN_AGENT.md"),
    ("Decisions", "docs/DECISIONS.md"),
]

STYLE = """\
:root { --bg: #fdfdfc; --fg: #1f2328; --muted: #59636e; --line: #d1d9e0; --code: #f3f4f6; --link: #0b62d6; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #16181c; --fg: #e6e8eb; --muted: #9aa4af; --line: #343a42; --code: #22262c; --link: #6aa8ff; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.6 system-ui, -apple-system, "Segoe UI", sans-serif; }
header { border-bottom: 1px solid var(--line); padding: 12px 16px; }
header nav { max-width: 860px; margin: 0 auto; display: flex; flex-wrap: wrap; gap: 6px 20px; }
header a { color: var(--fg); font-weight: 600; text-decoration: none; }
header a:hover, header a.current { color: var(--link); }
main { max-width: 860px; margin: 0 auto; padding: 8px 16px 64px; }
a { color: var(--link); }
h1, h2, h3 { line-height: 1.25; margin: 1.6em 0 0.5em; }
h1 { font-size: 2em; } h2 { font-size: 1.45em; border-bottom: 1px solid var(--line); padding-bottom: 0.2em; }
code { background: var(--code); border-radius: 4px; padding: 0.1em 0.35em; font-size: 0.9em;
  font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace; }
pre { background: var(--code); border-radius: 6px; padding: 12px 14px; overflow-x: auto; }
pre code { background: none; padding: 0; }
pre.mermaid { background: none; text-align: center; }
table { border-collapse: collapse; display: block; overflow-x: auto; margin: 1em 0; }
th, td { border: 1px solid var(--line); padding: 6px 12px; text-align: left; vertical-align: top; }
th { background: var(--code); }
blockquote { margin: 1em 0; padding: 0 1em; color: var(--muted); border-left: 4px solid var(--line); }
footer { max-width: 860px; margin: 0 auto; padding: 16px; color: var(--muted); font-size: 0.85em;
  border-top: 1px solid var(--line); }
"""


def source_files():
    """Every doc to publish, as repo-relative paths."""
    return ["README.md"] + [path.relative_to(ROOT).as_posix() for path in sorted(DOCS.rglob("*.md"))]


def output_path(source):
    """Where a doc lands inside docs/html/: README.md files become index.html."""
    rel = Path(source)
    if rel.parts[0] == "docs":
        rel = rel.relative_to("docs")
    if rel.name == "README.md":
        return (rel.parent / "index.html").as_posix()
    return rel.with_suffix(".html").as_posix()


def slugify(text, used):
    """GitHub-style heading id, so links like guide.md#add-a-logger keep working."""
    slug = re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")
    base, n = slug, 1
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug


def title_of(text, fallback):
    match = re.search(r"^# (.+)$", text, re.M)
    return match.group(1).strip() if match else fallback


def rel_href(from_out, to_out):
    return os.path.relpath(to_out, os.path.dirname(from_out) or ".").replace(os.sep, "/")


def rewrite_links(tokens, source, pages, dir_indexes, dropped):
    """Point .md links at the generated pages; unpublished repo files become plain text."""
    out = output_path(source)
    for token in tokens:
        if token.type != "inline" or not token.children:
            continue
        stack = []
        for child in token.children:
            if child.type == "link_open":
                href = child.attrGet("href") or ""
                if re.match(r"^(\w+:|#)", href):
                    stack.append(False)
                    continue
                path, _, frag = href.partition("#")
                target = os.path.normpath(os.path.join(os.path.dirname(source), path)).replace(os.sep, "/")
                if target in pages:
                    new = rel_href(out, output_path(target))
                elif target in dir_indexes:
                    new = rel_href(out, dir_indexes[target])
                else:
                    dropped.append(f"{source}: {href}")
                    child.type = "text"
                    child.content = ""
                    stack.append(True)
                    continue
                child.attrSet("href", new + (f"#{frag}" if frag else ""))
                stack.append(False)
            elif child.type == "link_close" and stack and stack.pop():
                child.type = "text"
                child.content = ""


def render(md, text, source, pages, dir_indexes, dropped):
    tokens = md.parse(text)
    used = set()
    for i, token in enumerate(tokens):
        if token.type == "heading_open":
            token.attrSet("id", slugify(tokens[i + 1].content, used))
    rewrite_links(tokens, source, pages, dir_indexes, dropped)
    body = md.renderer.render(tokens, md.options, {})
    body = re.sub(
        r'<pre><code class="language-mermaid">(.*?)</code></pre>',
        lambda m: f'<pre class="mermaid">{m.group(1)}</pre>',
        body,
        flags=re.S,
    )
    return body


def page(title, body, out, has_mermaid):
    nav = "".join(
        f'<a href="{rel_href(out, output_path(src))}"'
        f'{" class=current" if output_path(src) == out else ""}>{label}</a>'
        for label, src in NAV
    )
    mermaid = (
        f'<script src="{MERMAID_JS}"></script>\n<script>mermaid.initialize({{startOnLoad: true, '
        "theme: matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'default'}});</script>\n"
        if has_mermaid else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} - agent0</title>
<link rel="stylesheet" href="{rel_href(out, "style.css")}">
</head>
<body>
<header><nav>{nav}</nav></header>
<main>
{body}
</main>
<footer>Generated from the markdown docs in the agent0 repository.</footer>
{mermaid}</body>
</html>
"""


def directory_index(directory, members, titles):
    """An index page for a docs folder without a README, listing its pages."""
    items = "\n".join(f"- [{titles[src]}]({Path(src).name})" for src in members)
    return f"# {Path(directory).name.capitalize()}\n\n{items}\n"


def build(out_dir=OUT):
    out_dir = Path(out_dir)
    md = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])
    pages = {src: (ROOT / src).read_text(encoding="utf-8") for src in source_files()}
    titles = {src: title_of(text, Path(src).stem) for src, text in pages.items()}

    # Folders linked as "guide/" need a page to land on
    folders = {}
    for src in pages:
        folders.setdefault(os.path.dirname(src), []).append(src)
    dir_indexes = {}
    for folder, members in folders.items():
        readme = f"{folder}/README.md" if folder else "README.md"
        if readme in pages:
            dir_indexes[folder] = output_path(readme)
        elif folder == "docs":
            # docs/ itself lands at the root, where the top-level README already is
            dir_indexes[folder] = output_path("README.md")
        else:
            index_src = f"{folder}/README.md"
            pages[index_src] = directory_index(folder, sorted(members), titles)
            titles[index_src] = Path(folder).name.capitalize()
            dir_indexes[folder] = output_path(index_src)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    (out_dir / "style.css").write_text(STYLE, encoding="utf-8")

    dropped = []
    for src, text in pages.items():
        out = output_path(src)
        body = render(md, text, src, pages, dir_indexes, dropped)
        target = out_dir / out
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page(titles[src], body, out, 'class="mermaid"' in body), encoding="utf-8")
    return sorted(pages), dropped


if __name__ == "__main__":
    built, dropped = build()
    print(f"Built {len(built)} pages into {OUT.relative_to(ROOT)}/ - open {OUT.relative_to(ROOT)}/index.html")
    for link in dropped:
        print(f"  not published, shown as plain text: {link}", file=sys.stderr)
