/* GOOPHER — Google Cloud Applied AI CE Presentation (.pptx)
   Maps to the prompt flow: Title/context → Challenge → Solution → Architecture →
   Live demo → 4 hard requirements → Decisions/trade-offs → Reliability/trust →
   Business value → Why Google Cloud → Roadmap → Close/Q&A.
   Satisfies judging criteria: technical acumen, hands-on, customer solution,
   audience engagement, measurable business value, handling questions. */
const pptx = require("pptxgenjs");
const p = new pptx();

// ---- optional QA instrumentation (QA=1): records bounding boxes + text,
// flags out-of-bounds / overlaps, dumps text per slide. No renderer needed.
const QA = !!process.env.QA;
const PW = 13.333, PH = 7.5;
let _slideNo = 0, _issues = [], _slideRefs = [];
function _txt(t) {
  if (typeof t === "string") return t;
  if (Array.isArray(t)) return t.map((r) => (r && r.text) || "").join("");
  return "";
}
// always-on: auto-number slides (footers track real position) + optional QA hooks
{
  const origAdd = p.addSlide.bind(p);
  p.addSlide = function (...a) {
    const s = origAdd(...a);
    _slideNo += 1; const num = _slideNo; s.__n = num;
    if (QA) {
      s.__texts = []; s.__boxes = []; _slideRefs.push(s);
      const wrap = (fn, kind) => {
        const orig = s[fn].bind(s);
        s[fn] = function (arg, opts) {
          const o = (kind === "text") ? (opts || {}) : (arg || {});
          const { x = 0, y = 0, w = 0, h = 0 } = o;
          const eps = 0.02;
          if (x < -eps || y < -eps || x + w > PW + eps || y + h > PH + eps)
            _issues.push(`S${num} ${kind} OUT-OF-BOUNDS x=${x} y=${y} w=${w} h=${h}` + (kind === "text" ? ` :: "${_txt(arg).slice(0, 40)}"` : ""));
          if (kind === "text") { s.__texts.push(_txt(arg)); s.__boxes.push({ x, y, w, h, t: _txt(arg).slice(0, 30) }); }
          return orig(arg, opts);
        };
      };
      wrap("addText", "text"); wrap("addShape", "shape"); wrap("addImage", "image");
    }
    return s;
  };
}

p.defineLayout({ name: "W", width: 13.333, height: 7.5 });
p.layout = "W";
p.author = "GOOPHER — Applied AI CE Practice";
p.title = "GOOPHER — Unified Conversational Retail Agent";

// ---- palette ----
const C = {
  dark: "0A0E1F", ink: "0F172A", muted: "5B6577", soft: "8A94A6",
  panel: "F5F6FB", border: "E6E8F0", white: "FFFFFF",
  violet: "7C3AED", rose: "E11D48", teal: "0D9488", blue: "2563EB",
  amber: "F59E0B", green: "16A34A",
};
const PAGE_W = 13.333, M = 0.55, CW = PAGE_W - 2 * M;
const HF = "Georgia", BF = "Calibri";
const shadow = () => ({ type: "outer", color: "0F172A", blur: 9, offset: 3, angle: 135, opacity: 0.16 });
const ic = (n) => `icons/${n}.png`;

// ---- helpers ----
function kicker(s, text, color = C.violet, x = M, y = 0.5) {
  s.addText(text.toUpperCase(), { x, y, w: CW, h: 0.3, margin: 0,
    fontFace: BF, fontSize: 12, bold: true, color, charSpacing: 3 });
}
function title(s, text, y = 0.82, color = C.ink, w = CW) {
  s.addText(text, { x: M, y, w, h: 1.0, margin: 0, fontFace: HF, fontSize: 28, bold: true, color, valign: "top" });
}
function footer(s, n) {
  s.addText("GOOPHER · Unified Conversational Retail Agent on Google Cloud",
    { x: M, y: 7.06, w: 9, h: 0.3, margin: 0, fontFace: BF, fontSize: 9, color: C.soft });
  s.addText(String(n != null ? n : s.__n), { x: PAGE_W - 1.0, y: 7.06, w: 0.45, h: 0.3, margin: 0, align: "right", fontFace: BF, fontSize: 9, color: C.soft });
}
function lightBG(s) { s.background = { color: C.white }; }

// rounded white card with chip-icon, header, body lines
function card(s, o) {
  const { x, y, w, h, icon, chip = C.violet, head, headColor = C.ink, lines = [], headSize = 15, bodySize = 12.5 } = o;
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.09,
    fill: { color: C.white }, line: { color: C.border, width: 1 }, shadow: shadow() });
  let tx = x + 0.26, ty = y + 0.24;
  if (icon) {
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: tx, y: ty, w: 0.62, h: 0.62, rectRadius: 0.12, fill: { color: chip } });
    s.addImage({ path: ic(icon), x: tx + 0.15, y: ty + 0.15, w: 0.32, h: 0.32 });
  }
  const htx = icon ? tx + 0.82 : tx;
  if (head) s.addText(head, { x: htx, y: ty - 0.02, w: x + w - htx - 0.22, h: 0.66, margin: 0,
    fontFace: BF, fontSize: headSize, bold: true, color: headColor, valign: "middle" });
  if (lines.length) {
    const items = lines.map((t, i) => ({ text: t, options: { bullet: { indent: 12 }, breakLine: true, paraSpaceAfter: 5 } }));
    s.addText(items, { x: tx + 0.02, y: ty + 0.74, w: w - 0.5, h: h - (ty - y) - 0.9, margin: 0,
      fontFace: BF, fontSize: bodySize, color: C.muted, valign: "top" });
  }
}

// big stat callout card
function stat(s, o) {
  const { x, y, w, h = 1.7, num, label, color = C.violet } = o;
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.09, fill: { color: C.white }, line: { color: C.border, width: 1 }, shadow: shadow() });
  s.addText(num, { x: x + 0.1, y: y + 0.2, w: w - 0.2, h: 0.85, margin: 0, align: "center", fontFace: HF, fontSize: 40, bold: true, color });
  s.addText(label, { x: x + 0.18, y: y + 1.04, w: w - 0.36, h: h - 1.1, margin: 0, align: "center", valign: "top", fontFace: BF, fontSize: 11.5, color: C.muted });
}

// ============================================================ SLIDE 1 — TITLE
(() => {
  const s = p.addSlide();
  s.background = { path: "bg_dark.png" };
  s.addImage({ path: "logo.png", x: M, y: 0.62, w: 0.9, h: 0.9 });
  s.addText("GOOPHER", { x: M + 1.05, y: 0.62, w: 8, h: 0.5, margin: 0, fontFace: HF, fontSize: 22, bold: true, color: C.white });
  s.addText("Applied AI · Practice Customer Engineer", { x: M + 1.06, y: 1.08, w: 8, h: 0.4, margin: 0, fontFace: BF, fontSize: 12.5, color: "C9C2E8" });

  s.addText("The unified conversational retail agent", { x: M, y: 2.55, w: 11.6, h: 0.9, margin: 0, fontFace: HF, fontSize: 42, bold: true, color: C.white });
  s.addText([
    { text: "Type it · say it · show it", options: { color: "FCA5C0", bold: true } },
    { text: "  —  one agent that sees, talks, reasons, and transacts safely.", options: { color: "D7D3EC" } },
  ], { x: M, y: 3.55, w: 11.8, h: 0.5, margin: 0, fontFace: BF, fontSize: 17 });

  const chips = [
    ["Google ADK multi-agent", C.violet],
    ["Gemini 2.5 Flash · Vertex AI", C.rose],
    ["Cloud Run · Firestore", C.teal],
    ["Multimodal · multilingual · multichannel", C.blue],
  ];
  let cx = M;
  chips.forEach(([t, col]) => {
    const w = 0.34 + t.length * 0.082;
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: cx, y: 4.45, w, h: 0.44, rectRadius: 0.22, fill: { color: "FFFFFF", transparency: 88 }, line: { color: col, width: 1 } });
    s.addText(t, { x: cx, y: 4.45, w, h: 0.44, margin: 0, align: "center", valign: "middle", fontFace: BF, fontSize: 11, bold: true, color: "FFFFFF" });
    cx += w + 0.18;
  });

  s.addText([
    { text: "Presented to:  ", options: { bold: true, color: "FFFFFF" } },
    { text: "Domain Expert (Technical Stakeholder)  ·  VP of Strategy (Business Stakeholder)", options: { color: "C9C2E8" } },
  ], { x: M, y: 6.35, w: 12, h: 0.4, margin: 0, fontFace: BF, fontSize: 12.5 });
  s.addText("Live prototype — demonstrated in the GOOPHER Chrome side-panel extension, running on Google Cloud.",
    { x: M, y: 6.74, w: 12, h: 0.35, margin: 0, fontFace: BF, fontSize: 11, italic: true, color: "8E87B0" });

  s.addNotes(
    "Set the stage (60s). 'Thanks for the time. I'm the Applied-AI practice specialist you brought in to unblock this engagement. " +
    "Today I'll walk the technical design AND show a working prototype — GOOPHER — live in this Chrome extension, running on Google Cloud. " +
    "I'll address the domain expert on the architecture and the VP of Strategy on the business value, and leave plenty of room for questions. " +
    "Everything you'll see is real and deployed — not slideware.'"
  );
})();

