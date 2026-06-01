// GOOPHER camera-capture popup (for the Vision subagent).
//
// Why this exists: like the microphone, a Chrome MV3 SIDE PANEL can't reliably
// prompt for camera access, but a normal extension page opened as a popup WINDOW
// can. So the side panel opens this page; we capture one frame here and relay it
// (base64 JPEG) back to the side panel via chrome.runtime messaging, which then
// POSTs it to /vision along with the customer's question.

const video = document.getElementById("preview");
const canvas = document.getElementById("canvas");
const statusEl = document.getElementById("status");
const captureBtn = document.getElementById("capture");
const retryBtn = document.getElementById("retry");

// The customer's question is passed in the query string (?q=...).
const params = new URLSearchParams(location.search);
const question = params.get("q") || "";

let stream = null;

function setStatus(msg) {
  statusEl.textContent = msg;
}

function stopStream() {
  if (stream) {
    stream.getTracks().forEach((t) => t.stop());
    stream = null;
  }
}

function relayAndClose(payload) {
  try {
    chrome.runtime.sendMessage(payload);
  } catch (_) {
    /* ignore */
  }
  setTimeout(() => window.close(), 200);
}

async function run() {
  retryBtn.hidden = true;
  captureBtn.disabled = true;
  try {
    setStatus("Requesting camera…");
    // Prefer the rear camera on phones; fall back to any camera.
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 960 } },
      audio: false,
    });
    video.srcObject = stream;
    await video.play().catch(() => {});
    setStatus("Point at a toy or food item, then capture.");
    captureBtn.disabled = false;
  } catch (err) {
    setStatus("Camera blocked: " + (err?.name || err) + ". Allow it in Chrome settings.");
    retryBtn.hidden = false;
  }
}

// Capture one frame, downscale to keep the upload small, relay as base64 JPEG.
captureBtn.addEventListener("click", () => {
  if (!stream) return;
  const vw = video.videoWidth || 1280;
  const vh = video.videoHeight || 960;
  // Cap the longest side at 768px — plenty for recognition, small over the wire.
  const scale = Math.min(1, 768 / Math.max(vw, vh));
  canvas.width = Math.round(vw * scale);
  canvas.height = Math.round(vh * scale);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
  const b64 = dataUrl.split(",")[1] || "";
  stopStream();
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
window.addEventListener("beforeunload", stopStream);

run();
