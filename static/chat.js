// Chat form, streaming responses, status/thinking UI (with the model's live
// output) and the permission prompt.
// Loaded last: it declares the elements the other scripts use and wires up the
// listeners, so the DOM must already exist.

const chatForm = document.getElementById("main-chat-form");
const streamCard = document.getElementById("stream-card");
const streamHeading = document.getElementById("stream-heading");
const thinkingRow = document.getElementById("thinking-row");
const thinkingStream = document.getElementById("thinking-stream");
const streamOutput = document.getElementById("stream-output");
const streamAudio = document.getElementById("stream-audio");
const streamError = document.getElementById("stream-error");
const streamErrorText = document.getElementById("stream-error-text");
const responseCard = document.getElementById("server-response-card");

// The input is docked at the bottom and the newest card sits right above it,
// so keep the feed scrolled to the end whenever an answer card appears or its
// content changes. Changes inside the TTS dashboard / calendar (typing,
// browsing months) are ignored so they never yank the view away; opening the
// dashboard scrolls its top into view instead, since it can be taller than
// the screen.
const chatFeed = document.getElementById("chat-feed");
const chatFeedInner = chatFeed.querySelector(".chat-feed-inner");
const ttsDashboard = document.getElementById("tts-dashboard");
const LIVE_CARD_IDS = ["stream-card", "stream-audio", "stream-error", "stream-permission"];

// The input dock is position: fixed at the bottom; the layout above it stops
// --dock-h short of the screen bottom so no card is ever hidden behind it.
const chatDock = document.querySelector(".chat-dock");
new ResizeObserver(() => {
  document.documentElement.style.setProperty("--dock-h", `${chatDock.offsetHeight}px`);
}).observe(chatDock);

function scrollFeedToLatest() {
  chatFeed.scrollTop = chatFeed.scrollHeight;
}

let feedScrollQueued = false;
new MutationObserver((mutations) => {
  let toLatest = false;

  for (const m of mutations) {
    const shown = m.type === "attributes" && m.target.parentElement === chatFeedInner && !m.target.classList.contains("hidden");
    if (shown && m.target === ttsDashboard) {
      ttsDashboard.scrollIntoView({ block: "start" });
      return;
    }
    if (shown || LIVE_CARD_IDS.some((id) => m.target.closest?.(`#${id}`) || m.target.parentElement?.closest(`#${id}`))) {
      toLatest = true;
    }
  }

  if (toLatest && !feedScrollQueued) {
    feedScrollQueued = true;
    requestAnimationFrame(() => {
      feedScrollQueued = false;
      scrollFeedToLatest();
    });
  }
}).observe(chatFeedInner, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["class"] });

// Plain /ask page render: start at the server's answer.
scrollFeedToLatest();

function showStatus(message) {
  streamCard.classList.remove("hidden");
  streamHeading.textContent = message;
  thinkingRow.classList.remove("hidden");
  streamOutput.textContent = "";
  // The next llm_delta belongs to a new LLM call (e.g. the next tool step).
  thinkingBlockOpen = false;
}

// Live model output in the box beside the thinking image. Consecutive text of
// the same kind (reasoning vs. reply) is merged into one span, and each LLM
// call starts on a fresh paragraph. The box only follows the newest text
// while the user hasn't scrolled up in it to read.
let thinkingBlockOpen = false;
let thinkingSpan = null;

function appendThinkingDelta(kind, text) {
  if (!text) return;

  const box = thinkingStream;
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 24;

  if (!thinkingBlockOpen) {
    if (box.childNodes.length) box.append("\n\n");
    thinkingSpan = null;
    thinkingBlockOpen = true;
  }
  if (!thinkingSpan || thinkingSpan.dataset.kind !== kind) {
    thinkingSpan = document.createElement("span");
    thinkingSpan.dataset.kind = kind;
    thinkingSpan.className = `llm-${kind}`;
    box.append(thinkingSpan);
  }
  thinkingSpan.append(text);

  if (atBottom) box.scrollTop = box.scrollHeight;
}

function clearThinkingStream() {
  thinkingStream.textContent = "";
  thinkingSpan = null;
  thinkingBlockOpen = false;
}

