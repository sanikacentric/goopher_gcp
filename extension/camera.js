// GOOPHER camera-capture popup (for the Vision subagent).
//
// Why this exists: like the microphone, a Chrome MV3 SIDE PANEL can't reliably
// prompt for camera/mic access, but a normal extension page opened as a popup
// WINDOW can. This popup shows the live camera AND listens for the customer's
// spoken question at the same time ("show it and say it"). On capture, it relays
// one JPEG frame + the spoken (or typed) question to the side panel, which POSTs
// both to /vision.

const video = document.getElementById("preview");
const canvas = document.getElementById("canvas");
const statusEl = document.getElementById("status");
const transcriptEl = document.getElementById("transcript");
const captureBtn = document.getElementById("capture");
const retryBtn = document.getElementById("retry");

// Typed fallback question + speech language come in via the query string.
const params = new URLSearchParams(location.search);
const typedQuestion = params.get("q") || "";
const lang = params.get("lang") || "en-US";

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

let stream = null;
let recognition = null;
let finalTranscript = "";   // accumulated final speech
let liveTranscript = "";    // final + interim, shown live

function setStatus(msg) { statusEl.textContent = msg; }

function setTranscript(text, isEmpty) {
  transcriptEl.textContent = text;
  transcriptEl.classList.toggle("empty", !!isEmpty);
}

function stopAll() {
  try { recognition && recognition.stop(); } catch (_) {}
  if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; }
}

function relayAndClose(payload) {
  try { chrome.runtime.sendMessage(payload); } catch (_) {}
  setTimeout(() => window.close(), 200);
}

// --- speech: capture the spoken question while the camera is live ---
function startSpeech() {
  if (!SR) {
    setTranscript("Voice not supported here — type your question in GOOPHER instead.", true);
    return;
  }
  recognition = new SR();
  recognition.lang = lang;
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.onresult = (e) => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) finalTranscript += r[0].transcript + " ";
      else interim += r[0].transcript;
    }
    liveTranscript = (finalTranscript + interim).trim();
    if (liveTranscript) setTranscript("“" + liveTranscript + "”");
    else setTranscript("Listening…", true);
  };
  recognition.onerror = (e) => {
    if (e.error === "not-allowed" || e.error === "service-not-allowed") {
      setTranscript("Mic blocked — you can still capture and type your question.", true);
    }
    // "no-speech" and others: ignore; capture still works.
  };
  recognition.onend = () => {
    // Auto-restart while the window is open so a pause doesn't end listening.
    if (stream) { try { recognition.start(); } catch (_) {} }
  };
  try { recognition.start(); } catch (_) {}
}

// If the customer ALREADY typed a question in GOOPHER, we use camera ONLY (no
// mic, no speech). This is the demo-safe path: when presenting on a call (e.g.
// Google Meet), it avoids competing for the mic and prevents the popup from
// transcribing your narration as the command. With no typed question, we also
// listen so you can simply speak it.
const useVoice = !typedQuestion;

async function run() {
  retryBtn.hidden = true;
  captureBtn.disabled = true;
  finalTranscript = "";
  liveTranscript = "";
  try {
    setStatus(useVoice ? "Requesting camera & mic…" : "Requesting camera…");
    const constraints = {
      video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 960 } },
      audio: useVoice,   // only request the mic when we actually listen
    };
    stream = await navigator.mediaDevices.getUserMedia(constraints);
    // We keep the video track for the preview; the audio track was only needed
    // to grant the mic for SpeechRecognition, so stop it now.
    stream.getAudioTracks().forEach((t) => t.stop());
    video.srcObject = stream;
    await video.play().catch(() => {});
    captureBtn.disabled = false;

    if (useVoice) {
      setStatus("Point at a toy or food item, say your question, then capture.");
      setTranscript("🎤 Say your question, e.g. “place an order” or “what’s the price?”", true);
      startSpeech();
    } else {
      setStatus("Point at the item, then capture.");
      setTranscript(`Your question: “${typedQuestion}”`, false);
    }
  } catch (err) {
    const name = err?.name || String(err);
    let msg = "Camera blocked: " + name + ". Allow it in Chrome settings.";
    if (name === "NotReadableError" || name === "TrackStartError" || name === "AbortError") {
      msg = "Camera is in use by another app (e.g. Google Meet). Turn OFF your " +
            "camera there, then click Try again.";
    } else if (name === "NotAllowedError" || name === "SecurityError") {
      msg = "Camera permission denied. Allow it in Chrome settings, then Try again.";
    } else if (name === "NotFoundError") {
      msg = "No camera found on this device.";
    }
    setStatus(msg);
    retryBtn.hidden = false;
  }
}

// Capture one frame (downscaled), bundle it with the spoken/typed question.
captureBtn.addEventListener("click", () => {
  if (!stream) return;
  const vw = video.videoWidth || 1280;
  const vh = video.videoHeight || 960;
  const scale = Math.min(1, 768 / Math.max(vw, vh)); // cap longest side at 768px
  canvas.width = Math.round(vw * scale);
  canvas.height = Math.round(vh * scale);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
  const b64 = dataUrl.split(",")[1] || "";

  // A TYPED question always wins (demo-safe: your spoken narration can't
  // override it). Only when nothing was typed do we use the spoken question.
  const question = (typedQuestion || liveTranscript || "").trim();

  stopAll();
  setStatus("Sending to GOOPHER…");
  relayAndClose({
    type: "goopher_vision_image",
    image_b64: b64,
    mime_type: "image/jpeg",
    question,
    id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
  });
});

retryBtn.addEventListener("click", run);
window.addEventListener("beforeunload", stopAll);

run();
