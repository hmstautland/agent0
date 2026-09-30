import core.auth as auth_mod
import core.speech_routes as speech_routes
from fastapi.testclient import TestClient
from core.ui import app


def _logged_in_client(monkeypatch):
    monkeypatch.setattr(auth_mod, "PASSWORD", "testpass")
    client = TestClient(app)
    client.post("/login", data={"password": "testpass"})
    return client


def test_tts_voices_lists_grouped_kokoro_voices_and_formats(monkeypatch):
    client = _logged_in_client(monkeypatch)

    response = client.get("/tts/voices")
    data = response.json()

    assert response.status_code == 200
    assert {v["group"] for v in data["voices"]} == {"British English"}
    assert set(data["formats"]) == {"wav", "mp3", "flac", "ogg"}
    assert data["speed"]["min"] == 0.5
    assert data["speed"]["max"] == 2.0
    assert data["dialogue_default"] == {"voice_a": "bf_isabella", "voice_b": "bm_george"}


def test_tts_endpoint_returns_audio_url_on_success(monkeypatch):
    client = _logged_in_client(monkeypatch)

    monkeypatch.setattr(
        speech_routes,
        "synthesize",
        lambda text, voice_id, speed, output_format: {
            "path": "/tmp/tts_test.wav",
            "filename": "tts_test.wav",
            "mime_type": "audio/wav",
        },
    )

    response = client.post("/tts", data={"text": "hello", "voice": "bf_isabella"})

    assert response.status_code == 200
    body = response.json()
    assert body["audio_url"] == "/audio/tts_test.wav"
    assert body["mime_type"] == "audio/wav"


def test_tts_endpoint_returns_400_on_validation_error(monkeypatch):
    client = _logged_in_client(monkeypatch)

    def raise_value_error(text, voice_id, speed, output_format):
        raise ValueError("Speed must be between 0.5 and 2.0")

    monkeypatch.setattr(speech_routes, "synthesize", raise_value_error)

    response = client.post("/tts", data={"text": "hello", "speed": "10"})

    assert response.status_code == 400
    assert "Speed must be between" in response.json()["error"]


def test_tts_endpoint_returns_500_with_clear_message_when_kokoro_missing(monkeypatch):
    client = _logged_in_client(monkeypatch)

    def raise_runtime_error(text, voice_id, speed, output_format):
        raise RuntimeError("Kokoro TTS is not installed. Install it with `pip install kokoro soundfile`.")

    monkeypatch.setattr(speech_routes, "synthesize", raise_runtime_error)

    response = client.post("/tts", data={"text": "hello"})

    assert response.status_code == 500
    assert "Kokoro TTS is not installed" in response.json()["error"]


def test_tts_requires_authentication():
    client = TestClient(app)

    response = client.post("/tts", data={"text": "hello"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_tts_dialogue_endpoint_returns_audio_url_on_success(monkeypatch):
    client = _logged_in_client(monkeypatch)
    calls = []

    def fake_synthesize_dialogue(text, voice_a, voice_b, speed, output_format):
        calls.append((text, voice_a, voice_b))
        return {"path": "/tmp/tts_dialogue_test.wav", "filename": "tts_dialogue_test.wav", "mime_type": "audio/wav"}

    monkeypatch.setattr(speech_routes, "synthesize_dialogue", fake_synthesize_dialogue)

    response = client.post(
        "/tts/dialogue",
        data={"text": "A: hi\nB: hello", "voice_a": "bf_isabella", "voice_b": "bm_george"},
    )

    assert response.status_code == 200
    assert response.json()["audio_url"] == "/audio/tts_dialogue_test.wav"
    assert calls == [("A: hi\nB: hello", "bf_isabella", "bm_george")]


def test_tts_dialogue_endpoint_returns_400_for_unlabeled_lines(monkeypatch):
    client = _logged_in_client(monkeypatch)

    def raise_value_error(text, voice_a, voice_b, speed, output_format):
        raise ValueError('Each line must start with "A:" or "B:" to mark the speaker - got: "no label here"')

    monkeypatch.setattr(speech_routes, "synthesize_dialogue", raise_value_error)

    response = client.post("/tts/dialogue", data={"text": "no label here"})

    assert response.status_code == 400
    assert "A:" in response.json()["error"]


def test_tts_dialogue_requires_authentication():
    client = TestClient(app)

    response = client.post("/tts/dialogue", data={"text": "A: hi\nB: hello"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_tts_convert_endpoint_returns_audio_url_on_success(monkeypatch):
    client = _logged_in_client(monkeypatch)
    calls = []

    def fake_convert(upload_file_obj, filename, output_format):
        calls.append((filename, output_format))
        return {"path": "/tmp/converted_test.mp3", "filename": "converted_test.mp3", "mime_type": "audio/mpeg"}

    monkeypatch.setattr(speech_routes, "convert_audio_file", fake_convert)

    response = client.post(
        "/tts/convert",
        files={"file": ("clip.wav", b"fake wav bytes", "audio/wav")},
        data={"output_format": "mp3"},
    )

    assert response.status_code == 200
    assert response.json()["audio_url"] == "/audio/converted_test.mp3"
    assert calls == [("clip.wav", "mp3")]


def test_tts_convert_endpoint_returns_400_without_a_file(monkeypatch):
    client = _logged_in_client(monkeypatch)

    response = client.post("/tts/convert", data={"output_format": "mp3"})

    assert response.status_code == 400
    assert "No file provided" in response.json()["error"]


def test_tts_convert_endpoint_returns_400_for_unsupported_file_type(monkeypatch):
    client = _logged_in_client(monkeypatch)

    def raise_value_error(upload_file_obj, filename, output_format):
        raise ValueError("Unsupported input file type: .exe. Choose from ['flac', 'mp3', 'ogg', 'wav']")

    monkeypatch.setattr(speech_routes, "convert_audio_file", raise_value_error)

    response = client.post(
        "/tts/convert",
        files={"file": ("malware.exe", b"bytes", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "Unsupported input file type" in response.json()["error"]


def test_tts_convert_requires_authentication():
    client = TestClient(app)

    response = client.post(
        "/tts/convert",
        files={"file": ("clip.wav", b"bytes", "audio/wav")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_tts_files_lists_matches_for_the_dashboards_browse_panel(monkeypatch):
    client = _logged_in_client(monkeypatch)

    from pathlib import Path

    fake_match = Path("/tmp/my-holiday-music.mp3")
    monkeypatch.setattr(speech_routes, "find_audio_files", lambda q: [fake_match])

    response = client.get("/tts/files?q=holiday")

    assert response.status_code == 200
    assert response.json() == {"files": [{"filename": "my-holiday-music.mp3", "audio_url": "/audio/my-holiday-music.mp3"}]}


def test_tts_files_requires_authentication():
    client = TestClient(app)

    response = client.get("/tts/files", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
