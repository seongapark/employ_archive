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

# 속성 축. `scope` 는 인구 범위(15~64세·15~29세)다 — 연령(`age`)과 따로 두는
# 이유는 15~64세가 연령 구간들을 **가로지르기** 때문이다. age 에 넣으면 속성별
# 매트릭스에서 구간들과 나란히 서서 이중 계상으로 읽힌다.
Breakdown = Literal["total", "industry", "sex", "age", "scope"]

# 지표 축. 오래도록 `headcount` 하나뿐이었다(취업자수·종사자수·상시가입자수).
# 경활의 총괄 지표가 먼저 들어왔고, 그다음이 고용행정통계다.
Series = Literal[
    "headcount",            # 취업자수 · 종사자수 · 상시가입자수
    "unemployed",           # 실업자수
    "labor_force",          # 경제활동인구
    "inactive",             # 비경제활동인구
    "population",           # 15세 이상 인구
    "employment_rate",      # 고용률
    "unemployment_rate",    # 실업률
    "participation_rate",   # 경제활동참가율
    # 고용행정통계(ei)가 내는 것들. 고용보험 자격의 드나듦과 구직급여,
    # 그리고 고용24 구인·구직이다.
    "acquired",             # 피보험자격 취득자수
    "separated",            # 피보험자격 상실자수
    "benefit_new",          # 구직급여 신규신청자수
    "benefit_paid",         # 구직급여 지급자수
    "benefit_amount",       # 구직급여 지급액
    "job_openings",         # 고용24 신규구인인원
    "job_seekers",          # 고용24 신규구직인원
    "openings_ratio",       # 구인배수 = 신규구인 ÷ 신규구직
]

# 비율 지표의 yoy 는 증감량이 아니라 **%p 차이**다. 화면 포맷터가 unit 으로
# 갈라진다 — 천명 규칙으로 그리면 고용률 63.3 이 `6.3만명` 이 된다.
#
# 지급건수(천건)·1인당 지급액(천원)은 저장하지 않으므로 그 단위도 만들지
# 않는다. 쓰지 않는 단위를 열어 두면 열이 밀려 들어온 값이 그럴듯하게 통과한다.
Unit = Literal["천명", "%", "억원", "배"]

Status = Literal["잠정", "확정"]

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def make_id(source: str, period: str, breakdown: str, category: Optional[str],
            *, series: str = "headcount") -> str:
    """레코드 키. **지표가 반드시 들어간다.**

    안 들어가면 고용률과 취업자수가 같은 키를 갖고, store.upsert 가 둘을 같은
    관측으로 보아 서로 덮어쓴다 — 값이 조용히 뒤바뀐다.

    기본값이 `headcount` 라서 이미 쌓인 2,300여 건의 id 는 한 글자도 바뀌지
    않는다(그 자리에 원래 `headcount` 가 박혀 있었다).
    """
    tail = "" if breakdown == "total" else f"-{category}"
    return f"{source}-{period}-{series}-{breakdown}{tail}"


class Attachment(BaseModel):
    type: Literal["hwpx", "pdf", "xlsx"]
    url: str


class SeriesRecord(BaseModel):
    id: str
    source: Source
    series: Series = "headcount"
    breakdown: Breakdown
    category: Optional[str] = None
    period: str
    value: float
    unit: Unit = "천명"
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
