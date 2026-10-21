"""Runtime configuration read from the environment.

Secrets come from a secret manager in deployed environments. AWS Secrets Manager (ECS task
`secrets`), Vault Agent templates and Kubernetes/Docker secrets all deliver a secret either as an
environment variable or as a mounted file, so every secret here accepts both forms: `NAME`, or
`NAME_FILE` holding the path of a file whose content is the value. Locally, `.env` (see
`.env.example`) fills the environment.
"""

import os
from pathlib import Path

DEV_ENVS = frozenset({"dev", "development", "test", "testing", "local"})


def secret(name: str) -> str | None:
    """`name` from the environment, else the content of the file named by `name_FILE`."""
    value = os.environ.get(name)
    if value:
        return value
    path = os.environ.get(f"{name}_FILE")
    if not path:
        return None
    try:
        content = Path(path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"{name}_FILE points at {path!r}, which cannot be read: {exc}") from exc
    return content or None


def environment() -> str:
    return os.environ.get("OSIRIS_ENV", "").lower()


def is_dev_env() -> bool:
    """Only an explicit dev/test value counts; an unset or unknown OSIRIS_ENV is production."""
    return environment() in DEV_ENVS


def database_url(default: str) -> str:
    return secret("OSIRIS_DATABASE_URL") or default


def run_scheduler() -> bool:
    """Whether this process runs the background jobs (decay, settlement, retention). Behind a load
    balancer exactly one replica should, or every job runs once per replica."""
    return os.environ.get("OSIRIS_RUN_SCHEDULER", "1").lower() not in ("0", "false", "no")


def public_base_url() -> str | None:
    """Origin used in share and invite links (`OSIRIS_PUBLIC_BASE_URL`), without a trailing slash."""
    value = os.environ.get("OSIRIS_PUBLIC_BASE_URL", "").strip().rstrip("/")
    return value or None
