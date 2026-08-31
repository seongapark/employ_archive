"""고용동향 시계열 레코드.

전망 도메인과 달리 회차 이력을 쌓지 않는다. 실적 통계는 과거 수치가 개정되므로
같은 키(id)를 덮어쓰고 released_at 을 갱신한다.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

Source = Literal["eaps", "est", "ei"]
Breakdown = Literal["total", "industry", "sex", "age"]
Status = Literal["잠정", "확정"]

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def make_id(source: str, period: str, breakdown: str, category: Optional[str]) -> str:
    tail = "" if breakdown == "total" else f"-{category}"
    return f"{source}-{period}-headcount-{breakdown}{tail}"


class Attachment(BaseModel):
    type: Literal["hwpx", "pdf", "xlsx"]
    url: str


class SeriesRecord(BaseModel):
    id: str
    source: Source
    series: Literal["headcount"] = "headcount"
    breakdown: Breakdown
    category: Optional[str] = None
    period: str
    value: float
    unit: Literal["천명"] = "천명"
    yoy: Optional[float] = None
    status: Status = "잠정"
    released_at: date
    release_url: str
    attachments: list[Attachment] = Field(default_factory=list)
    collected_at: datetime

    @field_validator("period")
    @classmethod
    def check_period(cls, v: str) -> str:
        if not PERIOD_RE.match(v):
            raise ValueError(f"period 는 YYYY-MM 이어야 한다: {v!r}")
        return v

    @field_validator("release_url")
    @classmethod
    def check_url_scheme(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"release_url 은 http(s) 여야 한다: {v!r}")
        return v

    @model_validator(mode="after")
    def check_category(self):
        if self.breakdown == "total" and self.category:
            raise ValueError("breakdown=total 은 category 를 가질 수 없다")
        if self.breakdown != "total" and not self.category:
            raise ValueError(f"breakdown={self.breakdown} 는 category 가 필요하다")
        return self
