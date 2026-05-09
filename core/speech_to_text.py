from scipy.io.wavfile import write
from faster_whisper import WhisperModel
from pynput import keyboard
import sounddevice as sd
import tempfile
import numpy as np

# model = WhisperModel("base", compute_type="int8")  
model = WhisperModel("base", device="cpu", compute_type="int8")
# options: tiny, base, small (bigger = more accurate, slower)


recording = False
audio_buffer = []
fs = 16000


def on_press(key):
    global recording, audio_buffer
    try:
        if key.char == 'r':  # hold 'r' to record
            recording = True
            audio_buffer = []
            print("🎤 Recording...")
    except:
        pass


def on_release(key):
    global recording
    try:
        if key.char == 'r':
            recording = False
            print("✅ Done recording")
            return False  # stop listener
    except:
        pass


def record_push_to_talk():
    global recording, audio_buffer

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        with sd.InputStream(samplerate=fs, channels=1, device=1) as stream:
            while listener.running:
                if recording:
                    chunk, _ = stream.read(1024)
                    audio_buffer.append(chunk)

    audio = np.concatenate(audio_buffer)

    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    write(temp_file.name, fs, audio)

    return temp_file.name


def transcribe_audio(file_path):
    segments, _ = model.transcribe(file_path)

    text = ""
    for segment in segments:
        text += segment.text + " "

    #  well print another place in the future
    print(f"🤖 You said: {text}")
    return text.strip()


def listen():
    file_path = record_push_to_talk()
    text = transcribe_audio(file_path)

    #  well print another place in the future
    print(f"🤖 You said: {text}")
    return text.strip()