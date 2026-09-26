"""Player-side Mana Crystal ledger service (audit §3.2).

This module is the SINGLE authorized writer of `User.mana_crystals`. Every crystal
movement on the player side goes through `apply_crystal_delta`, which:

  1. computes `balance_after = user.mana_crystals + delta`,
  2. refuses to let a wallet go negative (defense-in-depth; callers already pre-check
     funds before debiting),
  3. mutates `user.mana_crystals`, and
  4. appends an append-only `CrystalLedger` row.

It deliberately does NOT commit — the calling endpoint owns the transaction so the
balance mutation and the ledger row land atomically (or roll back together).

Invariant guaranteed for any user touched only through this function:
    sum(CrystalLedger.delta WHERE user_id == u) == User(u).mana_crystals
"""
from __future__ import annotations

from sqlalchemy.orm import Session

import models


class InsufficientCrystalsError(ValueError):
    """Raised when applying a delta would drive a wallet balance below zero.

    Endpoints pre-check funds and surface a 402 before calling the service, so hitting
    this is a logic bug, not a normal user-facing condition — it is the last line of
    defense against minting value out of thin air."""


# Recognized reason codes. Not enforced at the DB level, but the service rejects anything
# unknown so a typo can't silently create an unauditable category.
VALID_REASON_CODES = frozenset({
    "opening_balance",
    "vault_lock",
    "siege_out_of_pocket",
    "siege_win_payout",
    "siege_forfeit",
    "bounty_reward",
    # Phase 3: real-money one-way top-up. Player paid via Stripe; crystals are credited
    # exactly once per PaymentIntent (CrystalPurchase.stripe_payment_intent_id is unique and
    # the webhook only credits a row that is not already 'succeeded'). This is a PURCHASE,
    # not a cash-out — there is no inverse (crystals -> money) path anywhere by design.
    "crystal_purchase",
})


def apply_crystal_delta(
    db: Session,
    user: "models.User",
    delta: int,
    reason_code: str,
    *,
    related_siege_id: int | None = None,
    related_bounty_id: int | None = None,
    related_domain_id: int | None = None,
    note: str | None = None,
) -> "models.CrystalLedger":
    """Apply a signed crystal `delta` to `user` and journal it.

    Args:
        db: active session (NOT committed here — caller owns the transaction).
        user: the User ORM instance whose wallet is being moved.
        delta: signed crystal movement (+credit / -debit).
        reason_code: one of VALID_REASON_CODES.

    Returns the staged (db.add'd, un-committed) CrystalLedger row.

    Raises:
        ValueError: unknown reason_code.
        InsufficientCrystalsError: the resulting balance would be negative.
    """
    if reason_code not in VALID_REASON_CODES:
        raise ValueError(f"Unknown crystal ledger reason_code: {reason_code!r}")

    current = user.mana_crystals or 0
    balance_after = current + delta
    if balance_after < 0:
        raise InsufficientCrystalsError(
            f"Crystal delta {delta} would drive user {user.id} balance "
            f"from {current} to {balance_after} (below zero)."
        )

    # The ONLY mutation of User.mana_crystals in the codebase.
    user.mana_crystals = balance_after

    entry = models.CrystalLedger(
        user_id=user.id,
        delta=delta,
        balance_after=balance_after,
        reason_code=reason_code,
        related_siege_id=related_siege_id,
        related_bounty_id=related_bounty_id,
        related_domain_id=related_domain_id,
        note=note,
    )
    db.add(entry)
    return entry
