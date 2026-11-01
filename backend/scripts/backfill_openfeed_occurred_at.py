"""One-off backfill: set CommBank bill `occurred_at` from the real transaction
time instead of the bank posting time.

OpenFeed exposes three dates per transaction: ``postedDateTime`` (posting),
``executionDateTime`` (real transaction time, preferred), and date-only
``valueDate`` / ``transactionDate``.  Before this fix the sync pipeline picked
``postedDateTime``, so card purchases showed the settlement day (often a day
later) instead of the purchase day.

This script re-fetches each connected person's CommBank feed and updates only
``bills.occurred_at`` in place, matched by the stable ``openfeed:{transactionId}``
external id.  Entries, categories, manual overrides and dedup/internal-transfer
links are left untouched.

Usage:

    # local
    backend/.venv/bin/python backend/scripts/backfill_openfeed_occurred_at.py

    # production (inside the api container, where .env is already loaded)
    docker compose exec api python scripts/backfill_openfeed_occurred_at.py

    # preview only
    ... --dry-run

Options:
    --dry-run          print what would change without writing
    --lookback-days N  fetch window in days (default 730, the CDR maximum)
"""

from __future__ import annotations

import argparse
import sys
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
from app.models import Bill, SourceCredential  # noqa: E402
from app.security.crypto import decrypt_payload, encrypt_payload  # noqa: E402
from app.sources.openfeed import (  # noqa: E402
    MAX_LOOKBACK_DAYS,
    OpenFeedAdapter,
    _pick_datetime,
)


def _transactions_by_id(payload: dict) -> tuple[dict[str, object], str | None]:
    adapter = OpenFeedAdapter()
    runtime = {**payload}
    # Force a full-history fetch: ignore any saved narrow date range.
    for key in ("from", "to", "since"):
        runtime.pop(key, None)
    runtime["lookback_days"] = payload.get("lookback_days") or MAX_LOOKBACK_DAYS

    raw = adapter.fetch_raw(runtime)
    data = raw.data or {}
    rows = data.get("transactions") or []
    by_id: dict[str, object] = {}
    for row in rows:
        tid = str(row.get("transactionId") or "").strip()
        if not tid:
            continue
        occurred = _pick_datetime(row)
        if occurred is not None:
            by_id[tid] = occurred
    return by_id, data.get("refresh_token")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=MAX_LOOKBACK_DAYS,
        help=f"fetch window in days (default {MAX_LOOKBACK_DAYS})",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        creds = SourceCredential.query.filter_by(source_type="commbank").all()
        if not creds:
            print("No CommBank credentials found; nothing to do.")
            return 0

        total_updated = 0
        total_missing = 0
        for cred in creds:
            print(f"\n== person {cred.person_id} ==")
            try:
                payload = decrypt_payload(cred.payload_encrypted)
            except Exception as exc:  # noqa: BLE001
                print(f"  cannot decrypt credential: {exc}")
                continue

            payload = {**payload, "lookback_days": args.lookback_days}
            try:
                by_id, new_refresh = _transactions_by_id(payload)
            except Exception as exc:  # noqa: BLE001
                print(f"  fetch failed: {exc}")
                continue

            print(f"  fetched {len(by_id)} transactions with a usable datetime")

            if new_refresh and new_refresh != payload.get("refresh_token"):
                payload = {**payload, "refresh_token": new_refresh}
                if not args.dry_run:
                    cred.payload_encrypted = encrypt_payload(payload)
                    db.session.commit()
                print("  persisted rotated refresh token")

            bills = Bill.query.filter_by(
                person_id=cred.person_id, source_type="commbank"
            ).all()
            updated = 0
            unchanged = 0
            missing = 0
            for bill in bills:
                external_id = bill.external_id or ""
                if not external_id.startswith("openfeed:"):
                    continue
                occurred = by_id.get(external_id[len("openfeed:") :])
                if occurred is None:
                    missing += 1
                    continue
                if bill.occurred_at == occurred:
                    unchanged += 1
                    continue
                updated += 1
                if not args.dry_run:
                    bill.occurred_at = occurred

            total_updated += updated
            total_missing += missing
            print(
                f"  bills: {updated} updated, {unchanged} already correct, "
                f"{missing} not found in feed"
            )
            if updated and not args.dry_run:
                db.session.commit()

        suffix = " (dry-run, nothing written)" if args.dry_run else ""
        print(
            f"\nDone. updated={total_updated}, missing={total_missing}{suffix}"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
