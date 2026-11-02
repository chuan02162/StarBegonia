"""One-off warm-up for the ABR merchant-name cache.

After entering an ABR GUID in the app, existing CommBank bills have not been
looked up yet. This script iterates every distinct CommBank merchant in the
database and resolves its registered business name via ABN Lookup, populating
the ``merchant_enrichments`` cache that the bills list and classification views
read from.

It is idempotent and safe: it only writes cache rows, never bills or entries.

Usage:

    # local
    backend/.venv/bin/python backend/scripts/backfill_abr_enrichments.py

    # production (inside the api container)
    docker compose exec api python scripts/backfill_abr_enrichments.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:  # pragma: no cover - not required inside the container
    pass

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Bill  # noqa: E402
from app.services import abr as abr_service  # noqa: E402
from app.services import secrets as secrets_service  # noqa: E402


def main() -> int:
    app = create_app()
    with app.app_context():
        rows = (
            db.session.query(Bill.household_id, Bill.merchant)
            .filter(
                Bill.source_type == "commbank",
                Bill.merchant.isnot(None),
                Bill.merchant != "",
                Bill.household_id.isnot(None),
            )
            .distinct()
            .all()
        )
        by_household: dict[int, set[str]] = defaultdict(set)
        for household_id, merchant in rows:
            by_household[int(household_id)].add(merchant.strip())

        processed = 0
        enriched = 0
        skipped = 0
        for household_id, merchants in sorted(by_household.items()):
            if not secrets_service.get_secret(household_id, "abr_guid"):
                print(
                    f"household {household_id}: no ABR GUID, "
                    f"skipping {len(merchants)} merchants"
                )
                skipped += len(merchants)
                continue
            print(f"household {household_id}: processing {len(merchants)} merchants…")
            for merchant in sorted(merchants):
                business_name = abr_service.enrich_merchant(merchant, household_id)
                processed += 1
                if business_name:
                    enriched += 1
                    print(f"  {merchant} -> {business_name}")

        print(
            f"\nDone. processed={processed}, enriched={enriched}, "
            f"skipped={skipped}"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
