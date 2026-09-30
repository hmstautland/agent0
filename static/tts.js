// Text-to-speech dashboard: opened via the chat bar's TTS icon. Generates
// speech through Kokoro (server picks the backend based on the chosen voice)
// and renders an audio player + a download link matching the chosen format.

const TTS_SETTINGS_KEY = "tts-dashboard-settings";

function loadTtsSettings() {
  try {
    return JSON.parse(sessionStorage.getItem(TTS_SETTINGS_KEY)) || {};
  } catch (err) {
    return {};
  }
}

function saveTtsSettings(settings) {
  try {
    sessionStorage.setItem(TTS_SETTINGS_KEY, JSON.stringify(settings));
  } catch (err) {
    // sessionStorage unavailable (private browsing, etc.) - selections just won't persist.
  }
}

function populateVoiceSelect(select, voices, wanted) {
  const groups = {};
  select.innerHTML = "";
  for (const voice of voices) {
    if (!groups[voice.group]) {
      groups[voice.group] = document.createElement("optgroup");
      groups[voice.group].label = voice.group;
      select.appendChild(groups[voice.group]);
    }
    const option = document.createElement("option");
    option.value = voice.id;
    option.textContent = voice.label;
    groups[voice.group].appendChild(option);
  }

  if (wanted && [...select.options].some((o) => o.value === wanted)) {
    select.value = wanted;
  }
}

async function loadVoices() {
  const saved = loadTtsSettings();

  try {
    const res = await fetch("/tts/voices");
    const data = await res.json();

    populateVoiceSelect(document.getElementById("tts-dash-voice"), data.voices, saved.voice || data.default);
    populateVoiceSelect(
      document.getElementById("tts-voice-a"),
      data.voices,
      saved.voiceA || data.dialogue_default?.voice_a
    );
    populateVoiceSelect(
      document.getElementById("tts-voice-b"),
      data.voices,
      saved.voiceB || data.dialogue_default?.voice_b
    );
  } catch (err) {
    // Voice selects just stay empty; synthesis still falls back to the
    // server-side defaults if none is sent.
  }
}

function applyDialogueMode(enabled) {
  document.getElementById("tts-single-voice-field").classList.toggle("hidden", enabled);
  document.getElementById("tts-voice-a-field").classList.toggle("hidden", !enabled);
  document.getElementById("tts-voice-b-field").classList.toggle("hidden", !enabled);
  document.getElementById("tts-dialogue-hint").classList.toggle("hidden", !enabled);

  const textArea = document.getElementById("tts-text");
  textArea.placeholder = enabled
    ? "A: Have you tried the new coffee place?\nB: Not yet, is it any good?"
    : "Type or paste text to speak...";
}

function initTtsControls() {
  const saved = loadTtsSettings();
  const speed = document.getElementById("tts-speed");
  const speedValue = document.getElementById("tts-speed-value");
  const format = document.getElementById("tts-format");
  const dialogueMode = document.getElementById("tts-dialogue-mode");

  if (saved.speed) speed.value = saved.speed;
  if (saved.format) format.value = saved.format;
  speedValue.textContent = `${parseFloat(speed.value).toFixed(2)}x`;

  speed.addEventListener("input", () => {
    speedValue.textContent = `${parseFloat(speed.value).toFixed(2)}x`;
  });

  dialogueMode.checked = Boolean(saved.dialogueMode);
  applyDialogueMode(dialogueMode.checked);
  dialogueMode.addEventListener("change", () => applyDialogueMode(dialogueMode.checked));

  const convertFormat = document.getElementById("tts-convert-format");
  if (saved.convertFormat) convertFormat.value = saved.convertFormat;
}

let selectedConvertFile = null;

function initConvertDropZone() {
  const dropZone = document.getElementById("tts-drop-zone");
  const fileInput = document.getElementById("tts-convert-file");
  const text = document.getElementById("tts-drop-zone-text");

  const setFile = (file) => {
    selectedConvertFile = file || null;
    text.textContent = file
      ? file.name
      : "Drag an audio file here, or click to browse (WAV, MP3, FLAC, OGG)";
  };

  dropZone.addEventListener("click", () => fileInput.click());
  dropZone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });

  fileInput.addEventListener("change", () => setFile(fileInput.files[0]));

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("tts-drop-zone-active");
  });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("tts-drop-zone-active"));
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("tts-drop-zone-active");
    if (e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      setFile(e.dataTransfer.files[0]);
    }
  });
}

function toggleTtsDashboard() {
  const dashboard = document.getElementById("tts-dashboard");
  const btn = document.querySelector(".tts-btn");
  const opening = dashboard.classList.contains("hidden");

  if (opening) {
    const input = document.getElementById("input");
    const textArea = document.getElementById("tts-text");
    if (input.value.trim() && !textArea.value.trim()) {
      textArea.value = input.value.trim();
    }
  }

  dashboard.classList.toggle("hidden");
  btn.setAttribute("aria-expanded", String(opening));
}

