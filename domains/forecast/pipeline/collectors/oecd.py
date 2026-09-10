from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timedelta, timezone

import requests

from .. import http
from ..models import ForecastRecord, INDICATOR_META, make_id

KST = timezone(timedelta(hours=9))

BASE = "https://www.oecd.org"
DATA_URL = (
    "https://sdmx.oecd.org/public/rest/data/OECD.ECO.MAD,{dsd}@{flow},/"
    "KOR.GDPV_ANNPCT+UNR+CPI_YTYPCT+ET.A"
    "?startPeriod={start}&endPeriod={end}&format=csvfilewithlabels"
)
# report_url() 로 대체된 뒤로 쓰는 곳이 없다 — source_url·landing_url 의
# 폴백으로 되살리지 말 것(기계용 주소를 절대 남기지 않는다는 이 파일의 원칙에
# 어긋난다).
LANDING_URL = "https://www.oecd.org/en/topics/economic-outlook.html"

# 회차 번호 → 발표일. SDMX 는 발표일을 주지 않으므로 여기 적는다.
# 새 회차가 나오면 반드시 추가한다 — 없으면 parse() 가 실패한다. 조용히 틀린
# 날짜를 쓰느니 시끄럽게 멈추는 편이 낫다.
#   116 https://www.oecd.org/en/about/news/media-advisories/2024/11/
#       oecd-to-release-economic-outlook-on-wednesday-4-december-2024.html
#   117 Volume 2025 Issue 1  118 Volume 2025 Issue 2  119 Volume 2026 Issue 1
# 114·115 는 2026-09-10 에 소급으로 넣었다. 발표일은 **기획재정부 보도참고**로
# 대조했다 — 기재부는 OECD 전망이 나오는 날 같은 날짜로 [보도참고]를 낸다.
# 이 대조법이 맞다는 근거: 116·117·118·119 의 기재부 보도참고 날짜가
# (2024-12-04·2025-06-03·2025-12-02·2026-06-03) 이미 들어 있던 값과 정확히 일치한다.
#   114 기재부 2023-11-29 [보도참고] 경제협력개발기구, '24년 한국경제 성장률 2.3% 전망
#   115 기재부 2024-05-02 [보도참고] 경제협력개발기구(OECD) 경제전망 발표
# 113(2023년 6월)은 SDMX 에 없다(DF_EO_113 404) — 넣지 않는다.
EDITIONS: dict[int, date] = {
    114: date(2023, 11, 29),
    115: date(2024, 5, 2),
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


SERIALS_URL = f"{BASE}/en/publications/serials/oecd-economic-outlook_g1ghgh13.html"

# 회차 116 이 2024년 2호다. 이후 한 호씩 번갈아 올라간다.
_FIRST_EDITION = 116
_FIRST_VOLUME = (2024, 2)

_SERIAL_LINK = re.compile(
    r'href="(/en/publications/oecd-economic-outlook-volume-'
    r'(?P<year>\d{4})-issue-(?P<issue>\d)_[0-9a-f]+-en\.html)"')


# 연재 목록(SERIALS_URL)은 **최근 네 권만** 싣는다(실측: 2024-2호 ~ 2026-1호).
# 그보다 옛 회차는 목록에서 못 찾으므로 주소를 여기 박는다. OECD iLibrary 는
# 옛 권호를 계속 들고 있고 주소도 안 바뀐다.
#
# **같은 권호에 주소가 둘인 함정이 여기 있다.** OECD 는 중간보고서를 직전 권의
# 호 번호 아래 끼워 넣는다 — `volume-2023/issue-2_0fd73462-en` 은 EO 114 가
# 아니라 **2024년 2월 중간전망**이다. 제목을 열어 확인하고 골랐다.
#   114 → OECD Economic Outlook, Volume 2023 Issue 2
#   115 → OECD Economic Outlook, Volume 2024 Issue 1
_ILIBRARY = "https://www.oecd-ilibrary.org/economics/oecd-economic-outlook"
REPORT_URLS: dict[int, str] = {
    114: f"{_ILIBRARY}/volume-2023/issue-2_7a5f73ce-en",
    115: f"{_ILIBRARY}/volume-2024/issue-1_69a0c310-en",
}


def volume_issue(edition: int) -> tuple[int, int]:
    """회차 번호를 (권 연도, 호) 로 바꾼다.

    OECD 본편은 연 2회이고 회차 번호가 한 호마다 1씩 오른다는 가정으로 산술만
    으로 구한다. 이 가정이 깨지면(번호를 건너뛰거나 Interim 이 끼어들거나
    재번호를 매기면) 계산값이 이웃 회차의 (권, 호) 를 가리키게 되는데, 그
    이웃 회차도 실제로 존재해 report_url() 의 목록 조회가 그 주소를 순순히
    돌려준다 — 링크는 열리지만 다른 회차 문서다. 그래서 EDITIONS 의 발표일로
    (권, 호)를 독립적으로 유도해 산술 결과와 맞춰 본다: **하반기 발표가 그 해
    2호, 상반기 발표가 1호**다.

    달을 12월로 못박으면 안 된다 — EO 114 는 2023-11-29 발표다(11월).
    12월만 2호로 보면 그 회차가 1호로 유도돼 멀쩡한 산술값과 어긋난다.
    실제 규칙은 연 2회, 상반기/하반기다. 이미 들어 있던 네 회차
    (116 2024-12-04 · 117 2025-06-03 · 118 2025-12-02 · 119 2026-06-03)의
    판정은 이 규칙에서도 그대로다.

    EDITIONS 에 없는 회차는 대조할 발표일이 없어 산술값을 그대로 믿는다 —
    다만 parse() 는 EDITIONS 에 없는 회차를 이 함수까지 오기 전에 이미
    거부하므로(EDITIONS.get 이 None), 실제로 이 경로를 타는 것은 report_url
    을 직접 부르는 호출뿐이고 그 결과는 report_url() 의 목록 소속 확인이
    마지막 방어선이 된다.
    """
    step = edition - _FIRST_EDITION
    year, issue = _FIRST_VOLUME
    total = (year * 2 + (issue - 1)) + step
    computed = total // 2, total % 2 + 1

    published_at = EDITIONS.get(edition)
    if published_at is not None:
        expected = (published_at.year, 2 if published_at.month >= 7 else 1)
        if computed != expected:
            raise ValueError(
                f"EO {edition} 의 권·호 산술값 {computed} 이 EDITIONS 발표일"
                f"({published_at})로 유도한 {expected} 와 어긋난다 — 회차 번호가"
                " 밀렸거나 Interim 이 끼어들었을 수 있다"
            )
    return computed


def parse_serials(page_html: str) -> dict[tuple[int, int], str]:
    """연재 목록에서 (권, 호) -> 보고서 주소 를 만든다.

    같은 (권, 호)에 주소가 둘이면(재발행판이 미리보기 옆에 남아 있는 경우 등)
    나중 것으로 조용히 덮어쓰지 않는다 — edition_with_label() 이 지평이
    겹치는 회차를 거부하는 것과 같은 이유로, 어느 쪽이 진짜 보고서인지 여기서
    고를 근거가 없기 때문이다.
    """
    found: dict[tuple[int, int], str] = {}
    for m in _SERIAL_LINK.finditer(page_html):
        key = (int(m.group("year")), int(m.group("issue")))
        url = BASE + m.group(1)
        if key in found and found[key] != url:
            raise ValueError(
                f"연재 목록에 권 {key[0]} {key[1]}호 주소가 둘이다: "
                f"{found[key]!r} 와 {url!r}"
            )
        found[key] = url
    if not found:
        raise ValueError("연재 목록에서 회차 링크를 찾지 못했다 — 서식이 바뀌었다")
    return found


def report_url(edition: int) -> str:
    """그 회차 보고서 주소를 준다. 목록에 없으면 실패시킨다.

    옛 회차 주소를 재활용하거나 기관 안내 페이지로 떨어뜨리지 않는다 — 둘 다
    독자를 다른 회차 문서로 데려간다(설계 4장).
    """
    # 회차 번호와 발표일이 어긋나지 않는지는 주소를 박아 둔 회차에서도 검사한다.
    key = volume_issue(edition)
    pinned = REPORT_URLS.get(edition)
    if pinned is not None:
        return pinned
    listing = parse_serials(http.get(SERIALS_URL).text)
    if key not in listing:
        raise ValueError(f"연재 목록에 EO {edition}(권 {key[0]} {key[1]}호)이 없다")
    return listing[key]


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
    # report_url() 은 네트워크를 타므로 레코드마다가 아니라 회차당 한 번만 부른다
    url = report_url(edition)
    records: list[ForecastRecord] = []
    for (measure, year), val in values.items():
        indicator = MEASURE_TO_INDICATOR.get(measure)
        if indicator is None or year not in target_years:
            continue
        records.append(_record(indicator, val, year, report_title, published_at, url))
    # 취업자 증감(만명) = ET(t) − ET(t−1)
    for year in target_years:
        cur = values.get(("ET", year))
        prev = values.get(("ET", year - 1))
        if cur is not None and prev is not None:
            records.append(_record(
                "emp_change", (cur - prev) / 10000, year, report_title, published_at, url
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
            published_at: date, url: str) -> ForecastRecord:
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
        source_url=url,
        landing_url=url,
        confidence="verified",
        collected_at=datetime.now(KST),
    )


def collect(today: date) -> list[ForecastRecord]:
    return parse(fetch_raw())


def collect_edition(edition: int) -> list[ForecastRecord]:
    """지난 회차 하나를 받아 온다(백필 전용)."""
    return parse(fetch_raw(edition))
