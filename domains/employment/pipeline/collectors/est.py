"""사업체노동력조사 수집기 (KOSIS OpenAPI).

세 출처 중 유일하게 API 로 얻는다. 표는 대분류와 중분류가 한 축에 섞여
90여 항목으로 나오므로 코드로 대분류만 걸러낸다.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta, timezone

import requests

from .. import hwpx
from ..models import Attachment, SeriesRecord, make_id
from ..periods import squash

KST = timezone(timedelta(hours=9))
API = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
ORG_ID = "118"
TBL_ID = "DT_118N_MON066"
STAT_URL = f"https://kosis.kr/statHtml/statHtml.do?orgId={ORG_ID}&tblId={TBL_ID}"

# 규모(C2) 는 '전체'만 쓴다. 코드는 KOSIS 메타데이터의 고정 식별자다.
SIZE_TOTAL_CODE = "13102732820SIZES.0"
# 항목(ITM) 도 '종사자_전체' 하나만 쓴다. itmId=ALL, objL2=ALL 로 받으면
# 월당 16,650행(90 산업 x 5 규모 x 36 항목)이 나와 26개월이면 40만 행을
# 넘어 KOSIS 의 4만 행 상한(err=31)에 걸린다. 필요한 조합만 서버에 요청한다.
ITEM_TOTAL_EMPLOYEES_CODE = "16118MF_1"

# 대분류는 코드가 알파벳으로 끝나고(...11SD), 중분류는 뒤에 숫자가 붙는다(...11SD35).
# 이름(C1_NM)은 코드범위 표기가 흔들려 판별 기준으로 못 쓴다.
MAJOR_CODE_RE = re.compile(r"INDUSTRY_\w*?S([A-Z])$")

TOTAL_NAME = "전체"


def _period(prd_de: str) -> str:
    return f"{prd_de[:4]}-{prd_de[4:6]}"


def _thousands(raw: str) -> float:
    return round(float(str(raw).replace(",", "")) / 1000, 1)


def parse(rows: list[dict], *, released_at: date, release_url: str,
          collected_at: datetime) -> list[SeriesRecord]:
    # (breakdown, category) -> {period: value}
    levels: dict[tuple[str, str | None], dict[str, float]] = {}
    for row in rows:
        if row.get("C2_NM") != TOTAL_NAME or row.get("ITM_NM") != "종사자_전체":
            continue
        name = str(row.get("C1_NM", "")).strip()
        code = str(row.get("C1", ""))
        period = _period(str(row.get("PRD_DE", "")))
        try:
            value = _thousands(row.get("DT"))
        except (TypeError, ValueError):
            continue

        if name == TOTAL_NAME:
            key = ("total", None)
        else:
            m = MAJOR_CODE_RE.search(code)
            if m is None:
                continue          # 중분류는 버린다 — 넣으면 대분류가 이중 계상된다
            key = ("industry", m.group(1))
        levels.setdefault(key, {})[period] = value

    records: list[SeriesRecord] = []
    for (breakdown, category), series in levels.items():
        for period, value in series.items():
            year, month = period.split("-")
            prior = series.get(f"{int(year) - 1}-{month}")
            records.append(SeriesRecord(
                id=make_id("est", period, breakdown, category), source="est",
                breakdown=breakdown, category=category, period=period,
                value=value,
                yoy=None if prior is None else round(value - prior, 1),
                released_at=released_at, release_url=release_url,
                attachments=[], collected_at=collected_at,
            ))
    return records


# 36 을 요청하지만 KOSIS 는 있는 만큼만 준다. 이 표는 2024-01 부터다 —
# 그 이전은 다른 산업분류 체계의 별도 표(DT_118N_MON056)에 있고 이어붙이지
# 않는다. 이어붙이면 전년동월대비가 재분류 효과를 고용 변화로 둔갑시킨다.
# 그래서 증감이 붙는 달은 2025-01 부터다.
def fetch(api_key: str, months: int = 36) -> list[dict]:
    params = {"method": "getList", "apiKey": api_key, "orgId": ORG_ID,
              "tblId": TBL_ID, "itmId": ITEM_TOTAL_EMPLOYEES_CODE, "objL1": "ALL",
              "objL2": SIZE_TOTAL_CODE, "prdSe": "M", "newEstPrdCnt": str(months),
              "format": "json", "jsonVD": "Y"}
    payload = requests.get(API, params=params, timeout=120).json()
    if isinstance(payload, dict):
        raise ValueError(f"KOSIS 오류: {payload.get('errMsg', payload)}")
    return payload


EXPECTED_CODES = set("BCDEFGHIJKLMNOPQRS")


def check_coverage(records: list[SeriesRecord]) -> None:
    """최신월에 기대한 대분류와 전체 행이 다 왔는지 본다.

    KOSIS 의 분류 코드 체계가 바뀌면 MAJOR_CODE_RE 가 산업을 조용히 흘린다.
    빠진 산업은 화면에서 그냥 없는 칸으로 보일 뿐 아무 오류도 남기지 않는다.
    """
    if not records:
        raise ValueError("수집된 레코드가 없다")
    latest = max(r.period for r in records)
    if not any(r.period == latest and r.breakdown == "total" for r in records):
        raise ValueError(f"{latest} 에 전체 종사자 행이 없다")
    got = {r.category for r in records
           if r.period == latest and r.breakdown == "industry"}
    missing = EXPECTED_CODES - got
    if missing:
        raise ValueError(f"{latest} 에 빠진 산업 대분류: {sorted(missing)}")


# 보도자료는 매월 말 전월 기준으로 나온다(임금만 전전월). 그런데 우리는 숫자를
# 보도자료가 아니라 KOSIS 표에서 받는데 그쪽 반영이 한 달 늦다 — 8월 말에 7월
# 고용 보도자료가 나와도 KOSIS 에는 아직 6월까지만 있다. 그래서 3 이다.
# 발표 주기가 전전월이라서가 아니다(sources.json 의 release_rule 은 보도자료 기준).
MAX_MONTHS_BEHIND = 3


def check_freshness(records: list[SeriesRecord], today: date) -> None:
    """최신월이 오늘로부터 너무 뒤처졌으면 실패시킨다.

    est 는 API 라 eaps 처럼 파싱이 잘리지는 않지만, KOSIS 가 표 갱신을
    멈추면 이 표가 없으면 영원히 ok:true 로 계속 보고된다. 발표 주기를
    아는 쪽은 여기뿐이다.
    """
    latest = max(r.period for r in records)
    year, month = (int(x) for x in latest.split("-"))
    behind = (today.year - year) * 12 + (today.month - month)
    if behind > MAX_MONTHS_BEHIND:
        raise ValueError(
            f"최신 기간이 {latest} 로 {behind}개월 뒤처졌다 — 수집이 잘렸거나 공표가 멈췄다")


def _end_of_month(year: int, month: int) -> date:
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    return date(year, month + 1, 1) - timedelta(days=1)


def _published_at(period: str) -> date:
    """조사대상월의 다음다음 달 말. sources.json 의 '매월 말, 전전월 기준' 이다.

    표에 발표일이 없어 규칙에서 계산한다. 실제로 2026-08-30 시점의 최신 기간이
    2026-06 인 것이 이 주기와 맞는다 — 7월 말 공표였다면 7월 자료가 나와 있어야 한다.
    """
    year, month = (int(x) for x in period.split("-"))
    month += 2
    if month > 12:
        year, month = year + 1, month - 12
    return _end_of_month(year, month)


def collect(today: date, *, releases_index: dict | None = None,
            industries: dict[str, str] | None = None,
            fetch_file=None) -> list[SeriesRecord]:
    api_key = os.environ.get("KOSIS_API_KEY", "").strip()
    if not api_key:
        raise ValueError("KOSIS_API_KEY 가 없다")
    rows = fetch(api_key)
    latest = max(_period(str(r.get("PRD_DE", ""))) for r in rows)
    records = parse(rows, released_at=_published_at(latest), release_url=STAT_URL,
                    collected_at=datetime.now(KST))
    check_coverage(records)
    check_freshness(records, today)

    # KOSIS 가 아직 담지 못한 달을 보도자료에서 보충한다. 실패해도 KOSIS 결과는
    # 그대로 돌려준다 — 있으면 좋은 것이지 이 수집기의 전제가 아니다.
    extra = _from_release(latest, releases_index, industries, fetch_file)
    return records + extra


def _from_release(kosis_latest, index, industries, fetch_file):
    if not index or not industries:
        return []
    posts = index.get("est", {})
    newer = sorted(p for p in posts if p > kosis_latest)
    if not newer:
        return []
    period = newer[-1]
    post = posts[period]
    files = [a for a in post.get("attachments", []) if a.get("type") == "hwpx"]
    if not files:
        return []

    released = _release_date(post)
    if released is None:
        return []

    getter = fetch_file or _download
    data = getter(files[0]["url"])
    if not data:
        return []
    return parse_release(
        data,
        released_at=released,
        release_url=post["url"],
        attachments=[Attachment(type="hwpx", url=files[0]["url"])],
        collected_at=datetime.now(KST),
        industries=industries,
        expect_period=period,
    )


def _release_date(post) -> date | None:
    """게시판 목록이 들고 있는 발표일. 지어내지 않는다 — 없으면 보충을 건너뛴다.

    released_at 은 store.upsert 가 '더 오래된 발표본이 최신 수치를 덮지 않게'
    쓰는 값이라, 틀린 날짜를 넣으면 나중에 KOSIS 가 그 달을 실어도 갱신이
    거부될 수 있다.
    """
    raw = post.get("posted_at")
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def _download(url: str) -> bytes | None:
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=90)
        return res.content if res.ok else None
    except Exception:
        return None


# ── 보도자료에서 최신월 보충 ──────────────────────────────────────────────
#
# KOSIS 반영은 보도자료보다 한 달 늦다. 8월 말에 7월 고용 보도자료가 나와도
# KOSIS 표에는 아직 6월까지만 있어서, 화면에서는 이 출처만 늘 한 달 뒤처져
# `미발표` 로 보였다 — 실제로는 이미 발표된 달인데도.
#
# 그래서 KOSIS 가 아직 담지 못한 달만 보도자료 hwpx 에서 읽어 얹는다. 과거
# 달은 그대로 KOSIS 를 쓴다: 보도자료는 천명을 정수로 반올림해 싣지만 KOSIS 는
# 소수 한 자리를 준다. 화면 표기가 만명 소수 첫째자리라 눈에는 같지만, 정밀도가
# 더 나은 쪽을 이력의 기본으로 둔다. 나중에 KOSIS 가 그 달을 실으면
# store.upsert 가 released_at 이 더 늦은 쪽으로 갱신한다.

RELEASE_KEYS = ("전체", "광업", "제조업")


def find_release_table(tables) -> list:
    """산업대분류별 종사자 표. 위치가 아니라 내용으로 찾는다."""
    for grid in tables:
        if len(grid) < 15:
            continue
        flat = squash(" ".join(" ".join(r) for r in grid[:6]))
        if all(k in flat for k in RELEASE_KEYS):
            return grid
    raise ValueError("보도자료에서 산업대분류별 종사자 표를 찾지 못했다")


def release_period(header: list[str]) -> str | None:
    """헤더의 마지막 월. `’25.7월 ’26.6월 7월` 이면 2026-07 이다.

    마지막 열은 연도를 생략하므로 바로 앞에서 본 연도를 잇는다.
    """
    year = None
    period = None
    for cell in header:
        text = squash(cell)
        both = re.search(r"(\d{2,4})\.(\d{1,2})월", text)
        if both:
            year, month = int(both.group(1)), int(both.group(2))
        else:
            only = re.fullmatch(r"(\d{1,2})월", text)
            if not (only and year is not None):
                continue
            month = int(only.group(1))
        if year < 100:
            year += 2000
        if 1 <= month <= 12:
            period = f"{year}-{month:02d}"
    return period


def _num(cell: str) -> float | None:
    raw = (cell or "").replace(",", "").strip()
    return float(raw) if re.fullmatch(r"-?\d+(\.\d+)?", raw) else None


def parse_release(data: bytes, *, released_at: date, release_url: str,
                  attachments: list[Attachment], collected_at: datetime,
                  industries: dict[str, str],
                  expect_period: str | None = None) -> list[SeriesRecord]:
    """보도자료 hwpx 에서 최신월의 전체·산업별 종사자를 읽는다.

    `industries` 는 {공백 지운 산업명: 대분류 코드}. 이름은 보도자료와
    industries.json 사이에 띄어쓰기가 어긋나므로(`기술서비스업` vs
    `기술 서비스업`) 공백을 지우고 맞춘다.
    """
    table = find_release_table(hwpx.tables(data))
    period = release_period(table[0])
    if period is None:
        raise ValueError("보도자료 표의 헤더에서 기준월을 읽지 못했다")
    if expect_period and period != expect_period:
        raise ValueError(f"보도자료 기준월이 다르다: 표는 {period}, 기대는 {expect_period}")

    # 최신월은 늘 맨 오른쪽 세 칸(값·증감·증감률)이다. 전체 행은 첫 칸이 병합돼
    # 산업 행보다 한 칸 짧으므로 끝에서부터 센다.
    def value_and_delta(row):
        return _num(row[len(row) - 3]), _num(row[len(row) - 2])

    total = None
    found: dict[str, tuple[float, float | None]] = {}
    for row in table[2:]:
        if len(row) < 4:
            continue
        head = squash(row[0]) or squash(row[1])
        value, delta = value_and_delta(row)
        if value is None:
            continue
        if head == "전체":
            total = (value, delta)
            continue
        code = industries.get(head)
        if code:
            found[code] = (value, delta)

    if total is None:
        raise ValueError("보도자료 표에 전체 행이 없다")
    if total[0] < 10000:
        raise ValueError(f"보도자료의 전체 종사자가 이상하다: {total[0]}")
    if not found:
        raise ValueError("보도자료 표에서 산업을 하나도 읽지 못했다")

    # 정수로 반올림된 18개를 더하므로 몇 천명 어긋난다. 그보다 크게 벌어지면
    # 산업을 빠뜨렸거나 열을 잘못 집은 것이다.
    gap = abs(sum(v for v, _ in found.values()) - total[0])
    if gap > 5:
        raise ValueError(f"산업 합이 전체와 다르다: 차이 {gap} (열을 잘못 집었을 수 있다)")

    def build(breakdown, category, pair):
        value, delta = pair
        return SeriesRecord(
            id=make_id("est", period, breakdown, category), source="est",
            breakdown=breakdown, category=category, period=period,
            value=value, yoy=delta, released_at=released_at,
            release_url=release_url, attachments=attachments,
            collected_at=collected_at,
        )

    records = [build("total", None, total)]
    records += [build("industry", code, pair) for code, pair in sorted(found.items())]
    return records
