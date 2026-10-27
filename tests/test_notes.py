import os

import tools.notes as notes


def test_save_note_and_list_notes_newest_first_with_search(monkeypatch, tmp_path):
    monkeypatch.setattr(notes, "NOTE_FOLDER", tmp_path)

    assert notes.save_note(text="buy milk").startswith("Note saved to ")
    notes.save_note(text="call the dentist")
    first, second = sorted(tmp_path.glob("note_*.txt"))
    os.utime(first, (1, 1))  # make the "buy milk" note clearly older

    assert [n["text"] for n in notes.list_notes()] == ["call the dentist", "buy milk"]
    assert [n["text"] for n in notes.list_notes(query="MILK")] == ["buy milk"]
    assert notes.list_notes(query="eggs") == "No notes contain 'eggs'."


def test_notes_saved_in_the_same_second_do_not_overwrite_each_other(monkeypatch, tmp_path):
    monkeypatch.setattr(notes, "NOTE_FOLDER", tmp_path)

    notes.save_note_text("one")
    notes.save_note_text("two")

    assert len(list(tmp_path.glob("note_*.txt"))) == 2


def test_save_note_rejects_empty_text(monkeypatch, tmp_path):
    monkeypatch.setattr(notes, "NOTE_FOLDER", tmp_path)

    assert notes.save_note(text="  ") == "Nothing to save: pass the note as text."
    assert notes.list_notes() == "No notes saved yet."
