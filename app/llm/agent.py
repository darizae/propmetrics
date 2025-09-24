import json
import os
from typing import Any, Dict, List, Tuple

import httpx
from fastapi import HTTPException
from dotenv import load_dotenv, find_dotenv

from app.cache.redis_cache import get_cache, spec_cache_key

load_dotenv(find_dotenv(usecwd=True), override=True)

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
    timeout = float(os.getenv("LLM_TIMEOUT_S", "20"))
    return httpx.Client(base_url=base, timeout=timeout)


def _cfg() -> Dict[str, Any]:
    # Read env lazily so `.env` and runtime overrides are honored
    model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo-0125").strip()
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    api_base = (os.getenv("OPENAI_API_BASE") or "").strip()
    org = (os.getenv("OPENAI_ORG") or "").strip()
    project = (os.getenv("OPENAI_PROJECT") or "").strip()
    timeout = float(os.getenv("LLM_TIMEOUT_S", "20"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "300"))
    max_prompt = int(os.getenv("LLM_MAX_PROMPT_CHARS", "1000"))
    return {
        "model": model,
        "api_key": api_key,
        "api_base": api_base,
        "org": org,
        "project": project,
        "timeout": timeout,
        "max_tokens": max_tokens,
        "max_prompt": max_prompt,
    }


def _make_openai_client(cfg: Dict[str, Any]):
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="missing_openai_api_key")
    if not cfg["api_key"].startswith("sk-"):
        raise HTTPException(status_code=400, detail="invalid_api_key_format")
    from openai import OpenAI
    kwargs: Dict[str, Any] = {"api_key": cfg["api_key"], "timeout": cfg["timeout"]}
    if cfg["api_base"]:
        kwargs["base_url"] = cfg["api_base"]
    if cfg["org"]:
        kwargs["organization"] = cfg["org"]
    if cfg["project"]:
        kwargs["project"] = cfg["project"]
    return OpenAI(**kwargs)


def _call_backend(fn: str, args: Dict[str, Any]) -> Tuple[str, str]:
    with _http() as c:
        if fn == "aggregate":
            r = c.post("/aggregate", json=args);
            r.raise_for_status()
            return "aggregate", json.dumps(r.json(), ensure_ascii=False)
        if fn == "download":
            r = c.post("/download", json=args);
            r.raise_for_status()
            return "download", r.text
    raise HTTPException(400, detail=f"unknown tool {fn}")


def ask(text: str) -> Dict[str, Any]:
    cfg = _cfg()
    if not text or len(text) > cfg["max_prompt"]:
        raise HTTPException(status_code=400, detail="prompt_too_long")

    cache = get_cache()
    cache_key = spec_cache_key("llm", {"text": text})
    if cache and cache.healthy():
        hit = cache.get(cache_key)
        if hit:
            return json.loads(hit)

    if os.getenv("LLM_MOCK", "0") == "1":
        with _http() as c:
            pr = c.post("/intent/parse", json={"text": text})
            if pr.status_code != 200:
                raise HTTPException(400, detail="PARSE_ERROR")
            spec = pr.json()["spec"]
            ar = c.post("/aggregate", json=spec)
            ar.raise_for_status()
            out = ar.json()
            out["llm"] = {
                "mode": "mock",
                "debug_api_key": cfg["api_key"],
                "debug_project": cfg["project"],
            }
    else:
        try:
            client = _make_openai_client(cfg)
            msgs = [{"role": "system", "content": _SYS}, {"role": "user", "content": text}]
            resp = client.chat.completions.create(
                model=cfg["model"],
                messages=msgs,
                tools=_TOOL_FUNCS,
                tool_choice="auto",
                max_tokens=cfg["max_tokens"],
                temperature=0.0,
            )
        except Exception as e:
            try:
                import openai
                if isinstance(e, openai.APIStatusError) and getattr(e, "status_code", None) == 401:
                    hint = "invalid_api_key"
                    if cfg["api_key"].startswith("sk-proj-") and not cfg["project"]:
                        hint = "project_key_missing_OPENAI_PROJECT"
                    raise HTTPException(
                        status_code=401,
                        detail={
                            "error": hint,
                            "debug_api_key": cfg["api_key"],
                            "debug_project": cfg["project"],
                        },
                    )
            except Exception:
                pass
            raise HTTPException(
                status_code=500,
                detail={
                    "error": str(e),
                    "debug_api_key": cfg["api_key"],
                    "debug_project": cfg["project"],
                },
            )

        msg = resp.choices[0].message
        tool_calls = msg.tool_calls or []
        tool_results: List[Dict[str, str]] = []
        for tc in tool_calls:
            fn = tc.function.name
            args = json.loads(tc.function.arguments or "{}")
            name, result = _call_backend(fn, args)
            tool_results.append({"tool_name": name, "result": result})

        if not tool_results:
            raise HTTPException(
                502,
                detail={
                    "error": "llm_no_tool_call",
                    "debug_api_key": cfg["api_key"],
                    "debug_project": cfg["project"],
                },
            )

        final = client.chat.completions.create(
            model=cfg["model"],
            messages=[
                {"role": "system", "content": _SYS},
                {"role": "user", "content": text},
                {"role": "assistant", "tool_calls": [
                    {"id": f"tool_{i}", "type": "function", "function": {"name": t["tool_name"], "arguments": ""}}
                    for i, t in enumerate(tool_results)
                ]},
                *[
                    {"role": "tool", "tool_call_id": f"tool_{i}", "name": t["tool_name"], "content": t["result"]}
                    for i, t in enumerate(tool_results)
                ],
            ],
            max_tokens=cfg["max_tokens"],
            temperature=0.0,
        )
        content = final.choices[0].message.content or "{}"
        try:
            out = json.loads(content)
        except Exception:
            try:
                out = json.loads(tool_results[-1]["result"])
            except Exception:
                raise HTTPException(
                    502,
                    detail={
                        "error": "llm_output_not_json",
                        "debug_api_key": cfg["api_key"],
                        "debug_project": cfg["project"],
                    },
                )

        out["llm"] = {
            "model": cfg["model"],
            "finish_reason": final.choices[0].finish_reason,
            "debug_api_key": cfg["api_key"],
            "debug_project": cfg["project"],
        }

    if cache and cache.healthy():
        cache.set(cache_key, json.dumps(out).encode("utf-8"))
    return out


