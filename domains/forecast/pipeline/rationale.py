"""전망 근거로 삼을 문장을 고른다.

기관도 PDF 도 모른다 — 본문과 지표코드를 받아 문장 하나를 고를 뿐이다. 기관별
규칙이 여기 번지지 않아야 테스트가 문자열만으로 돌고, 새 기관이 붙어도 이 파일이
자라지 않는다.

요약하지 않고 원문 문장을 그대로 준다. 요약은 기관이 하지 않은 말을 기관의
근거처럼 적을 위험이 있고, 그 오류는 수치와 달리 원문 대조로 드러나지 않는다.
"""
from __future__ import annotations

import re

# 지표 표제어. 한국어와 영어를 함께 둔다 — IMF·OECD 는 영문 보고서다.
INDICATOR_WORDS: dict[str, tuple[str, ...]] = {
    "emp_change": ("취업자", "고용", "employment"),
    "emp_rate": ("고용률", "employment rate"),
    "unemp_rate": ("실업률", "unemployment"),
    "gdp_growth": ("성장률", "국내총생산", "GDP", "growth"),
    "cpi": ("소비자물가", "물가", "inflation", "CPI"),
    "labor_force": ("경제활동참가율", "participation"),
}

# 인과 표지 — 이 문장이 '왜' 를 말한다는 신호
_CAUSE = ("배경", "때문", "기인", "반영", "영향", "힘입어", "따라",
          "due to", "driven by", "reflecting", "supported by",
          "owing to", "on the back of")

# 전망 표지 — 지난 일이 아니라 앞을 말한다는 신호
_FORECAST = ("전망", "예상", "것으로",
             "is projected", "are projected", "is expected", "are expected",
             "is forecast", "will")

_SENTENCE = re.compile(r"[^.。\n]+[.。]|[^.。\n]+$")


def sentences(text: str) -> list[str]:
    """본문을 문장 단위로 자른다. 빈 조각은 버린다."""
    return [s.strip() for s in _SENTENCE.findall(text) if s.strip()]


def pick(text: str, indicator: str) -> str | None:
    """그 지표의 근거 문장을 준다. 없으면 None.

    세 조건을 모두 만족해야 한다 — 지표 언급, 인과 표지, 전망 표지. 하나라도
    없으면 근거로 보지 않는다. 느슨하게 잡으면 엉뚱한 문장이 기관의 근거로
    남고, 그 잘못은 그럴듯해서 아무도 의심하지 않는다. 빡빡한 쪽으로 틀린다.
    """
    words = INDICATOR_WORDS.get(indicator, ())
    for sentence in sentences(text):
        lowered = sentence.lower()
        if not any(w.lower() in lowered for w in words):
            continue
        if not any(c.lower() in lowered for c in _CAUSE):
            continue
        if not any(f.lower() in lowered for f in _FORECAST):
            continue
        return sentence
    return None
