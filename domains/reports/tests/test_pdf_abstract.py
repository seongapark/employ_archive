"""PDF 초록 추출.

픽스처는 2026-09-10 에 기관 사이트에서 받은 실제 보고서에서 **쪽 텍스트만**
뜬 것이다(PDF 원본은 저장소에 두지 않는다). 앞 20쪽까지다.
"""
import json
from pathlib import Path

import pytest

from domains.reports.pipeline import pdf_abstract as pa

FIX = Path(__file__).parent / 'fixtures' / 'pdf'


def pages(name):
    return json.loads((FIX / f'{name}.json').read_text(encoding='utf-8'))['pages']


def extract(name):
    return pa.extract(pages(name))


# ── 요약 섹션이 있는 연구보고서 ─────────────────────────────────────────

@pytest.mark.parametrize('name,head', [
    ('kli-10303', '한국은 저출산과 고령화가'),
    ('kli-10285', '1. 서 론'),
])
def test_research_reports_yield_the_authors_summary(name, head):
    out = extract(name)
    assert out and out.startswith(head), name
    assert len(out) > 3000, '요약은 서너 쪽이다 — 한 쪽만 잡혔으면 구간이 틀렸다'


def test_summary_stops_before_the_body():
    # 제1장이 시작하면 멈춰야 한다. 안 멈추면 보고서 전문이 초록으로 들어간다.
    assert '제1장 서 론 제1절 연구의 배경' not in extract('kli-10303')


def test_running_headers_are_stripped():
    # '요 약 ⅲ' 같은 쪽머리가 문장 사이에 끼면 읽을 수 없게 된다.
    out = extract('kli-10285')
    assert '요 약 ⅰ' not in out
    assert '요 약 ⅲ' not in out


def test_words_broken_across_lines_are_rejoined():
    out = extract('kli-10285')
    assert 'multidimensional' in out
    assert 'multidi- mensional' not in out


def test_the_table_of_contents_is_not_mistaken_for_the_summary():
    # 목차에도 '요 약 ……… ⅰ' 줄이 있다. 그 쪽에서 시작하면 목차가 초록이 된다.
    assert '목 차' not in extract('kli-10303')[:200]


# ── 요약 섹션이 없으면 아무것도 내지 않는다 ─────────────────────────────

@pytest.mark.parametrize('name,why', [
    ('kli-10301', '노동리뷰 — 여러 편의 글 묶음'),
    ('kli-10298', '국제노동브리프 — 여러 편의 글 묶음'),
    ('kli-10282', '포럼 발제문집 — 요약 섹션이 없다'),
    ('kdi-18356', 'KDI FOCUS — 저자 요약 없이 본문으로 시작한다'),
])
def test_documents_without_a_summary_section_yield_nothing(name, why):
    # 본문 앞부분을 대신 싣지 않는다. 저자가 쓴 요약이 아니고, 브리프류는
    # 2단 조판이라 흔한 추출기가 좌우 단을 한 줄씩 섞어 놓는다.
    assert extract(name) is None, why


def test_empty_and_image_only_pdfs_are_quiet():
    # 스캔본은 쪽 텍스트가 전부 빈 문자열로 온다(KEIS 인력수급전망이 그렇다).
    assert pa.extract([]) is None
    assert pa.extract([''] * 52) is None
