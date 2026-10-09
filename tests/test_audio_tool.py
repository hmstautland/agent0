import features.audio.player as audio_mod


def _make_files(tmp_path, names):
    for name in names:
        (tmp_path / name).write_bytes(b"x")
    return tmp_path


# --- parse_play_command -----------------------------------------------------

def test_parse_play_command_extracts_filename():
    assert audio_mod.parse_play_command("play my-holiday-music.mp3") == {"query": "my-holiday-music.mp3"}


def test_parse_play_command_strips_filler_words():
    assert audio_mod.parse_play_command("play me the file my-music.mp3") == {"query": "my-music.mp3"}


def test_parse_play_command_handles_bare_number():
    assert audio_mod.parse_play_command("play number 2") == {"query": "2"}
    assert audio_mod.parse_play_command("play 2") == {"query": "2"}


def test_parse_play_command_handles_bare_play():
    assert audio_mod.parse_play_command("play") == {"query": None}


def test_parse_play_command_ignores_unrelated_sentences():
    assert audio_mod.parse_play_command("I want to play with the code") is None
    assert audio_mod.parse_play_command("please play my-music.mp3") is None


def test_parse_play_command_ignores_empty_input():
    assert audio_mod.parse_play_command("") is None
    assert audio_mod.parse_play_command(None) is None


# --- find_audio_files --------------------------------------------------------

def test_find_audio_files_lists_everything_when_no_query(monkeypatch, tmp_path):
    _make_files(tmp_path, ["a.wav", "b.mp3"])
    monkeypatch.setattr(audio_mod, "AUDIO_DIR", tmp_path)

    files = audio_mod.find_audio_files()

    assert {f.name for f in files} == {"a.wav", "b.mp3"}


def test_find_audio_files_ignores_non_audio_extensions(monkeypatch, tmp_path):
    _make_files(tmp_path, ["a.wav", "notes.txt", "b.mp3.bak"])
    monkeypatch.setattr(audio_mod, "AUDIO_DIR", tmp_path)

    files = audio_mod.find_audio_files()

    assert {f.name for f in files} == {"a.wav"}


def test_find_audio_files_matches_substring_case_insensitively(monkeypatch, tmp_path):
    _make_files(tmp_path, ["my-holiday-music.mp3", "my-work-music.wav", "unrelated.wav"])
    monkeypatch.setattr(audio_mod, "AUDIO_DIR", tmp_path)

    files = audio_mod.find_audio_files("HOLIDAY")

    assert [f.name for f in files] == ["my-holiday-music.mp3"]


def test_find_audio_files_matches_query_without_extension(monkeypatch, tmp_path):
    _make_files(tmp_path, ["my-holiday-music.mp3", "unrelated.wav"])
    monkeypatch.setattr(audio_mod, "AUDIO_DIR", tmp_path)

    files = audio_mod.find_audio_files("my-holiday-music")

    assert [f.name for f in files] == ["my-holiday-music.mp3"]


def test_find_audio_files_returns_empty_when_directory_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(audio_mod, "AUDIO_DIR", tmp_path / "does-not-exist")

    assert audio_mod.find_audio_files() == []


# --- play_audio_file ---------------------------------------------------------

def test_play_audio_file_plays_single_match(monkeypatch, tmp_path):
    _make_files(tmp_path, ["my-holiday-music.mp3", "unrelated.wav"])
    monkeypatch.setattr(audio_mod, "AUDIO_DIR", tmp_path)
    monkeypatch.setattr(audio_mod, "_last_candidates", [])

    result = audio_mod.play_audio_file(query="holiday")

    assert result == {
        "status": "play",
        "filename": "my-holiday-music.mp3",
        "audio_url": "/audio/my-holiday-music.mp3",
    }


def test_play_audio_file_offers_choices_for_multiple_matches(monkeypatch, tmp_path):
    _make_files(tmp_path, ["my-holiday-music.mp3", "my-work-music.wav"])
    monkeypatch.setattr(audio_mod, "AUDIO_DIR", tmp_path)
    monkeypatch.setattr(audio_mod, "_last_candidates", [])

    result = audio_mod.play_audio_file(query="music")

    assert result["status"] == "choose"
    assert {c["filename"] for c in result["candidates"]} == {"my-holiday-music.mp3", "my-work-music.wav"}
    assert {c["number"] for c in result["candidates"]} == {1, 2}


def test_play_audio_file_reports_no_match(monkeypatch, tmp_path):
    _make_files(tmp_path, ["a.wav"])
    monkeypatch.setattr(audio_mod, "AUDIO_DIR", tmp_path)
    monkeypatch.setattr(audio_mod, "_last_candidates", [])

    result = audio_mod.play_audio_file(query="nonexistent")

    assert result["status"] == "error"
    assert "nonexistent" in result["message"]


def test_play_audio_file_reports_no_saved_files_when_directory_is_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(audio_mod, "AUDIO_DIR", tmp_path)
    monkeypatch.setattr(audio_mod, "_last_candidates", [])

    result = audio_mod.play_audio_file(query=None)

    assert result == {"status": "error", "message": "There are no saved audio files yet."}


def test_play_audio_file_number_resolves_against_last_candidates(monkeypatch, tmp_path):
    _make_files(tmp_path, ["my-holiday-music.mp3", "my-work-music.wav"])
    monkeypatch.setattr(audio_mod, "AUDIO_DIR", tmp_path)
    monkeypatch.setattr(audio_mod, "_last_candidates", [])

    choose_result = audio_mod.play_audio_file(query="music")
    wanted = next(c for c in choose_result["candidates"] if c["filename"] == "my-work-music.wav")

    play_result = audio_mod.play_audio_file(query=str(wanted["number"]))

    assert play_result == {
        "status": "play",
        "filename": "my-work-music.wav",
        "audio_url": "/audio/my-work-music.wav",
    }


def test_play_audio_file_number_without_a_prior_list_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(audio_mod, "AUDIO_DIR", tmp_path)
    monkeypatch.setattr(audio_mod, "_last_candidates", [])

    result = audio_mod.play_audio_file(number=2)

    assert result["status"] == "error"
    assert "search by name first" in result["message"]


def test_play_audio_file_number_out_of_range_is_an_error(monkeypatch, tmp_path):
    _make_files(tmp_path, ["a.wav", "b.wav"])
    monkeypatch.setattr(audio_mod, "AUDIO_DIR", tmp_path)
    monkeypatch.setattr(audio_mod, "_last_candidates", [])

    audio_mod.play_audio_file(query=None)  # lists both, populating _last_candidates
    result = audio_mod.play_audio_file(number=99)

    assert result["status"] == "error"
    assert "only 2" in result["message"]


def test_play_audio_file_number_consumes_the_candidate_list(monkeypatch, tmp_path):
    _make_files(tmp_path, ["a.wav", "b.wav"])
    monkeypatch.setattr(audio_mod, "AUDIO_DIR", tmp_path)
    monkeypatch.setattr(audio_mod, "_last_candidates", [])

    audio_mod.play_audio_file(query=None)
    audio_mod.play_audio_file(number=1)

    # a second "play number" with no fresh search in between has nothing to resolve against
    result = audio_mod.play_audio_file(number=1)
    assert result["status"] == "error"


# --- describe_play_result ----------------------------------------------------

def test_describe_play_result_for_each_status():
    assert audio_mod.describe_play_result({"status": "play", "filename": "a.wav"}) == "Playing a.wav."
    assert "2 matching files" in audio_mod.describe_play_result(
        {"status": "choose", "candidates": [{}, {}]}
    )
    assert audio_mod.describe_play_result({"status": "error", "message": "nope"}) == "nope"