// ====================================================== SLIDE 2 — THE CHALLENGE
(() => {
  const s = p.addSlide(); lightBG(s);
  kicker(s, "The specialized challenge — the “unblocker”", C.rose);
  title(s, "A global retailer is blocked: self-service that can actually transact");

  // left: the problem statement card
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: M, y: 1.95, w: 5.95, h: 4.5, rectRadius: 0.09, fill: { color: C.dark }, shadow: shadow() });
  s.addText("THE CUSTOMER'S PROBLEM", { x: M + 0.32, y: 2.2, w: 5.3, h: 0.3, margin: 0, fontFace: BF, fontSize: 11.5, bold: true, color: "FCA5C0", charSpacing: 2 });
  s.addText([
    { text: "High-volume order management & product support", options: { bold: true, color: "FFFFFF", breakLine: true, paraSpaceAfter: 6 } },
    { text: "via chat AND voice — for a diverse, global base.", options: { color: "D7D3EC", breakLine: true, paraSpaceAfter: 14 } },
    { text: "They need consistent, context-aware routing and natural conversational flows — ", options: { color: "D7D3EC" } },
    { text: "and the agent must take real action against live inventory & orders, not just chat.", options: { color: "FFFFFF", bold: true } },
  ], { x: M + 0.32, y: 2.62, w: 5.35, h: 2.2, margin: 0, fontFace: BF, fontSize: 15 });
  s.addText("Required deliverable: a unified conversational agent with backend tools on a mock retail DB (real-time inventory / order status), extensible to sub-agents+context, multilingual, multichannel, multimodal.",
    { x: M + 0.32, y: 5.15, w: 5.35, h: 1.1, margin: 0, fontFace: BF, fontSize: 11.5, italic: true, color: "B9B2D8" });

  // right: why off-the-shelf fails
  s.addText("Why an off-the-shelf chatbot is impossible here", { x: 6.85, y: 1.95, w: 6.0, h: 0.4, margin: 0, fontFace: BF, fontSize: 15, bold: true, color: C.ink });
  const fails = [
    ["ban", "Answers, doesn't act", "FAQ bots can't safely place/track real orders against live inventory."],
    ["route", "No real routing + memory", "Can't delegate to specialists and keep context across channel/language switches."],
    ["globe", "Global base, many modes", "Needs text, voice, image & camera — in the shopper's language — as one experience."],
    ["lock", "Trust on transactions", "A purchase must be deterministic & auditable — never a free-form LLM guess."],
  ];
  let y = 2.45;
  fails.forEach(([i, h, b]) => {
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: 6.85, y, w: 5.95, h: 0.98, rectRadius: 0.09, fill: { color: C.white }, line: { color: C.border, width: 1 }, shadow: shadow() });
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: 7.09, y: y + 0.21, w: 0.56, h: 0.56, rectRadius: 0.11, fill: { color: C.rose } });
    s.addImage({ path: ic(i), x: 7.22, y: y + 0.34, w: 0.3, h: 0.3 });
    s.addText(h, { x: 7.8, y: y + 0.16, w: 4.85, h: 0.3, margin: 0, fontFace: BF, fontSize: 13, bold: true, color: C.ink, valign: "top" });
    s.addText(b, { x: 7.8, y: y + 0.48, w: 4.85, h: 0.42, margin: 0, fontFace: BF, fontSize: 11, color: C.muted, valign: "top" });
    y += 1.08;
  });
  footer(s);
  s.addNotes(
    "Define the unblocker (2 min). 'The retailer wants modern self-service for order management and support — over chat and voice — for a global base. " +
    "The blocker isn't 'add a chatbot.' It's four things at once: it must ACT on live inventory/orders, ROUTE to specialists while keeping context, " +
    "speak EVERY channel & modality in the customer's language, and do all that while keeping money-moving actions safe and auditable. " +
    "No off-the-shelf box does all four — that's why they engaged a specialist to build a custom agent architecture. That architecture is GOOPHER.'"
  );
})();

// ====================================================== SLIDE 3 — SOLUTION GLANCE
(() => {
  const s = p.addSlide(); lightBG(s);
  kicker(s, "The solution at a glance", C.violet);
  title(s, "GOOPHER — one agent that sees, talks, reasons & transacts");
  s.addText("A Google ADK multi-agent system on Gemini 2.5 Flash (Vertex AI), with backend tools on a mock retail database for real-time inventory & order status — every hard requirement met today, not 'on the roadmap'.",
    { x: M, y: 1.74, w: CW, h: 0.5, margin: 0, fontFace: BF, fontSize: 13, color: C.muted });

  const items = [
    ["sitemap", C.blue, "Sub-agents + context", "ROOT orchestrator delegates to inventory · order · checkout · fulfillment workers; context kept in one session store."],
    ["globe", C.violet, "Multi-lingual", "Language detected per turn and carried across the conversation (e.g. EN ⇄ ES) — same thread, same memory."],
    ["mobile", C.teal, "Multi-channel", "Web side-panel today + a Phone (voice) channel rendered as a mobile-device simulator — same features."],
    ["layers", C.rose, "Multi-modal", "Text, voice (speech-to-text + TTS), file upload, AND a camera 'see-it-shop-it' vision agent."],
  ];
  const w = (CW - 0.6) / 4;
  items.forEach(([icon, chip, h, b], i) => {
    card(s, { x: M + i * (w + 0.2), y: 2.35, w, h: 3.05, icon, chip, head: h, lines: [b], headSize: 14.5, bodySize: 12.5 });
  });

  // strip: backend tools on mock DB
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: M, y: 5.7, w: CW, h: 0.95, rectRadius: 0.09, fill: { color: C.panel }, line: { color: C.border, width: 1 } });
  s.addImage({ path: ic("db"), x: M + 0.3, y: 5.95, w: 0.42, h: 0.42 });
  s.addText([
    { text: "Backend tools on a mock retail DB:  ", options: { bold: true, color: C.ink } },
    { text: "search_inventory · check_stock · get_product_details · get_order_status · place_order · place_bulk_order · run_fulfillment", options: { color: C.muted } },
  ], { x: M + 0.95, y: 5.7, w: CW - 1.2, h: 0.95, margin: 0, valign: "middle", fontFace: BF, fontSize: 12.5 });
  footer(s);
  s.addNotes(
    "The solution in one breath (90s). 'GOOPHER is a unified conversational agent built on Google's Agent Development Kit and Gemini 2.5 Flash on Vertex AI. " +
    "It hits all four extension requirements TODAY: real sub-agents with shared context, multilingual, multichannel, and multimodal — including a camera 'see-it-shop-it' flow. " +
    "And it's not just talk: backend tools hit a mock retail database for live inventory and order status, and place real orders through a safe gate. " +
    "I'll show each of these live in a moment.'"
  );
})();

