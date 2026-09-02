"""고른 문장에 태그를 붙이고, 검증기가 쓰는 상수를 쥐고 있다.

문장을 고르는 일은 여기 없다 — 그 일은 이제 LLM(`llm_select.py`)이 한다.
LLM 이 고른 문장이 원문에 실재하는지 대조하는 검증은 `llm_verify.py` 에
있다. 이 파일에 남은 것은 두 가지뿐이다.

1. **태깅**(tagging) — `tags_for` · `TAG_WORDS` · `_FALSE_CONTAINMENT` ·
   `_word_present_as_tag`. 입력은 고른 문장 하나, 출력은 태그 리스트다.
2. `llm_verify.py` 가 그대로 가져다 쓰는 상수 — `_MAX_RATIONALE_LENGTH`
   (근거로 인정할 길이 상한) · `_DUPLICATED_HANGUL`(볼드체 겹침 렌더링
   결함 판정) · `_BULLET_MARKERS`/`_WRAP_BOUNDARY_MARKERS`(인용된 조각이
   문장·항목이 시작하는 자리에서 시작했는지 가릴 때 쓰는 표지 문자 집합).
   문장을 자르는 데는 더 이상 안 쓰이지만, 뜻은 남아 있다 — "이 표지로
   시작하는 자리가 새 항목의 머리다"는 지금도 참이고, `llm_verify` 는 그
   판단을 후보 문장이 진짜 항목 머리에서 시작했는지 검사하는 데 쓴다.

문장을 통째로 요약하지 않고 원문 그대로 인용하는 원칙, 그리고 태그가
추론이 아니라 문장에 실제로 있는 낱말에서만 나온다는 원칙은 선별이
LLM 으로 옮겨간 뒤에도 그대로다 — 이 파일이 아니라 `llm_select.py` ·
`llm_verify.py` 가 그 원칙을 지킨다.
"""
from __future__ import annotations

import re

# 근거로 인정할 유닛의 길이 상한. llm_verify.verify() 가 후보 문장의 길이를
# 검사할 때 그대로 쓴다.
#
# 실측 기준: 이 코퍼스 23개 픽스처를 통틀어 지표·인과·전망 세 조건을 모두
# 만족하는 가장 긴 실제 문장은 143자(KIET cpi)였고, 조건 없이 살아남는
# 가장 짧은 표 덩어리는 723자(OECD interim 2026-03 10쪽)였다. 300은 그
# 143자의 두 배쯤이면서 723자의 절반에도 한참 못 미친다 — 두 값 사이에
# 넉넉한 틈이 있어 정확한 숫자 자체는 예민하지 않다는 것이 이 상한을 두는
# 요점이다.
_MAX_RATIONALE_LENGTH = 300

# BOK 볼드체 인쇄가 pdfplumber 로는 글자마다 3번씩 겹쳐 뽑힌다 — 그 결과
# "낙낙낙관관관시시시나나나리리리오오오"처럼 같은 한글 음절이 세 번 이상
# 내리 반복된다. 산문이 아니라 렌더링 결함이다. llm_verify.verify() 가 후보
# 문장에 이 결함이 섞여 있는지 검사할 때 그대로 쓴다.
#
# 실측: bok_2026-08_summary.txt(순수 볼드 표 픽스처) 한 곳에서만 이런
# 3연속 동일 음절이 21회 나오고, 이 코퍼스의 진짜 산문 문장에는 단 한 곳도
# 없다 — "경경경제제제전전전망망망 요요요약약약표표표"·"낙낙낙관관관시시시
# 나나나리리리오오오"가 실례다.
#
# 한글 음절([가-힣])에만 건다 — 숫자에는 걸지 않는다. "1000"은 "0"이 세 번
# 이어지는 정당한 수치 표기이고, "222000222666" 처럼 숫자만 삼중 반복돼도
# 그 자체가 결함은 아니다(둘레 텍스트가 결함이라 결함처럼 '보일' 뿐이다).
# 숫자까지 걸면 진짜 수치를 담은 정상 문장을 통째로 버리게 된다.
_DUPLICATED_HANGUL = re.compile(r"([가-힣])\1\1")

# 불릿 표지 — 이 보고서들의 관행상 문장(또는 항목)이 시작하는 자리다.
# 이 상수의 전체 목록은 '-'·'='·'>'·'ㅇ'·'□'·'○'·'▶'·'ㆍ' 여덟이다.
#
# llm_verify._START_BOUNDARY_MARKERS 가 이 집합과 아래 _WRAP_BOUNDARY_MARKERS
# 의 합집합을 그대로 가져다 쓴다 — LLM 이 고른 후보 문장이 인용부호 중간이
# 아니라 실제 문장·항목의 머리에서 시작했는지 원문 좌표로 되짚어 확인할
# 때, "이 문자로 시작하는 자리가 새 항목의 머리다"라는 뜻을 그대로 재사용
# 하는 것이다.
_BULLET_MARKERS = "-=>ㅇ□○▶ㆍ"

