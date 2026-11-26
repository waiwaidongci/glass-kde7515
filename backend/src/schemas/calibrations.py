from pydantic import BaseModel, ConfigDict, Field, constr
from typing import Annotated


class CalibrationCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    label: Annotated[str, constr(strip_whitespace=True, min_length=2, max_length=140)]
    dataset_id: int = Field(gt=0)
    bench_offsets: dict[str, float] = Field(min_length=1, max_length=32)
    note: Annotated[str | None, constr(strip_whitespace=True, min_length=2, max_length=1000)] = None


class CalibrationInfo(BaseModel):
    id: int
    label: str
    dataset_id: int
    bench_offsets: dict[str, float]
    version: int
    created_at: str
    updated_at: str
    note: str | None
