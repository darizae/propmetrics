import json
import os
from typing import Any, Dict, List, Tuple

import httpx
from fastapi import HTTPException

from app.cache.redis_cache import get_cache, spec_cache_key

# Real OpenAI; mockable via LLM_MOCK=1
_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo-0125")
_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
_OPENAI_BASE = os.getenv("OPENAI_API_BASE", None)
_LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "20"))
_LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "300"))
_LLM_MAX_PROMPT_CHARS = int(os.getenv("LLM_MAX_PROMPT_CHARS", "1000"))

# Tool schema matching /aggregate and /download
_TOOL_FUNCS = [
    {
        "type": "function",
        "function": {
            "name": "aggregate",
            "description": "Compute aggregates over BRW parquet",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_range": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "string", "description": "YYYY-MM-DD"},
                            "end": {"type": "string", "description": "YYYY-MM-DD"},
                        },
                        "required": ["start", "end"],
                    },
                    "municipality": {"type": "array", "items": {"type": "string"}},
                    "land_use": {"type": "array", "items": {"type": "string"}},
                    "plz": {"type": "array", "items": {"type": "string"}},
                    "groupby": {"type": "string", "enum": ["none", "month", "municipality", "land_use"]},
                },
                "required": ["date_range"],
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "download",
            "description": "Download same aggregate as CSV",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_range": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "string"},
                            "end": {"type": "string"},
                        },
                        "required": ["start", "end"],
                    },
                    "municipality": {"type": "array", "items": {"type": "string"}},
                    "land_use": {"type": "array", "items": {"type": "string"}},
                    "plz": {"type": "array", "items": {"type": "string"}},
                    "groupby": {"type": "string", "enum": ["none", "month", "municipality", "land_use"]},
                },
                "required": ["date_range"],
            },
            "strict": True,
        },
    },
]

_SYS = (
    "You are a tool-using agent. Only use the provided functions; do not invent fields. "
    "Return a terse JSON object: {filters_echo,row_count,data[]} without prose. "
    "If filters yield zero rows, still return row_count: 0 with empty data[]. "
    "Never emit code blocks. Never mention functions."
)


def _http() -> httpx.Client:
    base = os.getenv("SERVER_URL", "http://127.0.0.1:8000")
    return httpx.Client(base_url=base, timeout=_LLM_TIMEOUT_S)


def _call_backend(fn: str, args: Dict[str, Any]) -> Tuple[str, str]:
    with _http() as c:
        if fn == "aggregate":
            r = c.post("/aggregate", json=args)
            r.raise_for_status()
            return "aggregate", json.dumps(r.json(), ensure_ascii=False)
        if fn == "download":
            r = c.post("/download", json=args)
            r.raise_for_status()
            return "download", r.text
    raise HTTPException(400, detail=f"unknown tool {fn}")


def ask(text: str) -> Dict[str, Any]:
    if not text or len(text) > _LLM_MAX_PROMPT_CHARS:
        raise HTTPException(status_code=400, detail="prompt_too_long")

    cache = get_cache()
    cache_key = spec_cache_key("llm", {"text": text})
    if cache and cache.healthy():
        hit = cache.get(cache_key)
        if hit:
            return json.loads(hit)

    if os.getenv("LLM_MOCK", "0") == "1":
        # Deterministic mock: rely on /intent/parse then /aggregate
        with _http() as c:
            pr = c.post("/intent/parse", json={"text": text})
            if pr.status_code != 200:
                raise HTTPException(400, detail="PARSE_ERROR")
            spec = pr.json()["spec"]
            ar = c.post("/aggregate", json=spec)
            ar.raise_for_status()
            out = ar.json()
            out["llm"] = {"mode": "mock"}
    else:
        if not _OPENAI_API_KEY:
            raise HTTPException(status_code=400, detail="missing_openai_api_key")
        from openai import OpenAI

        client = OpenAI(api_key=_OPENAI_API_KEY) if _OPENAI_BASE is None else OpenAI(api_key=_OPENAI_API_KEY, base_url=_OPENAI_BASE)

        msgs = [{"role": "system", "content": _SYS}, {"role": "user", "content": text}]
        resp = client.chat.completions.create(
            model=_OPENAI_MODEL,
            messages=msgs,
            tools=_TOOL_FUNCS,
            tool_choice="auto",
            max_tokens=_LLM_MAX_TOKENS,
            temperature=0.0,
            timeout=_LLM_TIMEOUT_S,
        )
        msg = resp.choices[0].message
        tool_calls = msg.tool_calls or []
        tool_results: List[Dict[str, str]] = []

        # One or more tool calls; process sequentially
        for tc in tool_calls:
            fn = tc.function.name
            args = json.loads(tc.function.arguments or "{}")
            name, result = _call_backend(fn, args)
            tool_results.append({"tool_name": name, "result": result})

        # Send tool outputs back for final
        if tool_results:
            msgs.append({"role": "assistant", "tool_calls": [
                {"id": f"tool_{i}", "type": "function", "function": {"name": t["tool_name"], "arguments": ""}}
                for i, t in enumerate(tool_results)
            ]})
            for i, t in enumerate(tool_results):
                msgs.append({"role": "tool", "tool_call_id": f"tool_{i}", "name": t["tool_name"], "content": t["result"]})

            final = client.chat.completions.create(
                model=_OPENAI_MODEL,
                messages=msgs,
                max_tokens=_LLM_MAX_TOKENS,
                temperature=0.0,
                timeout=_LLM_TIMEOUT_S,
            )
            content = final.choices[0].message.content or "{}"
            try:
                out = json.loads(content)
            except Exception:
                # Fallback: if assistant echoed tool JSON verbatim
                try:
                    out = json.loads(tool_results[-1]["result"])
                except Exception:
                    raise HTTPException(502, detail="llm_output_not_json")
            out["llm"] = {
                "model": _OPENAI_MODEL,
                "finish_reason": final.choices[0].finish_reason,
            }
        else:
            # No tools called; reject
            raise HTTPException(502, detail="llm_no_tool_call")

    if cache and cache.healthy():
        cache.set(cache_key, json.dumps(out).encode("utf-8"))
    return out
