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
    # 음수·0 은 줄 간격이 아니다 — 줄이 겹쳐 나온 것이다(BOK 은 한 쪽에
    # 네 개씩 나온다). 그대로 두면 사분위를 끌어내려 임계가 진짜 감김보다
    # 낮아지고, 감긴 줄마다 문단 나눔이 들어가 문장 한가운데가 끊긴다
    # (실측: 2026년 8월호 28쪽에서 한 문장이 둘로 갈렸다).
    spacing = [gap for gap in gaps if gap > 0]
    if not spacing:
        # 이 쪽의 줄 배치를 못 믿는다 — 아무것도 넣지 않는 쪽으로 기운다.
        return float("inf")
    return sorted(spacing)[len(spacing) // 4]


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


def page_words(data: bytes, page_no: int) -> list[dict]:
    """한 쪽의 낱말을 좌표와 함께 준다(1부터 세는 쪽번호).

    기재부 요약표는 연도 머리(`'26년`)가 하위 열 두 개(`1/4`·`연간e`) 위에
    걸쳐 있는데, extract_text() 는 그 걸침을 버려서 어느 숫자가 어느 해인지
    알 수 없게 된다. 열 복원에는 좌표가 있어야 한다.

    쪽 하나만 연다 — 57쪽짜리 보고서에서 낱말을 전부 들고 있을 이유가 없다.
    """
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as doc:
        return doc.pages[page_no - 1].extract_words()


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
        fallback = _document_split_x(doc.pages)
        # **쪽이 자기 경계를 갖고 있으면 그걸 쓴다.** 한 문서 안에서도 판형이
        # 섞인다 — 실측한 KLI 브리프는 쪽마다 경계가 355.5 이기도 하고 242.5
        # 이기도 하다. 문서 하나로 못박으면 다른 판형 쪽이 어긋난다.
        # 문서값은 전면 표에 가려 자기 경계를 못 찾은 쪽의 대타다.
        return [_page_text_with_breaks(
                    page,
                    column_split(page.chars, float(page.width)) or fallback)
                for page in doc.pages]


def _document_split_x(pages) -> float | None:
    """문서의 단 경계를 **한 번** 정한다. 1단 문서면 None.

    쪽마다 따로 재면 안 된다 — 전면 표가 실린 쪽은 가운데가 글자로 덮여
    빈 띠가 사라지고, 그 쪽만 1단으로 읽혀 두 단이 한 줄에 섞인다
    (KLI 브리프 제115호 11쪽이 실제로 그랬다: 10쪽은 갈렸는데 11쪽은 안 갈렸다).
    2단 문서의 단 경계는 쪽마다 바뀌지 않으므로 깨끗한 쪽에서 정해 전체에 쓴다.

    두 쪽 이상에서 같은 자리가 잡혀야 인정한다 — 한 쪽만 잡히면 그 쪽의
    우연한 여백일 수 있다.
    """
    found = []
    for page in pages:
        x = column_split(page.chars, float(page.width))
        if x is not None:
            found.append(x)
    if len(found) < 2:
        return None
    found.sort()
    return found[len(found) // 2]


# 단 사이 빈 띠의 최소 폭. 실측한 KLI 브리프의 단 간격은 **11pt** 다
# (x 350~361). 처음에 40pt 로 잡았다가 2단인데도 1단으로 읽혔다 — 단 간격은
# 생각보다 좁다. 대신 '쪽 전체 높이에 걸쳐 글자가 하나도 없을 것' 을 함께
# 요구해 우연한 낱말 사이 공백과 가른다(한 줄에만 뚫린 구멍은 안 걸린다).
_COLUMN_GUTTER = 8.0
# 가운데 부근에서만 찾는다. 바깥 여백·들여쓰기를 단 경계로 오인하지 않기 위해서다
# (실측에서 x 128~141 에도 13pt 짜리 띠가 있었는데 그건 왼쪽 단 안의 들여쓰기다).
_COLUMN_ZONE = (0.35, 0.65)


def column_split(chars, page_width: float) -> float | None:
    """2단이면 단을 가르는 x 를, 아니면 None 을 준다.

    **낱말이 아니라 글자로 잰다.** 낱말 중심으로 히스토그램을 그리면 긴 낱말이
    골을 메워 2단인 쪽도 1단으로 보인다(실측으로 그랬다). 글자가 덮는 x 구간을
    칠해 놓고 가운데에서 **아무 글자도 없는 띠**를 찾는다.
    """
    if len(chars) < 200:
        return None
    covered = set()
    for ch in chars:
        for x in range(int(ch["x0"]), int(ch["x1"]) + 1):
            covered.add(x)
    lo, hi = page_width * _COLUMN_ZONE[0], page_width * _COLUMN_ZONE[1]
    best_width, best_mid, start = 0.0, None, None
    for x in range(int(lo), int(hi) + 1):
        if x not in covered:
            if start is None:
                start = x
        elif start is not None:
            if x - start > best_width:
                best_width, best_mid = x - start, (start + x) / 2
            start = None
    if start is not None and hi - start > best_width:
        best_width, best_mid = hi - start, (start + hi) / 2
    return best_mid if best_width >= _COLUMN_GUTTER else None


def _page_text_with_breaks(page, split_x: float | None) -> str:
    """한 쪽의 원문. **2단이면 왼쪽 단을 다 읽고 오른쪽 단으로 넘어간다.**

    안 그러면 추출이 두 단을 한 줄에 이어 붙인다 — 실측(KLI 고용·노동브리프
    제115호 2쪽):

        다. 성장의 대부분이 고용창출이 미미한 반도체 부문 화된 것으로 볼 수 있다.

    앞이 왼쪽 단, 뒤가 오른쪽 단이다. 이런 원문에서 모델이 읽어서 뜻이 통하는
    문장을 만들면 그 문장은 원문의 부분열이 아니므로 llm_verify 가 전부
    '원문에 없다'로 거절한다(실제로 KLI 21자리 중 20이 그렇게 떨어졌다).
    """
    if split_x is None:
        return text_with_paragraph_breaks(page.extract_text_lines())

    # **쪽을 잘라서 각각 추출한다.** 줄 객체를 x 로 가르는 것으로는 안 된다 —
    # extract_text_lines() 가 두 단을 이미 **한 줄 객체로 합쳐** 놓아서, 그
    # 뒤에 가르면 합쳐진 줄이 통째로 한쪽에 들어갈 뿐이다. 그리고 합쳐진 줄과
    # 진짜 전면 줄(표 행)은 bbox 로 구별되지 않는다 — 둘 다 경계를 가로지른다.
    #
    # 그 대가로 **전면 표는 좌우로 쪼개진다.** 받아들일 만하다: 표를 읽는 것은
    # 수치 경로(page_texts)이고 이 함수는 근거 경로 전용이다. 근거는 서술
    # 문장을 뽑는 것이라 반토막 난 표를 인용할 일이 없다.
    height, width = float(page.height), float(page.width)
    left = page.crop((0, 0, split_x, height)).extract_text_lines()
    right = page.crop((split_x, 0, width, height)).extract_text_lines()
    if not left or not right:
        return text_with_paragraph_breaks(page.extract_text_lines())
    # 단 사이는 문단이 갈리는 자리이기도 하다 — 빈 줄로 띄운다.
    return (text_with_paragraph_breaks(left) + "\n\n"
            + text_with_paragraph_breaks(right))


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
