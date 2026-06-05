/* GOOPHER — Business Case deck (9 slides): current state → problem → requirements
   → GOOPHER solution → ROI → pilot. Maps to the Applied-AI CE prompt's "current
   technical blocker" framing. Outputs ../BUSINESS-CASE.pptx. */
const pptx = require("pptxgenjs");
const p = new pptx();

const QA = !!process.env.QA;
const PW = 13.333, PH = 7.5;
let _slideNo = 0, _issues = [], _refs = [];
const _txt = (t) => typeof t === "string" ? t : Array.isArray(t) ? t.map(r => (r && r.text) || "").join("") : "";
{
  const orig = p.addSlide.bind(p);
  p.addSlide = function (...a) {
    const s = orig(...a); _slideNo += 1; const num = _slideNo; s.__n = num;
    if (QA) {
      s.__t = []; _refs.push(s);
      const wrap = (fn, k) => { const o2 = s[fn].bind(s); s[fn] = function (arg, opts) {
        const o = k === "text" ? (opts || {}) : (arg || {}); const { x = 0, y = 0, w = 0, h = 0 } = o; const e = 0.02;
        if (x < -e || y < -e || x + w > PW + e || y + h > PH + e) _issues.push(`S${num} ${k} OOB x=${x} y=${y} w=${w} h=${h} ${k === "text" ? '"' + _txt(arg).slice(0, 36) + '"' : ""}`);
        if (k === "text") s.__t.push(_txt(arg)); return o2(arg, opts); }; };
      wrap("addText", "text"); wrap("addShape", "shape"); wrap("addImage", "image");
    }
    return s;
  };
}

p.defineLayout({ name: "W", width: 13.333, height: 7.5 });
p.layout = "W";
p.author = "GOOPHER — Applied AI CE";
p.title = "GOOPHER — Business Case";

const C = { dark: "0A0E1F", ink: "0F172A", muted: "5B6577", soft: "8A94A6", panel: "F5F6FB",
  border: "E6E8F0", white: "FFFFFF", violet: "7C3AED", rose: "E11D48", teal: "0D9488",
  blue: "2563EB", amber: "F59E0B", green: "16A34A" };
const M = 0.55, CW = PW - 2 * M, HF = "Georgia", BF = "Calibri";
const shadow = () => ({ type: "outer", color: "0F172A", blur: 9, offset: 3, angle: 135, opacity: 0.16 });
const ic = (n) => `icons/${n}.png`;

function kicker(s, t, c = C.violet) { s.addText(t.toUpperCase(), { x: M, y: 0.5, w: CW, h: 0.3, margin: 0, fontFace: BF, fontSize: 12, bold: true, color: c, charSpacing: 3 }); }
function title(s, t, c = C.ink) { s.addText(t, { x: M, y: 0.82, w: CW, h: 1.0, margin: 0, fontFace: HF, fontSize: 27, bold: true, color: c, valign: "top" }); }
function footer(s, label) {
  s.addText(label || "GOOPHER · Business case — unblocking modern self-service", { x: M, y: 7.06, w: 10, h: 0.3, margin: 0, fontFace: BF, fontSize: 9, color: C.soft });
  s.addText(String(s.__n), { x: PW - 1.0, y: 7.06, w: 0.45, h: 0.3, margin: 0, align: "right", fontFace: BF, fontSize: 9, color: C.soft });
}
const light = (s) => { s.background = { color: C.white }; };

