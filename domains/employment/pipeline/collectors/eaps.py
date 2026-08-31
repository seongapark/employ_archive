"""경제활동인구조사(고용동향) 수집기.

국가데이터처 고용·노동 보도자료 게시판에서 최신 회차의 xlsx 첨부를 받아
'3.산업(신)' 계열 시트를 읽는다. KOSIS API 를 쓰지 않는 이유는 원계열 월별
산업별 취업자 표가 2024년 12월에서 끊겼기 때문이다(스파이크 9장).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

import requests

from .. import xlsx
from ..models import Attachment, SeriesRecord, make_id
from ..periods import month_rows, squash

KST = timezone(timedelta(hours=9))
BOARD = "https://mods.go.kr/board.es"
BOARD_PARAMS = {"mid": "a10301030100", "bid": "a103010301",
                "ref_bid": "210,211,11109,11113,11814"}
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}

LEVEL_SHEETS = ("3.산업(신)", "3.산업(신) (2)")
DELTA_SHEETS = ("3.산업증감(신)", "3.산업증감(신) (2)")

# 보도자료 열 이름 → 한국표준산업분류 대분류.
# '광공업'과 '사회간접자본 및 기타서비스'는 집계 열이라 일부러 뺐다. 넣으면
# 제조업·서비스업이 이중 계상된다. 광업(B)은 '광공업'에 묶여 단독 제공되지 않는다.
INDUSTRY_COLUMNS: dict[str, str] = {
    "농림어업": "A", "제조업": "C", "전기,가스": "D", "수도,하수폐기물": "E",
    "건설업": "F", "도매및소매업": "G", "운수및창고업": "H", "숙박및음식점업": "I",
    "정보통신업": "J", "금융및보험업": "K", "부동산업": "L", "전문,과학기술": "M",
    "사업시설": "N", "공공행정사회보장": "O", "교육서비스업": "P",
    "보건업및사회복지": "Q", "예술,스포츠여가관련": "R",
    "협회및단체개인서비스": "S", "가구내고용": "T", "국제및외국기관": "U",
}
TOTAL_COLUMN = "전체취업자"

# 성별은 시트가 갈려 있고 취업자 열 하나만 쓴다.
SEX_SHEETS: dict[str, tuple[str, str]] = {
    "M": ("1.남자", "1.남자증감"),
    "F": ("1.여자", "1.여자증감"),
}
SEX_COLUMN = "취업자"

AGE_LEVEL_SHEET = "2.연령계층"
AGE_DELTA_SHEET = "2.연령계층증감"
# 라벨 부분일치용 토큰 → 분류 코드. 수준 시트와 증감 시트의 라벨 형태가
# 다르지만(`취업자$15-29세$계` vs `증감{…}$계$15-29세`) 둘 다 이 토큰을 품는다.
# 15∼19·20∼29·65/70/75세이상은 각각 15∼29·60세이상의 부분집합이라 뺀다 —
# 넣으면 합 불변식이 깨지고 화면에서 이중 계상된다.
AGE_TOKENS: dict[str, str] = {
    "15-29세": "15-29", "30-39세": "30-39", "40-49세": "40-49",
    "50-59세": "50-59", "60세이상": "60+",
}


def _header_labels(rows: list[list[str]]) -> dict[int, str]:
    """헤더가 4~7행에 걸쳐 있으므로(rows[3:7]) 열마다 위아래 조각을 이어붙인다."""
    width = max((len(r) for r in rows[:8]), default=0)
    labels: dict[int, str] = {}
    for col in range(width):
        parts = []
        for row in rows[3:7]:
            if col < len(row) and row[col]:
                parts.append(squash(row[col]))
        if parts:
            labels[col] = "".join(parts)
    return labels


def _numbers(rows: list[list[str]], labels: dict[int, str]) -> dict[str, dict[str, float]]:
    """{기간: {열이름: 값}}"""
    table: dict[str, dict[str, float]] = {}
    for period, row in month_rows(rows):
        bucket = table.setdefault(period, {})
        for col, name in labels.items():
            if col >= len(row):
                continue
            raw = (row[col] or "").replace(",", "").strip()
            if not raw:
                continue
            try:
                bucket[name] = round(float(raw), 1)
            except ValueError:
                continue
    return table


def _collect_sheets(data: bytes, names) -> dict[str, dict[str, float]]:
    merged: dict[str, dict[str, float]] = {}
    for name in names:
        rows = xlsx.read_sheet(data, name)
        for period, values in _numbers(rows, _header_labels(rows)).items():
            merged.setdefault(period, {}).update(values)
    return merged


def _by_token(data: bytes, sheet: str) -> dict[str, dict[str, float]]:
    """{기간: {분류코드: 값}} — 라벨에 AGE_TOKENS 가 들어간 열만."""
    rows = xlsx.read_sheet(data, sheet)
    labels = _header_labels(rows)
    picked = {col: code for col, label in labels.items()
              for token, code in AGE_TOKENS.items() if token in label}
    out: dict[str, dict[str, float]] = {}
    for period, row in month_rows(rows):
        bucket = out.setdefault(period, {})
        for col, code in picked.items():
            if col >= len(row):
                continue
            raw = (row[col] or "").replace(",", "").strip()
            if not raw:
                continue
            try:
                bucket[code] = round(float(raw), 1)
            except ValueError:
                continue
    return out


def parse(data: bytes, *, released_at: date, release_url: str,
          attachments: list[Attachment], collected_at: datetime) -> list[SeriesRecord]:
    levels = _collect_sheets(data, LEVEL_SHEETS)
    deltas = _collect_sheets(data, DELTA_SHEETS)

    records: list[SeriesRecord] = []
    for period, values in levels.items():
        delta = deltas.get(period, {})

        if TOTAL_COLUMN in values:
            records.append(SeriesRecord(
                id=make_id("eaps", period, "total", None), source="eaps",
                breakdown="total", category=None, period=period,
                value=values[TOTAL_COLUMN], yoy=delta.get(TOTAL_COLUMN),
                released_at=released_at, release_url=release_url,
                attachments=attachments, collected_at=collected_at,
            ))

        for column, code in INDUSTRY_COLUMNS.items():
            if column not in values:
                continue
            records.append(SeriesRecord(
                id=make_id("eaps", period, "industry", code), source="eaps",
                breakdown="industry", category=code, period=period,
                value=values[column], yoy=delta.get(column),
                released_at=released_at, release_url=release_url,
                attachments=attachments, collected_at=collected_at,
            ))

    def emit(breakdown: str, code: str, period: str,
             value: float, yoy: float | None) -> None:
        records.append(SeriesRecord(
            id=make_id("eaps", period, breakdown, code), source="eaps",
            breakdown=breakdown, category=code, period=period,
            value=value, yoy=yoy,
            released_at=released_at, release_url=release_url,
            attachments=attachments, collected_at=collected_at,
        ))

    for code, (level_sheet, delta_sheet) in SEX_SHEETS.items():
        levels_s = _collect_sheets(data, (level_sheet,))
        deltas_s = _collect_sheets(data, (delta_sheet,))
        for period, values in levels_s.items():
            if SEX_COLUMN not in values:
                continue
            emit("sex", code, period, values[SEX_COLUMN],
                 deltas_s.get(period, {}).get(SEX_COLUMN))

    age_levels = _by_token(data, AGE_LEVEL_SHEET)
    age_deltas = _by_token(data, AGE_DELTA_SHEET)
    for period, values in age_levels.items():
        for code, value in values.items():
            emit("age", code, period, value, age_deltas.get(period, {}).get(code))

    return records


def check_coverage(records: list[SeriesRecord]) -> None:
    """최신월에 기대한 산업과 전체 행이 다 왔는지 본다.

    헤더 철자가 조금만 달라져도 그 열은 INDUSTRY_COLUMNS 에 안 걸려 조용히
    빠진다. 빠진 산업은 화면에서 그냥 없는 칸으로 보일 뿐 아무 흔적도 남기지 않는다.
    TOTAL_COLUMN 철자가 바뀌면 총괄 행 자체가 통째로 빠질 수 있다 — 산업별
    표는 가득 찬 채 총괄 화면만 빈다.
    """
    if not records:
        raise ValueError("수집된 레코드가 없다")
    latest = max(r.period for r in records)
    if not any(r.period == latest and r.breakdown == "total" for r in records):
        raise ValueError(f"{latest} 에 전체 취업자 행이 없다")
    got = {r.category for r in records
           if r.period == latest and r.breakdown == "industry"}
    missing = set(INDUSTRY_COLUMNS.values()) - got
    if missing:
        raise ValueError(f"{latest} 에 빠진 산업 대분류: {sorted(missing)}")

    for breakdown, expected in (("sex", set(SEX_SHEETS)),
                                ("age", set(AGE_TOKENS.values()))):
        got = {r.category for r in records
               if r.period == latest and r.breakdown == breakdown}
        missing = expected - got
        if missing:
            name = "성별" if breakdown == "sex" else "연령"
            raise ValueError(f"{latest} 에 빠진 {name} 분류: {sorted(missing)}")


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
    html = requests.get(BOARD, params=BOARD_PARAMS, headers=HEADERS,
                        timeout=30).text.replace("&amp;", "&")
    m = re.search(
        r'href="(/boardDownload\.es\?[^"]*?list_no=(\d+)[^"]*)"\s+class="bf_xlsx">'
        r'<span class="hdn">([^<]*?고용동향)의 xlsx파일', html)
    if m is None:
        raise ValueError("게시판에서 고용동향 xlsx 첨부를 찾지 못했다")
    href, list_no, title = m.group(1), m.group(2), m.group(3)

    posted = re.search(
        rf"list_no={list_no}.{{0,4000}}?<strong>게시일</strong><span>(\d{{4}}-\d{{2}}-\d{{2}})</span>",
        html, re.S)
    if posted is None:
        raise ValueError(f"게시일을 찾지 못했다: {title}")
    released_at = date.fromisoformat(posted.group(1))

    view_url = (f"https://mods.go.kr/board.es?mid=a10301030100&bid=a103010301"
                f"&list_no={list_no}&act=view")
    data = requests.get("https://mods.go.kr" + href,
                        headers={**HEADERS, "Referer": BOARD}, timeout=90).content
    attachments = [Attachment(type="xlsx", url="https://mods.go.kr" + href)]
    return title, released_at, view_url, data, attachments


def collect(today: date) -> list[SeriesRecord]:
    title, released_at, view_url, data, attachments = latest_issue()
    records = parse(data, released_at=released_at, release_url=view_url,
                    attachments=attachments, collected_at=datetime.now(KST))
    check_coverage(records)
    check_freshness(records, today)
    return records
