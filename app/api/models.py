from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class DateRangeModel(BaseModel):
    start: str = Field(..., examples=["2024-01-01"])
    end: str = Field(..., examples=["2025-12-31"])


class QuerySpecModel(BaseModel):
    date_range: DateRangeModel
    municipality: Optional[List[str]] = None
    land_use: Optional[List[str]] = None  # NUTA codes (e.g., WA, WB, WR, MI, GE, GI, W, M, etc.)
    plz: Optional[List[str]] = None
    groupby: Literal["none", "month", "municipality", "land_use"] = "none"


class AggregateRow(BaseModel):
    month: Optional[str] = None
    municipality: Optional[str] = None
    land_use: Optional[str] = None
    zones: int
    median_eur_per_m2: Optional[float] = None


class AggregateResponse(BaseModel):
    filters_echo: dict
    row_count: int
    data: List[AggregateRow]
