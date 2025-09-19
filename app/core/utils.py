import hashlib, os, re, sys, time
from pathlib import Path
from typing import Dict, Any
import orjson


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def now_yyyymmdd() -> str:
    return time.strftime("%Y%m%d", time.gmtime())


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def dump_json(path: Path, data: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2))


_snake_re1 = re.compile(r"[^A-Za-z0-9]+")
_snake_re2 = re.compile(r"([a-z0-9])([A-Z])")


def snake(s: str) -> str:
    s = _snake_re2.sub(r"\1_\2", s)
    s = _snake_re1.sub("_", s).strip("_").lower()
    return s


def die(msg: str, code: int = 2) -> None:
    sys.stderr.write(msg + "\n")
    sys.exit(code)


def env(name: str, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if v is None:
        die(f"Missing env var: {name}")
    return v
