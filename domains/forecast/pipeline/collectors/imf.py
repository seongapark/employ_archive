from __future__ import annotations

import io
import re
from datetime import date, datetime, timedelta, timezone

from curl_cffi import requests as cf_requests

from ..models import ForecastRecord, INDICATOR_META, make_id

KST = timezone(timedelta(hours=9))

API_BASE = "https://www.imf.org/external/datamapper/api/v1"
# report_url() 로 대체된 뒤로 쓰는 곳이 없다 — source_url·landing_url 의
# 폴백으로 되살리지 말 것(기계용 주소를 절대 남기지 않는다는 이 파일의 원칙에
# 어긋난다). 정리는 imf.py 전체를 다시 볼 다른 작업에서 한다.
LANDING_URL = "https://www.imf.org/external/datamapper/profile/KOR"

# IMF DataMapper 코드 → 내부 지표코드
# 회차 → (표제, 발표일, 전망 지평 마지막 연도).
#
# DataMapper 도 SDMX 도 현재 데이터가 어느 회차인지 밝히지 않는다. 다만 WEO 는
# 4월판마다 전망 지평을 한 해 늘린다(2025년 10월판은 2030년까지, 현행은 2031년까지).
# 그래서 마지막 연도로 회차를 특정하고, 모르는 지평이 오면 실패시킨다 —
# 조용히 틀린 발표일을 붙이느니 멈추는 편이 낫다.
# 이 특정 방식이 성립하려면 항목마다 마지막 연도가 서로 달라야 한다 — 10월판처럼
# 지평을 늘리지 않는 회차가 늘어나면 두 회차가 같은 지평을 가질 수 있는데, 그때
# 고르는 기준이 없다. edition_with_label() 이 이를 검사해 조용히 하나를 고르는
# 대신 실패한다.
#
# Update 회차를 추가할 때는 키(라벨)에 반드시 "Update" 를 넣을 것 — report_url()
# 은 라벨에 "update" 가 있는지만 보고 슬러그에 -update- 를 넣을지 정한다.
# 예: 다음에 나올 2026년 7월판은 "April 2026" 과 같은 모양으로 "July 2026" 이라
# 적으면 world-economic-outlook-july-2026(오답, 실제로는 존재하지 않는 주소)이
# 만들어진다. 반드시 "Update July 2026" 으로 적어야 한다.
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
    # 라벨의 월과 published_at 의 월이 다른 곳에서 온 값이다(하나는 EDITIONS
    # 키, 하나는 그 옆 튜플) — EDITIONS 행을 고치다 한쪽만 바꾸면 둘이 어긋난
    # 채로 그럴듯한 주소가 만들어진다. 서로 맞는지 확인하고 아니면 멈춘다.
    if _MONTHS.index(month) + 1 != published_at.month:
        raise ValueError(
            f"회차 라벨의 월과 발표일의 월이 어긋난다: {label!r} vs {published_at} "
            "— EDITIONS 항목을 확인할 것"
        )
    kind = "world-economic-outlook-update" if "update" in lowered else "world-economic-outlook"
    return (f"{WEO_ISSUE_BASE}/{published_at:%Y/%m/%d}/"
            f"{kind}-{month}-{published_at:%Y}")


def edition_with_label(last_year: int) -> tuple[str, tuple[str, date, int]]:
    """전망 지평(마지막 연도)으로 회차를 찾아 라벨과 함께 돌려준다.

    라벨과 회차 정보를 한 번의 조회로 같이 얻는다 — 따로 찾으면 두 조회가
    서로 다른 답을 줄 수 있다(EDITIONS 를 두 번 훑는 사이에 바뀌지는 않더라도,
    "값으로 역매칭" 같은 코드가 원래 찾은 것과 다른 항목에 우연히 매치될 수
    있다). 지평이 EDITIONS 항목 여럿과 맞으면 — 위 EDITIONS 주석대로 설계가
    깨진 상황이라 — 조용히 하나를 고르지 않고 실패시킨다.
    """
    matches = [(label, edition) for label, edition in EDITIONS.items()
               if edition[2] == last_year]
    if not matches:
        raise ValueError(
            f"전망 지평이 {last_year}년인 WEO 회차를 모른다 — imf.EDITIONS 에 추가할 것"
        )
    if len(matches) > 1:
        labels = [label for label, _ in matches]
        raise ValueError(
            f"전망 지평이 {last_year}년인 WEO 회차가 {labels} 로 여럿이다 — "
            "EDITIONS 항목은 last_year 가 서로 달라야 회차를 특정할 수 있다"
        )
    return matches[0]


