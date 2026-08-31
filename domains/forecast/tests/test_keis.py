from datetime import date
from pathlib import Path

import pytest

from domains.forecast.pipeline.collectors import keis

FIXTURES = Path(__file__).parent / "fixtures"
LIST_HTML = (FIXTURES / "keis_list.html").read_text(encoding="utf-8")
PAGE_2026_08 = (FIXTURES / "keis_2026-08_forecast.txt").read_text(encoding="utf-8")
PAGE_2025_12 = (FIXTURES / "keis_2025-12_forecast.txt").read_text(encoding="utf-8")


def _lines(text):
    return [line for line in text.split("\n") if line.strip()]


def test_parse_list_reads_title_date_and_pdf_link():
    listed = keis.parse_list(LIST_HTML)
    first = listed[0]
    assert first.issue.title == "고용동향브리프 2026년 제5호"
    assert first.issue.published_at == date(2026, 8, 3)
    assert first.pdf_url.startswith("https://www.keis.or.kr/keis/ko/cmmn/download.do?")
    assert "sn=11349" in first.pdf_url


def test_parse_list_uses_the_per_issue_detail_page_as_landing():
    # 목록 URL 을 쓰면 회차가 밀려날 때 링크가 다른 호를 가리킨다
    first = keis.parse_list(LIST_HTML)[0]
    assert first.issue.url == (
        "https://www.keis.or.kr/keis/ko/proj/118/pblc/detail.do"
        "?categoryIdx=126&pubIdx=11349"
    )


def test_parse_list_does_not_double_count_the_featured_block():
    # 목록 맨 위 대표 게시물은 1번 행과 같은 회차를 한 번 더 싣는다
    listed = keis.parse_list(LIST_HTML)
    assert len(listed) == 2
    assert [item.issue.published_at for item in listed] == [
        date(2026, 8, 3), date(2025, 12, 31)
    ]


def test_parse_list_keeps_the_newest_first():
    listed = keis.parse_list(LIST_HTML)
    assert listed[0].issue.published_at > listed[1].issue.published_at


def test_parse_list_raises_when_a_publication_row_has_no_date():
    # subject 앵커는 있는데 cell-date 가 없다 — 서식이 바뀐 게시물 행
    row = """
    <tr>
      <td class="cell-subject">
        <a href="javascript:void(0)" onclick="goDetail('categoryIdx=126&pubIdx=99999')">
          고용동향브리프 날짜없음호
        </a>
      </td>
      <td class="cell-link"><div class="btn-group">
        <a href="/keis/ko/cmmn/download.do?dn=x.pdf&amp;sn=99999" class="btn btn-sm btn-primary">다운로드</a>
      </div></td>
    </tr>
    """
    with pytest.raises(ValueError):
        keis.parse_list(row)


def test_parse_list_raises_when_a_publication_row_has_no_pdf_link():
    # subject 앵커와 게시일은 있는데 download.do 링크가 없다
    row = """
    <tr>
      <td class="cell-subject">
        <a href="javascript:void(0)" onclick="goDetail('categoryIdx=126&pubIdx=99999')">
          고용동향브리프 PDF없음호
        </a>
      </td>
      <td class="cell-date"><span>2026.01.01</span></td>
    </tr>
    """
    with pytest.raises(ValueError):
        keis.parse_list(row)


def test_parse_list_skips_a_row_without_a_subject_anchor():
    # goDetail(...) 앵커가 없는 행은 헤더·레이아웃용 행이라 조용히 건너뛴다
    header_row = """
    <tr>
      <th class="cell-no">번호</th>
      <th class="cell-subject">제목</th>
      <th class="cell-date">등록일</th>
    </tr>
    """
    assert keis.parse_list(header_row) == []


def test_header_columns_reads_four_annual_columns():
    got = keis.header_columns(_lines(PAGE_2025_12))
    assert got == [(2023, "annual"), (2024, "annual"),
                   (2025, "annual"), (2026, "annual")]


def test_header_columns_attaches_half_years_to_the_last_year():
    # 반기 두 열은 마지막 연도의 하위 열이고 표 오른쪽에 붙는다
    got = keis.header_columns(_lines(PAGE_2026_08))
    assert got == [(2023, "annual"), (2024, "annual"), (2025, "annual"),
                   (2026, "annual"), (2026, "h1"), (2026, "h2")]


