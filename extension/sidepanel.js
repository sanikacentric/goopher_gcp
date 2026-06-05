// GOOPHER side panel controller: login flow, chat rendering, multi-modal
// attachments, channel/language switching, and VOICE input. Maintains a stable
// session_id so the backend memory agent preserves context across switches.
import { criticFlag, criticHeal, getCustomer, getToken, getMyOrders, login, logout, sendAdvise, sendChat, sendVision } from "./api.js";

// Version marker — confirms which build of the side panel Chrome has loaded.
// Open the side panel's DevTools console; if you don't see this line after a
// reload, Chrome is still running an old cached copy (reload the extension AND
// close/reopen the side panel).
console.log("GOOPHER side panel v0.7.0 — RSI: 👎 Teach GOOPHER (recursive self-improvement)");

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
  camBtn: document.getElementById("camBtn"),
  adviseBtn: document.getElementById("adviseBtn"),
  speakToggle: document.getElementById("speakToggle"),
  muteBtn: document.getElementById("muteBtn"),
  cartBtn: document.getElementById("cartBtn"),
  cartCount: document.getElementById("cartCount"),
  ordersPanel: document.getElementById("ordersPanel"),
  ordersList: document.getElementById("ordersList"),
  ordersClose: document.getElementById("ordersClose"),
  phoneClock: document.getElementById("phoneClock"),
};

// Phone (Voice) channel → render the chat as a mobile-device simulator. Same
// features as Web (voice, camera, cart, orders); it's a visual skin toggled by
// the Channel selector.
function updatePhoneClock() {
  if (!els.phoneClock) return;
  const d = new Date();
  let h = d.getHours();
  const m = String(d.getMinutes()).padStart(2, "0");
  const ampm = h >= 12 ? "PM" : "AM";
  h = h % 12 || 12;
  els.phoneClock.textContent = `${h}:${m} ${ampm}`;
}
function applyChannelSkin() {
  const isPhone = els.channel.value === "phone";
  els.chatView.classList.toggle("gp-phone", isPhone);
  if (isPhone) updatePhoneClock();
}
setInterval(updatePhoneClock, 30000);

// ---- voice mute (🔊 / 🔇) ----
// The header mute button mirrors the "Speak" toggle (speakToggle stays the
// source of truth all the TTS checks already use) and stops any speech now.
function reflectMute() {
  if (!els.muteBtn) return;
  const muted = !(els.speakToggle && els.speakToggle.checked);
  els.muteBtn.textContent = muted ? "🔇" : "🔊";
  els.muteBtn.title = muted ? "Voice muted — click to unmute" : "Mute voice";
  els.muteBtn.classList.toggle("muted", muted);
}
function setMuted(muted) {
  if (els.speakToggle) els.speakToggle.checked = !muted;
  if (muted) { try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch (_) {} }
  try { chrome.storage.local.set({ goopher_muted: muted }); } catch (_) {}
  reflectMute();
}

// One stable session id per browser profile keeps memory/context continuous.
let sessionId = null;
let pendingAttachments = [];
let lastUserText = "";   // last thing the customer asked — for the RSI "teach" loop
// When a checkout preview is on screen we hold its confirm/cancel actions here,
// so that a SPOKEN or typed "yes / confirm order / cancel" resolves THAT order
// instead of being sent to the backend as a brand-new request.
let pendingConfirm = null;

// Does this short reply mean "yes, go ahead" or "no, stop"? Used only while a
// checkout preview is waiting, to interpret voice/typed confirmations.
function confirmIntent(text) {
  const t = (text || "").toLowerCase().replace(/[^a-z\s]/g, " ").replace(/\s+/g, " ").trim();
  if (!t) return null;
  const YES = ["yes", "yeah", "yep", "yup", "ya", "confirm", "confirm order", "confirm it",
    "confirm the order", "place it", "place order", "place the order", "go ahead", "sure",
    "ok", "okay", "do it", "proceed", "yes please", "yes confirm", "confirmed", "absolutely"];
  const NO = ["no", "nope", "cancel", "cancel order", "cancel it", "stop", "dont", "do not",
    "never mind", "nevermind", "no thanks", "forget it"];
  if (YES.includes(t) || /\b(yes|confirm|proceed|go ahead|place (it|the order|order))\b/.test(t)) return "yes";
  if (NO.includes(t) || /\b(no|cancel|stop|nope|never ?mind)\b/.test(t)) return "no";
  return null;
}

