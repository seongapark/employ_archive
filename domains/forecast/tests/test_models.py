from datetime import date, datetime
import pytest
from domains.forecast.pipeline.models import ForecastRecord, make_id, VALUE_RANGES, INDICATOR_META


def base_kwargs(**over):
    kw = dict(
        id="oecd-2026-08-gdp_growth-2027", org="OECD", org_name_ko="OECD",
        report_title="Economic Outlook 119", published_at=date(2026, 8, 29),
        target_year=2027, indicator="gdp_growth", value=1.9, unit="%",
        source_url="https://www.oecd.org/en/publications/"
                    "oecd-economic-outlook-volume-2026-issue-1_2d1956f0-en.html",
        landing_url="https://www.oecd.org/en/publications/"
                    "oecd-economic-outlook-volume-2026-issue-1_2d1956f0-en.html",
        confidence="verified", collected_at=datetime(2026, 8, 29, 16, 0),
    )
    kw.update(over)
    return kw


def test_valid_record_with_defaults():
    r = ForecastRecord(**base_kwargs())
    assert r.target_period == "annual"
    assert r.prev_value is None
    assert r.revision is None
    assert r.source_page is None


def test_record_no_longer_carries_a_rationale_field():
    # 근거는 rationales.json 이 정본이다. 두 곳에 두면 어느 쪽이 맞는지 모호해진다
    assert "rationale" not in ForecastRecord.model_fields
    assert "rationale_tags" not in ForecastRecord.model_fields


def test_value_out_of_range_rejected():
    with pytest.raises(ValueError):
        ForecastRecord(**base_kwargs(value=12.5))  # gdp_growth 범위는 -10~10


def test_unknown_indicator_rejected():
    with pytest.raises(ValueError):
        ForecastRecord(**base_kwargs(indicator="gdp"))


def test_api_looking_source_url_rejected():
    with pytest.raises(ValueError, match="source_url"):
        ForecastRecord(**base_kwargs(
            source_url="https://sdmx.oecd.org/public/rest/data/OECD.ECO.MAD,DSD_EO@DF_EO,/KOR"
        ))


def test_api_looking_landing_url_rejected():
    with pytest.raises(ValueError, match="landing_url"):
        ForecastRecord(**base_kwargs(
            landing_url="https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES"
        ))


def test_datamapper_api_path_rejected():
    # 호스트는 www.imf.org 로 평범해 보여도 경로에 /api/ 가 있으면 기계용이다
    with pytest.raises(ValueError):
        ForecastRecord(**base_kwargs(
            source_url="https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH/KOR"
        ))


# 실제 수집기들이 레코드에 박아 넣는 진짜 보고서 주소들 — 오탐 없이 통과해야 한다
REAL_REPORT_URLS = [
    "https://www.imf.org/en/publications/weo/issues/2026/04/14/world-economic-outlook-april-2026",
    "https://www.oecd.org/en/publications/oecd-economic-outlook-volume-2026-issue-1_2d1956f0-en.html",
    "https://www.oecd.org/content/dam/oecd/en/publications/reports/2025/03/"
    "oecd-economic-outlook-interim-report-march-2025_47a36021/89af4857-en.pdf",
    "https://www.bok.or.kr/fileSrc/portal/411de844aef442e7ad07896b7bbe2eef/1/"
    "4e0f66601a6a4f95ac4164f9286de537.pdf",
    "https://www.bok.or.kr/portal/bbs/P0002359/view.do?nttId=10088282&menuNo=200066",
    "https://www.kdi.re.kr/file/download?atch_no=%2FxwjQYioi8mBMiV99xGqUQ%3D%3D",
    "https://www.kdi.re.kr/research/economy?pub_no=18476",
    "https://www.keis.or.kr/keis/ko/cmmn/download.do?dn=20251231110535986.pdf&path=pblc"
    "&fn=report.pdf&sn=11264&fsn=22414&ty=P",
    "https://www.keis.or.kr/keis/ko/proj/118/pblc/detail.do?categoryIdx=126&pubIdx=11264",
    "https://www.kiet.re.kr/common/file/userDownload?atch_no=6xVUWLubWriyVwkZiQ%2BZPQ%3D%3D",
    "https://www.kiet.re.kr/trends/ecolookView?ecolook_no=50",
    "https://www.kli.re.kr/boardDownload.es?bid=0002&list_no=145319&seq=1",
    "https://www.kli.re.kr/board.es?mid=a10201010100&bid=0002&act=view&list_no=145319",
]


@pytest.mark.parametrize("url", REAL_REPORT_URLS)
def test_real_report_urls_from_every_collector_are_accepted(url):
    ForecastRecord(**base_kwargs(source_url=url, landing_url=url))


def test_make_id():
    assert make_id("OECD", date(2026, 8, 29), "gdp_growth", 2027) == \
        "oecd-2026-08-gdp_growth-2027"


def test_meta_loaded_from_indicators_json():
    assert set(VALUE_RANGES) == set(INDICATOR_META)
    assert VALUE_RANGES["gdp_growth"] == (-10, 10)
    assert INDICATOR_META["emp_change"]["unit"] == "만명"


def test_make_id_keeps_annual_ids_unchanged():
    assert make_id("BOK", date(2026, 8, 27), "emp_change", 2026, "annual") == \
        "bok-2026-08-emp_change-2026"


def test_make_id_separates_half_year_records():
    assert make_id("BOK", date(2026, 8, 27), "emp_change", 2026, "h1") == \
        "bok-2026-08-emp_change-2026-h1"
    assert make_id("BOK", date(2026, 8, 27), "emp_change", 2026, "h2") == \
        "bok-2026-08-emp_change-2026-h2"
