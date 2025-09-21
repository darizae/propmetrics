"""
Export a minimal Actions-ready OpenAPI spec for tool use.
Keeps only /aggregate and /download. Writes actions/openapi.yaml.
"""
from pathlib import Path

import os
import yaml

from app.api.main import app

os.environ.setdefault("DATA_DIR", "./data")


def main():
    raw = app.openapi()  # dict
    # Retain only analytics endpoints
    paths = raw.get("paths", {})
    keep = {k: v for k, v in paths.items() if k in ("/aggregate", "/download")}
    raw["paths"] = keep

    # Slim description for Actions
    raw["info"]["title"] = "propmetrics-tools"
    raw["info"]["description"] = (
        "Tool-only API for computing aggregates over NYC rolling sales Parquet. "
        "Return numbers and small tables; no prose."
    )
    # Optional server hint for local/dev
    raw["servers"] = [{"url": os.getenv("SERVER_URL", "http://localhost:8000")}]

    outdir = Path("actions")
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / "openapi.yaml"
    with out.open("w") as f:
        yaml.safe_dump(raw, f, sort_keys=False)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