// card with icon chip + head + body lines
function card(s, o) {
  const { x, y, w, h, icon, chip = C.violet, head, lines = [], headSize = 14, bodySize = 11.5, headColor = C.ink } = o;
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.09, fill: { color: C.white }, line: { color: C.border, width: 1 }, shadow: shadow() });
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: x + 0.24, y: y + 0.22, w: 0.56, h: 0.56, rectRadius: 0.11, fill: { color: chip } });
  s.addImage({ path: ic(icon + "W"), x: x + 0.38, y: y + 0.36, w: 0.28, h: 0.28 });
  s.addText(head, { x: x + 0.92, y: y + 0.2, w: w - 1.1, h: 0.58, margin: 0, fontFace: BF, fontSize: headSize, bold: true, color: headColor, valign: "middle" });
  if (lines.length) s.addText(lines.map(t => ({ text: t, options: { bullet: { indent: 10 }, breakLine: true, paraSpaceAfter: 3 } })),
    { x: x + 0.26, y: y + 0.86, w: w - 0.5, h: h - 0.96, margin: 0, fontFace: BF, fontSize: bodySize, color: C.muted, valign: "top" });
}
function stat(s, o) {
  const { x, y, w, h = 1.7, num, label, color = C.violet } = o;
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.09, fill: { color: C.white }, line: { color: C.border, width: 1 }, shadow: shadow() });
  s.addText(num, { x: x + 0.1, y: y + 0.2, w: w - 0.2, h: 0.8, margin: 0, align: "center", fontFace: HF, fontSize: 36, bold: true, color });
  s.addText(label, { x: x + 0.16, y: y + 1.0, w: w - 0.32, h: h - 1.06, margin: 0, align: "center", valign: "top", fontFace: BF, fontSize: 11, color: C.muted });
}
// labelled box for diagrams
function box(s, o) {
  const { x, y, w, h, color, head, sub, icon, fill = C.white, headColor = C.ink } = o;
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color, width: 1.5 }, shadow: shadow() });
  if (icon) { s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: x + 0.16, y: y + (h - 0.46) / 2, w: 0.46, h: 0.46, rectRadius: 0.1, fill: { color } });
    s.addImage({ path: ic(icon + "W"), x: x + 0.27, y: y + (h - 0.46) / 2 + 0.11, w: 0.24, h: 0.24 }); }
  const tx = x + (icon ? 0.74 : 0.18);
  s.addText(head, { x: tx, y: y + 0.12, w: x + w - tx - 0.14, h: 0.32, margin: 0, fontFace: BF, fontSize: 12.5, bold: true, color: headColor });
  if (sub) s.addText(sub, { x: tx, y: y + 0.42, w: x + w - tx - 0.14, h: h - 0.5, margin: 0, fontFace: BF, fontSize: 10, color: C.muted, valign: "top" });
}
const arrow = (s, x, y) => s.addImage({ path: ic("arrow"), x, y, w: 0.3, h: 0.3 });

