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


# 기획서 3.3 의 태그 체계. 순서를 표와 같게 두어 화면에서 늘 같은 차례로 보인다.
TAG_WORDS: dict[str, tuple[str, ...]] = {
    "수출": ("수출", "export"),
    "글로벌경기": ("글로벌", "세계경제", "global"),
    "환율": ("환율", "exchange rate"),
    "통상정책": ("통상", "관세", "tariff"),
    "내수": ("내수", "민간소비", "domestic demand"),
    "건설투자": ("건설투자", "건설경기"),
    "설비투자": ("설비투자",),
    "재정정책": ("재정", "추경", "fiscal"),
    "통화정책": ("통화정책", "금리", "monetary"),
    "인구구조": ("인구구조", "생산가능인구", "고령"),
    "돌봄일자리": ("돌봄", "보건복지"),
    "제조업고용": ("제조업",),
    "건설업고용": ("건설업",),
    "유가": ("유가", "oil price"),
    "농산물": ("농산물",),
    "공공요금": ("공공요금",),
}


# 짧은 태그 낱말이 부분열로 걸리는 흔한 낱말 중, 뜻이 그 태그와 무관한 것.
# "통상적(으로)"는 "평소·으레"라는 뜻이지 통상정책과 무관하고, "통상임금"은
# 초과근로수당 산정 기준이 되는 노동법 용어(정기적으로 지급되는 통상의
# 급여)이지 무역 통상정책과 무관하다. "유가증권"은 증권 용어이지 원유
# 가격과 무관하다. 셋 다 "employment" 가 "unemployment" 안에 우연히
# 들어 있는 것과 같은 모양의 사고다 — 짧은 낱말이 더 긴 낱말 안에 들어
# 있다고 해서 그 긴 낱말이 짧은 낱말의 한 예가 되는 게 아니다. 이런
# 겹침을 일반적으로 추론하지 않고, "이 긴 낱말 안에서는 이 짧은 낱말을
# 세지 않는다"라고 이름 붙일 수 있는 쌍만 여기 적어 둔다 — 새 겹침이 생기면
# 이유를 댈 수 있을 때만 한 줄을 더한다.
_FALSE_CONTAINMENT: dict[str, tuple[str, ...]] = {
    "통상": ("통상적", "통상임금"),
    "유가": ("유가증권",),
}


def _word_present_as_tag(lowered: str, word: str) -> bool:
    """word 가 태그 낱말로 실제 나타났는지 본다.

    _FALSE_CONTAINMENT 에 등록된, 뜻이 다른 더 긴 낱말 안에서만 나타난
    경우는 세지 않는다 — 그 부분을 지우고도 word 가 남아 있어야 진짜로
    나타난 것이다.
    """
    for unrelated in _FALSE_CONTAINMENT.get(word, ()):
        lowered = lowered.replace(unrelated, "")
    return _word_present(lowered, word)


def tags_for(sentence: str) -> list[str]:
    """인용한 문장 안의 낱말에서만 태그를 뽑는다.

    태그는 그 문장에 붙이는 이름표이지 추론이 아니다. '반도체' 가 수출을
    함의하더라도 문장에 '수출' 이 없으면 붙이지 않는다 — 지어낸 태그로 거른
    결과는 사용자가 검증할 방법이 없다.
    """
    lowered = sentence.lower()
    return [tag for tag, words in TAG_WORDS.items()
            if any(_word_present_as_tag(lowered, w.lower()) for w in words)]
