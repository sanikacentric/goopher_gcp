// GOOPHER storefront: fetches the public catalog and renders both departments.
// This page is a plain storefront — the GOOPHER *extension* (side panel) is what
// provides the conversational assistant on top of it. We do NOT embed a chat
// widget here, by design: GOOPHER lives in the Chrome extension.

// Same-origin when served by the backend (recommended). If you open this file
// directly, point API_BASE at your running backend instead.
const API_BASE = location.origin.startsWith("http")
  ? location.origin
  : "http://localhost:8080";

const DEPT_ICON = { Clothing: "👗", Food: "🍿", Toys: "🧸" };
// Per-item emoji so the demo looks lively without real product images.
const ITEM_ICON = {
  Dress: "👗", "Casual Dress": "👗", Snacks: "🍪", Beverages: "🥤",
  "Balls & Sports": "🏀", "Building Sets": "🧱", "Outdoor & Action": "🔫",
  "Arts & Crafts": "🎨", Vehicles: "🚗", Puzzles: "🧩",
};
const NAME_ICON = [
  [/chip/i, "🥔"], [/oreo|cookie/i, "🍪"], [/peanut|nuts/i, "🥜"],
  [/cola|soda/i, "🥤"], [/cheez|cracker/i, "🧀"], [/bar/i, "🍫"],
  [/denim|jean/i, "👖"], [/maxi|midi|dress|wrap/i, "👗"],
  [/basketball|ball/i, "🏀"], [/lego|brick/i, "🧱"], [/nerf|blaster|dart/i, "🔫"],
  [/play-?doh|dough/i, "🎨"], [/hot wheels|car/i, "🚗"], [/puzzle/i, "🧩"],
];

function iconFor(p) {
  for (const [re, ic] of NAME_ICON) if (re.test(p.name)) return ic;
  return ITEM_ICON[p.category] || DEPT_ICON[p.department] || "🛍️";
}

function stockPill(total) {
  if (total <= 0) return `<span class="stock-pill out-stock">Out of stock</span>`;
  if (total < 10) return `<span class="stock-pill low-stock">Only ${total} left</span>`;
  return `<span class="stock-pill in-stock">${total} in stock</span>`;
}

function card(p) {
  const total = p.total_stock ?? 0;
  const options = (p.colors || []).slice(0, 3).join(" · ");
  const ask =
    p.department === "Food"
      ? `Ask GOOPHER: “is ${p.name.split(" ").slice(0, 2).join(" ")} in stock?”`
      : `Ask GOOPHER: “show me ${p.name.split(" ").slice(1, 3).join(" ").toLowerCase()}”`;
  return `
    <article class="card">
      <div class="card-thumb">${iconFor(p)}</div>
      <div class="card-body">
        <div class="card-brand">${p.brand}</div>
        <div class="card-name">${p.name}</div>
        <div>
          <span class="card-price">$${p.sale_price.toFixed(2)}</span>
          <span class="card-list">$${p.list_price.toFixed(2)}</span>
        </div>
        <div class="card-options">${options}</div>
        ${stockPill(total)}
        <div class="card-sku">${p.sku}</div>
        <div class="ask-hint">${ask}</div>
      </div>
    </article>`;
}

function section(dept, items) {
  const cls = dept === "Food" ? "dept-section food" : "dept-section";
  return `
    <section class="${cls}" id="${dept}">
      <h2 class="dept-title">${DEPT_ICON[dept] || ""} ${dept}
        <span class="dept-badge">${items.length} items</span>
      </h2>
      <div class="grid">${items.map(card).join("")}</div>
    </section>`;
}

async function load() {
  const el = document.getElementById("catalog");
  try {
    const res = await fetch(`${API_BASE}/catalog`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    // Show Clothing first, then Food, then Toys, then anything else.
    const order = ["Clothing", "Food", "Toys"];
    const depts = [
      ...order.filter((d) => data.catalog[d]),
      ...Object.keys(data.catalog).filter((d) => !order.includes(d)),
    ];
    el.innerHTML = depts.map((d) => section(d, data.catalog[d])).join("");
  } catch (err) {
    el.innerHTML = `<p class="loading">⚠️ Couldn't load the catalog from ${API_BASE}.
      Make sure the GOOPHER backend is running (uvicorn on port 8080).<br><small>${err.message}</small></p>`;
  }
}

load();
