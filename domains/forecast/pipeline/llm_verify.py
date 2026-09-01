"""LLM 이 고른 문장이 원문에 실재하는지 대조한다.

이 모듈은 네트워크를 모른다 — (후보, 원문) 두 문자열만 받는 순수 함수라
모델을 바꾸거나 사람이 손으로 넣은 문장에도 같은 검사가 걸린다.

핵심은 공백을 지우고 대조하는 것이다. 화면에는 "이 기관은 이렇게 전망했다"
로 뜨므로, LLM 이 매끄럽게 다듬은 문장은 그럴듯해서 아무도 의심하지 않는
최악의 실패가 된다. 낱말을 하나라도 바꾸면 이 대조에 걸린다.

공백을 무시하는 이유는 두 가지다. 원문 한 문장이 여러 줄에 걸쳐 있어도
이어 붙인 답이 통과해야 하고, pdfplumber 가 낱말 중간에 넣은 공백
("작용하 고,")을 LLM 이 붙여 쓴 것은 오히려 개선이라 막을 이유가 없다.
낱말 자체를 바꾸는 것과는 다른 일이다.
"""
from __future__ import annotations

import re

from .rationale import (_DUPLICATED_HANGUL, _MAX_RATIONALE_LENGTH)

_WHITESPACE = re.compile(r"\s+")


class Rejected(Exception):
    """후보를 저장하지 않는다. reason 은 로그에 그대로 남긴다."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def normalize(s: str) -> str:
    """공백을 전부 지운다. 줄바꿈도 공백이라 함께 사라진다."""
    return _WHITESPACE.sub("", s)


def verify(candidate: str, source_page_text: str) -> str:
    """통과하면 candidate 를 그대로 돌려준다. 아니면 Rejected."""
    if not candidate.strip():
        raise Rejected("빈 문장이다")
    if len(candidate) > _MAX_RATIONALE_LENGTH:
        raise Rejected(f"{_MAX_RATIONALE_LENGTH}자보다 길다({len(candidate)}자)")
    if _DUPLICATED_HANGUL.search(candidate):
        raise Rejected("굵은 글씨 반복 렌더링 흔적이 들어 있다")
    if normalize(candidate) not in normalize(source_page_text):
        raise Rejected("원문에 없다")
    return candidate