// ====================================================== SLIDE 4 — ARCHITECTURE
(() => {
  const s = p.addSlide(); lightBG(s);
  kicker(s, "Technical deep-dive · architecture", C.blue);
  title(s, "How it works — a real multi-agent system on Google Cloud");

  const row = (x, y, w, h, color, label, sub, icon) => {
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: C.white }, line: { color, width: 1.5 }, shadow: shadow() });
    if (icon) { s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: x + 0.16, y: y + (h - 0.5) / 2, w: 0.5, h: 0.5, rectRadius: 0.1, fill: { color } });
      s.addImage({ path: ic(icon), x: x + 0.28, y: y + (h - 0.5) / 2 + 0.12, w: 0.26, h: 0.26 }); }
    s.addText(label, { x: x + (icon ? 0.78 : 0.18), y: y + 0.12, w: w - (icon ? 0.92 : 0.32), h: 0.34, margin: 0, fontFace: BF, fontSize: 13, bold: true, color: C.ink });
    if (sub) s.addText(sub, { x: x + (icon ? 0.78 : 0.18), y: y + 0.44, w: w - (icon ? 0.92 : 0.32), h: h - 0.5, margin: 0, fontFace: BF, fontSize: 10.5, color: C.muted, valign: "top" });
  };
  const arrow = (x, y) => s.addImage({ path: ic("arrow"), x, y, w: 0.3, h: 0.3 });

  // top lane: client -> cloud run -> orchestrator
  row(M, 1.75, 3.55, 1.0, C.violet, "GOOPHER extension (MV3)", "Chrome side panel · web + phone · voice/camera popups", "comments");
  arrow(M + 3.62, 2.1);
  row(M + 4.0, 1.75, 3.4, 1.0, C.muted, "Cloud Run · FastAPI", "Auth (JWT) · rate-limit · CORS · /version", "cloud");
  arrow(M + 7.47, 2.1);
  row(M + 7.85, 1.75, CW - 7.85, 1.0, C.amber, "ROOT orchestrator (ADK)", "Gemini 2.5 Flash on Vertex AI — decides & delegates", "robot");

  // pre-process strip
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: M, y: 2.95, w: CW, h: 0.62, rectRadius: 0.07, fill: { color: C.panel }, line: { color: C.border, width: 1 } });
  s.addText([
    { text: "Deterministic pre-processing (no LLM):  ", options: { bold: true, color: C.ink } },
    { text: "modality · language · channel · memory  →  then the agent runs through the common Agent Harness", options: { color: C.muted } },
  ], { x: M + 0.25, y: 2.95, w: CW - 0.5, h: 0.62, margin: 0, valign: "middle", fontFace: BF, fontSize: 12 });

  // workers row (4) — agent-as-tool
  s.addText("Worker sub-agents (agent-as-tool) — each picks a registry skill, calls its tools", { x: M, y: 3.74, w: CW, h: 0.3, margin: 0, fontFace: BF, fontSize: 11.5, bold: true, color: C.blue });
  const workers = [
    ["inventory_agent", "search · stock · details", C.blue, "sitemap"],
    ["order_agent", "status · history · bulk", C.blue, "route"],
    ["checkout_agent", "cart · payment · place", C.teal, "lock"],
    ["order_mgmt_agent", "9-stage fulfillment", C.teal, "cog"],
  ];
  const ww = (CW - 0.6) / 4;
  workers.forEach(([h, sub, col, icon], i) => row(M + i * (ww + 0.2), 4.08, ww, 0.95, col, h, sub, icon));

  // bottom lane: tools -> firestore ; plus gate + guardian + observability
  row(M, 5.25, 4.0, 1.0, C.teal, "Backend tools + mock retail DB", "Firestore (cloud) / SQLite (local) · ORDER_PLACED", "db");
  row(M + 4.25, 5.25, 4.0, 1.0, C.violet, "Transactional gate (deterministic)", "cart → payment → ORDER_PLACED → receipt", "lock");
  row(M + 8.5, 5.25, CW - 8.5, 1.0, C.violet, "Guardian + Observability", "self-heal · Cloud Trace · /dev portal", "shield");

  s.addText("LLM orchestrates & converses;  deterministic code transacts.",
    { x: M, y: 6.45, w: CW, h: 0.4, margin: 0, fontFace: BF, fontSize: 13, italic: true, bold: true, color: C.ink, align: "center" });
  footer(s);
  s.addNotes(
    "Architecture (3 min — the centerpiece for the technical stakeholder). 'Top lane: the Chrome extension talks over HTTPS+JWT to FastAPI on Cloud Run, which runs a real ADK orchestrator on Gemini 2.5 Flash via Vertex AI. " +
    "Before the LLM, deterministic Python handles modality/language/channel/memory — fast, free, reliable. " +
    "The orchestrator delegates to four worker sub-agents using the agent-as-tool pattern; each picks a skill from a registry and calls in-process tools that hit the mock retail DB in Firestore. " +
    "Crucially, checkout is a DETERMINISTIC transactional gate, and a self-healing Guardian plus Cloud Trace and a live /dev portal make the whole thing observable. " +
    "The one line to remember: the LLM orchestrates and converses; deterministic code transacts.' (Open /dev here if time permits.)"
  );
})();