async function ensureSession() {
  const o = await chrome.storage.local.get("goopher_session");
  if (o.goopher_session) {
    sessionId = o.goopher_session;
  } else {
    await newSession();
  }
}

// Start a brand-new session id (a fresh conversation). Used on each sign-in so
// each new sign-in session starts clean.
async function newSession() {
  sessionId = "sess-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
  await chrome.storage.local.set({ goopher_session: sessionId });
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

// Render an agent response (from /chat OR /vision). `srcText` is the original
// order text, re-sent (with confirm) if the customer confirms a pending order.
async function deliverResponse(resp, viaVoice = false, srcText = "") {
  const meta = `${resp.channel} · ${resp.language}${resp.used_tools?.length ? " · " + resp.used_tools.join(",") : ""}`;
  if (resp.checkout && resp.checkout.pending) {
    // STEP 1: show the cart preview and ask to confirm (nothing charged yet).
    addMessage(resp.reply, "bot", meta);
    if (viaVoice && els.speakToggle?.checked) speak(resp.reply, resp.language);
    // For typed/voice orders srcText is the original message. For a VISION
    // preview srcText is empty, so fall back to the resolved order text the
    // backend carried (confirm_text) — the Confirm button re-places THAT item.
    const confirmSrc = srcText || resp.checkout.confirm_text || "";
    renderConfirmButtons(confirmSrc, viaVoice);
    return;
  }
  if (resp.checkout && resp.checkout.ok) {
    await renderCheckout(resp.checkout, meta);
    if (resp.checkout.order_id) currentIds.add(resp.checkout.order_id);  // this session
    refreshOrders();   // new order placed → update the cart badge/panel
    if (viaVoice && els.speakToggle?.checked) {
      speak(`Payment successful. Order ${resp.checkout.order_id} placed successfully.`, resp.language);
    }
  } else {
    addMessage(resp.reply, "bot", meta);
    if (viaVoice && els.speakToggle?.checked) {
      speak(resp.reply, resp.language);
    }
    addTeachRow(srcText || lastUserText, resp.reply);
  }
}

// RSI demo — a 👎 affordance under a reply. Flags the exchange, runs one
// self-improvement cycle (Gemini-as-judge writes a corrective lesson), and shows
// the lesson GOOPHER taught itself. Isolated: hits /critic/*, never /chat.
function addTeachRow(userText, replyText) {
  if (!userText || !replyText) return;
  const row = document.createElement("div");
  row.className = "gp-teach";
  const btn = document.createElement("button");
  btn.className = "gp-teach-btn";
  btn.textContent = "👎 Teach GOOPHER";
  btn.title = "Mark this answer unhelpful — the CriticAgent (RSI) will learn from it";
  const status = document.createElement("span");
  status.className = "gp-teach-status";
  row.appendChild(btn);
  row.appendChild(status);
  els.messages.appendChild(row);
  els.messages.scrollTop = els.messages.scrollHeight;

  btn.addEventListener("click", async () => {
    btn.disabled = true;
    status.textContent = " GOOPHER is reflecting…";
    try {
      const conv = `Customer: ${userText}\nGOOPHER: ${replyText}`;
      await criticFlag({ conversation_text: conv, sessionId, csat_score: 2 });
      const heal = await criticHeal();
      const lesson = heal.lessons && heal.lessons[0] && heal.lessons[0].lesson;
      btn.remove();
      status.className = "gp-teach-learned";
      status.textContent = lesson
        ? `💡 GOOPHER learned: ${lesson}`
        : "✅ Logged — GOOPHER will improve from this.";
    } catch (err) {
      status.textContent = "⚠ " + (err.message || err);
      btn.disabled = false;
    }
  });
}

// Confirm / Cancel buttons under a pending-order preview.
function renderConfirmButtons(srcText, viaVoice) {
  const row = document.createElement("div");
  row.className = "gp-confirm-row";
  const yes = document.createElement("button");
  yes.className = "gp-primary gp-confirm-yes"; yes.textContent = "✅ Confirm order";
  const no = document.createElement("button");
  no.className = "gp-confirm-no"; no.textContent = "✖ Cancel";
  row.appendChild(yes); row.appendChild(no);
  els.messages.appendChild(row);
  els.messages.scrollTop = els.messages.scrollHeight;

  // The actual confirm/cancel logic, reusable from the buttons AND from a spoken
  // or typed "yes/confirm/cancel" (see send()). `spokenAs` echoes what was said.
  const doConfirm = async (spokenAs, nowVoice) => {
    const speak = nowVoice ?? viaVoice;
    pendingConfirm = null;
    row.remove();
    addMessage(spokenAs || "✅ Yes, place the order", "user");
    showTyping();
    try {
      const resp = await sendChat({
        message: srcText, sessionId, channel: els.channel.value,
        language: els.language.value, voice: speak, confirm: true,
      });
      hideTyping();
      await deliverResponse(resp, speak, srcText);
    } catch (err) {
      hideTyping();
      addMessage("⚠️ " + err.message, "bot");
    }
  };
  const doCancel = (spokenAs) => {
    pendingConfirm = null;
    row.remove();
    if (spokenAs) addMessage(spokenAs, "user");
    addMessage("Order cancelled — nothing was charged.", "bot");
  };

  // Register as the active pending confirmation so voice/typed replies resolve it.
  pendingConfirm = { doConfirm, doCancel, srcText };

  yes.addEventListener("click", () => doConfirm());
  no.addEventListener("click", () => doCancel());
}

// ---- Shopping Advisor (explicit ReAct / PlanReActPlanner) ----
// A SEPARATE read-only agent (POST /advise) that PLANS → ACTS over tools →
// REASONS → recommends. It never places an order. We show the recommendation
// AND a collapsible "reasoning" panel with the visible ReAct plan — the demo
// showcase of explicit ReAct alongside the production function-calling agents.
async function askAdvisor(text) {
  let q = (text || "").trim();
  const auto = !q;
  if (auto) {
    // Empty tap → make a CONTEXTUAL recommendation off the customer's MOST RECENT
    // order. Don't hardcode a department/price — let the ReAct advisor read the
    // actual last order (its department AND price) and recommend accordingly
    // (e.g. last order was a $17.99 Toy → other Toys at/under ~$17.99).
    q = "Look at my MOST RECENT order. Identify its department and price, then " +
        "recommend a few other items from the SAME department priced at or below " +
        "what I just bought. Reply with a short bulleted list of product names " +
        "and prices only — no long explanation.";
  }
  addMessage(auto ? "🧠 Recommend items based on my last order" : "🧠 " + q, "user");
  els.messageInput.value = "";
  const typing = document.createElement("div");
  typing.className = "gp-typing"; typing.id = "typing";
  typing.textContent = "Advisor is reasoning (plan → act → reason)…";
  els.messages.appendChild(typing);
  els.messages.scrollTop = els.messages.scrollHeight;
  try {
    const resp = await sendAdvise({
      message: q, sessionId, channel: els.channel.value, language: els.language.value,
    });
    hideTyping();
    const meta = `🧠 ReAct · ${resp.engine || "advisor"}${resp.used_tools?.length ? " · " + resp.used_tools.join(",") : ""}`;
    addMessage(resp.reply, "bot", meta);
    if (resp.plan) renderReactPlan(resp.plan);
  } catch (err) {
    hideTyping();
    if (err.message === "UNAUTHORIZED") { await logout(); showLogin(); return; }
    addMessage("⚠️ Advisor error: " + err.message, "bot");
  }
}

// Render the visible ReAct trace as a collapsible "reasoning" card.
function renderReactPlan(planText) {
  const d = document.createElement("details");
  d.className = "gp-react";
  const s = document.createElement("summary");
  s.textContent = "🧠 How GOOPHER reasoned (ReAct plan)";
  const pre = document.createElement("pre");
  pre.className = "gp-react-plan";
  pre.textContent = planText;
  d.appendChild(s); d.appendChild(pre);
  els.messages.appendChild(d);
  els.messages.scrollTop = els.messages.scrollHeight;
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
// /orders/mine returns the customer's FULL history (persisted). We split it into
// two sections so a fresh sign-in is clean:
//   • Current orders — placed in THIS sign-in session (the badge counts these)
//   • Order history — orders that already existed at sign-in (previous sessions)
let ordersCache = [];
let currentIds = new Set();   // order ids placed in THIS sign-in session

function setCartBadge(n) {
  els.cartCount.textContent = String(n);
  els.cartCount.hidden = !n;
}

// Reset so this sign-in session starts at 0 current orders (everything already
// in the account becomes "history").
function startFreshOrders() { currentIds = new Set(); }

function orderCard(o) {
  const items = (o.items || [])
    .map((it) => {
      const opt = [it.color, it.size].filter(Boolean).join(", ");
      return `<li>${it.name}${opt ? ` (${opt})` : ""} × ${it.qty} — $${Number(it.unit_price).toFixed(2)}</li>`;
    })
    .join("");
  return `
    <div class="gp-order-card">
      <div class="gp-order-top">
        <span class="gp-order-id">${o.order_id}</span>
        <span class="gp-order-status">${o.status || "Processing"}</span>
      </div>
      <ul class="gp-order-items">${items}</ul>
      <div class="gp-order-foot">
        <span>Total: <b>$${Number(o.total).toFixed(2)}</b></span>
        ${o.tracking_number ? `<span>📦 ${o.carrier || "UPS"} ${o.tracking_number}</span>` : ""}
        ${o.estimated_delivery ? `<span>ETA ${o.estimated_delivery}</span>` : ""}
      </div>
    </div>`;
}

function renderOrders(orders) {
  const current = orders.filter((o) => currentIds.has(o.order_id));
  const history = orders.filter((o) => !currentIds.has(o.order_id));
  let html = `<div class="gp-order-section">🛒 Current orders <span class="gp-sec-count">this session</span></div>`;
  html += current.length
    ? current.map(orderCard).join("")
    : `<p class="gp-orders-empty">No orders yet this session. Try “place an order of oreo cookies”.</p>`;
  if (history.length) {
    html += `<div class="gp-order-section gp-order-section-hist">🧾 Order history <span class="gp-sec-count">${history.length} previous</span></div>`;
    html += history.map(orderCard).join("");
  }
  els.ordersList.innerHTML = html;
}

async function refreshOrders() {
  try {
    const data = await getMyOrders();
    ordersCache = data.orders || [];
    setCartBadge(currentIds.size);   // badge = THIS session's orders only
    renderOrders(ordersCache);
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
  if (els.muteBtn) {
    els.muteBtn.hidden = false;      // show the mute button once signed in
    try {
      const o = await chrome.storage.local.get("goopher_muted");
      if (els.speakToggle) els.speakToggle.checked = !o.goopher_muted;
    } catch (_) {}
    reflectMute();
  }
  applyChannelSkin();                // honor the current channel (phone vs web)
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
  if (els.muteBtn) els.muteBtn.hidden = true;
  closeOrders();
}

// ---- core send ----
// `viaVoice` is true ONLY when the question came from the microphone. We speak
// the answer aloud just for voice questions; typed questions stay text-only.
async function send(text, attachments, viaVoice = false) {
  const channel = els.channel.value;
  const language = els.language.value;

  // If a checkout preview is waiting, interpret "yes/confirm/cancel" (spoken or
  // typed) as resolving THAT order — don't send it to the backend as a new turn.
  if (pendingConfirm && (!attachments || attachments.length === 0)) {
    const intent = confirmIntent(text);
    if (intent === "yes") { await pendingConfirm.doConfirm(text, viaVoice); return; }
    if (intent === "no")  { pendingConfirm.doCancel(text); return; }
    // Anything else cancels the pending preview and proceeds as a normal request.
    pendingConfirm = null;
  }

  addMessage(text || "(attachment)", "user");
  lastUserText = text || "(attachment)";
  els.messageInput.value = "";
  pendingAttachments = [];
  renderAttachments();
  showTyping();

  try {
    const resp = await sendChat({ message: text, sessionId, channel, language, attachments, voice: viaVoice });
    hideTyping();
    await deliverResponse(resp, viaVoice, text);   // text re-sent if they confirm
  } catch (err) {
    hideTyping();
    if (err.message === "UNAUTHORIZED") {
      await logout();
      showLogin();
      els.loginError.textContent = "Session expired. Please sign in again.";
      els.loginError.hidden = false;
    } else if (/failed to fetch|network/i.test(err.message)) {
      addMessage(
        "⚠️ Couldn't reach GOOPHER. If you attached a large file/photo, try a " +
          "smaller one; otherwise the service may be waking up — please send again.",
        "bot"
      );
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
    // Stop any answer still being read aloud, so it can't echo into the mic and
    // garble/drop the recognition before you even start talking.
    try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch (_) {}
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

// ---- camera input (Vision subagent) ----
// Like the mic, camera capture runs in a popup WINDOW (camera.html) because MV3
// side panels can't reliably prompt for camera access. The popup relays a single
// JPEG frame back here; we POST it to /vision with the customer's question.
let camWindowId = null;

function setupCamera() {
  if (!chrome.windows || !els.camBtn) {
    if (els.camBtn) els.camBtn.hidden = true;
    return;
  }

  let lastVisionId = null;
  chrome.runtime.onMessage.addListener(async (msg) => {
    if (msg?.type !== "goopher_vision_image" || !msg.image_b64) return;
    if (msg.id && msg.id === lastVisionId) return; // de-dupe broadcast
    lastVisionId = msg.id || null;

    const question = (msg.question || "").trim();
    const viaVoice = !!msg.via_voice;   // spoken question → speak the answer
    // Show exactly what the customer said/typed — don't fabricate a question.
    // With nothing given, the backend defaults to "identify + price".
    addMessage(question ? `📷 ${question}` : "📷 (sent a photo)", "user");
    showTyping();
    try {
      const resp = await sendVision({
        question,
        image_b64: msg.image_b64,
        mime_type: msg.mime_type || "image/jpeg",
        sessionId,
        channel: els.channel.value,
        language: els.language.value,
      });
      hideTyping();
      await deliverResponse(resp, viaVoice);
    } catch (err) {
      hideTyping();
      if (err.message === "UNAUTHORIZED") { await logout(); showLogin(); }
      else addMessage("📷 " + err.message, "bot");
    }
  });

  els.camBtn.addEventListener("click", async () => {
    try { window.speechSynthesis && window.speechSynthesis.cancel(); } catch (_) {}
    // The customer can SPEAK the question in the camera window; whatever they
    // typed here is passed as a fallback. Pass the speech language too.
    const q = els.messageInput.value.trim();
    const langCode = LANG_BCP47[els.language.value] || "en-US";
    const url = chrome.runtime.getURL(
      `camera.html?q=${encodeURIComponent(q)}&lang=${encodeURIComponent(langCode)}`);
    if (camWindowId !== null) {
      try { await chrome.windows.update(camWindowId, { focused: true }); return; }
      catch (_) { camWindowId = null; }
    }
    try {
      const win = await chrome.windows.create({ url, type: "popup", width: 420, height: 520 });
      camWindowId = win.id;
    } catch (err) {
      addMessage("📷 Couldn't open the camera window: " + (err?.message || err), "bot");
    }
  });

  if (chrome.windows?.onRemoved) {
    chrome.windows.onRemoved.addListener((closedId) => {
      if (closedId === camWindowId) camWindowId = null;
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
    // Fresh start for each new sign-in session: new conversation, cleared chat,
    // and a refreshed cart (showChat re-fetches /orders/mine for this customer).
    await newSession();
    els.messages.innerHTML = "";
    startFreshOrders();       // this session's "current orders" start empty
    setCartBadge(0);
    closeOrders();
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

// 🧠 Shopping Advisor (ReAct) — routes the current input to /advise instead of
// /chat, so it never places an order; it recommends and shows its reasoning.
if (els.adviseBtn) els.adviseBtn.addEventListener("click", () => askAdvisor(els.messageInput.value));

// Mute button toggles voice (and stops any current speech). The Speak checkbox
// stays in sync either way.
if (els.muteBtn) els.muteBtn.addEventListener("click", () =>
  setMuted(els.speakToggle ? els.speakToggle.checked : false));
if (els.speakToggle) els.speakToggle.addEventListener("change", () => setMuted(!els.speakToggle.checked));

// Channel switch → toggle the phone simulator skin (Phone vs Web).
els.channel.addEventListener("change", applyChannelSkin);

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
  setupCamera();
  const token = await getToken();
  if (token) {
    await showChat();
  } else {
    showLogin();
  }
})();
