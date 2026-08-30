"""사업체노동력조사 수집기 (KOSIS OpenAPI).

세 출처 중 유일하게 API 로 얻는다. 표는 대분류와 중분류가 한 축에 섞여
90여 항목으로 나오므로 코드로 대분류만 걸러낸다.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta, timezone

import requests

from ..models import SeriesRecord, make_id

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


def collect(today: date) -> list[SeriesRecord]:
    api_key = os.environ.get("KOSIS_API_KEY", "").strip()
    if not api_key:
        raise ValueError("KOSIS_API_KEY 가 없다")
    rows = fetch(api_key)
    latest = max(_period(str(r.get("PRD_DE", ""))) for r in rows)
    records = parse(rows, released_at=_published_at(latest), release_url=STAT_URL,
                    collected_at=datetime.now(KST))
    check_coverage(records)
    return records