// ============================================ SLIDE 4b — ARCHITECTURE DEEP-DIVE
(() => {
  const s = p.addSlide(); lightBG(s);
  kicker(s, "Architecture deep-dive · one request, end-to-end", C.blue);
  title(s, "Trace a single turn through the stack");

  // ---- left: numbered request flow ----
  const lx = M, lw = 7.25;
  s.addShape(p.shapes.LINE, { x: lx + 0.18, y: 2.1, w: 0, h: 4.05, line: { color: C.border, width: 2 } });
  const steps = [
    ["1", "Input — GOOPHER extension", "text · 🎤 voice · 📷 camera · 📎 file  →  HTTPS + JWT", C.violet],
    ["2", "Edge + Authentication — Cloud Run · FastAPI", "JWT · email allowlist · master-pw · fail-closed  ·  rate/size limits · CORS", C.muted],
    ["3", "Pre-process (no LLM) + Memory Agent", "modality · language · channel agents  ·  Memory Agent LOADS session by session_id", C.teal],
    ["4", "Route", "purchase? → deterministic transactional gate (skip LLM)  ·  else → agent path", C.amber],
    ["5", "Agent Harness", "build agent · ensure ADK session · run (retry · degrade-once · structured result)", C.violet],
    ["6", "ROOT sub-agent: goopher_orchestrator — Gemini 2.5 Flash (Vertex)", "selects ONE worker via agent-as-tool (stays in control)", C.amber],
    ["7", "Worker sub-agent (e.g. inventory_agent) PICKS an agent skill", "skill (instruction + tools) → calls its tools via native function-calling", C.blue],
    ["8", "Tools → mock retail DB", "read/write Firestore: catalog · orders · ORDER_PLACED", C.teal],
    ["9", "Respond", "channel-format reply · Memory Agent PERSISTS turn · stream back · trace (Cloud Trace + /dev)", C.violet],
  ];
  let y = 1.92; const rh = 0.475;
  steps.forEach(([n, head, detail, col]) => {
    s.addShape(p.shapes.OVAL, { x: lx, y, w: 0.36, h: 0.36, fill: { color: col } });
    s.addText(n, { x: lx, y, w: 0.36, h: 0.36, margin: 0, align: "center", valign: "middle", fontFace: BF, fontSize: 13, bold: true, color: "FFFFFF" });
    s.addText(head, { x: lx + 0.52, y: y - 0.05, w: lw - 0.55, h: 0.26, margin: 0, fontFace: BF, fontSize: 12.5, bold: true, color: C.ink, valign: "middle" });
    s.addText(detail, { x: lx + 0.52, y: y + 0.205, w: lw - 0.55, h: 0.25, margin: 0, fontFace: BF, fontSize: 10.5, color: C.muted, valign: "middle" });
    y += rh;
  });

  // ---- right: cross-cutting concerns ----
  const rx = 8.15, rw = PAGE_W - M - rx; // ~4.63
  s.addText("Cross-cutting (every turn)", { x: rx, y: 1.78, w: rw, h: 0.3, margin: 0, fontFace: BF, fontSize: 13, bold: true, color: C.blue });
  const cc = [
    ["lock", C.violet, "Transactional gate — deterministic", ["cart → payment → ORDER_PLACED → receipt", "the LLM never executes the purchase"]],
    ["layers", C.rose, "Isolated side-agents", ["/vision (Gemini Vision) · /advise (ReAct)", "Guardian self-heal — separate endpoints, don't touch /chat"]],
    ["eye", C.teal, "Observability & resilience", ["Cloud Trace spans · live /dev · /metrics · /version", "graceful fallback + circuit breaker"]],
  ];
  let cy = 2.15; const ch = 1.2;
  cc.forEach(([icon, chip, head, lines]) => {
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: rx, y: cy, w: rw, h: ch, rectRadius: 0.08, fill: { color: C.white }, line: { color: C.border, width: 1 }, shadow: shadow() });
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: rx + 0.2, y: cy + 0.2, w: 0.5, h: 0.5, rectRadius: 0.1, fill: { color: chip } });
    s.addImage({ path: ic(icon), x: rx + 0.32, y: cy + 0.32, w: 0.26, h: 0.26 });
    s.addText(head, { x: rx + 0.82, y: cy + 0.16, w: rw - 1.0, h: 0.5, margin: 0, fontFace: BF, fontSize: 12.5, bold: true, color: C.ink, valign: "middle" });
    s.addText(lines.map((t) => ({ text: t, options: { bullet: { indent: 11 }, breakLine: true, paraSpaceAfter: 3 } })),
      { x: rx + 0.24, y: cy + 0.7, w: rw - 0.46, h: 0.46, margin: 0, fontFace: BF, fontSize: 10.5, color: C.muted, valign: "top" });
    cy += ch + 0.16;
  });
  // tech stack strip
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: rx, y: cy + 0.02, w: rw, h: 0.66, rectRadius: 0.08, fill: { color: C.dark } });
  s.addText([
    { text: "STACK   ", options: { bold: true, color: "FCA5C0", charSpacing: 2 } },
    { text: "Vertex AI · Gemini 2.5 Flash · ADK · Cloud Run · Firestore · Cloud Trace", options: { color: "D7D3EC" } },
  ], { x: rx + 0.22, y: cy + 0.02, w: rw - 0.4, h: 0.66, margin: 0, valign: "middle", fontFace: BF, fontSize: 10.5 });

  footer(s);
  s.addNotes(
    "Architecture deep-dive (3–4 min — for the technical stakeholder; great for Q&A). Walk the numbers 1→9: " +
    "1) The extension captures text, voice, camera or a file and calls the API over HTTPS with a JWT. " +
    "2) Cloud Run + FastAPI authenticates and applies rate/size limits and CORS. " +
    "3) Deterministic Python detects modality, language and channel and LOADS session memory by session_id — no LLM, so it's fast, free and reliable. " +
    "4) We branch: a purchase goes to the deterministic transactional gate and SKIPS the LLM entirely; everything else goes to the agent path. " +
    "5) The common Agent Harness builds the agent, ensures the ADK session, and runs it with retries and degrade-once. " +
    "6) The ROOT orchestrator on Gemini 2.5 Flash via Vertex selects ONE worker using agent-as-tool — so it stays in control and there are no delegation loops. " +
    "7) That worker picks a skill from the registry and calls its tools via native function-calling. " +
    "8) Tools read and write the mock retail DB in Firestore — catalog, orders, and the ORDER_PLACED table. " +
    "9) We channel-format the reply, PERSIST the turn to memory, stream it back, and trace the whole thing to Cloud Trace and the live /dev portal. " +
    "On the right are the three things true on EVERY turn: the deterministic gate, the isolated side-agents (vision, advisor, guardian), and full observability + resilience. " +
    "I can drill into any box."
  );
})();

// ======================================== SLIDE 4c — INSIDE THE AGENT PLATFORM
(() => {
  const s = p.addSlide(); lightBG(s);
  kicker(s, "Architecture deep-dive · components in detail", C.blue);
  title(s, "Inside the platform — sub-agents, skills & the guard rails");

  const panels = [
    ["sitemap", C.blue, "Sub-agents  (the LLM agents)",
      ["ROOT: goopher_orchestrator (routes)",
       "inventory_agent — search · stock",
       "order_agent — status · history · bulk",
       "checkout_agent — cart · pay · place",
       "order_management_agent — fulfillment",
       "Isolated: vision_agent · advisor_agent · guardian"]],
    ["layers", C.amber, "Agent skills  (registry — SEPARATE)",
      ["A skill = INSTRUCTION + TOOLS",
       "an agent PICKS a skill (≠ a sub-agent)",
       "inventory · order  (read-only)",
       "checkout · fulfillment  (transactional)",
       "read-only flag enforced in code",
       "introspect live → GET /skills"]],
    ["lock", C.violet, "Authentication & edge",
      ["JWT bearer token on every request",
       "Email allowlist + master password",
       "Fail-closed — no match → rejected",
       "Rate-limit · request-size limit · CORS",
       "Secrets in env / secret — never committed"]],
    ["db", C.teal, "Memory agent  (shared state)",
      ["One session store keyed by session_id",
       "Firestore (cloud) / SQLite (local)",
       "Turns + working-memory facts",
       "LOAD at start · PERSIST at end of turn",
       "Durable & shared across instances"]],
    ["shield", C.rose, "Guardrails  (safety)",
      ["Deterministic gate — LLM never pays",
       "No substitution · confirm-before-charge",
       "Loop prevention (agent-as-tool)",
       "Bounded retries · graceful fallback",
       "Self-healing Guardian (circuit breaker)"]],
    ["check", C.green, "Quality — unit tests & evals",
      ["117 unit tests (pytest) gate every change",
       "8 evals on agent behaviour",
       "CI/CD: push → test + eval → Cloud Run",
       "CI-sim blocks google.* → tests fallback",
       "Isolation asserts (advisor ∌ checkout)"]],
  ];
  const w = (CW - 0.6) / 3, h = 2.32;
  panels.forEach(([icon, chip, head, lines], i) => {
    const x = M + (i % 3) * (w + 0.3), y = 1.95 + Math.floor(i / 3) * (h + 0.28);
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.09, fill: { color: C.white }, line: { color: C.border, width: 1 }, shadow: shadow() });
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: x + 0.24, y: y + 0.22, w: 0.54, h: 0.54, rectRadius: 0.11, fill: { color: chip } });
    s.addImage({ path: ic(icon), x: x + 0.37, y: y + 0.35, w: 0.28, h: 0.28 });
    s.addText(head, { x: x + 0.9, y: y + 0.2, w: w - 1.08, h: 0.58, margin: 0, fontFace: BF, fontSize: 12.5, bold: true, color: C.ink, valign: "middle" });
    s.addText(lines.map((t) => ({ text: t, options: { bullet: { indent: 10 }, breakLine: true, paraSpaceAfter: 2 } })),
      { x: x + 0.26, y: y + 0.88, w: w - 0.5, h: h - 0.98, margin: 0, fontFace: BF, fontSize: 10, color: C.muted, valign: "top" });
  });
  footer(s);
  s.addNotes(
    "Components in detail (3–4 min — the 'show me the rigor' slide). Six panels, each its own concern. " +
    "1) Sub-agents are the LLM agents: the ROOT goopher_orchestrator and four named workers — inventory, order, checkout, order_management — plus three isolated ones (vision, advisor, guardian). " +
    "2) Agent SKILLS are a SEPARATE concept: a skill is an instruction + a set of tools, registered once; an agent PICKS a skill. Browse-and-track skills are read-only; checkout/fulfillment are transactional — and the read-only flag is enforced in code so the advisor can never get a checkout tool. See GET /skills. " +
    "3) Authentication: JWT on every call, an email allowlist plus master password, fail-closed, with rate/size limits and CORS; secrets never committed. " +
    "4) The Memory Agent is one session store keyed by session_id, durable in Firestore, holding turns plus working-memory facts; loaded at the start and persisted at the end of every turn. " +
    "5) Guardrails: the deterministic gate, no-substitution, confirm-before-charge, structural loop prevention, graceful fallback, and the self-healing Guardian. " +
    "6) Quality: 117 unit tests and 8 evals gate every change via CI/CD, plus a CI-simulation that blocks the google packages to prove the production fallback path. " +
    "The headline: sub-agents and skills are different layers, and safety/quality are first-class, not afterthoughts."
  );
})();

