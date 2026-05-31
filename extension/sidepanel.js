// GOOPHER side panel controller: login flow, chat rendering, multi-modal
// attachments, channel/language switching, and VOICE input. Maintains a stable
// session_id so the backend memory agent preserves context across switches.
import { getCustomer, getToken, login, logout, sendChat } from "./api.js";

const els = {
  loginView: document.getElementById("loginView"),
  chatView: document.getElementById("chatView"),
  email: document.getElementById("email"),
  password: document.getElementById("password"),
  loginBtn: document.getElementById("loginBtn"),
  loginError: document.getElementById("loginError"),
  logoutBtn: document.getElementById("logoutBtn"),
  messages: document.getElementById("messages"),
  composer: document.getElementById("composer"),
  messageInput: document.getElementById("messageInput"),
  channel: document.getElementById("channel"),
  language: document.getElementById("language"),
  fileInput: document.getElementById("fileInput"),
  attachmentBar: document.getElementById("attachmentBar"),
  micBtn: document.getElementById("micBtn"),
};

// One stable session id per browser profile keeps memory/context continuous.
let sessionId = null;
let pendingAttachments = [];

async function ensureSession() {
  const o = await chrome.storage.local.get("goopher_session");
  if (o.goopher_session) {
    sessionId = o.goopher_session;
  } else {
    sessionId = "sess-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    await chrome.storage.local.set({ goopher_session: sessionId });
  }
}

// ---- message rendering ----
function addMessage(text, who, meta) {
  const div = document.createElement("div");
  div.className = `gp-msg ${who}`;
  div.textContent = text;
  if (meta) {
    const m = document.createElement("span");
    m.className = "gp-meta";
    m.textContent = meta;
    div.appendChild(m);
  }
  els.messages.appendChild(div);
  els.messages.scrollTop = els.messages.scrollHeight;
  return div;
}

function showTyping() {
  const t = document.createElement("div");
  t.className = "gp-typing";
  t.id = "typing";
  t.textContent = "GOOPHER is typing…";
  els.messages.appendChild(t);
  els.messages.scrollTop = els.messages.scrollHeight;
}
function hideTyping() {
  document.getElementById("typing")?.remove();
}

// ---- attachments (multi-modal) ----
function renderAttachments() {
  els.attachmentBar.innerHTML = "";
  pendingAttachments.forEach((a, i) => {
    const chip = document.createElement("span");
    chip.className = "gp-chip";
    chip.textContent = `${a.kind === "image" ? "🖼️" : "📄"} ${a.filename}`;
    const x = document.createElement("button");
    x.textContent = "✕";
    x.onclick = () => {
      pendingAttachments.splice(i, 1);
      renderAttachments();
    };
    chip.appendChild(x);
    els.attachmentBar.appendChild(chip);
  });
}

function fileToAttachment(file) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => {
      const b64 = reader.result.toString().split(",")[1];
      const kind = file.type.startsWith("image/")
        ? "image"
        : file.type.startsWith("audio/")
        ? "audio"
        : "file";
      resolve({ kind, filename: file.name, mime_type: file.type || "application/octet-stream", content_b64: b64 });
    };
    reader.readAsDataURL(file);
  });
}

// ---- view switching ----
async function showChat() {
  els.loginView.hidden = true;       // hide the sign-in form after login
  els.chatView.hidden = false;
  els.logoutBtn.hidden = false;
  const customer = await getCustomer();
  if (els.messages.childElementCount === 0) {
    addMessage(
      `Hi, I'm GOOPHER — your shopping agent. Ask me about products or your orders (e.g. "do you have barbecue chips?" or "where is ORD-50002?").`,
      "bot"
    );
  }
}

function showLogin() {
  els.loginView.hidden = false;
  els.chatView.hidden = true;        // hide chat while logged out
  els.logoutBtn.hidden = true;
}

// ---- core send ----
async function send(text, attachments) {
  const channel = els.channel.value;
  const language = els.language.value;

  addMessage(text || "(attachment)", "user");
  els.messageInput.value = "";
  pendingAttachments = [];
  renderAttachments();
  showTyping();

  try {
    const resp = await sendChat({ message: text, sessionId, channel, language, attachments });
    hideTyping();
    const meta = `${resp.channel} · ${resp.language}${resp.used_tools?.length ? " · " + resp.used_tools.join(",") : ""}`;
    const bubble = addMessage(resp.reply, "bot", meta);
    // On the phone channel, also speak the answer aloud (voice out).
    if (channel === "phone") speak(resp.reply, resp.language);
    return bubble;
  } catch (err) {
    hideTyping();
    if (err.message === "UNAUTHORIZED") {
      await logout();
      showLogin();
      els.loginError.textContent = "Session expired. Please sign in again.";
      els.loginError.hidden = false;
    } else {
      addMessage("⚠️ " + err.message, "bot");
    }
  }
}

