import pytest

import tools.files as filesmod


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(filesmod, "BASE_DIR", str(tmp_path))
    return tmp_path


SOURCE = 'def f():\n    x = 1\n    call("a")\n    return x\n'
EXPECTED = 'def f():\n    x = 1\n    call(\'b\')\n    return x\n'


@pytest.mark.parametrize("indent", ["    ", "  ", ""])
def test_lenient_edit_keeps_lines_and_indentation(project, indent):
    (project / "m.py").write_text(SOURCE)

    result = filesmod.edit_file(
        path="m.py", old_text=f"{indent}call('a')\n", new_text=f"{indent}call('b')\n"
    )

    assert result.startswith("File edited")
    assert (project / "m.py").read_text() == EXPECTED
    compile(EXPECTED, "m.py", "exec")


def test_lenient_edit_multiline_does_not_cross_extra_lines(project):
    (project / "m.py").write_text(SOURCE)

    result = filesmod.edit_file(
        path="m.py",
        old_text="  x = 1\n  call('a')\n",
        new_text="  x = 2\n    call('a')\n",
    )

    assert result.startswith("File edited")
    assert (project / "m.py").read_text() == 'def f():\n    x = 2\n    call(\'a\')\n    return x\n'


def test_lenient_edit_delete_removes_whole_line(project):
    (project / "m.py").write_text(SOURCE)

    result = filesmod.edit_file(path="m.py", old_text="  call('a')\n", new_text="")

    assert result.startswith("File edited")
    assert (project / "m.py").read_text() == "def f():\n    x = 1\n    return x\n"


def test_lenient_edit_space_does_not_match_newline(project):
    (project / "m.py").write_text(SOURCE)

    result = filesmod.edit_file(path="m.py", old_text="x = 1 call('a')", new_text="y")

    assert result.startswith("old_text not found")
    assert (project / "m.py").read_text() == SOURCE


def _backups(project, name):
    return sorted((project / "local_storage" / "backups").glob(f"*/{name}"))


def test_edit_saves_the_previous_version_under_local_storage_backups_not_next_to_the_file(project):
    (project / "m.py").write_text(SOURCE)

    result = filesmod.edit_file(path="m.py", old_text='call("a")', new_text='call("b")')

    [backup] = _backups(project, "m.py")
    assert backup.read_text() == SOURCE
    assert str(backup.relative_to(project)) in result
    assert not (project / "m.py.bak").exists()


def test_every_write_keeps_its_own_backup_so_history_is_not_one_level_deep(project):
    (project / "n.txt").write_text("v1\n")

    filesmod.write_file(path="n.txt", content="v2\n")
    filesmod.write_file(path="n.txt", content="v3\n")

    assert [b.read_text() for b in _backups(project, "n.txt")] == ["v1\n", "v2\n"]


def test_backups_keep_the_project_relative_path_and_new_files_get_none(project):
    (project / "sub").mkdir()
    (project / "sub" / "a.txt").write_text("old")

    filesmod.write_file(path="sub/a.txt", content="new")
    created = filesmod.write_file(path="sub/fresh.txt", content="x")

    assert [b.read_text() for b in _backups(project, "sub/a.txt")] == ["old"]
    assert _backups(project, "sub/fresh.txt") == [] and "saved as" not in created


def test_read_files_returns_just_the_requested_line_range_with_the_text_unchanged(project):
    (project / "big.py").write_text("".join(f"line {i}\n" for i in range(1, 11)))

    result = filesmod.read_files(path="big.py", start_line=3, end_line=5)

    assert result == "[lines 3-5 of 10]\nline 3\nline 4\nline 5\n"


def test_read_files_line_range_defaults_and_bounds(project):
    (project / "f.txt").write_text("a\nb\nc\n")

    assert filesmod.read_files(path="f.txt", start_line=2).endswith("b\nc\n")
    assert filesmod.read_files(path="f.txt", end_line=99).startswith("[lines 1-3 of 3]")
    assert "has 3 lines" in filesmod.read_files(path="f.txt", start_line=5)
    assert filesmod.read_files(path="f.txt", start_line="oops", end_line=1) == "[lines 1-1 of 3]\na\n"


def test_read_files_applies_the_line_range_to_every_path_in_a_list(project):
    (project / "x.txt").write_text("1\n2\n3\n")
    (project / "y.txt").write_text("4\n5\n6\n")

    result = filesmod.read_files(paths=["x.txt", "y.txt"], start_line=2, end_line=2)

    assert result == {"x.txt": "[lines 2-2 of 3]\n2\n", "y.txt": "[lines 2-2 of 3]\n5\n"}


def test_search_files_returns_matching_line_numbers_so_a_section_can_be_read(project):
    (project / "auth.py").write_text("import os\n\ndef login(user):\n    return user\n\nlogin('x')\n")
    (project / "other.txt").write_text("nothing here\n")

    assert filesmod.search_files(keyword="login") == [
        {"path": "auth.py", "matches": ["3: def login(user):", "6: login('x')"]},
    ]


