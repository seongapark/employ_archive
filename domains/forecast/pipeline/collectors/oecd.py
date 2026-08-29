from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone

import requests

from ..models import ForecastRecord, INDICATOR_META, make_id

KST = timezone(timedelta(hours=9))

DATA_URL = (
    "https://sdmx.oecd.org/public/rest/data/OECD.ECO.MAD,DSD_EO@DF_EO,/"
    "KOR.GDPV_ANNPCT+UNR+CPI_YTYPCT+ET.A"
    "?startPeriod={start}&endPeriod={end}&format=csvfilewithlabels"
)
LANDING_URL = "https://www.oecd.org/en/topics/economic-outlook.html"

MEASURE_TO_INDICATOR = {
    "GDPV_ANNPCT": "gdp_growth",
    "UNR": "unemp_rate",
    "CPI_YTYPCT": "cpi",
}


def _data_url(today: date) -> str:
    # ET 차분에 전년(today.year-1) 값이 필요해 start를 1년 앞당긴다
    return DATA_URL.format(start=today.year - 1, end=today.year + 1)


def fetch_raw(today: date) -> str:
    resp = requests.get(_data_url(today), timeout=60)
    resp.raise_for_status()
    return resp.text


def parse(raw_csv: str, today: date) -> list[ForecastRecord]:
    rows = list(csv.DictReader(io.StringIO(raw_csv)))
    report_title = rows[0]["STRUCTURE_NAME"] if rows else "OECD Economic Outlook"
    values: dict[tuple[str, int], float] = {}
    for row in rows:
        if row["REF_AREA"] != "KOR" or row["FREQ"] != "A":
            continue
        if not row.get("OBS_VALUE", "").strip():
            continue
        values[(row["MEASURE"], int(row["TIME_PERIOD"]))] = float(row["OBS_VALUE"])

    target_years = [today.year, today.year + 1]
    records: list[ForecastRecord] = []
    for (measure, year), val in values.items():
        indicator = MEASURE_TO_INDICATOR.get(measure)
        if indicator is None or year not in target_years:
            continue
        records.append(_record(indicator, val, year, report_title, today))
    # 취업자 증감(만명) = ET(t) − ET(t−1)
    for year in target_years:
        cur = values.get(("ET", year))
        prev = values.get(("ET", year - 1))
        if cur is not None and prev is not None:
            records.append(
                _record("emp_change", (cur - prev) / 10000, year, report_title, today)
            )
    return records


def _record(indicator: str, value: float, year: int,
            report_title: str, today: date) -> ForecastRecord:
    meta = INDICATOR_META[indicator]
    return ForecastRecord(
        id=make_id("OECD", today, indicator, year),
        org="OECD",
        org_name_ko="OECD",
        report_title=report_title,
        published_at=today,
        target_year=year,
        indicator=indicator,
        value=round(value, meta["decimals"]),
        unit=meta["unit"],
        source_url=_data_url(today),
        landing_url=LANDING_URL,
        confidence="verified",
        collected_at=datetime.now(KST),
    )


def collect(today: date) -> list[ForecastRecord]:
    return parse(fetch_raw(today), today)