// ====================================================== SLIDE 5 — LIVE DEMO
(() => {
  const s = p.addSlide();
  s.background = { path: "bg_dark.png" };
  kicker(s, "Hands-on · live demonstration", "FCA5C0");
  s.addText("Live demo — in the GOOPHER extension", { x: M, y: 0.78, w: CW, h: 0.9, margin: 0, fontFace: HF, fontSize: 30, bold: true, color: C.white });
  s.addText("Everything below is run live in the side panel, against the deployed Cloud Run service.",
    { x: M, y: 1.62, w: CW, h: 0.4, margin: 0, fontFace: BF, fontSize: 13, color: "C9C2E8" });

  const demos = [
    ["comments", "Conversational order + confirm", "“do you have oreos?” → “place an order” → shows cart → “please confirm” → staged receipt. Never substitutes."],
    ["camera", "See-it, shop-it (Gemini Vision)", "Show a real soccer ball → “what's the price?” → “place an order” → confirm. Same model recognizes + reasons + replies."],
    ["eye", "Radical transparency (/dev)", "Watch the live pipeline: harness → orchestrator → worker → skill → tool → memory. Multilingual + voice in the same thread."],
    ["shield", "Self-healing (the finale)", "💥 Kill Vertex → DETECT → DIAGNOSE → REMEDIATE → VERIFY → restore. Isolated; never touches live flows."],
  ];
  const w = (CW - 0.6) / 2, h = 1.95;
  demos.forEach(([icon, head, body], i) => {
    const x = M + (i % 2) * (w + 0.6), y = 2.35 + Math.floor(i / 2) * (h + 0.35);
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.1, fill: { color: "FFFFFF", transparency: 90 }, line: { color: "FFFFFF", width: 1 } });
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: x + 0.28, y: y + 0.3, w: 0.66, h: 0.66, rectRadius: 0.13, fill: { color: C.rose } });
    s.addImage({ path: ic(icon), x: x + 0.45, y: y + 0.47, w: 0.32, h: 0.32 });
    s.addText(`${i + 1}.  ${head}`, { x: x + 1.12, y: y + 0.28, w: w - 1.4, h: 0.5, margin: 0, fontFace: BF, fontSize: 16, bold: true, color: "FFFFFF" });
    s.addText(body, { x: x + 1.12, y: y + 0.84, w: w - 1.4, h: h - 1.0, margin: 0, fontFace: BF, fontSize: 12.5, color: "D7D3EC", valign: "top" });
  });
  s.addNotes(
    "DEMO (8–10 min — the hands-on score). Drive the extension; narrate intent before each click. " +
    "1) Type 'do you have oreos?' then 'place an order of oreo cookies' → show the cart + 'please confirm' → Confirm → staged receipt. Stress: no substitution, confirm before charge. " +
    "2) Camera: show the soccer ball, ask price, then 'place an order' → confirm. Gemini Vision on Vertex recognizes + prices + acts. " +
    "3) Open /dev: point at the live pipeline (harness → orchestrator → worker → skill → tool → memory). Switch language/voice to show context carried. " +
    "4) Finale: /dev Guardian → Kill Vertex → watch DETECT→DIAGNOSE→REMEDIATE→VERIFY → Restore all. " +
    "If anything is slow (cold start), narrate it as graceful degradation and pivot to the Guardian — it always works."
  );
})();

// ====================================================== SLIDE 6 — 4 REQUIREMENTS
(() => {
  const s = p.addSlide(); lightBG(s);
  kicker(s, "How GOOPHER meets the four hard requirements", C.teal);
  title(s, "Sub-agents + context · multilingual · multichannel · multimodal");

  const items = [
    ["sitemap", C.blue, "Sub-agents & context",
      ["ROOT orchestrator → inventory/order/checkout/fulfillment workers (agent-as-tool).",
       "One session store keyed by session_id (Firestore, durable) shared by all agents.",
       "“is it in navy?” → “order it” resolves across turns; survives autoscaling."]],
    ["globe", C.violet, "Multi-lingual",
      ["Per-turn language detection; the language is remembered and carried.",
       "Start Web/English, continue Phone/Spanish — same thread, same memory.",
       "Extensible to Vertex Translation for long-tail locales."]],
    ["mobile", C.teal, "Multi-channel",
      ["Web side-panel + a Phone (voice) channel rendered as a mobile simulator.",
       "Channel-aware formatting (voice-safe text for phone).",
       "Path to telephony / CCAI for true phone & SMS."]],
    ["layers", C.rose, "Multi-modal",
      ["Text, voice (browser STT + TTS), file upload (e.g. bulk order CSV).",
       "Camera “see-it-shop-it” — a dedicated Gemini Vision agent.",
       "Each modality detected deterministically, then routed."]],
  ];
  const w = (CW - 0.6) / 2, h = 2.25;
  items.forEach(([icon, chip, head, lines], i) => {
    const x = M + (i % 2) * (w + 0.6), y = 1.95 + Math.floor(i / 2) * (h + 0.3);
    card(s, { x, y, w, h, icon, chip, head, lines, headSize: 15.5, bodySize: 12 });
  });
  footer(s);
  s.addNotes(
    "Tie back to the exact requirements (2 min). 'The prompt named four things to be extensible to — we built all four in. " +
    "Sub-agents with shared context via one session store on Firestore. Multilingual, carried across turns. Multichannel — web plus a phone simulator, with a clean path to CCAI. " +
    "And multimodal — text, voice, files, and camera vision. This slide is your checklist; I can go deep on any box.'"
  );
})();

// ====================================================== SLIDE 7 — DECISIONS / TRADE-OFFS
(() => {
  const s = p.addSlide(); lightBG(s);
  kicker(s, "Architectural decisions & trade-offs", C.amber);
  title(s, "Why this custom design — defending the engineering choices");

  const rows = [
    ["lock", "Deterministic transactional gate", "LLM places orders end-to-end", "“LLM orchestrates, code transacts.” Money/inventory actions are structured, auditable, reproducible — never a hallucinated purchase."],
    ["sitemap", "Agent-as-tool (not transfer)", "sub_agents / transfer handoff", "Orchestrator stays in control & composes the reply; workers can't transfer back → delegation loops are impossible by construction."],
    ["cog", "Deterministic pre-processing", "modality/lang/channel as LLM agents", "We tried LLM agents — they failed for zero benefit. Detecting language needs no intelligence; plain code is reliable & free."],
    ["brain", "Native function-calling + targeted ReAct", "PlanReActPlanner everywhere", "Native tool-calling for production (reliable, fast); explicit ReAct only for the read-only advisor, where the visible plan adds value."],
    ["cloud", "Gemini 2.5 Flash on Vertex (one model)", "many models / self-hosted", "One natively-multimodal model does reasoning, language AND vision — less ops, lower latency, Vertex security & quota."],
    ["sync", "Graceful fallback + self-heal", "fail the request", "If the LLM/ADK path errors, a deterministic engine answers; the Guardian heals forward — the service degrades, it doesn't go down."],
  ];
  const w = (CW - 0.5) / 2, h = 1.4;
  rows.forEach(([icon, head, vs, why], i) => {
    const x = M + (i % 2) * (w + 0.5), y = 1.9 + Math.floor(i / 2) * (h + 0.18);
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: C.white }, line: { color: C.border, width: 1 }, shadow: shadow() });
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: x + 0.2, y: y + 0.22, w: 0.5, h: 0.5, rectRadius: 0.1, fill: { color: C.violet } });
    s.addImage({ path: ic(icon), x: x + 0.32, y: y + 0.34, w: 0.26, h: 0.26 });
    s.addText(head, { x: x + 0.82, y: y + 0.16, w: w - 1.0, h: 0.34, margin: 0, fontFace: BF, fontSize: 13.5, bold: true, color: C.ink });
    s.addText([{ text: "Chosen over: ", options: { italic: true, color: C.rose } }, { text: vs, options: { italic: true, color: C.soft } }],
      { x: x + 0.82, y: y + 0.47, w: w - 1.0, h: 0.26, margin: 0, fontFace: BF, fontSize: 10.5 });
    s.addText(why, { x: x + 0.22, y: y + 0.78, w: w - 0.42, h: 0.56, margin: 0, fontFace: BF, fontSize: 11, color: C.muted, valign: "top" });
  });
  footer(s);
  s.addNotes(
    "Defend the design (3 min — the technical-acumen score). For each: name the choice, the alternative, and WHY. " +
    "The headline trade-off is the deterministic gate — we deliberately keep the LLM OUT of executing payments. " +
    "Agent-as-tool prevents loops structurally. We didn't force deterministic work into agents. We use native function-calling for reliability and reserve explicit ReAct for the one read-only advisor. " +
    "One Gemini model on Vertex keeps ops and latency down. And graceful fallback + self-healing means we degrade, not fail. " +
    "Invite the expert to push on any row — this is where the conversation gets good."
  );
})();

