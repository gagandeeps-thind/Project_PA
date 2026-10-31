"""Rate limits: shared counts through Upstash, fallback when it is down, and the player's real IP.

A fake Upstash REST server (standard library) stands in for the real one, so the suite runs
offline. Run directly from the backend directory:
    python tests/test_rate_limits.py
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "rate-limit-test-secret-aaaaaaaaaaaaaaaaaaaaaaaa")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))

from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core import rate_limit  # noqa: E402

TOKEN = "fake-upstash-token"


class FakeUpstash(BaseHTTPRequestHandler):
    """Implements the MULTI/EXEC endpoint for the four sorted-set commands the limiter sends."""
    sets: "dict[str, dict[str, int]]" = {}
    calls = 0

    def do_POST(self) -> None:  # noqa: N802 (http.server naming)
        FakeUpstash.calls += 1
        if self.headers.get("Authorization") != f"Bearer {TOKEN}" or self.path != "/multi-exec":
            self.send_response(401)
            self.end_headers()
            return
        commands = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        out = []
        for name, key, *args in commands:
            members = FakeUpstash.sets.setdefault(key, {})
            if name == "ZREMRANGEBYSCORE":
                low, high = int(args[0]), int(args[1])
                gone = [m for m, s in members.items() if low <= s <= high]
                for m in gone:
                    del members[m]
                out.append({"result": len(gone)})
            elif name == "ZADD":
                members[args[1]] = int(args[0])
                out.append({"result": 1})
            elif name == "ZCARD":
                out.append({"result": len(members)})
            else:  # PEXPIRE
                out.append({"result": 1})
        body = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        pass


def _app(limit: int) -> TestClient:
    app = FastAPI()
    app.get("/limited", dependencies=[Depends(rate_limit._rate_limit(limit, 60, "test"))])(lambda: {"ok": True})
    return TestClient(app)


def _production_mode(upstash_url, trust_cf: bool = False) -> None:
    rate_limit._IS_DEV_ENV = False
    rate_limit.UPSTASH_URL = upstash_url
    rate_limit.UPSTASH_TOKEN = TOKEN
    rate_limit.TRUST_CF_CONNECTING_IP = trust_cf
    rate_limit._rate_buckets.clear()
    FakeUpstash.sets.clear()


def test_instances_share_one_count_through_upstash(url: str) -> None:
    _production_mode(url)
    first, second = _app(3), _app(3)  # two "instances": separate apps, one Upstash
    codes = [c.get("/limited").status_code for c in (first, second, first)]
    rate_limit._rate_buckets.clear()  # a restart or another process: no local memory at all
    codes.append(second.get("/limited").status_code)
    assert codes == [200, 200, 200, 429], codes
    assert not rate_limit._rate_buckets, "with Upstash answering, nothing is counted locally"
    print("PASS test_instances_share_one_count_through_upstash")


def test_an_upstash_outage_falls_back_to_per_process_counting() -> None:
    _production_mode("http://127.0.0.1:9")  # nothing listens on the discard port
    client = _app(2)
    codes = [client.get("/limited").status_code for _ in range(3)]
    assert codes == [200, 200, 429], codes
    print("PASS test_an_upstash_outage_falls_back_to_per_process_counting")


def test_a_rejected_token_also_falls_back(url: str) -> None:
    _production_mode(url)
    rate_limit.UPSTASH_TOKEN = "wrong"
    codes = [_app(1).get("/limited").status_code for _ in range(2)]
    assert codes == [200, 429], codes
    print("PASS test_a_rejected_token_also_falls_back")


def test_players_behind_cloudflare_get_their_own_bucket() -> None:
    _production_mode(None, trust_cf=True)
    client = _app(1)
    a = client.get("/limited", headers={"CF-Connecting-IP": "203.0.113.7"}).status_code
    b = client.get("/limited", headers={"CF-Connecting-IP": "198.51.100.4"}).status_code
    a_again = client.get("/limited", headers={"CF-Connecting-IP": "203.0.113.7"}).status_code
    assert (a, b, a_again) == (200, 200, 429), (a, b, a_again)
    print("PASS test_players_behind_cloudflare_get_their_own_bucket")


def test_without_the_origin_lock_the_header_is_not_trusted() -> None:
    # Anyone can send CF-Connecting-IP straight to the origin; rotating it must not reset the limit.
    _production_mode(None, trust_cf=False)
    client = _app(1)
    codes = [client.get("/limited", headers={"CF-Connecting-IP": f"203.0.113.{i}"}).status_code for i in range(2)]
    assert codes == [200, 429], codes
    print("PASS test_without_the_origin_lock_the_header_is_not_trusted")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeUpstash)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fake_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        test_instances_share_one_count_through_upstash(fake_url)
        test_an_upstash_outage_falls_back_to_per_process_counting()
        test_a_rejected_token_also_falls_back(fake_url)
        test_players_behind_cloudflare_get_their_own_bucket()
        test_without_the_origin_lock_the_header_is_not_trusted()
    finally:
        server.shutdown()
