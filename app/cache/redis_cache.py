import os, hashlib
from dataclasses import dataclass
from typing import Optional, Any
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


def get_cache() -> Cache:
    url = os.getenv("REDIS_URL", "")
    ttl = int(os.getenv("CACHE_TTL_SECONDS", "86400"))
    client = None
    if url.startswith("fakeredis://"):
        if fakeredis:
            client = fakeredis.FakeRedis()
    elif url and redis:
        client = redis.from_url(url)
    return Cache(client=client, ttl=ttl)


def spec_cache_key(prefix: str, spec_model) -> str:
    payload = orjson.dumps(spec_model.model_dump(exclude_none=True), option=orjson.OPT_SORT_KEYS)
    h = hashlib.sha256(payload).hexdigest()
    return f"pm:v1:{prefix}:{h}"
