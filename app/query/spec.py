from typing import Literal, Optional, List
from datetime import date
from pydantic import BaseModel, field_validator

GroupBy = Literal["none", "month", "municipality", "land_use"]


class DateRange(BaseModel):
    start: date
    end: date

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, v, info):
        start = info.data.get("start")
        if start and v < start:
            raise ValueError("end < start")
        return v


class QuerySpec(BaseModel):
    date_range: DateRange
    municipality: Optional[List[str]] = None
    land_use: Optional[List[str]] = None
    plz: Optional[List[str]] = None
    groupby: GroupBy = "none"
