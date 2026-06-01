// GOOPHER side panel controller: login flow, chat rendering, multi-modal
// attachments, channel/language switching, and VOICE input. Maintains a stable
// session_id so the backend memory agent preserves context across switches.
import { getCustomer, getToken, getMyOrders, login, logout, sendChat } from "./api.js";

// Version marker — confirms which build of the side panel Chrome has loaded.
// Open the side panel's DevTools console; if you don't see this line after a
// reload, Chrome is still running an old cached copy (reload the extension AND
// close/reopen the side panel).
console.log("GOOPHER side panel v0.3.0 — cart + staged checkout + orders panel");

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
  speakToggle: document.getElementById("speakToggle"),
  cartBtn: document.getElementById("cartBtn"),
  cartCount: document.getElementById("cartCount"),
  ordersPanel: document.getElementById("ordersPanel"),
  ordersList: document.getElementById("ordersList"),
  ordersClose: document.getElementById("ordersClose"),
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

const _delay = (ms) => new Promise((r) => setTimeout(r, ms));

// Build a readable cart "receipt" from the structured cart lines.
function cartText(c) {
  const lines = (c.cart && c.cart.length
    ? c.cart
    : (c.items || []).map((s) => ({ name: s, qty: 1 }))
  ).map((it) => {
    if (it.unit_price != null) {
      const opt = [it.color, it.size].filter(Boolean).join(", ");
      return `• ${it.name}${opt ? ` (${opt})` : ""} × ${it.qty}` +
        `  —  $${Number(it.unit_price).toFixed(2)} ea = $${Number(it.line_total).toFixed(2)}`;
    }
    return `• ${it.name}`;
  });
  const subtotal = c.subtotal != null ? c.subtotal : c.total;
  return `🛒 Your cart\n${lines.join("\n")}\n──────────\nSubtotal: $${Number(subtotal).toFixed(2)}`;
}

