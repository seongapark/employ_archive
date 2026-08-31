"""월별 보도자료 색인.

`series.json` 은 숫자를 든다. 이 색인은 **그 숫자가 어느 글에서 나왔는지**를 든다.

왜 나눴나: 수집기는 최신 회차 하나를 받아 28개월치를 한꺼번에 읽는다. 그래서
모든 달의 레코드가 같은 게시글 URL 과 같은 첨부를 갖게 되고, 화면에서 2025년
3월을 보다가 `보도자료` 를 누르면 2026년 7월 글이 열렸다. 달마다 게시글을 찾아
넣으려면 레코드의 메타데이터를 고쳐야 하는데, `store.upsert` 는 값이 같으면
메타데이터 변경을 일부러 무시한다(그게 옳다 — 숫자가 같으면 같은 관측이다).
색인을 따로 두면 그 규칙을 건드리지 않고도 달마다 정확한 출처를 갖는다.

게시판이 둘이다. 고용노동부(사업체노동력조사·고용행정통계)와 국가데이터처(경활).
목록에서 제목의 `YYYY년 M월` 을 읽어 기간을 얻고, 상세에서 첨부를 얻는다.

여기 있는 함수는 전부 **HTML 문자열을 받는 순수 함수**다. 네트워크는 fetch.py
쪽 얇은 층이 맡는다 — 그래야 픽스처로 검증된다.
"""
from __future__ import annotations

import re
import time
from typing import Callable

import requests

# 제목의 연·월. 경활은 `26년 7월 고용동향` 처럼 두 자리 연도를 쓰기도 한다.
_TITLE_PERIOD = re.compile(r"(\d{2,4})\s*년\s*(\d{1,2})\s*월")
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_TAG = re.compile(r"<[^>]+>")
_POSTED = re.compile(r"(20\d{2})[.\-/](\d{2})[.\-/](\d{2})")


def _strip(html: str) -> str:
    return re.sub(r"\s+", " ", _TAG.sub(" ", html)).strip()


def period_of(title: str) -> str | None:
    """제목에서 기준월을 읽는다. 없으면 None — 부가조사·분기 자료가 그렇다."""
    m = _TITLE_PERIOD.search(title)
    if m is None:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    if year < 100:                      # `26년` → 2026년
        year += 2000
    if not (1 <= month <= 12) or not (2000 <= year <= 2100):
        return None
    return f"{year}-{month:02d}"


def moel_list(html: str, *, must_contain: str) -> dict[str, dict]:
    """고용노동부 보도자료 목록 → {기간: {url, title}}.

    `must_contain` 으로 같은 게시판의 다른 통계를 걸러낸다. 사업체노동력조사
    검색 결과에는 `지역별사업체노동력조사`·`직종별사업체노동력조사` 도 섞여
    들어오는데, 이들은 분기·반기 자료라 월 색인에 넣으면 안 된다.
    """
    out: dict[str, dict] = {}
    body = _COMMENT.sub("", html)
    for m in re.finditer(r'enewsView\.do\?news_seq=(\d+)[^>]*>(.*?)</a>(.{0,900}?)(?=enewsView\.do\?|$)',
                         body, re.S):
        seq, title, rest = m.group(1), _strip(m.group(2)), m.group(3)
        if must_contain not in title.replace(" ", ""):
            continue
        period = period_of(title)
        if period is None:
            continue
        post = {
            "url": f"https://www.moel.go.kr/news/enews/report/enewsView.do?news_seq={seq}",
            "title": title,
        }
        # 발표일. 목록 행이 들고 있으므로 지어낼 필요가 없다 — 보도자료에서 읽은
        # 숫자의 released_at 이 여기서 온다.
        posted = _POSTED.search(_strip(rest))
        if posted:
            post["posted_at"] = f"{posted.group(1)}-{posted.group(2)}-{posted.group(3)}"
        out.setdefault(period, post)
    return out


