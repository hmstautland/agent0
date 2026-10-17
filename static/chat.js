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

const permSection = document.getElementById("stream-permission");
const permForm = document.getElementById("stream-permission-form");

// Set when a stream delivers a final answer, an error or a permission card -
// a stream that ends without one of these was cut off.
let streamFinished = false;

function showError(message) {
  thinkingImg.classList.add("hidden");
  streamErrorText.textContent = message;
  streamError.classList.remove("hidden");
}

function showPermissionRequest(eventData) {
  document.getElementById("perm-action").textContent = eventData.action;
  document.getElementById("perm-risk").textContent = eventData.risk;
  document.getElementById("perm-reason").textContent = eventData.reason || "No reason provided.";
  document.getElementById("perm-args").textContent = JSON.stringify(eventData.args || {}, null, 2);
  document.getElementById("perm-external").classList.toggle("hidden", !eventData.external);
  document.getElementById("perm-run-id").value = eventData.run_id;

  permSection.classList.remove("hidden");
}

async function handleAskStream(formData) {
  clearStreamUI();
  responseCard?.classList.add("hidden");
  permSection.classList.add("hidden");
  streamFinished = false;

  let res;
  try {
    res = await fetch("/ask_stream", {
      method: "POST",
      body: formData,
    });
  } catch (error) {
    showError(`Could not reach the server: ${error.message}`);
    return;
  }

  if (!res.ok) {
    showError(`The server answered ${res.status} ${res.statusText}. Try again, or reload the page if you were logged out.`);
    return;
  }

  if (!res.body) {
    showStatus("LLM stream not available.");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
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
  } catch (error) {
    showError(`The connection was lost: ${error.message}`);
    return;
  }

  if (buffer.trim()) {
    try {
      handleStreamEvent(JSON.parse(buffer));
    } catch (error) {
      console.error("Stream parse error", error, buffer);
    }
  }

  if (!streamFinished) {
    showError("The response ended before the agent finished. Check the server log and try again.");
  }
}

function handleStreamEvent(event) {
  if (["final_response", "error", "permission_required"].includes(event.event)) {
    streamFinished = true;
  }

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
      loadCalendarMonth(event.show_calendar.year, event.show_calendar.month, event.show_calendar.day);
    }
    renderAudioResult(event.audio);
  } else if (event.event === "error") {
    showError(event.message || "Unknown error");
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

// Approve/Reject continues the parked run over the stream, so progress keeps
// showing instead of falling back to the full-page /ask.
permForm.addEventListener("submit", async function (e) {
  e.preventDefault();
  const formData = new FormData(permForm);
  formData.set("permission_decision", e.submitter?.value === "y" ? "y" : "n");
  await handleAskStream(formData);
});

document.getElementById("input").addEventListener("keydown", function (e) {
  if (e.key === "Enter") {
    e.preventDefault();
    chatForm.requestSubmit();
  }
});
