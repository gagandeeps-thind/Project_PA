"""Server clock helpers. Times are stored as naive UTC (SQLite has no time zones)."""
from datetime import datetime, timezone



def _now_naive_utc() -> datetime:
    """Server-side 'now' as a naive UTC datetime (tz stripped) for SQLite-compatible storage."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

def _to_naive_utc(dt: datetime) -> datetime:
    """Normalize a client-supplied datetime to naive UTC so comparisons with stored values work.
    Accepts either aware or naive datetimes; assumes naive inputs are already UTC."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)
