"""Consent and blocking lookups shared by `main.py` and the growth modules (G4).

These depend only on `models`, so `main` can import them at the top without the import
cycle the growth routers have.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

import models


def needs_location_consent(db: Session, user_id: int) -> bool:
    """True for v2 players who have not granted location consent. Legacy v1 players predate
    the consent screen and have `consent_required=False`."""
    profile = db.query(models.PlayerProfile).filter(models.PlayerProfile.user_id == user_id).first()
    return profile is not None and bool(profile.consent_required) and profile.location_consent_at is None


def blocked_user_ids(db: Session, user_id: int) -> set[int]:
    """Everyone this player blocked or was blocked by."""
    rows = db.query(models.UserBlock.blocker_id, models.UserBlock.blocked_id).filter(
        (models.UserBlock.blocker_id == user_id) | (models.UserBlock.blocked_id == user_id)).all()
    return {b if a == user_id else a for a, b in rows}


def is_blocked_between(db: Session, a: int, b: int) -> bool:
    return db.query(models.UserBlock.id).filter(
        ((models.UserBlock.blocker_id == a) & (models.UserBlock.blocked_id == b))
        | ((models.UserBlock.blocker_id == b) & (models.UserBlock.blocked_id == a))).first() is not None
