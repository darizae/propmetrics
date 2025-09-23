import argparse, json, time
from typing import Tuple
import httpx


def post_json(client: httpx.Client, path: str, payload: dict) -> Tuple[float, httpx.Response]:
    t0 = time.perf_counter()
    r = client.post(path, json=payload, timeout=60.0)
    dt = (time.perf_counter() - t0) * 1000.0
    return dt, r


def main() -> int:
    ap = argparse.ArgumentParser(description="Acceptance checks for propmetrics (DE BRW)")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--max-latency-ms", type=int, default=10000)
    args = ap.parse_args()

    ok = True
    with httpx.Client(base_url=args.base_url) as client:
        q1 = {"date_range": {"start": "2018-01-01", "end": "2030-12-31"}, "groupby": "month"}
        dt1, r1 = post_json(client, "/aggregate", q1)
        body1 = r1.json() if r1.status_code == 200 else {}
        conds1 = [r1.status_code == 200, dt1 <= args.max_latency_ms,
                  isinstance(body1.get("row_count"), int) and body1["row_count"] >= 1, "filters_echo" in body1]
        print(json.dumps({"query": "Q1_monthly", "latency_ms": round(dt1, 2), "ok": all(conds1)}, indent=2))
        ok = ok and all(conds1)

        q2 = {"date_range": {"start": "2011-01-01", "end": "2030-12-31"},
              "municipality": ["koeln"], "groupby": "none"}
        dt2, r2 = post_json(client, "/aggregate", q2)
        body2 = r2.json() if r2.status_code == 200 else {}
        row2 = (body2.get("data") or [{}])[0]
        conds2 = [r2.status_code == 200, dt2 <= args.max_latency_ms,
                  body2.get("row_count", 0) in (0, 1), isinstance(row2.get("zones", 0), int), "filters_echo" in body2]
        print(
            json.dumps({"query": "Q2_municipality_summary", "latency_ms": round(dt2, 2), "ok": all(conds2)}, indent=2))
        ok = ok and all(conds2)

        q3 = {"date_range": {"start": "2018-01-01", "end": "2030-12-31"}, "groupby": "land_use"}
        dt3, r3 = post_json(client, "/aggregate", q3)
        body3 = r3.json() if r3.status_code == 200 else {}
        conds3 = [r3.status_code == 200, dt3 <= args.max_latency_ms,
                  isinstance(body3.get("row_count"), int) and body3["row_count"] >= 1, "filters_echo" in body3]
        ok3 = all(conds3)
        print(json.dumps({"query": "Q3_land_use", "latency_ms": round(dt3, 2), "ok": ok3}, indent=2))
        if not ok3:
            print(json.dumps({"status": r3.status_code, "body": body3}, indent=2))
        ok = ok and ok3
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
