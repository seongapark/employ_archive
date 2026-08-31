from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from curl_cffi import requests as cf_requests

from ..models import ForecastRecord, INDICATOR_META, make_id

KST = timezone(timedelta(hours=9))

API_BASE = "https://www.imf.org/external/datamapper/api/v1"
LANDING_URL = "https://www.imf.org/external/datamapper/profile/KOR"

# IMF DataMapper 코드 → 내부 지표코드
# 회차 → (표제, 발표일, 전망 지평 마지막 연도).
#
# DataMapper 도 SDMX 도 현재 데이터가 어느 회차인지 밝히지 않는다. 다만 WEO 는
# 4월판마다 전망 지평을 한 해 늘린다(2025년 10월판은 2030년까지, 현행은 2031년까지).
# 그래서 마지막 연도로 회차를 특정하고, 모르는 지평이 오면 실패시킨다 —
# 조용히 틀린 발표일을 붙이느니 멈추는 편이 낫다.
#   April 2026  https://www.imf.org/en/publications/weo/issues/2026/04/14/world-economic-outlook-april-2026
EDITIONS: dict[str, tuple[str, date, int]] = {
    "April 2026": ("IMF World Economic Outlook, April 2026", date(2026, 4, 14), 2031),
}

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


WEO_ISSUE_BASE = "https://www.imf.org/en/publications/weo/issues"
_MONTHS = ("january", "february", "march", "april", "may", "june",
           "july", "august", "september", "october", "november", "december")


def report_url(label: str, published_at: date) -> str:
    """회차의 WEO 보고서 주소를 발표일에서 조립한다.

    IMF 는 회차 주소가 규칙적이라 목록을 긁을 필요가 없다. 라벨에 'Update' 가
    있으면 슬러그에 -update- 가 들어간다.

    주소가 실제로 열리는지 여기서 확인하지 않는다 — 매 수집마다 요청이 한 번 더
    붙고, 틀린 주소는 사람이 눌러 보면 즉시 드러난다. 회차를 추가할 때 그 주소를
    한 번 열어 보는 것으로 갈음한다.
    """
    lowered = label.lower()
    month = next((m for m in _MONTHS if m in lowered), None)
    if month is None:
        raise ValueError(f"회차 라벨에서 월을 읽지 못했다: {label!r}")
    kind = "world-economic-outlook-update" if "update" in lowered else "world-economic-outlook"
    return (f"{WEO_ISSUE_BASE}/{published_at:%Y/%m/%d}/"
            f"{kind}-{month}-{published_at:%Y}")


def edition_for_horizon(last_year: int) -> tuple[str, date, int]:
    for edition in EDITIONS.values():
        if edition[2] == last_year:
            return edition
    raise ValueError(
        f"전망 지평이 {last_year}년인 WEO 회차를 모른다 — imf.EDITIONS 에 추가할 것"
    )


def parse(imf_code: str, payload: dict, today: date) -> list[ForecastRecord]:
    indicator = IMF_CODE_TO_INDICATOR[imf_code]
    meta = INDICATOR_META[indicator]
    series = payload.get("values", {}).get(imf_code, {}).get("KOR", {})
    if not series:
        return []
    edition = edition_for_horizon(max(int(y) for y in series))
    title, published_at, _ = edition
    label = next(l for l, e in EDITIONS.items() if e == edition)
    url = report_url(label, published_at)
    records: list[ForecastRecord] = []
    for year in (published_at.year, published_at.year + 1):
        val = series.get(str(year))
        if val is None:
            continue
        records.append(ForecastRecord(
            id=make_id("IMF", published_at, indicator, year),
            org="IMF",
            org_name_ko="IMF",
            report_title=title,
            published_at=published_at,
            target_year=year,
            indicator=indicator,
            value=round(float(val), meta["decimals"]),
            unit=meta["unit"],
            source_url=url,
            landing_url=url,
            confidence="verified",
            collected_at=datetime.now(KST),
        ))
    return records


def collect(today: date) -> list[ForecastRecord]:
    records: list[ForecastRecord] = []
    for code in IMF_CODE_TO_INDICATOR:
        records.extend(parse(code, fetch_raw(code), today))
    return records


# 보관된 지난 회차. IMF SDMX 에는 아카이브된 vintage 가 이것 하나뿐이다
# (WEO_2026_APR_VINTAGE 등은 204 로 비어 있다).
#   October 2025  https://www.imf.org/en/publications/weo/issues/2025/10/14/world-economic-outlook-october-2025
SDMX_BASE = "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES"
VINTAGES: dict[str, tuple[str, str, date]] = {
    "October 2025": ("WEO_2025_OCT_VINTAGE/1.0.0",
                     "IMF World Economic Outlook, October 2025", date(2025, 10, 14)),
}

_OBS = re.compile(r'OBS_VALUE="([^"]+)" TIME_PERIOD="(\d{4})"')


def fetch_vintage(flow: str, imf_code: str) -> str:
    from curl_cffi import requests as cf_requests

    resp = cf_requests.get(f"{SDMX_BASE}/{flow}/KOR.{imf_code}.A",
                           impersonate="chrome", timeout=90)
    resp.raise_for_status()
    return resp.text


def parse_vintage(xml: str, imf_code: str, label: str, title: str,
                  published_at: date) -> list[ForecastRecord]:
    series = {int(year): float(value) for value, year in _OBS.findall(xml)}
    if not series:
        return []
    payload = {"values": {imf_code: {"KOR": {str(y): v for y, v in series.items()}}}}
    url = report_url(label, published_at)
    records = []
    for year in (published_at.year, published_at.year + 1):
        val = payload["values"][imf_code]["KOR"].get(str(year))
        if val is None:
            continue
        indicator = IMF_CODE_TO_INDICATOR[imf_code]
        meta = INDICATOR_META[indicator]
        records.append(ForecastRecord(
            id=make_id("IMF", published_at, indicator, year),
            org="IMF", org_name_ko="IMF", report_title=title,
            published_at=published_at, target_year=year, indicator=indicator,
            value=round(float(val), meta["decimals"]), unit=meta["unit"],
            source_url=url, landing_url=url, confidence="verified",
            collected_at=datetime.now(KST),
        ))
    return records


def collect_vintage(label: str) -> list[ForecastRecord]:
    flow, title, published_at = VINTAGES[label]
    records: list[ForecastRecord] = []
    for code in IMF_CODE_TO_INDICATOR:
        records.extend(parse_vintage(fetch_vintage(flow, code), code, label, title, published_at))
    return records
