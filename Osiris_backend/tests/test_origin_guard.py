"""With OSIRIS_ORIGIN_SECRET set, only requests carrying X-Origin-Verify (added by the CDN) are served.

Run directly from the backend directory:
    python tests/test_origin_guard.py
"""
import os
import sys

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "origin-guard-test-secret-aaaaaaaaaaaaaaaaaaaaa")
os.environ["OSIRIS_ORIGIN_SECRET"] = "origin-guard-test-value"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.origin_guard import OriginGuardMiddleware
import main

client = TestClient(main.app)
VERIFIED = {"X-Origin-Verify": "origin-guard-test-value"}


def test_requests_that_skip_the_cdn_are_refused() -> None:
    assert client.get("/api/v2/challenges/live").status_code == 403
    r = client.get("/api/v2/challenges/live", headers={"X-Origin-Verify": "wrong"})
    assert r.status_code == 403 and r.json() == {"detail": "Forbidden"}, r.text
    print("PASS test_requests_that_skip_the_cdn_are_refused")


def test_requests_through_the_cdn_are_served() -> None:
    r = client.get("/api/v2/challenges/live", headers=VERIFIED)
    assert r.status_code != 403, r.text
    print("PASS test_requests_through_the_cdn_are_served")


def test_the_stripe_webhook_is_not_exempt() -> None:
    # Stripe must call the CDN hostname, which adds the header; a direct call is refused.
    assert client.post("/api/v1/payments/stripe/webhook", content=b"{}").status_code == 403
    r = client.post("/api/v1/payments/stripe/webhook", content=b"{}", headers=VERIFIED)
    assert r.status_code != 403, r.text
    print("PASS test_the_stripe_webhook_is_not_exempt")


def test_the_platform_health_check_needs_no_header() -> None:
    assert client.get("/healthz").status_code == 200
    print("PASS test_the_platform_health_check_needs_no_header")


def test_without_the_setting_the_check_is_off() -> None:
    bare = FastAPI()
    bare.get("/ping")(lambda: {"ok": True})
    bare.add_middleware(OriginGuardMiddleware, secret="")
    assert TestClient(bare).get("/ping").status_code == 200
    print("PASS test_without_the_setting_the_check_is_off")


if __name__ == "__main__":
    test_requests_that_skip_the_cdn_are_refused()
    test_requests_through_the_cdn_are_served()
    test_the_stripe_webhook_is_not_exempt()
    test_the_platform_health_check_needs_no_header()
    test_without_the_setting_the_check_is_off()