// ====================================================== SLIDE 7b — CHALLENGES
(() => {
  const s = p.addSlide(); lightBG(s);
  kicker(s, "Hands-on · the hard parts", C.rose);
  title(s, "Engineering challenges — and how we unblocked them");

  const rows = [
    ["sitemap", "Sub-agents skipped / ran out of order", "ADK let the LLM skip sub-agents; a SequentialAgent can't be an AgentTool.", "Agent-as-tool composition + deterministic pre-processing (modality/lang/channel as plain code)."],
    ["brain", "Gemini 2.5 “thinking” ate the answer", "Vision + the ReAct advisor returned a plan but no final text (thinking spent the budget).", "thinking_budget=0 + token cap; a grounded synthesis fallback guarantees an answer."],
    ["check", "A cloud-only bug hid behind green local tests", "The ADK path isn't exercised in CI (no creds), so a prod regression could slip through.", "CI-sim: block google.* and run the whole suite via the deterministic fallback path."],
    ["lock", "LLM could substitute or auto-charge", "A free-form LLM placing orders risks wrong items and unconfirmed charges.", "No-substitution + a deterministic confirm-before-charge gate on EVERY modality."],
    ["db", "Context lost on channel / language switch", "Per-instance memory drops context across Web↔Phone, EN↔ES, and scale-to-zero.", "One session store keyed by session_id, durable in Firestore, shared by all agents."],
    ["cloud", "Vertex vs AI Studio SDK; quota “limit:0” lies", "google.generativeai can't reach Vertex; a wrong model reads as a zero quota.", "Unified google.genai (vertexai=True) + pin gemini-2.5-flash (verified quota)."],
  ];
  const w = (CW - 0.5) / 2, h = 1.42;
  rows.forEach(([icon, ch, detail, sol], i) => {
    const x = M + (i % 2) * (w + 0.5), y = 1.9 + Math.floor(i / 2) * (h + 0.18);
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: C.white }, line: { color: C.border, width: 1 }, shadow: shadow() });
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: x + 0.2, y: y + 0.22, w: 0.5, h: 0.5, rectRadius: 0.1, fill: { color: C.rose } });
    s.addImage({ path: ic(icon), x: x + 0.32, y: y + 0.34, w: 0.26, h: 0.26 });
    s.addText([{ text: "⚠  ", options: { color: C.rose, bold: true } }, { text: ch, options: { bold: true, color: C.ink } }],
      { x: x + 0.82, y: y + 0.16, w: w - 1.0, h: 0.32, margin: 0, fontFace: BF, fontSize: 12.5, valign: "middle" });
    s.addText(detail, { x: x + 0.82, y: y + 0.5, w: w - 1.02, h: 0.32, margin: 0, fontFace: BF, fontSize: 10.5, italic: true, color: C.soft, valign: "top" });
    s.addText([{ text: "✓  ", options: { color: C.teal, bold: true } }, { text: sol, options: { color: C.muted } }],
      { x: x + 0.22, y: y + 0.86, w: w - 0.42, h: 0.5, margin: 0, fontFace: BF, fontSize: 11, valign: "top" });
  });
  footer(s);
  s.addNotes(
    "Challenges (2–3 min — shows hands-on depth, which the panel scores). 'Building this surfaced real problems. " +
    "ADK let the model skip sub-agents and a SequentialAgent can't be an AgentTool — so I moved pre-processing to deterministic code and used agent-as-tool. " +
    "Gemini 2.5's thinking starved the answer on vision and the ReAct advisor — fixed with thinking_budget=0 plus a grounded synthesis fallback. " +
    "The ADK path isn't testable in CI, so a cloud-only bug could hide — I added a CI-simulation that blocks the google packages and runs everything through the fallback. " +
    "I kept the LLM from substituting or auto-charging with a deterministic confirm-before-charge gate. Context across channels/languages lives in one Firestore session store. " +
    "And I learned the SDK/quota gotchas: google.genai for Vertex, and pin the right model. Each of these is documented in LEARNINGS.md.'"
  );
})();

// ============================================================ SLIDE 7c — WOW
(() => {
  const s = p.addSlide();
  s.background = { path: "bg_dark.png" };
  kicker(s, "The differentiators", "FCA5C0");
  s.addText("What makes them lean in", { x: M, y: 0.78, w: CW, h: 0.9, margin: 0, fontFace: HF, fontSize: 30, bold: true, color: C.white });

  const wow = [
    ["camera", "See-it, shop-it", "Show a real object to the camera — Gemini Vision prices it and orders it."],
    ["sync", "Self-healing, live on stage", "Kill a dependency with a button; watch DETECT→DIAGNOSE→REMEDIATE→VERIFY recover it."],
    ["eye", "Radical transparency", "The live agent pipeline — agent → skill → tool → memory — for every single turn."],
    ["brain", "Two agent styles, one model", "Native function-calling for transactions; visible ReAct (you watch it plan) for advice."],
    ["lock", "Safe by design", "The AI never executes payment — a deterministic, auditable gate does; confirm-before-charge."],
    ["bolt", "Production-shaped", "117 tests · CI/CD · self-healing · observable — on Google Cloud, free-tier-first."],
  ];
  const w = (CW - 0.6) / 3, h = 2.05;
  wow.forEach(([icon, head, body], i) => {
    const x = M + (i % 3) * (w + 0.3), y = 2.05 + Math.floor(i / 3) * (h + 0.3);
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.1, fill: { color: "FFFFFF", transparency: 90 }, line: { color: "FFFFFF", width: 1 } });
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: x + 0.26, y: y + 0.26, w: 0.64, h: 0.64, rectRadius: 0.13, fill: { color: C.rose } });
    s.addImage({ path: ic(icon), x: x + 0.43, y: y + 0.43, w: 0.3, h: 0.3 });
    s.addText(head, { x: x + 1.04, y: y + 0.28, w: w - 1.2, h: 0.6, margin: 0, fontFace: BF, fontSize: 15.5, bold: true, color: "FFFFFF", valign: "middle" });
    s.addText(body, { x: x + 0.28, y: y + 1.04, w: w - 0.54, h: h - 1.2, margin: 0, fontFace: BF, fontSize: 12, color: "D7D3EC", valign: "top" });
  });
  s.addNotes(
    "Wow factor (90s — the memorable beat). 'If you remember six things: you can SHOW a product to a camera and it orders it; you can BREAK a dependency on stage and watch it self-heal; " +
    "you can SEE the agent pipeline for every turn; it runs TWO agent styles on one model; the AI never touches payment; and it's production-shaped — tested, CI/CD, self-healing — on Google Cloud. " +
    "Most demos show one of these; GOOPHER shows all six, live.'"
  );
})();

