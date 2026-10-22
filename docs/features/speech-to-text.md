# Speech-to-text

Speak instead of typing, transcribed locally with faster-whisper.

## Using it

- **Web:** click 🎤, speak, then click ⏹. The transcription fills the chat box for you to check and send. If it starts with "note", it's saved as a [note](notes.md) straight away.
- **CLI:** `python -m agent`, answer `s` at "Type (t) or Speak (s)?", press Enter, then hold **r** while speaking. Say or type "switch to text" / "switch to speech" to change modes.

## How it works

The browser records with `MediaRecorder` (`static/speech.js`) and posts the audio to `POST /speech` (`core/speech_routes.py`, login required). `core/speech_to_text.py` transcribes it with the Whisper `base` model on CPU (int8). STT is a direct UI action, not an agent tool, so it never goes through the model or the permission check.

## Limits

- The model size (`base`) and device are hard-coded in `core/speech_to_text.py`.
- The CLI records from input device 1 and keeps the recording in process-global state, so it's single-user.
- On other devices the mic needs HTTPS (see [remote access](remote-access.md)).
