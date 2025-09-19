from pathlib import Path
import json, time
import httpx
from typer import Typer, Option
from dotenv import load_dotenv
from app.core.utils import ensure_dir, sha256_file, dump_json, now_yyyymmdd, env

app = Typer(no_args_is_help=True)


def _http_client():
    return httpx.Client(
        headers={"User-Agent": "nyc-fetch/0.1 (+local)"},
        timeout=httpx.Timeout(30.0, connect=10.0, read=30.0),
        follow_redirects=True,
        http2=False,
    )


def _fetch_one(client: httpx.Client, name: str, url: str, data_dir: Path) -> dict:
    snap_date = now_yyyymmdd()
    raw_dir = data_dir / "raw" / "nyc_rolling_sales" / name / snap_date
    ensure_dir(raw_dir)

    head = None
    try:
        head = client.head(url)
    except Exception:
        head = None

    file_name = url.split("/")[-1].split("?")[0] or f"{name}.xls"
    dest = raw_dir / file_name
    tmp = raw_dir / (file_name + ".part")

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
        except Exception as e:
            if attempt == retries:
                raise
            time.sleep(2 * attempt)

    sha = sha256_file(dest)
    meta = {
        "source_url": url,
        "saved_path": str(dest),
        "sha256": sha,
        "size_bytes": dest.stat().st_size,
        "fetched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "http_last_modified": head.headers.get("last-modified") if head else None,
        "http_etag": head.headers.get("etag") if head else None,
        "content_type": head.headers.get("content-type") if head else None,
    }
    dump_json(raw_dir / "metadata.json", meta)
    return meta


@app.command()
def all():
    load_dotenv()
    data_dir = Path(env("DATA_DIR"))
    sources_path = Path(env("NYC_SOURCES_JSON"))
    sources = json.loads(sources_path.read_text())
    with _http_client() as client:
        results = {}
        for name, url in sources.items():
            results[name] = _fetch_one(client, name, url, data_dir)
    print(json.dumps(results, indent=2))


@app.command()
def one(name: str = Option(..., help="borough key in sources JSON")):
    load_dotenv()
    data_dir = Path(env("DATA_DIR"))
    sources_path = Path(env("NYC_SOURCES_JSON"))
    sources = json.loads(sources_path.read_text())
    url = sources.get(name)
    if not url:
        raise SystemExit(f"unknown source key: {name}")
    with _http_client() as client:
        meta = _fetch_one(client, name, url, data_dir)
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    app()
