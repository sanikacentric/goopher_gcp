"""
Database access layer for GOOPHER.

Provides a single `Repository` interface with two interchangeable backends:

  * SQLiteRepository   — zero-config local development & unit tests.
  * FirestoreRepository — Google Cloud Firestore, which has a genuine
                          always-free tier (1 GiB storage, 50K reads/day).

The backend is chosen by `settings.db_backend` ("sqlite" | "firestore") so the
exact same agent / tool / API code runs locally and on Cloud Run unchanged.

Both backends are seeded from `backend/data/goopher_catalog.json`.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from abc import ABC, abstractmethod
from typing import Optional

from ..config import DATA_FILE, get_settings
from ..models.schemas import Customer, Order, Product

logger = logging.getLogger(__name__)


def load_seed() -> dict:
    """Read the synthetic store catalog (clothing & food) from disk."""
    with open(DATA_FILE, "r", encoding="utf-8") as fh:
        return json.load(fh)


def catalog_fingerprint(data: Optional[dict] = None) -> str:
    """Stable hash of the catalog's products, used to detect when the on-disk
    catalog has changed so a persistent backend (Firestore) can auto-resync."""
    data = data or load_seed()
    blob = json.dumps(data.get("products", []), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Abstract interface
# --------------------------------------------------------------------------- #
class Repository(ABC):
    """Backend-agnostic data access used by tools, agents, and the API."""

    @abstractmethod
    def seed(self) -> None: ...

    @abstractmethod
    def list_products(self) -> list[Product]: ...

    @abstractmethod
    def get_product(self, sku: str) -> Optional[Product]: ...

    @abstractmethod
    def get_order(self, order_id: str) -> Optional[Order]: ...

    @abstractmethod
    def list_orders_for_customer(self, customer_id: str) -> list[Order]: ...

    @abstractmethod
    def save_order(self, order: Order) -> None:
        """Insert or update an order (used when a customer places a new order)."""

    @abstractmethod
    def save_order_placed(self, record: dict) -> None:
        """Insert a fulfilled-order record into the ORDER_PLACED table (order
        management). `record` is a JSON-serializable dict keyed by order_id."""

    @abstractmethod
    def get_customer_by_email(self, email: str) -> Optional[tuple[Customer, str]]:
        """Return (customer, password_hash) or None."""

    # ---- Shared helpers (backend-independent) ----

    # Words that carry no discriminating signal in this catalog (generic category
    # words that match EVERY item in a department) or are conversational filler.
    # Dropping them means "what's the price of the cheese snack crackers" is
    # matched on the words that matter (cheese, crackers) instead of "snack",
    # which would otherwise match every food item.
    _STOPWORDS = {
        # clothing category words (match every clothing item)
        "dress", "dresses", "casual", "women", "womens", "woman", "ladies",
        "clothing", "apparel", "outfit", "wear",
        # food category words (match every food item)
        "snack", "snacks", "food", "foods", "grocery", "groceries", "item",
        "items", "product", "products", "drink", "drinks", "beverage", "beverages",
        # toys category words (match every toy item)
        "toy", "toys", "game", "games", "plaything", "playthings",
        # conversational filler
        "show", "me", "find", "get", "the", "a", "an", "can", "could", "let",
        "know", "please", "price", "cost", "priced", "do", "you", "have", "in",
        "of", "for", "want", "looking", "look", "need", "i", "my", "is", "it",
        "this", "that", "like", "one", "any", "some", "with", "and", "or", "to",
        "on", "under", "below", "less", "than", "whats", "what", "tell", "about",
        "there", "are", "buy", "purchase", "available", "stock", "much", "how",
    }

    def search_products(self, query: str = "", color: str = "", size: str = "",
                        max_price: float | None = None) -> list[Product]:
        """
        Search the catalog by keyword + optional facet filters.

        The free-text `query` is tokenized into significant words (filler/category
        words removed) and each product is SCORED by how many of those words appear
        in its searchable text. This replaces the old whole-string `in` check,
        which failed whenever the user typed a full sentence rather than an exact
        substring of a product description.

        Behaviour:
          * Department word only (e.g. "snacks", "dresses") -> return that whole
            department (browsing an aisle), still honoring color/size/price.
          * No significant words  -> treat as a browse (all products pass the text
            check); the color/size/price filters still apply.
          * Has significant words -> keep only products matching at least one, and
            return them ranked by match count (best matches first).
        """
        import re

        words = re.findall(r"[a-z0-9]+", query.lower())
        raw_tokens = [t for t in words if t not in self._STOPWORDS and len(t) > 1]

        # If the shopper only named a department/category (e.g. "show me snacks",
        # "what dresses do you have"), scope the results to that department rather
        # than returning the whole store or nothing. These words are stopwords for
        # keyword matching, so we detect them from the raw words here.
        dept_filter: str | None = None
        if {"snack", "snacks", "food", "foods", "drink", "drinks", "beverage",
            "beverages", "grocery", "groceries"} & set(words):
            dept_filter = "Food"
        elif {"dress", "dresses", "clothing", "apparel", "outfit"} & set(words):
            dept_filter = "Clothing"
        elif {"toy", "toys", "game", "games", "plaything", "playthings"} & set(words):
            dept_filter = "Toys"

        # Expand each token with a naive singular form so plural queries match,
        # e.g. "oreos" -> also try "oreo", "cookies" -> "cookie", "chips" ->
        # "chip". We keep BOTH forms; matching the haystack on either counts.
        def singularize(word: str) -> str:
            if word.endswith("ies") and len(word) > 4:
                return word[:-3] + "y"
            if word.endswith("es") and len(word) > 4:
                return word[:-2]
            if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
                return word[:-1]
            return word

        tokens: list[str] = []
        for t in raw_tokens:
            tokens.append(t)
            s = singularize(t)
            if s != t:
                tokens.append(s)
        # De-dupe while preserving order.
        tokens = list(dict.fromkeys(tokens))

        scored: list[tuple[int, Product]] = []
        for p in self.list_products():
            # Strong fields = name/brand/colors(flavors)/category; a match here
            # means the shopper named the product. Weak field = description, where
            # an incidental word ("chocolate" in a granola bar's blurb) shouldn't
            # rank as high as a name match. Sizes/material are weak too.
            strong = " ".join([p.name, p.brand, " ".join(p.colors), p.category]).lower()
            weak = " ".join([p.description, p.material, " ".join(p.sizes)]).lower()

            # Facet filters (applied regardless of free-text query).
            if dept_filter and p.department != dept_filter:
                continue
            if color and color.lower() not in [c.lower() for c in p.colors]:
                continue
            if size and size.upper() not in [s.upper() for s in p.sizes]:
                continue
            if max_price is not None and p.sale_price > max_price:
                continue

            if tokens:
                # Weight strong-field hits 3x weak-field hits so the product the
                # shopper actually named ranks well above incidental mentions.
                score = sum(3 for t in tokens if t in strong)
                score += sum(1 for t in tokens if t in weak and t not in strong)
                if score == 0:
                    continue
            else:
                score = 0  # browse: keep all that passed the facet filters
            scored.append((score, p))

        if not scored:
            return []

        # Highest score first; stable for equal scores (keeps seed order).
        scored.sort(key=lambda sp: sp[0], reverse=True)

        # Relevance cutoff: when the query produced real keyword matches, only
        # return products whose score is close to the best. This stops a specific
        # ask ("cheese crackers") from also returning every weakly-related item.
        if tokens:
            best = scored[0][0]
            if best > 0:
                threshold = max(1, best * 0.6)
                scored = [sp for sp in scored if sp[0] >= threshold]
        return [p for _, p in scored]

    def check_stock(self, variant_id: str) -> Optional[dict]:
        """Return live stock info for a single variant across the catalog."""
        for p in self.list_products():
            for v in p.variants:
                if v.variant_id == variant_id:
                    return {
                        "variant_id": v.variant_id,
                        "product": p.name,
                        "brand": p.brand,
                        "color": v.color,
                        "size": v.size,
                        "stock": v.stock,
                        "in_stock": v.stock > 0,
                        "sale_price": p.sale_price,
                    }
        return None


# --------------------------------------------------------------------------- #
# SQLite backend
# --------------------------------------------------------------------------- #
class SQLiteRepository(Repository):
    def __init__(self, path: str):
        self.path = path
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        # Products/orders are stored as JSON blobs keyed by id — simple and
        # sufficient for a demo, and it mirrors the document model of Firestore.
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (sku TEXT PRIMARY KEY, doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, customer_id TEXT, doc TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS customers (email TEXT PRIMARY KEY, doc TEXT NOT NULL, password_hash TEXT);
            CREATE TABLE IF NOT EXISTS order_placed (order_id TEXT PRIMARY KEY, customer_id TEXT, doc TEXT NOT NULL);
            """
        )
        self._conn.commit()

    def seed(self) -> None:
        data = load_seed()
        cur = self._conn.cursor()
        cur.execute("DELETE FROM products")
        cur.execute("DELETE FROM orders")
        cur.execute("DELETE FROM customers")
        for p in data["products"]:
            cur.execute("INSERT INTO products VALUES (?,?)", (p["sku"], json.dumps(p)))
        for o in data["orders"]:
            cur.execute("INSERT INTO orders VALUES (?,?,?)", (o["order_id"], o["customer_id"], json.dumps(o)))
        for c in data["customers"]:
            cust = {k: v for k, v in c.items() if k != "password_hash"}
            cur.execute("INSERT INTO customers VALUES (?,?,?)", (c["email"], json.dumps(cust), c["password_hash"]))
        self._conn.commit()

    def list_products(self) -> list[Product]:
        rows = self._conn.execute("SELECT doc FROM products").fetchall()
        return [Product(**json.loads(r["doc"])) for r in rows]

    def get_product(self, sku: str) -> Optional[Product]:
        row = self._conn.execute("SELECT doc FROM products WHERE sku=?", (sku,)).fetchone()
        return Product(**json.loads(row["doc"])) if row else None

    def get_order(self, order_id: str) -> Optional[Order]:
        row = self._conn.execute("SELECT doc FROM orders WHERE order_id=?", (order_id,)).fetchone()
        return Order(**json.loads(row["doc"])) if row else None

    def list_orders_for_customer(self, customer_id: str) -> list[Order]:
        rows = self._conn.execute("SELECT doc FROM orders WHERE customer_id=?", (customer_id,)).fetchall()
        return [Order(**json.loads(r["doc"])) for r in rows]

    def save_order(self, order: Order) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO orders VALUES (?,?,?)",
            (order.order_id, order.customer_id, json.dumps(order.model_dump())),
        )
        self._conn.commit()

    def save_order_placed(self, record: dict) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO order_placed VALUES (?,?,?)",
            (record["order_id"], record.get("customer_id", ""), json.dumps(record)),
        )
        self._conn.commit()

    def get_customer_by_email(self, email: str) -> Optional[tuple[Customer, str]]:
        row = self._conn.execute("SELECT doc, password_hash FROM customers WHERE email=?", (email,)).fetchone()
        if not row:
            return None
        return Customer(**json.loads(row["doc"])), row["password_hash"]


