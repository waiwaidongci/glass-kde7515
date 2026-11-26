from pydantic import BaseModel, ConfigDict, Field


class RetestCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset_id: int = Field(gt=0)
    quota: int = Field(gt=0, le=5000)
    settings: dict[str, float] = Field(default_factory=dict, max_length=20)


class RetestSign(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    note: str = Field(min_length=4, max_length=1000)


class RetestInfo(BaseModel):
    id: int
    dataset_id: int
    quota: int
    status: str
    settings: dict
    plan_fingerprint: dict
    created_at: str
    signed_at: str | None
    signed_by: int | None
    sign_note: str | None