// Staged checkout confirmation shown to the customer, in order:
//   1) "🛒 Your cart"            — the item(s) added to the cart
//   2) "💳 Processing payment…"  — payment in progress
//   3) "✅ Payment successful"   — amount charged (+ txn)
//   4) "🎉 ORDER PLACED SUCCESSFULLY" (only if the backend wrote ORDER_PLACED)
async function renderCheckout(c, meta) {
  const items = (c.items || []).join("; ");

  // 1) Cart
  addMessage(cartText(c), "bot");
  await _delay(700);

  // 2) Processing payment…
  const pay = addMessage("💳 Processing payment…", "bot");
  await _delay(1100);

  // 3) Payment successful
  pay.firstChild.nodeValue = "💳 Processing payment… done.";
  addMessage(
    `✅ Payment successful — $${Number(c.total).toFixed(2)} charged` +
      (c.transaction_id ? ` (txn ${c.transaction_id}).` : "."),
    "bot"
  );
  await _delay(700);

  // 4) Order placement → ORDER PLACED
  const progress = addMessage("⏳ Order placement is in progress…", "bot");
  await _delay(1100);

  if (c.order_placed) {
    progress.firstChild.nodeValue = "⏳ Order placement is in progress… done.";
    addMessage(
      `🎉 ORDER PLACED SUCCESSFULLY\n` +
        `• Order: ${c.order_id}\n` +
        (items ? `• Item(s): ${items}\n` : "") +
        (c.tracking_number ? `• Tracking: UPS ${c.tracking_number}\n` : "") +
        (c.estimated_delivery ? `• Est. delivery: ${c.estimated_delivery}` : ""),
      "bot",
      meta
    );
  } else {
    // Payment ok but the order record wasn't confirmed — be honest about it.
    addMessage(
      `⚠️ Payment succeeded, but order placement could not be confirmed. ` +
        `Order id ${c.order_id || "—"}. Please check your orders shortly.`,
      "bot",
      meta
    );
  }
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

// ---- cart / orders panel ----
// A persistent header button (top corner) lets the customer open a panel of
// everything they've already ordered. Data comes from the authoritative
// /orders/mine endpoint, so it always reflects real placed orders.
let ordersCache = [];

function setCartBadge(n) {
  els.cartCount.textContent = String(n);
  els.cartCount.hidden = !n;
}

function renderOrders(orders) {
  els.ordersList.innerHTML = "";
  if (!orders.length) {
    els.ordersList.innerHTML =
      `<p class="gp-orders-empty">No orders yet. Try “place an order of oreo cookies”.</p>`;
    return;
  }
  for (const o of orders) {
    const items = (o.items || [])
      .map((it) => {
        const opt = [it.color, it.size].filter(Boolean).join(", ");
        return `<li>${it.name}${opt ? ` (${opt})` : ""} × ${it.qty} — $${Number(it.unit_price).toFixed(2)}</li>`;
      })
      .join("");
    const card = document.createElement("div");
    card.className = "gp-order-card";
    card.innerHTML = `
      <div class="gp-order-top">
        <span class="gp-order-id">${o.order_id}</span>
        <span class="gp-order-status">${o.status || "Processing"}</span>
      </div>
      <ul class="gp-order-items">${items}</ul>
      <div class="gp-order-foot">
        <span>Total: <b>$${Number(o.total).toFixed(2)}</b></span>
        ${o.tracking_number ? `<span>📦 ${o.carrier || "UPS"} ${o.tracking_number}</span>` : ""}
        ${o.estimated_delivery ? `<span>ETA ${o.estimated_delivery}</span>` : ""}
      </div>`;
    els.ordersList.appendChild(card);
  }
}

async function refreshOrders() {
  try {
    const data = await getMyOrders();
    ordersCache = data.orders || [];
    setCartBadge(data.count || ordersCache.length);
    return ordersCache;
  } catch (err) {
    if (err.message === "UNAUTHORIZED") { await logout(); showLogin(); }
    return ordersCache;
  }
}

async function openOrders() {
  renderOrders(await refreshOrders());
  els.ordersPanel.hidden = false;
}

function closeOrders() {
  els.ordersPanel.hidden = true;
}

function toggleOrders() {
  if (els.ordersPanel.hidden) openOrders();
  else closeOrders();
}

// ---- view switching ----
async function showChat() {
  els.loginView.hidden = true;       // hide the sign-in form after login
  els.chatView.hidden = false;
  els.logoutBtn.hidden = false;
  els.cartBtn.hidden = false;        // show the cart/orders button once signed in
  const customer = await getCustomer();
  if (els.messages.childElementCount === 0) {
    addMessage(
      `Hi, I'm GOOPHER — your shopping agent. Ask me about products or your orders (e.g. "do you have barbecue chips?" or "where is ORD-50002?").`,
      "bot"
    );
  }
  refreshOrders();                   // prime the cart badge with existing orders
}

function showLogin() {
  els.loginView.hidden = false;
  els.chatView.hidden = true;        // hide chat while logged out
  els.logoutBtn.hidden = true;
  els.cartBtn.hidden = true;
  closeOrders();
}

// ---- core send ----
// `viaVoice` is true ONLY when the question came from the microphone. We speak
// the answer aloud just for voice questions; typed questions stay text-only.
async function send(text, attachments, viaVoice = false) {
  const channel = els.channel.value;
  const language = els.language.value;

  addMessage(text || "(attachment)", "user");
  els.messageInput.value = "";
  pendingAttachments = [];
  renderAttachments();
  showTyping();

  try {
    const resp = await sendChat({ message: text, sessionId, channel, language, attachments, voice: viaVoice });
    hideTyping();
    const meta = `${resp.channel} · ${resp.language}${resp.used_tools?.length ? " · " + resp.used_tools.join(",") : ""}`;

    // Staged checkout confirmation: payment success → placement in progress →
    // ORDER PLACED SUCCESSFULLY. Shown only on a successful checkout turn.
    if (resp.checkout && resp.checkout.ok) {
      await renderCheckout(resp.checkout, meta);
      refreshOrders();   // new order placed → update the cart badge/panel
      if (viaVoice && els.speakToggle?.checked) {
        speak(`Payment successful. Order ${resp.checkout.order_id} placed successfully.`, resp.language);
      }
    } else {
      addMessage(resp.reply, "bot", meta);
      // Speak ONLY when the question was asked by voice (mic) and 🔊 is on.
      if (viaVoice && els.speakToggle?.checked) {
        speak(resp.reply, resp.language);
      }
    }
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

// ---- voice input ----
// Voice capture runs in a popup WINDOW (mic.html), NOT here, because Chrome MV3
// side panels can't reliably obtain microphone access (SpeechRecognition throws
// "not-allowed" even when the mic is allowed in Chrome settings). A normal
// extension popup window CAN get the mic; it captures speech and relays the
// transcript back via chrome.runtime messaging, which we handle below.
const LANG_BCP47 = {
  en: "en-US", es: "es-ES", fr: "fr-FR", de: "de-DE",
  pt: "pt-BR", hi: "hi-IN", zh: "zh-CN",
};
let micWindowId = null;

function setupMic() {
  if (!chrome.windows) {
    els.micBtn.hidden = true;
    return;
  }

  // Receive the transcript relayed from the mic popup, then send it as a chat.
  // De-dupe: the popup may emit more than one "final" result for one utterance,
  // and chrome.runtime broadcasts can arrive more than once — guard so a single
  // spoken question produces exactly one answer.
  let lastVoiceMsgId = null;
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg?.type === "goopher_transcript" && msg.transcript) {
      if (msg.id && msg.id === lastVoiceMsgId) return; // duplicate delivery
      lastVoiceMsgId = msg.id || null;
      els.messageInput.value = msg.transcript;
      send(msg.transcript, [], /* viaVoice */ true); // speak the answer
    }
  });

  els.micBtn.addEventListener("click", async () => {
    const langCode = LANG_BCP47[els.language.value] || "en-US";
    const url = chrome.runtime.getURL(`mic.html?lang=${encodeURIComponent(langCode)}`);

    // If a mic window is already open, just focus it.
    if (micWindowId !== null) {
      try {
        await chrome.windows.update(micWindowId, { focused: true });
        return;
      } catch (_) {
        micWindowId = null;
      }
    }
    try {
      const win = await chrome.windows.create({ url, type: "popup", width: 360, height: 260 });
      micWindowId = win.id;
    } catch (err) {
      addMessage("🎤 Couldn't open the voice window: " + (err?.message || err), "bot");
    }
  });

  if (chrome.windows?.onRemoved) {
    chrome.windows.onRemoved.addListener((closedId) => {
      if (closedId === micWindowId) micWindowId = null;
    });
  }
}

