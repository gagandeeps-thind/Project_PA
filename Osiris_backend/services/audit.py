"""Append-only audit events, written in the caller's transaction."""
import json
from typing import Optional

from sqlalchemy.orm import Session

import models



def _audit(
    db: Session, *, actor_type: str, actor_id: Optional[int], action: str,
    entity_type: str, entity_id: Optional[int], details: Optional[dict] = None,
) -> None:
    """Append an AuditEvent in the caller's transaction. Never pass coordinates here."""
    db.add(models.AuditEvent(
        actor_type=actor_type, actor_id=actor_id, action=action,
        entity_type=entity_type, entity_id=entity_id,
        details_json=json.dumps(details or {}, default=str, sort_keys=True),
    ))
