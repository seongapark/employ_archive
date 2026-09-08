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
import unicodedata
from typing import Sequence

from .rationale import _DUPLICATED_HANGUL, _MAX_RATIONALE_LENGTH

_WHITESPACE = re.compile(r"\s+")

# 빈 줄 — 개행 두 개 사이에 공백만 있는 자리. pdf.text_with_paragraph_breaks
# 가 문단 나눔에 넣는 표지이고, 감김(개행 하나)과 구별된다.
_BLANK_LINE = re.compile(r"\n[^\S\n]*\n")

# 마침표 대조만으로는 "문장 중간에서 시작하는 조각"을 못 잡는다 — 부분열
# 검사는 위치를 가리지 않기 때문이다. 그래서 매치 시작 자리가 실제
# 문장·항목의 머리인지 원문 좌표로 되짚어 확인한다(_starts_at_a_boundary).
#
# 표지를 목록으로 두지 않는다. 목록은 유한한데 기관마다 새 기호가 나와
# 그때마다 그 항목의 근거가 통째로 거절됐다(실측: BOK 의 ▢ U+25A2·▪ U+25AA,
# 그리고 글꼴이 매핑 못 한 사설영역 글자들). 대신 "줄머리에서 글자가
# 시작하기 전까지의 기호 무리" 로 본다 — 무엇이 오든 걸린다.

# 문장 종결부호 — 이 뒤에서 새 문장이 시작한다. 국문 보고서 불릿은 종종
# 마침표 없이 끝나므로(예: "…지속될 것으로 예상") 끝은 검사하지 않는다 —
# 시작만 검사한다. 잘린 머리(주어 없는 인용)가 이 프로젝트가 실제로 본
# 실패 모양이다. 종결부호는 줄 첫머리가 아니라 어디에 있어도 문장을 끝낸다.
#
# 다만 '.' 는 문장 종결부호이자 소수점이다. 숫자가 마침표에 딱 붙어
# 있을 때만 소수점으로 보는 좁은 판정으로는 부족하다 — pdfplumber 가
# 남긴 원문은 소수점 한가운데로 줄이 감길 수 있다.
# 그래서 앞뒤 모두 공백을 건너뛰고 판정한다(_looks_like_a_decimal_point).
_SENTENCE_TERMINATORS = frozenset(".。")

# 글자 — 한글·영숫자. 이것이 나오기 전까지는 아직 항목 내용이 아니다.
_WORDLIKE = re.compile(r"[0-9A-Za-z가-힣]")

# 번호 붙은 항목("1)"). 숫자를 쓰므로 위 기호 무리 규칙에 안 걸려 따로 둔다.
# '.' 붙은 번호("3.")는 넣지 않는다 — 그 마침표는 _SENTENCE_TERMINATORS 와
# _looks_like_a_decimal_point 가 이미 소수점과 가려 가며 다룬다.
_NUMBERED_ITEM = re.compile(r"\s*\d+\)\s*")

# 후보가 표지를 스스로 물고 오는 경우("ㅇ 소비가…")를 위해, pos 자리에서
# 시작하는 기호 무리를 본다.
_LEADING_MARKERS = re.compile(r"[^\s0-9A-Za-z가-힣]+\s*")


