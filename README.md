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
