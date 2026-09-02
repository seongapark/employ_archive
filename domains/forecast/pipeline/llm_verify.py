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

from .rationale import (_BULLET_MARKERS, _DUPLICATED_HANGUL,
                         _MAX_RATIONALE_LENGTH, _WRAP_BOUNDARY_MARKERS)

_WHITESPACE = re.compile(r"\s+")

# 마침표 대조만으로는 "문장 중간에서 시작하는 조각"을 못 잡는다 — 부분열
# 검사는 위치를 가리지 않기 때문이다. 그래서 매치 시작 자리가 실제
# 문장·항목의 머리인지 원문 좌표로 되짚어 확인한다(_starts_at_a_boundary).
#
# 표지 집합은 rationale.py 가 이미 실측으로 확정해 둔 두 개
# (_BULLET_MARKERS · _WRAP_BOUNDARY_MARKERS)의 합집합을 그대로 쓴다 — 이
# 모듈은 후보가 어느 수집 경로(OCR 인 KEIS 대 텍스트 레이어가 있는 나머지
# 여섯 기관)에서 왔는지 모르므로 두 집합을 가리지 않고 합쳐 받는다.
#
# ')' 는 여기 넣지 않는다 — rationale.py 어디에도 ')' 단독을 항목 표지로
# 쓴 적이 없고, 이 코퍼스에서 ')' 는 "1)"처럼 번호 뒤에 올 때만 항목의
# 일부다(괄호 안 예시 "가격(예: 100원)"처럼 그냥 닫는 괄호로 훨씬 자주
# 쓰인다). 번호 붙은 항목은 아래 _ITEM_PREFIX 로 따로 잡는다.
_START_BOUNDARY_MARKERS = frozenset(_BULLET_MARKERS) | frozenset(_WRAP_BOUNDARY_MARKERS)

# 문장 종결부호 — 이 뒤에서 새 문장이 시작한다. 국문 보고서 불릿은 종종
# 마침표 없이 끝나므로(예: "…지속될 것으로 예상") 끝은 검사하지 않는다 —
# 시작만 검사한다. 잘린 머리(주어 없는 인용)가 이 프로젝트가 실제로 본
# 실패 모양이다. 종결부호는 줄 첫머리가 아니라 어디에 있어도 문장을 끝낸다
# — 그래서 아래 표지·번호 판정과 달리 줄 시작 제약을 받지 않는다.
#
# 다만 '.' 는 문장 종결부호이자 소수점이다. 숫자가 마침표에 딱 붙어
# 있을 때만 소수점으로 보는 좁은 판정으로는 부족하다 — pdfplumber 가
# 남긴 원문은 소수점 한가운데로 줄이 감겨("성장률은 3.\n5%…") 마침표와
# 숫자 사이에 개행이 낄 수도, 반대쪽으로 감겨("성장률은 3\n.5%…") 숫자
# 쪽에 개행이 낄 수도 있다. 이 모듈은 원문을 고치지 않고 pdfplumber 가
# 남긴 그대로를 보므로, 앞뒤 모두 공백(개행 포함)을 건너뛰고 그다음
# 문자가 숫자인지 보는 별도 판정(_looks_like_a_decimal_point)을 따로
# 둔다 — 이 모듈이 애초에 공백을 무시하는 이유(엉뚱한 공백)와 같은
# 현상이다.
_SENTENCE_TERMINATORS = frozenset(".。")

