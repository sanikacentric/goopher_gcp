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

export async function sendChat({ message, sessionId, channel, language, attachments, voice }) {
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
      attachments: attachments || [],
    }),
  });
  if (res.status === 401) throw new Error("UNAUTHORIZED");
  if (!res.ok) throw new Error(`Server error ${res.status}`);
  return res.json();
}
