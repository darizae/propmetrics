Day 1 targets
- Stream-download NRW Bodenrichtwerte ZIP to data/raw/de_boris_brw/<YYYYMMDD>/, plus metadata.json; extract shapefile.
- Normalize to canonical columns and write data/parquet/de_boris_brw/de_boris_brw.parquet.
- Emit data/meta/de_boris_brw/schema.json with fingerprint.

Commands
- make install
- make fetch
- make normalize

Completion checks
- data/raw/.../<date>/metadata.json exists.
- data/parquet/de_boris_brw/de_boris_brw.parquet exists and is non-empty.
- data/meta/de_boris_brw/schema.json and data/parquet/de_boris_brw/SUMMARY.json exist.

Day 2 targets
- DuckDB view over Parquet.
- POST /aggregate -> {filters_echo,row_count,data[]}
- POST /download -> CSV of identical result set.

Day 3 targets
- Redis cache and x-cache headers; /health with snapshot + schema fingerprint; tests for cache/health/coercions/median.

Day 4 targets
- OpenAPI export; scripted acceptance checks.

Dataset reference
- OpenGeodata.NRW Bodenrichtwerte (license: DL-DE-Zero 2.0). See sources JSON and model PDF.

## 0.3

Scope: minimal text→spec→/aggregate layer and a dev UI. Deterministic parsing (no external APIs). Optional LLM front using GPT-3.5 with real tool calls into the local service; tests mock it.

Run:
- `make install`
- `make fetch && make normalize`
- `make serve` then open `http://127.0.0.1:8000/ui`
- `make test` (uses fakeredis and disables LLM by default)
- `make accept`

LLM front (optional):
- Set `OPENAI_API_KEY`, optionally `OPENAI_MODEL=gpt-3.5-turbo-0125`
- `make llm_accept PROMPT='Monthly since 2018'` (calls `/llm/ask` against the running server)

Example prompts:
- `Monthly since 2018`
- `Köln und Bochum 2011..2024`
- `NUTA WA, WR in 2023`

Rate limit:
- Enable via `RATE_QPS` and `RATE_BURST`; affects `/aggregate`, `/intent/parse`, `/llm/ask`. Disabled when `RATE_QPS=0`.