def edition_for_horizon(last_year: int) -> tuple[str, date, int]:
    return edition_with_label(last_year)[1]


def parse(imf_code: str, payload: dict, today: date) -> list[ForecastRecord]:
    indicator = IMF_CODE_TO_INDICATOR[imf_code]
    meta = INDICATOR_META[indicator]
    series = payload.get("values", {}).get(imf_code, {}).get("KOR", {})
    if not series:
        return []
    label, (title, published_at, _) = edition_with_label(max(int(y) for y in series))
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


# ── 과거 회차: WEO Historical Forecasts Database ──────────────────────────
#
# **SDMX 아카이브에는 vintage 가 하나뿐이다**(WEO_2025_OCT_VINTAGE). 다른 이름은
# 전부 404 이고(2025 JAN/APR/JUL · 2026 JAN/APR/JUL · 2024 OCT 실측), IMF 데이터
# 포털의 Dataset Vintages 목록도 "Result 1 of 1" 이다. DataMapper 는 현행 회차만
# 준다. 그래서 지난 회차는 이 파일에서만 온다 — IMF 가 "그때 그 회차가 무엇을
# 전망했는가" 를 모아 배포하는 엑셀이다.
#
# **범위가 좁다는 것을 알고 쓴다:**
#  - 시트가 셋뿐이라 **실업률(LUR)이 없다.** 성장률·물가만 채워진다.
#  - 열이 S<연도>(4월판)·F<연도>(10월판) 뿐이라 **1·7월 Update 는 없다** —
#    Update 는 데이터베이스를 내지 않는다. 그 회차를 채우려면 Update PDF 를
#    따로 읽어야 한다(미착수).
#
# 발표일은 지어내지 않고 **기획재정부 보도참고**로 대조했다. 그 대조법이 맞다는
# 근거: 이미 들어 있던 두 회차의 기재부 날짜가 정확히 일치한다
# (F2025 2025-10-14 · S2026 2026-04-14).
HISTORICAL_URL = ("https://data.imf.org/-/media/iData/External-Storage/Documents/"
                  "977574FA66914EAD900D3FEC55C7316A/en/WEOhistorical.xlsx")
HISTORICAL_SHEETS = {"ngdp_rpch": "gdp_growth", "pcpi_pch": "cpi"}
# 열 접두 → (표제, 발표일). 기재부 보도참고로 확인한 것만 싣는다.
HISTORICAL_VINTAGES: dict[str, tuple[str, date]] = {
    "F2024": ("IMF World Economic Outlook, October 2024", date(2024, 10, 22)),
    "S2025": ("IMF World Economic Outlook, April 2025", date(2025, 4, 22)),
}

_XL_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_COL = re.compile(r"[A-Z]+")


def _sheet_rows(zf, sheet_file: str, shared: list[str]):
    """시트를 한 줄씩 {열문자: 값} 으로 흘려보낸다.

    openpyxl 을 쓰지 않는다 — 사람이 한 번 돌리는 백필 때문에 의존성을 늘리지
    않으려는 것이다. xlsx 는 zip 안의 XML 이라 표준 라이브러리로 읽힌다.
    시트 하나가 28MB 라 통째로 올리지 않고 iterparse 로 흘린다.
    """
    from xml.etree import ElementTree as ET

    with zf.open("xl/" + sheet_file.lstrip("/")) as handle:
        for _, element in ET.iterparse(handle, events=("end",)):
            if element.tag != _XL_NS + "row":
                continue
            row = {}
            for cell in element:
                value = cell.find(_XL_NS + "v")
                if value is None:
                    continue
                column = _COL.match(cell.get("r")).group(0)
                row[column] = (shared[int(value.text)] if cell.get("t") == "s"
                               else value.text)
            yield row
            element.clear()


