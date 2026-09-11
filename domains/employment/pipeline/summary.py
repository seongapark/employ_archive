"""보도자료 hwpx 에서 **원문의 요약 줄을 그대로** 뽑아 온다.

세 출처 모두 첫머리에 요약 상자를 둔다. 그 줄들을 글자 그대로 가져오는 것이
이 모듈이 하는 전부다 — 문장을 새로 짓지 않는다. 화면이 "보도자료 요약" 이라
말하면서 우리가 쓴 문장을 보여주면, 그건 요약이 아니라 창작이다.

규칙이 아무것도 못 잡으면 빈 리스트를 돌려준다. 비슷해 보이는 줄로 때우지
않는다 — 빈칸은 화면이 "아직 없습니다" 라고 말하지만, 엉뚱한 줄은 아무도
틀린 줄 모른다.

출처마다 멈추는 방식이 다르다:

* 경활·행정통계는 요약 상자가 통째로 이어져 있어 **불릿이 끊기면** 끝이다.
* 사업체는 불릿 사이에 표가 끼어 있다. 같은 규칙을 쓰면 첫 줄만 건지므로
  **다음 절(`2.`) 이 나올 때까지** 읽는다.
"""
from __future__ import annotations

import re
from typing import Callable, NamedTuple, Sequence

from . import hwpx

MAX_LINES = 8


class Rule(NamedTuple):
    start: Callable[[str], bool]
    bullets: tuple[str, ...]
    # None 이면 불릿이 한 번 끊길 때 멈춘다.
    stop: Callable[[str], bool] | None


def _eaps_start(text: str) -> bool:
    # 목차에도 `□ 2026년 8월 고용동향(요약)` 이 있다. 그쪽은 불릿이 붙어 있어
    # 갈린다 — 본문 상자 제목에는 아무 기호도 없다.
    return text.endswith("(요약)") and not text.startswith("□")


RULES: dict[str, Rule] = {
    "eaps": Rule(start=_eaps_start, bullets=("□", "○"), stop=None),
    "ei": Rule(start=lambda t: t.startswith("<주요 특징>"),
               bullets=("▣", "○", "*"), stop=None),
    # 입·이직자 절에도 `□ (총괄)` 이 있다. 첫 번째만 쓴다.
    "est": Rule(start=lambda t: t.startswith("□ (총괄)"),
                bullets=("□", "ㅇ"),
                stop=lambda t: bool(re.match(r"^2\.\s", t))),
}


def extract(source: str, paragraphs: Sequence[str]) -> list[str]:
    rule = RULES.get(source)
    if rule is None:
        return []

    begin = None
    for i, text in enumerate(paragraphs):
        if rule.start(text):
            # 시작 표시 자체가 불릿이면(사업체의 `□ (총괄)`) 그 줄부터 담는다.
            begin = i if text.startswith(rule.bullets) else i + 1
            break
    if begin is None:
        return []

    lines: list[str] = []
    for text in paragraphs[begin:]:
        if rule.stop is not None and rule.stop(text):
            break
        if text.startswith(rule.bullets):
            lines.append(text)
            if len(lines) >= MAX_LINES:
                break
        elif rule.stop is None and lines:
            break
    return lines


def from_hwpx(source: str, data: bytes) -> list[str]:
    return extract(source, hwpx.paragraphs(data))
