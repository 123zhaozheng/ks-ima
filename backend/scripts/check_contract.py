"""Fail when the checked OpenAPI contract no longer matches the app."""

from __future__ import annotations

import json
from pathlib import Path

from ima.api.app import create_app
from ima.config import Settings


def main() -> None:
    expected = Path(__file__).parents[2] / "frontend/generated/openapi.json"
    actual = (
        json.dumps(
            create_app(Settings(environment="test")).openapi(),
            ensure_ascii=True,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    if not expected.exists() or expected.read_text() != actual:
        raise SystemExit("OpenAPI drift detected; run `python backend/scripts/export_openapi.py`")


if __name__ == "__main__":
    main()
