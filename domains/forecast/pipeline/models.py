from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlparse

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


# source_url·landing_url 은 사람이 읽는 보고서 페이지여야 한다("원문 보기"가
# JSON/CSV/XML 을 띄우면 안 된다). 기계용 주소를 걸러내는 규칙은 호스트가
# sdmx./api. 로 시작하거나(sdmx.oecd.org, api.imf.org) 경로에 /rest/data/
# 또는 /api/ 가 있는 경우로 좁힌다 — 이 조합은 이 프로젝트가 실제로 쓰는 모든
# SDMX·REST·DataMapper 엔드포인트를 잡아내면서, 각 수집기가 쓰는 진짜 보고서
# 주소(예: kdi.re.kr/file/download?atch_no=..., kli.re.kr/boardDownload.es?...)
# 에는 걸리지 않는다. 이보다 느슨하게(예: 문자열 어디든 "api" 포함) 잡으면
# "kiet.re.kr"처럼 우연히 글자가 겹치는 정상 주소까지 오탐해 모든 수집기가
# 한꺼번에 깨진다.
_MACHINE_ENDPOINT_HOST = re.compile(r"^(sdmx|api)\.")
_MACHINE_ENDPOINT_PATH = re.compile(r"/(rest/data|api)/")


def _is_machine_endpoint(url: str) -> bool:
    parsed = urlparse(url)
    return bool(_MACHINE_ENDPOINT_HOST.match(parsed.netloc)) or bool(
        _MACHINE_ENDPOINT_PATH.search(parsed.path)
    )


def make_id(org: str, published_at: date, indicator: str, target_year: int,
            target_period: str = "annual") -> str:
    # 연간 id에는 접미사를 붙이지 않는다 — 이미 쌓인 레코드의 id가 바뀌면
    # 같은 전망치가 새 레코드로 다시 들어와 수정 이력이 어긋난다
    suffix = "" if target_period == "annual" else f"-{target_period}"
    return f"{org.lower()}-{published_at:%Y-%m}-{indicator}-{target_year}{suffix}"


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

    @model_validator(mode="after")
    def check_urls_are_not_machine_endpoints(self):
        # 레코드가 만들어질 때마다(수집기 호출은 물론 store.load_forecasts 의
        # model_validate 에서도) 걸린다 — 새 수집기가 실수로 API 주소를 넣거나
        # forecasts.json 을 손으로 고치다 기계용 주소가 섞여도 조용히 지나가지
        # 않는다. 다만 이 프로젝트가 실제로 쓰는 SDMX·OECD REST·DataMapper
        # 모양만 잡아낸다(_is_machine_endpoint 의 패턴 참고) — 여기 없는 새
        # 모양(예: /apiv2/, stats.oecd.org/sdmx-json/...)의 엔드포인트가
        # 생기면 패턴을 추가해야 한다(설계 3.0, 전역 제약).
        for field in ("source_url", "landing_url"):
            url = getattr(self, field)
            if _is_machine_endpoint(url):
                raise ValueError(
                    f"{field} 가 기계용 API/데이터 주소를 가리킨다: {url!r}"
                )
        return self
