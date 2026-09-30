"""PDF 보고서 수집기(한국은행·KDI)가 공유하는 회차 표현과 레코드 조립.

두 기관은 회차를 찾는 길이 다를 뿐(RSS vs 본문) 요약표를 읽어 레코드로 옮기는
일은 똑같다. 이 부분이 갈라지면 한쪽만 고쳐진 채 표기가 어긋나므로 여기 모은다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Callable, Collection, Mapping, NamedTuple, Sequence

from . import pdf
from .models import ForecastRecord, INDICATOR_META, make_id

KST = timezone(timedelta(hours=9))


class Issue(NamedTuple):
    title: str
    published_at: date
    url: str


# 매일 최근 몇 회차까지 다시 보는가. 최신 한 회차만 보면, 어떤 회차가 실패한 채로
# 다음 회차가 나오는 순간 그 회차는 다시 시도되지 않고 영영 빠진다 — BOK 2025년
# 11월판이 그렇게 넉 달 비어 있었다.
RECENT_ROUNDS = 3


class PartialFailure(Exception):
    """몇 회차는 받았고 몇 회차는 실패했다. 받은 것은 버리지 않는다(collect.main)."""

    def __init__(self, records: list[ForecastRecord], message: str):
        super().__init__(message)
        self.records = records


def collect_recent(issues: Sequence, collect_issue: Callable[..., list[ForecastRecord]],
                   known: Collection[date]) -> list[ForecastRecord]:
    """최근 RECENT_ROUNDS 회차 중 아직 없는 것(발표일 기준)만 받는다.

    이미 있는 회차는 요청도 안 한다 — 평소에는 최신 회차 하나를 보던 때와
    비용이 같다.
    """
    records: list[ForecastRecord] = []
    failures = []
    for issue in issues[:RECENT_ROUNDS]:
        if issue.published_at in known:
            continue
        try:
            records.extend(collect_issue(issue))
        except Exception as exc:
            failures.append(f"{issue.published_at} {type(exc).__name__}: {exc}")
    if failures:
        raise PartialFailure(records, " / ".join(failures))
    return records


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
