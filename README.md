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