// ============================================================ 1. CURRENT ARCH
(() => {
  const s = p.addSlide(); light(s);
  kicker(s, "The customer's situation today", C.rose);
  title(s, "Current architecture — fragmented, rule-based self-service");
  s.addText("A global retailer's self-service is a set of disconnected, scripted systems — they can answer FAQs, but can't reliably help (or transact) across channels and languages.",
    { x: M, y: 1.72, w: CW, h: 0.5, margin: 0, fontFace: BF, fontSize: 12.5, color: C.muted });

  // channel boxes
  box(s, { x: M, y: 2.4, w: 3.3, h: 1.0, color: C.muted, icon: "phone", head: "Phone", sub: "IVR / DTMF menu tree (“press 1…”)" });
  box(s, { x: M, y: 3.6, w: 3.3, h: 1.0, color: C.muted, icon: "comments", head: "Web", sub: "rule-based / keyword chatbot (decision tree)" });
  arrow(s, M + 3.4, 3.15); arrow(s, M + 3.4, 3.75);
  // brittle logic
  box(s, { x: M + 3.85, y: 2.95, w: 3.0, h: 1.1, color: C.amber, icon: "cog", head: "Scripted rules / FAQ", sub: "read-only · breaks off-script · no memory" });
  arrow(s, M + 6.95, 3.35);
  // human agents
  box(s, { x: M + 7.4, y: 2.95, w: CW - 7.4, h: 1.1, color: C.rose, icon: "users", head: "Escalate → call-center agents", sub: "high cost · queues · after-hours gaps" });

  // siloed backend
  s.addText("Backend systems — siloed, not wired to the bots:", { x: M, y: 4.85, w: CW, h: 0.3, margin: 0, fontFace: BF, fontSize: 11.5, bold: true, color: C.ink });
  const sys = [["server", "Order Mgmt (OMS)"], ["db", "Inventory"], ["users", "CRM"]];
  const bw = 2.6;
  sys.forEach(([i, t], k) => box(s, { x: M + k * (bw + 0.3), y: 5.18, w: bw, h: 0.7, color: C.muted, icon: i, head: t, sub: "" }));
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: M + 3 * (bw + 0.3) + 0.0, y: 5.18, w: CW - 3 * (bw + 0.3), h: 0.7, rectRadius: 0.08, fill: { color: C.panel }, line: { color: C.border, width: 1 } });
  s.addText("English-only · no cross-channel context · can't take action", { x: M + 3 * (bw + 0.3) + 0.18, y: 5.18, w: CW - 3 * (bw + 0.3) - 0.3, h: 0.7, margin: 0, valign: "middle", fontFace: BF, fontSize: 10.5, italic: true, color: C.muted });

  s.addText("Net effect: the bot deflects the easy FAQs and dumps everything else on live agents.",
    { x: M, y: 6.15, w: CW, h: 0.4, margin: 0, fontFace: BF, fontSize: 12, italic: true, bold: true, color: C.ink, align: "center" });
  footer(s);
})();

// ====================================================== 2. ISSUES & CHALLENGES
(() => {
  const s = p.addSlide(); light(s);
  kicker(s, "Why the status quo fails", C.rose);
  title(s, "Issues & challenges with the current self-service");
  const items = [
    ["warn", "Rigid decision trees", ["Any off-script phrasing → dead-ends and “I didn't understand.”"]],
    ["times", "No context across channels", ["Web → phone restarts from scratch; the customer repeats themselves."]],
    ["globe", "English-only", ["Underserves a diverse, global base; no real NLU for other languages."]],
    ["ban", "Read-only — can't act", ["Can't check live inventory or place/track orders → escalate."]],
    ["wrench", "Brittle & costly to scale", ["Per-market chatbots and hand-written rules; slow, expensive to maintain."]],
    ["layers", "Single modality", ["No voice NLU, no images/files — text-only, scripted."]],
  ];
  const w = (CW - 0.6) / 3, h = 2.2;
  items.forEach(([icon, head, lines], i) => card(s, { x: M + (i % 3) * (w + 0.3), y: 1.95 + Math.floor(i / 3) * (h + 0.3), w, h, icon, chip: C.rose, head, lines, headSize: 13.5 }));
  footer(s);
})();

