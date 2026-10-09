// Chat form, streaming responses, status/thinking UI and the permission prompt.
// Loaded last: it declares the elements the other scripts use and wires up the
// listeners, so the DOM must already exist.

const chatForm = document.getElementById("main-chat-form");
const streamCard = document.getElementById("stream-card");
const streamHeading = document.getElementById("stream-heading");
const thinkingImg = document.getElementById("thinking-img");
const streamOutput = document.getElementById("stream-output");
const streamAudio = document.getElementById("stream-audio");
const streamError = document.getElementById("stream-error");
const streamErrorText = document.getElementById("stream-error-text");
const responseCard = document.getElementById("server-response-card");

function showStatus(message) {
  streamCard.classList.remove("hidden");
  streamHeading.textContent = message;
  thinkingImg.classList.remove("hidden");
  streamOutput.textContent = "";
}

function clearStreamUI() {
  streamHeading.textContent = "";
  streamOutput.textContent = "";
  streamErrorText.textContent = "";
  streamAudio.innerHTML = "";
  thinkingImg.classList.add("hidden");
  streamCard.classList.add("hidden");
  calendarCard.classList.add("hidden");
  streamAudio.classList.add("hidden");
  streamError.classList.add("hidden");
}

async function showPermissionRequest(eventData) {
  const permSection = document.getElementById("stream-permission");
  const permAction = document.getElementById("perm-action");
  const permRisk = document.getElementById("perm-risk");
  const permReason = document.getElementById("perm-reason");
  const permArgs = document.getElementById("perm-args");
  const permInput = document.getElementById("perm-input");
  const permActionField = document.getElementById("perm-action-field");
  const permArgsField = document.getElementById("perm-args-field");
  const permRiskField = document.getElementById("perm-risk-field");
  const permButtons = document.getElementById("perm-buttons");

  permAction.textContent = eventData.action;
  permRisk.textContent = eventData.risk;
  permReason.textContent = eventData.reason || "No reason provided.";
  permArgs.textContent = JSON.stringify(eventData.args || {}, null, 2);

  permInput.value = eventData.input || "";
  permActionField.value = eventData.action;
  permArgsField.value = JSON.stringify(eventData.args || {});
  permRiskField.value = eventData.risk;

  permButtons.innerHTML = `
    <button type="submit" name="permission_decision" value="y">Approve</button>
    <button type="submit" name="permission_decision" value="n">Reject</button>
  `;

  permSection.classList.remove("hidden");
}

async function handleAskStream(formData) {
  clearStreamUI();
  responseCard?.classList.add("hidden");
  document.getElementById("stream-permission").classList.add("hidden");

  const res = await fetch("/ask_stream", {
    method: "POST",
    body: formData,
  });

  if (!res.body) {
    showStatus("LLM stream not available.");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop();

    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        handleStreamEvent(JSON.parse(line));
      } catch (error) {
        console.error("Stream parse error", error, line);
      }
    }
  }

  if (buffer.trim()) {
    try {
      handleStreamEvent(JSON.parse(buffer));
    } catch (error) {
      console.error("Stream parse error", error, buffer);
    }
  }
}

function handleStreamEvent(event) {
  if (event.event === "status") {
    showStatus(event.message);
  } else if (event.event === "final_response") {
    thinkingImg.classList.add("hidden");
    if (event.response) {
      streamCard.classList.remove("hidden");
      streamHeading.textContent = "Response";
      streamOutput.textContent = event.response;
    } else {
      streamCard.classList.add("hidden");
    }
    if (event.show_calendar) {
      loadCalendarMonth(event.show_calendar.year, event.show_calendar.month);
    }
    renderAudioResult(event.audio);
  } else if (event.event === "error") {
    thinkingImg.classList.add("hidden");
    streamErrorText.textContent = event.message || "Unknown error";
    streamError.classList.remove("hidden");
  } else if (event.event === "permission_required") {
    thinkingImg.classList.add("hidden");
    showPermissionRequest(event);
  }
}

chatForm.addEventListener("submit", async function (e) {
  e.preventDefault();
  const formData = new FormData(chatForm);
  await handleAskStream(formData);
});

document.getElementById("input").addEventListener("keydown", function (e) {
  if (e.key === "Enter") {
    e.preventDefault();
    chatForm.requestSubmit();
  }
});
