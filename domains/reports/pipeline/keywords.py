"""고용 키워드 매칭. **판정은 하지 않는다.**

매칭은 네 기관 전부에 돌리고, 그 결과를 담을지 말지에 쓰는 것만 build 가
KDI·KIET 로 한정한다(스펙 §5-3). 둘을 나누지 않으면 KLI·KEIS 레코드의
matched 가 비어 주제 화면이 반쪽이 된다.
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
