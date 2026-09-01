from datetime import date
from pathlib import Path

import pytest

from domains.forecast.pipeline.collectors import kli

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = (FIXTURES / "kli_2026_forecast.txt").read_text(encoding="utf-8")
ISSUE = kli.Issue("2025년 노동시장 평가와 2026년 노동시장 전망", date(2026, 1, 2),
                  "https://www.kli.re.kr/board.es?list_no=147627")


def by_key(records):
    return {(r.indicator, r.target_year, r.target_period): r for r in records}


def test_table_block_excludes_the_caption_and_the_prose_around_it():
    # 표 앞뒤로 서술이 길게 붙어 있어 페이지를 통째로 넘기면 헤더를 잘못 잡는다.
    # 캡션도 빼야 한다 — "...하반기 및 ... 연간 고용 전망" 의 기간 낱말이
    # 헤더로 딸려 들어가면 열 복원이 어긋난다.
    block = kli.forecast_table(PAGE)
    assert "고용 전망" not in block          # 캡션 제외
    assert "상반기 하반기p 연간p" in block    # 진짜 헤더는 남는다
    assert "취업자" in block
    assert "인구추계" not in block           # 표 뒤 본문도 들어오면 안 된다


def test_parse_reads_the_employment_forecast():
    got = by_key(kli.parse(PAGE, ISSUE, "https://x/y.pdf", 24))
    assert got[("emp_change", 2026, "annual")].value == 21.0   # 210천명 -> 21.0만명
    assert got[("unemp_rate", 2026, "annual")].value == 2.8
    assert got[("emp_rate", 2026, "annual")].value == 63.1


def test_parse_keeps_the_half_year_columns():
    got = by_key(kli.parse(PAGE, ISSUE, "https://x/y.pdf", 24))
    assert got[("emp_change", 2026, "h1")].value == 22.0
    assert got[("emp_change", 2026, "h2")].value == 20.0
    assert got[("emp_rate", 2026, "h1")].value == 62.9


def test_parse_drops_years_before_publication():
    years = {r.target_year for r in kli.parse(PAGE, ISSUE, "https://x/y.pdf", 24)}
    assert years == {2026}


def test_parse_record_fields():
    r = by_key(kli.parse(PAGE, ISSUE, "https://x/y.pdf", 24))[("emp_change", 2026, "annual")]
    assert r.org == "KLI"
    assert r.org_name_ko == "한국노동연구원"
    assert r.unit == "만명"
    assert r.confidence == "extracted"
    assert r.published_at == date(2026, 1, 2)
    assert r.id == "kli-2026-01-emp_change-2026"


def test_parse_omits_indicators_the_report_does_not_forecast():
    inds = {r.indicator for r in kli.parse(PAGE, ISSUE, "https://x/y.pdf", 24)}
    assert "gdp_growth" not in inds  # 노동시장 전망이라 성장률·물가는 없다
    assert "cpi" not in inds


def test_forecast_table_raises_when_the_caption_is_missing():
    with pytest.raises(ValueError):
        kli.forecast_table("표가 없는 페이지 본문")


class _Resp:
    def __init__(self, text="", content=b""):
        self.text = text
        self.content = content


def test_collect_issue_rationales_finds_the_real_employment_rationale(monkeypatch):
    # 이 보고서는 표 앞뒤 서술이 표와 같은 쪽에 실린다 — PAGE 픽스처가
    # 그 쪽 원문 그대로다(2025년 12월호, 68쪽).
    monkeypatch.setattr(kli.http, "get", lambda url, **kw: _Resp(content=b"%PDF"))
    monkeypatch.setattr(kli.pdf, "page_texts", lambda data: ["표지", PAGE])

    got = kli.collect_issue_rationales(ISSUE)
    by_ind = {r.indicator: r for r in got}
    # PAGE 에서 그대로 딴 문장이다 — 지어내지 않는다
    assert by_ind["emp_change"].text == (
        "2025년 하반기 고용 증가폭은 20만 명을 상회할 것으로 예상되는데, 이는 보건업 및 "
        "사회복지 서비스업, 정보통신업, 전문ㆍ과학 및 기술서비스업 등 서비스업 전반의 "
        "견조한 고용 증가가 뒷받침된 결과이다."
    )
    assert by_ind["emp_change"].org == "KLI"
    assert by_ind["emp_change"].published_at == ISSUE.published_at
    # 근거는 그 문장이 실제로 실린 쪽(2, 표지 다음)으로 인용한다 —
    # 고정된 쪽 번호가 아니라 실제로 찾은 쪽이어야 한다
    assert by_ind["emp_change"].source_page == 2
    assert by_ind["emp_change"].source_url == kli.DOWNLOAD_URL.format(no="147627")


def test_collect_issue_rationales_excludes_indicators_this_report_does_not_forecast(monkeypatch):
    # 같은 쪽에 "이러한 긍정적 전망의 주요 원인으로는 …" 처럼 성장률을 말하는
    # 문장도 있지만(실측), 이 기관은 성장률·물가를 전망하지 않으므로
    # gdp_growth·cpi 근거로 저장되면 안 된다.
    monkeypatch.setattr(kli.http, "get", lambda url, **kw: _Resp(content=b"%PDF"))
    monkeypatch.setattr(kli.pdf, "page_texts", lambda data: [PAGE])

    got = kli.collect_issue_rationales(ISSUE)
    inds = {r.indicator for r in got}
    assert "gdp_growth" not in inds
    assert "cpi" not in inds


def test_collect_issue_rationales_returns_empty_when_no_table_found(monkeypatch):
    monkeypatch.setattr(kli.http, "get", lambda url, **kw: _Resp(content=b"%PDF"))
    monkeypatch.setattr(kli.pdf, "page_texts", lambda data: ["표지", "본문"])

    assert kli.collect_issue_rationales(ISSUE) == []
