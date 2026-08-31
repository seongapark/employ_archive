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