// ========================================================== 3. BUSINESS IMPACT
(() => {
  const s = p.addSlide(); light(s);
  kicker(s, "What it costs the business", C.rose);
  title(s, "Business impact of the current state");
  stat(s, { x: M, y: 1.95, w: 2.86, num: "~70%", label: "abandon after a poor self-service experience (industry)", color: C.rose });
  stat(s, { x: M + 3.06, y: 1.95, w: 2.86, num: "$1–12", label: "per live-agent contact vs cents for self-service", color: C.amber });
  stat(s, { x: M + 6.12, y: 1.95, w: 2.86, num: "Low", label: "containment → escalation overflow & long queues", color: C.rose });
  stat(s, { x: M + 9.18, y: 1.95, w: CW - 9.18, num: "Slow", label: "per-market rebuilds delay global expansion", color: C.amber });

  const levers = [
    ["dollar", "Lost sales", "Shoppers who can't get help abandon the cart and don't come back."],
    ["frown", "Low CSAT & churn", "Frustrating, English-only bot → poor experience, especially abroad."],
    ["users", "High cost-to-serve", "Mis-deflected contacts flood expensive live-agent queues."],
    ["clock", "Slow to expand", "Each new language/market means rebuilding brittle chatbots."],
  ];
  const w = (CW - 0.6) / 2, h = 1.35;
  levers.forEach(([icon, head, body], i) => {
    const x = M + (i % 2) * (w + 0.6), y = 4.0 + Math.floor(i / 2) * (h + 0.22);
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: C.panel }, line: { color: C.border, width: 1 } });
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: x + 0.22, y: y + 0.36, w: 0.6, h: 0.6, rectRadius: 0.12, fill: { color: C.rose } });
    s.addImage({ path: ic(icon + "W"), x: x + 0.37, y: y + 0.51, w: 0.3, h: 0.3 });
    s.addText(head, { x: x + 1.0, y: y + 0.2, w: w - 1.2, h: 0.4, margin: 0, fontFace: BF, fontSize: 14.5, bold: true, color: C.ink });
    s.addText(body, { x: x + 1.0, y: y + 0.6, w: w - 1.2, h: 0.66, margin: 0, fontFace: BF, fontSize: 11.5, color: C.muted, valign: "top" });
  });
  s.addText("Figures are illustrative industry benchmarks — actuals confirmed in discovery.", { x: M, y: 6.86, w: CW, h: 0.25, margin: 0, fontFace: BF, fontSize: 9, italic: true, color: C.soft });
  footer(s);
})();

// ============================================================ 4. DOWNTIME/LOSS
(() => {
  const s = p.addSlide(); light(s);
  kicker(s, "The cost of inaction", C.rose);
  title(s, "Downtime & loss — the price of the status quo");
  s.addText("Every contact the bot can't resolve is an escalation cost or a lost sale. An illustrative annual model (actuals confirmed in discovery):",
    { x: M, y: 1.72, w: CW, h: 0.5, margin: 0, fontFace: BF, fontSize: 12.5, color: C.muted });

  // worked model card (left)
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: M, y: 2.35, w: 7.1, h: 3.5, rectRadius: 0.09, fill: { color: C.dark }, shadow: shadow() });
  s.addText("ILLUSTRATIVE ANNUAL LOSS MODEL", { x: M + 0.3, y: 2.55, w: 6.5, h: 0.3, margin: 0, fontFace: BF, fontSize: 11.5, bold: true, color: "FCA5C0", charSpacing: 2 });
  const rows = [
    ["Self-service contacts / year", "5,000,000"],
    ["× share that fail / mis-route (low containment)", "× 40%"],
    ["× avg cost of an escalated live-agent contact", "× $8"],
    ["= avoidable service cost / year", "$16.0 M"],
    ["+ abandoned shoppers (no help) → lost GMV", "$ millions"],
  ];
  let y = 3.0;
  rows.forEach(([l, v], i) => {
    const strong = i >= 3;
    s.addText(l, { x: M + 0.3, y, w: 4.9, h: 0.42, margin: 0, fontFace: BF, fontSize: 12, color: strong ? "FFFFFF" : "D7D3EC", bold: strong, valign: "middle" });
    s.addText(v, { x: M + 5.2, y, w: 1.6, h: 0.42, margin: 0, align: "right", fontFace: HF, fontSize: strong ? 15 : 12.5, bold: true, color: strong ? "FCA5C0" : "FFFFFF", valign: "middle" });
    y += 0.5;
  });

  // big number + drivers (right)
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: 7.85, y: 2.35, w: CW - 7.3, h: 1.55, rectRadius: 0.09, fill: { color: C.white }, line: { color: C.rose, width: 1.5 }, shadow: shadow() });
  s.addImage({ path: ic("down"), x: 8.1, y: 2.7, w: 0.5, h: 0.5 });
  s.addText("$16M+/yr", { x: 8.7, y: 2.55, w: 4.0, h: 0.6, margin: 0, fontFace: HF, fontSize: 34, bold: true, color: C.rose });
  s.addText("avoidable cost, before counting lost revenue", { x: 8.1, y: 3.35, w: CW - 7.6, h: 0.45, margin: 0, fontFace: BF, fontSize: 11, color: C.muted });

  const drivers = [
    ["clock", "After-hours & peak gaps", "no 24/7 help → abandoned contacts at the worst times"],
    ["frown", "Repeat contacts", "unresolved issues come back 2–3× — re-work"],
    ["globe", "Underserved markets", "non-English shoppers can't self-serve at all"],
  ];
  let dy = 4.1;
  drivers.forEach(([i, h, b]) => {
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: 7.85, y: dy, w: CW - 7.3, h: 0.85, rectRadius: 0.08, fill: { color: C.panel }, line: { color: C.border, width: 1 } });
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: 8.05, y: dy + 0.18, w: 0.5, h: 0.5, rectRadius: 0.1, fill: { color: C.rose } });
    s.addImage({ path: ic(i + "W"), x: 8.17, y: dy + 0.3, w: 0.26, h: 0.26 });
    s.addText(h, { x: 8.7, y: dy + 0.12, w: CW - 7.95, h: 0.3, margin: 0, fontFace: BF, fontSize: 12, bold: true, color: C.ink });
    s.addText(b, { x: 8.7, y: dy + 0.42, w: CW - 7.95, h: 0.4, margin: 0, fontFace: BF, fontSize: 10, color: C.muted, valign: "top" });
    dy += 0.95;
  });
  s.addText("Illustrative model for framing — we instrument the real numbers in the pilot.", { x: M, y: 6.86, w: CW, h: 0.25, margin: 0, fontFace: BF, fontSize: 9, italic: true, color: C.soft });
  footer(s);
})();

