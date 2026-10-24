"""Account rules shared by the sign-up paths."""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

import models



def _check_email_unique(db: Session, email: str, exclude_table: Optional[str] = None) -> None:
    """Verify an email is not already registered in ANY auth table
    (User, Merchant, Admin) so accounts don't silently shadow each other in auth_login."""
    if exclude_table != "user":
        if db.query(models.User).filter(models.User.email == email).first():
            raise HTTPException(status_code=400, detail="Email already registered as a player account.")
    if exclude_table != "merchant":
        if db.query(models.Merchant).filter(models.Merchant.email == email).first():
            raise HTTPException(status_code=400, detail="Email already registered as a merchant account.")
    if exclude_table != "admin":
        if db.query(models.Admin).filter(models.Admin.email == email).first():
            raise HTTPException(status_code=400, detail="Email already registered as an admin account.")
