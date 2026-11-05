"""Seeds a running local API with two connected players for the Social tab emulator run.

QA Me follows QA Friend; the friend has a verified run, a photo + workouts + chart post, a
caption post, and a direct message to QA Me. A third player has a public post for Discover.
"""

import base64
import json
import sys
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

API = "http://localhost:8000"
PASSWORD = "QaSocial1!"
# A valid 8x8 grey JPEG.
JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////"
    "////////////////////wgALCAAIAAgBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAAA//aAAgBAQAAAAE//9k="
)


def call(method: str, path: str, body=None, token=None):
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
    )
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 (local test server)
        raw = r.read()
        return json.loads(raw) if raw else None


def register(email: str, name: str) -> tuple[int, str]:
    data = call(
        "POST",
        "/api/v2/auth/register",
        {
            "email": email,
            "password": PASSWORD,
            "display_name": name,
            "goal": "fitness",
            "location_consent": True,
        },
    )
    return data["profile"]["user_id"], data["access_token"]


def session(
    token: str, activity: str, distance: float, duration: float, hours_ago: float
) -> int:
    started = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    return call(
        "POST",
        "/api/v2/training/sessions",
        {
            "client_session_id": str(uuid.uuid4()),
            "activity_key": activity,
            "mode": "train",
            "source": "sensor",
            "started_at": started,
            "duration_s": duration,
            "distance_m": distance,
            "series": {"hr": [[0, 120], [600, 150], [1200, 162]]},
            "devices": [],
        },
        token,
    )["id"]


def main() -> None:
    me_id, me = register("qa.me@example.com", "QA Me")
    friend_id, friend = register("qa.friend@example.com", "QA Friend")
    _stranger_id, stranger = register("qa.stranger@example.com", "Discover Dana")
    session(me, "run", 3000.0, 1080.0, 30)
    call("POST", f"/api/v2/osirians/{friend_id}/follow", token=me)
    run = session(friend, "run", 5000.0, 1500.0, 2)
    ride = session(friend, "cycle", 12000.0, 2400.0, 1)
    call(
        "POST",
        "/api/v2/social/posts",
        {
            "caption": "Brick day done",
            "photo_jpeg_base64": base64.b64encode(JPEG).decode(),
            "training_session_ids": [run, ride],
            "chart": "weekly_progress",
        },
        friend,
    )
    call("POST", "/api/v2/social/posts", {"caption": "Rest day stretch"}, friend)
    dana_run = session(stranger, "run", 10000.0, 3000.0, 3)
    call(
        "POST",
        "/api/v2/social/posts",
        {"caption": "Sunday 10K", "training_session_ids": [dana_run]},
        stranger,
    )
    call(
        "POST",
        f"/api/v2/social/conversations/{me_id}/messages",
        {"body": "Run tomorrow at 6?"},
        friend,
    )
    print(f"seeded me={me_id} friend={friend_id}")  # noqa: T201


if __name__ == "__main__":
    sys.exit(main())