def test_header_columns_ignores_the_caption_year_without_a_suffix():
    # 캡션의 '표1 20264 고용 전망' 은 연도 줄이 아니다 — '년' 이 없다
    got = keis.header_columns(_lines(PAGE_2026_08))
    assert len(got) == 6


def test_header_columns_ignores_ocr_noise_on_the_year_line():
    # 헤더 줄 끝에 'Sandan' 같은 쓰레기 토큰이 붙는다
    got = keis.header_columns(["2023년 2024년 2025년 2026년6 Sandan", "상반기 하반기"])
    assert got == [(2023, "annual"), (2024, "annual"), (2025, "annual"),
                   (2026, "annual"), (2026, "h1"), (2026, "h2")]


def test_header_columns_raises_when_there_is_no_year_row():
    with pytest.raises(ValueError, match="연도 줄"):
        keis.header_columns(["취업자 28,416 28,576", "실업률 2.7 2.8"])


ISSUE_2026_08 = keis.Issue(
    "고용동향브리프 2026년 제5호", date(2026, 8, 3),
    "https://www.keis.or.kr/keis/ko/proj/118/pblc/detail.do?categoryIdx=126&pubIdx=11349")
ISSUE_2025_12 = keis.Issue(
    "[본문] 2025년 고용동향브리프_10호_최종", date(2025, 12, 31),
    "https://www.keis.or.kr/keis/ko/proj/118/pblc/detail.do?categoryIdx=126&pubIdx=11264")


def by_key(records):
    return {(r.indicator, r.target_year, r.target_period): r for r in records}


def test_parse_table_picks_the_change_row_under_employed():
    # '(증감)' 은 생산가능인구·경제활동인구·취업자 밑에 세 번 나온다.
    # 취업자 아래 것만 emp_change 다.
    got = keis.parse_table(PAGE_2025_12)
    assert got[("emp_change", 2026, "annual")] == 16.2   # 162천명 -> 16.2만명
    assert got[("emp_change", 2025, "annual")] == 20.5   # 205천명, 경활 (192) 아님


def test_parse_table_keeps_the_section_across_a_label_only_then_numbers_only_split():
    # tesseract psm 6 이 라벨 줄과 숫자 줄을 둘로 쪼갤 때가 있다. 숫자만
    # 있는 줄(label == "")이 대분류를 지우면, 그 다음 줄의 진짜 '(증감)'
    # 라벨이 '취업자' 대분류를 잃어 emp_change 를 못 찾는다.
    table = "\n".join([
        "2023년 2024년 2025년 2026년",
        "취업자",
        "28,416 28,576 28,781 28,943",
        "(증감) (327) (159) (205) (162)",
        "실업률 2.7 2.8 2.7 2.7",
        "고용률 62.6 62.7 62.9 63.0",
    ])
    got = keis.parse_table(table)
    assert got[("emp_change", 2026, "annual")] == 16.2


def test_parse_table_resets_section_after_a_block_ends():
    # 취업자의 '(증감)' 뒤에 실업자처럼 새 대분류 아닌 행이 오고, 거기에도
    # '(증감)' 하위행이 있다면 — 대분류를 안 지우면 이 값이 emp_change 로
    # 잘못 덮어써진다. 실업자의 (999)들이 뚜렷이 다른 값이라 회귀가 나면
    # 바로 드러난다.
    table = "\n".join([
        "2024년 2025년 2026년",
        "취업자 28,576 28,781 28,943",
        "(증감) (159) (205) (162)",
        "실업자 823 810 812",
        "(증감) (999) (999) (999)",
        "실업률 2.8 2.7 2.7",
        "고용률 62.7 62.9 63.0",
    ])
    got = keis.parse_table(table)
    assert got[("emp_change", 2025, "annual")] == 20.5
    assert got[("emp_change", 2026, "annual")] == 16.2
    assert all(value != 99.9 for (indicator, *_), value in got.items()
               if indicator == "emp_change")


def test_parse_table_reads_rates_without_conversion():
    got = keis.parse_table(PAGE_2025_12)
    assert got[("emp_rate", 2026, "annual")] == 63.0
    assert got[("unemp_rate", 2026, "annual")] == 2.7


