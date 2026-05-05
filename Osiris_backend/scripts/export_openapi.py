"""Dump the FastAPI OpenAPI spec to Documentation/openapi.json so the Flutter frontend in
Google Antigravity can regenerate its Dart client without running the server.

Run from the project root or from Osiris_backend; both work:

    python scripts/export_openapi.py
    python Osiris_backend/scripts/export_openapi.py

This is a coordination artifact. Re-run after any schema-affecting change (new endpoint,
new Pydantic field, route rename) so Antigravity stays in sync.
"""
import json
import os
import sys

# Allow `import main` regardless of which CWD this is launched from.
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(HERE, ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(BACKEND_DIR, ".."))
sys.path.insert(0, BACKEND_DIR)

import main  # noqa: E402

OUT_PATH = os.path.join(PROJECT_ROOT, "Documentation", "openapi.json")


def main_export() -> None:
    spec = main.app.openapi()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, sort_keys=True)
    rel = os.path.relpath(OUT_PATH, PROJECT_ROOT)
    print(f"Wrote OpenAPI spec ({len(spec.get('paths', {}))} paths) to {rel}")


if __name__ == "__main__":
    main_export()
