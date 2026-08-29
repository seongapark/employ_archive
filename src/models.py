from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

Indicator = Literal[
    "emp_change", "emp_rate", "unemp_rate", "gdp_growth",
    "cpi", "emp_rate_youth", "labor_force",
]

_INDICATORS_PATH = Path(__file__).resolve().parent.parent / "data" / "indicators.json"
INDICATOR_META: dict[str, dict] = {
    row["code"]: row
    for row in json.loads(_INDICATORS_PATH.read_text(encoding="utf-8"))
}
VALUE_RANGES: dict[str, tuple[float, float]] = {
    code: (meta["range"][0], meta["range"][1])
    for code, meta in INDICATOR_META.items()
}


def make_id(org: str, published_at: date, indicator: str, target_year: int) -> str:
    return f"{org.lower()}-{published_at:%Y-%m}-{indicator}-{target_year}"


class ForecastRecord(BaseModel):
    id: str
    org: str
    org_name_ko: str
    report_title: str
    published_at: date
    target_year: int = Field(ge=2000, le=2100)
    target_period: Literal["annual", "h1", "h2"] = "annual"
    indicator: Indicator
    value: float
    unit: str
    prev_value: Optional[float] = None
    revision: Optional[float] = None
    rationale: str = ""
    rationale_tags: list[str] = Field(default_factory=list)
    source_url: str
    source_page: Optional[int] = None
    landing_url: str
    confidence: Literal["verified", "extracted", "reviewed"]
    collected_at: datetime

    @model_validator(mode="after")
    def check_value_range(self):
        lo, hi = VALUE_RANGES[self.indicator]
        if not (lo <= self.value <= hi):
            raise ValueError(
                f"{self.indicator} value {self.value} out of range [{lo}, {hi}]"
            )
        return self
