"""Share and invite links come from OSIRIS_PUBLIC_BASE_URL, never from a forged Host header.

Run directly from the backend directory:
    python tests/test_public_base_url.py
"""
import os
import sys

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "public-base-url-test-secret-aaaaaaaaaaaaaaaaa")
os.environ["OSIRIS_PUBLIC_BASE_URL"] = "https://osiris.example/"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from fastapi.testclient import TestClient

import database
import growth_api
import main
import models


PREFIX = "public_base_url_test_"
client = TestClient(main.app)


def cleanup() -> None:
    db = database.SessionLocal()
    try:
        ids = [u.id for u in db.query(models.User).filter(models.User.email.like(PREFIX + "%")).all()]
        if ids:
            growth_api.delete_growth_data(db, ids)
            db.query(models.User).filter(models.User.id.in_(ids)).delete(synchronize_session=False)
            db.commit()
    finally:
        db.close()


def _player() -> dict:
    r = client.post("/api/v2/auth/register", json={
        "email": f"{PREFIX}ada@example.com", "password": "BaseUrlTest1!", "display_name": "Ada",
        "location_consent": True, "goal": "running", "install_id": f"{PREFIX}device",
    })
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}", "Host": "evil.example"}


def test_links_ignore_a_forged_host_header() -> None:
    r = client.get("/api/v2/me/referrals", headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["url"].startswith("https://osiris.example/join/"), r.json()["url"]
    print("PASS test_links_ignore_a_forged_host_header")


def test_production_without_public_base_url_refuses_links() -> None:
    saved = {k: os.environ.get(k) for k in ("OSIRIS_ENV", "OSIRIS_PUBLIC_BASE_URL")}
    os.environ["OSIRIS_ENV"] = "production"
    os.environ.pop("OSIRIS_PUBLIC_BASE_URL")
    try:
        r = client.get("/api/v2/me/referrals", headers=HEADERS)
    finally:
        for k, v in saved.items():
            os.environ[k] = v
    assert r.status_code == 503 and "evil.example" not in r.text, r.text
    print("PASS test_production_without_public_base_url_refuses_links")


if __name__ == "__main__":
    cleanup()
    try:
        HEADERS = _player()
        test_links_ignore_a_forged_host_header()
        test_production_without_public_base_url_refuses_links()
    finally:
        cleanup()
