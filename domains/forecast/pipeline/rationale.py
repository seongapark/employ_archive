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
#
# "원인"·"로 인해"·"결과이다"·"결과다" 는 KLI 2026년 전망 픽스처를 실측해
# 더한 것이다(모두 줄 감김을 편 뒤에야 드러난 문장이다):
#   - "이러한 긍정적 전망의 주요 원인으로는 …" (gdp_growth)
#   - "인구효과로 인해 … 사라질 전망 …"        (emp_change)
#   - "… 견조한 고용 증가가 뒷받침된 결과이다." (emp_change)
#
# "인해"는 반드시 "로 인해"로만 둔다 — 맨 "인해"는 "확인해"·"승인해"·
# "부인해" 안에도 부분열로 들어 있어("~해 보다"의 그 "해"가 아니라 "확인·
# 승인·부인" 동사 어간에 우연히 "인해"가 걸린다), "확인해 보면 …"("만약
# 확인하면") 같은 조건절까지 인과로 오인한다 — "결과"를 "결과이다"·
# "결과다"로만 두는 것과 정확히 같은 부류의 사고다. 이 코퍼스의 "인해"
# 용례 세 곳(인구효과로 인해 ×2, 그로 인해 ×1)은 전부 "로 인해"이고,
# "로"·"으로" 없이 홀로 쓰인 "인해"는 이 코퍼스에 하나도 없다 — 그래서
# "로 인해"로 좁혀도 실측 수확은 그대로다. 줄 감김을 편 뒤 "인구효과로"와
# "인해"는 공백 하나로 이어져 "인구효과로 인해"가 되므로, 이 리터럴은
# 줄 감김 이후에도 그대로 걸린다.
#
# "결과"는 반드시 "결과이다"·"결과다"로만 둔다 — 절대 맨 낱말 "결과"로
# 줄이지 않는다. "조사 결과"·"설문 결과"·"그 결과"는 전부 "조사해 보니"라는
# 뜻이지 "그것 때문에"가 아니다. 이 코퍼스에서 맨 "결과"를 재 보면 위 두
# 어미형 말고는 아무것도 더 못 건지면서, 저 오탐 하나만 새로 들인다 —
# "것으로 나타났다"를 뺀 것과 정확히 같은 이유다. 나중에 누가 "결과이다·
# 결과다"를 맨 "결과" 하나로 "간단히" 합치고 싶어질 텐데, 그러면 안 된다.
# "요인"·"덕분"·"탓"은 이 코퍼스에서 실측했지만 아무것도 더 못 건져 넣지
# 않았다.
_CAUSE = ("배경", "때문", "기인", "반영", "영향", "힘입어",
          "원인", "로 인해", "결과이다", "결과다",
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

# 이 정규식은 _unwrap 이 편 텍스트에만 쓴다. 거기 남은 줄바꿈은 줄 감김이
# 아니라 진짜 경계(문단·항목)이므로, 문자군에서 '\n' 을 빼 두는 것이 곧
# "경계를 넘어 이어 붙이지 않는다"는 뜻이 된다. 원문에 그대로 쓰면 마침표
# 없이 끝나는 감긴 줄이 두 갈래 어디에도 안 걸려 조용히 사라진다.
#
# re.MULTILINE 이 있어야 '$' 가 글 전체의 끝뿐 아니라 줄마다의 끝에도
# 걸린다. 없으면 마침표 없이 끝나는 경계(예: 마침표를 안 쓰는 국문 보고서
# 문체의 '○' 항목)가 마지막 한 줄만 빼고 전부 조용히 사라진다 — 줄 감김을
# 펴 놓고도 같은 결함을 한 단계 위에서 되풀이하는 셈이다.
_SENTENCE = re.compile(r"[^.。\n]+[.。]|[^.。\n]+$", re.MULTILINE)

# 마침표가 숫자 사이(소수점)에 오면 문장 끝이 아니다 — "0.3%p" 를 문장
# 경계로 잘못 보면 인용문이 숫자 한가운데서 끊겨 주어를 잃는다. 분리 전에
# 원문에 나타날 일이 없는 사용자 정의 영역 문자로 잠깐 숨겨 둔다.
_DECIMAL_POINT = re.compile(r"(?<=\d)\.(?=\d)")
_DECIMAL_PLACEHOLDER = ""

# 근거로 인정할 유닛의 길이 상한. 항목 표지 경계(_unwrap)를 넣은 뒤에도
# 빈 줄도 표지도 없는 표 쪽은 여전히 통째로 한 유닛이 된다 — BOK·KDI·OECD
# 픽스처에서 723~2,750자짜리 덩어리가 실측됐다. 그 덩어리가 지금 안 뽑히는
# 건 안전해서가 아니라 인과 표지가 그 안에 하나도 없어서일 뿐이다(실측:
# 23개 픽스처 전부에서 확인). _CAUSE 를 넓힐수록 그 표지가 우연히 표 쪽
# 각주에 들어올 여지도 넓어진다 — "한 낱말 차이"의 여유가 change 1 로 한
# 번 더 줄었다.
#
# 실측 기준: 이 코퍼스 23개 픽스처를 통틀어 pick 의 지표·인과·전망 세
# 조건을 모두 만족하는 가장 긴 실제 문장은 143자(KIET cpi)였고, 조건 없이
# 살아남는 가장 짧은 표 덩어리는 723자(OECD interim 2026-03 10쪽)였다.
# 300은 그 143자의 두 배쯤이면서 723자의 절반에도 한참 못 미친다 — 두 값
# 사이에 넉넉한 틈이 있어 정확한 숫자 자체는 예민하지 않다는 것이 이
# 상한을 두는 요점이다. "표처럼 보이는가" 를 추론하지 않는다 — 자릿수
# 비율 같은 구조적 판정은 시도했다가 버렸다: 진짜 문장
# "2026년 예정된 사업 참여 인원은 약 92만 명이다." 는 숫자 비율이 20%로,
# OECD 표의 글자 사이를 띄운 헤더(자릿수 비율 10% 미만)보다도 높다 —
# 길이만 본다.
_MAX_RATIONALE_LENGTH = 300


def sentences(text: str, *, bullets: bool = False) -> list[str]:
    """본문을 문장 단위로 자른다. 빈 조각은 버린다.

    줄바꿈은 **문장 경계가 아니라 줄 감김**이다. pdfplumber 는 PDF 가
    오른쪽 여백에서 줄을 접은 자리마다 줄바꿈을 낸다 — 세 줄에 걸친 한
    문장은 앞 두 줄이 마침표 없이 끝난다. 그래서 먼저 _unwrap 으로 감긴
    줄을 공백으로 이어 붙여 편 뒤에(문단 경계와 항목 표지만 진짜 경계로
    남긴다), 그 결과를 마침표로 자른다.

    bullets 는 기본 False 로 잠가 둔다 — 이 옵션은 텍스트 레이어 없는
    PDF 를 OCR 로 읽는 KEIS 수집기만 명시적으로 켜야 한다(자세한 이유는
    _bullet_sentences 참고). 나머지 여섯 기관은 텍스트 레이어가 있는
    PDF 를 읽어 문장이 실제 마침표로 끝나므로 이 옵션을 켤 이유가 없고,
    잘못 켜졌을 때의 부작용(_BULLET_MARKERS 는 '-' 를 표지로도 보고,
    _NEGATIVE_NUMBER 의 단위 허용 목록이 모든 형태를 못 덮어 줄 감김으로
    생긴 음수를 새 문장의 시작으로 오인할 수 있다)을 감수할 이유도 없다.

    **인용문에 원문에 없던 공백이 낱말 한가운데 하나 낄 수 있다.** _unwrap
    은 감긴 줄을 공백으로 이어 붙인다(" ".join). pdfplumber 는 줄 끝
    공백을 지워 넘기므로, 그 이음매가 낱말 중간에서 줄이 감긴 자리
    ("작용하"|"고,")인지 원래부터 공백이 있던 낱말 경계("사회복지"|
    "서비스업,")인지 원문 자체에 아무 표시도 남지 않는다 — 텍스트 레이어가
    그 차이를 기록하지 않으므로 둘을 가를 방법이 없다. 그래서 고치려
    하지 않는다: 두 낱말을 하나로 조용히 붙여 마치 원래 그랬던 것처럼
    보이게 하는 쪽보다, 눈에 띄는 군더더기 공백 하나가 남는 쪽을 택한다 —
    전자는 원문에 없던 확신을 지어내고, 후자는 적어도 의심할 여지를
    남긴다. 실례는 KIET cpi 인용문의 "작용하 고,", KLI gdp_growth
    인용문의 "메가트 렌드"다 — 아래 pin 테스트가 이 인공물을 의도적으로
    못박는다.
    """
    if bullets:
        return _bullet_sentences(text)
    # 소수점 가리기는 _unwrap 뒤에 온다. '-' 가 이 경로의 표지 집합
    # (_WRAP_BOUNDARY_MARKERS)에 있던 예전에는 이 순서 자체가 결과를
    # 바꿨다 — 소수점을 먼저 가리면 "-0.3%p" 의 소수점 자리에 원문에 없는
    # 문자가 들어가 _NEGATIVE_NUMBER 판정이 어긋나, 줄 감김으로 잘린
    # 음수가 새 항목으로 오인되곤 했다. 지금은 _WRAP_BOUNDARY_MARKERS 에
    # '-' 가 없어(아래 참고) _unwrap 이 '-' 로 시작하는 줄을 표지 후보로도
    # 보지 않으므로, 이 순서를 바꿔도 결과가 달라지지 않는다(실측으로
    # 확인했다). 그래도 이 순서를 그대로 둔다 — 비용이 없고, 표지 집합에
    # '-' 가 다시 들어올 경우를 대비한 방어선이기도 하다.
    protected = _DECIMAL_POINT.sub(_DECIMAL_PLACEHOLDER, _unwrap(text))
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
    """쪽 하단 장식 줄이다 — 워터마크 URL 이거나 장식 규칙(점선 등)이다."""
    return "www." in line or _HAS_WORD_CHAR.search(line) is None


# '-' 표지 바로 뒤에 단위 붙은 숫자가 오면 불릿이 아니라 줄 감김으로 잘린
# 음수다("-0.3%p 하락"처럼). 관찰된 단위(%p·%·퍼센트·만 명·억·조)로만
# 좁힌다 — "이 숫자처럼 보이면 다 막는다"는 일반 규칙으로 넓히면 새 단위가
# 나올 때마다 이유 없이 오탐이 늘어난다. '년'은 이 목록에 없으므로
# "-2026년…"·"-또한…" 은 여전히 불릿으로 남는다.
_NEGATIVE_NUMBER = re.compile(r"^-\s*\d[\d.,]*\s*(?:%p|%|퍼센트|만\s*명|억|조)")


def _is_bullet_marker_line(line: str, *, markers: str = _BULLET_MARKERS) -> bool:
    """줄이 불릿 표지로 시작하는가.

    '-' 만 특별하다 — 이 표지는 이 보고서들의 불릿 기호이자 음수의 부호
    이기도 하다. 그 둘을 가르는 건 표지 뒤에 오는 것이다: 단위 붙은
    숫자가 곧바로 오면(_NEGATIVE_NUMBER) 새 항목이 아니라 줄 감김으로
    잘린 음수이므로 표지로 보지 않는다.

    markers 를 따로 받는다 — 표지의 뜻(항목이 여기서 시작한다)은 두 경로가
    같지만, 읽는 방식이 달라 실제로 나타나는 글자가 조금 다르다(아래
    _WRAP_BOUNDARY_MARKERS 참고). 기본값은 OCR 경로가 쓰던 그대로다.
    """
    if not line or line[0] not in markers:
        return False
    if line[0] == "-" and _NEGATIVE_NUMBER.match(line):
        return False
    return True


# 줄 감김을 펼 때 "여기서 새 항목이 시작한다"고 볼 표지 — 기본 경로
# (_unwrap) 전용이다. OCR 경로의 _BULLET_MARKERS 와 겹치지만 **일부러
# 다르다**:
#
# - **'•' 를 더한다.** 같은 보고서라도 텍스트 레이어를 그대로 읽으면
#   원래 글자인 '•' 가 나오고, 400dpi OCR 로 읽으면 그 점이 'ㅇ'·'○'·'-'
#   로 뭉개져 나온다 — 뜻은 하나(새 항목 시작)이므로 이 경로에도 더한다.
#   실측: BOK 픽스처는 '•' 를 16개 유닛으로 가르는 표지로만 쓴다. 빼면
#   BOK 가 16유닛에서 2유닛으로 무너진다(서술 항목과 그 아래 표가 다시
#   한 덩어리가 된다) — 표지가 없다고 짐작한 게 아니라 실측으로 확인했다.
#
# - **'-' 를 뺀다.** OCR 경로는 '-' 가 실제 불릿 기호이자 줄 감김에 잘린
#   음수의 부호이기도 해서 _NEGATIVE_NUMBER 로 그 둘을 가른다(위
#   _is_bullet_marker_line 참고). 그런데 이 경로(텍스트 레이어가 있는 PDF)
#   가 다루는 문서에는 애초에 '-' 를 문장·항목의 불릿 기호로 쓰는 실례가
#   없다 — 있는 건 표 안의 음수뿐이다. 실측: kdi_2026-08_summary 26행의
#   "-150 -28 3 -26 -233 91 -65", oecd_interim_2026-03_p9 의 "-0 .1"·
#   "-0 .3" 처럼 숫자 뒤에 단위가 곧바로 붙지 않는 값이 줄 앞으로 감겨
#   실제로 나온다. _NEGATIVE_NUMBER 의 단위 허용 목록(%p·%·퍼센트·
#   만\s*명·억·조)은 이런 형태를 못 덮는다 — 표지에 '-' 를 그대로 두면
#   그 값이 새 항목 시작으로 오인되어 부호가 앞 문장에서 떨어져 나간다
#   ("+23,000"으로 읽히는 값이 실은 "-23,000"). '-' 를 아예 표지에서 빼면
#   이 위험 자체가 사라진다 — _NEGATIVE_NUMBER 의 허용 목록이 무엇을
#   놓치든 상관없어진다.
#   실측: 이 코퍼스의 텍스트 레이어가 있는 세 문장(KIET cpi 143자, KLI
#   emp_change 114자, KLI gdp_growth 98자)은 '-' 를 빼도 그대로 나온다 —
#   production 이 잃는 게 없다.
#
# 그래서 두 상수는 다른 값을 갖는다: _BULLET_MARKERS 는 OCR 경로(KEIS,
# bullets=True) 전용이라 '-' 를 그대로 두고, 이 상수는 그 값에서 '-' 를
# 뺀 자리에 '•' 를 더한다. 우연히 갈라진 게 아니다 — 나란히 "정리"해
# 하나로 합치면 위 두 실측이 다시 깨진다.
_WRAP_BOUNDARY_MARKERS = "=>ㅇ□○▶•"


def _unwrap(text: str) -> str:
    """줄 감김을 편다 — 감긴 줄은 공백으로 잇고, 진짜 경계만 줄바꿈으로 남긴다.

    경계는 **두 가지뿐**이고 둘 다 이름 붙은 것이다. "이 줄은 표처럼
    보인다" 같은 짐작은 하지 않는다 — 그런 판정은 새 표 모양이 나올 때마다
    하나씩 뚫린다.

    - **빈 줄** — 문단 경계다. 이게 없으면 한 쪽 전체가 하나로 이어질 수
      있다.
    - **항목 표지로 시작하는 줄**(_WRAP_BOUNDARY_MARKERS) — 이 보고서들의
      관행상 새 항목이 시작하는 자리다. 이 규칙이 없으면 마침표를 안 쓰는
      국문 보고서 문체에서 서술 항목과 그 아래 표가 통째로 한 덩어리가
      된다. 실측: KIET 2026년 하반기 거시 전망 쪽은 빈 줄이 하나도 없고
      본문 마침표도 없어, 표지 규칙 없이 펴면 서술 네 항목과 표 전체가
      1,039자 한 덩어리가 되고 그 덩어리가 인과·전망 표지를 모두 갖춰
      gdp_growth·cpi 의 "근거"로 뽑힌다 — 숫자 한 쪽을 기관의 설명인 양
      보여주는 셈이다. 표지를 경계로 두면 같은 쪽에서 실제 서술 문장
      하나(145자)만 뽑힌다.

    표지 글자 자체는 인용문에 넣지 않는다 — 편집 기호이지 기관이 쓴
    말이 아니다. OCR 경로(_bullet_sentences)도 같은 이유로 떼어낸다.
    """
    lines: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            joined = " ".join(part for part in current if part)
            current.clear()
            if joined.strip():
                lines.append(joined)

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if _is_bullet_marker_line(line, markers=_WRAP_BOUNDARY_MARKERS):
            flush()
            line = line[1:].strip()
        if line:
            current.append(line)
    flush()
    return "\n".join(lines)


def _bullet_sentences(text: str) -> list[str]:
    """줄바꿈이 아니라 불릿 표지에서 문장을 가른다. 빈 조각은 버린다.

    텍스트 레이어 없는 PDF 를 OCR 로 읽으면 한 문장이 여러 줄에 걸쳐
    줄바꿈으로 감기고, 그 줄은 마침표로 끝나지 않는다. 줄바꿈 자체를
    경계로 쓰면 감긴 줄이 그대로 쪼개져 문장이 반 토막 난다 — KEIS
    2026년 제5호 20쪽 원문이 실례다: "…경기 개선 기대가"(주어)와 그
    다음 줄 "자리한 것으로 전망된다"(서술어)가 같은 문장인데 줄바꿈만
    보면 남남이 된다.

    줄 하나를 넷 중 하나로 본다:
    - **빈 줄** — 문단·쪽 경계다. 지금까지 모은 문장을 닫는다(flush).
    - **불릿 표지로 시작하는 줄**(_is_bullet_marker_line) — 새 문장의
      시작이다. 먼저 지금까지 모은 문장을 닫고, 표지를 뗀 나머지로
      새로 연다.
    - **쪽 하단 장식 줄**(_is_page_furniture) — 그 줄 자체만 버리고
      지나간다. *닫지 않는다.* 장식은 문단 경계가 아니라 문장 한가운데
      우연히 끼어든 쓰레기다 — "...부진 완화와" 다음 줄에 워터마크가
      끼고 그 다음 줄에 "내수 회복이..."로 문장이 이어지는 경우가
      실례다. 여기서 닫아 버리면, 장식 다음에 오는 진짜 이어지는 줄이
      이미 비어 버린 current 에 도착해 아래 넷째 갈래에도 안 걸려
      조용히 사라진다 — 문장이 반 토막 나고, 그 반 토막이 완결된
      문장처럼 보인다("...부진 완화와"만 남아 마침표 없이도 뜻이 통하는
      것처럼 읽힌다). 설계 문서 9장이 막으려는 실패 모양이 정확히 이것이다.
    - **그 밖의 줄** — 줄 감김이다. 이미 열린 문장이 있으면(current 가
      비어 있지 않으면) 공백을 끼워 이어 붙이고, 아직 표지가 안 나온
      상태(캡션·머리말)면 조용히 버린다.

    본문 전체에 불릿 표지가 하나도 없으면(예: 표 원문처럼 숫자뿐인 쪽)
    모든 줄이 이 마지막 갈래에서 버려져 빈 리스트를 준다 — pick 이 그
    쪽에서 아무 근거도 못 찾는 게 정상이라는 뜻이다.

    여러 쪽 원문을 이어 붙여 이 함수에 한 번에 넘기면, 쪽 경계에 빈 줄이
    없는 한 앞 쪽 마지막 불릿과 뒤 쪽 첫 줄이 하나로 이어질 수 있다.
    keis.collect_issue_rationales 는 쪽마다 이 함수를(정확히는 pick 을
    통해) 따로 호출해 애초에 그 위험을 없앤다 — 한 호출은 한 쪽의 텍스트만
    본다.
    """
    units: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            joined = " ".join(part for part in current if part)
            current.clear()
            if joined:
                units.append(joined)

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            flush()
        elif _is_bullet_marker_line(line):
            flush()
            current.append(line[1:].strip())
        elif _is_page_furniture(line):
            continue
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

    네 조건을 모두 만족해야 한다 — 길이, 지표 언급, 인과 표지, 전망 표지.
    하나라도 없으면 근거로 보지 않는다. 느슨하게 잡으면 엉뚱한 문장이 기관의
    근거로 남고, 그 잘못은 그럴듯해서 아무도 의심하지 않는다. 빡빡한 쪽으로
    틀린다.

    길이부터 본다 — _MAX_RATIONALE_LENGTH 보다 길면 나머지 세 조건은 볼
    것도 없이 문장이 아니다(위 상수 옆 주석에 실측 근거를 적어 뒀다). 그
    유닛은 건너뛸 뿐 순회를 멈추지는 않는다 — 같은 문서 뒤쪽에 짧고 진짜인
    문장이 남아 있을 수 있다.

    bullets 는 그대로 sentences() 에 넘길 뿐이다 — 문장을 무엇으로 볼지는
    sentences() 하나가 정하고, 여기 네 조건(길이·지표·인과·전망)은 그 문장이
    무엇이든 똑같이 적용된다.
    """
    for sentence in sentences(text, bullets=bullets):
        if len(sentence) > _MAX_RATIONALE_LENGTH:
            continue
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
