"""Create or update the single Admin row.

Public admin registration is intentionally NOT exposed as an API endpoint — admins are
seeded out-of-band by running this script. Only Gagan should ever invoke it.

Two ways to call it:

    # Interactive (prompts for email + password)
    python scripts/seed_admin.py

    # Non-interactive (reads from env vars)
    OSIRIS_ADMIN_EMAIL=you@example.com OSIRIS_ADMIN_PASSWORD=letmein \\
        OSIRIS_ADMIN_NAME="Gagan" python scripts/seed_admin.py

Idempotent: re-running with the same email updates the password / name in place rather
than creating a duplicate row. Passwords are bcrypt-hashed before storage."""
import getpass
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, BACKEND_DIR)

import bcrypt  # noqa: E402

import database  # noqa: E402
import models   # noqa: E402

models.Base.metadata.create_all(bind=database.engine)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def prompt(label: str, fallback_env: str, hidden: bool = False) -> str:
    env_val = os.environ.get(fallback_env)
    if env_val:
        return env_val
    if hidden:
        return getpass.getpass(f"{label}: ")
    return input(f"{label}: ").strip()


def main() -> None:
    email = prompt("Admin email", "OSIRIS_ADMIN_EMAIL")
    password = prompt("Admin password (max 12 chars)", "OSIRIS_ADMIN_PASSWORD", hidden=True)
    name = prompt("Display name", "OSIRIS_ADMIN_NAME") or email

    if not email or not password:
        print("Email and password are required.", file=sys.stderr)
        sys.exit(1)
    if len(password) > 12:
        print("Password must be 12 characters or fewer (matches the in-app cap).", file=sys.stderr)
        sys.exit(1)

    db = database.SessionLocal()
    try:
        existing = db.query(models.Admin).filter(models.Admin.email == email).first()
        if existing:
            existing.hashed_password = hash_password(password)
            existing.name = name
            db.commit()
            print(f"Updated admin '{email}' (id={existing.id}).")
        else:
            new_admin = models.Admin(
                email=email,
                hashed_password=hash_password(password),
                name=name,
            )
            db.add(new_admin)
            db.commit()
            db.refresh(new_admin)
            print(f"Created admin '{email}' (id={new_admin.id}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
