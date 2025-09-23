from pathlib import Path
import json, time, zipfile
import httpx
from typer import Typer, Option
from dotenv import load_dotenv
from app.core.utils import ensure_dir, sha256_file, dump_json, now_yyyymmdd, env

app = Typer(no_args_is_help=True)


def _http_client():
    return httpx.Client(
        headers={"User-Agent": "de-brw-fetch/0.1 (+local)"},
        timeout=httpx.Timeout(60.0, connect=15.0, read=60.0),
        follow_redirects=True,
        http2=False,
    )


def _fetch_zip(client: httpx.Client, name: str, url: str, data_dir: Path) -> dict:
    snap_date = now_yyyymmdd()
    raw_dir = data_dir / "raw" / "de_boris_brw" / snap_date
    ensure_dir(raw_dir)

    dest = raw_dir / f"{name}.zip"
    tmp = raw_dir / f"{name}.zip.part"

    retries = 3
    for attempt in range(1, retries + 1):
        try:
            with client.stream("GET", url) as r:
                r.raise_for_status()
                with tmp.open("wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
            tmp.replace(dest)
            break
        except Exception:
            if attempt == retries:
                raise
            time.sleep(2 * attempt)

    sha = sha256_file(dest)
    # Best-effort extract
    extract_dir = raw_dir / name
    ensure_dir(extract_dir)
    try:
        with zipfile.ZipFile(dest) as z:
            z.extractall(extract_dir)
    except Exception:
        pass

    meta = {
        "source_url": url,
        "saved_path": str(dest),
        "extracted_dir": str(extract_dir),
        "sha256": sha,
        "size_bytes": dest.stat().st_size,
        "fetched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    dump_json(raw_dir / "metadata.json", meta)
    return meta


@app.command()
def current():
    load_dotenv()
    data_dir = Path(env("DATA_DIR"))
    sources_path = Path(env("DE_BRW_SOURCES_JSON"))
    sources = json.loads(sources_path.read_text())
    with _http_client() as client:
        url = sources["current"]
        meta = _fetch_zip(client, "brw_current", url, data_dir)
    print(json.dumps(meta, indent=2))


@app.command()
def year(year: int = Option(..., help="e.g., 2024")):
    load_dotenv()
    data_dir = Path(env("DATA_DIR"))
    sources_path = Path(env("DE_BRW_SOURCES_JSON"))
    sources = json.loads(sources_path.read_text())
    url = (sources.get("years") or {}).get(str(year))
    if not url:
        raise SystemExit(f"unknown or missing year: {year}")
    with _http_client() as client:
        meta = _fetch_zip(client, f"brw_{year}", url, data_dir)
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    app()