// ---- voice input (Web Speech API: speech-to-text, free, built into Chrome) ----
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let listening = false;

const LANG_BCP47 = {
  en: "en-US", es: "es-ES", fr: "fr-FR", de: "de-DE",
  pt: "pt-BR", hi: "hi-IN", zh: "zh-CN",
};

// Track whether the user has granted microphone access this session, so we only
// prompt once.
let micGranted = false;

// Request microphone permission via getUserMedia. In a Chrome extension side
// panel the SpeechRecognition API will throw "not-allowed" unless the page has
// been granted mic access first — calling getUserMedia from a user gesture (the
// click) is what surfaces Chrome's permission prompt. We immediately stop the
// stream; we only needed it to trigger/confirm the grant.
async function ensureMicPermission() {
  if (micGranted) return true;
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("no-media-devices");
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  stream.getTracks().forEach((t) => t.stop());
  micGranted = true;
  return true;
}

function startRecognition() {
  recognition = new SR();
  recognition.lang = LANG_BCP47[els.language.value] || "en-US";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    listening = true;
    els.micBtn.classList.add("listening");
    els.messageInput.placeholder = "Listening… speak now";
  };
  recognition.onresult = (e) => {
    const transcript = e.results[0][0].transcript;
    els.messageInput.value = transcript;
    send(transcript.trim(), []); // auto-send the spoken question
  };
  recognition.onerror = (e) => {
    if (e.error === "not-allowed" || e.error === "service-not-allowed") {
      micGranted = false;
      addMessage(
        "🎤 Microphone access is blocked. Click the 🔒/camera icon in Chrome's " +
          "address bar (or chrome://settings/content/microphone) and allow the " +
          "microphone for this extension, then try the mic again.",
        "bot"
      );
    } else if (e.error === "no-speech") {
      addMessage("🎤 I didn't catch that — tap the mic and speak again.", "bot");
    } else {
      addMessage("🎤 Voice error: " + e.error, "bot");
    }
  };
  recognition.onend = () => {
    listening = false;
    els.micBtn.classList.remove("listening");
    els.messageInput.placeholder = "Ask about products or your orders…";
  };
  recognition.start();
}

function setupMic() {
  if (!SR) {
    // Browser without speech recognition — hide the mic gracefully.
    els.micBtn.hidden = true;
    return;
  }
  els.micBtn.addEventListener("click", async () => {
    if (listening) {
      recognition?.stop();
      return;
    }
    try {
      // Surface Chrome's mic-permission prompt (needed in the extension panel)
      // before handing off to the Speech API.
      await ensureMicPermission();
      startRecognition();
    } catch (err) {
      const name = err?.name || err?.message || "error";
      if (name === "NotAllowedError" || name === "SecurityError") {
        addMessage(
          "🎤 Microphone permission was denied. Open Chrome's site settings for " +
            "this extension and set Microphone to Allow, then click the mic again.",
          "bot"
        );
      } else if (name === "NotFoundError" || name === "no-media-devices") {
        addMessage("🎤 No microphone was found on this device.", "bot");
      } else {
        addMessage("🎤 Couldn't start voice input: " + name, "bot");
      }
    }
  });
}

// Speak a reply aloud on the phone (voice) channel.
function speak(text, language) {
  if (!window.speechSynthesis) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = LANG_BCP47[language] || "en-US";
  window.speechSynthesis.speak(u);
}

// ---- event handlers ----
els.loginBtn.addEventListener("click", async () => {
  els.loginError.hidden = true;
  try {
    await login(els.email.value.trim(), els.password.value);
    await showChat();
  } catch (e) {
    els.loginError.textContent = "Sign-in failed. Check your credentials and that the backend is running.";
    els.loginError.hidden = false;
  }
});

els.logoutBtn.addEventListener("click", async () => {
  await logout();
  els.messages.innerHTML = "";
  showLogin();
});

els.fileInput.addEventListener("change", async (e) => {
  for (const f of e.target.files) {
    pendingAttachments.push(await fileToAttachment(f));
  }
  renderAttachments();
  els.fileInput.value = "";
});

els.composer.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = els.messageInput.value.trim();
  if (!text && pendingAttachments.length === 0) return;
  await send(text, [...pendingAttachments]);
});

// ---- boot ----
(async function init() {
  await ensureSession();
  setupMic();
  const token = await getToken();
  if (token) {
    await showChat();
  } else {
    showLogin();
  }
})();