def test_parse_table_reads_the_half_year_columns():
    got = keis.parse_table(PAGE_2026_08)
    assert got[("emp_change", 2026, "annual")] == 14.6
    assert got[("emp_change", 2026, "h1")] == 10.8
    assert got[("emp_change", 2026, "h2")] == 18.5
    assert got[("emp_rate", 2026, "h2")] == 63.3
    assert got[("unemp_rate", 2026, "h2")] == 2.6


def test_parse_table_ignores_indicators_we_do_not_collect():
    # 경제활동참가율은 표에 있지만 어느 수집기도 채우지 않는 지표라 뺀다
    got = keis.parse_table(PAGE_2026_08)
    assert not any(indicator == "labor_force" for indicator, _, _ in got)


def test_parse_table_raises_when_the_table_is_incomplete():
    # 서식이 바뀌어 절반만 읽히면 조용히 넘기지 않는다. emp_change 는
    # 찾았으니 이건 '다른 표'가 아니라 전망표가 망가진 것이다 —
    # NotForecastTable 이 아닌 일반 ValueError 여야 find_forecast_page 가
    # 이걸 건너뛰지 않고 그대로 흘려보낸다.
    partial = "\n".join([
        "2023년 2024년 2025년 2026년",
        "취업자 28,416 28,576 28,781 28,943",
        "(증감) (327) (159) (205) (162)",
    ])
    with pytest.raises(ValueError, match="지표") as exc_info:
        keis.parse_table(partial)
    assert not isinstance(exc_info.value, keis.NotForecastTable)


def test_parse_table_raises_not_forecast_table_when_no_indicator_matches():
    # 연도 헤더는 있는데 우리 지표가 하나도 안 걸린다 — 브리프에 흔한
    # '다른 표'(예: 고용률 추이표)를 만난 정상적인 경우다.
    other_table = "\n".join([
        "2023년 2024년 2025년 2026년",
        "제조업 4,500 4,520 4,480 4,510",
        "서비스업 18,200 18,350 18,500 18,620",
    ])
    with pytest.raises(keis.NotForecastTable):
        keis.parse_table(other_table)


def test_parse_table_raises_a_plain_error_when_a_real_table_has_the_wrong_column_count():
    # OCR 이 헤더의 반기 하위줄('상반기 하반기')을 통째로 놓쳐 열이 4개인데
    # 데이터 줄은 여전히 6개짜리다. 지표 라벨은 다 걸리므로(취업자 밑
    # (증감), 실업률, 고용률) 이건 '다른 표'가 아니라 전망표를 못 읽은
    # 것이다 — NotForecastTable 이 아닌 일반 ValueError 여야
    # find_forecast_page 가 조용히 건너뛰지 않고 그대로 흘려보낸다.
    garbled_header = "\n".join([
        "2023년 2024년 2025년 2026년",
        "잡음",  # 상반기·하반기 하위줄이 사라진 자리
        "취업자 28,416 28,576 28,781 28,943 28,738 29,093",
        "(증감) (327) (159) (205) (162) (108) (185)",
        "실업률 2.7 2.8 2.7 2.7 3.2 2.6",
        "고용률 62.6 62.7 62.9 63.0 62.5 63.3",
    ])
    with pytest.raises(ValueError, match="열 개수") as exc_info:
        keis.parse_table(garbled_header)
    assert not isinstance(exc_info.value, keis.NotForecastTable)


def test_number_parses_wrapped_and_bare_values():
    assert keis._number("(146)") == 146.0
    assert keis._number("(-0.8)") == -0.8
    assert keis._number("(0.0)") == 0.0
    assert keis._number("146") == 146.0
    assert keis._number("29,203") == 29203.0
    assert keis._number("−177") == -177.0


def test_number_rejects_unbalanced_brackets_and_non_numbers():
    # '1)' 같은 각주 표시가 숫자로 읽히면 그 줄의 값 개수가 하나 밀린다
    assert keis._number("1)") is None
    assert keis._number("(146") is None
    assert keis._number("(증감)") is None
    assert keis._number("(증가율)") is None
    assert keis._number("30H") is None
    assert keis._number("15~29세") is None


