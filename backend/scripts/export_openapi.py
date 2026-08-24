"""Export a deterministic OpenAPI document for frontend generation/checks."""

from __future__ import annotations

import json
from pathlib import Path

from ima.api.app import create_app
from ima.config import Settings


def export(path: Path) -> None:
    app = create_app(Settings(environment="test"))
    document = app.openapi()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=True, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    export(Path(__file__).parents[2] / "frontend/generated/openapi.json")