def test_search_files_caps_matches_per_file_and_still_lists_filename_only_hits(project):
    (project / "many.py").write_text("".join(f"login {i}\n" for i in range(10)))
    (project / "login_notes.txt").write_text("unrelated\n")

    result = {r["path"]: r for r in filesmod.search_files(keyword="login")}

    assert len(result["many.py"]["matches"]) == filesmod.MAX_MATCHES_PER_FILE
    assert result["login_notes.txt"] == {"path": "login_notes.txt"}


def _long_python_file(project, name="long.py", defs=30):
    body = "".join(f"def func_{i}():\n" + "    pass\n" * 14 for i in range(defs))
    (project / name).write_text(body)
    return body


def test_a_long_file_is_returned_as_an_outline_unless_a_range_is_given(project):
    body = _long_python_file(project)
    assert body.count("\n") >= filesmod.WHOLE_FILE_LINE_LIMIT

    outline = filesmod.read_files(path="long.py")

    assert outline.startswith("[long.py has ") and "start_line" in outline
    assert "1: def func_0():" in outline and "16: def func_1():" in outline
    assert "    pass" not in outline and len(outline) < len(body) / 3


def test_an_explicit_range_returns_the_text_even_for_a_long_file(project):
    _long_python_file(project)

    section = filesmod.read_files(path="long.py", start_line=16, end_line=17)
    whole = filesmod.read_files(path="long.py", start_line=1, end_line=450)

    assert section == "[lines 16-17 of 450]\ndef func_1():\n    pass\n"
    assert whole.count("def func_") == 30


def test_a_short_file_is_still_returned_whole(project):
    (project / "short.py").write_text("def f():\n    pass\n")

    assert filesmod.read_files(path="short.py") == "def f():\n    pass\n"


def test_a_long_file_without_definitions_falls_back_to_its_first_lines(project):
    (project / "data.txt").write_text("".join(f"row {i}\n" for i in range(500)))

    outline = filesmod.read_files(path="data.txt")

    assert "1: row 0" in outline and f"{filesmod.OUTLINE_FALLBACK_LINES}: row" in outline and "row 61" not in outline


def test_the_outline_lists_module_level_constants_so_settings_can_be_found(project):
    body = "import os\nMAX_STEPS = int(os.getenv('MAX_STEPS', 8))\nname = 'x'\n" + "".join(f"def f{i}():\n" + "    pass\n" * 14 for i in range(30))
    (project / "cfg.py").write_text(body)

    outline = filesmod.read_files(path="cfg.py")

    assert "2: MAX_STEPS = int(" in outline and "name = 'x'" not in outline


def test_searching_and_listing_skip_local_storage_so_old_backups_are_not_matched(project):
    (project / "real.py").write_text("MAX_STEPS = 8\n")
    (project / "local_storage" / "backups" / "20260101_000000_000000").mkdir(parents=True)
    (project / "local_storage" / "backups" / "20260101_000000_000000" / "real.py").write_text("MAX_STEPS = 1\n")

    assert [r["path"] for r in filesmod.search_files(keyword="MAX_STEPS")] == ["real.py"]
    assert "local_storage" not in str(filesmod.get_project_structure())


@pytest.mark.parametrize("name", [".env", ".env.local", ".env.bak", "server.pem", "private.key", "id_rsa", "credentials.json", ".netrc", "secrets.yaml"])
def test_secret_files_cannot_be_read_written_or_edited(project, name):
    (project / name).write_text("TOKEN=hunter2\n")

    for result in (
        filesmod.read_files(path=name),
        filesmod.write_file(path=name, content="x"),
        filesmod.edit_file(path=name, old_text="TOKEN", new_text="OTHER"),
    ):
        assert result.startswith("Access denied") and "hunter2" not in result

    assert (project / name).read_text() == "TOKEN=hunter2\n"


def test_secret_files_are_not_searched_or_listed(project):
    (project / ".env").write_text("SESSION_SECRET=hunter2\n")
    (project / "app.py").write_text("print('hi')\n")

    assert "hunter2" not in str(filesmod.search_files(keyword="SESSION_SECRET"))
    assert ".env" not in str(filesmod.get_project_structure())
    assert "app.py" in str(filesmod.get_project_structure())


def test_a_link_with_an_innocent_name_cannot_reach_a_secret(project):
    (project / ".env").write_text("TOKEN=hunter2\n")
    (project / "notes.txt").symlink_to(project / ".env")

    assert filesmod.read_files(path="notes.txt").startswith("Access denied")


def test_the_git_folder_and_the_event_log_are_off_limits(project):
    (project / ".git").mkdir()
    (project / ".git" / "config").write_text("url = https://user:pass@host\n")
    (project / "local_storage").mkdir()
    (project / "local_storage" / "logs.txt").write_text("{}\n")

    assert filesmod.read_files(path=".git/config").startswith("Access denied")
    assert filesmod.read_files(path="local_storage/logs.txt").startswith("Access denied")


def test_ordinary_files_with_similar_names_are_still_readable(project):
    for name in ("environment.py", "keys.py", "secret_santa.txt", "notes.env.md"):
        (project / name).write_text("ok\n")
        assert filesmod.read_files(path=name) == "ok\n"