def mods_list(html: str, *, must_contain: str = "고용동향") -> dict[str, dict]:
    """국가데이터처 보도자료 목록 → {기간: {url, title, attachments}}.

    이 게시판에는 고용동향 말고도 부가조사·지역별고용조사·임금근로 일자리동향이
    섞여 있다. 제목이 `고용동향` 으로 끝나는 월간 회차만 가져간다 — `고령층
    부가조사` 같은 글도 `2026년 5월` 을 달고 있어서 기간만으로는 갈리지 않는다.

    첨부가 목록 페이지에 이미 있으므로 상세를 따로 두드리지 않는다(고용노동부는
    상세에만 있어서 그쪽만 detail 요청이 필요하다).
    """
    body = _COMMENT.sub("", html.replace("&amp;", "&"))
    files = mods_attachments(body)

    out: dict[str, dict] = {}
    for m in re.finditer(r'<a class="board_link"[^>]*list_no=(\d+)[^>]*>(.*?)</a>', body, re.S):
        list_no, title = m.group(1), _strip(m.group(2))
        if not title.replace(" ", "").endswith(must_contain):
            continue
        period = period_of(title)
        if period is None:
            continue
        out.setdefault(period, {
            "url": ("https://mods.go.kr/board.es?mid=a10301030100&bid=a103010301"
                    f"&list_no={list_no}&act=view"),
            "title": title,
            "attachments": files.get(list_no, []),
        })
    return out


# 첨부 확장자 → 화면이 쓰는 이름. hwp 와 hwpx 는 같은 한글 문서이므로 한 종류로
# 묶고, 둘 다 있으면 hwpx 를 남긴다(둘을 다 내보내면 `한글 받기` 버튼이 두 개다).
_EXT = {"hwpx": "hwpx", "hwp": "hwpx", "pdf": "pdf", "xlsx": "xlsx", "xls": "xlsx"}
_PREFER = {"hwpx": ("hwpx", "hwp"), "pdf": ("pdf",), "xlsx": ("xlsx", "xls")}


def _pick(raw: list[tuple[str, str]]) -> list[dict]:
    """[(원본확장자, url)] → 종류당 하나. 순서는 hwpx · pdf · xlsx."""
    out = []
    for kind, prefer in _PREFER.items():
        for want in prefer:
            hit = next((url for ext, url in raw if ext == want), None)
            if hit:
                out.append({"type": kind, "url": hit})
                break
    return out


def mods_attachments(html: str) -> dict[str, list[dict]]:
    """국가데이터처 목록 페이지의 첨부를 게시글 번호별로. 링크 클래스가
    `bf_pdf`·`bf_hwpx` 처럼 확장자를 그대로 들고 있다."""
    raw: dict[str, list[tuple[str, str]]] = {}
    for m in re.finditer(
            r'href="(/boardDownload\.es\?[^"]*?list_no=(\d+)[^"]*)"\s*class="bf_(\w+)"',
            html.replace("&amp;", "&")):
        href, list_no, ext = m.group(1), m.group(2), m.group(3).lower()
        if ext not in _EXT:
            continue
        raw.setdefault(list_no, []).append((ext, "https://mods.go.kr" + href))
    return {no: _pick(items) for no, items in raw.items()}


def moel_attachments(html: str) -> list[dict]:
    """고용노동부 게시글의 첨부. 같은 파일이 이름 링크와 `다운로드` 링크로
    두 번 나오므로 종류당 하나만 남긴다."""
    raw = []
    for m in re.finditer(r'href="(/common/downloadFile\.do\?[^"]+)"',
                         html.replace("&amp;", "&")):
        href = m.group(1)
        ext = re.search(r"file_ext=([A-Za-z]+)", href)
        ext = (ext.group(1) if ext else "").lower()
        if ext not in _EXT:
            continue
        raw.append((ext, "https://www.moel.go.kr" + href))
    return _pick(raw)


def merge(existing: dict, source: str, found: dict[str, dict]) -> dict:
    """찾은 회차를 색인에 얹는다.

    이미 있는 달의 값은 덮어쓰지 않는다 — 상세에서 받아둔 첨부를 목록만 보고
    지우면 안 된다. 다만 **없던 항목은 채운다**: 색인이 담는 것이 늘어날 때
    (발표일 posted_at 을 뒤늦게 읽기 시작한 것처럼) 옛 항목이 영영 비어 있으면
    안 되기 때문이다. 실제로 그 일이 있었다 — posted_at 이 없어 사업체노동력조사
    보충이 조용히 건너뛰어졌다.
    """
    index = {k: dict(v) for k, v in existing.items()}
    slot = {k: dict(v) for k, v in index.get(source, {}).items()}
    for period, post in found.items():
        if period not in slot:
            slot[period] = dict(post)
            continue
        for key, value in post.items():
            slot[period].setdefault(key, value)
    index[source] = slot
    return index


def missing_attachments(index: dict, source: str) -> list[str]:
    """첨부를 아직 못 받은 달. 상세 페이지는 이 목록만큼만 두드린다."""
    return sorted(p for p, v in index.get(source, {}).items() if "attachments" not in v)


