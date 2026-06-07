// Marketplace storefront: fetches the public catalog and renders every
// department as a professional product grid (real photos, ratings, prices).

// Same-origin when served by the backend (recommended). If you open this file
// directly, point API_BASE at your running backend instead.
const API_BASE = location.origin.startsWith("http")
  ? location.origin
  : "http://localhost:8080";

const DEPT_ICON = { Clothing: "👗", Food: "🍿", Toys: "🧸" };
// Emoji is the GRACEFUL FALLBACK shown only if a product photo fails to load.
const NAME_ICON = [
  [/chip/i, "🥔"], [/oreo|cookie/i, "🍪"], [/peanut|nuts/i, "🥜"],
  [/cola|soda/i, "🥤"], [/cheez|cracker/i, "🧀"], [/bar/i, "🍫"],
  [/denim|jean/i, "👖"], [/maxi|midi|dress|wrap/i, "👗"],
  [/soccer|football/i, "⚽"], [/basketball/i, "🏀"], [/ball/i, "⚽"],
  [/lego|brick/i, "🧱"], [/nerf|blaster|dart/i, "🔫"],
  [/play-?doh|dough/i, "🎨"], [/hot wheels|car/i, "🚗"], [/puzzle/i, "🧩"],
];

function iconFor(p) {
  for (const [re, ic] of NAME_ICON) if (re.test(p.name)) return ic;
  return DEPT_ICON[p.department] || "🛍️";
}

// Product graphics: render the product's emoji as a CRISP, CONSISTENT flat icon
// via the Twemoji CDN (clean vector art — never a random photo, a face, or
// off-topic content). Each product always shows the correct category icon.
function twemojiCode(emoji) {
  const cps = [];
  for (const ch of emoji) {
    const cp = ch.codePointAt(0);
    if (cp !== 0xfe0f) cps.push(cp.toString(16)); // drop the VS16 selector
  }
  return cps.join("-");
}
function imgUrl(p) {
  return `https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/svg/${twemojiCode(iconFor(p))}.svg`;
}

function stars(rating) {
  const r = Math.max(0, Math.min(5, Number(rating) || 0));
  const full = Math.round(r);
  return `<div class="card-rating" title="${r.toFixed(1)} out of 5">
      <span class="stars">${"★".repeat(full)}${"☆".repeat(5 - full)}</span>
      <span class="rating-num">${r.toFixed(1)}</span>
    </div>`;
}

function stockPill(total) {
  if (total <= 0) return `<span class="stock-pill out-stock">Out of stock</span>`;
  if (total < 10) return `<span class="stock-pill low-stock">Only ${total} left</span>`;
  return `<span class="stock-pill in-stock">${total} in stock</span>`;
}

function card(p) {
  const total = p.total_stock ?? 0;
  const options = (p.colors || []).slice(0, 3).join(" · ");
  const off =
    p.list_price > p.sale_price
      ? Math.round((1 - p.sale_price / p.list_price) * 100)
      : 0;
  return `
    <article class="card">
      <div class="card-thumb">
        ${off ? `<span class="card-off">-${off}%</span>` : ""}
        <img class="card-img" src="${imgUrl(p)}" alt="${p.name}" loading="lazy"
             onerror="this.style.display='none';this.nextElementSibling.style.display='grid';" />
        <span class="card-emoji" style="display:none">${iconFor(p)}</span>
      </div>
      <div class="card-body">
        <div class="card-brand">${p.brand}</div>
        <div class="card-name">${p.name}</div>
        ${stars(p.rating)}
        <div class="card-pricerow">
          <span class="card-price">$${p.sale_price.toFixed(2)}</span>
          <span class="card-list">$${p.list_price.toFixed(2)}</span>
        </div>
        <div class="card-options">${options}</div>
        ${stockPill(total)}
        <button class="add-btn" type="button">Add to Cart</button>
      </div>
    </article>`;
}

function section(dept, items) {
  // Per-department class (clothing/food/toys) drives the accent color in CSS.
  const cls = `dept-section ${dept.toLowerCase()}`;
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
    el.innerHTML = `<p class="loading">⚠️ Couldn't load the catalog right now.
      Please refresh in a moment.<br><small>${err.message}</small></p>`;
  }
}

// "Add to Cart" gives a quick visual confirmation (storefront demo — the real
// cart + checkout live in the shopping assistant).
document.addEventListener("click", (e) => {
  const btn = e.target.closest(".add-btn");
  if (!btn || btn.classList.contains("added")) return;
  btn.classList.add("added");
  const label = btn.textContent;
  btn.textContent = "✓ Added to Cart";
  setTimeout(() => { btn.classList.remove("added"); btn.textContent = label; }, 1500);
});

load();
