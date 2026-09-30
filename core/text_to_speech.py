import mimetypes
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent

AUDIO_DIR = BASE_DIR / "local_storage" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Python's mimetypes module guesses the legacy "audio/x-wav" / "audio/x-flac"
# aliases for these extensions on some systems. The /audio StaticFiles mount
# (core/ui.py) relies on mimetypes to set the Content-Type header, and
# stricter browsers (Safari in particular) refuse to play audio served with
# a non-standard type even though the bytes are perfectly valid - so the
# standard IANA types are registered explicitly, overriding the guess.
mimetypes.add_type("audio/wav", ".wav")
mimetypes.add_type("audio/flac", ".flac")

# Kokoro's native output rate. Kept as-is end-to-end (no resampling) since
# nothing downstream requires a different rate.
SAMPLE_RATE = 24000

# "auto" picks CUDA when available, otherwise CPU. Override with "cpu" or
# "cuda" to force one.
KOKORO_DEVICE = os.environ.get("TTS_DEVICE", "auto")

KOKORO_CACHE_DIR = Path(os.environ.get("KOKORO_CACHE_DIR", BASE_DIR / "models" / "kokoro"))
KOKORO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
# huggingface_hub (used internally by kokoro to fetch model weights) honors
# this to decide where downloaded files land; only set it if the user/host
# hasn't already pointed it somewhere else.
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(KOKORO_CACHE_DIR))

# Official English voices from hexgrad/Kokoro-82M
# (huggingface.co/hexgrad/Kokoro-82M/tree/main/voices). Only British English
# is offered - American English voices were dropped by request. lang_code
# selects Kokoro's grapheme-to-phoneme + prosody pipeline for the accent - it
# must match the voice's accent or the model mispronounces the text.
KOKORO_VOICES = {
    "bf_alice": {"label": "Alice (female)", "group": "British English", "lang_code": "b"},
    "bf_emma": {"label": "Emma (female)", "group": "British English", "lang_code": "b"},
    "bf_isabella": {"label": "Isabella (female)", "group": "British English", "lang_code": "b"},
    "bf_lily": {"label": "Lily (female)", "group": "British English", "lang_code": "b"},
    "bm_daniel": {"label": "Daniel (male)", "group": "British English", "lang_code": "b"},
    "bm_fable": {"label": "Fable (male)", "group": "British English", "lang_code": "b"},
    "bm_george": {"label": "George (male)", "group": "British English", "lang_code": "b"},
    "bm_lewis": {"label": "Lewis (male)", "group": "British English", "lang_code": "b"},
}
DEFAULT_VOICE = "bf_isabella"

# Defaults for the two-speaker dialogue feature.
DEFAULT_DIALOGUE_VOICE_A = "bf_isabella"
DEFAULT_DIALOGUE_VOICE_B = "bm_george"

# Silence inserted between dialogue turns, in seconds.
DIALOGUE_TURN_GAP_SECONDS = 0.3

_DIALOGUE_LINE_RE = re.compile(r"^\s*([AB])\s*:\s*(.+)$", re.IGNORECASE)

MIN_SPEED = 0.5
MAX_SPEED = 2.0
DEFAULT_SPEED = 1.0

OUTPUT_FORMATS = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "flac": "audio/flac",
    "ogg": "audio/ogg",
}
DEFAULT_OUTPUT_FORMAT = "wav"

# Long CPU synthesis jobs would otherwise tie up the request for a long time,
# so text past this length is rejected with a clear error instead.
MAX_TTS_WORDS = 10000

# Each chunk is synthesized in one Kokoro call and the results concatenated;
# this keeps memory/latency per call bounded for very long input. Kokoro
# further splits each chunk at sentence boundaries internally.
KOKORO_CHUNK_CHARS = 2000

# Cap on uploads to the format converter - generous for a spoken-word clip,
# small enough that an upload can't fill the disk.
MAX_CONVERT_FILE_BYTES = 100 * 1024 * 1024

_pipelines = {}  # lang_code -> KPipeline, lazily created and reused


def get_voices() -> list[dict]:
    """List the available Kokoro voices as [{"id", "label", "group"}, ...]."""
    return [
        {"id": voice_id, "label": info["label"], "group": info["group"]}
        for voice_id, info in KOKORO_VOICES.items()
    ]


def validate_speed(speed) -> float:
    try:
        speed = float(speed)
    except (TypeError, ValueError):
        raise ValueError(f"Speed must be a number between {MIN_SPEED} and {MAX_SPEED}")

    if not (MIN_SPEED <= speed <= MAX_SPEED):
        raise ValueError(f"Speed must be between {MIN_SPEED} and {MAX_SPEED}")

    return speed


