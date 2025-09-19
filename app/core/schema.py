from pathlib import Path
from typing import Dict
import hashlib
from app.core.utils import dump_json, ensure_dir


def schema_fingerprint(columns: Dict[str, str]) -> str:
    payload = "|".join(f"{k}:{v}" for k, v in sorted(columns.items()))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def write_schema(base_dir: Path, dataset: str, columns: Dict[str, str]) -> str:
    fp = schema_fingerprint(columns)
    out_dir = base_dir / "meta" / dataset
    ensure_dir(out_dir)
    dump_json(out_dir / "schema.json", {"columns": columns, "fingerprint": fp})
    return fp