def test_number_rejects_tokens_that_strip_to_nothing():
    # ',,,' 는 정규식은 통과하지만 콤마를 지우면 빈 문자열이라 숫자가 아니다.
    # float("") 로 새는 ValueError 를 여기서 막아야 find_forecast_page 가
    # "표 없음"으로 오판하지 않는다.
    assert keis._number(",,,") is None
    assert keis._number("(,,,)") is None
    assert keis._number(",") is None


def test_parse_drops_years_before_publication():
    years = {r.target_year for r in keis.parse(PAGE_2026_08, ISSUE_2026_08, "https://x/y.pdf", 19)}
    assert years == {2026}


def test_parse_keeps_the_publication_year_column():
    # 공표일 기준 전망치는 모두 넣는다 — 지난 상반기 열도 버리지 않는다
    got = by_key(keis.parse(PAGE_2025_12, ISSUE_2025_12, "https://x/y.pdf", 10))
    assert got[("emp_change", 2025, "annual")].value == 20.5
    assert got[("emp_change", 2026, "annual")].value == 16.2


def test_parse_keeps_the_elapsed_first_half():
    got = by_key(keis.parse(PAGE_2026_08, ISSUE_2026_08, "https://x/y.pdf", 19))
    assert ("emp_change", 2026, "h1") in got


def test_parse_marks_records_as_extracted_with_the_source_page():
    record = keis.parse(PAGE_2026_08, ISSUE_2026_08, "https://x/y.pdf", 19)[0]
    assert record.org == "KEIS"
    assert record.org_name_ko == "한국고용정보원"
    assert record.confidence == "extracted"
    assert record.source_page == 19
    assert record.source_url == "https://x/y.pdf"
    assert record.landing_url == ISSUE_2026_08.url


def test_parse_uses_the_right_units():
    got = by_key(keis.parse(PAGE_2026_08, ISSUE_2026_08, "https://x/y.pdf", 19))
    assert got[("emp_change", 2026, "annual")].unit == "만명"
    assert got[("emp_rate", 2026, "annual")].unit == "%"


PAGE_NO_FORECAST = (FIXTURES / "keis_no_forecast.txt").read_text(encoding="utf-8")
LISTED_2026_08 = keis.ListedIssue(ISSUE_2026_08, "https://x/keis-2026-5.pdf")


def test_find_forecast_page_returns_the_table_page_with_its_number():
    got = keis.find_forecast_page(
        [PAGE_NO_FORECAST, PAGE_2025_12], [9, 10], ISSUE_2025_12.published_at)
    assert got == (10, PAGE_2025_12)


def test_find_forecast_page_skips_the_prose_page_that_quotes_the_numbers():
    # 도입부 쪽은 같은 수치를 문장으로 싣는다. 표 형태로 지표가 다 나오는
    # 쪽만 고르므로 자연히 걸러진다.
    assert keis.find_forecast_page(
        [PAGE_NO_FORECAST], [9], ISSUE_2026_08.published_at) is None


def test_find_forecast_page_returns_none_when_the_issue_has_no_forecast():
    assert keis.find_forecast_page(
        [PAGE_NO_FORECAST, PAGE_NO_FORECAST], [3, 4], ISSUE_2026_08.published_at) is None


def test_find_forecast_page_reraises_errors_other_than_a_missing_header():
    # 헤더는 있는데 지표가 일부만 읽히면 표는 있는데 못 읽은 것이다 — 이건
    # "표 없음"이 아니므로 건너뛰지 않고 그대로 위로 흘려보내야 한다.
    broken = "\n".join([
        "2023년 2024년 2025년 2026년",
        "취업자 28,416 28,576 28,781 28,943",
        "(증감) (327) (159) (205) (162)",
    ])
    with pytest.raises(ValueError, match="지표"):
        keis.find_forecast_page([broken], [3], ISSUE_2026_08.published_at)


def test_find_forecast_page_skips_a_different_table_and_finds_the_real_one_later():
    # 2025년 10호에서 실제로 벌어진 회귀 — 연도 헤더가 있는 다른 표(예:
    # 산업별 취업자)를 먼저 만나도, 지표가 하나도 안 걸리면 "다른 표"로
    # 건너뛰고 뒤쪽의 진짜 전망표를 찾아내야 한다.
    other_table = "\n".join([
        "2023년 2024년 2025년 2026년",
        "제조업 4,500 4,520 4,480 4,510",
        "서비스업 18,200 18,350 18,500 18,620",
    ])
    got = keis.find_forecast_page(
        [other_table, PAGE_2025_12], [2, 10], ISSUE_2025_12.published_at)
    assert got == (10, PAGE_2025_12)


