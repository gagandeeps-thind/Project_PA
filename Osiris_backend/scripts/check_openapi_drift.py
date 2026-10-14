"""Phase 0 CI gate: fail if the live OpenAPI schema drifts from the committed contract.

The committed contract is `Documentation/openapi.json` — three clients (customer app,
merchant app, admin web) are generated against it. Any code change that alters the API
surface must regenerate the contract in the same commit, or CI fails here.

Usage:
    python scripts/check_openapi_drift.py            # check (exit 1 on drift)
    python scripts/check_openapi_drift.py --write    # regenerate the committed contract

Comparison is structural (parsed JSON, key-order independent), so cosmetic reformatting
of the committed file does not cause false drift.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(HERE, ".."))
REPO_ROOT = os.path.abspath(os.path.join(BACKEND_DIR, ".."))
CONTRACT = os.path.join(REPO_ROOT, "Documentation", "openapi.json")

sys.path.insert(0, BACKEND_DIR)


def _canonical(spec: dict) -> str:
    return json.dumps(spec, sort_keys=True, indent=2)


def main() -> int:
    # Import lazily so a missing dep surfaces as a normal import error.
    from main import app

    live = app.openapi()

    write = "--write" in sys.argv
    if write:
        with open(CONTRACT, "w", encoding="utf-8") as fh:
            fh.write(_canonical(live) + "\n")
        print(f"Wrote committed contract: {CONTRACT}")
        return 0

    if not os.path.exists(CONTRACT):
        print(f"ERROR: committed contract missing: {CONTRACT}", file=sys.stderr)
        print("Run: python scripts/check_openapi_drift.py --write", file=sys.stderr)
        return 1

    with open(CONTRACT, encoding="utf-8") as fh:
        committed = json.load(fh)

    if _canonical(live) == _canonical(committed):
        print("OpenAPI contract is in sync.")
        return 0

    print("ERROR: OpenAPI drift detected.", file=sys.stderr)
    print("The live schema differs from Documentation/openapi.json.", file=sys.stderr)
    print("If the API change is intentional, regenerate the contract:", file=sys.stderr)
    print("    python scripts/check_openapi_drift.py --write", file=sys.stderr)
    print("and commit Documentation/openapi.json.", file=sys.stderr)

    # Show which paths changed to make the failure actionable.
    live_paths = set(live.get("paths", {}))
    committed_paths = set(committed.get("paths", {}))
    added = sorted(live_paths - committed_paths)
    removed = sorted(committed_paths - live_paths)
    if added:
        print(f"  + added paths:   {added}", file=sys.stderr)
    if removed:
        print(f"  - removed paths: {removed}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
