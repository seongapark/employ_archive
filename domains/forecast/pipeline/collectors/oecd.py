from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timedelta, timezone

import requests

from ..models import ForecastRecord, INDICATOR_META, make_id

KST = timezone(timedelta(hours=9))

DATA_URL = (
    "https://sdmx.oecd.org/public/rest/data/OECD.ECO.MAD,{dsd}@{flow},/"
    "KOR.GDPV_ANNPCT+UNR+CPI_YTYPCT+ET.A"
    "?startPeriod={start}&endPeriod={end}&format=csvfilewithlabels"
)
LANDING_URL = "https://www.oecd.org/en/topics/economic-outlook.html"

# 회차 번호 → 발표일. SDMX 는 발표일을 주지 않으므로 여기 적는다.
# 새 회차가 나오면 반드시 추가한다 — 없으면 parse() 가 실패한다. 조용히 틀린
# 날짜를 쓰느니 시끄럽게 멈추는 편이 낫다.
#   116 https://www.oecd.org/en/about/news/media-advisories/2024/11/
#       oecd-to-release-economic-outlook-on-wednesday-4-december-2024.html
#   117 Volume 2025 Issue 1  118 Volume 2025 Issue 2  119 Volume 2026 Issue 1
EDITIONS: dict[int, date] = {
    116: date(2024, 12, 4),
    117: date(2025, 6, 3),
    118: date(2025, 12, 2),
    119: date(2026, 6, 3),
}

_EDITION_NO = re.compile(r"Economic Outlook (?:No\s*)?(\d+)")

MEASURE_TO_INDICATOR = {
    "GDPV_ANNPCT": "gdp_growth",
    "UNR": "unemp_rate",
    "CPI_YTYPCT": "cpi",
}


def edition_number(report_title: str) -> int:
    """표제에서 회차 번호를 뽑는다.

    최신 데이터플로는 "Economic Outlook 119", 과거 회차는 "Economic Outlook No 118"
    로 표기가 다르다.
    """
    match = _EDITION_NO.search(report_title)
    if not match:
        raise ValueError(f"회차 번호를 읽을 수 없다: {report_title!r}")
    return int(match.group(1))


def _data_url(edition: int | None = None) -> str:
    """최신 회차는 DF_EO, 과거 회차는 DF_EO_<번호> 데이터플로에 들어 있다.

    최신 회차에는 번호가 붙은 데이터플로가 없다(DF_EO_119 는 존재하지 않는다).
    """
    if edition is None or edition >= max(EDITIONS):
        dsd, flow = "DSD_EO", "DF_EO"
    else:
        dsd, flow = f"DSD_EO_{edition}", f"DF_EO_{edition}"
    # ET 차분에 전년 값이 필요해 넉넉히 받고, 대상연도는 데이터에서 정한다
    return DATA_URL.format(dsd=dsd, flow=flow, start=2000, end=2100)


def fetch_raw(edition: int | None = None) -> str:
    resp = requests.get(_data_url(edition), timeout=60)
    resp.raise_for_status()
    return resp.text


def parse(raw_csv: str) -> list[ForecastRecord]:
    rows = list(csv.DictReader(io.StringIO(raw_csv)))
    report_title = rows[0]["STRUCTURE_NAME"] if rows else "OECD Economic Outlook"
    edition = edition_number(report_title)
    published_at = EDITIONS.get(edition)
    if published_at is None:
        raise ValueError(
            f"Economic Outlook {edition} 의 발표일을 모른다 — oecd.EDITIONS 에 추가할 것"
        )

    values: dict[tuple[str, int], float] = {}
    for row in rows:
        if row["REF_AREA"] != "KOR" or row["FREQ"] != "A":
            continue
        if not row.get("OBS_VALUE", "").strip():
            continue
        values[(row["MEASURE"], int(row["TIME_PERIOD"]))] = float(row["OBS_VALUE"])

    target_years = _forecast_years(values)
    source_url = _data_url(edition)
    records: list[ForecastRecord] = []
    for (measure, year), val in values.items():
        indicator = MEASURE_TO_INDICATOR.get(measure)
        if indicator is None or year not in target_years:
            continue
        records.append(_record(indicator, val, year, report_title, published_at, source_url))
    # 취업자 증감(만명) = ET(t) − ET(t−1)
    for year in target_years:
        cur = values.get(("ET", year))
        prev = values.get(("ET", year - 1))
        if cur is not None and prev is not None:
            records.append(_record(
                "emp_change", (cur - prev) / 10000, year, report_title, published_at, source_url
            ))
    return records


def _forecast_years(values: dict[tuple[str, int], float]) -> list[int]:
    """전망 구간은 데이터의 마지막 두 해다.

    수집일로 잡으면 회차마다 어긋난다 — 12월 회차는 다음 두 해를 전망하고
    6월 회차는 당해와 다음 해를 전망한다. 과거 회차 백필에서도 같은 규칙이 맞다.
    """
    years = sorted({year for _, year in values})
    return years[-2:]


def _record(indicator: str, value: float, year: int, report_title: str,
            published_at: date, source_url: str) -> ForecastRecord:
    meta = INDICATOR_META[indicator]
    return ForecastRecord(
        id=make_id("OECD", published_at, indicator, year),
        org="OECD",
        org_name_ko="OECD",
        report_title=report_title,
        published_at=published_at,
        target_year=year,
        indicator=indicator,
        value=round(value, meta["decimals"]),
        unit=meta["unit"],
        source_url=source_url,
        landing_url=LANDING_URL,
        confidence="verified",
        collected_at=datetime.now(KST),
    )


def collect(today: date) -> list[ForecastRecord]:
    return parse(fetch_raw())


def collect_edition(edition: int) -> list[ForecastRecord]:
    """지난 회차 하나를 받아 온다(백필 전용)."""
    return parse(fetch_raw(edition))