// ========================================================== 5. REQUIREMENTS
(() => {
  const s = p.addSlide(); light(s);
  kicker(s, "What good looks like (the required deliverable)", C.blue);
  title(s, "The requirement — a unified conversational agent");
  // the core deliverable banner
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: M, y: 1.85, w: CW, h: 1.0, rectRadius: 0.09, fill: { color: C.dark }, shadow: shadow() });
  s.addImage({ path: ic("flagW"), x: M + 0.3, y: 2.12, w: 0.46, h: 0.46 });
  s.addText([
    { text: "Core deliverable:  ", options: { bold: true, color: "FCA5C0" } },
    { text: "a unified conversational agent prototype with backend tool(s) that integrate a ", options: { color: "FFFFFF" } },
    { text: "mock retail database for real-time inventory / order status", options: { bold: true, color: "FFFFFF" } },
    { text: " — one agent that answers AND acts.", options: { color: "D7D3EC" } },
  ], { x: M + 0.95, y: 1.85, w: CW - 1.2, h: 1.0, margin: 0, valign: "middle", fontFace: BF, fontSize: 13.5 });

  s.addText("…and extensible to four capabilities:", { x: M, y: 3.05, w: CW, h: 0.3, margin: 0, fontFace: BF, fontSize: 12.5, bold: true, color: C.ink });
  const reqs = [
    ["sitemap", C.blue, "Sub-agents + context", ["specialists for inventory / orders / checkout, with context kept when switching between them"]],
    ["globe", C.violet, "Multi-lingual", ["a diverse, global customer base served in their own language"]],
    ["mobile", C.teal, "Multi-channel", ["phone, web, and beyond — one experience across channels"]],
    ["layers", C.amber, "Multi-modal", ["text, voice, images, and files — not just typed chat"]],
  ];
  const w = (CW - 0.9) / 4, h = 2.7;
  reqs.forEach(([icon, chip, head, lines], i) => card(s, { x: M + i * (w + 0.3), y: 3.45, w, h, icon, chip, head, lines, headSize: 13.5, bodySize: 11.5 }));
  footer(s);
})();

