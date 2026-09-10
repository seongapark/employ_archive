"""기획재정부 「경제정책방향」/「경제성장전략」 수집기.

연 2회(연간 전망 12~1월, 하반기 전망 6~8월) 나온다. 취업자 증감 전망을 싣는
몇 안 되는 출처라 이 아카이브에 값이 크다. 실업률은 이 표에 없다.

## 알아야 알 수 있는 것 셋

**1. 보고서 이름이 정권을 따라 바뀐다.** 「경제정책방향」이 2025-01-02 회차를
끝으로 「경제성장전략」으로 갈렸다(새정부). 둘 중 하나만 찾으면 2025년 8월
이후가 통째로 빈다. 그래서 KEYWORDS 로 둘 다 훑는다. 또 바뀔 수 있는 자리다.

**2. 게시판 검색은 `searchCondition` 없이는 조용히 무시된다.** `searchKeyword`
만 붙이면 200 과 함께 **필터되지 않은 전체 목록**이 온다 — 빈 결과가 아니라
그럴듯한 목록이 오므로 눈으로는 성공처럼 보인다. POST 검색은 빈 응답(len 0)이라
쓸 수 없다. 이 파라미터를 빼지 말 것.

**3. 요약표의 열은 좌표 없이는 복원할 수 없다.** 연도 머리가 하위 열 여러 개에
걸쳐 있다:

    '25년        '26년          '27년e
    실적    1/4      연간e       연간
    ...
    취업자 증감(만명)  19   18    15     17

extract_text() 는 이 걸침을 버려서 `19 18 15 17` 네 숫자가 남는데, 그중 어느
것이 2026년 **연간 전망**인지 알 방법이 사라진다(15 가 답이고, 18 은 1분기
실적이다). 그래서 낱말 좌표로 하위 열을 연도에 붙이고 `연간` 열만 취한다.
회차마다 분기 열이 있고 없고가 달라서 열 개수를 상수로 박아 둘 수 없다.
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import date, datetime
from typing import NamedTuple

from .. import http, pdf, report
from ..models import ForecastRecord
from ..report import Issue

BASE = "https://www.moef.go.kr"
BBS_ID = "MOSFBBS_000000000028"
MENU_NO = "4010100"
LIST_URL = (f"{BASE}/nw/nes/nesdta.do?bbsId={BBS_ID}&menuNo={MENU_NO}"
            "&searchCondition=1&searchKeyword={keyword}&pageIndex={page}")
VIEW_URL = (f"{BASE}/nw/nes/detailNesDtaView.do?searchBbsId1={BBS_ID}"
            "&searchNttId1={ntt}&menuNo={menu}").format(
                ntt="{ntt}", menu=MENU_NO)

KEYWORDS = ("경제정책방향", "경제성장전략")
LIST_PAGES = 3  # 회차는 연 2회다 — 3쪽(30건)이면 검색어당 10년치가 넘는다

LABEL_TO_INDICATOR = {
    "실질GDP": "gdp_growth",
    "고용률": "emp_rate",
    "취업자증감": "emp_change",
    "소비자물가": "cpi",
}

_LIST_ITEM = re.compile(
    r"fn_egov_select\('(?P<ntt>[A-Z_0-9]+)'\);\">(?P<title>.*?)</a>"
    r'.*?<span class="date">\s*(?P<date>\d{4})\.(?P<month>\d{2})\.(?P<day>\d{2})',
    re.S,
)

# 회차 제목은 보고서 이름으로 **시작한다**. 같은 검색어에 간담회·플랫폼 개설·
# 보도설명이 잔뜩 걸리는데(예: '경제정책방향 국민소통 플랫폼 개설',
# '홍남기 부총리 … 경제정책방향 기업인 간담회'), 그것들은 이름이 문장 중간에 있다.
_ISSUE_TITLE = re.compile(
    r"^[「\[(]?\s*(?:새정부|[‘’ʼ']?\d{2,4}년)\s*(?:하반기\s*)?경제(?:정책방향|성장전략)"
)

# 파일이름은 <a> 의 글자다(<span> 안이 아니다). 같은 첨부에 걸린 '다운로드'
# 단추는 글자가 <span> 으로 시작해 이 정규식에 안 걸린다 — 그래서 걸러진다.
_ATTACHMENT = re.compile(
    r'href="(?P<url>/com/cmm/fms/FileDown\.do[^"]*?atchFileId=[^"]+)"[^>]*>\s*'
    r"(?P<name>[^<]+?)\s*</a>",
    re.S,
)
# 주소에 `;jsessionid=...` 가 끼어 온다. source_url 은 forecasts.json 에 커밋되므로
# 세션 토큰을 그대로 실으면 안 되고, 실어 봐야 그 세션이 끝나면 죽는 주소다.
# 붙이지 않아도 파일은 그대로 받아진다(실측).
_JSESSIONID = re.compile(r";jsessionid=[^?]*")
# 보도자료는 한 쪽짜리 요약이라 전망표가 없다. 본문(_최종.pdf 등)에 있다.
# 전망표는 본문에 있다. 보도자료(한두 쪽 요약)와 모두발언은 뒤로 미룬다 —
# 실측한 첨부 이름이 '(보도자료) ….pdf' 도 되고 '250101 … 보도자료.pdf' 도 되므로
# 앞머리로만 판정하면 못 거른다. 순서만 미루고 버리지는 않는다(회차에 따라
# 본문 없이 보도자료에만 표가 실릴 수 있다).
_SIDE_ATTACHMENT = re.compile(r"보도자료|모두발언|수혜자별")

_TABLE_CAPTION = re.compile(r"경제전망\s*(?:요약|전망치)?")
# 작은따옴표가 회차마다 다르다 — 2026년 하반기호는 U+0027('25년), 1월호들은
# U+2018(‘25년)이다. 한 벌만 받으면 그 회차만 조용히 안 잡힌다.
_YEAR_HEAD = re.compile(r"^[‘’ʼ'`]?(\d{2,4})년[ep]?$")
# 연간 전망 열의 이름이 회차마다 다르다: 하반기호는 '연간'/'연간e', 1월호는 '전망'.
_ANNUAL_HEAD = re.compile(r"^(?:연간|전망)[ep]?$")
_PERIOD_HEAD = re.compile(r"^(?:연간|전망|실적|\d/4)")
_NUMBER = re.compile(r"^△?-?[\d,]+(?:\.\d+)?$")
# 연도 머리와 그 연간 열이 같은 자리에 올 때의 부동소수점 오차 여유(px).
_COLUMN_SLACK = 2.0


class Column(NamedTuple):
    year: int
    x: float


def _center(word: dict) -> float:
    return (word["x0"] + word["x1"]) / 2


def _rows(words: list[dict], tol: float = 5.0) -> list[list[dict]]:
    """낱말을 같은 줄끼리 묶는다.

    **바로 앞 낱말과 견준다(줄의 첫 낱말이 아니라).** 머리글 한 줄이 글자
    크기 차이로 top 이 조금씩 흘러서, 첫 낱말에 고정해 재면 줄이 쪼개진다 —
    실측한 연도 줄은 하반기호가 149.4 → 151.4 → 152.8, 1월호가
    164.1 → 168.4 라, 첫 낱말 기준으로 재면 연도 하나가 떨어져 나간다.
    본문 줄 간격은 15px 이상이라 이 연쇄로 이웃 줄이 붙지는 않는다.
    """
    out: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if out and abs(word["top"] - out[-1][-1]["top"]) <= tol:
            out[-1].append(word)
        else:
            out.append([word])
    return [sorted(row, key=lambda w: w["x0"]) for row in out]


def _to_year(token: str) -> int | None:
    match = _YEAR_HEAD.match(token)
    if not match:
        return None
    value = int(match.group(1))
    return value if value > 100 else 2000 + value


def annual_columns(words: list[dict]) -> list[Column]:
    """요약표에서 **연간 전망** 열만 골라 (연도, x중심) 으로 준다.

    연도 줄과 그 아래 기간 줄을 찾아, 기간 토큰을 x 구간으로 연도에 붙이고
    연간 전망 열만 남긴다 — '실적'·'1/4' 은 전망이 아니다.
    """
    rows = _rows(words)
    for index, row in enumerate(rows[:-1]):
        years = [(_to_year(w["text"]), _center(w)) for w in row]
        years = [(y, x) for y, x in years if y is not None]
        if len(years) < 2:
            continue
        below = rows[index + 1]
        periods = [w for w in below if _PERIOD_HEAD.match(w["text"])]
        if not any(_ANNUAL_HEAD.match(w["text"]) for w in periods):
            continue
        # **최근접이 아니라 구간 포함으로 붙인다.** 연도 머리는 자기 하위 열들
        # 위에 가운데 놓이므로, 하위 열이 여럿이면 오른쪽 끝 열(=연간)이 다음
        # 연도 머리에 더 가까워진다. 2025년 경제정책방향 72쪽이 실제로 그렇다:
        #   ‘24년@365 … 연간e@433 … ‘25년@493
        # 최근접으로 붙이면 ‘24년의 연간이 ‘25년 것이 되어 값이 한 해씩 밀린다.
        # 연도 머리 x 는 자기 연간 열 x 이하이고 다음 연도 머리 x 미만이다.
        years.sort(key=lambda yx: yx[1])
        columns = []
        for word in periods:
            if not _ANNUAL_HEAD.match(word["text"]):
                continue
            x = _center(word)
            # 그 열의 **왼쪽에 있는 마지막 연도**에 붙인다. 열 구간의 오른쪽
            # 경계로 자르면 안 된다 — 하위 열이 하나뿐인 해는 연도 머리와 열이
            # 같은 자리에 오는데, 실측 x 가 505.44 대 505.43999 로 갈려
            # 경계 비교가 한 해 왼쪽으로 떨어졌다(2026년 경제성장전략 55쪽).
            left = [y for y, yx in years if yx <= x + _COLUMN_SLACK]
            if left:
                columns.append(Column(left[-1], x))
        if columns:
            return columns
    raise ValueError("요약표에서 연도·기간 머리글을 찾지 못했다")


def _label(text: str) -> str:
    """행 이름에서 단위·괄호·구분자를 떼어 LABEL_TO_INDICATOR 의 열쇠로 만든다."""
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"^[▪▫ㅇ·・\-\s]+", "", text)
    return re.sub(r"\s+", "", text)


def _value(token: str) -> float:
    # 정부 보고서는 음수를 세모로 쓴다: △9.7 = -9.7
    return float(token.replace("△", "-").replace(",", ""))


def parse_words(words: list[dict]) -> dict[tuple[str, int, str], float]:
    """요약표 쪽의 낱말에서 {(지표, 연도, 'annual'): 값} 을 뽑는다."""
    columns = annual_columns(words)
    values: dict[tuple[str, int, str], float] = {}
    for row in _rows(words):
        numbers = [w for w in row if _NUMBER.match(w["text"])]
        label_words = [w for w in row if not _NUMBER.match(w["text"])]
        if not numbers or not label_words:
            continue
        indicator = LABEL_TO_INDICATOR.get(
            _label(" ".join(w["text"] for w in label_words))
        )
        if indicator is None:
            continue
        for column in columns:
            near = min(numbers, key=lambda w: abs(_center(w) - column.x))
            # 숫자는 오른쪽 맞춤이라 머리글보다 조금 오른쪽에 온다(실측 +14~18px).
            # 30px 을 넘으면 그 열에 값이 없는 줄이므로 붙이지 않는다.
            if abs(_center(near) - column.x) <= 30:
                values[(indicator, column.year, "annual")] = _value(near["text"])
    if not values:
        raise ValueError("요약표에서 지표 행을 하나도 읽지 못했다")
    return values


def is_issue_title(title: str) -> bool:
    return bool(_ISSUE_TITLE.match(title.strip()))


def parse_list(page_html: str) -> list[tuple[str, date, str]]:
    out = []
    for match in _LIST_ITEM.finditer(page_html):
        title = html_lib.unescape(
            re.sub(r"<[^>]+>", "", match.group("title"))
        ).strip()
        published = date(int(match.group("date")), int(match.group("month")),
                         int(match.group("day")))
        out.append((match.group("ntt"), published, title))
    return out


def parse_attachments(view_html: str) -> list[tuple[str, str]]:
    """(파일이름, 절대주소) 목록. 같은 첨부가 두 번 실려 있어 중복을 없앤다."""
    seen, out = set(), []
    for match in _ATTACHMENT.finditer(view_html):
        name = html_lib.unescape(match.group("name")).strip()
        url = BASE + _JSESSIONID.sub("", html_lib.unescape(match.group("url")))
        if url in seen or not name.lower().endswith(".pdf"):
            continue
        seen.add(url)
        out.append((name, url))
    return sorted(out, key=lambda nu: bool(_SIDE_ATTACHMENT.search(nu[0])))


def list_issues() -> list[Issue]:
    found: dict[str, Issue] = {}
    for keyword in KEYWORDS:
        for page in range(1, LIST_PAGES + 1):
            html = http.get(LIST_URL.format(keyword=keyword, page=page)).text
            rows = parse_list(html)
            if not rows:
                break
            for ntt, published, title in rows:
                if not is_issue_title(title):
                    continue
                found[ntt] = Issue(title=title, published_at=published,
                                   url=VIEW_URL.format(ntt=ntt))
    if not found:
        raise ValueError("게시판에서 경제정책방향·경제성장전략 회차를 찾지 못했다")
    return sorted(found.values(), key=lambda i: i.published_at, reverse=True)


def collect_issue(issue: Issue) -> list[ForecastRecord]:
    attachments = parse_attachments(http.get(issue.url).text)
    if not attachments:
        raise ValueError(f"{issue.title}: PDF 첨부를 찾지 못했다")
    failures = []
    for name, url in attachments:
        data = http.get(url).content
        if data[:4] != b"%PDF":
            continue
        pages = pdf.page_texts(data)
        for page_no, text in enumerate(pages, start=1):
            if not _TABLE_CAPTION.search(text) or "취업자" not in text:
                continue
            try:
                values = parse_words(pdf.page_words(data, page_no))
            except ValueError as exc:
                # 표 차례·본문 서술에도 같은 낱말이 나온다 — 쪽 단위로 실패를 가둔다
                failures.append(f"{name} {page_no}쪽: {exc}")
                continue
            records = report.records_from_values(
                values, org="MOEF", org_name_ko="기획재정부", issue=issue,
                source_url=url, source_page=page_no,
            )
            # 표는 읽혔는데 남은 레코드가 없다면 열이 한 해씩 밀린 것이다
            # (records_from_values 가 발표연도 이전 해를 실적으로 보고 버린다).
            # 빈 손을 성공으로 돌려주면 그 회차가 조용히 사라진다.
            if not records:
                failures.append(f"{name} {page_no}쪽: 전망 연도가 하나도 안 남았다"
                                f"(읽은 연도 {sorted({y for _, y, _ in values})})")
                continue
            return records
    detail = " / ".join(failures[:3]) or "표를 실은 쪽이 없다"
    raise ValueError(f"{issue.title}: 경제전망 요약표를 읽지 못했다 — {detail}")


def collect(today: date) -> list[ForecastRecord]:
    return collect_issue(list_issues()[0])
