from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from curl_cffi import requests as cf_requests

from ..models import ForecastRecord, INDICATOR_META, make_id

KST = timezone(timedelta(hours=9))

API_BASE = "https://www.imf.org/external/datamapper/api/v1"
LANDING_URL = "https://www.imf.org/external/datamapper/profile/KOR"

# IMF DataMapper 코드 → 내부 지표코드
IMF_CODE_TO_INDICATOR = {
    "NGDP_RPCH": "gdp_growth",
    "PCPIPCH": "cpi",
    "LUR": "unemp_rate",
}


def fetch_raw(imf_code: str) -> dict:
    # www.imf.org는 Akamai가 일반 HTTP 클라이언트를 403 차단하므로
    # 브라우저 TLS 핑거프린트로 위장해야 한다
    resp = cf_requests.get(
        f"{API_BASE}/{imf_code}/KOR", impersonate="chrome", timeout=60
    )
    resp.raise_for_status()
    return resp.json()


def parse(imf_code: str, payload: dict, today: date) -> list[ForecastRecord]:
    indicator = IMF_CODE_TO_INDICATOR[imf_code]
    meta = INDICATOR_META[indicator]
    series = payload.get("values", {}).get(imf_code, {}).get("KOR", {})
    records: list[ForecastRecord] = []
    for year in (today.year, today.year + 1):
        val = series.get(str(year))
        if val is None:
            continue
        records.append(ForecastRecord(
            id=make_id("IMF", today, indicator, year),
            org="IMF",
            org_name_ko="IMF",
            report_title=f"IMF WEO ({today:%Y.%m} 조회 기준)",
            published_at=today,
            target_year=year,
            indicator=indicator,
            value=round(float(val), meta["decimals"]),
            unit=meta["unit"],
            source_url=f"{API_BASE}/{imf_code}/KOR",
            landing_url=LANDING_URL,
            confidence="verified",
            collected_at=datetime.now(KST),
        ))
    return records


def collect(today: date) -> list[ForecastRecord]:
    records: list[ForecastRecord] = []
    for code in IMF_CODE_TO_INDICATOR:
        records.extend(parse(code, fetch_raw(code), today))
    return records
