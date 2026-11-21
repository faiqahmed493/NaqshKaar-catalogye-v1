from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from ..deps import Principal
from ..models import AuditLog


def audit(db: Session, actor: Principal | None, action: str, entity_type: str, entity_id: uuid.UUID | str,
          details: dict[str, Any] | None = None) -> None:
    db.add(AuditLog(
        actor_user_id=actor.user_id if actor else None,
        actor_api_key_id=actor.api_key_id if actor else None,
        action=action, entity_type=entity_type, entity_id=str(entity_id), details=details,
    ))
