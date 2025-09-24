import argparse
import json

import httpx


def main():
    ap = argparse.ArgumentParser(description="Run a real LLM call through /llm/ask")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--prompt", required=True)
    args = ap.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=60.0) as c:
        r = c.post("/llm/ask", json={"text": args.prompt})
        print(json.dumps({"status": r.status_code, "body": r.json() if r.headers.get("content-type","").startswith("application/json") else r.text}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
