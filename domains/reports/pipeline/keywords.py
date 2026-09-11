"""고용 키워드 매칭. **판정은 하지 않는다.**

다섯 기관 전부에 돌린다. keywords 는 거르는 도구가 아니라 **분류하는
도구**다 — 결과(matched)는 담을지 말지가 아니라 주제 화면의 입구로 쓰인다.
읽을 만한 것을 고르는 일(거르는 일)은 recommend 가 별도 파일에서 한다.
키워드를 고치면 재수집 없이 build 가 수십 초에 다시 매긴다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

KEYWORDS_PATH = Path(__file__).resolve().parent.parent / 'data' / 'keywords.json'

_SPACE = re.compile(r'\s+')


def load_keywords(path: Path | str | None = None) -> dict[str, list[str]]:
    p = Path(path or KEYWORDS_PATH)
    return json.loads(p.read_text(encoding='utf-8'))


def _squash(s: str) -> str:
    """공백을 지운다 — '청년 고용'과 '청년고용'을 같은 것으로 본다."""
    return _SPACE.sub('', s or '')


def match(text: str, keywords: dict[str, list[str]] | None = None) -> list[str]:
    kw = keywords if keywords is not None else load_keywords()
    hay = _squash(text)
    hits: list[str] = []
    for topic, words in kw.items():
        if any(_squash(w) in hay for w in words):
            hits.append(topic)
    return hits
