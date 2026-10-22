import importlib.util
import re
from pathlib import Path

spec = importlib.util.spec_from_file_location("build_html", Path("docs/build_html.py"))
build_html = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_html)


def test_every_internal_link_and_anchor_in_the_html_docs_resolves(tmp_path):
    build_html.build(tmp_path)

    pages = {path: path.read_text(encoding="utf-8") for path in tmp_path.rglob("*.html")}
    broken = []
    for path, text in pages.items():
        for href in re.findall(r'href="([^"]+)"', text):
            if re.match(r"^\w+:", href):
                continue
            file, _, anchor = href.partition("#")
            target = (path.parent / file).resolve() if file else path
            if not target.exists():
                broken.append(f"{path.name}: {href}")
            elif anchor and f'id="{anchor}"' not in target.read_text(encoding="utf-8"):
                broken.append(f"{path.name}: {href} (no such heading)")

    assert (tmp_path / "index.html").exists()
    assert (tmp_path / "features" / "index.html").exists()
    assert broken == []


def test_md_links_become_html_and_unpublished_files_become_text(tmp_path):
    _, dropped = build_html.build(tmp_path)
    home = (tmp_path / "index.html").read_text(encoding="utf-8")

    assert 'href="features/agent-loop.html"' in home
    assert ".md\"" not in home
    assert "README.md: CLAUDE.md" in dropped
