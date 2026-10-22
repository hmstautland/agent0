# Notes

Quick notes saved to local storage, by typing or speaking.

## Using it

- Start a message with `note` or `take note`: "note: buy coffee filters". In the web UI it's saved directly, without the model.
- Say the same into the mic button. The transcription is saved as a note.
- Ask the agent to remember something, or to list your notes ("what notes did I save about coffee?"). It uses the `save_note` and `list_notes` tools.

## How it works

Each note is a text file `local_storage/note_<timestamp>.txt` with a `Saved:` and `Source:` (text, speech or agent) header. HTML and script tags are stripped before saving. Code: `tools/notes.py`.

## Limits

- Notes can't be edited or deleted from chat.
- `list_notes` searches by plain substring, not full-text search.
