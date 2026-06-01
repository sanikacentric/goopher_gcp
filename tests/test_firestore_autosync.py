"""
Unit tests for FirestoreRepository.sync_catalog_if_changed (auto-reseed).

These use a tiny in-memory fake of the Firestore client surface the repository
touches, so they run without any GCP dependency or network. They lock in the
behavior that makes catalog changes (e.g. adding a Toys department) show up in
the cloud automatically, while preserving runtime orders/customers.
"""
from __future__ import annotations

from backend.app.db import database
from backend.app.db.database import FirestoreRepository, catalog_fingerprint, load_seed


# --------------------------------------------------------------------------- #
# Minimal Firestore fake
# --------------------------------------------------------------------------- #
class _Snap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        self.reference = None  # set by _Doc.stream wrapper

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _Doc:
    def __init__(self, coll, doc_id):
        self._coll = coll
        self.id = doc_id

    def get(self):
        return _Snap(self.id, self._coll._docs.get(self.id))

    def set(self, data):
        self._coll._docs[self.id] = dict(data)


class _Coll:
    def __init__(self):
        self._docs: dict[str, dict] = {}

    def document(self, doc_id):
        return _Doc(self, doc_id)

    def stream(self):
        for doc_id in list(self._docs):
            snap = _Snap(doc_id, self._docs[doc_id])
            snap.reference = _Doc(self, doc_id)
            yield snap


class _Batch:
    def __init__(self, db):
        self._db = db
        self._ops: list = []

    def set(self, doc, data):
        self._ops.append(("set", doc, dict(data)))

    def delete(self, doc):
        self._ops.append(("delete", doc, None))

    def commit(self):
        for op, doc, data in self._ops:
            if op == "set":
                doc.set(data)
            else:
                doc._coll._docs.pop(doc.id, None)
        self._ops.clear()


class _FakeDB:
    def __init__(self):
        self._colls: dict[str, _Coll] = {}

    def collection(self, name):
        return self._colls.setdefault(name, _Coll())

    def batch(self):
        return _Batch(self)


def _make_repo() -> FirestoreRepository:
    repo = FirestoreRepository.__new__(FirestoreRepository)  # skip __init__ (no GCP)
    repo.db = _FakeDB()
    return repo


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_fresh_db_full_seed():
    repo = _make_repo()
    changed = repo.sync_catalog_if_changed()
    assert changed is True
    # Products, orders, customers all seeded.
    data = load_seed()
    assert len(repo.db.collection("products")._docs) == len(data["products"])
    assert len(repo.db.collection("orders")._docs) == len(data["orders"])
    # Fingerprint stamped.
    meta = repo.db.collection("_meta").document("catalog").get().to_dict()
    assert meta["fingerprint"] == catalog_fingerprint()


def test_unchanged_catalog_is_noop():
    repo = _make_repo()
    repo.sync_catalog_if_changed()
    # Second call sees a matching fingerprint -> no re-sync.
    assert repo.sync_catalog_if_changed() is False


def test_changed_catalog_resyncs_products_only(monkeypatch):
    repo = _make_repo()
    repo.sync_catalog_if_changed()  # initial seed

    # Simulate a runtime-created order that must NOT be wiped on re-sync.
    repo.db.collection("orders").document("ORD-RUNTIME").set({"order_id": "ORD-RUNTIME"})
    # Simulate a stale product no longer in the catalog.
    repo.db.collection("products").document("OLD-SKU-0000").set({"sku": "OLD-SKU-0000"})

    # Make the on-disk catalog look different (drop a product) so the fingerprint changes.
    base = load_seed()
    trimmed = dict(base)
    trimmed["products"] = base["products"][:-1]
    monkeypatch.setattr(database, "load_seed", lambda: trimmed)

    changed = repo.sync_catalog_if_changed()
    assert changed is True

    prod_ids = set(repo.db.collection("products")._docs)
    assert "OLD-SKU-0000" not in prod_ids          # stale SKU deleted
    assert prod_ids == {p["sku"] for p in trimmed["products"]}
    # Runtime order survived the product re-sync.
    assert "ORD-RUNTIME" in repo.db.collection("orders")._docs
