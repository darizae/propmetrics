import os, sys, yaml
from app.api.main import app
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    raw = app.openapi()
    paths = raw.get("paths", {})
    keep = {k: v for k, v in paths.items() if k in ("/aggregate", "/download")}
    raw["paths"] = keep
    raw["info"]["title"] = "propmetrics-tools"
    raw["info"][
        "description"] = "Tool-only API for computing aggregates over NRW Bodenrichtwerte Parquet. Return numbers; no prose."
    raw["servers"] = [{"url": os.getenv("SERVER_URL", "http://localhost:8000")}]
    outdir = ROOT / "actions";
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / "openapi.yaml"
    with out.open("w") as f:
        yaml.safe_dump(raw, f, sort_keys=False)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