async function generateSpeech() {
  const textArea = document.getElementById("tts-text");
  const voiceSelect = document.getElementById("tts-dash-voice");
  const voiceASelect = document.getElementById("tts-voice-a");
  const voiceBSelect = document.getElementById("tts-voice-b");
  const dialogueMode = document.getElementById("tts-dialogue-mode");
  const speed = document.getElementById("tts-speed");
  const format = document.getElementById("tts-format");
  const btn = document.getElementById("tts-generate-btn");
  const player = document.getElementById("tts-player");
  const audio = document.getElementById("tts-audio");
  const link = document.getElementById("tts-download");
  const error = document.getElementById("tts-error");

  const text = textArea.value.trim();
  const isDialogue = dialogueMode.checked;

  error.classList.add("hidden");

  if (!text) {
    error.textContent = "Type something first.";
    error.classList.remove("hidden");
    return;
  }

  saveTtsSettings({
    voice: voiceSelect.value,
    voiceA: voiceASelect.value,
    voiceB: voiceBSelect.value,
    dialogueMode: isDialogue,
    speed: speed.value,
    format: format.value,
  });

  const originalLabel = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Generating…";
  player.classList.add("hidden");

  try {
    const formData = new FormData();
    formData.append("text", text);
    formData.append("speed", speed.value);
    formData.append("output_format", format.value);

    let endpoint = "/tts";
    if (isDialogue) {
      endpoint = "/tts/dialogue";
      if (voiceASelect.value) formData.append("voice_a", voiceASelect.value);
      if (voiceBSelect.value) formData.append("voice_b", voiceBSelect.value);
    } else if (voiceSelect.value) {
      formData.append("voice", voiceSelect.value);
    }

    const res = await fetch(endpoint, {
      method: "POST",
      body: formData,
    });

    const data = await res.json();

    if (!res.ok) {
      error.textContent = data.error || "Speech generation failed.";
      error.classList.remove("hidden");
      return;
    }

    audio.src = data.audio_url;
    link.href = data.audio_url;
    link.download = data.filename;
    link.textContent = `Download ${format.value.toUpperCase()}`;

    player.classList.remove("hidden");
    // Ignore rejection here - browsers can block autoplay-with-sound
    // (especially after the await above breaks the user-gesture chain),
    // but the file is fine and the visible native controls still work.
    audio.play().catch(() => {});
  } catch (err) {
    error.textContent = "Speech generation failed.";
    error.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    btn.textContent = originalLabel;
  }
}

async function convertFile() {
  const format = document.getElementById("tts-convert-format");
  const btn = document.getElementById("tts-convert-btn");
  const player = document.getElementById("tts-player");
  const audio = document.getElementById("tts-audio");
  const link = document.getElementById("tts-download");
  const error = document.getElementById("tts-error");

  error.classList.add("hidden");

  if (!selectedConvertFile) {
    error.textContent = "Choose a file to convert first.";
    error.classList.remove("hidden");
    return;
  }

  saveTtsSettings({ ...loadTtsSettings(), convertFormat: format.value });

  const originalLabel = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Converting…";
  player.classList.add("hidden");

  try {
    const formData = new FormData();
    formData.append("file", selectedConvertFile);
    formData.append("output_format", format.value);

    const res = await fetch("/tts/convert", {
      method: "POST",
      body: formData,
    });

    const data = await res.json();

    if (!res.ok) {
      error.textContent = data.error || "Conversion failed.";
      error.classList.remove("hidden");
      return;
    }

    audio.src = data.audio_url;
    link.href = data.audio_url;
    link.download = data.filename;
    link.textContent = `Download ${format.value.toUpperCase()}`;

    player.classList.remove("hidden");
    // Ignore rejection here - browsers can block autoplay-with-sound
    // (especially after the await above breaks the user-gesture chain),
    // but the file is fine and the visible native controls still work.
    audio.play().catch(() => {});
  } catch (err) {
    error.textContent = "Conversion failed.";
    error.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    btn.textContent = originalLabel;
  }
}

function renderSavedAudioResults(files) {
  const results = document.getElementById("tts-play-results");

  if (!files || files.length === 0) {
    results.innerHTML = `<p class="tts-hint">No saved audio files match.</p>`;
    return;
  }

  results.innerHTML = files
    .map(
      (f, i) => `<button type="button" class="audio-choice-btn" data-index="${i}">▶ ${f.filename}</button>`
    )
    .join("");

  results.querySelectorAll(".audio-choice-btn").forEach((btn) => {
    btn.addEventListener("click", () => playSavedAudio(files[Number(btn.dataset.index)]));
  });
}

function playSavedAudio(file) {
  const player = document.getElementById("tts-player");
  const audio = document.getElementById("tts-audio");
  const link = document.getElementById("tts-download");

  audio.src = file.audio_url;
  link.href = file.audio_url;
  link.download = file.filename;
  link.textContent = "Download";

  player.classList.remove("hidden");
  audio.play().catch(() => {});
}

async function searchSavedAudio() {
  const query = document.getElementById("tts-play-search").value.trim();
  const results = document.getElementById("tts-play-results");

  try {
    const res = await fetch(`/tts/files${query ? `?q=${encodeURIComponent(query)}` : ""}`);
    const data = await res.json();
    renderSavedAudioResults(data.files);
  } catch (err) {
    results.innerHTML = `<p class="tts-hint">Couldn't load saved files.</p>`;
  }
}

loadVoices();
initTtsControls();
initConvertDropZone();
searchSavedAudio();

document.getElementById("tts-play-search").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    searchSavedAudio();
  }
});
