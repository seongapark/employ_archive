"""경제활동인구조사(고용동향) 수집기.

국가데이터처 고용·노동 보도자료 게시판에서 최신 회차의 xlsx 첨부를 받아
'3.산업(신)' 계열 시트를 읽는다. KOSIS API 를 쓰지 않는 이유는 원계열 월별
산업별 취업자 표가 2024년 12월에서 끊겼기 때문이다(스파이크 9장).
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta, timezone

from ..http import SESSION
from .. import xlsx
from ..models import Attachment, SeriesRecord, make_id
from ..periods import month_rows, squash
# 게시판 주소는 releases.py 한 곳에만 둔다 — 그쪽이 같은 게시판의 목록을 읽고,
# 두 벌로 두면 한쪽만 고쳐져 목록과 원문 링크가 어긋난다(주소 근거는 그 주석).
from ..releases import MODS_BOARD as BOARD, MODS_PARAMS as BOARD_PARAMS, mods_view_url

KST = timezone(timedelta(hours=9))
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
    html = SESSION.get(BOARD, params=BOARD_PARAMS, headers=HEADERS,
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

    view_url = mods_view_url(list_no)
    data = SESSION.get("https://mods.go.kr" + href,
                        headers={**HEADERS, "Referer": BOARD}, timeout=90).content
    attachments = [Attachment(type="xlsx", url="https://mods.go.kr" + href)]
    return title, released_at, view_url, data, attachments


# ── 15~34세 (KOSIS) ─────────────────────────────────────────────────────
#
# 보도자료 xlsx 에는 15~34세 시트가 없다(1529·3039 뿐이라 합쳐서 만들 수도
# 없다). KOSIS 의 같은 경활 표(check_kosis 가 대조하는 DT_1DA7002S)에 연령
# 코드 `1534` 가 있어 여덟 지표를 그대로 받는다. 증감 시트가 없으므로 yoy 는
# 12개월 전 값과의 차이다 — 비율은 반올림된 값끼리 빼므로 0.1 흔들릴 수 있다.
KOSIS_API = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
KOSIS_TABLE = {"orgId": "101", "tblId": "DT_1DA7002S"}
KOSIS_AGE_1534 = ("1534", "15 - 34세")
KOSIS_AGE_1529 = ("75", "15 - 29세")
# 항목 코드 → (KOSIS 항목 이름, 지표). 이름도 맞춘다 — 코드는 그대로인데 항목이
# 바뀌면 조용히 다른 숫자를 싣게 된다.
KOSIS_ITEMS = {
    "T10": ("인구", "population"),
    "T20": ("경제활동인구", "labor_force"),
    "T30": ("취업자", "headcount"),
    "T40": ("실업자", "unemployed"),
    "T50": ("비경제활동인구", "inactive"),
    "T60": ("경제활동참가율", "participation_rate"),
    "T80": ("실업률", "unemployment_rate"),
    "T90": ("고용률", "employment_rate"),
}


def fetch_kosis_ages(api_key: str, months: int = 40, get=SESSION.get) -> list[dict]:
    """15~34세와 대조용 15~29세. 25개월 그림의 첫 달까지 yoy 가 붙도록 넉넉히."""
    params = {"method": "getList", "apiKey": api_key, "format": "json", "jsonVD": "Y",
              "prdSe": "M", "newEstPrdCnt": str(months), "itmId": " ".join(KOSIS_ITEMS),
              "objL1": f"{KOSIS_AGE_1534[0]} {KOSIS_AGE_1529[0]}", **KOSIS_TABLE}
    payload = get(KOSIS_API, params=params, timeout=60).json()
    if isinstance(payload, dict):
        raise ValueError(f"KOSIS 오류(15~34세): {payload.get('errMsg', payload)}")
    return payload


def _kosis_levels(rows: list[dict], age: tuple[str, str]) -> dict[str, dict[str, float]]:
    """{기간: {지표: 값}}."""
    code, name = age
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        if str(row.get("C1")) != code:
            continue
        if str(row.get("C1_NM", "")).strip() != name:
            raise ValueError(f"KOSIS 연령 {code} 이름이 '{row.get('C1_NM')}' 이다 — '{name}' 이어야 한다")
        item = KOSIS_ITEMS.get(str(row.get("ITM_ID")))
        if item is None:
            continue
        if row.get("ITM_NM") != item[0]:
            raise ValueError(f"KOSIS 항목 {row.get('ITM_ID')} 이름이 '{row.get('ITM_NM')}' 이다 "
                             f"— '{item[0]}' 이어야 한다")
        try:
            value = round(float(str(row.get("DT")).replace(",", "")), 1)
        except (TypeError, ValueError):
            continue
        prd = str(row.get("PRD_DE", ""))
        out.setdefault(f"{prd[:4]}-{prd[4:6]}", {})[item[1]] = value
    return out


def parse_kosis_1534(rows: list[dict], *, xlsx_data: bytes, released_at: date,
                     release_url: str, attachments: list[Attachment],
                     collected_at: datetime) -> list[SeriesRecord]:
    # 15~29세는 xlsx 와 KOSIS 양쪽에 있다. 둘이 같은 달에 같은 값을 말해야
    # 이 표·코드가 아직 우리가 아는 그 경활 표다. 어긋나면 15~34세를 싣지 않는다.
    kosis_1529 = _kosis_levels(rows, KOSIS_AGE_1529)
    xlsx_1529 = _totals_sheet(xlsx_data, "1529")
    shared = sorted(set(kosis_1529) & set(xlsx_1529))
    if not shared:
        raise ValueError("KOSIS 와 xlsx 가 함께 가진 15~29세 달이 없다")
    period = shared[-1]
    for series, value in kosis_1529[period].items():
        if abs(xlsx_1529[period].get(series, value) - value) > 0.2:
            raise ValueError(f"{period} 15~29세 {series}: KOSIS {value} vs xlsx "
                             f"{xlsx_1529[period][series]} — 표가 바뀌었는지 확인")

    levels = _kosis_levels(rows, KOSIS_AGE_1534)
    records: list[SeriesRecord] = []
    for period in contiguous_tail(levels):
        year, month = period.split("-")
        prior = levels.get(f"{int(year) - 1}-{month}", {})
        for series, value in levels[period].items():
            before = prior.get(series)
            records.append(SeriesRecord(
                id=make_id("eaps", period, "scope", "15-34", series=series),
                source="eaps", series=series, breakdown="scope", category="15-34",
                period=period, value=value, unit=TOTAL_UNITS[series],
                yoy=None if before is None else round(value - before, 1),
                released_at=released_at, release_url=release_url,
                attachments=attachments, collected_at=collected_at,
            ))
    return records


def collect(today: date) -> list[SeriesRecord]:
    title, released_at, view_url, data, attachments = latest_issue()
    now = datetime.now(KST)
    records = parse(data, released_at=released_at, release_url=view_url,
                    attachments=attachments, collected_at=now)
    # 두 검사는 취업자수 계열을 두고 쓰인 것이다. 총괄 지표를 섞은 뒤에 돌리면
    # `있어야 할 산업 21개` 같은 셈이 어긋난다 — 그래서 먼저 돌리고 뒤에 얹는다.
    check_coverage(records)
    check_freshness(records, today)
    records += parse_totals(data, released_at=released_at, release_url=view_url,
                            attachments=attachments, collected_at=now)
    api_key = os.environ.get("KOSIS_API_KEY", "").strip()
    if not api_key:
        raise ValueError("KOSIS_API_KEY 가 없다 — 15~34세를 받을 수 없다")
    return records + parse_kosis_1534(
        fetch_kosis_ages(api_key), xlsx_data=data, released_at=released_at,
        release_url=view_url, attachments=attachments, collected_at=now)


# ── 총괄 지표 (1.전체 · 1564 · 1529) ──────────────────────────────────────
#
# 세 시트의 레이아웃이 완전히 같다 — 인구·경제활동인구·취업자·실업자·비경활·
# 참가율·고용률·실업률 여덟 열이고, 증감 시트도 같은 배치다. 그래서 파서 하나가
# (범위, 수준시트, 증감시트) 셋을 돌면 끝난다.
#
# 열은 **위치가 아니라 이름으로** 찾는다. 위치로 집으면 국가데이터처가 열을
# 하나 끼워 넣는 날 고용률 자리에서 실업률을 읽고도 아무 일 없이 지나간다.

TOTAL_SCOPES = (
    # (breakdown, category, 수준 시트, 증감 시트)
    ("total", None, "1.전체", "1.전체증감"),
    ("scope", "15-64", "1564", "1564증감"),
    ("scope", "15-29", "1529", "1529증감"),
)

# 비율은 unit 이 %, 그 yoy 는 증감량이 아니라 %p 차이다.
TOTAL_UNITS = {
    "population": "천명", "labor_force": "천명", "headcount": "천명",
    "unemployed": "천명", "inactive": "천명",
    "participation_rate": "%", "employment_rate": "%", "unemployment_rate": "%",
}


def total_series_of(label: str) -> str | None:
    """열 이름 → 지표. 순서가 중요하다 — `비경제활동인구` 는 `경제활동인구` 를
    품고 있고, 증감 시트의 실업률 열에는 단위 주석이 통째로 붙어 있다
    (`(단위:전년대비,천명)실업률(%p)`)."""
    if "참가율" in label:
        return "participation_rate"
    if "고용률" in label:
        return "employment_rate"
    if "실업률" in label:
        return "unemployment_rate"
    if label == "실업자":
        return "unemployed"
    if label == "비경제활동인구":
        return "inactive"
    if label == "경제활동인구":
        return "labor_force"
    if label == "취업자":
        return "headcount"
    if label in ("15세이상인구", "인구"):
        return "population"
    return None


def _totals_sheet(data: bytes, sheet: str) -> dict[str, dict[str, float]]:
    """{기간: {지표: 값}}. 여덟 지표가 다 안 잡히면 형식이 바뀐 것이므로 멈춘다."""
    rows = xlsx.read_sheet(data, sheet)
    labels = _header_labels(rows)
    picked = {col: s for col, label in labels.items()
              if (s := total_series_of(label)) is not None}
    missing = set(TOTAL_UNITS) - set(picked.values())
    if missing:
        raise ValueError(f"{sheet} 에서 못 찾은 지표: {sorted(missing)} (열: {labels})")

    out: dict[str, dict[str, float]] = {}
    for period, row in month_rows(rows):
        bucket = out.setdefault(period, {})
        for col, series in picked.items():
            if col >= len(row):
                continue
            raw = (row[col] or "").replace(",", "").strip()
            if not raw:
                continue
            try:
                bucket[series] = round(float(raw), 1)
            except ValueError:
                continue
    return out


def contiguous_tail(periods) -> list[str]:
    """끝에서부터 한 달씩 이어지는 구간만.

    회차마다 앞쪽 몇 행은 연도별 8월이라 띄엄띄엄하다(2021-08, 2022-08, …).
    그대로 시계열로 그리면 2년 간격이 한 칸으로 붙어 급변한 것처럼 보인다.
    """
    ordered = sorted(periods)
    if not ordered:
        return []
    run = [ordered[-1]]
    for period in reversed(ordered[:-1]):
        year, month = int(run[0][:4]), int(run[0][5:7]) - 1
        if month < 1:
            year, month = year - 1, 12
        if period != f"{year}-{month:02d}":
            break
        run.insert(0, period)
    return run


def total_headcount_matches(data: bytes) -> bool:
    """`1.전체` 와 `3.산업(신)` 이 같은 취업자수를 말하는가.

    어긋나면 두 시트를 섞어 쓰고 있다는 뜻이고, 화면의 카드와 지표가 서로 다른
    숫자를 말하게 된다. 그래서 총괄 지표에서는 전체 취업자수를 다시 내지 않고
    (산업 시트가 주인이다) 대신 이걸로 확인한다.
    """
    totals = _totals_sheet(data, "1.전체")
    industry = _collect_sheets(data, LEVEL_SHEETS)
    shared = set(totals) & set(industry)
    return bool(shared) and all(
        totals[p].get("headcount") == industry[p].get(TOTAL_COLUMN) for p in shared)


def parse_totals(data: bytes, *, released_at: date, release_url: str,
                 attachments: list[Attachment],
                 collected_at: datetime) -> list[SeriesRecord]:
    """경제활동인구조사 총괄 지표. 취업자수 계열(parse)과 겹치지 않는다."""
    # 교차 확인은 적어만 두면 소용없다. 어긋난 채로 통과시키면 카드는 산업
    # 시트의 취업자수를, 지표는 총괄 시트의 숫자를 말하게 되고 둘이 다른데도
    # 화면은 아무 말을 하지 않는다.
    if not total_headcount_matches(data):
        raise ValueError("`1.전체` 와 `3.산업(신)` 의 취업자수가 어긋난다")

    records: list[SeriesRecord] = []
    for breakdown, category, level_sheet, delta_sheet in TOTAL_SCOPES:
        levels = _totals_sheet(data, level_sheet)
        deltas = _totals_sheet(data, delta_sheet)
        for period in contiguous_tail(levels):
            delta = deltas.get(period, {})
            for series, value in levels[period].items():
                # 전체 취업자수는 산업 시트가 만든다. 여기서 또 내면 같은 id 를
                # 두 곳이 쓰게 되고, 언젠가 둘이 어긋나면 어느 쪽이 이겼는지
                # 아무도 모른다(total_headcount_matches 가 둘의 일치를 지킨다).
                if series == "headcount" and breakdown == "total":
                    continue
                records.append(SeriesRecord(
                    id=make_id("eaps", period, breakdown, category, series=series),
                    source="eaps", series=series, breakdown=breakdown,
                    category=category, period=period,
                    value=value, unit=TOTAL_UNITS[series], yoy=delta.get(series),
                    released_at=released_at, release_url=release_url,
                    attachments=attachments, collected_at=collected_at,
                ))
    return records
