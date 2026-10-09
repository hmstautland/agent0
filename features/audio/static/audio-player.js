// Renders the "audio" field of a final_response stream event (see
// core/agent_routes.py's audio_play_result / features/audio/player.py's
// play_audio_file) into the streamAudio element declared in chat.js, which
// loads after this file but always runs before any of these functions are
// called.

function escapeAudioText(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}

function escapeHtmlAttr(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderAudioResult(audio) {
  if (!audio || audio.status === "error") {
    streamAudio.innerHTML = "";
    streamAudio.classList.add("hidden");
    return;
  }

  if (audio.status === "play") {
    streamAudio.innerHTML = `
      <div class="audio-play-card">
        <audio controls autoplay src="${escapeHtmlAttr(audio.audio_url)}"></audio>
        <p class="audio-play-filename">${escapeAudioText(audio.filename)}</p>
      </div>
    `;
    streamAudio.classList.remove("hidden");
    return;
  }

  if (audio.status === "choose") {
    const buttons = (audio.candidates || [])
      .map(
        (c) => `
        <button type="button" class="audio-choice-btn" data-number="${escapeHtmlAttr(c.number)}">
          ${escapeHtmlAttr(c.number)}. ${escapeAudioText(c.filename)}
        </button>`
      )
      .join("");

    streamAudio.innerHTML = `<div class="audio-play-card"><div class="audio-choice-list">${buttons}</div></div>`;
    streamAudio.classList.remove("hidden");

    streamAudio.querySelectorAll(".audio-choice-btn").forEach((btn) => {
      btn.addEventListener("click", () => submitPlayNumber(btn.dataset.number));
    });
    return;
  }

  streamAudio.innerHTML = "";
  streamAudio.classList.add("hidden");
}

// Sends "play number N" through the normal chat stream, exactly as if the
// user had typed or spoken it - reuses handleAskStream (chat.js) so the
// choice, permission handling, etc. all behave identically.
async function submitPlayNumber(number) {
  const formData = new FormData();
  formData.append("input", `play number ${number}`);
  await handleAskStream(formData);
}
