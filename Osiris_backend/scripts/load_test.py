"""HTTP load test for the player API: concurrent players cycling through the app's main reads.

Seeds players over the public API (sign-up, then a verified walk each), then runs N concurrent
clients for a fixed time. Each client has its own token and sends If-None-Match like the app's
HTTP cache. Every tenth request is a profile write. Prints throughput, latency percentiles per
endpoint and overall, bytes on the wire, and errors.

    python scripts/load_test.py --base-url http://127.0.0.1:8000 --players 60 --users 20 --seconds 30

Run it against a dev or scratch deployment only: it creates accounts (email prefix `loadtest.`)
and runs. Rate limits are off in dev/test (OSIRIS_ENV=dev); against a production-like
environment most requests would be throttled, which measures the limiter, not the API.
"""
from __future__ import annotations

import argparse
import json
import random
import secrets
import statistics
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone

import httpx

HOME = (44.6488, -63.5752)  # Halifax, where the pilot seeds challenges


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _register(client: httpx.Client, run_tag: str, i: int) -> str:
    response = client.post("/api/v2/auth/register", json={
        "email": f"loadtest.{run_tag}.{i}@example.com",
        "password": "LoadTest-12345",
        "display_name": f"Load {i}",
        "location_consent": True,
    })
    response.raise_for_status()
    return response.json()["access_token"]


def _verified_walk(client: httpx.Client, token: str, rng: random.Random) -> None:
    """A 6-10 minute walk of ~50 points so the boards have data to rank."""
    headers = {"Authorization": f"Bearer {token}"}
    run = client.post("/api/v2/runs", headers=headers, json={"activity_type": "walk", "device_started_at": _now_iso()})
    run.raise_for_status()
    run_id = run.json()["id"]
    client.post(f"/api/v2/runs/{run_id}/start", headers=headers, json={"device_started_at": _now_iso()}).raise_for_status()
    lat, lng = HOME[0] + rng.uniform(-0.01, 0.01), HOME[1] + rng.uniform(-0.01, 0.01)
    step = rng.uniform(0.00008, 0.00012)  # ~10 m per 8 s: a brisk walk
    points = []
    for seq in range(50):
        lat += step
        points.append({"sequence": seq, "t_ms": seq * 8_000, "lat": lat, "lng": lng, "accuracy_m": 6})
    client.post(f"/api/v2/runs/{run_id}/points", headers=headers, json={"points": points}).raise_for_status()
    client.post(f"/api/v2/runs/{run_id}/finish", headers=headers, json={
        "device_finished_at": _now_iso(), "idempotency_key": f"loadtest-{run_id}-{secrets.token_hex(4)}",
    }).raise_for_status()


READS = [
    ("today", "/api/v2/me/today", {"lat": HOME[0], "lng": HOME[1]}),
    ("progression", "/api/v2/me/progression", None),
    ("hub live", "/api/v2/challenge-hub", {"section": "live"}),
    ("hub finished", "/api/v2/challenge-hub", {"section": "finished"}),
    ("nearby", "/api/v2/challenges/nearby", {"lat": HOME[0], "lng": HOME[1]}),
    ("board distance", "/api/v2/leaderboards/global", {"board": "distance", "period": "all"}),
    ("board pace", "/api/v2/leaderboards/global", {"board": "pace", "period": "all"}),
    ("communities", "/api/v2/communities", None),
]


def _worker(base_url: str, token: str, deadline: float, seed: int, out: dict, lock: threading.Lock) -> None:
    rng = random.Random(seed)
    etags: dict[str, str] = {}
    samples: list[tuple[str, float, int, int]] = []  # (endpoint, ms, status, bytes)
    headers = {"Authorization": f"Bearer {token}", "Accept-Encoding": "gzip"}
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        n = 0
        while time.perf_counter() < deadline:
            n += 1
            if n % 10 == 0:
                name, start = "profile write", time.perf_counter()
                response = client.put("/api/v2/me/profile", headers=headers,
                                      json={"utc_offset_minutes": rng.choice([-240, -180, 0, 60])})
            else:
                name, path, params = READS[rng.randrange(len(READS))]
                key = path + json.dumps(params, sort_keys=True)
                req_headers = dict(headers)
                if key in etags:
                    req_headers["If-None-Match"] = etags[key]
                start = time.perf_counter()
                response = client.get(path, params=params, headers=req_headers)
                if response.headers.get("etag"):
                    etags[key] = response.headers["etag"]
            elapsed_ms = (time.perf_counter() - start) * 1000
            wire = int(response.headers.get("content-length") or len(response.content))
            samples.append((name, elapsed_ms, response.status_code, wire))
    with lock:
        out["samples"].extend(samples)


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1))))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--players", type=int, default=60, help="accounts to seed (each gets one verified walk)")
    parser.add_argument("--users", type=int, default=20, help="concurrent clients")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--seed", type=int, default=20261024)
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    run_tag = secrets.token_hex(3)
    with httpx.Client(base_url=args.base_url, timeout=30.0) as client:
        client.get("/healthz").raise_for_status()
        tokens = []
        for i in range(args.players):
            token = _register(client, run_tag, i)
            _verified_walk(client, token, rng)
            tokens.append(token)

    out: dict = {"samples": []}
    lock = threading.Lock()
    deadline = time.perf_counter() + args.seconds
    threads = [
        threading.Thread(target=_worker, args=(args.base_url, tokens[i % len(tokens)], deadline, args.seed + i, out, lock))
        for i in range(args.users)
    ]
    started = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - started

    samples = out["samples"]
    by_endpoint: dict[str, list[float]] = defaultdict(list)
    for name, ms, _status, _bytes in samples:
        by_endpoint[name].append(ms)
    all_ms = [ms for _n, ms, _s, _b in samples]
    errors = [s for s in samples if s[2] >= 400]
    summary = {
        "users": args.users,
        "seconds": round(wall, 1),
        "requests": len(samples),
        "throughput_rps": round(len(samples) / wall, 1),
        "p50_ms": round(_pct(all_ms, 50), 1),
        "p95_ms": round(_pct(all_ms, 95), 1),
        "p99_ms": round(_pct(all_ms, 99), 1),
        "not_modified": sum(1 for s in samples if s[2] == 304),
        "errors": len(errors),
        "error_statuses": sorted({s[2] for s in errors}),
        "bytes_on_wire": sum(s[3] for s in samples),
        "endpoints": {
            name: {"n": len(v), "p50_ms": round(_pct(v, 50), 1), "p95_ms": round(_pct(v, 95), 1),
                   "mean_ms": round(statistics.fmean(v), 1)}
            for name, v in sorted(by_endpoint.items())
        },
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"{summary['requests']} requests in {summary['seconds']} s with {args.users} users: "
              f"{summary['throughput_rps']} req/s, p50 {summary['p50_ms']} ms, p95 {summary['p95_ms']} ms, "
              f"p99 {summary['p99_ms']} ms, {summary['not_modified']} x 304, {summary['errors']} errors, "
              f"{summary['bytes_on_wire'] / 1e6:.2f} MB")
        for name, row in summary["endpoints"].items():
            print(f"  {name:<16} n={row['n']:<5} p50 {row['p50_ms']:>7} ms  p95 {row['p95_ms']:>7} ms")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
