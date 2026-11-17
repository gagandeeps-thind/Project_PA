"""Account rules shared by the sign-up paths."""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

import models



def _check_email_unique(db: Session, email: str, exclude_table: Optional[str] = None) -> None:
    """Verify an email is not already registered in ANY auth table
    (User, Merchant, Admin) so accounts don't silently shadow each other in auth_login.
    One message for every table, so sign-up cannot be used to find out which emails are admins."""
    tables = {"user": models.User, "merchant": models.Merchant, "admin": models.Admin}
    for name, table in tables.items():
        if name != exclude_table and db.query(table.id).filter(table.email == email).first():
            raise HTTPException(status_code=400, detail="Email already registered.")
