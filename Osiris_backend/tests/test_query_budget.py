"""Query budget: the hot read endpoints run a fixed number of SQL statements, whatever the data size.

    python tests/test_query_budget.py

Seeds the scripts/perf_audit.py data set twice (small and three times larger) on an in-memory
database and checks every audited endpoint stays within its budget and does not grow with the
data, which is how an N+1 shows up. Leaves no rows behind.
"""
import os
import sys

os.environ.setdefault("OSIRIS_ENV", "test")
os.environ.setdefault("OSIRIS_JWT_SECRET", "query-budget-test-secret-aaaaaaaaaaaaaaaaaaa")
BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(BACKEND, "scripts"))
sys.path.insert(0, BACKEND)

import perf_audit  # noqa: E402

# Statements per request, auth lookups included. Raise one only with a reason in the commit.
BUDGET = {
    "arise domains": 8,
    "arise routes": 5,
    "v1 domains nearby": 4,
    "season leaderboard": 12,
    "city leaderboard": 11,
    "global board": 7,
    "training sessions": 5,
    "feed posts": 13,
    "social feed": 16,
    "suggested osirians": 6,
    "bounties nearby": 4,
    "merchant bounties": 5,
}
SMALL, LARGE = 15, 45


def _results(ctx: dict) -> dict:
    return {label: (status, queries) for label, status, queries in perf_audit.measure(ctx)}


def test_endpoints_stay_within_budget_and_do_not_grow() -> None:
    small = _results(perf_audit.seed(SMALL))
    large = _results(perf_audit.seed(LARGE))
    assert set(BUDGET) == set(large), sorted(set(BUDGET) ^ set(large))
    for label, (status, queries) in large.items():
        assert status == 200, (label, status)
        assert queries <= BUDGET[label], f"{label}: {queries} queries, budget {BUDGET[label]}"
        assert queries == small[label][1], f"{label}: {small[label][1]} queries at {SMALL} players, {queries} at {LARGE}"
    print("PASS test_endpoints_stay_within_budget_and_do_not_grow")


def test_prefiltered_and_batched_results_are_complete() -> None:
    """The SQL bounding boxes and the aggregate feed queries return the same rows as before."""
    ctx = perf_audit.seed(LARGE)
    client, player, admin = ctx["client"], ctx["player"], ctx["admin"]
    near = {"lat": perf_audit.LAT, "lng": perf_audit.LNG}

    domains = client.get("/api/v2/arise/domains", params=near, headers=player).json()
    shown = domains["suggested"] + domains["hard"]
    assert len(shown) == LARGE, len(shown)  # the far copies on another continent are not near
    assert sum(1 for d in shown if d["photo_url"]) == LARGE // 2
    assert all(d["owner_name"].startswith("Runner ") for d in shown)
    routes = client.get("/api/v2/arise/routes", params=near, headers=player).json()
    assert len(routes) == LARGE and all(r["owner_name"].startswith("Runner ") for r in routes)
    v1 = client.get("/api/v1/domains/nearby", params=near, headers=player).json()
    assert len(v1) == LARGE and v1 == sorted(v1, key=lambda d: d["distance_km"])
    assert len(client.get("/api/v1/bounties/nearby", params=near, headers=player).json()) == 20
    page = client.get("/api/v1/bounties/nearby", params={**near, "limit": 5, "offset": 5}, headers=player).json()
    assert [b["title"] for b in page] == [f"Chest {b}" for b in range(5, 10)], page

    posts = client.get("/api/v2/feed/posts", params={"limit": 10}, headers=player).json()["items"]
    assert posts and all(p["comment_count"] == 5 and len(p["recent_comments"]) == 3 for p in posts)
    assert all(p["reactions"] == {"fire": 5} and p["total_reactions"] == 5 for p in posts)
    newest = [c["body"] for c in posts[0]["recent_comments"]]
    assert newest == ["nice 3", "nice 4", "nice 5"], newest

    sessions = client.get("/api/v2/me/training/sessions", params={"limit": 50}, headers=player).json()["items"]
    by_id = sorted(sessions, key=lambda s: s["id"])
    best, expected = 0.0, {}
    for s in by_id:  # a PR beats every earlier session of the activity
        expected[s["id"]] = s["distance_m"] > best
        best = max(best, s["distance_m"])
    assert {s["id"]: s["is_pr"] for s in sessions} == expected

    bounties = client.get(f"/api/v1/merchants/{ctx['merchant_id']}/bounties", headers=admin).json()
    assert len(bounties) == 20 and all(b["coupons_issued"] == 1 for b in bounties)
    season = client.get("/api/v2/seasons/perf-season/leaderboard", headers=player).json()
    assert len(season["communities"]) == 8 and sum(c["entered_members"] for c in season["communities"]) == LARGE
    print("PASS test_prefiltered_and_batched_results_are_complete")


if __name__ == "__main__":
    test_endpoints_stay_within_budget_and_do_not_grow()
    test_prefiltered_and_batched_results_are_complete()