// ====================================================== 6. PROPOSED ARCH (GOOPHER)
(() => {
  const s = p.addSlide(); light(s);
  kicker(s, "The solution", C.violet);
  title(s, "Proposed architecture — GOOPHER, a unified agent on Google Cloud");

  const row = (x, y, w, h, color, head, sub, icon) => box(s, { x, y, w, h, color, head, sub, icon });
  // lane 1
  row(M, 1.85, 3.5, 1.0, C.violet, "Channels — one agent", "web · phone (voice) · camera · file", "comments");
  arrow(s, M + 3.58, 2.2);
  row(M + 3.95, 1.85, 3.3, 1.0, C.muted, "Cloud Run · FastAPI", "auth (JWT) · rate/size limits", "cloud");
  arrow(s, M + 7.32, 2.2);
  row(M + 7.7, 1.85, CW - 7.7, 1.0, C.amber, "ROOT orchestrator (ADK)", "Gemini 2.5 Flash · Vertex AI", "robot");
  // pre-process strip
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: M, y: 3.0, w: CW, h: 0.55, rectRadius: 0.07, fill: { color: C.panel }, line: { color: C.border, width: 1 } });
  s.addText([{ text: "Deterministic pre-process (no LLM):  ", options: { bold: true, color: C.ink } }, { text: "modality · language · channel · memory (session_id) → Agent Harness", options: { color: C.muted } }],
    { x: M + 0.22, y: 3.0, w: CW - 0.4, h: 0.55, margin: 0, valign: "middle", fontFace: BF, fontSize: 11.5 });
  // workers
  s.addText("Worker sub-agents (agent-as-tool) → pick a registry skill → call tools", { x: M, y: 3.68, w: CW, h: 0.28, margin: 0, fontFace: BF, fontSize: 11.5, bold: true, color: C.blue });
  const wk = [["inventory_agent", C.blue, "sitemap"], ["order_agent", C.blue, "route"], ["checkout_agent", C.teal, "lock"], ["order_mgmt_agent", C.teal, "cog"]];
  const ww = (CW - 0.9) / 4;
  wk.forEach(([h, col, icon], i) => box(s, { x: M + i * (ww + 0.3), y: 4.0, w: ww, h: 0.9, color: col, head: h, sub: "", icon }));
  // data + cross-cutting
  row(M, 5.05, 4.1, 1.0, C.teal, "Mock retail DB (Firestore)", "catalog · orders · ORDER_PLACED", "db");
  row(M + 4.35, 5.05, 4.1, 1.0, C.violet, "Deterministic gate", "cart → payment → ORDER_PLACED", "lock");
  row(M + 8.7, 5.05, CW - 8.7, 1.0, C.rose, "Guardian · RSI · /dev", "self-heal · self-improve · observe", "shield");
  s.addText("LLM orchestrates & converses;  deterministic code transacts  —  safe, observable, self-healing & self-improving.",
    { x: M, y: 6.2, w: CW, h: 0.4, margin: 0, align: "center", fontFace: BF, fontSize: 12, italic: true, bold: true, color: C.ink });
  footer(s);
})();

// ====================================================== 7. CHALLENGES (GOOPHER)
(() => {
  const s = p.addSlide(); light(s);
  kicker(s, "Risks for the new design — and how we manage them", C.amber);
  title(s, "Challenges of the GOOPHER architecture (and mitigations)");
  const items = [
    ["dollar", "LLM cost & latency", "~4–5 calls/turn → deterministic pre-process, caching, model tiering; trade cost for visible orchestration."],
    ["lock", "Hallucination on transactions", "Deterministic gate + no-substitution + confirm-before-charge — the LLM never executes a purchase."],
    ["sitemap", "Multi-agent complexity / loops", "Agent-as-tool (no transfer-back), common harness, bounded retries — loops can't form."],
    ["db", "Grounding to live systems", "Tools + RAG; here a mock DB — production wires real OMS / inventory / payments."],
    ["cloud", "Model / quota availability", "Vertex AI + a deterministic fallback engine + self-healing Guardian — degrade, don't fail."],
    ["shield", "Trust & change management", "Full observability (/dev, Cloud Trace), human-in-the-loop, and a measured pilot before scale."],
  ];
  const w = (CW - 0.6) / 3, h = 2.3;
  items.forEach(([icon, head, body], i) => card(s, { x: M + (i % 3) * (w + 0.3), y: 1.95 + Math.floor(i / 3) * (h + 0.3), w, h, icon, chip: C.amber, head, lines: [body], headSize: 13.5, bodySize: 11 }));
  footer(s);
})();

