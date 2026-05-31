// GOOPHER voice-capture popup.
//
// Why this exists: Chrome MV3 SIDE PANELS cannot reliably obtain microphone
// access — SpeechRecognition throws "not-allowed" there even when the mic is
// allowed in Chrome settings. A normal extension page opened as a popup WINDOW
// *can* get the mic. So the side panel opens this page, we capture speech here,
// and we send the transcript back to the side panel via chrome.runtime messaging.

const dot = document.getElementById("dot");
const statusEl = document.getElementById("status");
const retryBtn = document.getElementById("retry");

// Target language is passed in the query string (?lang=en-US).
const params = new URLSearchParams(location.search);
const lang = params.get("lang") || "en-US";

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

function setStatus(msg) {
  statusEl.textContent = msg;
}

// Send a message to the side panel (and anywhere else listening), then close.
function relayAndClose(payload) {
  try {
    chrome.runtime.sendMessage(payload);
  } catch (_) {
    /* ignore */
  }
  // Give the message a moment to flush before closing the window.
  setTimeout(() => window.close(), 250);
}

async function run() {
  if (!SR) {
    setStatus("Speech recognition isn't supported in this browser.");
    retryBtn.hidden = false;
    return;
  }

  // 1) Obtain mic permission explicitly (popup windows can show this prompt).
  try {
    setStatus("Requesting microphone…");
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((t) => t.stop()); // we only needed the grant
  } catch (err) {
    setStatus("Microphone blocked: " + (err?.name || err) + ". Allow it in Chrome settings.");
    retryBtn.hidden = false;
    return;
  }

  // 2) Run speech recognition.
  const recognition = new SR();
  recognition.lang = lang;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    dot.classList.add("live");
    setStatus("Listening… speak now");
  };
  recognition.onresult = (e) => {
    const result = e.results[e.results.length - 1];
    const transcript = result[0].transcript;
    setStatus("“" + transcript + "”");
    if (result.isFinal) {
      relayAndClose({ type: "goopher_transcript", transcript: transcript.trim() });
    }
  };
  recognition.onerror = (e) => {
    dot.classList.remove("live");
    if (e.error === "no-speech") {
      setStatus("Didn't catch that. Click Try again.");
    } else if (e.error === "not-allowed" || e.error === "service-not-allowed") {
      setStatus("Microphone not allowed. Enable it in Chrome settings, then retry.");
    } else {
      setStatus("Voice error: " + e.error);
    }
    retryBtn.hidden = false;
  };
  recognition.onend = () => {
    dot.classList.remove("live");
  };

  try {
    recognition.start();
  } catch (err) {
    setStatus("Couldn't start: " + (err?.message || err));
    retryBtn.hidden = false;
  }
}

retryBtn.addEventListener("click", () => {
  retryBtn.hidden = true;
  run();
});

run();
