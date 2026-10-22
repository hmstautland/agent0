import agent
import tools.skills as skills


def _write(folder, name, description, body):
    (folder / f"{name}.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n")


def test_index_lists_skills_and_load_skill_returns_only_the_body(monkeypatch, tmp_path):
    monkeypatch.setattr(skills, "SKILL_FOLDER", tmp_path)
    _write(tmp_path, "weekly-report", "summarise the week", "Step 1: do it")

    assert "- weekly-report: summarise the week" in skills.skills_index()
    assert skills.load_skill(name="weekly-report") == "Step 1: do it"


def test_unknown_skill_lists_what_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(skills, "SKILL_FOLDER", tmp_path)
    _write(tmp_path, "a", "x", "body")

    assert skills.load_skill(name="nope") == "ERROR: no skill named 'nope'. Available: a."


def test_no_skills_means_no_index_and_files_without_frontmatter_are_ignored(monkeypatch, tmp_path):
    monkeypatch.setattr(skills, "SKILL_FOLDER", tmp_path)
    (tmp_path / "notes.md").write_text("just text")

    assert skills.skills_index() == ""


def test_shipped_weekly_report_skill_is_valid_and_in_the_system_prompt():
    assert "weekly-report" in skills._skills()
    assert "SKILLS" in agent.system_message()["content"]
    assert "search_history" in skills.load_skill(name="weekly-report")


def test_shipped_move_code_skill_keeps_the_destination_first_rule():
    body = skills.load_skill(name="move-code-out-of-file")

    assert "Write the destination file FIRST" in body
    assert "extract_inline_scripts" in body
