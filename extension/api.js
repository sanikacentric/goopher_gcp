// Thin API client for the GOOPHER backend. Handles auth token storage and the
// chat / bulk-order calls. Token is kept in chrome.storage.local.
import { CONFIG } from "./config.js";

const TOKEN_KEY = "goopher_token";
const CUSTOMER_KEY = "goopher_customer";

export async function getToken() {
  const o = await chrome.storage.local.get(TOKEN_KEY);
  return o[TOKEN_KEY] || null;
}

export async function getCustomer() {
  const o = await chrome.storage.local.get(CUSTOMER_KEY);
  return o[CUSTOMER_KEY] || null;
}

export async function login(email, password) {
  const res = await fetch(`${CONFIG.API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error("Invalid credentials");
  const data = await res.json();
  await chrome.storage.local.set({
    [TOKEN_KEY]: data.access_token,
    [CUSTOMER_KEY]: data.customer,
  });
  return data.customer;
}

export async function logout() {
  await chrome.storage.local.remove([TOKEN_KEY, CUSTOMER_KEY]);
}

export async function sendChat({ message, sessionId, channel, language, attachments, voice, confirm }) {
  const token = await getToken();
  const res = await fetch(`${CONFIG.API_BASE}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      channel,
      language: language || null,
      voice: !!voice,
      confirm: !!confirm,
      attachments: attachments || [],
    }),
  });
  if (res.status === 401) throw new Error("UNAUTHORIZED");
  if (!res.ok) throw new Error(`Server error ${res.status}`);
  return res.json();
}

// Vision subagent: send a captured camera frame + the customer's question to
// the dedicated /vision endpoint. Returns the same shape as a chat response
// (reply + optional checkout), so the side panel renders it identically.
export async function sendVision({ question, image_b64, mime_type, sessionId, channel, language }) {
  const token = await getToken();
  const res = await fetch(`${CONFIG.API_BASE}/vision`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      question: question || "",
      image_b64,
      mime_type: mime_type || "image/jpeg",
      session_id: sessionId,
      channel,
      language: language || null,
    }),
  });
  if (res.status === 401) throw new Error("UNAUTHORIZED");
  if (!res.ok) throw new Error(`Server error ${res.status}`);
  return res.json();
}

// Shopping-Advisor subagent (explicit ReAct / PlanReActPlanner). Returns
// { reply, plan, used_tools, engine } — `plan` is the visible PLAN -> ACTION ->
// REASONING trace we show in the "watch GOOPHER reason" panel. Read-only: never
// places an order. Separate endpoint so the main chat flow is untouched.
export async function sendAdvise({ message, sessionId, channel, language }) {
  const token = await getToken();
  const res = await fetch(`${CONFIG.API_BASE}/advise`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      channel,
      language: language || null,
    }),
  });
  if (res.status === 401) throw new Error("UNAUTHORIZED");
  if (!res.ok) throw new Error(`Server error ${res.status}`);
  return res.json();
}

// The signed-in customer's orders — backs the header cart/orders panel.
export async function getMyOrders() {
  const token = await getToken();
  const res = await fetch(`${CONFIG.API_BASE}/orders/mine`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 401) throw new Error("UNAUTHORIZED");
  if (!res.ok) throw new Error(`Server error ${res.status}`);
  return res.json();
}
