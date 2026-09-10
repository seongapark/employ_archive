"""PDF 쪽 텍스트에서 저자가 쓴 초록(`요 약` 섹션)을 뽑는다.

기관도 네트워크도 PDF 라이브러리도 모른다 — **쪽 텍스트 목록만 받는다.**
그래서 테스트가 실제 보고서에서 뜬 텍스트 픽스처만으로 돈다.

**요약 섹션이 없으면 아무것도 내지 않는다.** 본문 앞부분을 대신 실어 두는
안(발췌)을 만들어 실측까지 했다가 뺐다(2026-09-10 사용자 결정). 두 가지가
걸렸다. 하나는 그 글이 저자가 "이게 요약이다" 라고 쓴 글이 아니라는 것이고,
하나는 브리프류가 거의 다 2단 조판이라 흔한 PDF 추출기가 왼쪽 단과 오른쪽
단을 한 줄씩 번갈아 이어 붙인다는 것이다 — 사람이 읽을 수 없는 글이 나온다.
덩어리를 갈라 읽으면 풀리지만, 그렇게까지 해서 얻는 것이 목차도 초록도 없는
49건(KDI FOCUS·현안분석)뿐이라 값이 안 맞았다.
"""
from __future__ import annotations

import re

# 요약 섹션이 시작하는 쪽: 본문이 '요 약' 으로 열린다.
# 목차 쪽은 '목 차' 로 열리므로 여기 걸리지 않는다.
_SUMMARY_START = re.compile(r'^\s*요\s*약(\s|$)')
# 요약이 끝나고 본문이 시작하는 신호.
_BODY_START = re.compile(r'^\s*(제\s*1\s*장|제\s*Ⅰ\s*장|Ⅰ\s*\.|1\s*\.\s*서\s*론|서\s*론\s*$)')
# 러닝헤더 조각: '요 약 ⅲ', 'ⅳ', 로마자만 있는 줄.
_ROMAN = r'[ⅰ-ⅿⅠ-Ⅿivxlcdm]+'
_HEADER_ONLY = re.compile(rf'^\s*(요\s*약\s*)?{_ROMAN}\s*$', re.I)
_HEADER_WITH_TITLE = re.compile(rf'^\s*{_ROMAN}\s+\S.{{0,60}}$', re.I)
_SECTION_TITLE = re.compile(r'^\s*요\s*약\s*$')


def extract(pages: list[str]) -> str | None:
    """요약 섹션 전문. 없으면 None."""
    start = _summary_start(pages)
    if start is None:
        return None
    chunks = []
    for i in range(start, len(pages)):
        text = pages[i] or ''
        if i > start and _BODY_START.match(text):
            break
        cleaned = _strip_headers(text, first=(i == start))
        if cleaned:
            chunks.append(cleaned)
    return _join(chunks) or None


def _summary_start(pages: list[str]) -> int | None:
    for i, text in enumerate(pages or []):
        if _SUMMARY_START.match(text or ''):
            return i
    return None


def _strip_headers(text: str, *, first: bool) -> str:
    out = []
    for n, line in enumerate((text or '').split('\n')):
        s = line.strip()
        if not s:
            continue
        if n < 2 and (_HEADER_ONLY.match(s) or _HEADER_WITH_TITLE.match(s)):
            continue
        if first and _SECTION_TITLE.match(s):
            continue
        out.append(s)
    return ' '.join(out)


def _join(chunks: list[str]) -> str:
    s = ' '.join(c for c in chunks if c)
    # 줄 끝에서 잘린 낱말을 붙인다: 'multidi- mensional' → 'multidimensional'
    s = re.sub(r'([A-Za-z])-\s+([a-z])', r'\1\2', s)
    return re.sub(r'\s+', ' ', s).strip()
