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
const doneBtn = document.getElementById("done");

// Target language is passed in the query string (?lang=en-US).
const params = new URLSearchParams(location.search);
const lang = params.get("lang") || "en-US";

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

let micStream = null;   // kept open so the mic stays WARM (captures the 1st word)

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
  try { micStream && micStream.getTracks().forEach((t) => t.stop()); } catch (_) {}
  // Give the message a moment to flush before closing the window.
  setTimeout(() => window.close(), 250);
}

async function run() {
  if (!SR) {
    setStatus("Speech recognition isn't supported in this browser.");
    retryBtn.hidden = false;
    return;
  }

  // 1) Obtain mic permission AND keep the stream open so the mic stays warm.
  // (Stopping it here makes SpeechRecognition re-acquire the device, and the
  // ~300ms warmup swallows the first words. Keeping it open fixes that.)
  try {
    setStatus("Requesting microphone…");
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    setStatus("Microphone blocked: " + (err?.name || err) + ". Allow it in Chrome settings.");
    retryBtn.hidden = false;
    return;
  }

  // 2) Run speech recognition.
  // CONTINUOUS so a natural pause mid-sentence doesn't end capture early — we
  // accumulate the full utterance and only finish after a real silence (or when
  // the user clicks Done). This fixes "it closed while I was still talking".
  const recognition = new SR();
  recognition.lang = lang;
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;
  activeRecognition = recognition;

  let sent = false;
  let finalText = "";
  let silenceTimer = null;
  const SILENCE_MS = 1800;   // end this long after you stop speaking
  const MAX_MS = 20000;      // hard cap so it never hangs

  const relayOnce = (transcript) => {
    if (sent) return;
    sent = true;
    if (silenceTimer) clearTimeout(silenceTimer);
    relayAndClose({
      type: "goopher_transcript",
      transcript: (transcript || "").trim(),
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    });
  };
  // Stop a moment after the last speech so the whole sentence is captured.
  const armSilence = () => {
    if (silenceTimer) clearTimeout(silenceTimer);
    silenceTimer = setTimeout(() => { try { recognition.stop(); } catch (_) {} }, SILENCE_MS);
  };

  recognition.onstart = () => {
    dot.classList.add("live");
    setStatus("Starting…");
    doneBtn.hidden = false;
  };
  // Fires when audio capture actually begins — only NOW is it safe to speak, so
  // this is the real "go" cue (prevents losing the first words).
  recognition.onaudiostart = () => setStatus("🎤 Listening — speak now");
  recognition.onresult = (e) => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) finalText += r[0].transcript + " ";
      else interim += r[0].transcript;
    }
    setStatus("“" + (finalText + interim).trim() + "”");
    armSilence();              // reset the silence countdown on every word
  };
  recognition.onerror = (e) => {
    dot.classList.remove("live");
    if (e.error === "no-speech") {
      if (finalText.trim()) { relayOnce(finalText); return; }
      setStatus("Didn't catch that. Click Try again.");
    } else if (e.error === "not-allowed" || e.error === "service-not-allowed") {
      setStatus("Microphone not allowed. Enable it in Chrome settings, then retry.");
    } else if (e.error === "aborted") {
      return;                  // we stopped it on purpose
    } else {
      setStatus("Voice error: " + e.error);
    }
    doneBtn.hidden = true;
    retryBtn.hidden = false;
  };
  recognition.onend = () => {
    dot.classList.remove("live");
    const t = finalText.trim();
    if (t) relayOnce(t);       // relay the FULL accumulated sentence
    else if (!sent) { setStatus("Didn't catch that. Click Try again."); doneBtn.hidden = true; retryBtn.hidden = false; }
  };

  setTimeout(() => { try { recognition.stop(); } catch (_) {} }, MAX_MS);

  try {
    recognition.start();
  } catch (err) {
    setStatus("Couldn't start: " + (err?.message || err));
    retryBtn.hidden = false;
  }
}

let activeRecognition = null;
retryBtn.addEventListener("click", () => {
  retryBtn.hidden = true;
  doneBtn.hidden = true;
  run();
});
doneBtn.addEventListener("click", () => {
  // Finish now and send what's been captured.
  try { activeRecognition && activeRecognition.stop(); } catch (_) {}
});

run();
