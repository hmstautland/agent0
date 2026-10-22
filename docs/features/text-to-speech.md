# Text-to-speech (Kokoro-82M)

Turn text, a two-person dialogue or a document into speech, generated locally.

## Using it

Open the dashboard with the 🗣️ icon in the chat bar. Weights download from Hugging Face the first time an accent is used, into `KOKORO_CACHE_DIR`. After that everything runs offline.

**ffmpeg** is required for MP3/OGG output and for converting files (WAV and FLAC work without it): `sudo pacman -S ffmpeg` or `sudo apt install ffmpeg`.

**Voices** (British English): Alice, Emma, Isabella, Lily (female); Daniel, Fable, George, Lewis (male).

**Dialogue**: start each line with `A:` or `B:` (case-insensitive). Each speaker gets their own voice (defaults: A Isabella, B George), and turns are joined with a 0.3 s gap. Consecutive lines from one speaker are merged, and lines without a prefix are rejected.

```
A: Have you tried the new coffee place?
B: Not yet, is it any good?
```

**Documents**: drop or browse a `.txt`, `.md`/`.markdown` or `.docx` file (max 20 MB) to fill the text box. Markdown files are flattened to speakable text; text you type is left as it is. `.doc` isn't supported.

**File names**: the optional title is sanitised and made unique (`My Clip.wav`, `My Clip_2.wav`). Without a title, the file is named `tts_<date>_<HH-MM>`. A dialog shows the saved file with a "Play now" button; nothing plays automatically.

**Convert**: re-encode a WAV/MP3/FLAC/OGG file (max 100 MB) with ffmpeg, without running Kokoro. Output is named `converted_<timestamp>.<ext>`.

## How it works

Everything lives in `features/audio/`. `text_to_speech.py` runs Kokoro, `routes.py` holds the endpoints, and `static/tts.js` is the dashboard. TTS is a direct UI action, not an agent tool. Output goes to `local_storage/audio/` and is served at `/audio/<file>`, which requires login.

| Endpoint | Purpose |
| --- | --- |
| `POST /tts` | Generate speech (`text`, `voice`, `speed`, `output_format`, `title`) |
| `POST /tts/dialogue` | Two-speaker dialogue (`text`, `voice_a`, `voice_b`, `speed`, `output_format`, `title`) |
| `POST /tts/convert` | Re-encode an audio file (`file`, `output_format`) |
| `POST /tts/extract-text` | Extract text from a document (`file`) |
| `GET /tts/voices` | Voices, formats, speed range and defaults |
| `GET /tts/files` | List or search saved audio (`q`) |

All routes require a logged-in session (401 otherwise).

## Settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `TTS_DEVICE` | `auto` | `auto` (CUDA if available), `cpu`, or `cuda` |
| `KOKORO_CACHE_DIR` | `models/kokoro` | Model weight cache |

## Limits

- Speed 0.5-2.0 (default 1.0); formats `wav` (default), `mp3`, `flac`, `ogg`; max 10,000 words per request; default voice Isabella.
- British English voices only.

Kokoro-82M is released by [hexgrad](https://huggingface.co/hexgrad/Kokoro-82M) under Apache 2.0.
