"""국내기관 전망보고서 PDF에서 요약표를 읽는다.

기관마다 표의 열 구성이 다르고 같은 기관도 회차마다 바뀐다(한국은행 7열,
KDI 6열, KDI 수정호는 수정폭 2열이 더 붙어 7열). 열 위치를 고정하면 회차가
바뀔 때 조용히 어긋나므로, 헤더의 연도 토큰과 기간 토큰만으로 열을 복원한다.
"""
from __future__ import annotations

import io
import re
from typing import Collection, Iterable, Mapping

# 표 헤더에서 기간 한 칸을 뜻하는 낱말 → 내부 코드
PERIOD_CODES = {
    "연간": "annual",
    "상반": "h1", "상반기": "h1",
    "하반": "h2", "하반기": "h2",
    "수정폭": "revision",
}

_YEAR = re.compile(r"((?:19|20)\d{2})[pe]?\)?$")
_NUMBER = re.compile(r"-?\.*[\d,]+(?:\.\d+)?$")
_PERIOD_WORD = re.compile(r"(연간|상반|하반|수정폭)")
_BRACKETED = re.compile(r"\[[^\]]*\]|<[^>]*>")
_FOOTNOTE = re.compile(r"\d+\)")
_UNIT_PAREN = re.compile(r"\((?:%|%p|만명|억달러|달러/배럴)\)")


def is_bold_overprint(line: str) -> bool:
    """줄의 모든 낱말이 글자마다 3번씩 찍혔는지 본다(공백은 겹치지 않는다)."""
    tokens = line.split()
    if not tokens:
        return False
    return all(
        len(token) % 3 == 0
        and all(token[i] == token[i + 1] == token[i + 2] for i in range(0, len(token), 3))
        for token in tokens
    )


def unbold_line(line: str) -> str:
    """볼드 오버프린트로 3번씩 찍힌 줄을 원래대로 되돌린다.

    세 글자마다 하나만 남기므로 1,000 처럼 같은 숫자가 이어져도 잃지 않는다.
    (연달아 3개를 하나로 접는 방식은 1,000 을 1,0 으로 망가뜨린다.)
    3중 인쇄가 아닌 줄은 손대지 않는다.
    """
    if not is_bold_overprint(line):
        return line
    return " ".join(token[::3] for token in line.split())


# 문단 나눔 판정 — 임계는 감김 간격의 _BREAK_FACTOR 배, 그 임계가 실제로
# 골 한가운데에 있는지는 _VALLEY_FACTOR 로 확인한다(둘 다 실측으로 정했다).
NUL = chr(0)
_BREAK_FACTOR = 1.5
_VALLEY_FACTOR = 1.5