# --------------------------------------------------------------------------- #
# Firestore backend (Google Cloud free tier)
# --------------------------------------------------------------------------- #
class FirestoreRepository(Repository):
    def __init__(self, project: str, database: str = "(default)"):
        # Imported lazily so local/SQLite runs don't need the GCP SDK installed.
        from google.cloud import firestore  # type: ignore

        self.db = firestore.Client(project=project, database=database)

    def seed(self) -> None:
        data = load_seed()
        batch = self.db.batch()
        for p in data["products"]:
            batch.set(self.db.collection("products").document(p["sku"]), p)
        for o in data["orders"]:
            batch.set(self.db.collection("orders").document(o["order_id"]), o)
        for c in data["customers"]:
            batch.set(self.db.collection("customers").document(c["email"]), c)
        batch.commit()
        self._stamp_catalog(data)

    # --- Auto-sync ---------------------------------------------------------- #
    def _stamp_catalog(self, data: Optional[dict] = None) -> None:
        """Record the catalog fingerprint so we can detect future changes."""
        data = data or load_seed()
        self.db.collection("_meta").document("catalog").set(
            {"fingerprint": catalog_fingerprint(data), "product_count": len(data["products"])}
        )

    def _sync_products(self, data: dict) -> None:
        """Make the `products` collection exactly match the on-disk catalog:
        upsert every current product and delete any stale SKUs. Runtime data
        (orders, customers) is left untouched."""
        catalog_skus = {p["sku"] for p in data["products"]}
        batch = self.db.batch()
        for p in data["products"]:
            batch.set(self.db.collection("products").document(p["sku"]), p)
        for doc in self.db.collection("products").stream():
            if doc.id not in catalog_skus:
                batch.delete(doc.reference)
        batch.commit()

    def sync_catalog_if_changed(self) -> bool:
        """If the on-disk catalog differs from what Firestore was last seeded
        with, re-sync. Returns True if a re-sync happened.

        * Fresh database (no fingerprint): full seed (products + demo orders +
          demo customers).
        * Existing database, catalog changed: re-sync products only, preserving
          any orders/customers created at runtime.
        """
        data = load_seed()
        fp = catalog_fingerprint(data)
        snap = self.db.collection("_meta").document("catalog").get()
        if snap.exists:
            if snap.to_dict().get("fingerprint") == fp:
                return False  # already up to date
            self._sync_products(data)
        else:
            self.seed()
            return True  # seed() already stamped the catalog
        self._stamp_catalog(data)
        return True

    def list_products(self) -> list[Product]:
        return [Product(**d.to_dict()) for d in self.db.collection("products").stream()]

    def get_product(self, sku: str) -> Optional[Product]:
        snap = self.db.collection("products").document(sku).get()
        return Product(**snap.to_dict()) if snap.exists else None

    def get_order(self, order_id: str) -> Optional[Order]:
        snap = self.db.collection("orders").document(order_id).get()
        return Order(**snap.to_dict()) if snap.exists else None

    def list_orders_for_customer(self, customer_id: str) -> list[Order]:
        q = self.db.collection("orders").where("customer_id", "==", customer_id).stream()
        return [Order(**d.to_dict()) for d in q]

    def save_order(self, order: Order) -> None:
        self.db.collection("orders").document(order.order_id).set(order.model_dump())

    def save_order_placed(self, record: dict) -> None:
        self.db.collection("order_placed").document(record["order_id"]).set(record)

    def get_customer_by_email(self, email: str) -> Optional[tuple[Customer, str]]:
        snap = self.db.collection("customers").document(email).get()
        if not snap.exists:
            return None
        doc = snap.to_dict()
        pwd = doc.pop("password_hash", "")
        return Customer(**{k: v for k, v in doc.items() if k in Customer.model_fields}), pwd


# --------------------------------------------------------------------------- #
# Factory (singleton per process)
# --------------------------------------------------------------------------- #
_repo: Optional[Repository] = None


def get_repository() -> Repository:
    """Return the configured repository, creating & seeding it on first use."""
    global _repo
    if _repo is not None:
        return _repo

    settings = get_settings()
    if settings.db_backend == "firestore":
        _repo = FirestoreRepository(settings.google_cloud_project, settings.firestore_database)
        # Firestore is persistent, so we don't re-seed on every boot. But if the
        # on-disk catalog changed (e.g. a new department was added), re-sync the
        # products collection automatically so deploys don't require a manual
        # seed. Runtime orders/customers are preserved.
        if settings.auto_seed_firestore:
            try:
                if _repo.sync_catalog_if_changed():
                    logger.info("Firestore catalog re-synced from goopher_catalog.json")
            except Exception as exc:  # never let a sync failure block startup
                logger.warning("Firestore catalog auto-sync skipped: %s", exc)
    else:
        _repo = SQLiteRepository(settings.sqlite_path)
        _repo.seed()  # SQLite is ephemeral in containers, so seed on boot.
    return _repo
