
# propmetrics

NRW land value (BORIS/BRW) ETL → Parquet → FastAPI tools with optional UI and LLM front.

## Features

- ETL: stream ZIP, extract Shapefile, normalize to Parquet (`de_boris_brw.parquet`)
- Analytics API: `/aggregate`, `/download`, `/health`
- Deterministic intent parser: `/intent/parse` (no external APIs)
- Minimal UI at `/ui`
- Optional LLM front `/llm/ask` with tool calls (numbers-only, JSON)
- Redis caching with canonicalized keys and `x-cache` headers
- OpenAPI Actions schema: `actions/openapi.yaml`
- Tests and scripted acceptance

## Quick Start (Docker)

```bash
docker run --rm -p 8000:8000 \
  -e DATA_DIR=/data \
  -e REDIS_URL=fakeredis:// \
  -e CORS_ORIGINS=* \
  -e LLM_MOCK=1 \
  -v "$PWD/data:/data:ro" \
  ghcr.io/<your-namespace>/propmetrics:0.3
````

Endpoints:

* UI: [http://127.0.0.1:8000/ui](http://127.0.0.1:8000/ui)
* Health: `curl -s http://127.0.0.1:8000/health | jq .`
* Example aggregate:

```bash
curl -s http://127.0.0.1:8000/aggregate \
  -H 'content-type: application/json' \
  -d '{"date_range":{"start":"2018-01-01","end":"2030-12-31"},"groupby":"month"}' | jq .
```

## Quick Start (Source)

```bash
make install
make fetch
make normalize
make serve
# open http://127.0.0.1:8000/ui
```

Acceptance:

```bash
make accept
```

Tests:

```bash
make test
```

## API

* `POST /aggregate` → `{filters_echo,row_count,data[]}`

  * filters: `date_range{start,end}`, `municipality[]`, `land_use[]`, `plz[]`, `groupby ∈ {none,month,municipality,land_use}`
* `POST /download` → CSV of the same result
* `GET /health` → dataset snapshot + schema fingerprint + cache status
* `POST /intent/parse` → `{spec,tokens,fallback}` (internal)
* `POST /llm/ask` → numbers-only JSON using tool calls (optional; requires OpenAI API key)
* `GET /openapi.yaml` → reduced Actions schema (also in `actions/openapi.yaml`)

## Configuration

Environment variables:

* `DATA_DIR` (required): path with `parquet/de_boris_brw/de_boris_brw.parquet`
* `REDIS_URL` (`redis://…` or `fakeredis://`)
* `SERVER_URL` (for schema export)
* `CORS_ORIGINS` (comma-separated origins for UI)
* `RATE_QPS`, `RATE_BURST` (optional rate limiting for `/aggregate`, `/intent/parse`, `/llm/ask`)
* `ADMIN_TOKEN` (for `/admin/refresh`)
* LLM (optional): `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_PROJECT`, `OPENAI_ORG`, `OPENAI_API_BASE`, `LLM_MOCK=1`

## Data and Schema

Dataset: OpenGeodata NRW BORIS Bodenrichtwerte (DL-DE-Zero 2.0).
Canonical columns: `municipality`, `land_use`, `plz`, `eur_per_m2`, `stichtag`.
Schema fingerprint stored at `data/meta/de_boris_brw/schema.json`.

## Development

* OpenAPI export: `make openapi` → `actions/openapi.yaml`
* Admin refresh (clears cache, remounts Parquet):

```bash
curl -s -X POST http://127.0.0.1:8000/admin/refresh \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .
```

## Repository Layout

```
app/         # API, query planner, intent parser, UI static
scripts/     # acceptance, OpenAPI export, LLM accept
actions/     # openapi.yaml (reduced, tools-only)
sources/     # source URLs (NRW BORIS)
tests/       # API, cache, intent, LLM mock
artifacts/   # demo clips and screenshots (optional)
```

## License

Code: MIT (adjust as necessary).
Data: DL-DE-Zero 2.0.

## Agent-assisted setup

[Open the agent setup page](https://darizae.github.io/propmetrics/) or [copy the plain-text prompt](docs/agent-setup.txt) into your coding agent. Review its proposed changes and verification results.
