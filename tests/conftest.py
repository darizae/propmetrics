import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATA_DIR", "./data")

from app.api.main import app  # noqa: E402


@pytest.fixture(scope="session")
def data_ready():
    p = Path(os.environ["DATA_DIR"]) / "parquet" / "nyc_rolling_sales" / "nyc_rolling_sales.parquet"
    if not p.exists():
        pytest.skip(f"Parquet not found at {p}. Run `make fetch && make normalize` first.")
    return p


@pytest.fixture
def client(data_ready):
    with TestClient(app) as c:
        yield c


def base_spec():
    return {"date_range": {"start": "1990-01-01", "end": "2030-12-31"}, "groupby": "none"}
