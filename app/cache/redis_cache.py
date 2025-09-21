import os, hashlib
from dataclasses import dataclass
from typing import Optional, Any, Dict, List
import orjson

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None

try:
    import fakeredis  # type: ignore
except Exception:  # pragma: no cover
    fakeredis = None


@dataclass
class Cache:
    client: Any | None
    ttl: int

    def get(self, key: str) -> Optional[bytes]:
        if not self.client:
            return None
        try:
            return self.client.get(key)
        except Exception:
            return None

    def set(self, key: str, value: bytes) -> None:
        if not self.client:
            return
        try:
            self.client.setex(key, self.ttl, value)
        except Exception:
            pass

    def healthy(self) -> bool:
        if not self.client:
            return False
        try:
            return bool(self.client.ping())
        except Exception:
            return False


def _try_ping(client: Any) -> bool:
    try:
        return bool(client.ping())
    except Exception:
        return False


def get_cache() -> Cache:
    url = os.getenv("REDIS_URL", "").strip()
    ttl = int(os.getenv("CACHE_TTL_SECONDS", "86400"))
    client = None

    if url.startswith("fakeredis://"):
        if fakeredis:
            client = fakeredis.FakeRedis()
    elif url and redis:
        candidate = redis.from_url(url)
        if _try_ping(candidate):
            client = candidate
        else:
            client = None

    return Cache(client=client, ttl=ttl)


def _lower_sorted_strip(xs):
    if xs is None:
        return None
    return sorted([x.strip().lower() for x in xs])


def _sorted_keepcase(xs: Optional[List[str]]) -> Optional[List[str]]:
    if xs is None:
        return None
    return sorted(xs)


def canonical_spec_dict(spec_model) -> Dict[str, Any]:
    if hasattr(spec_model, "model_dump"):
        d = spec_model.model_dump(exclude_none=True)
    else:
        d = dict(spec_model)

    dr = d.get("date_range") or {}
    start = dr.get("start")
    end = dr.get("end")
    # handle date objects or strings
    start_iso = start.isoformat() if hasattr(start, "isoformat") else str(start)
    end_iso = end.isoformat() if hasattr(end, "isoformat") else str(end)

    out: Dict[str, Any] = {
        "date_range": {"start": start_iso, "end": end_iso},
        "groupby": d.get("groupby", "none"),
        "borough": _lower_sorted_strip(d.get("borough")),
        "neighborhood": _lower_sorted_strip(d.get("neighborhood")),
        "building_class_category": _sorted_keepcase(
            [(x.strip() if isinstance(x, str) else x) for x in (d.get("building_class_category") or [])]) or None,
    }
    return out


def spec_cache_key(prefix: str, spec_model) -> str:
    payload = orjson.dumps(canonical_spec_dict(spec_model), option=orjson.OPT_SORT_KEYS)
    h = hashlib.sha256(payload).hexdigest()
    return f"pm:v1:{prefix}:{h}"
