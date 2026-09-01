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


def sentences(text: str, *, bullets: bool = False) -> list[str]:
    """본문을 문장 단위로 자른다. 빈 조각은 버린다.

    bullets 는 기본 False 로 잠가 둔다 — 이 옵션은 텍스트 레이어 없는
    PDF 를 OCR 로 읽는 KEIS 수집기만 명시적으로 켜야 한다(자세한 이유는
    _bullet_sentences 참고). 나머지 여섯 기관은 텍스트 레이어가 있는
    PDF 를 읽어 문장이 실제 마침표로 끝나므로 이 옵션을 켤 이유가 없고,
    잘못 켜졌을 때의 부작용(줄 감김으로 생긴 "-0.3%p" 같은 줄을 새 문장의
    시작으로 오인)을 감수할 이유도 없다.
    """
    if bullets:
        return _bullet_sentences(text)
    protected = _DECIMAL_POINT.sub(_DECIMAL_PLACEHOLDER, text)
    return [
        s.strip().replace(_DECIMAL_PLACEHOLDER, ".")
        for s in _SENTENCE.findall(protected)
        if s.strip()
    ]


# 불릿 표지 — 이 보고서들의 관행상 문장(또는 항목)이 시작하는 자리다.
# 뒤 세 개(ㅇ·□·○·▶)는 이 픽스처엔 없지만 국문 보고서 관행이라 미리 넣는다.
_BULLET_MARKERS = "-=>ㅇ□○▶"

# 한글도 로마자도 없는 줄 — 점선 같은 장식 규칙이다. 워터마크 URL('www.')은
# 이 조건 없이도 흔히 로마자를 포함하므로 따로 검사한다.
_HAS_WORD_CHAR = re.compile(r"[가-힣a-zA-Z]")


def _is_page_furniture(line: str) -> bool:
    """쪽 하단 장식 줄이다 — 워터마크 URL 이거나 장식 규칙(점선 등)이다.

    이 검사는 줄이 불릿 표지로 시작하는지 확인한 *뒤에* 걸어야 한다.
    예를 들어 '= =' 처럼 표지 문자(=) 하나뿐인 줄은 한글도 로마자도 없어
    이 조건에 걸리지만, 그건 장식이 아니라 (내용이 비었을 뿐) 불릿 한
    항목이다 — 불릿 판정이 이 판정보다 먼저 와야 그런 줄을 장식으로
    잘못 삼키지 않는다.
    """
    return "www." in line or _HAS_WORD_CHAR.search(line) is None


def _bullet_sentences(text: str) -> list[str]:
    """줄바꿈이 아니라 불릿 표지에서 문장을 가른다.

    텍스트 레이어 없는 PDF 를 OCR 로 읽으면 한 문장이 여러 줄에 걸쳐
    줄바꿈으로 감기고, 그 줄은 마침표로 끝나지 않는다. 줄바꿈 자체를
    경계로 쓰면 감긴 줄이 그대로 쪼개져 문장이 반 토막 난다 — KEIS
    2026년 제5호 20쪽 원문이 실례다: "…경기 개선 기대가"(주어)와 그
    다음 줄 "자리한 것으로 전망된다"(서술어)가 같은 문장인데 줄바꿈만
    보면 남남이 된다.

    대신 이 보고서들이 실제로 쓰는 불릿 표지(_BULLET_MARKERS)를 문장의
    시작으로 삼는다. 표지로 시작하지 않는 줄은 줄 감김으로 보고 공백을
    끼워 앞 문장에 이어 붙인다. 첫 표지가 나오기 전 줄(캡션·머리말)은
    아직 열린 문장이 없으므로 버린다.

    쪽 하단 장식 줄(_is_page_furniture)을 만나면 지금까지 모은 문장을
    닫고 그 장식 줄 자체는 버린다 — 안 그러면 마지막 문장이 "20 ⋯
    www.keis.or.kr" 같은 각주까지 통째로 삼켜, 사용자에게 보일 인용문에
    장식 문자가 섞여 나간다.
    """
    units: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            units.append(" ".join(current))
            current.clear()

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line[0] in _BULLET_MARKERS:
            flush()
            current.append(line[1:].strip())
        elif _is_page_furniture(line):
            flush()
        elif current:
            current.append(line)
        # current 가 비어 있고(첫 표지 전) 표지도 아니고 장식도 아닌 줄은
        # 캡션·머리말로 보고 조용히 지나간다.
    flush()
    return units


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