// ====================================================== SLIDE 8 — RELIABILITY / TRUST
(() => {
  const s = p.addSlide(); lightBG(s);
  kicker(s, "Reliability, safety & trust", C.violet);
  title(s, "Production-grade trust — by design, not by hope");

  const items = [
    ["ban", C.rose, "Never substitutes", "If the exact item isn't found, it says so — it won't swap in a different product."],
    ["check", C.teal, "Confirm before charge", "Cart preview + “please confirm” on every path — text, voice, and camera alike."],
    ["sync", C.violet, "Self-healing Guardian", "Circuit breaker · retry · failover · heal-forward; chaos buttons prove it live."],
    ["sitemap", C.blue, "No agent loops", "Agent-as-tool, no nested agents, single-pass turns, bounded retries, degrade-once."],
    ["db", C.teal, "Durable shared state", "One session store on Firestore — context survives scale-to-zero & autoscaling."],
    ["eye", C.amber, "Full observability", "Live /dev pipeline, Cloud Trace spans, /metrics, /version — debug any turn."],
  ];
  const w = (CW - 0.6) / 3, h = 1.95;
  items.forEach(([icon, chip, head, body], i) => {
    const x = M + (i % 3) * (w + 0.3), y = 1.95 + Math.floor(i / 3) * (h + 0.25);
    card(s, { x, y, w, h, icon, chip, head, lines: [body], headSize: 14, bodySize: 12 });
  });
  footer(s);
  s.addNotes(
    "Reliability & trust (2 min — pre-empts the 'is it safe?' question). 'For a retailer, an agent that touches orders has to be trustworthy. " +
    "GOOPHER never substitutes, always confirms before charging, can't loop by construction, keeps durable shared state, self-heals, and is fully observable. " +
    "These aren't promises — most are visible live in the /dev portal.'"
  );
})();

// ====================================================== SLIDE 9 — BUSINESS VALUE
(() => {
  const s = p.addSlide(); lightBG(s);
  kicker(s, "Business & strategic value — for the VP of Strategy", C.rose);
  title(s, "From technical win to measurable business value");

  stat(s, { x: M, y: 1.95, w: 2.86, num: "24/7", label: "Self-service order mgmt & support — every channel, every language", color: C.violet });
  stat(s, { x: M + 3.06, y: 1.95, w: 2.86, num: "60–80%", label: "Typical self-service deflection of routine contacts (industry benchmark)", color: C.teal });
  stat(s, { x: M + 6.12, y: 1.95, w: 2.86, num: "~$0", label: "Idle cost — Cloud Run scales to zero between conversations", color: C.amber });
  stat(s, { x: M + 9.18, y: 1.95, w: CW - 9.18, num: "1 agent", label: "Replaces search + support + checkout hand-offs", color: C.rose });

  const levers = [
    ["chart", "Higher conversion & AOV", "Natural discovery + “see-it-shop-it” + recommendations turn questions into orders."],
    ["globe", "Instant global reach", "One agent serves every language & channel — no per-market chatbot rebuilds."],
    ["bolt", "Lower cost to serve", "Deflect routine contacts; serverless + free-tier-first keeps run-cost low."],
    ["shield", "Brand-safe automation", "No substitutions, confirm-before-charge, self-healing — automation you can trust on revenue."],
  ];
  const w = (CW - 0.6) / 2, h = 1.35;
  levers.forEach(([icon, head, body], i) => {
    const x = M + (i % 2) * (w + 0.6), y = 4.0 + Math.floor(i / 2) * (h + 0.22);
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: C.panel }, line: { color: C.border, width: 1 } });
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: x + 0.22, y: y + 0.36, w: 0.6, h: 0.6, rectRadius: 0.12, fill: { color: C.rose } });
    s.addImage({ path: ic(icon), x: x + 0.37, y: y + 0.51, w: 0.3, h: 0.3 });
    s.addText(head, { x: x + 1.0, y: y + 0.2, w: w - 1.2, h: 0.4, margin: 0, fontFace: BF, fontSize: 14.5, bold: true, color: C.ink });
    s.addText(body, { x: x + 1.0, y: y + 0.6, w: w - 1.2, h: 0.66, margin: 0, fontFace: BF, fontSize: 12, color: C.muted, valign: "top" });
  });
  s.addText("Benchmarks are illustrative industry ranges, not client results.", { x: M, y: 6.86, w: CW, h: 0.25, margin: 0, fontFace: BF, fontSize: 9, italic: true, color: C.soft });
  footer(s);
  s.addNotes(
    "Business value (2–3 min — speak to the VP of Strategy). 'Translate the tech into outcomes: 24/7 self-service across every channel and language; " +
    "deflection of routine contacts (industry sees 60–80%); near-zero idle cost because it scales to zero; and one agent replacing three hand-offs. " +
    "The growth levers: higher conversion & basket size from natural discovery and see-it-shop-it; instant global reach without rebuilding per market; lower cost to serve; and brand-safe automation. " +
    "I'm flagging the numbers as illustrative benchmarks — in a pilot we'd instrument the real deflection, conversion and CSAT.'"
  );
})();

// ====================================================== SLIDE 10 — WHY GOOGLE CLOUD
(() => {
  const s = p.addSlide(); lightBG(s);
  kicker(s, "Why Google Cloud is the right platform", C.blue);
  title(s, "The architecture maps cleanly to Google Cloud strengths");
  const items = [
    ["robot", C.violet, "Vertex AI · Gemini 2.5 Flash", "One natively-multimodal model — text, reasoning & vision in a managed, secure, high-quota service."],
    ["sitemap", C.blue, "Agent Development Kit (ADK)", "First-class multi-agent orchestration, tools & tracing — less glue code, more capability."],
    ["bolt", C.amber, "Cloud Run", "Serverless, scales to zero, container-native — pay only for live conversations."],
    ["db", C.teal, "Firestore", "Durable, shared session state across instances — context survives autoscaling."],
    ["eye", C.rose, "Cloud Trace & Logging", "Every agent/tool is a span — pinpoint the failing node in a multi-agent turn."],
    ["plug", C.teal, "Extensible to CCAI / Translation", "Clear path to true telephony, agent-assist, and long-tail languages."],
  ];
  const w = (CW - 0.6) / 3, h = 1.95;
  items.forEach(([icon, chip, head, body], i) => {
    const x = M + (i % 3) * (w + 0.3), y = 1.95 + Math.floor(i / 3) * (h + 0.25);
    card(s, { x, y, w, h, icon, chip, head, lines: [body], headSize: 13.5, bodySize: 12 });
  });
  footer(s);
  s.addNotes(
    "Why Google Cloud (90s — the CE angle). 'Every block of this design is a Google Cloud strength: Gemini on Vertex gives us one multimodal model under managed security and quota; " +
    "ADK gives first-class multi-agent orchestration and tracing; Cloud Run is serverless and scales to zero; Firestore gives durable shared state; Cloud Trace makes it debuggable; " +
    "and there's a clean path to CCAI and Vertex Translation. The prototype isn't bolted onto the cloud — it's native to it.'"
  );
})();

