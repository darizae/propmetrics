import os
from pathlib import Path
import pandas as pd

data_dir = Path(__file__).resolve().parents[1] / "data"
src = data_dir / "parquet" / "de_boris_brw" / "de_boris_brw.parquet"
if not src.exists():
    raise SystemExit(f"missing {src}")

df = pd.read_parquet(src)
# Stratified downsample: keep all 2023–2024 + 1% of older rows
recent = df[df["stichtag"] >= "2023-01-01"]
older = df[df["stichtag"] < "2023-01-01"].sample(frac=0.01, random_state=13)
demo = pd.concat([recent, older], ignore_index=True)

out = Path("./demo/parquet/de_boris_brw")
out.mkdir(parents=True, exist_ok=True)
demo.to_parquet(out / "de_boris_brw_demo.parquet", index=False)
print({"rows": len(demo), "out": str(out / "de_boris_brw_demo.parquet")})
