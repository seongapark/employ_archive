"""한국고용정보원 「고용동향브리프」 수집기.

원칙은 연 1회다 — 연말호가 이듬해 연간 전망을 싣는다. 다만 2026년은 하반기
전망호(제5호)가 따로 나왔다. 회차 번호로 전망호를 특정할 수 없다는 뜻이라,
새 호가 올라오면 열어 보고 전망표가 있는지 확인한다.

이 브리프의 PDF 에는 텍스트 레이어가 없다(ocr.py 머리말 참고). 쪽을
렌더링해 읽으므로 다른 수집기보다 느리고, 그래서 두 단계로 나눈다 —
낮은 해상도로 후보 쪽을 좁힌 뒤 그 쪽만 정밀하게 읽는다.
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import date, datetime
from typing import NamedTuple

from .. import http, ocr, report
from ..models import ForecastRecord
from ..report import Issue

BASE = "https://www.keis.or.kr"
LIST_URL = f"{BASE}/keis/ko/proj/118/pblc/list.do"
DETAIL_URL = f"{BASE}/keis/ko/proj/118/pblc/detail.do?categoryIdx={{category}}&pubIdx={{pub}}"

_ROW = re.compile(r"<tr[\s>].*?</tr>", re.S)
_SUBJECT = re.compile(
    r"goDetail\('categoryIdx=(?P<category>\d+)&(?:amp;)?pubIdx=(?P<pub>\d+)'\)[^>]*>"
    r"(?P<title>.*?)</a>", re.S)
_DATE = re.compile(r'class="cell-date".*?<span>(\d{4})\.(\d{2})\.(\d{2})</span>', re.S)
_PDF = re.compile(r'href="(/keis/ko/cmmn/download\.do\?[^"]+)"')


class ListedIssue(NamedTuple):
    issue: Issue
    pdf_url: str


def parse_list(page_html: str) -> list[ListedIssue]:
    """목록 페이지의 <tr> 을 회차로 옮긴다.

    목록 맨 위 대표 게시물 블록은 1번 행과 같은 회차를 한 번 더 싣는다.
    <tr> 만 읽어 중복을 피한다.

    subject 앵커(goDetail(...))가 없는 행은 헤더·레이아웃용 행이라 조용히
    건너뛴다. 하지만 subject 앵커가 있는데 게시일이나 PDF 링크가 없다면
    그 행은 분명 게시물인데 못 읽은 것이다 — 서식이 바뀐 신호이므로
    조용히 넘기지 않고 실패시킨다. 그래야 매일 도는 수집기가 1번 행을
    건너뛰고 이미 있는 회차를 다시 모아 added: 0 으로 조용히 끝나는
    사고를 막는다.
    """
    listed = []
    for row in _ROW.findall(page_html):
        subject = _SUBJECT.search(row)
        if not subject:
            continue
        title = html_lib.unescape(subject.group("title")).strip()
        published = _DATE.search(row)
        pdf = _PDF.search(row)
        if not published:
            raise ValueError(f"{title}: 게시일을 찾지 못했다 — 서식이 바뀌었다")
        if not pdf:
            raise ValueError(f"{title}: PDF 다운로드 링크를 찾지 못했다 — 서식이 바뀌었다")
        listed.append(ListedIssue(
            issue=Issue(
                title=title,
                published_at=datetime.strptime(
                    "".join(published.groups()), "%Y%m%d").date(),
                url=DETAIL_URL.format(category=subject.group("category"),
                                      pub=subject.group("pub")),
            ),
            pdf_url=BASE + html_lib.unescape(pdf.group(1)),
        ))
    return listed


def list_issues() -> list[ListedIssue]:
    listed = parse_list(http.get(LIST_URL).text)
    if not listed:
        raise ValueError("목록에서 고용동향브리프 회차를 찾지 못했다")
    return listed


# 연도 칸은 '2026년', 잠정치는 '2026년p'. OCR 이 그 p 를 6·0 으로도 읽는다.
_YEAR_CELL = re.compile(r"(20\d{2})년[a-zA-Z0-9]?")
_HALF_WORDS = {"상반기": "h1", "하반기": "h2"}
# 헤더 줄로 인정할 최소 연도 개수. 본문 문장에도 연도가 한둘 나온다.
_MIN_YEARS = 3


class NoHeaderRow(ValueError):
    """전망표의 연도 줄이 없다 — 이 쪽에는 전망표가 없다는 뜻이다."""


class NotForecastTable(ValueError):
    """연도 헤더는 있지만 우리가 찾는 지표가 하나도 없다 — 전망표가 아닌
    다른 표다.

    브리프 한 호에는 연도 헤더가 있는 표가 여럿 실린다(고용률 추이,
    산업별 취업자 등). 그런 표를 만나면 지표가 하나도 안 걸리는 게
    정상이라 "다른 표다"로 건너뛴다. 반면 지표가 일부만 걸리면 그건
    전망표인데 서식이 바뀌어 못 읽은 것이니 조용히 넘기면 안 된다.
    """


def header_columns(lines: list[str]) -> list[tuple[int, str]]:
    """헤더에서 열 순서대로 (연도, 기간) 을 만든다.

    이 표에는 '연간' 토큰이 없다 — 연도 칸 자체가 연간이고, 반기가 있을 때만
    마지막 연도의 하위 열로 오른쪽에 붙는다. 기존 pdf._columns 가 기간 토큰을
    연도 블록으로 묶는 것과 구조가 달라 여기서 따로 만든다.
    """
    for index, line in enumerate(lines):
        years = [int(y) for y in _YEAR_CELL.findall(line)]
        if len(years) < _MIN_YEARS:
            continue
        columns = [(year, "annual") for year in years]
        following = lines[index + 1] if index + 1 < len(lines) else ""
        halves = [_HALF_WORDS[word] for word in ("상반기", "하반기")
                  if word in following]
        return columns + [(years[-1], half) for half in halves]
    raise NoHeaderRow("표에서 연도 줄을 찾지 못했다")


# 표의 대분류. '(증감)' 이 여러 번 나오므로 직전 대분류를 기억해야 한다.
_SECTIONS = ("생산가능인구", "경제활동인구", "취업자", "비경제활동인구")
# (대분류, 행 이름) -> 지표코드. 대분류가 필요 없는 행은 왼쪽을 None 으로 둔다.
LABEL_TO_INDICATOR = {
    ("취업자", "(증감)"): "emp_change",
    (None, "실업률"): "unemp_rate",
    (None, "고용률"): "emp_rate",
}
# 표는 천명 단위, 아카이브는 만명 단위다
SCALE = {"emp_change": 0.1}
REQUIRED_INDICATORS = frozenset({"emp_change", "emp_rate", "unemp_rate"})

# 괄호는 양쪽이 짝을 이뤄야 한다 — 한쪽만 있으면 숫자가 아니라 각주 표시
# ('1)' 같은) 다. 짝을 안 보면 '1)' 이 값 1.0 으로 읽혀 열이 하나 밀리고,
# 그 밀린 개수가 우연히 len(columns) 와 같으면 그 줄 전체가 엉뚱한
# 기간에 조용히 들어간다.
_NUMBER = re.compile(r"^\([-−]?[\d,]+(?:\.\d+)?\)$"
                      r"|^\[[-−]?[\d,]+(?:\.\d+)?\]$"
                      r"|^[-−]?[\d,]+(?:\.\d+)?$")
_WRAPPING_PAREN = re.compile(r"^[(\[]|[)\]]$")


def _number(token: str) -> float | None:
    """'(146)' · '-0.8' · '29,203' 을 숫자로. 아니면 None.

    이 표는 증감·증가율을 괄호로 감싸므로 기존 pdf._NUMBER 로는 못 읽는다.
    """
    if not _NUMBER.match(token):
        return None
    cleaned = _WRAPPING_PAREN.sub("", token).replace(",", "").replace("−", "-")
    if not cleaned or cleaned == "-":
        # ',,,' 처럼 콤마·부호만 있는 토큰은 정규식은 통과하지만 숫자가 아니다.
        # 여기서 걸러야 파서가 이 줄을 조용히 건너뛴다 — 안 그러면 float("")
        # 가 예상 못 한 ValueError 를 던져, 표가 있는 쪽을 없는 쪽으로 오판한다.
        return None
    return float(cleaned)


def _split_row(line: str) -> tuple[str, list[float]]:
    """줄을 (행 이름, 숫자들) 로 가른다. 첫 숫자 앞까지가 이름이다."""
    words, numbers = [], []
    for token in line.split():
        value = _number(token)
        if value is None and not numbers:
            words.append(token)
        elif value is not None:
            numbers.append(value)
    return "".join(words), numbers


def parse_table(text: str) -> dict[tuple[str, int, str], float]:
    """전망표 원문에서 {(지표, 연도, 기간): 값} 을 뽑는다."""
    lines = [line for line in text.split("\n") if line.strip()]
    columns = header_columns(lines)

    values: dict[tuple[str, int, str], float] = {}
    section = None
    # 지표 라벨이 한 번이라도 걸렸는지 따로 기록한다. 숫자 개수가 열 개수와
    # 안 맞아 값을 못 채운 줄이라도, 라벨만은 우리 지표였을 수 있다 —
    # 그 경우와 '지표가 원래 하나도 없는 표'를 구분해야 한다(아래 참고).
    label_matched_indicator = False
    for line in lines:
        label, numbers = _split_row(line)
        if label in _SECTIONS:
            section = label
        elif label and not label.startswith("("):
            # 대분류가 끝나는 지점. 이걸 안 지우면, 훗날 다른 대분류 밑에도
            # '(증감)' 하위행이 생겼을 때 그게 여전히 '취업자' 대분류로
            # 남아 있는 section 과 짝지어져 emp_change 로 잘못 읽힌다.
            # label 이 빈 줄(숫자만 있는 줄)은 여기서 걸러야 한다 — tesseract
            # psm 6 이 라벨 줄과 숫자 줄을 둘로 쪼갤 때가 있는데, 그 숫자만
            # 있는 줄 때문에 section 이 지워지면 바로 다음 줄의 진짜 라벨이
            # 대분류를 잃는다.
            section = None
        indicator = (LABEL_TO_INDICATOR.get((section, label))
                     or LABEL_TO_INDICATOR.get((None, label)))
        if indicator is not None:
            label_matched_indicator = True
        if len(numbers) != len(columns):
            continue
        if indicator is None:
            continue
        scale = SCALE.get(indicator, 1.0)
        for (year, period), value in zip(columns, numbers):
            values[(indicator, year, period)] = round(value * scale, 2)

    found = {indicator for indicator, _, _ in values}
    missing = REQUIRED_INDICATORS - found
    if missing == REQUIRED_INDICATORS:
        if not label_matched_indicator:
            # 라벨조차 하나도 안 걸렸다 — 연도 헤더는 있지만 이 표엔 우리
            # 지표가 아예 없다. 서식이 바뀐 게 아니라 애초에 다른 표라는 뜻이다.
            raise NotForecastTable(
                f"전망표가 아니다 — 지표를 하나도 찾지 못했다: {sorted(missing)}")
        # 라벨은 걸렸는데 숫자 개수가 매번 열 개수와 어긋났다 — 예를 들어
        # OCR 이 반기 하위줄을 통째로 놓쳐 열이 4개인데 데이터 줄은 여전히
        # 6개짜리다. 이건 '다른 표'가 아니라 전망표를 못 읽은 것이니
        # NotForecastTable 로 조용히 건너뛰면 안 된다 — find_forecast_page 가
        # 진짜 전망표를 그대로 지나쳐 "전망표 없음"으로 보고해 버린다.
        raise ValueError(
            "전망표를 찾았지만 열 개수가 맞지 않는다 — 헤더의 반기 줄을 "
            "잘못 읽었을 가능성이 크다")
    if missing:
        raise ValueError(f"전망표에서 지표를 찾지 못했다: {sorted(missing)}")
    return values


def parse(text: str, issue: Issue, source_url: str,
          source_page: int) -> list[ForecastRecord]:
    return report.records_from_values(
        parse_table(text), org="KEIS", org_name_ko="한국고용정보원", issue=issue,
        source_url=source_url, source_page=source_page,
    )


# 1차 스크리닝 해상도. 라벨을 못 읽어도 상관없다 — '전망' 두 글자만 찾는다.
SCREEN_DPI = 150
SCREEN_KEYWORD = "전망"


def find_forecast_page(page_texts: list[str], page_numbers: list[int],
                       published_at: date) -> tuple[int, str] | None:
    """전망표가 실린 (쪽번호, 원문) 을 준다. 없으면 None.

    캡션으로 찾지 않는다 — OCR 이 '표1' 을 'WED' 로도 읽는다. 실제로 파싱해
    보고 지표가 다 나오는 쪽을 고른다. 표 앞 도입부 쪽이 같은 수치를 문장으로
    싣는데, 그 쪽은 헤더가 없어 자연히 걸러진다.

    건너뛰는 예외는 NoHeaderRow · NotForecastTable 둘로 한정한다(허용 목록).
    메시지 문자열로 판별하면(예: '지표'가 없으면 건너뛴다) parse_table 이
    앞으로 던질 수도 있는, 지금은 예상 못 한 다른 오류까지 전부 "표 없음"
    으로 조용히 삼켜버린다. 표는 있는데 못 읽은 경우를 놓치지 않으려면
    알려진 "표 없음" 신호만 건너뛰고 나머지는 전부 위로 흘려보내야 한다.

    브리프 한 호에는 연도 헤더가 있는 표가 여러 개 실린다 — 전망표는 그중
    하나일 뿐이다. NotForecastTable 은 그런 '다른 표'를 만났다는 뜻이라
    건너뛰고 다음 후보 쪽을 계속 찾는다.

    이 브리프는 도입부에 취업자·(증감)·실업률·고용률을 과거 연도만으로 채운
    요약표를 싣는데, 그 표는 우리 지표 3개가 전부 걸려 parse_table 을 그대로
    통과한다. 그래서 지표가 다 나온다고 바로 받아들이지 않고, 열에 발표연도
    이상인 연도가 하나라도 있는지까지 확인한다. 없으면 과거 실적표일 뿐이니
    건너뛰고 다음 후보를 본다 — 그렇지 않으면 parse() 가 발표연도 이전 열을
    전부 버려 빈 리스트를 내놓고, collect_issue 는 "전망 없음"으로 오판한다.

    이건 대가가 있는 선택이다. 지표 3개가 하나도 안 걸리면 '다른 표'로
    보고 넘어가야 흔한 경우(호마다 있는 다른 연도표들)를 통과시킬 수 있다.
    하지만 그 대가로, 진짜 전망표인데 OCR 이 심하게 망가져 지표 3개를
    전부 놓친 쪽도 똑같이 조용히 건너뛰어진다 — 그러면 이 회차는 "전망표
    없음"으로 보고되고 만다. 그래서 "이 회차엔 분명 전망표가 있는데
    빈손으로 나온다"는 문제를 조사할 땐, 표가 없다고 단정하지 말고 그
    표 쪽의 OCR 품질부터 의심해야 한다.

    다만 그 의심은 이 함수에 넘어온 후보 쪽에만 유효하다. 후보 자체는
    150dpi 스크리닝에서 '전망' 두 글자가 걸린 쪽만 추려 만든다(전처리 없이).
    그 해상도·전처리 없음 조건에서 '전망'이 심하게 뭉개지면 표가 실린 쪽이
    애초에 후보에 오르지 못해 이 함수는 호출조차 안 된다 — 그러면 400dpi
    전처리 출력을 아무리 들여다봐도 그 쪽은 없다. "표가 없다고 보고된 회차"를
    조사할 땐 이 두 지점(150dpi 스크리닝 탈락 vs 여기서의 건너뛰기)을 모두
    의심해야 한다.
    """
    for page_no, text in zip(page_numbers, page_texts):
        try:
            values = parse_table(text)
        except (NoHeaderRow, NotForecastTable):
            continue
        years = {year for _, year, _ in values}
        if not any(year >= published_at.year for year in years):
            continue
        return page_no, text
    return None


def collect_issue(listed: ListedIssue, *, fetch=None,
                  read_pages=None) -> list[ForecastRecord]:
    """회차 하나를 읽는다. 전망표가 없으면 빈 리스트 — 실패가 아니다."""
    fetch = fetch or (lambda url: http.get(url).content)
    read_pages = read_pages or ocr.page_texts

    data = fetch(listed.pdf_url)
    screened = read_pages(data, None, dpi=SCREEN_DPI, preprocess=False)
    candidates = [page_no for page_no, text in enumerate(screened, start=1)
                  if SCREEN_KEYWORD in text]
    if not candidates:
        return []

    texts = read_pages(data, candidates, dpi=400, preprocess=True)
    found = find_forecast_page(texts, candidates, listed.issue.published_at)
    if found is None:
        # 후보는 있었는데 전망표로 확정된 쪽이 없었다는 뜻이다. "후보 자체가
        # 없었다"(위의 return [])와 로그에서 구분돼야, 원인을 150dpi 스크리닝
        # 탈락과 여기 판정 실패 중 어디서부터 찾을지 바로 알 수 있다.
        print(f"{listed.issue.title}: 후보 {len(candidates)}쪽 중 전망표로 "
              f"확정된 쪽이 없다")
        return []
    page_no, text = found
    records = parse(text, listed.issue, listed.pdf_url, page_no)
    if not records:
        # find_forecast_page 가 이미 발표연도 이상 열이 있는 쪽만 통과시켰으니,
        # 그 쪽에서 parse 가 빈 리스트를 낸다면 그건 "전망 없음"이 아니라
        # 모순이다 — 조용히 넘기면 안 된다.
        raise ValueError(
            f"{listed.issue.title}: {page_no}쪽에서 전망표를 찾았지만 "
            "레코드를 만들지 못했다")
    return records


def collect(today: date) -> list[ForecastRecord]:
    return collect_issue(list_issues()[0])