function clearStreamUI() {
  streamHeading.textContent = "";
  streamOutput.textContent = "";
  streamErrorText.textContent = "";
  streamAudio.innerHTML = "";
  clearThinkingStream();
  thinkingRow.classList.add("hidden");
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
  thinkingRow.classList.add("hidden");
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

// The send arrow turns into a stop block while a request runs. Stopping
// aborts the stream, tells the server (POST /ask_stream/stop) to cancel the
// request and discard what it left behind (its log lines; the turn is never
// stored), and leaves the typed question in the input to finish and resend.
const sendBtn = document.getElementById("send-btn");
let activeRequest = null;

function setRunning(running) {
  sendBtn.textContent = running ? "■" : "➜";
  sendBtn.classList.toggle("stop", running);
  sendBtn.type = running ? "button" : "submit";
  sendBtn.setAttribute("aria-label", running ? "Stop" : "Send");
  sendBtn.title = running ? "Stop - discard this request" : "Send";
}

function newRequestId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

async function handleAskStream(formData) {
  if (activeRequest) return;

  const active = { id: newRequestId(), controller: new AbortController(), stopped: false };
  activeRequest = active;
  formData.set("request_id", active.id);
  setRunning(true);
  try {
    await streamRequest(formData, active.controller.signal);
  } finally {
    if (activeRequest === active) {
      activeRequest = null;
      setRunning(false);
    }
  }
}

async function stopRequest() {
  const active = activeRequest;
  if (!active || active.stopped) return;
  active.stopped = true;

  const body = new FormData();
  body.set("request_id", active.id);
  const stopping = fetch("/ask_stream/stop", { method: "POST", body })
    .then((res) => (res.ok ? res.json() : null))
    .catch(() => null);
  active.controller.abort();

  clearStreamUI();
  responseCard?.classList.add("hidden");
  permSection.classList.add("hidden");
  streamCard.classList.remove("hidden");
  streamHeading.textContent = "Stopped. Nothing from this request was kept.";

  const result = await stopping;
  if (result?.already_done?.length) {
    streamOutput.textContent = `Already done before it stopped (not undone): ${result.already_done.join(", ")}`;
  }

  activeRequest = null;
  setRunning(false);
  document.getElementById("input").focus();
}

sendBtn.addEventListener("click", function () {
  if (activeRequest) stopRequest();
});

async function streamRequest(formData, signal) {
  clearStreamUI();
  responseCard?.classList.add("hidden");
  permSection.classList.add("hidden");
  streamFinished = false;

  let res;
  try {
    res = await fetch("/ask_stream", {
      method: "POST",
      body: formData,
      signal,
    });
  } catch (error) {
    if (signal.aborted) return;
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
    if (signal.aborted) return;
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
  } else if (event.event === "llm_delta") {
    appendThinkingDelta(event.kind, event.text);
  } else if (event.event === "final_response") {
    thinkingRow.classList.add("hidden");
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
    thinkingRow.classList.add("hidden");
    showPermissionRequest(event);
  }
}

chatForm.addEventListener("submit", async function (e) {
  e.preventDefault();
  if (activeRequest) return;
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

// "+" starts a new conversation: the agent stops seeing the earlier questions
// (it can still look them up with its search_history tool).
document.getElementById("new-chat-btn").addEventListener("click", async function () {
  let res;
  try {
    res = await fetch("/conversation/new", { method: "POST" });
  } catch (error) {
    showError(`Could not reach the server: ${error.message}`);
    return;
  }
  if (!res.ok) {
    showError(`The server answered ${res.status} ${res.statusText}. Reload the page if you were logged out.`);
    return;
  }

  clearStreamUI();
  responseCard?.classList.add("hidden");
  permSection.classList.add("hidden");
  streamCard.classList.remove("hidden");
  streamHeading.textContent = "New conversation started.";
  document.getElementById("input").focus();
});

document.getElementById("input").addEventListener("keydown", function (e) {
  if (e.key === "Enter") {
    e.preventDefault();
    chatForm.requestSubmit();
  }
});