def validate_output_format(output_format) -> str:
    output_format = (output_format or DEFAULT_OUTPUT_FORMAT).lower()

    if output_format not in OUTPUT_FORMATS:
        raise ValueError(f"Unsupported output format: {output_format}. Choose from {sorted(OUTPUT_FORMATS)}")

    return output_format


def _resolve_device() -> str:
    if KOKORO_DEVICE in ("cpu", "cuda"):
        return KOKORO_DEVICE

    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def _get_pipeline(lang_code: str):
    if lang_code not in _pipelines:
        from kokoro import KPipeline

        _pipelines[lang_code] = KPipeline(lang_code=lang_code, device=_resolve_device())

    return _pipelines[lang_code]


def _chunk_text(text: str, max_chars: int = KOKORO_CHUNK_CHARS) -> list[str]:
    """Split text into chunks of at most max_chars, breaking on sentence boundaries."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks = []
    current = ""

    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()

    if current:
        chunks.append(current)

    return chunks or [text]


def _synthesize_kokoro(text: str, voice_id: str, speed: float) -> np.ndarray:
    lang_code = KOKORO_VOICES[voice_id]["lang_code"]
    pipeline = _get_pipeline(lang_code)

    segments = []
    for chunk in _chunk_text(text):
        for _, _, audio in pipeline(chunk, voice=voice_id, speed=speed):
            segments.append(np.asarray(audio))

    if not segments:
        raise ValueError("No audio was generated for the given text")

    return np.concatenate(segments)


def _write_wav(samples: np.ndarray, path: Path) -> None:
    import soundfile as sf

    sf.write(str(path), samples, SAMPLE_RATE, subtype="PCM_16")


def _encode_flac(wav_path: Path) -> Path:
    import soundfile as sf

    out_path = wav_path.with_suffix(".flac")
    data, sr = sf.read(str(wav_path))
    sf.write(str(out_path), data, sr, format="FLAC")
    return out_path


# wav/flac entries are only used by the standalone file converter below - the
# TTS pipeline itself writes those two formats directly via soundfile and
# never needs ffmpeg for them.
_FFMPEG_CODEC_ARGS = {
    "wav": ["-codec:a", "pcm_s16le"],
    "flac": ["-codec:a", "flac"],
    "mp3": ["-codec:a", "libmp3lame", "-qscale:a", "2"],
    "ogg": ["-codec:a", "libopus", "-b:a", "96k"],
}


def _run_ffmpeg(input_path: Path, out_path: Path, output_format: str) -> None:
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(input_path), *_FFMPEG_CODEC_ARGS[output_format], str(out_path)],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError:
        raise RuntimeError(f"ffmpeg is not installed; cannot encode audio to {output_format}") from None
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"{output_format} encoding failed: {e.stderr.decode(errors='replace')}") from e


def _encode_with_ffmpeg(wav_path: Path, output_format: str) -> Path:
    out_path = wav_path.with_suffix(f".{output_format}")
    _run_ffmpeg(wav_path, out_path, output_format)
    return out_path


def _finalize_output(wav_path: Path, output_format: str) -> dict:
    if output_format == "wav":
        out_path = wav_path
    elif output_format == "flac":
        out_path = _encode_flac(wav_path)
    else:
        out_path = _encode_with_ffmpeg(wav_path, output_format)

    return {
        "path": str(out_path),
        "filename": out_path.name,
        "mime_type": OUTPUT_FORMATS[output_format],
    }


def synthesize(
    text: str,
    voice_id: str = None,
    speed: float = DEFAULT_SPEED,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
) -> dict:
    """Synthesize text to speech with Kokoro-82M, returning {"path", "filename", "mime_type"}."""
    text = (text or "").strip()
    if not text:
        raise ValueError("No text provided")

    word_count = len(text.split())
    if word_count > MAX_TTS_WORDS:
        raise ValueError(f"Text is too long (max {MAX_TTS_WORDS} words)")

    voice_id = voice_id or DEFAULT_VOICE
    if voice_id not in KOKORO_VOICES:
        raise ValueError(f"Unknown voice: {voice_id}")

    output_format = validate_output_format(output_format)
    speed = validate_speed(speed)

    try:
        samples = _synthesize_kokoro(text, voice_id, speed)
    except ImportError as e:
        raise RuntimeError(
            "Kokoro TTS is not installed. Install it with `pip install kokoro soundfile` (see README)."
        ) from e

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    wav_path = AUDIO_DIR / f"tts_{timestamp}.wav"
    _write_wav(samples, wav_path)

    return _finalize_output(wav_path, output_format)


def parse_dialogue(text: str) -> list[tuple[str, str]]:
    """Parse "A: ..." / "B: ..." lines into [(speaker, line), ...].

    Every non-blank line must start with "A:" or "B:" (case-insensitive) to
    mark who's speaking; consecutive lines for the same speaker are merged
    into a single turn.
    """
    turns = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = _DIALOGUE_LINE_RE.match(line)
        if not match:
            raise ValueError(f'Each line must start with "A:" or "B:" to mark the speaker - got: "{line}"')

        speaker, content = match.group(1).upper(), match.group(2).strip()
        if turns and turns[-1][0] == speaker:
            turns[-1] = (speaker, f"{turns[-1][1]} {content}")
        else:
            turns.append((speaker, content))

    if not turns:
        raise ValueError("No dialogue lines found")

    return turns


def synthesize_dialogue(
    text: str,
    voice_a: str = DEFAULT_DIALOGUE_VOICE_A,
    voice_b: str = DEFAULT_DIALOGUE_VOICE_B,
    speed: float = DEFAULT_SPEED,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
) -> dict:
    """Synthesize a two-speaker script into one audio file.

    text lines must be prefixed "A:" / "B:" (see parse_dialogue); voice_a and
    voice_b are the Kokoro voice IDs to use for each speaker. Turns are
    concatenated with a short silence gap between them.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("No text provided")

    voice_a = voice_a or DEFAULT_DIALOGUE_VOICE_A
    voice_b = voice_b or DEFAULT_DIALOGUE_VOICE_B
    for voice_id in (voice_a, voice_b):
        if voice_id not in KOKORO_VOICES:
            raise ValueError(f"Unknown voice: {voice_id}")

    output_format = validate_output_format(output_format)
    speed = validate_speed(speed)

    turns = parse_dialogue(text)

    word_count = sum(len(line.split()) for _, line in turns)
    if word_count > MAX_TTS_WORDS:
        raise ValueError(f"Text is too long (max {MAX_TTS_WORDS} words)")

    voices = {"A": voice_a, "B": voice_b}
    gap = np.zeros(int(DIALOGUE_TURN_GAP_SECONDS * SAMPLE_RATE), dtype=np.float32)

    try:
        segments = []
        for i, (speaker, line) in enumerate(turns):
            if i > 0:
                segments.append(gap)
            segments.append(_synthesize_kokoro(line, voices[speaker], speed))
    except ImportError as e:
        raise RuntimeError(
            "Kokoro TTS is not installed. Install it with `pip install kokoro soundfile` (see README)."
        ) from e

    samples = np.concatenate(segments)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    wav_path = AUDIO_DIR / f"tts_dialogue_{timestamp}.wav"
    _write_wav(samples, wav_path)

    return _finalize_output(wav_path, output_format)


