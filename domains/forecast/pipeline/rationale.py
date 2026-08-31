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
# "고용"·맨 "growth" 처럼 흔한 낱말은 담지 않는다 — "고용"은 "고용률"·
# "고용시장" 안에도 들어 있고, "growth"는 "employment growth"·"export
# growth"·"wage growth" 어디에나 붙어 다른 지표의 문장을 가로챈다. 아래
# _claimed_by_a_more_specific_word 가 남은 겹침(예: "employment" 대
# "employment rate")을 한 번 더 막아준다.
INDICATOR_WORDS: dict[str, tuple[str, ...]] = {
    "emp_change": ("취업자", "employment"),
    "emp_rate": ("고용률", "employment rate"),
    "unemp_rate": ("실업률", "unemployment"),
    "gdp_growth": ("성장률", "국내총생산", "GDP", "economic growth"),
    "cpi": ("소비자물가", "물가", "inflation", "CPI"),
    "labor_force": ("경제활동참가율", "participation"),
}

# 인과 표지 — 이 문장이 '왜' 를 말한다는 신호.
# "따라" 는 빼고 "따라서"만 둔다 — "정부 지침에 따라"는 "…에 의하면"이지
# "…때문에"가 아니다. "따라서"만 온전히 인과다.
_CAUSE = ("배경", "때문", "기인", "반영", "영향", "힘입어", "따라서",
          "due to", "driven by", "reflecting", "supported by",
          "owing to", "on the back of")

# 전망 표지 — 지난 일이 아니라 앞을 말한다는 신호
_FORECAST = ("전망", "예상",
             "is projected", "are projected", "is expected", "are expected",
             "is forecast", "will")

# "것으로" 는 대개 앞을 보는 말이지만 "것으로 나타났다/밝혀졌다/조사됐다"는
# 이미 드러난 사실을 말한다 — 그 뒤에 이런 완결형이 오면 전망 표지로 치지 않는다.
_FORECAST_SUFFIX = re.compile(r"것으로(?!\s*(?:나타났|밝혀졌|조사됐|조사되었))")

_SENTENCE = re.compile(r"[^.。\n]+[.。]|[^.。\n]+$")

# 마침표가 숫자 사이(소수점)에 오면 문장 끝이 아니다 — "0.3%p" 를 문장
# 경계로 잘못 보면 인용문이 숫자 한가운데서 끊겨 주어를 잃는다. 분리 전에
# 원문에 나타날 일이 없는 사용자 정의 영역 문자로 잠깐 숨겨 둔다.
_DECIMAL_POINT = re.compile(r"(?<=\d)\.(?=\d)")
_DECIMAL_PLACEHOLDER = ""


def sentences(text: str) -> list[str]:
    """본문을 문장 단위로 자른다. 빈 조각은 버린다."""
    protected = _DECIMAL_POINT.sub(_DECIMAL_PLACEHOLDER, text)
    return [
        s.strip().replace(_DECIMAL_PLACEHOLDER, ".")
        for s in _SENTENCE.findall(protected)
        if s.strip()
    ]


def _claimed_by_a_more_specific_word(lowered: str, word: str, indicator: str) -> bool:
    """다른 지표의 낱말이 이 낱말을 통째로 품고, 그 낱말도 문장에 있으면 참이다.

    "고용"은 "고용률" 안에 들어 있다. 고용률을 말하는 문장에서 emp_change 의
    "고용"이 먼저 걸리면 실업률 자리에 성장률 설명이 붙는 것과 같은 사고가
    난다 — 더 구체적인(감싸는) 낱말이 문장에 있으면 그쪽에 양보한다.
    """
    for other_indicator, other_words in INDICATOR_WORDS.items():
        if other_indicator == indicator:
            continue
        for other_word in other_words:
            ow = other_word.lower()
            if word != ow and word in ow and ow in lowered:
                return True
    return False


def _mentions_indicator(lowered: str, indicator: str) -> bool:
    for word in INDICATOR_WORDS.get(indicator, ()):
        w = word.lower()
        if w in lowered and not _claimed_by_a_more_specific_word(lowered, w, indicator):
            return True
    return False


def pick(text: str, indicator: str) -> str | None:
    """그 지표의 근거 문장을 준다. 없으면 None.

    세 조건을 모두 만족해야 한다 — 지표 언급, 인과 표지, 전망 표지. 하나라도
    없으면 근거로 보지 않는다. 느슨하게 잡으면 엉뚱한 문장이 기관의 근거로
    남고, 그 잘못은 그럴듯해서 아무도 의심하지 않는다. 빡빡한 쪽으로 틀린다.
    """
    for sentence in sentences(text):
        lowered = sentence.lower()
        if not _mentions_indicator(lowered, indicator):
            continue
        if not any(c.lower() in lowered for c in _CAUSE):
            continue
        if not (any(f.lower() in lowered for f in _FORECAST)
                or _FORECAST_SUFFIX.search(lowered)):
            continue
        return sentence
    return None