// ============================================ 8. BUSINESS IMPACT MEETS REQUIREMENTS
(() => {
  const s = p.addSlide(); light(s);
  kicker(s, "GOOPHER meets the requirement — and moves the business", C.green);
  title(s, "Business impact & requirement coverage");
  // requirement → delivered table (left)
  s.addText("Every required capability — delivered today", { x: M, y: 1.85, w: 6.3, h: 0.3, margin: 0, fontFace: BF, fontSize: 13, bold: true, color: C.ink });
  const reqs = [
    "Backend tools on a mock retail DB (live inventory / orders)",
    "Sub-agents + context kept when switching",
    "Multi-lingual (carried across the conversation)",
    "Multi-channel (web + phone simulator → CCAI path)",
    "Multi-modal (text · voice · file · camera vision)",
    "Acts safely (deterministic confirm-before-charge gate)",
  ];
  let y = 2.25;
  reqs.forEach((r) => {
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: M, y, w: 6.3, h: 0.62, rectRadius: 0.07, fill: { color: C.white }, line: { color: C.border, width: 1 }, shadow: shadow() });
    s.addImage({ path: ic("check"), x: M + 0.16, y: y + 0.16, w: 0.3, h: 0.3 });
    s.addText(r, { x: M + 0.58, y, w: 5.6, h: 0.62, margin: 0, valign: "middle", fontFace: BF, fontSize: 11, color: C.ink });
    y += 0.7;
  });

  // business value stats (right)
  s.addText("…and the business upside", { x: 7.2, y: 1.85, w: CW - 6.65, h: 0.3, margin: 0, fontFace: BF, fontSize: 13, bold: true, color: C.green });
  const cards = [
    ["clock", "24/7 · every channel & language", "no after-hours gaps; one agent, all markets"],
    ["up", "60–80% deflection (target)", "routine contacts self-served → lower cost"],
    ["chartB", "Higher conversion & AOV", "see-it-shop-it + recommendations turn questions into orders"],
    ["sync", "Self-improving (RSI)", "learns from feedback — gets better with no redeploy"],
  ];
  let cy = 2.25;
  cards.forEach(([icon, head, body]) => {
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: 7.2, y: cy, w: CW - 6.65, h: 0.95, rectRadius: 0.08, fill: { color: C.panel }, line: { color: C.border, width: 1 } });
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: 7.4, y: cy + 0.22, w: 0.52, h: 0.52, rectRadius: 0.11, fill: { color: C.green } });
    s.addImage({ path: ic(icon + "W"), x: 7.53, y: cy + 0.35, w: 0.26, h: 0.26 });
    s.addText(head, { x: 8.05, y: cy + 0.14, w: CW - 7.7, h: 0.34, margin: 0, fontFace: BF, fontSize: 13, bold: true, color: C.ink });
    s.addText(body, { x: 8.05, y: cy + 0.46, w: CW - 7.7, h: 0.42, margin: 0, fontFace: BF, fontSize: 10.5, color: C.muted, valign: "top" });
    cy += 1.05;
  });
  s.addText("Deflection / AOV are illustrative targets — instrumented and validated in the pilot.", { x: M, y: 6.78, w: CW, h: 0.25, margin: 0, fontFace: BF, fontSize: 9, italic: true, color: C.soft });
  footer(s);
})();

