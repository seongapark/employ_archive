"""고용행정 통계로 본 노동시장 동향 수집기.

고용노동부 보도자료 게시판에서 최신 회차의 hwpx 첨부를 받아 상시가입자
수준·증감 표를 읽는다. 표는 인덱스가 아니라 헤더 내용으로 찾는다 —
회차마다 표 개수가 달라 인덱스가 밀린다.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

import requests

from .. import hwpx
from ..models import Attachment, SeriesRecord, make_id
from ..periods import month_rows, squash

KST = timezone(timedelta(hours=9))
LIST_URL = "https://www.moel.go.kr/news/enews/report/enewsList.do"
VIEW_URL = "https://www.moel.go.kr/news/enews/report/enewsView.do"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}
SEARCH = {"pageIndex": "1", "bbs_id": "12", "searchField": "1",
          "searchText": "고용행정통계", "pageUnit": "30"}

HEADER_KEYS = ("전산업", "농림어업", "제조업")

# 열 위치 → 한국표준산업분류 대분류.
# 헤더가 0행·1행에 나뉘고 병합셀이 섞여 이름으로 짜맞추기 어렵다. 위치로 읽고
# check_layout 이 이름을 검증한다 — 서식이 바뀌면 조용히 틀리는 대신 실패한다.
#
# 앞 표(11열): 0=월 1=전산업 2=농림어업 3=제조업 4=전기·가스 5=건설업
#              6=서비스업(집계) 7=수도·하수·폐기업 8=도소매 9=운수창고 10=숙박음식
LEAD_COLUMNS: dict[int, str] = {
    2: "A", 3: "C", 4: "D", 5: "F", 7: "E", 8: "G", 9: "H", 10: "I",
}
# 이어지는 표(12열): 0=월 1=정보통신업 … 10=협회·개인서비스 11=기타*(집계)
CONT_COLUMNS: dict[int, str] = {
    1: "J", 2: "K", 3: "L", 4: "M", 5: "N", 6: "O", 7: "P", 8: "Q", 9: "R", 10: "S",
}
TOTAL_COLUMN = 1

# 6(서비스업)과 11(기타*)은 일부러 뺐다. 집계 열이라 넣으면 이중 계상된다.

_LEAD_HEADER = {1: "전산업", 2: "농림어업", 3: "제조업", 6: "서비스업"}
_CONT_HEADER = {1: "정보통신업", 8: "보건복지", 11: "기타*"}


def check_layout(lead: list[list[str]], cont: list[list[str]]) -> None:
    # 비교 전에 공백을 지운다 — 헤더가 두 줄로 접히면 '정보 통신업' 처럼 온다.
    for col, expected in _LEAD_HEADER.items():
        got = lead[0][col] if col < len(lead[0]) else ""
        if squash(got) != expected:
            raise ValueError(f"앞 표의 열 배치가 바뀌었다: {col}번은 {expected!r} 여야 하는데 {got!r}")
    header = cont[1] if len(cont) > 1 else []
    for col, expected in _CONT_HEADER.items():
        got = header[col] if col < len(header) else ""
        if squash(got) != expected:
            raise ValueError(f"이어지는 표의 열 배치가 바뀌었다: {col}번은 {expected!r} 여야 하는데 {got!r}")


def _num(cell: str) -> float | None:
    raw = (cell or "").replace(",", "").strip()
    if not re.fullmatch(r"-?\d+(\.\d+)?", raw):
        return None
    return float(raw)


def _flat(cells) -> str:
    """헤더 비교용. 공백을 지운다.

    hwpx 리더가 셀 안 문단을 공백으로 잇기 때문에 두 줄로 접힌 헤더가
    '농림 어업', '정보 통신업' 처럼 나온다. 공백을 그대로 두고 매칭하면
    상시가입자 표를 놓치고 뒤쪽 구직급여 표를 집는다.

    셀 안 공백만 지우고 셀 사이는 띄운다. 전부 이어붙이면 키워드가 두 셀
    경계를 걸쳐 가짜로 매칭될 수 있다 — 앞 셀 끝 '산' + 뒤 셀 시작 '업'.
    """
    return " ".join(squash(c) for c in cells)


def find_tables(tables) -> tuple[list, list, list, list]:
    cand = [
        i for i, g in enumerate(tables)
        if g and len(g[0]) > 5 and all(k in _flat(g[0]) for k in HEADER_KEYS)
    ]
    if len(cand) < 2:
        raise ValueError(f"수준·증감 표를 찾지 못했다 (후보 {cand})")
    # 문서 안에서 상시가입자 표(수준·증감)가 구직급여 표보다 먼저 나온다는
    # 순서 가정이다. 이게 깨지면 check_layout 은 못 잡고(헤더가 같으므로)
    # 아래 크기 검증만이 뒤바뀜을 막는다.
    level_i, delta_i = cand[0], cand[1]

    level, delta = tables[level_i], tables[delta_i]
    lv, dv = _num(level[-1][1]), _num(delta[-1][1])
    # 헤더가 같아 순서로만 구분된다. 크기로 뒤바뀜을 잡는다.
    if lv is None or lv < 10000:
        raise ValueError(f"수준 표의 전산업이 이상하다: {lv}")
    if dv is None or abs(dv) >= 1000:
        raise ValueError(f"증감 표의 전산업이 이상하다: {dv}")

    return level, tables[level_i + 1], delta, tables[delta_i + 1]


def headline_delta(tables) -> float | None:
    """p1 <주요 특징> 박스의 '27만 7천명 증가' 를 천명 단위 부호값으로."""
    for g in tables:
        text = " ".join(" ".join(r) for r in g)
        if "주요 특징" not in text and "고용보험" not in text:
            continue
        m = re.search(r"고용보험\s*가입자는\s*([\d,]+)\s*만\s*([\d,]+)?\s*천?\s*명[이가]?\s*(증가|감소)", text)
        if m is None:
            m2 = re.search(r"고용보험\s*가입자는\s*([\d,]+)\s*천\s*명[이가]?\s*(증가|감소)", text)
            if m2 is None:
                continue
            value = float(m2.group(1).replace(",", ""))
            return value if m2.group(2) == "증가" else -value
        man = float(m.group(1).replace(",", ""))
        cheon = float((m.group(2) or "0").replace(",", ""))
        value = man * 10 + cheon
        return value if m.group(3) == "증가" else -value
    return None


TOTAL_KEY = "__total__"


def _series_by_period(lead, cont) -> dict[str, dict[str, float]]:
    """{기간: {KSIC 코드 또는 TOTAL_KEY: 값}}.

    마지막 행만 읽지 않는다. 이 표는 28개월치를 담고 있고, 한 회차에서 전 기간을
    가져와야 24개월 시계열이 첫 수집만으로 채워진다. 최신월만 읽으면 24개월을
    모으는 데 2년이 걸린다.
    """
    out: dict[str, dict[str, float]] = {}

    for period, row in month_rows(lead):
        bucket = out.setdefault(period, {})
        if TOTAL_COLUMN < len(row):
            value = _num(row[TOTAL_COLUMN])
            if value is not None:
                bucket[TOTAL_KEY] = value
        for col, code in LEAD_COLUMNS.items():
            if col < len(row):
                value = _num(row[col])
                if value is not None:
                    bucket[code] = value

    for period, row in month_rows(cont):
        bucket = out.setdefault(period, {})
        for col, code in CONT_COLUMNS.items():
            if col < len(row):
                value = _num(row[col])
                if value is not None:
                    bucket[code] = value

    return out


def parse(data: bytes, *, released_at: date, release_url: str,
          attachments: list[Attachment], collected_at: datetime) -> list[SeriesRecord]:
    tables = hwpx.tables(data)
    level_a, level_b, delta_a, delta_b = find_tables(tables)
    check_layout(level_a, level_b)
    check_layout(delta_a, delta_b)

    levels = _series_by_period(level_a, level_b)
    deltas = _series_by_period(delta_a, delta_b)
    if not levels:
        raise ValueError("수준 표에서 월 행을 찾지 못했다")

    # 문서가 스스로 검증 대조점을 갖고 있다 — 최신월 총량 증감이 요약문에 문장으로
    # 나온다. 어긋나면 서식이 바뀐 것이므로 조용히 틀린 숫자를 넣지 않고 실패한다.
    #
    # 요약문을 못 읽는 것도 실패다. 정규식이 안 맞는다는 건 서식이 바뀌었다는
    # 뜻이고, 그게 바로 이 대조가 막으려는 상황이다. 여기서 넘어가면 가드가
    # 정작 위험할 때만 침묵하게 된다.
    latest = max(levels)
    stated = headline_delta(tables)
    if stated is None:
        raise ValueError("주요 특징 박스에서 총량 증감 문장을 읽지 못했다 — 서식이 바뀌었을 수 있다")

    total_delta = deltas.get(latest, {}).get(TOTAL_KEY)
    if total_delta is None:
        raise ValueError(f"{latest} 증감표에 전산업 값이 없다")

    if abs(stated - total_delta) > 1.0:
        raise ValueError(
            f"요약문과 증감표가 대조에 실패했다: 요약 {stated} vs 표 {total_delta}")

    records: list[SeriesRecord] = []
    for period, values in levels.items():
        delta = deltas.get(period, {})
        if TOTAL_KEY in values:
            records.append(SeriesRecord(
                id=make_id("ei", period, "total", None), source="ei",
                breakdown="total", category=None, period=period,
                value=values[TOTAL_KEY], yoy=delta.get(TOTAL_KEY),
                released_at=released_at, release_url=release_url,
                attachments=attachments, collected_at=collected_at,
            ))
        for code, value in values.items():
            if code == TOTAL_KEY:
                continue
            records.append(SeriesRecord(
                id=make_id("ei", period, "industry", code), source="ei",
                breakdown="industry", category=code, period=period,
                value=value, yoy=delta.get(code),
                released_at=released_at, release_url=release_url,
                attachments=attachments, collected_at=collected_at,
            ))
    return records


EXPECTED_CODES = set("ACDEFGHIJKLMNOPQRS")


def check_coverage(records: list[SeriesRecord]) -> None:
    """최신월에 기대한 대분류와 전체 행이 다 왔는지 본다.

    열 위치가 밀리거나 값이 비면 그 산업이 조용히 빠진다. 화면에서는 그냥
    없는 칸으로 보일 뿐 아무 흔적도 남지 않는다. 형제 수집기 둘도 같은 가드를 갖는다.
    """
    if not records:
        raise ValueError("수집된 레코드가 없다")
    latest = max(r.period for r in records)
    if not any(r.period == latest and r.breakdown == "total" for r in records):
        raise ValueError(f"{latest} 에 전체 상시가입자 행이 없다")
    got = {r.category for r in records
           if r.period == latest and r.breakdown == "industry"}
    missing = EXPECTED_CODES - got
    if missing:
        raise ValueError(f"{latest} 에 빠진 산업 대분류: {sorted(missing)}")


MAX_MONTHS_BEHIND = 2      # 전월 기준으로 매월 공표된다 (sources.json 의 release_rule)


def check_freshness(records: list[SeriesRecord], today: date) -> None:
    """최신월이 오늘로부터 너무 뒤처졌으면 실패시킨다.

    파싱이 조용히 잘리면 check_coverage 는 못 잡는다 — latest 를 자기가 읽은
    것에서 뽑으므로 골대가 같이 움직인다. 발표 주기를 아는 쪽은 여기뿐이다.
    """
    latest = max(r.period for r in records)
    year, month = (int(x) for x in latest.split("-"))
    behind = (today.year - year) * 12 + (today.month - month)
    if behind > MAX_MONTHS_BEHIND:
        raise ValueError(
            f"최신 기간이 {latest} 로 {behind}개월 뒤처졌다 — 수집이 잘렸거나 공표가 멈췄다")


def latest_issue() -> tuple[str, date, str, bytes, list[Attachment]]:
    html = requests.post(LIST_URL, data=SEARCH,
                         headers={**HEADERS, "Referer": LIST_URL}, timeout=30).text
    m = re.search(r'news_seq=(\d+)[^>]*>(.*?)</a>', html, re.S)
    if m is None:
        raise ValueError("게시판에서 회차를 찾지 못했다")
    seq = m.group(1)
    title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(2))).strip()
    if "고용행정" not in title:
        raise ValueError(f"고용행정통계 회차가 아니다: {title}")

    view = f"{VIEW_URL}?news_seq={seq}"
    detail = requests.get(view, headers=HEADERS, timeout=30).text.replace("&amp;", "&")
    link = re.search(r'href="(/common/downloadFile\.do\?[^"]*file_ext=hwpx)"', detail)
    if link is None:
        raise ValueError(f"hwpx 첨부를 찾지 못했다: {title}")

    # 페이지 아무 데서나 날짜 모양을 찾으면 안 된다 — 스크립트 버전, 바닥글의
    # 무관한 날짜에 걸릴 수 있다. 상세 화면의 '등록일' 라벨에 붙은 값만 취한다.
    posted = re.search(r"<dt>등록일</dt>\s*<dd>\s*(\d{4})-(\d{2})-(\d{2})", detail)
    if posted is None:
        raise ValueError(f"등록일을 찾지 못했다: {title}")
    released_at = date(int(posted.group(1)), int(posted.group(2)), int(posted.group(3)))

    data = requests.get("https://www.moel.go.kr" + link.group(1),
                        headers={**HEADERS, "Referer": view}, timeout=120).content
    attachments = [Attachment(type="hwpx", url="https://www.moel.go.kr" + link.group(1))]
    return title, released_at, view, data, attachments


def collect(today: date) -> list[SeriesRecord]:
    title, released_at, view, data, attachments = latest_issue()
    records = parse(data, released_at=released_at, release_url=view,
                    attachments=attachments, collected_at=datetime.now(KST))
    check_coverage(records)
    check_freshness(records, today)
    return records
