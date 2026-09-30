from datetime import date, datetime

from domains.forecast.pipeline import watch
from domains.forecast.pipeline.models import ForecastRecord, make_id


def rec(org: str, pub: date) -> ForecastRecord:
    return ForecastRecord(
        id=make_id(org, pub, "gdp_growth", pub.year), org=org, org_name_ko=org,
        report_title="t", published_at=pub, target_year=pub.year,
        indicator="gdp_growth", value=1.0, unit="%",
        source_url="https://example.com/a", landing_url="https://example.com",
        confidence="verified", collected_at=datetime(2026, 9, 1),
    )


OECD_SEP = ("OECD", date(2026, 9, 23), "[보도참고] 경제협력개발기구, 9월 중간 경제전망 발표")


def test_announced_round_missing_after_grace_fails():
    # 2026-09-30 사고 그대로: 기재부는 9/23 에 알렸고 우리 최신은 6/3 이었다
    records = [rec("OECD", date(2026, 6, 3))]
    got = watch.missing_announced(records, [OECD_SEP], date(2026, 9, 30))
    assert len(got) == 1 and "OECD 2026-09-23" in got[0]


def test_announced_round_within_grace_or_present_passes():
    assert watch.missing_announced([rec("OECD", date(2026, 6, 3))], [OECD_SEP], date(2026, 9, 24)) == []
    assert watch.missing_announced([rec("OECD", date(2026, 9, 23))], [OECD_SEP], date(2026, 9, 30)) == []


def test_notices_that_are_not_forecast_rounds_are_ignored():
    notices = [
        ("OECD", date(2026, 7, 2), "[보도참고] 경제협력개발기구(OECD) 2026 한국경제보고서 발표"),
        ("OECD", date(2026, 6, 2), "허장 2차관, 경제협력개발기구(OECD) 각료이사회 참석 위해 프랑스로 출국"),
        # IMF 업데이트는 수집 대상이 아니다
        ("IMF", date(2026, 7, 8), "[보도참고] 2026년 국제통화기금(IMF) 7월 세계경제전망(WEO) 업데이트"),
    ]
    records = [rec("OECD", date(2026, 6, 3)), rec("IMF", date(2026, 4, 14))]
    assert watch.missing_announced(records, notices, date(2026, 9, 30)) == []


def test_imf_regular_round_is_watched():
    notice = ("IMF", date(2026, 10, 14), "[보도참고] 2026년 국제통화기금(IMF) 10월 세계경제전망")
    got = watch.missing_announced([rec("IMF", date(2026, 4, 14))], [notice], date(2026, 10, 20))
    assert len(got) == 1


def test_domestic_org_overdue_by_its_own_rhythm():
    # 분기마다 내는 기관이 한 주기를 통째로 건너뛰면 울린다
    days = [date(2025, 11, 27), date(2026, 2, 26), date(2026, 5, 28), date(2026, 8, 27)]
    records = [rec("BOK", d) for d in days]
    assert watch.overdue(records, date(2026, 11, 30), ["BOK"]) == []
    assert len(watch.overdue(records, date(2026, 12, 31), ["BOK"])) == 1


def test_check_splits_orgs_between_notices_and_rhythm():
    records = [rec("OECD", date(2026, 6, 3)), rec("OECD", date(2026, 3, 26)),
               rec("KDI", date(2026, 5, 13)), rec("KDI", date(2026, 8, 19))]
    got = watch.check(records, date(2026, 9, 30), notices=lambda: [OECD_SEP])
    assert len(got) == 1 and got[0].startswith("OECD")
