"""원문 PDF 로 초록 채우기.

네트워크에도 PDF 라이브러리에도 나가지 않는다 — `fetch` 와 `read` 를 주입한다.
그 주입 지점이 있다는 사실 자체를 여기서 지킨다.
"""
import pytest

from domains.reports.pipeline import enrich
from domains.reports.pipeline.models import RawReport

SUMMARY = ['요 약\n이 연구는 청년 고용을 다룬다.', '제1장 서 론\n본문이다.']


def rec(**kw):
    base = dict(id='kli-1', org='kli', board='kli-research', series='연구보고서',
                title='제목', published='2025-05-01', date_precision='day',
                landing_url='https://example.org/1', file_url='https://example.org/1.pdf')
    base.update(kw)
    return RawReport(**base)


def test_a_record_with_an_abstract_is_left_alone():
    assert enrich.needs_text(rec(abstract='이미 있다')) is False


def test_a_record_without_a_file_cannot_be_helped():
    assert enrich.needs_text(rec(file_url=None)) is False


def test_a_record_tried_once_is_not_downloaded_again():
    # 이게 없으면 요약 없는 보고서를 회차마다 다시 내려받는다.
    assert enrich.needs_text(rec(abstract_tried=True)) is False
    assert enrich.needs_text(rec()) is True


def test_the_summary_lands_in_the_abstract():
    r = rec()
    enrich.enrich_record(r, fetch=lambda url: b'%PDF-fake', read=lambda data: SUMMARY)
    assert r.abstract.startswith('이 연구는 청년 고용을')
    assert r.abstract_tried is True and r.abstract_note is None


def test_a_document_without_a_summary_says_so():
    r = rec()
    enrich.enrich_record(r, fetch=lambda url: b'%PDF-fake',
                         read=lambda data: ['목 차\n제1장 …'])
    assert r.abstract is None
    assert r.abstract_note == '요약 섹션 없음'


def test_a_scanned_book_is_named_as_one():
    # 쪽 텍스트가 전부 비어 온다(KEIS 인력수급전망). '요약 없음' 과 구별해야
    # OCR 이 필요한 건수를 나중에 셀 수 있다.
    r = rec()
    enrich.enrich_record(r, fetch=lambda url: b'%PDF-fake', read=lambda data: [''] * 40)
    assert r.abstract_note == '텍스트가 없는 스캔본'


def test_a_download_failure_is_recorded_not_raised():
    # 한 건이 죽어서 회차가 통째로 멈추면 안 된다.
    def boom(url):
        raise RuntimeError('502')
    r = rec()
    assert enrich.enrich_record(r, fetch=boom) is True
    assert '내려받기 실패' in r.abstract_note
    assert r.abstract_tried is True, '실패도 시도다 — 표시가 없으면 매번 다시 받는다'


def test_a_broken_pdf_is_recorded_not_raised():
    def boom(data):
        raise ValueError('EOF marker not found')
    r = rec()
    assert enrich.enrich_record(r, fetch=lambda url: b'%PDF-fake', read=boom) is True
    assert 'PDF 를 열 수 없음' in r.abstract_note


def test_a_huge_file_is_skipped_before_parsing():
    r = rec()
    enrich.enrich_record(r, fetch=lambda url: b'%PDF-' + b'x' * enrich.MAX_BYTES,
                         read=lambda data: pytest.fail('열지 말았어야 한다'))
    assert '너무 큼' in r.abstract_note


def test_read_pdf_refuses_what_is_not_a_pdf():
    # 로그인 페이지 HTML 이 오는 경우가 있다. pdfplumber 에 넘기면 예외가 난다.
    assert enrich.read_pdf('<html>로그인이 필요합니다</html>'.encode('utf-8')) == []
