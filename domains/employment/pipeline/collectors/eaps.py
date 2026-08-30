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


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _header_labels(rows: list[list[str]]) -> dict[int, str]:
    """헤더가 4~6행에 걸쳐 있으므로 열마다 위아래 조각을 이어붙인다."""
    width = max((len(r) for r in rows[:8]), default=0)
    labels: dict[int, str] = {}
    for col in range(width):
        parts = []
        for row in rows[3:7]:
            if col < len(row) and row[col]:
                parts.append(_norm(row[col]))
        if parts:
            labels[col] = "".join(parts)
    return labels


_MONTH_START = re.compile(r"^(\d{4})\.(\d{1,2})$")
_MONTH_ONLY = re.compile(r"^(\d{1,2})$")


def _period_rows(rows: list[list[str]]) -> list[tuple[str, list[str]]]:
    """월별 행만 골라 (YYYY-MM, 행) 으로 바꾼다.

    첫 칸에는 연평균(단독 4자리, 예: '2025'), 분기('2025.1/4'), 월별 값이
    한 표에 섞여 있다. 월은 연도가 바뀌는 시작 행에서만 'YYYY.  M' 처럼
    연도를 달고, 그 뒤로는 숫자만 온다 — 그래서 4자리 단독 행을 연도로
    오인해 이어붙이면 월 시작 행(연도가 붙은 행)은 정규식에 안 걸려 버려지고,
    그 다음 숫자만 있는 행들은 훨씬 전에 마지막으로 봤던 연평균 연도에
    잘못 붙는다 — 다음 해로 넘어간 월이 이전 해로 주저앉는다. 빈 행은 표의
    블록 경계이므로 연도 문맥을 끊는다.
    """
    out: list[tuple[str, list[str]]] = []
    year: str | None = None
    for row in rows:
        first = _norm(row[0]) if row else ""
        if not first:
            year = None
            continue
        m = _MONTH_START.fullmatch(first)
        if m:
            year, month = m.group(1), int(m.group(2))
            if 1 <= month <= 12:
                out.append((f"{year}-{month:02d}", row))
            continue
        m = _MONTH_ONLY.fullmatch(first)
        if year and m:
            month = int(m.group(1))
            if 1 <= month <= 12:
                out.append((f"{year}-{month:02d}", row))
    return out


def _numbers(rows: list[list[str]], labels: dict[int, str]) -> dict[str, dict[str, float]]:
    """{기간: {열이름: 값}}"""
    table: dict[str, dict[str, float]] = {}
    for period, row in _period_rows(rows):
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
    return records


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
    return parse(data, released_at=released_at, release_url=view_url,
                 attachments=attachments, collected_at=datetime.now(KST))
