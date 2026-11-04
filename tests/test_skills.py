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


def test_shipped_decision_log_skill_inserts_below_the_marker_in_docs():
    body = skills.load_skill(name="decision-log")
    log = open("docs/DECISIONS.md", encoding="utf-8").read()
    marker = "<!-- New decisions go directly below this line, newest first. -->"

    assert marker in body
    assert log.count(marker) == 1


def test_a_malformed_or_duplicate_skill_file_is_skipped_not_fatal(monkeypatch, tmp_path):
    monkeypatch.setattr(skills, "SKILL_FOLDER", tmp_path)
    (tmp_path / "a-open.md").write_text("---\nname: broken\ndescription: x\n")  # no closing ---
    (tmp_path / "b-binary.md").write_bytes(b"---\n\xff\xfe\n---\nbody")
    (tmp_path / "c-empty.md").write_text("---\nname: empty\ndescription: x\n---\n")
    _write(tmp_path, "d-good", "ok", "first")
    (tmp_path / "e-dup.md").write_text("---\nname: d-good\ndescription: dup\n---\nsecond\n")

    assert list(skills._skills()) == ["d-good"]
    assert skills.load_skill(name="d-good") == "first"


def test_skills_are_found_from_any_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    assert "weekly-report" in skills._skills()


def test_local_first_prompt_lists_the_skills_so_their_requests_reach_the_tool_loop():
    assert "- weekly-report:" in agent.local_only_prompt()


def test_shipped_document_feature_skill_asks_before_writing_docs():
    body = skills.load_skill(name="document-feature")

    assert "docs/features/README.md" in body
    assert "Do not write any docs" in body
