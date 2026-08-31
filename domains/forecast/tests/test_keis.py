from datetime import date
from pathlib import Path

import pytest

from domains.forecast.pipeline.collectors import keis

FIXTURES = Path(__file__).parent / "fixtures"
LIST_HTML = (FIXTURES / "keis_list.html").read_text(encoding="utf-8")


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