def pick(text: str, indicator: str, *, bullets: bool = False) -> str | None:
    """그 지표의 근거 문장을 준다. 없으면 None.

    세 조건을 모두 만족해야 한다 — 지표 언급, 인과 표지, 전망 표지. 하나라도
    없으면 근거로 보지 않는다. 느슨하게 잡으면 엉뚱한 문장이 기관의 근거로
    남고, 그 잘못은 그럴듯해서 아무도 의심하지 않는다. 빡빡한 쪽으로 틀린다.

    bullets 는 그대로 sentences() 에 넘길 뿐이다 — 문장을 무엇으로 볼지는
    sentences() 하나가 정하고, 여기 세 조건(지표·인과·전망)은 그 문장이
    무엇이든 똑같이 적용된다.
    """
    for sentence in sentences(text, bullets=bullets):
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
#
# 영문 낱말은 "IMF·OECD 가 한국을 두고 실제로 쓰는 표현"만 적는다 — 태그가
# 없다고 아무 말이나 채우면 그 낱말이 나중에 거짓 태그를 만든다.
# "건설투자"·"facility investment" 는 한국은행·통계청이 GDP 지출 항목을
# 영문으로 낼 때 쓰는 공식 명칭 그대로다(IMF Article IV 도 한국 자료를
# 인용할 때 이 이름을 그대로 쓴다). "manufacturing employment"·
# "construction employment" 는 OECD Economic Surveys: Korea 가 부문별
# 고용을 말할 때 쓰는 표현이다. "demographic"·"working-age population"·
# "aging population"/"ageing population"/"population aging"/
# "population ageing" 은 한국의 인구 감소를 다루는 IMF·OECD 문서에 흔히
# 나오는 표현이다("adverse demographics", "the working-age population is
# projected to decline", "a rapidly aging population"). "agricultural
# prices"·"administered prices" 는 한국 물가 분해를 다룰 때 IMF 가 쓰는
# 표현이다. "돌봄일자리"에는 영문을 붙이지 않는다 — 이건 정부가 보건복지
# 부문에 재정으로 만드는 한국 특유의 일자리 정책 용어라, IMF·OECD 문서에서
# 이 개념 하나를 가리키는 표준 표현을 찾지 못했다. 없는 것을 지어내 붙이면
# 그 자체가 검증 안 되는 태그가 된다.
#
# "aging" 을 낱말 하나로는 쓰지 않는다 — en_US 사전(로컬에 있는 Hunspell
# 사전, 62,002 낱말)을 전수 대조한 결과 damaging·discouraging·
# disparaging·encouraging·engaging·packaging·portaging·raging·staging
# 9개 낱말이 전부 "aging"을 부분열로 품고 있었고, 이 중 다수가 거시경제
# 서술에 흔히 쓰이는 낱말이다("Trade tensions are damaging the export
# outlook" 처럼). "population" 과 짝지은 구(句) 형태 4가지로만 적는다 —
# 이 구를 통째로 담는 낱말은 없다.
TAG_WORDS: dict[str, tuple[str, ...]] = {
    "수출": ("수출", "export"),
    "글로벌경기": ("글로벌", "세계경제", "global"),
    "환율": ("환율", "exchange rate"),
    "통상정책": ("통상", "관세", "tariff"),
    "내수": ("내수", "민간소비", "domestic demand"),
    "건설투자": ("건설투자", "건설경기", "construction investment"),
    "설비투자": ("설비투자", "facility investment"),
    "재정정책": ("재정", "추경", "fiscal"),
    "통화정책": ("통화정책", "금리", "monetary"),
    "인구구조": ("인구구조", "생산가능인구", "고령",
              "demographic", "working-age population",
              "aging population", "ageing population",
              "population aging", "population ageing"),
    "돌봄일자리": ("돌봄", "보건복지"),
    "제조업고용": ("제조업", "manufacturing employment"),
    "건설업고용": ("건설업", "construction employment"),
    "유가": ("유가", "oil price"),
    "농산물": ("농산물", "agricultural prices"),
    "공공요금": ("공공요금", "administered prices"),
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

    지표 낱말(INDICATOR_WORDS)과 달리 태그 낱말은 서로 경쟁하지 않는다 —
    표 안의 모든 낱말 쌍을 대조해도 겹치는 자리가 없다(태그 부여 조사 시
    확인). 그래서 영문도 낱말 경계를 두지 않고 한국어와 똑같이 부분열로
    찾는다: 경계를 두면 IMF·OECD 원문이 흔히 쓰는 복수형("exports"·
    "tariffs"·"oil prices"·"exchange rates")이 "s" 하나 때문에 걸리지
    않는다. 부분열로 찾을 때 생기는 거짓 겹침은 이 함수가 일반화해서
    처리하지 않고, _FALSE_CONTAINMENT 에 이름 붙은 것만 걸러낸다.
    """
    for unrelated in _FALSE_CONTAINMENT.get(word, ()):
        lowered = lowered.replace(unrelated, "")
    return word in lowered


def tags_for(sentence: str) -> list[str]:
    """인용한 문장 안의 낱말에서만 태그를 뽑는다.

    태그는 그 문장에 붙이는 이름표이지 추론이 아니다. '반도체' 가 수출을
    함의하더라도 문장에 '수출' 이 없으면 붙이지 않는다 — 지어낸 태그로 거른
    결과는 사용자가 검증할 방법이 없다.
    """
    lowered = sentence.lower()
    return [tag for tag, words in TAG_WORDS.items()
            if any(_word_present_as_tag(lowered, w.lower()) for w in words)]