def test_find_forecast_page_skips_a_past_years_only_summary_table():
    # 도입부의 요약표는 취업자·(증감)·실업률·고용률을 과거 연도만으로 채워
    # 우리 지표 3개가 다 걸린다 — parse_table 은 그대로 통과시킨다. 하지만
    # 발표연도 이상 열이 하나도 없으니 진짜 전망표가 아니다. 이 표가 뒤쪽의
    # 진짜 전망표보다 먼저 나와도 건너뛰고 계속 찾아야 한다.
    past_years_only = "\n".join([
        "2021년 2022년 2023년 2024년",
        "취업자 27,583 27,896 28,166 28,416",
        "(증감) (306) (313) (270) (250)",
        "실업률 3.0 2.9 2.9 2.8",
        "고용률 61.5 61.9 62.2 62.6",
    ])
    got = keis.find_forecast_page(
        [past_years_only, PAGE_2025_12], [3, 10], ISSUE_2025_12.published_at)
    assert got == (10, PAGE_2025_12)


def test_collect_issue_reads_the_table_with_two_ocr_passes():
    calls = []

    by_page = {3: PAGE_NO_FORECAST, 4: PAGE_2025_12}

    def fake_read_pages(data, pages=None, *, dpi=400, preprocess=True):
        calls.append({"pages": pages, "dpi": dpi, "preprocess": preprocess})
        if pages is None:                      # 1차 스크리닝
            return ["표지", "목차", PAGE_NO_FORECAST, PAGE_2025_12]
        return [by_page[p] for p in pages]

    records = keis.collect_issue(
        LISTED_2026_08, fetch=lambda url: b"%PDF-", read_pages=fake_read_pages)

    assert calls[0] == {"pages": None, "dpi": 150, "preprocess": False}
    assert calls[1] == {"pages": [3, 4], "dpi": 400, "preprocess": True}
    assert by_key(records)[("emp_change", 2026, "annual")].value == 16.2
    assert records[0].source_page == 4


def test_collect_issue_returns_nothing_when_the_issue_has_no_forecast_table():
    # 대부분의 호가 그렇다. 실패가 아니다.
    def fake_read_pages(data, pages=None, *, dpi=400, preprocess=True):
        return ["표지", "본문"] if pages is None else [PAGE_NO_FORECAST]

    assert keis.collect_issue(
        LISTED_2026_08, fetch=lambda url: b"%PDF-", read_pages=fake_read_pages) == []


def test_collect_issue_raises_when_a_real_table_is_unreadable():
    # 헤더는 있는데 지표가 일부만 읽히면 서식이 바뀐 것이다 — 조용히 넘기지 않는다
    broken = "\n".join([
        "2023년 2024년 2025년 2026년",
        "취업자 28,416 28,576 28,781 28,943",
        "(증감) (327) (159) (205) (162)",
        "전망",
    ])

    def fake_read_pages(data, pages=None, *, dpi=400, preprocess=True):
        return [broken] if pages is None else [broken]

    with pytest.raises(ValueError, match="지표"):
        keis.collect_issue(LISTED_2026_08, fetch=lambda url: b"%PDF-",
                           read_pages=fake_read_pages)


def test_collect_issue_raises_when_an_accepted_page_yields_no_records(monkeypatch):
    # find_forecast_page 가 이미 발표연도 이상 열이 있는 쪽만 통과시켰으니,
    # 그 쪽에서 parse 가 빈 리스트를 낸다면 그건 "전망 없음"이 아니라
    # 모순이다 — 빈 리스트로 조용히 넘기지 않고 실패시킨다.
    monkeypatch.setattr(
        keis, "find_forecast_page", lambda texts, pages, published_at: (4, "dummy"))
    monkeypatch.setattr(keis, "parse", lambda text, issue, url, page: [])

    def fake_read_pages(data, pages=None, *, dpi=400, preprocess=True):
        return ["전망"] if pages is None else ["dummy"]

    with pytest.raises(ValueError, match="레코드"):
        keis.collect_issue(LISTED_2026_08, fetch=lambda url: b"%PDF-",
                           read_pages=fake_read_pages)
