"""PDF 보고서 수집기(한국은행·KDI)가 공유하는 회차 표현과 레코드 조립.

두 기관은 회차를 찾는 길이 다를 뿐(RSS vs 본문) 요약표를 읽어 레코드로 옮기는
일은 똑같다. 이 부분이 갈라지면 한쪽만 고쳐진 채 표기가 어긋나므로 여기 모은다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Mapping, NamedTuple

from . import pdf
from .models import ForecastRecord, INDICATOR_META, make_id

KST = timezone(timedelta(hours=9))


class Issue(NamedTuple):
    title: str
    published_at: date
    url: str


def records_from_table(
    text: str,
    labels: Mapping[str, str],
    *,
    org: str,
    org_name_ko: str,
    issue: Issue,
    source_url: str,
    source_page: int,
) -> list[ForecastRecord]:
    """요약표 페이지 원문을 그 회차의 전망 레코드로 옮긴다."""
    return records_from_values(
        pdf.parse_summary_table(text, labels),
        org=org, org_name_ko=org_name_ko, issue=issue,
        source_url=source_url, source_page=source_page,
    )


def records_from_values(
    values: Mapping[tuple[str, int, str], float],
    *,
    org: str,
    org_name_ko: str,
    issue: Issue,
    source_url: str,
    source_page: int,
    confidence: str = "extracted",
) -> list[ForecastRecord]:
    """{(지표, 연도, 기간): 값} 을 그 회차의 전망 레코드로 옮긴다."""
    collected_at = datetime.now(KST)
    records = []
    for (indicator, year, period), value in sorted(values.items()):
        # 발표연도보다 앞선 해는 전망이 아니라 실적이다
        if year < issue.published_at.year:
            continue
        meta = INDICATOR_META[indicator]
        records.append(ForecastRecord(
            id=make_id(org, issue.published_at, indicator, year, period),
            org=org,
            org_name_ko=org_name_ko,
            report_title=issue.title,
            published_at=issue.published_at,
            target_year=year,
            target_period=period,
            indicator=indicator,
            value=round(value, meta["decimals"]),
            unit=meta["unit"],
            source_url=source_url,
            source_page=source_page,
            landing_url=issue.url,
            confidence=confidence,
            collected_at=collected_at,
        ))
    return records


def rationales_from_text(text: str, *, org: str, issue: Issue,
                         indicators: Iterable[str], source_url: str,
                         source_page: int | None,
                         bullets: bool = False) -> list["Rationale"]:
    """본문에서 지표별 근거 문장을 뽑는다. 없는 지표는 건너뛴다.

    bullets 는 rationale.pick 에 그대로 넘긴다 — OCR 로만 읽는 수집기(KEIS)가
    줄바꿈이 아니라 불릿 표지로 문장을 가르고 싶을 때 켠다. 기본은 False 라
    이 함수를 그대로 쓰는 다른 다섯 기관은 지금과 똑같이 동작한다.
    """
    from . import rationale
    from .rationale_store import Rationale

    out = []
    for indicator in indicators:
        sentence = rationale.pick(text, indicator, bullets=bullets)
        if sentence is None:
            continue
        out.append(Rationale(
            org=org, published_at=issue.published_at, indicator=indicator,
            text=sentence, tags=rationale.tags_for(sentence),
            source_url=source_url, source_page=source_page,
        ))
    return out
