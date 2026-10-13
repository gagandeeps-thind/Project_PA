"""Crystal ledger backfill + reconciliation.

Two modes:

  Backfill (default):
      python scripts/reconcile_ledger.py
    For every user that has NO CrystalLedger history, write a single 'opening_balance'
    backfill row equal to their current `mana_crystals`, so that
        sum(CrystalLedger.delta) == mana_crystals
    holds for every user. Users that already have ledger rows are left untouched
    (idempotent — running twice is a no-op).

  Check (CI gate):
      python scripts/reconcile_ledger.py --check
    Assert sum(CrystalLedger.delta) == mana_crystals for EVERY user, and that no ledger
    rows belong to a user id that no longer exists. Prints each problem and exits non-zero
    if any is found. Does NOT mutate.

Run from the Osiris_backend directory (so `import database/models` resolves). Honors the
same OSIRIS_DATABASE_URL / SQLite URL the app uses.
"""
import argparse
import os
import sys

# Make the backend package importable regardless of invocation cwd.
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, BACKEND_DIR)

# The fail-closed boot check needs an explicit env for a non-prod run.
os.environ.setdefault("OSIRIS_ENV", "dev")

from sqlalchemy import func  # noqa: E402

import database  # noqa: E402
import models  # noqa: E402


def _ledger_sum_by_user(db):
    """Return {user_id: sum_of_deltas} for users that have at least one ledger row."""
    rows = (
        db.query(models.CrystalLedger.user_id, func.coalesce(func.sum(models.CrystalLedger.delta), 0))
        .group_by(models.CrystalLedger.user_id)
        .all()
    )
    return {uid: total for uid, total in rows}


def backfill(db) -> int:
    """Write one opening_balance row for every user with no ledger history. Returns count."""
    have_history = set(_ledger_sum_by_user(db).keys())
    created = 0
    for user in db.query(models.User).all():
        if user.id in have_history:
            continue
        balance = user.mana_crystals or 0
        # apply_crystal_delta would double-count (it adds delta to mana_crystals). For a
        # backfill we want a row whose delta == current balance and balance_after == balance
        # WITHOUT changing the wallet, so we write the row directly.
        db.add(models.CrystalLedger(
            user_id=user.id,
            delta=balance,
            balance_after=balance,
            reason_code="opening_balance",
            note="Backfill: reconcile pre-ledger balance",
        ))
        created += 1
    db.commit()
    return created


def check(db) -> int:
    """Return the number of problems found (0 == healthy): users whose ledger sum !=
    mana_crystals, plus user ids that have ledger rows but no users row.

    Orphaned rows matter even though no wallet reads them: SQLite reuses a freed user id, so
    the next account created inherits the orphaned history and fails reconciliation for no
    reason of its own. Production keeps erased users as tombstones, so any orphan means a
    hard delete skipped the ledger."""
    sums = _ledger_sum_by_user(db)
    discrepancies = 0
    user_ids = set()
    for user in db.query(models.User).all():
        user_ids.add(user.id)
        ledger_total = sums.get(user.id, 0)
        wallet = user.mana_crystals or 0
        if ledger_total != wallet:
            discrepancies += 1
            print(
                f"  DISCREPANCY user {user.id} ({user.email}): "
                f"ledger sum={ledger_total} but mana_crystals={wallet}"
            )
    for uid in sorted(set(sums) - user_ids):
        discrepancies += 1
        print(f"  ORPHAN ledger rows for missing user {uid}: sum={sums[uid]}")
    return discrepancies


def main() -> int:
    parser = argparse.ArgumentParser(description="Crystal ledger backfill / reconciliation.")
    parser.add_argument(
        "--check", action="store_true",
        help="Verify sum(deltas)==mana_crystals for every user; exit non-zero on any mismatch.",
    )
    args = parser.parse_args()

    # Ensure tables exist (lets --check run on a fresh CI DB even before any seed).
    models.Base.metadata.create_all(bind=database.engine)

    db = database.SessionLocal()
    try:
        if args.check:
            bad = check(db)
            total = db.query(models.User).count()
            if bad:
                print(f"FAIL: {bad} ledger problem(s) found across {total} user(s).")
                return 1
            print(f"OK: all {total} user(s) reconcile (sum(deltas) == mana_crystals).")
            return 0
        else:
            created = backfill(db)
            print(f"Backfill complete: {created} opening_balance row(s) written.")
            # Self-verify after backfill.
            bad = check(db)
            if bad:
                print(f"WARNING: {bad} user(s) still out of balance after backfill.")
                return 1
            return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