def _save_upload_bounded(upload_file_obj, dest_path: Path, max_bytes: int) -> None:
    """Copy a file-like object to dest_path, aborting if it exceeds max_bytes."""
    written = 0
    try:
        with open(dest_path, "wb") as buffer:
            while True:
                chunk = upload_file_obj.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise ValueError(f"File is too large (max {max_bytes // (1024 * 1024)} MB)")
                buffer.write(chunk)
    except ValueError:
        dest_path.unlink(missing_ok=True)
        raise


def convert_audio_file(upload_file_obj, filename: str, output_format: str) -> dict:
    """Convert an uploaded audio file (wav/mp3/flac/ogg) to another format.

    No TTS synthesis is involved - this just re-encodes whatever audio the
    user provides via ffmpeg, for when only the output format needs to
    change.
    """
    ext = Path(filename or "").suffix.lstrip(".").lower()
    if ext not in OUTPUT_FORMATS:
        raise ValueError(f"Unsupported input file type: .{ext or '?'}. Choose from {sorted(OUTPUT_FORMATS)}")

    output_format = validate_output_format(output_format)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    input_path = AUDIO_DIR / f"upload_{timestamp}.{ext}"
    _save_upload_bounded(upload_file_obj, input_path, MAX_CONVERT_FILE_BYTES)

    try:
        out_path = AUDIO_DIR / f"converted_{timestamp}.{output_format}"
        if ext == output_format:
            shutil.copyfile(input_path, out_path)
        else:
            _run_ffmpeg(input_path, out_path, output_format)
    finally:
        input_path.unlink(missing_ok=True)

    return {
        "path": str(out_path),
        "filename": out_path.name,
        "mime_type": OUTPUT_FORMATS[output_format],
    }
