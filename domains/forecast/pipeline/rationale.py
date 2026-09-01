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
# 맨 "growth" 만은 담지 않는다 — "employment growth"·"export growth"·
# "wage growth" 어디에나 붙어 다른 지표의 문장을 가로채고, 이를 막을
# 구체성 관계도 없다(성장 서술이면 뭐든 걸리는 것이지, 특정 낱말을 감싸는
# 게 아니다). "고용"은 그대로 둔다 — "고용률"과 겹치는 문제는 아래
# _MORE_SPECIFIC_FORM 이 명시적으로 처리하므로, 낱말 자체를 빼서 "고용
# 증가세가 이어질 것으로 전망된다" 같은 흔한 문장까지 놓칠 필요가 없다.
INDICATOR_WORDS: dict[str, tuple[str, ...]] = {
    "emp_change": ("취업자", "고용", "employment"),
    "emp_rate": ("고용률", "employment rate"),
    "unemp_rate": ("실업률", "unemployment"),
    "gdp_growth": ("성장률", "국내총생산", "GDP", "economic growth"),
    "cpi": ("소비자물가", "물가", "inflation", "CPI"),
    "labor_force": ("경제활동참가율", "participation"),
}

# 인과 표지 — 이 문장이 '왜' 를 말한다는 신호.
# "따라"·"따라서" 는 둘 다 뺀다. "~에 따라"는 "…에 의하면"이지 "…때문에"가
# 아니고, "~에 따라서"는 그 강조형이라 같은 문제를 그대로 되풀이한다.
# 문장 맨 앞의 "따라서"는 그나마 접속부사답게 쓰이지만, 그때 가리키는 원인은
# 이 문장이 아니라 앞 문장에 있다 — 인용문 한 문장만 떼어 저장하는 이 모듈의
# 전제(2.1)와 맞지 않는다. 배경·때문·기인·반영·영향·힘입어는 모두 원인이
# 그 문장 안에 있어 혼자 떼어내도 뜻이 선다.
_CAUSE = ("배경", "때문", "기인", "반영", "영향", "힘입어",
          "due to", "driven by", "reflecting", "supported by",
          "owing to", "on the back of")

# 전망 표지 — 지난 일이 아니라 앞을 말한다는 신호
_FORECAST = ("전망", "예상",
             "is projected", "are projected", "is expected", "are expected",
             "is forecast", "will")

# "것으로" 는 뒤에 앞을 보는 낱말이 올 때만 전망 표지다. 뒤에 오지 말아야
# 할 회고형(나타났다·밝혀졌다·확인됐다·드러났다·알려졌다·집계됐다 …)을
# 나열하는 금지 목록은 새 회고 동사가 나올 때마다 하나씩 뚫린다 — IMF
# 수집기의 오류 분기, KEIS 표 판정이 배웠던 것과 같은 이유로 허용 목록으로
# 돈다. 목록에 없는 낯선 동사는 실패로 닫힌다.
# 관측된다·예측된다도 관측·예측 기관이 흔히 쓰는 전망 어미다. 반대로
# 판단된다·풀이된다·추정된다·내다보인다는 뺀다 — 현재 상태에 대한 평가·해석·
# 추정이지 앞을 보는 말이 아니거나("판단된다"·"풀이된다"·"추정된다"), 이
# 보고서 문체에서 드물게 쓰인다("내다보인다").
_FORECAST_SUFFIX = re.compile(r"것으로\s*(?:전망|예상|보인다|기대된다|점쳐진다|관측된다|예측된다)")

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


# 낱말 하나가 다른 낱말 안에 통째로 들어 있다고 해서 그쪽이 더 구체적인 건
# 아니다 — "employment" 는 "unemployment" 안에도 부분열로 들어 있지만
# "un-" 부정 접두사일 뿐이라 실업이 고용의 더 구체적인 형태가 되는 게
# 아니다. 그런 포함 관계를 일반적으로 추론하면 이런 우연한 겹침까지
# 넘겨짚어 실업률 문장이 취업자 증감 자리로(혹은 그 반대로) 넘어간다.
# 그래서 추론하지 않고, 아래처럼 "이 낱말은 저 낱말의 더 구체적인 표현이다"
# 라고 이름 붙일 수 있는 쌍만 적어 둔다 — 새 겹침이 생기면 이유를 댈 수
# 있을 때만 여기 한 줄을 더한다.
_MORE_SPECIFIC_FORM = {
    "고용": "고용률",              # 고용 증감(emp_change) < 고용률(emp_rate)
    "employment": "employment rate",
}


def _claimed_by_a_more_specific_word(lowered: str, word: str) -> bool:
    """word 보다 더 구체적인 표현이 문장에도 있으면 참이다."""
    specific = _MORE_SPECIFIC_FORM.get(word)
    return specific is not None and specific in lowered


# 영문 표제어는 낱말 경계로 찾는다 — 안 그러면 "employment" 가 "un-" 부정
# 접두사가 붙은 "unemployment" 안에서도 우연히 걸려, 고용을 한마디도 안 한
# 순수 실업률 문장까지 emp_change 의 근거 후보가 된다. 한글 표제어는 그대로
# 부분열로 찾는다 — 조사가 명사에 바로 붙어("국내총생산은"처럼) 공백이
# 낱말 경계와 일치하지 않기 때문이다.
_ASCII_WORD = re.compile(r"^[a-z0-9][a-z0-9 ]*$")


def _word_present(lowered: str, word: str) -> bool:
    if _ASCII_WORD.match(word):
        return re.search(rf"\b{re.escape(word)}\b", lowered) is not None
    return word in lowered


def _mentions_indicator(lowered: str, indicator: str) -> bool:
    for word in INDICATOR_WORDS.get(indicator, ()):
        w = word.lower()
        if _word_present(lowered, w) and not _claimed_by_a_more_specific_word(lowered, w):
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