# 표지 문자는 줄의 첫 내용일 때만 인정한다 — 표지 문자가 줄 어디에 있어도
# 인정하면 "-" 는 음수 부호와, ")" 는 여는 괄호를 닫는 자리와 구별이 안
# 된다(실측: "성장률은 -0.3%p 감소했다고 밝혔다" 에서 "-" 뒤부터, "가격
# (예: 100원) 상승이 예상된다" 에서 ")" 뒤부터 시작하는 조각이 그대로
# 통과해 버렸다 — 둘 다 주어 잘린 조각이다). 그래서 표지는 "그 줄의 첫
# 내용"일 때만 인정한다: 줄 시작(직전 개행 또는 원문 시작)부터 매치
# 자리까지가 공백과 항목 표지 하나(또는 번호 붙은 괄호 표지)뿐이어야 한다.
#
# 줄 첫머리로 좁힌 것만으로는 부족하다 — pdfplumber 는 배치 위치로 줄을
# 감으므로, 음수로 시작하는 줄("…늘어\n-0.3%p 낮아질…")도 마이너스 부호로
# 시작하는 줄만큼 있을 법하다. 실측: "-0.3%p" 처럼 표지 문자 바로 뒤에
# 숫자가 붙으면 통과해 버렸다(줄 첫머리라는 조건만 봤을 뿐 표지 자체가
# 진짜 불릿인지는 안 봤다). '=' 도 _WRAP_BOUNDARY_MARKERS 를 통해 같은
# 모양이다("=2026년…"). 그래서 "실제 불릿은 항상 뒤에 공백이 오고,
# '-0.3' 은 절대 그렇지 않다"는 사실을 그대로 규칙으로 쓴다 — 표지 문자
# 하나만 있는 갈래는 뒤에 공백이 하나 이상 와야 인정한다. 번호 붙은
# 괄호 표지("1)")는 그대로 둔다 — 그쪽은 표지 자체가 숫자+')' 형태라
# 애초에 음수·괄호 닫기와 헷갈릴 자리가 아니다.
#
# 번호 표지는 ')' 붙은 것만 여기서 잡는다("1)"). '.' 붙은 번호("3.")는
# 넣지 않는다 — 그 마침표는 위 _SENTENCE_TERMINATORS 와
# _looks_like_a_decimal_point 가 이미 소수점과 가려 가며 다룬다. 여기 또
# 넣으면 "3.5" 같은 소수점을 문장 종결부호 쪽에서는 막아 놓고 항목 표지
# 쪽에서 도로 통과시키는 두 규칙 불일치가 생긴다.
_marker_class = "".join(re.escape(ch) for ch in sorted(_START_BOUNDARY_MARKERS))
_ITEM_PREFIX = re.compile(rf"\s*(?:[{_marker_class}]\s+|\d+\)\s*)")


