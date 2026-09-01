"""KDI 경제전망 수집기.

/research/economy 는 최신 회차 본문이면서 지난 회차로 가는 드롭다운
(yearSelectUpDown)도 같이 싣는다. 드롭다운은 pub_no 와 표시 라벨만 줄 뿐
정식 제목·발표일이 없어, 회차마다 본문을 열어 parse_issue 로 실제 값을
읽는다. 드롭다운은 1982년까지 이어지므로 백필이 보지도 않을 옛 회차까지
열어보지 않도록 라벨의 연도로 미리 거른다(list_issues). 일상 수집기는
드롭다운을 아예 타지 않고 이 페이지 하나만 본다(collect) — 최신 회차를
찾자고 드롭다운 전체를 열 이유가 없다. 본문에서 회차 제목·발표일과 장별
PDF 링크를 얻어 요약 장을 읽는다. KDI PDF 표지에는 발표일이 없으므로
날짜는 반드시 본문 페이지에서 가져온다.
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import date, datetime

from .. import http, pdf, rationale_store, report
from ..models import ForecastRecord
from ..report import Issue  # 두 수집기가 같은 회차 표현을 쓴다

BASE = "https://www.kdi.re.kr"
LIST_URL = f"{BASE}/research/economy"
ISSUE_URL = f"{BASE}/research/economy?pub_no={{no}}"

# 요약표 행 이름(공백·단위·각주 제거) → 내부 지표코드. KDI 표에는 고용률이 없다.
LABEL_TO_INDICATOR = {
    "국내총생산": "gdp_growth",
    "소비자물가": "cpi",
    "취업자수(증감)": "emp_change",
    "실업률": "unemp_rate",
}

# 요약표로 인정하는 최소 지표. 동향 장에 실린 다른 표들을 거른다
REQUIRED_INDICATORS = {"gdp_growth", "cpi", "emp_change", "unemp_rate"}

# 회차 제목 앞에 네비게이션용 <h2>가 여럿 있으므로 h2 경계를 넘지 않도록 막는다
_TITLE_BLOCK = re.compile(
    r"<h2>(?P<title>(?:(?!</?h2).)*?)"
    r"<p>(?P<date>20\d{2}\.\d{2}\.\d{2})</p>\s*</h2>",
    re.S,
)
_CHAPTER = re.compile(
    r'<li class="down"><p>(?P<label>.*?)</p>'
    r"<button[^>]*location\.href='(?P<href>/file/download\?atch_no=[^']+)'",
    re.S,
)
# 드롭다운 select 본문만 잘라 그 안의 option 만 줍는다 — 페이지 다른 곳의
# option 태그(있다면)를 회차로 잘못 세는 사고를 막는다
_ISSUE_SELECT = re.compile(
    r'<select id="yearSelectUpDown"[^>]*>(?P<body>.*?)</select>', re.S,
)
_ISSUE_OPTION = re.compile(r'<option value="(?P<no>\d+)"[^>]*>(?P<label>[^<]*)</option>')
# 라벨 맨 앞의 4자리가 곧 연도다("2026년 8월", "2026 상반기", "1982年 2/4" 모두 그렇다)
_LABEL_YEAR = re.compile(r"(\d{4})")

# backfill.SINCE(2024-11-01)와 맞춘 기본 커트라인. 백필은 실제로는 이 값을
# 쓰지 않고 SINCE.year 를 그대로 넘긴다 — 여기 값은 backfill 을 거치지 않고
# list_issues() 를 단독으로 부를 때 쓰는 보수적인 기본값일 뿐이다.
DEFAULT_SINCE_YEAR = 2024

# 2월호(당해 연도 하나만 전망) 헤더가 수정폭 칸을 세로로 접어 내보내는
# 문제를 다룬다. "연도 한 토큰뿐인 줄 → 연도 두 개 이상인 줄 → 수정폭
# 표시뿐인 줄" 세 줄로 쪼개져 실제 표(기간 줄)보다 앞에 나온다.
_FOLD_YEAR_TOKEN = re.compile(r"(?:19|20)\d{2}[pe]?\)?")
_FOLD_REVISION_LINE = re.compile(r"수정폭\d*\)?")


def _unfold_february_header(text: str) -> str:
    """2월호가 세로로 접어 내보내는 수정폭 헤더를 8월호와 같은 한 줄 모양으로 편다.

    2월호는 당해 연도 하나만 전망하므로 열은 [실적 연도][전망 연도][수정폭]
    세 블록뿐이다. 그런데 pdfplumber가 표를 텍스트로 뽑을 때 수정폭 칸 위에
    세로로 쌓인 "연도"와 "수정폭n)" 글자를 실제 표보다 앞줄에, 게다가 세
    줄로 쪼개어 내놓는다: 연도 한 토큰뿐인 줄(전망 연도만 반복), 연도 두 개
    이상인 줄(실적·전망 연도), 수정폭 표시뿐인 줄. 기간 줄(상반기·하반기·
    연간…)은 그 뒤에 그대로 온전히 남아 있고, 다만 맨 끝 칸에 수정폭 몫으로
    "연간"이 한 번 더 중복돼 있을 뿐이다.

    실제 열 순서는 [연도 두 개 줄의 마지막 연도가 수정폭 몫] 이므로, 앞의
    연도 한 토큰뿐인 줄은 버리고 연도 줄의 마지막 토큰을 한 번 더 이어 붙이며,
    기간 줄의 마지막 "연간"을 수정폭 표시로 바꿔치기하면 pdf.parse_summary_table
    이 8월호에서 이미 잘 읽는 모양 그대로가 된다.

    이 네 줄 모양(연도 한 줄 → 연도 여러 개 줄 → 수정폭 줄 → 기간 줄)이
    통째로 나타날 때만 손댄다. 조금이라도 다르면(수정폭 줄이 없거나 연도
    줄이 비는 등, 표가 또 바뀐 것) 아무것도 바꾸지 않고 그대로 돌려준다 —
    어설프게 짜맞추면 값이 조용히 틀린 열에 들어가므로, 모양이 안 맞을 땐
    기존처럼 pdf.parse_summary_table 이 시끄럽게 실패하는 편이 훨씬 안전하다.
    """
    lines = text.split("\n")
    for i in range(len(lines) - 3):
        bare_year = lines[i].split()
        year_block = lines[i + 1].split()
        revision_mark = lines[i + 2].split()
        period_row = lines[i + 3].split()
        if len(bare_year) != 1 or not _FOLD_YEAR_TOKEN.fullmatch(bare_year[0]):
            continue
        if len(year_block) < 2 or not all(_FOLD_YEAR_TOKEN.fullmatch(t) for t in year_block):
            continue
        if len(revision_mark) != 1 or not _FOLD_REVISION_LINE.fullmatch(revision_mark[0]):
            continue
        if len(period_row) < 2 or not any(
            re.search(r"연간|상반|하반", token) for token in period_row
        ):
            continue
        new_year_line = " ".join([*year_block, year_block[-1]])
        new_period_line = " ".join([*period_row[:-1], revision_mark[0]])
        return "\n".join([*lines[:i], new_year_line, new_period_line, *lines[i + 4:]])
    return text


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_issue(page_html: str, url: str) -> Issue:
    match = _TITLE_BLOCK.search(page_html)
    if not match:
        raise ValueError("본문에서 회차 제목·발표일을 찾지 못했다")
    return Issue(
        title=re.sub(r"\s+,", ",", _text(match.group("title"))),
        published_at=datetime.strptime(match.group("date"), "%Y.%m.%d").date(),
        url=url,
    )


def parse_chapters(page_html: str) -> list[tuple[str, str]]:
    """(장 이름, 내려받기 URL) 을 본문에 실린 순서대로 돌려준다."""
    return [
        (_text(m.group("label")), BASE + html_lib.unescape(m.group("href")))
        for m in _CHAPTER.finditer(page_html)
    ]


def parse_issue_list(page_html: str) -> list[tuple[str, str]]:
    """회차 선택 드롭다운에서 (pub_no, 표시 라벨) 을 문서 순서(최신 먼저)대로 돌려준다.

    select 가 없으면 빈 리스트를 조용히 돌려주는 대신 예외를 던진다 —
    그러면 뒤에서 회차가 하나도 없는 것과 구별이 안 돼 백필이 조용히
    아무 일도 안 하고 끝나 버린다.
    """
    match = _ISSUE_SELECT.search(page_html)
    if not match:
        raise ValueError("페이지에서 회차 선택 목록을 찾지 못했다")
    return [(m.group("no"), m.group("label").strip())
            for m in _ISSUE_OPTION.finditer(match.group("body"))]


def _label_year(label: str) -> int | None:
    """드롭다운 라벨 맨 앞의 연도를 읽는다. 못 읽으면 None."""
    match = _LABEL_YEAR.search(label)
    return int(match.group(1)) if match else None


def parse(text: str, issue: Issue, source_url: str, source_page: int) -> list[ForecastRecord]:
    return report.records_from_table(
        _unfold_february_header(text), LABEL_TO_INDICATOR,
        org="KDI", org_name_ko="KDI",
        issue=issue, source_url=source_url, source_page=source_page,
    )


def list_issues(since_year: int = DEFAULT_SINCE_YEAR) -> list[Issue]:
    """드롭다운에 남은 회차를 최신순으로 준다.

    드롭다운은 pub_no 와 표시 라벨(예: "2025 상반기")만 줄 뿐 정식 제목과
    발표일이 없어, 회차마다 본문을 열어 parse_issue 로 실제 값을 읽어야
    한다. 문제는 드롭다운이 1982년까지 이어진다는 것 — 백필이 보는 기간
    (since_year) 보다 뚜렷하게 이전인 회차까지 매번 페이지를 열어 확인할
    이유가 없으므로, 라벨에서 읽히는 연도만으로 미리 거른다. "2024 하반기"
    처럼 커트라인 그 해에 나온 회차도 있을 수 있어 since_year 자체는
    포함한다. 라벨에서 연도를 못 읽는 경우엔 걸러내지 않고 그냥 연다 —
    회차를 조용히 건너뛰는 실패가, 필요 없는 페이지 하나를 더 여는 것보다
    훨씬 위험하다.
    """
    options = parse_issue_list(http.get(LIST_URL).text)
    if not options:
        raise ValueError("드롭다운에서 회차를 찾지 못했다")
    issues = []
    for no, label in options:
        year = _label_year(label)
        if year is not None and year < since_year:
            continue
        url = ISSUE_URL.format(no=no)
        issues.append(parse_issue(http.get(url).text, url))
    return issues


def collect_issue(issue: Issue, page_html: str | None = None) -> list[ForecastRecord]:
    """회차 하나의 본문에서 장별 PDF를 찾아 요약표를 읽는다.

    page_html 을 넘기면 그 내용을 그대로 쓴다 — collect() 가 최신 회차의
    본문을 이미 한 번 받아 놓고 여기서 같은 URL을 또 받는 중복 요청을
    막기 위한 것으로, list_issues() 를 거치는 백필 쪽은 그냥 issue 만
    넘기면 된다.
    """
    if page_html is None:
        page_html = http.get(issue.url).text
    for _, url in parse_chapters(page_html):
        # 장은 본문 순서대로 나오지만 표가 어디 실릴지는 회차마다 다르다. 앞 장이
        # 502거나 표 없는 첨부여도 뒷 장을 마저 봐야 하므로 장 단위로 실패를 가둔다.
        try:
            # find_summary_table 도 페이지마다 pdf.parse_summary_table 을 돌려 지표가
            # 다 있는지 확인한다 — 2월호는 여기서부터 접힌 헤더를 펴 둬야 요약 페이지
            # 자체를 찾는다. parse() 에서도 다시 펴지만 이미 편 텍스트는 그대로 지나간다.
            found = pdf.find_summary_table(
                (_unfold_february_header(t) for t in pdf.page_texts(http.get(url).content)),
                LABEL_TO_INDICATOR, REQUIRED_INDICATORS,
            )
        except Exception:
            continue
        if found is None:
            continue
        page_no, text = found
        return parse(text, issue, url, page_no)
    raise ValueError(f"{issue.title}: 요약표를 실은 장을 찾지 못했다")


def collect_issue_rationales(issue: Issue, page_html: str | None = None) -> list["Rationale"]:
    """그 회차의 근거 문장을 준다. 요약표를 실은 장을 못 찾으면 빈 리스트.

    collect_issue 와 같은 순서로 장을 시도해, 표가 처음 확정되는 장 하나만
    쓴다 — 장마다 표가 있을 수 있는데, 뒷 장까지 다 뒤지면 같은 지표에
    대해 서로 다른 장에서 두 문장이 나올 수 있다. 그 장 안에서 표 쪽 앞뒤
    한 쪽씩을 함께 본다(keis.collect_issue_rationales·bok.
    collect_issue_rationales 참고).

    "요약" 장을 통째로 스캔하지 않는 이유는 실측(2026년 8월호)에 있다: 그
    장 1쪽은 성장률·물가·고용 세 줄이 마침표도 빈 줄도 없이 붙어 있어,
    rationale.sentences 가 셋을 하나의 "문장"으로 묶는다("우리 경제는
    글로벌 반도체경기 호황에 힘입어 … 취업자 수는 2026년 11만명 증가한
    후 …"). 그러면 성장률 문장의 인과 표지("힘입어")가 고용 근거에도
    그대로 묻어와, 성장률 얘기를 고용 증감의 근거인 양 인용하게 된다.
    표 쪽(그 장의 마지막 쪽) 바로 앞뒤 한 쪽으로 창을 좁히면 이 1쪽은
    창 밖에 남아 이 위험을 피한다 — 그 대신 이 장에 실린 진짜 요약
    문장도 함께 놓치지만, 지표를 뒤섞어 인용하는 것보다는 아무것도
    인용하지 않는 편이 낫다.
    """
    collected: list["Rationale"] = []
    if page_html is None:
        page_html = http.get(issue.url).text
    for _, url in parse_chapters(page_html):
        try:
            pages = [_unfold_february_header(t) for t in pdf.page_texts(http.get(url).content)]
            found = pdf.find_summary_table(pages, LABEL_TO_INDICATOR, REQUIRED_INDICATORS)
        except Exception:
            continue
        if found is None:
            continue
        page_no, _ = found
        for neighbor in (page_no - 1, page_no, page_no + 1):
            if not (1 <= neighbor <= len(pages)):
                continue
            collected = rationale_store.merge(collected, report.rationales_from_text(
                pages[neighbor - 1], org="KDI", issue=issue,
                indicators=sorted(REQUIRED_INDICATORS), source_url=url,
                source_page=neighbor))
        return collected
    return collected


def collect(today: date) -> list[ForecastRecord]:
    # /research/economy 자체가 최신 회차 본문이다. list_issues() 를 타면
    # 드롭다운에 걸린 회차(1982년까지, 100개가 넘는다) 마다 발표일 확인용
    # 페이지를 열어야 하는데, 일상 수집기가 최신 회차 하나 때문에 그 비용을
    # 치를 이유가 없다 — 예전처럼 이 페이지 하나만 보고 바로 회차를 구성한다.
    page_html = http.get(LIST_URL).text
    issue = parse_issue(page_html, LIST_URL)
    return collect_issue(issue, page_html)
