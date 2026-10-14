"""In-process Prometheus metrics with no third-party dependency.

Exposed at GET /metrics in the Prometheus text format (version 0.0.4). Values are per process,
like the rate limiter; with several workers, scrape each one or aggregate in Prometheus.

Label cardinality is bounded on purpose: requests are labelled by route *template*
(`/api/v2/runs/{run_id}/points`), never by raw path, user, or query string, so the series
count cannot grow with traffic and no personal data reaches the metrics store.
"""
from __future__ import annotations

import threading
from bisect import bisect_left
from collections import defaultdict

# Seconds. Covers the PRD read target (p95 < 0.5 s) with resolution on both sides.
LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)

_lock = threading.Lock()
_requests: dict[tuple[str, str, str], int] = defaultdict(int)          # (method, route, status) -> count
_latency_counts: dict[tuple[str, str], list[int]] = {}                  # (method, route) -> per-bucket counts
_latency_sum: dict[tuple[str, str], float] = defaultdict(float)
_latency_total: dict[tuple[str, str], int] = defaultdict(int)
_run_outcomes: dict[str, int] = defaultdict(int)                       # status -> count
_run_reasons: dict[str, int] = defaultdict(int)                        # reason code -> count
_exercise_outcomes: dict[tuple[str, str], int] = defaultdict(int)      # (exercise, status) -> count
_exercise_reasons: dict[str, int] = defaultdict(int)                   # reason code -> count


def observe_request(method: str, route: str, status: int, seconds: float) -> None:
    key = (method, route)
    with _lock:
        _requests[(method, route, str(status))] += 1
        counts = _latency_counts.setdefault(key, [0] * len(LATENCY_BUCKETS))
        i = bisect_left(LATENCY_BUCKETS, seconds)
        if i < len(counts):
            counts[i] += 1
        _latency_sum[key] += seconds
        _latency_total[key] += 1


def observe_run_verification(status: str, reason_codes: list[str]) -> None:
    with _lock:
        _run_outcomes[status] += 1
        for code in reason_codes:
            _run_reasons[code] += 1


def observe_exercise_verification(exercise: str, status: str, reason_codes: list[str]) -> None:
    with _lock:
        _exercise_outcomes[(exercise, status)] += 1
        for code in reason_codes:
            _exercise_reasons[code] += 1


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def render() -> str:
    """Current values in Prometheus text exposition format."""
    out: list[str] = []
    with _lock:
        out.append("# HELP osiris_http_requests_total HTTP requests by method, route template and status.")
        out.append("# TYPE osiris_http_requests_total counter")
        for (method, route, status), n in sorted(_requests.items()):
            out.append(f'osiris_http_requests_total{{method="{method}",route="{_label(route)}",status="{status}"}} {n}')

        out.append("# HELP osiris_http_request_duration_seconds Request latency by method and route template.")
        out.append("# TYPE osiris_http_request_duration_seconds histogram")
        for (method, route), counts in sorted(_latency_counts.items()):
            labels = f'method="{method}",route="{_label(route)}"'
            cumulative = 0
            for bound, n in zip(LATENCY_BUCKETS, counts):
                cumulative += n
                out.append(f'osiris_http_request_duration_seconds_bucket{{{labels},le="{bound}"}} {cumulative}')
            total = _latency_total[(method, route)]
            out.append(f'osiris_http_request_duration_seconds_bucket{{{labels},le="+Inf"}} {total}')
            out.append(f"osiris_http_request_duration_seconds_sum{{{labels}}} {_latency_sum[(method, route)]:.6f}")
            out.append(f"osiris_http_request_duration_seconds_count{{{labels}}} {total}")

        out.append("# HELP osiris_run_verifications_total Finished runs by verification status.")
        out.append("# TYPE osiris_run_verifications_total counter")
        for status, n in sorted(_run_outcomes.items()):
            out.append(f'osiris_run_verifications_total{{status="{_label(status)}"}} {n}')

        out.append("# HELP osiris_run_rejection_reasons_total Reason codes on rejected or flagged runs.")
        out.append("# TYPE osiris_run_rejection_reasons_total counter")
        for code, n in sorted(_run_reasons.items()):
            out.append(f'osiris_run_rejection_reasons_total{{reason="{_label(code)}"}} {n}')

        out.append("# HELP osiris_exercise_verifications_total Exercise sets by exercise and server status.")
        out.append("# TYPE osiris_exercise_verifications_total counter")
        for (exercise, status), n in sorted(_exercise_outcomes.items()):
            out.append(f'osiris_exercise_verifications_total{{exercise="{_label(exercise)}",status="{_label(status)}"}} {n}')

        out.append("# HELP osiris_exercise_flag_reasons_total Reason codes on flagged or rejected exercise sets.")
        out.append("# TYPE osiris_exercise_flag_reasons_total counter")
        for code, n in sorted(_exercise_reasons.items()):
            out.append(f'osiris_exercise_flag_reasons_total{{reason="{_label(code)}"}} {n}')
    return "\n".join(out) + "\n"


def reset() -> None:
    """Test hook: clear every series."""
    with _lock:
        for store in (_requests, _latency_counts, _latency_sum, _latency_total, _run_outcomes, _run_reasons,
                      _exercise_outcomes, _exercise_reasons):
            store.clear()