def _wrap_gap(gaps: list[float]) -> float:
    """이 쪽에서 '한 문장이 다음 줄로 넘어간' 간격을 고른다.

    최소값을 쓰면 위첨자나 겹친 줄 하나가 임계를 바닥으로 끌어내려, 감긴
    줄마다 빈 줄이 들어간다. 그래서 아래쪽 사분위를 쓴다 — 이상치 몇 개는
    그 아래에 묻히고, 감김이 드문 쪽(대부분이 한 줄짜리 항목인 쪽)에서는
    거꾸로 임계가 높아져 아무것도 안 넣는 쪽으로 기운다. 어느 쪽으로
    틀리든 손해가 '근거를 못 찾는다' 쪽이어야 한다.
    """
    return sorted(gaps)[len(gaps) // 4]


def _despace(text: str) -> str:
    """U+0000 을 공백으로 바꾼다.

    실측: KDI 2024 상반기 PDF 는 공백 자리에 U+0000 을 내놓는다(그 회차 본문에
    67개, 같이 확인한 다른 문서 세 개에는 0개) — 그 폰트의 공백 글리프가
    유니코드로 안 매핑된 것이다. 지우면 "경제는높은" 처럼 낱말이 붙어 없는
    낱말이 만들어지므로 공백으로 바꾼다.

    그냥 두면 두 군데가 함께 어긋난다. llm_verify 가 경계를 뒤로 훑을 때
    NUL 은 파이썬에서 공백이 아니라 거기서 멈춰 문단 나눔에 닿지 못하고,
    모델이 그 자리를 보통 공백으로 옮겨 적으면 대조에서 "원문에 없다"가 된다.
    NUL 만 다룬다 — 실측에서 나온 제어문자가 이것뿐이라, 더 넓히면 안 본
    문자에 대한 짐작이 된다.
    """
    return text.replace(NUL, " ")


def text_with_paragraph_breaks(lines) -> str:
    """줄과 좌표를 받아, 문단이 갈리는 자리에 빈 줄을 넣은 원문을 만든다.

    감김(한 문장이 다음 줄로 넘어간 것)과 새 항목은 세로 간격이 다르다.
    간격이 갈리는 쪽에서만 빈 줄을 넣고, 안 갈리는 쪽은 그대로 둔다 —
    문단 나눔이 아닌 자리에 빈 줄을 넣으면 llm_verify 가 그 자리를 항목
    시작으로 인정해, 주어가 잘린 조각이 근거로 저장된다. 못 넣어서
    근거가 빈 칸으로 남는 것보다 그쪽이 나쁘다.
    """
    texts = [_despace(line["text"]) for line in lines]
    if len(lines) < 2:
        return "\n".join(texts)
    gaps = [b["top"] - a["bottom"] for a, b in zip(lines, lines[1:])]
    threshold = _wrap_gap(gaps) * _BREAK_FACTOR
    below = [gap for gap in gaps if gap <= threshold]
    above = [gap for gap in gaps if gap > threshold]
    if not below or not above or min(above) < max(below) * _VALLEY_FACTOR:
        return "\n".join(texts)
    out = [texts[0]]
    for gap, text in zip(gaps, texts[1:]):
        if gap > threshold:
            out.append("")
        out.append(text)
    return "\n".join(out)


def page_texts(data: bytes) -> list[str]:
    import pdfplumber  # 무거운 의존성이라 실제로 PDF를 읽을 때만 불러온다

    with pdfplumber.open(io.BytesIO(data)) as doc:
        return [page.extract_text() or "" for page in doc.pages]


def page_texts_with_breaks(data: bytes) -> list[str]:
    """page_texts 와 같되, 문단이 갈리는 자리에 빈 줄을 넣는다.

    근거 선별(llm_select)만 쓴다 — 매일 도는 수집기 여섯 개는 page_texts 를
    그대로 쓴다. 빈 줄은 llm_verify 가 "여기서 항목이 시작한다"고 인정하는
    표지이므로, 이 함수를 쓰는 쪽만 그 판정을 받게 둔다.

    빈 줄을 안 넣는 쪽도 extract_text() 가 아니라 extract_text_lines() 를
    이어 붙인다 — 한 쪽 안에서 두 가지 추출을 섞으면 넣고 안 넣고에 따라
    원문이 달라질 수 있다. 실측으로 둘은 같았다(KDI·KLI·OECD Interim
    59쪽 전부 바이트까지 일치). 같으니까 하나로 고른 것이지, 달라도
    괜찮아서가 아니다.
    """
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as doc:
        return [text_with_paragraph_breaks(page.extract_text_lines())
                for page in doc.pages]


def find_summary_table(
    pages: Iterable[str], labels: Mapping[str, str], required: Collection[str]
) -> tuple[int, str] | None:
    """required 지표가 모두 나오는 첫 표 페이지를 (1부터 세는 쪽번호, 원문) 으로 준다.

    제목 문자열로 페이지를 찾으면 보고서 편집이 바뀔 때마다 깨진다. 대신 실제로
    표를 읽어 보고 필요한 지표가 다 나오는 페이지를 고른다. 앞쪽에 실린 지표가
    일부만 담긴 작은 표들은 자연히 걸러진다.
    """
    for index, text in enumerate(pages, start=1):
        try:
            values = parse_summary_table(text, labels)
        except ValueError:
            continue
        if set(required) <= {indicator for indicator, _, _ in values}:
            return index, text
    return None


def _numbers(line: str) -> list[float]:
    cleaned = _BRACKETED.sub(" ", line)
    out = []
    for token in cleaned.split():
        if _NUMBER.fullmatch(token):
            out.append(float(token.lstrip(".").replace(",", "")))
    return out


def _label(line: str) -> str:
    cleaned = _BRACKETED.sub(" ", line)
    words = []
    for token in cleaned.split():
        if _NUMBER.fullmatch(token):
            break
        words.append(token)
    label = " ".join(words)
    label = _UNIT_PAREN.sub("", label)
    label = _FOOTNOTE.sub("", label)
    return re.sub(r"[\s•·⋅]", "", label)


def _header_tokens(lines: list[str]) -> tuple[list[int], list[str]]:
    years: list[int] = []
    periods: list[str] = []
    for line in lines:
        for token in line.split():
            year = _YEAR.fullmatch(token)
            if year:
                years.append(int(year.group(1)))
                continue
            word = re.sub(r"[^가-힣]", "", token)
            word = re.sub(r"(p|e)$", "", word)
            if word in PERIOD_CODES:
                periods.append(PERIOD_CODES[word])
    return years, periods


def _columns(years: list[int], periods: list[str]) -> list[tuple[int, str]]:
    """기간 토큰을 연도 블록으로 묶어 열 순서대로 (연도, 기간) 을 만든다.

    상반기와 수정폭은 새 블록을 열고, 연간은 현재 블록이 이미 연간을 가졌으면
    새 블록을 열며, 하반기는 현재 블록에 붙는다. 블록 수와 연도 수가 어긋나면
    서식이 바뀐 것이므로 조용히 넘기지 않고 실패시킨다.
    """
    blocks: list[list[str]] = []
    current: list[str] | None = None
    for period in periods:
        opens_block = (
            period in ("h1", "revision")
            or (period == "annual"
                and (current is None or "annual" in current or "revision" in current))
        )
        if opens_block:
            current = [period]
            blocks.append(current)
        elif current is None:
            raise ValueError(f"표 헤더 불일치: 기간 {periods} 이 연도로 시작하지 않는다")
        else:
            current.append(period)
    if len(blocks) != len(years):
        raise ValueError(f"표 헤더 불일치: 연도 {years} vs 기간 블록 {blocks}")
    return [(year, period) for year, block in zip(years, blocks) for period in block]


def _header_lines(lines: list[str]) -> list[str]:
    marks = [
        i for i, line in enumerate(lines[:15])
        if _PERIOD_WORD.search(line) and len(_numbers(line)) < 3
    ]
    if not marks:
        raise ValueError("표에서 기간 헤더(연간·상반기·하반기)를 찾지 못했다")
    # 연도 줄은 기간 줄 바로 위에 있고, KDI 수정호처럼 두 줄로 쪼개지기도 한다
    return lines[max(0, min(marks) - 3):max(marks) + 1]


def parse_summary_table(
    text: str, labels: Mapping[str, str]
) -> dict[tuple[str, int, str], float]:
    """요약표 페이지 원문에서 {(지표, 연도, 기간): 값} 을 뽑는다.

    labels 는 표의 행 이름(공백·단위·각주를 뗀 형태) → 내부 지표코드.
    """
    # 보고서가 볼드로 인쇄한 줄은 글자가 3번씩 찍혀 나온다 — 라벨도 숫자도 못 읽으므로 먼저 되돌린다
    lines = [unbold_line(line) for line in text.split("\n") if line.strip()]
    years, periods = _header_tokens(_header_lines(lines))
    columns = _columns(years, periods)

    values: dict[tuple[str, int, str], float] = {}
    for line in lines:
        numbers = _numbers(line)
        if len(numbers) != len(columns):
            continue
        indicator = labels.get(_label(line))
        if indicator is None:
            continue
        for (year, period), value in zip(columns, numbers):
            if period == "revision":
                continue
            values[(indicator, year, period)] = value
    return values
