from datetime import date, datetime

import pytest

from domains.forecast.pipeline import relink
from domains.forecast.pipeline.models import ForecastRecord


def _rec(org, url, **kw):
    base = dict(
        id=f"{org.lower()}-2026-04-gdp_growth-2026", org=org, org_name_ko=org,
        report_title="IMF World Economic Outlook, April 2026",
        published_at=date(2026, 4, 14), target_year=2026, target_period="annual",
        indicator="gdp_growth", value=2.5, unit="%",
        source_url=url, landing_url=url, confidence="verified",
        collected_at=datetime(2026, 4, 15),
    )
    base.update(kw)
    return ForecastRecord(**base)


def test_relink_replaces_only_the_urls():
    rec = _rec("IMF", "https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH/KOR")
    result = relink.relink([rec], {"IMF": lambda r: "https://www.imf.org/en/publications/weo/issues/x"})
    got = result.records[0]
    assert got.source_url == "https://www.imf.org/en/publications/weo/issues/x"
    assert got.landing_url == "https://www.imf.org/en/publications/weo/issues/x"
    # 수치와 식별자는 한 글자도 바뀌지 않는다
    assert (got.id, got.value, got.revision, got.prev_value) == (
        rec.id, rec.value, rec.revision, rec.prev_value)


def test_relink_leaves_other_orgs_alone():
    rec = _rec("BOK", "https://www.bok.or.kr/report.pdf", id="bok-1")
    result = relink.relink([rec], {"IMF": lambda r: "https://x"})
    assert result.records[0].source_url == "https://www.bok.or.kr/report.pdf"
    assert result.changed == 0


def test_relink_leaves_oecd_interim_alone():
    # OECD Interim 은 org 가 OECD 라 같은 해결자에 걸리지만, 이미 보고서 PDF를
    # 가리키고 있으므로 건드리면 안 된다. 제목에 회차 번호("Economic Outlook 119")를
    # 넣어 두어, edition_number 의 정규식이 우연히 실패해서 걸러지는 게 아니라
    # 해결자 자체가 "Interim" 을 보고 거른다는 것을 확인한다 — 회차 번호가
    # 읽혔다면 필터가 없었을 경우 oecd.report_url(네트워크 호출)까지 갔을 것이다.
    rec = _rec(
        "OECD", "https://oecd.example/report.pdf",
        id="oecd-interim-2026-03", org_name_ko="OECD",
        report_title="OECD Economic Outlook 119, Interim Report March 2026",
    )
    with pytest.raises(ValueError, match="Interim"):
        relink._oecd_resolver(rec)


def test_relink_reports_records_it_could_not_resolve():
    rec = _rec("IMF", "https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH/KOR")

    def failing(_):
        raise ValueError("회차를 찾지 못했다")

    result = relink.relink([rec], {"IMF": failing})
    assert result.changed == 0
    assert len(result.unresolved) == 1
    # 조용히 넘기지 않는다 — 원본은 그대로 남는다
    assert result.records[0].source_url == rec.source_url