// ====================================================== 9. NEXT STEPS / PILOT
(() => {
  const s = p.addSlide(); light(s);
  kicker(s, "From prototype to production", C.teal);
  title(s, "Next steps — detailed architecture & a measured pilot");
  const phases = [
    ["flag", C.green, "Now — PoC (done)", ["GOOPHER live on Cloud Run + Firestore", "all 4 requirements + safe checkout", "117 tests · CI/CD · /dev portal"]],
    ["wrench", C.violet, "Detailed design — 2–3 wks", ["integration blueprint: OMS · payments · CCAI telephony", "SSO/IdP · Secret Manager · network IAM", "Vertex Vector Search for RSI; security review"]],
    ["target", C.blue, "PILOT — 4–6 wks", ["one market / cohort, A/B vs current self-service", "instrument: containment · CSAT · AOV · cost/contact", "human-in-the-loop review of agent actions"]],
    ["rocket", C.rose, "Production rollout", ["multi-region · min-instances for latency", "evals + guardrails in CI; phased traffic", "more languages, channels & sub-agents"]],
  ];
  const w = (CW - 0.9) / 4;
  phases.forEach(([icon, col, head, lines], i) => {
    const x = M + i * (w + 0.3), y = 2.0;
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 3.3, rectRadius: 0.09, fill: { color: C.white }, line: { color: C.border, width: 1 }, shadow: shadow() });
    s.addShape(p.shapes.RECTANGLE, { x, y, w, h: 0.12, fill: { color: col } });
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: x + 0.24, y: y + 0.32, w: 0.6, h: 0.6, rectRadius: 0.12, fill: { color: col } });
    s.addImage({ path: ic(icon + "W"), x: x + 0.39, y: y + 0.47, w: 0.3, h: 0.3 });
    s.addText(head, { x: x + 0.22, y: y + 1.06, w: w - 0.44, h: 0.5, margin: 0, fontFace: BF, fontSize: 13.5, bold: true, color: C.ink, valign: "top" });
    s.addText(lines.map(t => ({ text: t, options: { bullet: { indent: 11 }, breakLine: true, paraSpaceAfter: 6 } })),
      { x: x + 0.24, y: y + 1.62, w: w - 0.46, h: 1.6, margin: 0, fontFace: BF, fontSize: 10.5, color: C.muted, valign: "top" });
    if (i < 3) s.addImage({ path: ic("arrow"), x: x + w + 0.0, y: y + 1.55, w: 0.28, h: 0.28 });
  });
  // pilot KPI bar
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: M, y: 5.55, w: CW, h: 0.85, rectRadius: 0.09, fill: { color: C.dark } });
  s.addImage({ path: ic("chartBW"), x: M + 0.28, y: 5.78, w: 0.4, h: 0.4 });
  s.addText([
    { text: "PILOT SUCCESS METRICS   ", options: { bold: true, color: "FCA5C0", charSpacing: 1 } },
    { text: "containment % · CSAT · AOV uplift · cost per contact · time-to-resolution · language coverage — vs the current self-service baseline.", options: { color: "D7D3EC" } },
  ], { x: M + 0.85, y: 5.55, w: CW - 1.05, h: 0.85, margin: 0, valign: "middle", fontFace: BF, fontSize: 11.5 });
  s.addText("Low-risk ramp: the prototype already proves the hard parts — production is integration + hardening, validated by the pilot.",
    { x: M, y: 6.6, w: CW, h: 0.35, margin: 0, align: "center", fontFace: BF, fontSize: 11.5, italic: true, color: C.ink });
  footer(s);
})();

p.writeFile({ fileName: "../BUSINESS-CASE.pptx" }).then((f) => console.log("WROTE", f));
if (QA) { _refs.forEach((s, i) => { console.log(`\n--- Slide ${i + 1} ---`); console.log((s.__t || []).filter(Boolean).join(" | ")); });
  console.log("\n==== GEOMETRY ===="); console.log(_issues.length ? _issues.join("\n") : "none"); }