# 줄 감김을 편 뒤 "여기서 새 항목이 시작한다"고 볼 표지. _BULLET_MARKERS 와
# 겹치지만 '-' 를 빼고 '•'·'*'·'§' 를 더한 값이다 — 원래는 텍스트 레이어가
# 있는 PDF 를 읽는 경로가 OCR 경로와 다른 글자를 표지로 썼기 때문이다(OCR
# 은 '•' 가 'ㅇ'·'○'·'-' 로 뭉개져 나오고, '-' 는 문장 불릿이 아니라 표
# 안의 음수 부호로만 쓰였다).
#
# llm_verify._START_BOUNDARY_MARKERS 가 위 _BULLET_MARKERS 와 합쳐 그대로
# 쓴다 — 후보가 어느 수집 경로에서 왔는지 그 모듈은 모르므로 두 집합을
# 가리지 않고 합쳐 받는다.
_WRAP_BOUNDARY_MARKERS = "=>ㅇ□○▶•*§"


# 낱말 하나가 다른 낱말 안에 통째로 들어 있다고 해서 그쪽이 더 구체적인 건
# 아니다. 짧은 태그 낱말이 부분열로 걸리는 흔한 낱말 중, 뜻이 그 태그와
# 무관한 것만 이름 붙여 걸러낸다.
#
# "통상적(으로)"는 "평소·으레"라는 뜻이지 통상정책과 무관하고, "통상임금"은
# 초과근로수당 산정 기준이 되는 노동법 용어(정기적으로 지급되는 통상의
# 급여)이지 무역 통상정책과 무관하다. "유가증권"은 증권 용어이지 원유
# 가격과 무관하다. 이런 겹침을 일반적으로 추론하지 않고, "이 긴 낱말
# 안에서는 이 짧은 낱말을 세지 않는다"라고 이름 붙일 수 있는 쌍만 여기
# 적어 둔다 — 새 겹침이 생기면 이유를 댈 수 있을 때만 한 줄을 더한다.
#
# "이유"는 실제로 배포된 데이터에서 잡았다 — rationales.json 의 KLI
# 2025-08-29 emp_change 근거가 "…취업자 수 증가가 예상보다 컸던 **이유가**
# 예상을 넘어선 고령층…"이라는 문장 하나 때문에 화면에 "요인은 유가"로
# 떴다. 원유 가격은 그 문장에 한 글자도 없다. "유가증권"보다 훨씬 위험한
# 겹침이다: "이유"는 한국어에서 흔한 낱말인 데다, 하필 **인과를 말하는
# 문장에 특히 자주** 나온다 — 이 기능이 고르는 문장이 정확히 그런 문장이다.
# "국제유가 상승이 이유가 되어…" 처럼 둘 다 든 문장에서는 "이유"만 지워도
# 진짜 "유가"가 남아 태그가 그대로 붙는다(실측).
#
# "건설업체"는 코퍼스 안에서 찾은 같은 부류다 — kdi_2025-08_p4.txt 의
# "**건설업체**의 재무건전성 악화"가 맨 "건설업"에 걸려, 건설회사의 재무
# 상태를 말하는 문장에 "건설업고용"(건설업 **고용**) 태그가 붙는다. 회사의
# 재무와 그 업종의 고용은 다른 얘기다.
_FALSE_CONTAINMENT: dict[str, tuple[str, ...]] = {
    "통상": ("통상적", "통상임금"),
    "유가": ("유가증권", "이유"),
    "건설업": ("건설업체",),
}


def _word_present_as_tag(lowered: str, word: str) -> bool:
    """word 가 태그 낱말로 실제 나타났는지 본다.

    태그 낱말은 서로 경쟁하지 않는다 — 표 안의 모든 낱말 쌍을 대조해도
    겹치는 자리가 없다(태그 부여 조사 시 확인). 그래서 영문도 낱말 경계를
    두지 않고 한국어와 똑같이 부분열로 찾는다: 경계를 두면 IMF·OECD 원문이
    흔히 쓰는 복수형("exports"·"tariffs"·"oil prices"·"exchange rates")이
    "s" 하나 때문에 걸리지 않는다. 부분열로 찾을 때 생기는 거짓 겹침은 이
    함수가 일반화해서 처리하지 않고, _FALSE_CONTAINMENT 에 이름 붙은 것만
    걸러낸다.
    """
    for unrelated in _FALSE_CONTAINMENT.get(word, ()):
        lowered = lowered.replace(unrelated, "")
    return word in lowered


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


def tags_for(sentence: str) -> list[str]:
    """인용한 문장 안의 낱말에서만 태그를 뽑는다.

    태그는 그 문장에 붙이는 이름표이지 추론이 아니다. '반도체' 가 수출을
    함의하더라도 문장에 '수출' 이 없으면 붙이지 않는다 — 지어낸 태그로 거른
    결과는 사용자가 검증할 방법이 없다.
    """
    lowered = sentence.lower()
    return [tag for tag, words in TAG_WORDS.items()
            if any(_word_present_as_tag(lowered, w.lower()) for w in words)]
