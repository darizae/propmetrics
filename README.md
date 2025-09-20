Day 1 targets
- Stream-download borough files to data/raw/nyc_rolling_sales/<borough>/<YYYYMMDD>/, plus metadata.json.
- Normalize to canonical columns and write data/parquet/nyc_rolling_sales/nyc_rolling_sales.parquet.
- Emit data/meta/nyc_rolling_sales/schema.json with fingerprint.
Commands
- make install
- make fetch
- make normalize
- make test
Completion checks
- data/raw/.../<date>/metadata.json exists for each borough.
- data/parquet/nyc_rolling_sales/nyc_rolling_sales.parquet exists and is non-empty.
- data/meta/nyc_rolling_sales/schema.json and data/parquet/nyc_rolling_sales/SUMMARY.json exist.

---

Day 2 targets
- DuckDB view over Parquet.
- POST /aggregate -> {filters_echo,row_count,data[]}
- POST /download -> CSV of identical result set.

Commands
- make install
- make serve
- curl -s http://127.0.0.1:8000/aggregate -H 'content-type: application/json' -d '{"date_range":{"start":"1990-01-01","end":"2030-12-31"},"groupby":"month"}' | jq .