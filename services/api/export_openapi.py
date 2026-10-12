"""Write the API's OpenAPI schema; packages/shared-types generates TS types from it."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from atlas_api.app import app


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "packages/shared-types/openapi.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
