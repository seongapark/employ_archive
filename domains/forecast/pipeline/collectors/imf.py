"""IMF World Economic Outlook 수집기.

## 정규 회차(4·10월): SDMX `IMF.RES:WEO`

값과 **발표일**을 같은 곳에서 받는다. 데이터셋 속성 `PUBLICATION_DATE` 가 그
회차의 발표일이다(2026-04-14T13:00Z, 지난 판 WEO_2025_OCT_VINTAGE 는 2025-10-14 —
둘 다 기재부 보도참고 날짜와 일치). 예전에는 DataMapper 가 회차를 안 밝혀서
전망 지평(마지막 연도)으로 회차를 추정했는데, **10월판은 지평을 늘리지 않아**
4월판과 구별되지 않는다 — 2026년 10월판이 4월판 날짜로 조용히 저장될 뻔했다.
시계열 속성 `COUNTRY_UPDATE_DATE` 는 쓰지 않는다. 현행 판에서도 9/26/2025 로 낡아 있다.

## 업데이트(1·7월): 업데이트 PDF 부록표 1

WEO 데이터셋은 업데이트를 싣지 않는다(7/8 업데이트 뒤에도 PUBLICATION_DATE 가
4/14 였다). 업데이트 PDF 의 Annex Table 1 에 한국 성장률 행이 있다 — **성장률만**
있고 물가·실업률은 없다. 발표일은 기재부 보도참고에서 온다(PDF 가 안 밝힌다).

## 원문 링크

보고서 페이지(`/en/publications/weo/issues/…`)는 코드로 열면 403(Akamai)이라
확인할 수 없다. 원문 PDF(`/-/media/…/text.ashx`)는 열린다. 그래서 **PDF 를 받아
표지가 그 회차인지 확인한 뒤** source_url 로 싣고, 사람이 여는 보고서 페이지는
landing_url 로 싣는다.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from curl_cffi import requests as cf_requests

from ..models import ForecastRecord, INDICATOR_META, make_id

KST = timezone(timedelta(hours=9))

SDMX_BASE = "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES"
WEO_URL = SDMX_BASE + "/WEO/+/KOR.{code}.A?attributes=all&measures=all"
MEDIA_BASE = "https://www.imf.org/-/media/Files/Publications/WEO"

# IMF 지표코드 → 내부 지표코드
IMF_CODE_TO_INDICATOR = {
    "NGDP_RPCH": "gdp_growth",
    "PCPIPCH": "cpi",
    "LUR": "unemp_rate",
}


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


def _label_parts(label: str) -> tuple[bool, str, int]:
    """'Update July 2026' → (True, 'July', 2026)."""
    m = re.fullmatch(r"(Update )?([A-Z][a-z]+) (\d{4})", label)
    if not m or m.group(2).lower() not in _MONTHS:
        raise ValueError(f"회차 라벨을 읽지 못했다: {label!r}")
    return bool(m.group(1)), m.group(2), int(m.group(3))


def regular_label(published_at: date) -> str:
    if published_at.month not in (4, 10):
        raise ValueError(f"WEO 데이터셋의 발표일이 {published_at} 이다 — 4·10월판만 "
                         "실린다는 가정이 깨졌다. 업데이트가 데이터셋에 들어왔는지 확인할 것")
    return f"{_MONTHS[published_at.month - 1].capitalize()} {published_at.year}"


def pdf_url(label: str) -> str:
    update, month, year = _label_parts(label)
    return f"{MEDIA_BASE}/{year}/{'Update/' if update else ''}{month}/English/text.ashx"


def report_pages(url: str) -> list[str]:
    from .. import http, pdf

    data = http.get(url).content
    if data[:4] != b"%PDF":
        raise ValueError(f"원문이 PDF 가 아니다: {url}")
    return pdf.page_texts(data)


def report_cover(url: str) -> str:
    return report_pages(url)[0]


def check_cover(cover: str, label: str) -> None:
    """표지가 그 회차인지 본다. 표지에는 '2026 APR', '2025 O C T' 처럼 연도와
    달 약자가 찍혀 있고, 업데이트면 'WORLD ECONOMIC OUTLOOK UPDATE' 다."""
    update, month, year = _label_parts(label)
    flat = re.sub(r"\s+", "", cover).upper()
    if f"{year}{month[:3].upper()}" not in flat or ("OUTLOOKUPDATE" in flat) != update:
        raise ValueError(f"원문 PDF 의 표지가 {label} 회차가 아니다: {flat[:80]!r}")


def fetch_weo(imf_code: str) -> dict:
    resp = cf_requests.get(WEO_URL.format(code=imf_code), impersonate="chrome",
                           timeout=90, headers={"Accept": "application/json"})
    resp.raise_for_status()
    return resp.json()


def parse_weo(payload: dict) -> tuple[date, dict[int, float]]:
    """SDMX JSON 에서 (발표일, {연도: 값}) 을 꺼낸다."""
    structure = payload["data"]["structures"][0]
    dataset = payload["data"]["dataSets"][0]
    names = [a["id"] for a in structure["attributes"]["dataSet"]]
    attrs = dict(zip(names, dataset.get("attributes") or []))
    stamp = attrs.get("PUBLICATION_DATE")
    if not stamp:
        raise ValueError("WEO 데이터셋에 PUBLICATION_DATE 가 없다 — 회차를 정할 수 없다")
    published_at = date.fromisoformat(stamp[0][:10])

    periods = [v["value"] for v in structure["dimensions"]["observation"][0]["values"]]
    if len(dataset["series"]) != 1:
        raise ValueError(f"한국 시계열이 {len(dataset['series'])}개다 — 하나여야 한다")
    (series,) = dataset["series"].values()
    values = {int(periods[int(k)]): float(obs[0]) for k, obs in series["observations"].items()
              if obs[0] is not None}
    return published_at, values


def _records(label: str, title: str, published_at: date, indicator: str,
             series: dict[int, float], source_url: str) -> list[ForecastRecord]:
    meta = INDICATOR_META[indicator]
    landing = report_url(label, published_at)
    return [
        ForecastRecord(
            id=make_id("IMF", published_at, indicator, year),
            org="IMF", org_name_ko="IMF", report_title=title,
            published_at=published_at, target_year=year, indicator=indicator,
            value=round(series[year], meta["decimals"]), unit=meta["unit"],
            source_url=source_url, landing_url=landing, confidence="verified",
            collected_at=datetime.now(KST),
        )
        for year in (published_at.year, published_at.year + 1) if year in series
    ]


def collect(today: date) -> list[ForecastRecord]:
    parsed = {code: parse_weo(fetch_weo(code)) for code in IMF_CODE_TO_INDICATOR}
    dates = {published_at for published_at, _ in parsed.values()}
    if len(dates) != 1:
        raise ValueError(f"지표마다 회차가 다르다: {sorted(dates)} — 갱신 도중일 수 있다")
    (published_at,) = dates
    label = regular_label(published_at)
    url = pdf_url(label)
    check_cover(report_cover(url), label)

    title = f"IMF World Economic Outlook, {label}"
    records: list[ForecastRecord] = []
    for code, (_, series) in parsed.items():
        records.extend(_records(label, title, published_at,
                                IMF_CODE_TO_INDICATOR[code], series, url))
    if not records:
        raise ValueError(f"{label}: 레코드가 하나도 안 나왔다")
    return records


# ── 업데이트 회차 ────────────────────────────────────────────────────────

_UPDATE_MONTHS = (1, 7)
_WEO_NOTICE = re.compile(r"(\d{1,2})월\s*세계경제전망")
_YEARS = re.compile(r"^(?:\d{4}\s+){5}\d{4}$", re.M)
_KOREA_ROW = re.compile(r"^Korea((?:\s+-?\d+\.\d+){6})\s*$", re.M)


def update_growth(annex_text: str, year: int) -> dict[int, float]:
    """부록표 1(Real GDP Growth)의 한국 행에서 {year, year+1} 성장률을 읽는다.

    머리는 '2024 2025 2026 2027 2026 2027' 이다 — 앞 넷이 값, 뒤 둘이 직전 WEO
    대비 차이다. 머리의 앞 네 해로 열을 찾는다(회차마다 첫 해가 다르다).
    """
    text = annex_text.replace("–", "-").replace("−", "-")
    head = _YEARS.search(text)
    row = _KOREA_ROW.search(text)
    if not head or not row:
        raise ValueError("업데이트 부록표 1 에서 연도 머리나 Korea 행을 찾지 못했다")
    years = [int(y) for y in head.group(0).split()]
    values = [float(v) for v in row.group(1).split()]
    if years[4:] != [year, year + 1]:
        raise ValueError(f"부록표의 전망 연도가 {years[4:]} 다 — {year} 회차가 아니다")
    return {y: values[years[:4].index(y)] for y in (year, year + 1)}


def update_rounds(notices) -> list[tuple[str, date]]:
    """기재부 보도참고에서 업데이트 회차를 (라벨, 발표일) 로, 최근 것부터 뽑는다.

    2025년 보도참고는 제목에 '업데이트' 가 없다('7월 세계경제전망 발표') —
    제목 낱말이 아니라 **몇 월 전망인지**로 가른다.
    """
    out = {}
    for org, published, title in notices:
        m = _WEO_NOTICE.search(title)
        if org != "IMF" or not title.startswith("[보도참고]") or not m:
            continue
        month = int(m.group(1))
        if month in _UPDATE_MONTHS and month == published.month:
            label = f"Update {_MONTHS[month - 1].capitalize()} {published.year}"
            out[label] = published
    return sorted(out.items(), key=lambda kv: kv[1], reverse=True)


def collect_update_round(label: str, published_at: date) -> list[ForecastRecord]:
    url = pdf_url(label)
    pages = report_pages(url)
    check_cover(pages[0], label)
    annex = [t for t in pages if "Annex Table 1" in t and "Real GDP Growth" in t]
    if not annex:
        raise ValueError(f"{label}: 부록표 1(Real GDP Growth)을 찾지 못했다")
    series = update_growth(annex[0], published_at.year)
    title = f"IMF World Economic Outlook Update, {label.removeprefix('Update ')}"
    return _records(label, title, published_at, "gdp_growth", series, url)


def collect_update(today: date, notices: Callable[[], list] | None = None) -> list[ForecastRecord]:
    if notices is None:
        from ..watch import moef_notices as notices
    rounds = update_rounds(notices())
    if not rounds:
        raise ValueError("기재부 보도참고에서 IMF 업데이트 회차를 찾지 못했다")
    return collect_update_round(*rounds[0])


# 보관된 지난 회차. IMF SDMX 에는 아카이브된 vintage 가 이것 하나뿐이다
# (WEO_2026_APR_VINTAGE 등은 204 로 비어 있다).
#   October 2025  https://www.imf.org/en/publications/weo/issues/2025/10/14/world-economic-outlook-october-2025
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
