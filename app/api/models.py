from typing import List, Optional, Literal, Union
from pydantic import BaseModel, Field


class DateRangeModel(BaseModel):
    start: str = Field(..., examples=["2024-01-01"])
    end: str = Field(..., examples=["2025-12-31"])


class QuerySpecModel(BaseModel):
    date_range: DateRangeModel
    borough: Optional[List[str]] = None
    neighborhood: Optional[List[str]] = None
    building_class_category: Optional[List[str]] = None
    groupby: Literal["none", "month", "neighborhood", "class"] = "none"


class AggregateRowBase(BaseModel):
    txns: int
    total_sale_price: Optional[float] = None
    median_sale_price: Optional[float] = None
    median_price_per_sqft: Optional[float] = None


class RowByMonth(AggregateRowBase):
    month: str


class RowByNeighborhood(AggregateRowBase):
    neighborhood: str


class RowByClass(AggregateRowBase):
    building_class_category: str


AggregateRow = Union[AggregateRowBase, RowByMonth, RowByNeighborhood, RowByClass]


class AggregateResponse(BaseModel):
    filters_echo: dict
    row_count: int
    data: List[AggregateRow]