class Rejected(Exception):
    """후보를 저장하지 않는다. reason 은 로그에 그대로 남긴다."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _is_private_use(ch: str) -> bool:
    """사설영역(U+E000–U+F8FF) 글자인가.

    글꼴이 유니코드로 안 매핑해 남은 자국이라 뜻이 없다. 실측(BOK 2026년
    8월호): U+E0F8 이 30줄, U+F000 이 25줄. 모델은 이런 글자를 옮겨 적지
    않으므로 원문에만 남아 대조를 깨뜨린다 — 양쪽에서 지우고 본다.
    """
    return "" <= ch <= ""


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
        if ch.isspace() or _is_private_use(ch):
            continue
        # 글자 단위로 NFKC 를 건다 — 문자열 통째로 걸면 글자 수가 바뀌어
        # index_map 이 원문 좌표를 잃는다. 이걸로 전각·호환 문자는 잡히지만
        # 자모가 풀린 한글(ㄱ+ㅏ)까지 모으지는 못한다. 이 코퍼스에서는 늘
        # 모아진 채로 나와 문제가 안 됐다 — 그렇지 않은 문서를 만나면
        # 여기가 아니라 추출 단계에서 다뤄야 한다.
        for out in unicodedata.normalize("NFKC", ch):
            chars.append(out)
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


def _is_marker_run(prefix: str) -> bool:
    """줄머리부터 여기까지가 '글자 없는 기호 무리' 인가.

    비어 있으면 아니다 — 줄머리라는 것만으로는 항목 시작이 아니고, 감긴
    줄도 줄머리이기 때문이다.

    마침표류는 기호로 세지 않는다. pdfplumber 가 소수점 한가운데로 줄을
    감으면 줄머리가 "." 로 시작한다("성장률은 3
. 5% 상승할 전망") —
    그것을 표지로 보면 "5% 상승할 전망" 이라는 머리 잘린 조각이 통과한다.
    마침표는 위 종결부호 판정이 이미 소수점과 가려 가며 다루므로, 여기까지
    내려왔다는 것은 그 마침표가 소수점이었다는 뜻이다.
    """
    symbols = [ch for ch in prefix
               if not ch.isspace() and ch not in _SENTENCE_TERMINATORS]
    return bool(symbols) and not _WORDLIKE.search(prefix)


def _marker_allows(prefix: str, following: str) -> bool:
    """기호 무리 뒤가 항목 내용인가, 아니면 그 기호가 숫자의 일부인가.

    실측으로 막아야 했던 것은 둘뿐이다: 줄머리 음수("-0.3%p 낮아질")와
    줄머리 등호("=2026년"). 둘 다 기호가 숫자에 **딱 붙어** 있다. 진짜
    글머리표는 뒤에 공백이 오거나("▢ 2026년 성장률은"), 공백 없이 붙더라도
    그 뒤가 글자다("▪견조한"). 그래서 "공백 없이 붙은 채 숫자가 뒤따르면
    표지가 아니다" 하나로 가른다 — 기호 목록을 들지 않고도 갈린다.
    """
    if prefix and prefix[-1].isspace():
        return True
    return not following[:1].isdigit()


def _starts_at_a_boundary(source: str, pos: int) -> bool:
    """source[pos] 가 문장·항목이 시작하는 자리인가.

    - **빈 줄**이 앞에 있으면 문단 나눔이다(pdf.text_with_paragraph_breaks 가
      세로 간격을 보고 넣는다). 표지도 마침표도 없이 간격으로만 갈리는
      항목이 있어서(KDI 요약 쪽) 이것이 없으면 그 근거가 통째로 빈 칸이 된다.
    - **문장 종결부호**가 앞에 있으면(공백은 건너뛴다) 줄 어디서든 인정한다.
      단 그 마침표가 소수점이면 아니다.
    - **기호 무리**가 그 줄의 첫 내용이면 글머리표로 본다. 줄 안 아무 데서나
      인정하면 "가격(예: 100원) 상승이" 의 ')' 뒤부터 시작하는 조각이
      통과한다 — 그래서 줄머리로 좁힌다.
    - **후보가 표지를 스스로 포함하는 경우**도 인정한다("ㅇ 소비가…").
      이때 pos 앞은 앞 줄의 마지막 글자인데, 국문 불릿은 마침표 없이
      끝나는 게 보통이라 앞을 보는 판정으로는 표지를 못 찾는다.
    """
    i = pos - 1
    newlines = 0
    while i >= 0 and source[i].isspace():
        if source[i] == "\n":
            newlines += 1
        i -= 1
    if i < 0:
        return True
    if newlines >= 2:
        return True
    if source[i] in _SENTENCE_TERMINATORS and not _looks_like_a_decimal_point(source, i):
        return True

    line_start = source.rfind("\n", 0, pos) + 1
    prefix = source[line_start:pos]
    if _NUMBERED_ITEM.fullmatch(prefix):
        return True
    if _is_marker_run(prefix) and _marker_allows(prefix, source[pos:]):
        return True
    if not prefix.strip():
        own = _LEADING_MARKERS.match(source, pos)
        if own and _marker_allows(own.group(), source[own.end():]):
            return True
    return False


def verify_in_pages(candidate: str, pages: Sequence[str],
                    hinted_page: int | None = None) -> tuple[str, int]:
    """후보가 실제로 실린 쪽을 찾아 (문장, 1부터 세는 쪽번호) 를 준다.

    모델이 댄 쪽번호를 믿지 않는다 — 맞는 문장을 찾고도 쪽을 틀리게 대고,
    같은 회차를 다시 돌리면 다른 번호가 나온다(실측: BOK 2026년 8월호에서
    cpi 를 8쪽이라 했으나 11쪽, emp_change 를 23쪽이라 했으나 39쪽. KLI
    2026-01-02 은 24와 23 사이를 오갔다). 그 흔들림 때문에 원문에 실재하는
    문장이 "원문에 없다"로 버려졌다.

    보증은 약해지지 않는다. 여전히 문장이 원문에 실재해야 하고 항목 시작
    자리여야 한다 — 바뀐 것은 **어느 쪽인지를 모델에게 묻지 않는다**는 것
    뿐이고, 그 결과 저장되는 인용 쪽번호는 오히려 정확해진다.

    쪽 차례는 힌트부터 본다. 같은 문장이 여러 쪽에 실렸을 때(BOK 은 개관과
    상세장이 같은 문장을 쓴다) 모델이 본 쪽을 그대로 두는 편이 인용으로
    자연스럽고, 실행마다 쪽번호가 달라지지도 않는다.
    """
    order = []
    if hinted_page is not None and 0 < hinted_page <= len(pages):
        order.append(hinted_page)
    order += [n for n in range(1, len(pages) + 1) if n not in order]

    other: Rejected | None = None
    for page_no in order:
        try:
            return verify(candidate, pages[page_no - 1]), page_no
        except Rejected as exc:
            # "원문에 없다" 는 이 쪽에 없다는 뜻일 뿐이다 — 모든 쪽을 다 본
            # 뒤에야 결론이 된다. 다른 사유는 그 쪽에 문장이 실재한다는
            # 뜻이므로 그대로 전한다(사람이 원인을 헷갈리지 않게).
            if exc.reason != "원문에 없다" and other is None:
                other = exc
    raise other or Rejected("원문에 없다")


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
    span = source_page_text[index_map[pos]:index_map[pos + len(norm_candidate) - 1] + 1]
    if _BLANK_LINE.search(span):
        # 지어낸 문장은 아니지만 기관이 한 문장으로 말한 것도 아니다.
        # 공백을 지우고 대조하므로 빈 줄을 건너뛴 후보도 부분열로 통과한다 —
        # 시작 자리만 보고 끝을 안 보기 때문이다. 실측: KDI 2025-08 4쪽에서
        # 물가 항목과 고용 항목이 한 근거로 붙어 저장됐다.
        raise Rejected("여러 항목을 이어 붙였다(중간에 문단 나눔이 있다)")
    return candidate
