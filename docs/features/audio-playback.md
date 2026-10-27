# Audio playback

Find and play audio saved in `local_storage/audio/` (for example from [text-to-speech](text-to-speech.md)) by name or number.

## Using it

- "play holiday" plays the file whose name contains "holiday" (`my-holiday-music.mp3`).
- If several files match, they're shown as buttons. Click one, or type "play number 2".
- "play" on its own lists the saved files.

## How it works

`features/audio/player.py` (`play_audio_file`) is a registry tool, so the model can use it. Messages starting with "play" are also caught directly (`parse_play_command`) before the model runs, because the local model doesn't reliably reach for the tool on its own. A list of matches is sent as a structured `audio` field on the final answer and drawn as buttons (`features/audio/static/audio-player.js`).

## Limits

- The list behind "number N" is kept in process memory. It's lost on restart and shared by everyone using the server, so it's single-user.