class Rejected(Exception):
    """후보를 저장하지 않는다. reason 은 로그에 그대로 남긴다."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _normalize_with_index(s: str) -> tuple[str, list[int]]:
    """공백을 지우면서, 남은 문자 각각이 원문에서 몇 번째 자리였는지 기록한다.

    normalize() 는 이 함수의 결과 문자열만 쓴다 — 두 구현을 따로 두면
    "공백을 지운다"는 규칙이 갈라질 수 있어, 하나로 합쳐 둔다. index_map 은
    verify() 가 부분열이 발견된 정규화 좌표를 원문 좌표로 되짚어 시작 경계를
    검사할 때만 쓴다.
    """
    chars: list[str] = []
    index_map: list[int] = []
    for i, ch in enumerate(s):
        if not ch.isspace():
            chars.append(ch)
            index_map.append(i)
    return "".join(chars), index_map


def normalize(s: str) -> str:
    """공백을 전부 지운다. 줄바꿈도 공백이라 함께 사라진다."""
    return _normalize_with_index(s)[0]


def _looks_like_a_decimal_point(source: str, i: int) -> bool:
    """source[i] (마침표) 가 소수점인가 — 줄 감김으로 앞뒤 어느 쪽이 떨어져
    있어도 본다.

    앞뒤 모두 공백(개행 포함)을 건너뛰고 처음 나오는 문자가 숫자인지만
    본다. pdfplumber 는 페이지 여백 위치를 기준으로 줄을 감으므로, 숫자
    뒤에서 마침표가 다음 줄로 넘어가는 경우("3.\n5%")와 마침표 뒤에서
    숫자가 다음 줄로 넘어가는 경우("3\n.5%") 둘 다 물리적으로 똑같이
    있을 법하다 — 한쪽만 공백을 건너뛰고 볼 이유가 없다.

    앞쪽에 공백을 건너뛰는 것이 "…이다. 5%" 처럼 실제로 끝난 문장 뒤에
    오는 숫자를 소수점으로 오인하게 만들지는 않는다 — 그 마침표 앞은
    공백을 건너뛰어도 "다"(숫자 아님)이므로 여전히 걸리지 않는다.

    앞뒤가 모두 숫자면 문장 경계 취급을 안 하므로, "3. 5% 성장률의
    배경"처럼 번호 항목의 내용이 우연히 숫자로 시작하면 항목 경계를
    놓친다 — 일부러 받아들이는 손해다. 근거를 하나 놓쳐 빈 칸으로 남는
    것이, 두 자리를 이어 붙여 기관이 하지 않은 문장을 내보내는 것보다
    낫다.
    """
    if source[i] != ".":
        return False
    k = i - 1
    while k >= 0 and source[k].isspace():
        k -= 1
    j = i + 1
    while j < len(source) and source[j].isspace():
        j += 1
    return k >= 0 and source[k].isdigit() and j < len(source) and source[j].isdigit()


def _starts_at_a_boundary(source: str, pos: int) -> bool:
    """source[pos] 가 문장·항목이 시작하는 자리인가.

    세 판정은 성격이 다르다.

    - **문장 종결부호**는 pos 바로 앞(공백은 건너뛴다)에 있으면 줄 어디서든
      인정한다 — 마침표는 그 자리에 있는 것만으로 문장이 끝났다는 뜻이라
      줄 시작일 필요가 없다. 단, 그 마침표가 소수점이면 인정하지 않는다
      (_looks_like_a_decimal_point).
    - **항목 표지·번호가 pos 앞에 있는 경우**는 그 줄의 첫 내용일 때만
      인정한다. 줄 안 아무 데서나 인정하면 "-" 는 음수 부호와, ")" 는
      여는 괄호를 닫는 자리와 구별이 안 된다(_ITEM_PREFIX 옆 주석의 실측
      참고).
    - **항목 표지·번호가 pos 자체에서 시작하는 경우**도 인정한다 — LLM 이
      표지까지 포함해 후보를 돌려줄 수 있다("ㅇ 소비가…"). 이때는 pos
      바로 앞을 봐도 소용없다: 그 자리는 앞 줄의 마지막 글자인데, 국문
      보고서 불릿은 마침표 없이 끝나는 게 보통이라(_SENTENCE_TERMINATORS
      옆 주석 참고) 앞을 보는 판정으로는 표지 자체를 절대 못 찾는다.
      그래서 pos 앞이 아니라 pos 부터 뒤로 _ITEM_PREFIX 가 매치하는지
      보되, 그 줄에서 pos 앞쪽에 표지 말고 다른 내용이 없을 때만
      허용한다(줄 중간에 우연히 표지 모양이 나온 자리를 항목 시작으로
      오인하지 않기 위해서다).

    이 목록 밖의 "문장처럼 보인다"는 어떤 짐작도 하지 않는다 — 표지
    집합을 실측 없이 넓히면 다음에 그 짐작이 하나씩 틀린다(_BULLET_MARKERS
    옆 주석과 같은 이유).
    """
    i = pos - 1
    while i >= 0 and source[i].isspace():
        i -= 1
    if i < 0:
        return True
    if source[i] in _SENTENCE_TERMINATORS and not _looks_like_a_decimal_point(source, i):
        return True
    line_start = source.rfind("\n", 0, pos) + 1
    prefix = source[line_start:pos]
    if _ITEM_PREFIX.fullmatch(prefix) is not None:
        return True
    return not prefix.strip() and _ITEM_PREFIX.match(source, pos) is not None


def verify(candidate: str, source_page_text: str) -> str:
    """통과하면 candidate 를 그대로 돌려준다. 아니면 Rejected."""
    if not candidate.strip():
        raise Rejected("빈 문장이다")
    if len(candidate) > _MAX_RATIONALE_LENGTH:
        raise Rejected(f"{_MAX_RATIONALE_LENGTH}자보다 길다({len(candidate)}자)")
    if _DUPLICATED_HANGUL.search(candidate):
        raise Rejected("굵은 글씨 반복 렌더링 흔적이 들어 있다")
    norm_candidate = normalize(candidate)
    norm_source, index_map = _normalize_with_index(source_page_text)
    pos = norm_source.find(norm_candidate)
    if pos == -1:
        raise Rejected("원문에 없다")
    if not _starts_at_a_boundary(source_page_text, index_map[pos]):
        raise Rejected("문장·항목이 시작하는 자리가 아닌 곳에서 시작한다")
    return candidate
