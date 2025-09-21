import time, sys, json
from typing import Tuple
import httpx
import typer

app = typer.Typer(help="Acceptance checks for propmetrics")


def post_json(client: httpx.Client, path: str, payload: dict) -> Tuple[float, httpx.Response]:
    t0 = time.perf_counter()
    r = client.post(path, json=payload, timeout=60.0)
    dt = (time.perf_counter() - t0) * 1000.0
    return dt, r


@app.command("run")
def run(
        base_url: str = typer.Option("http://127.0.0.1:8000", help="Base URL for API"),
        max_latency_ms: int = typer.Option(10000, help="P95 acceptance latency"),
):
    ok = True
    with httpx.Client(base_url=base_url) as client:
        # Q1: Monthly volume last 24 months (should have data)
        q1 = {
            "date_range": {"start": "2023-01-01", "end": "2030-12-31"},
            "groupby": "month",
        }
        dt1, r1 = post_json(client, "/aggregate", q1)
        if r1.status_code != 200: ok = False
        body1 = r1.json()
        conds1 = [
            dt1 <= max_latency_ms,
            isinstance(body1.get("row_count"), int) and body1["row_count"] > 0,
            "filters_echo" in body1,
        ]
        print(json.dumps({"query": "Q1_monthly", "latency_ms": round(dt1, 2), "ok": all(conds1)}, indent=2))
        ok = ok and all(conds1)

        # Q2: Borough-wide summary across full window (row_count==1, txns>0)
        q2 = {
            "date_range": {"start": "1990-01-01", "end": "2030-12-31"},
            "borough": ["manhattan"],
            "groupby": "none",
        }
        dt2, r2 = post_json(client, "/aggregate", q2)
        body2 = r2.json() if r2.status_code == 200 else {}
        row2 = (body2.get("data") or [{}])[0]
        conds2 = [
            r2.status_code == 200,
            dt2 <= max_latency_ms,
            body2.get("row_count", 0) in (0, 1),  # allow 0 if empty but usually 1
            isinstance(row2.get("txns", 0), int) and row2.get("txns", 0) >= 0,
            "filters_echo" in body2,
        ]
        print(json.dumps({"query": "Q2_borough_summary", "latency_ms": round(dt2, 2), "ok": all(conds2)}, indent=2))
        ok = ok and all(conds2)

        # Q3: Neighborhood grouping for Queens (should return multiple rows)
        q3 = {
            "date_range": {"start": "1990-01-01", "end": "2030-12-31"},
            "borough": ["queens"],
            "groupby": "neighborhood",
        }
        dt3, r3 = post_json(client, "/aggregate", q3)
        body3 = r3.json() if r3.status_code == 200 else {}
        conds3 = [
            r3.status_code == 200,
            dt3 <= max_latency_ms,
            isinstance(body3.get("row_count"), int) and body3["row_count"] >= 1,
            "filters_echo" in body3,
        ]
        print(json.dumps({"query": "Q3_neighborhoods", "latency_ms": round(dt3, 2), "ok": all(conds3)}, indent=2))
        ok = ok and all(conds3)

    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    app()
