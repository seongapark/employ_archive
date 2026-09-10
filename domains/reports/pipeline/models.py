"""보고서 한 건의 모양과 날짜 정규화.

이 모듈은 기관도 HTML 도 모른다. 문자열과 dict 만 다루므로 네 기관을 안 거치고
테스트가 돈다.
"""
from __future__ import annotations

import calendar
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

CUTOFF = '2021-01-01'

DatePrecision = Literal['day', 'month', 'year']

_DAY = re.compile(r'^(\d{4})\D+(\d{1,2})\D+(\d{1,2})\D*$')
_MONTH = re.compile(r'^(\d{4})\D+(\d{1,2})\D*$')
_YEAR = re.compile(r'^(\d{4})\D*$')


def normalize_published(raw: str) -> tuple[str, str]:
    """발간일 문자열을 (ISO 날짜, 정밀도) 로 바꾼다.

    부분 날짜는 정렬이 깨지지 않게 월말·연말로 채우되, 채웠다는 사실을
    정밀도로 남긴다. 화면은 이 정밀도보다 자세히 적지 않는다.
    """
    s = (raw or '').strip()
    m = _DAY.match(s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        return f'{y:04d}-{mo:02d}-{d:02d}', 'day'
    m = _MONTH.match(s)
    if m:
        y, mo = (int(x) for x in m.groups())
        last = calendar.monthrange(y, mo)[1]
        return f'{y:04d}-{mo:02d}-{last:02d}', 'month'
    m = _YEAR.match(s)
    if m:
        return f'{int(m.group(1)):04d}-12-31', 'year'
    raise ValueError(f'발간일을 읽을 수 없다: {raw!r}')


def report_id(org: str, native_id: str) -> str:
    """기관이 부여한 번호를 그대로 쓴다 — 재수집해도 안 흔들린다."""
    return f'{org}-{native_id}'


class RawReport(BaseModel):
    """수집기가 만드는 모양. 판정 필드가 없다."""

    id: str
    org: str
    board: str
    series: str
    title: str
    authors: list[str] = Field(default_factory=list)
    published: str
    date_precision: DatePrecision
    pages: Optional[int] = None
    landing_url: str
    file_url: Optional[str] = None
    abstract: Optional[str] = None
    toc: list[str] = Field(default_factory=list)
    # 원문 PDF 에서 초록을 뜯어 보려 시도했는가. 없으면 요약 섹션이 없는 보고서를
    # 회차마다 헛되이 다시 내려받는다. 사유는 abstract_note 에 남는다.
    abstract_tried: bool = False
    abstract_note: Optional[str] = None
    collected_at: Optional[str] = None

    @field_validator('published')
    @classmethod
    def _after_cutoff(cls, v: str) -> str:
        if v < CUTOFF:
            raise ValueError(f'{CUTOFF} 이전은 담지 않는다: {v}')
        return v


class Report(RawReport):
    """build 가 판정을 붙인 모양."""

    employment: bool
    matched: list[str] = Field(default_factory=list)