// ========================================================== SLIDE 10b — LEARNINGS
(() => {
  const s = p.addSlide(); lightBG(s);
  kicker(s, "What I'd carry into the next build", C.violet);
  title(s, "Key learnings");

  const items = [
    ["brain", C.violet, "“ReAct” is a paradigm, not a class", "Native function-calling IS ReAct — done better; reach for a text-scratchpad planner only when you want a visible plan."],
    ["lock", C.teal, "LLM orchestrates; code transacts", "Route money-affecting / irreversible actions through deterministic, auditable handlers — never the model."],
    ["sitemap", C.blue, "Loop safety is graph shape, not prompts", "Agent-as-tool (no transfer-back), workers with no nested agents, single-pass turns — cycles can't exist by construction."],
    ["sync", C.rose, "A model quirk that bit once bites again", "Encode the remedy as a reusable pattern (thinking_budget=0 fixed both vision and the ReAct advisor)."],
    ["check", C.green, "Test the path production runs", "A cloud-only ADK bug hid behind a green local suite — a CI-sim of the prod fallback is what gave confidence."],
    ["db", C.teal, "Centralize state; keep agents stateless", "One durable session store by session_id; let read-only agents pull memory from tools, not their own state."],
  ];
  const w = (CW - 0.6) / 3, h = 1.98;
  items.forEach(([icon, chip, head, body], i) => {
    const x = M + (i % 3) * (w + 0.3), y = 1.95 + Math.floor(i / 3) * (h + 0.25);
    card(s, { x, y, w, h, icon, chip, head, lines: [body], headSize: 13, bodySize: 11.5 });
  });
  footer(s);
  s.addNotes(
    "Learnings (90s — shows reflection / seniority). 'Six takeaways I'd carry forward: ReAct is a paradigm, not a class — native function-calling is ReAct done better. " +
    "Keep money off the model — LLM orchestrates, code transacts. Loop safety comes from the graph shape, not prompt wording. A model quirk that bites once will bite again, so encode the fix. " +
    "Test the path production actually runs — a CI-sim of the ADK fallback caught what local tests couldn't. And centralize state by session_id while keeping agents stateless where you can. " +
    "All of these are written up in LEARNINGS.md with the war stories behind them.'"
  );
})();

// ====================================================== SLIDE 11 — ROADMAP
(() => {
  const s = p.addSlide(); lightBG(s);
  kicker(s, "Implementation & next steps", C.teal);
  title(s, "From working prototype to production ramp");

  const phases = [
    ["check", C.green, "Now — Prototype (done)", ["Live on Cloud Run + Firestore", "All 4 requirements + safe checkout", "117 tests · CI/CD · /dev portal"]],
    ["users", C.blue, "Pilot — 4–6 wks", ["Multi-user + real SSO (Firebase/IdP)", "Secret Manager · CORS/IAM hardening", "Instrument deflection / conversion / CSAT"]],
    ["plug", C.violet, "Integrate — 6–10 wks", ["Live inventory/OMS + payment provider", "CCAI telephony + agent-assist", "Vertex Translation for long-tail locales"]],
    ["rocket", C.rose, "Scale — ongoing", ["Multi-region · min-instances for latency", "Eval suite + guardrails in CI", "Dynamic skill selection, more sub-agents"]],
  ];
  const w = (CW - 0.9) / 4;
  phases.forEach(([icon, col, head, lines], i) => {
    const x = M + i * (w + 0.3), y = 2.1;
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 3.7, rectRadius: 0.09, fill: { color: C.white }, line: { color: C.border, width: 1 }, shadow: shadow() });
    s.addShape(p.shapes.RECTANGLE, { x, y, w, h: 0.12, fill: { color: col } });
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: x + 0.24, y: y + 0.34, w: 0.66, h: 0.66, rectRadius: 0.13, fill: { color: col } });
    s.addImage({ path: ic(icon), x: x + 0.41, y: y + 0.51, w: 0.32, h: 0.32 });
    s.addText(head, { x: x + 0.22, y: y + 1.12, w: w - 0.44, h: 0.6, margin: 0, fontFace: BF, fontSize: 14, bold: true, color: C.ink, valign: "top" });
    s.addText(lines.map((t) => ({ text: t, options: { bullet: { indent: 12 }, breakLine: true, paraSpaceAfter: 7 } })),
      { x: x + 0.24, y: y + 1.72, w: w - 0.46, h: 1.85, margin: 0, fontFace: BF, fontSize: 11.5, color: C.muted, valign: "top" });
    if (i < 3) s.addImage({ path: ic("arrow"), x: x + w + 0.0, y: y + 1.7, w: 0.28, h: 0.28 });
  });
  s.addText("Low-risk ramp: the prototype already encodes the hard parts (safety gate, context, multimodal); production is integration + hardening, not re-architecture.",
    { x: M, y: 6.05, w: CW, h: 0.6, margin: 0, fontFace: BF, fontSize: 12.5, italic: true, color: C.ink, align: "center" });
  footer(s);
  s.addNotes(
    "Roadmap (90s). 'The prototype already solves the hard parts — the safety gate, shared context, and multimodal. So production is a low-risk ramp: " +
    "Pilot adds real auth, Secret Manager, hardening, and instrumentation. Integrate connects live OMS/payments and CCAI telephony plus Vertex Translation. " +
    "Scale is multi-region, evals in CI, and more sub-agents. Each phase is integration and hardening — not re-architecture.'"
  );
})();

// ====================================================== SLIDE 12 — CLOSE / Q&A
(() => {
  const s = p.addSlide();
  s.background = { path: "bg_dark.png" };
  s.addImage({ path: "logo.png", x: M, y: 0.6, w: 0.8, h: 0.8 });
  s.addText("GOOPHER", { x: M + 0.95, y: 0.66, w: 8, h: 0.7, margin: 0, fontFace: HF, fontSize: 20, bold: true, color: C.white, valign: "middle" });

  s.addText("One agent. Every channel, language & modality.\nSafe to transact. Heals itself.", { x: M, y: 2.0, w: 11.8, h: 1.5, margin: 0, fontFace: HF, fontSize: 32, bold: true, color: C.white, lineSpacingMultiple: 1.05 });

  const tags = ["Sub-agents + context", "Multilingual", "Multichannel", "Multimodal", "Deterministic checkout", "Self-healing", "Vertex AI · ADK · Cloud Run"];
  let cx = M, cy = 3.9;
  tags.forEach((t) => {
    const w = 0.4 + t.length * 0.088;
    if (cx + w > PAGE_W - M) { cx = M; cy += 0.58; }
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x: cx, y: cy, w, h: 0.46, rectRadius: 0.23, fill: { color: "FFFFFF", transparency: 88 }, line: { color: C.violet, width: 1 } });
    s.addText(t, { x: cx, y: cy, w, h: 0.46, margin: 0, align: "center", valign: "middle", fontFace: BF, fontSize: 10.5, bold: true, color: "FFFFFF" });
    cx += w + 0.16;
  });

  s.addText("Thank you — let's discuss.", { x: M, y: 5.15, w: 11.8, h: 0.6, margin: 0, fontFace: HF, fontSize: 24, bold: true, color: "FCA5C0" });
  s.addText("Happy to go deep on: sub-agent routing & context · multilingual & multichannel scale · the transactional gate · loop prevention · CCAI & production integration.",
    { x: M, y: 5.85, w: 11.8, h: 0.7, margin: 0, fontFace: BF, fontSize: 13, color: "D7D3EC" });
  s.addNotes(
    "Close + Q&A (30s, then open the floor). 'To recap: one agent across every channel, language and modality; safe to transact because deterministic code does the transacting; and it heals itself. " +
    "It directly unblocks the engagement and it's native to Google Cloud. I'd love your questions — and I can pull up the live extension or the /dev portal to answer any of them.' " +
    "Keep QUESTION-ANSWER.md open for crisp answers + where-to-point."
  );
})();

if (QA) {
  // text overlap lint within a slide (rough AABB overlap of text boxes)
  // (skipped pairwise spam — only report clear large overlaps)
  console.log("\n==== CONTENT (per slide) ====");
  _slideRefs.forEach((s, i) => {
    console.log(`\n--- Slide ${i + 1} ---`);
    console.log(s.__texts.filter(Boolean).join(" | "));
  });
  console.log("\n==== GEOMETRY ISSUES ====");
  console.log(_issues.length ? _issues.join("\n") : "none (all elements within page bounds)");
  console.log("\nSlides built:", _slideNo);
} else {
  p.writeFile({ fileName: "../PRESENTATION.pptx" }).then((f) => console.log("WROTE", f));
}