// Strip markdown so the TTS engine doesn't read "asterisk asterisk", URLs, etc.
function speechCleanup(text) {
  return text
    .replace(/\[(.*?)\]\((.*?)\)/g, "$1") // [label](url) -> label
    .replace(/[*_`#>]+/g, "")             // markdown markers
    .replace(/^\s*[-•]\s*/gm, ", ")        // bullets -> pauses
    .replace(/https?:\/\/\S+/g, "")        // bare URLs
    .replace(/\s{2,}/g, " ")
    .trim();
}

// Pick the best available voice for a language, preferring Google voices
// (Chrome ships Google's network TTS voices, e.g. "Google US English").
function pickVoice(bcp47) {
  const voices = window.speechSynthesis.getVoices() || [];
  const base = bcp47.split("-")[0];
  const byLang = voices.filter((v) => v.lang && v.lang.toLowerCase().startsWith(base));
  return (
    byLang.find((v) => /google/i.test(v.name)) || // prefer a Google voice
    byLang[0] ||
    voices.find((v) => /google/i.test(v.name)) ||
    null
  );
}

// Speak a reply aloud using the browser's (Google) text-to-speech voices.
function speak(text, language) {
  if (!window.speechSynthesis) return;
  const clean = speechCleanup(text);
  if (!clean) return;

  const bcp47 = LANG_BCP47[language] || "en-US";
  window.speechSynthesis.cancel(); // stop any in-progress utterance

  const utter = () => {
    const u = new SpeechSynthesisUtterance(clean);
    u.lang = bcp47;
    const v = pickVoice(bcp47);
    if (v) u.voice = v;
    u.rate = 1.0;
    u.pitch = 1.0;
    window.speechSynthesis.speak(u);
  };

  // Voices load asynchronously; if they aren't ready yet, wait for the event.
  if ((window.speechSynthesis.getVoices() || []).length === 0) {
    window.speechSynthesis.onvoiceschanged = () => {
      window.speechSynthesis.onvoiceschanged = null;
      utter();
    };
    // Fallback in case the event never fires.
    setTimeout(utter, 300);
  } else {
    utter();
  }
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

els.cartBtn.addEventListener("click", toggleOrders);
els.ordersClose.addEventListener("click", closeOrders);

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
