"""
Database access layer for GOOPHER.

Provides a single `Repository` interface with two interchangeable backends:

  * SQLiteRepository   — zero-config local development & unit tests.
  * FirestoreRepository — Google Cloud Firestore, which has a genuine
                          always-free tier (1 GiB storage, 50K reads/day).

The backend is chosen by `settings.db_backend` ("sqlite" | "firestore") so the
exact same agent / MCP / API code runs locally and on Cloud Run unchanged.

Both backends are seeded from `backend/data/jcpenney_casual_dresses.json`.
"""
from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from typing import Optional

from ..config import DATA_FILE, get_settings
from ..models.schemas import Customer, Order, Product


def load_seed() -> dict:
    """Read the synthetic JCPenney casual-dress dataset from disk."""
    with open(DATA_FILE, "r", encoding="utf-8") as fh:
        return json.load(fh)


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
    def get_customer_by_email(self, email: str) -> Optional[tuple[Customer, str]]:
        """Return (customer, password_hash) or None."""

    # ---- Shared helpers (backend-independent) ----
    def search_products(self, query: str = "", color: str = "", size: str = "",
                        max_price: float | None = None) -> list[Product]:
        """Filter the catalog in memory. Cheap because the demo catalog is small."""
        q = query.lower().strip()
        results: list[Product] = []
        for p in self.list_products():
            haystack = f"{p.name} {p.brand} {p.description} {p.material}".lower()
            if q and q not in haystack:
                continue
            if color and color.lower() not in [c.lower() for c in p.colors]:
                continue
            if size and size.upper() not in [s.upper() for s in p.sizes]:
                continue
            if max_price is not None and p.sale_price > max_price:
                continue
            results.append(p)
        return results

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
    else:
        _repo = SQLiteRepository(settings.sqlite_path)
        _repo.seed()  # SQLite is ephemeral in containers, so seed on boot.
    return _repo
