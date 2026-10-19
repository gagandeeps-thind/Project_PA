"""Write (or check) the app's bundled copy of the exercise catalog.

`services/exercises.py` is the source of truth. The customer app bundles
`shared/assets/exercise_catalog.json` so the on-device rep engine works offline and
on first launch, before it has fetched `GET /api/v2/exercises`.

Usage:
    python scripts/export_exercise_catalog.py            # check (exit 1 on drift)
    python scripts/export_exercise_catalog.py --write    # regenerate the bundled copy
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(HERE, ".."))
ASSET = os.path.abspath(os.path.join(BACKEND_DIR, "..", "shared", "assets", "exercise_catalog.json"))

sys.path.insert(0, BACKEND_DIR)


def rendered() -> str:
    from services.exercises import catalog_payload

    return json.dumps(catalog_payload(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    text = rendered()
    if "--write" in sys.argv:
        os.makedirs(os.path.dirname(ASSET), exist_ok=True)
        with open(ASSET, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        sys.stdout.write(f"Wrote {ASSET}\n")
        return 0
    if not os.path.exists(ASSET):
        sys.stderr.write(f"ERROR: bundled catalog missing: {ASSET}\n")
        return 1
    with open(ASSET, encoding="utf-8") as fh:
        if json.load(fh) != json.loads(text):
            sys.stderr.write("ERROR: bundled exercise catalog drifted. Run: "
                             "python scripts/export_exercise_catalog.py --write\n")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
