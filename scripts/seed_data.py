"""
Seed the configured database with the JCPenney casual-dress dataset.

Usage:
    # local SQLite (default)
    python scripts/seed_data.py

    # Firestore (set these first)
    set DB_BACKEND=firestore
    set GOOGLE_CLOUD_PROJECT=your-project
    python scripts/seed_data.py
"""
import sys
from pathlib import Path

# Make `backend` importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.config import get_settings  # noqa: E402
from backend.app.db.database import get_repository  # noqa: E402


def main() -> None:
    settings = get_settings()
    repo = get_repository()
    repo.seed()
    products = repo.list_products()
    print(f"Seeded {settings.db_backend} backend with {len(products)} products.")
    for p in products:
        units = sum(v.stock for v in p.variants)
        print(f"  {p.sku:16s} {p.name[:40]:40s} ${p.sale_price:6.2f}  {units} units")


if __name__ == "__main__":
    main()