# ── 네트워크 층 ───────────────────────────────────────────────────────────
# 위의 파서는 HTML 만 받는다. 여기부터가 게시판을 두드리는 부분이다.

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}
MOEL_LIST = "https://www.moel.go.kr/news/enews/report/enewsList.do"
MODS_BOARD = "https://mods.go.kr/board.es"
MODS_PARAMS = {"mid": "a10301030100", "bid": "a103010301",
               "ref_bid": "210,211,11109,11113,11814"}

# 게시판마다 페이지가 어떻게 도는지가 다르다. 고용노동부는 pageUnit 이 먹어서
# 한 페이지에 30건을 받으면 2년치가 들어오고, 국가데이터처는 pageUnit 을 무시하고
# 10건 고정이라 페이지를 넘겨야 한다(고용동향은 그중 3건쯤이다).
BOARDS = {
    "eaps": {"kind": "mods", "title_contains": "고용동향", "pages": 12},
    "est": {"kind": "moel", "keyword": "사업체노동력조사",
            "title_contains": "사업체노동력조사", "pages": 2},
    "ei": {"kind": "moel", "keyword": "고용행정통계",
           "title_contains": "고용행정", "pages": 2},
}

# 첫 실행에서 고용노동부 상세를 60건 두드리면 게시판에도 무리고 그날 수집도 길어진다.
# 한 번에 이만큼만 채우고 나머지는 다음 실행으로 미룬다 — 색인은 숫자가 아니라
# 출처라서 며칠에 걸쳐 채워져도 화면이 틀리지 않는다(그동안 그 달은 게시판 목록으로 간다).
MAX_DETAILS_PER_RUN = 12


def _get(url: str, params: dict, *, tries: int = 3, timeout: int = 60) -> str | None:
    """실패해도 예외를 올리지 않는다. 색인은 있으면 좋은 것이지 수집의 전제가
    아니다 — 게시판이 잠깐 죽었다고 그날 숫자 수집까지 같이 죽으면 안 된다."""
    for attempt in range(tries):
        try:
            res = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            if res.ok:
                return res.text
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    return None


def fetch_list(source: str, *, get: Callable = _get) -> dict[str, dict]:
    """게시판 목록을 넘겨가며 {기간: 게시글} 을 모은다."""
    board = BOARDS[source]
    found: dict[str, dict] = {}
    for page in range(1, board["pages"] + 1):
        if board["kind"] == "moel":
            html = get(MOEL_LIST, {"pageIndex": str(page), "bbs_id": "12",
                                   "searchField": "1", "searchText": board["keyword"],
                                   "pageUnit": "30"})
            page_found = moel_list(html, must_contain=board["title_contains"]) if html else {}
        else:
            html = get(MODS_BOARD, {**MODS_PARAMS, "nPage": str(page)})
            page_found = mods_list(html, must_contain=board["title_contains"]) if html else {}
        if not page_found and html is not None and page > 1:
            break               # 더 넘겨도 안 나온다
        for period, post in page_found.items():
            found.setdefault(period, post)
    return found


def fill_attachments(index: dict, source: str, *,
                     limit: int = MAX_DETAILS_PER_RUN,
                     get: Callable = _get) -> tuple[dict, int]:
    """첨부가 빈 달의 상세를 받아 채운다. 국가데이터처는 목록에서 이미 채워져
    있으므로 여기 걸릴 달이 없다."""
    if BOARDS[source]["kind"] != "moel":
        return index, 0
    out = {k: dict(v) for k, v in index.items()}
    slot = dict(out.get(source, {}))
    filled = 0
    for period in missing_attachments(index, source)[::-1]:      # 최신월부터
        if filled >= limit:
            break
        html = get(slot[period]["url"], {})
        if html is None:
            continue
        slot[period] = {**slot[period], "attachments": moel_attachments(html)}
        filled += 1
    out[source] = slot
    return out, filled


def refresh(existing: dict, *, get: Callable = _get,
            limit: int = MAX_DETAILS_PER_RUN) -> tuple[dict, dict]:
    """색인 한 바퀴. (새 색인, 출처별 요약) 을 돌려준다."""
    index = {k: dict(v) for k, v in (existing or {}).items()}
    summary: dict[str, dict] = {}
    for source in BOARDS:
        before = len(index.get(source, {}))
        found = fetch_list(source, get=get)
        index = merge(index, source, found)
        index, filled = fill_attachments(index, source, limit=limit, get=get)
        summary[source] = {
            "months": len(index.get(source, {})),
            "added": len(index.get(source, {})) - before,
            "attachments_filled": filled,
            "pending": len(missing_attachments(index, source)),
        }
    return index, summary