def read_historical(data: bytes, sheet_name: str,
                    iso3: str = "KOR") -> dict[str, dict[int, float]]:
    """{열접두: {전망연도: 값}} 을 준다. 열접두는 'S2025' 처럼 회차를 가리킨다."""
    import zipfile
    from xml.etree import ElementTree as ET

    zf = zipfile.ZipFile(io.BytesIO(data))
    shared = [(t.text or "") for t in
              ET.fromstring(zf.read("xl/sharedStrings.xml")).iter(_XL_NS + "t")]
    rels = {r.get("Id"): r.get("Target") for r in
            ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))}
    sheets = {s.get("name"): rels[s.get(_REL_NS + "id")] for s in
              ET.fromstring(zf.read("xl/workbook.xml")).iter(_XL_NS + "sheet")}
    if sheet_name not in sheets:
        raise ValueError(f"WEO 과거 전망 파일에 {sheet_name} 시트가 없다 "
                         f"— 있는 것: {sorted(sheets)}")

    rows = _sheet_rows(zf, sheets[sheet_name], shared)
    header = next(rows)
    column_of = {name: col for col, name in header.items()}
    if "year" not in column_of or "ISOAlpha_3Code" not in column_of:
        raise ValueError(f"{sheet_name} 시트의 머리글이 바뀌었다: {sorted(column_of)[:8]}")

    out: dict[str, dict[int, float]] = {}
    for row in rows:
        if row.get(column_of["ISOAlpha_3Code"]) != iso3:
            continue
        year = int(row[column_of["year"]])
        for name, col in column_of.items():
            if not name.startswith(("S", "F")) or not name[1:5].isdigit():
                continue
            raw = row.get(col)
            # 값이 없는 칸은 "." 로 온다
            if raw is None or raw == ".":
                continue
            out.setdefault(name[:5], {})[year] = float(raw)
    if not out:
        raise ValueError(f"{sheet_name} 시트에서 {iso3} 행을 찾지 못했다")
    return out


def collect_vintage_historical(label: str, *, data: bytes | None = None
                               ) -> list[ForecastRecord]:
    """WEO 과거 전망 파일에서 회차 하나를 레코드로 옮긴다(백필 전용)."""
    title, published_at = HISTORICAL_VINTAGES[label]
    if data is None:
        from curl_cffi import requests as cf_requests
        resp = cf_requests.get(HISTORICAL_URL, impersonate="chrome", timeout=300)
        resp.raise_for_status()
        data = resp.content

    url = report_url(title.split(", ")[-1], published_at)
    collected_at = datetime.now(KST)
    records: list[ForecastRecord] = []
    for sheet_name, indicator in HISTORICAL_SHEETS.items():
        series = read_historical(data, sheet_name).get(label)
        if not series:
            raise ValueError(f"{label} 회차가 {sheet_name} 시트에 없다")
        meta = INDICATOR_META[indicator]
        for year in (published_at.year, published_at.year + 1):
            if year not in series:
                continue
            records.append(ForecastRecord(
                id=make_id("IMF", published_at, indicator, year),
                org="IMF", org_name_ko="IMF", report_title=title,
                published_at=published_at, target_year=year, indicator=indicator,
                value=round(series[year], meta["decimals"]), unit=meta["unit"],
                source_url=url, landing_url=url, confidence="verified",
                collected_at=collected_at,
            ))
    if not records:
        raise ValueError(f"{label} 회차에서 레코드가 하나도 안 나왔다")
    return records
