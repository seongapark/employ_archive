"""OECD Interim Economic Outlook(3월·9월) 수집기.

본편 EO 와 달리 Interim 은 SDMX 에 올라오지 않는다. 발간 페이지에도 xlsx·csv 가
없고 Projections HTML 에는 표가 실리지 않아, 보고서 PDF 가 유일한 경로다.

전망표는 90도로 놓여 있다. 국가명은 글자마다 따로 배치돼 'K o re a' 로 추출되고,
값은 한 줄에 하나씩 열 우선으로 나온다. 그래서 행 이름과 값을 순서로 맞춘다 —
라벨 한 줄이 사라지면 조용히 다른 나라 값이 되므로, 행 수와 열 크기가 어긋나면
실패시킨다.

Interim 은 성장률과 헤드라인 물가만 싣는다. 고용·실업률은 본편 EO 에만 있다.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Mapping

from .. import http, pdf, rationale_store, report
from ..models import ForecastRecord

BASE = "https://www.oecd.org"
LANDING_URL = f"{BASE}/en/topics/sub-issues/economic-outlook.html"

# 회차 → (발표일, 보고서 PDF). SDMX 가 없어 손으로 관리한다.
# 새 회차(3월·9월)가 나오면 여기에 추가한다.
EDITIONS: dict[str, tuple[date, str]] = {
    "March 2025": (date(2025, 3, 17), f"{BASE}/content/dam/oecd/en/publications/reports/"
                   "2025/03/oecd-economic-outlook-interim-report-march-2025_47a36021/89af4857-en.pdf"),
    "September 2025": (date(2025, 9, 23), f"{BASE}/content/dam/oecd/en/publications/reports/"
                       "2025/09/oecd-economic-outlook-interim-report-september-2025_ae3d418b/67b10c01-en.pdf"),
    "March 2026": (date(2026, 3, 26), f"{BASE}/content/dam/oecd/en/publications/reports/"
                   "2026/03/oecd-economic-outlook-interim-report-march-2026_254a8d56/d4623013-en.pdf"),
}

# 열 머리글 낱말. 여기서부터는 행 이름이 아니다.
_COLUMN_WORDS = {"InterimEO", "projections", "Diffe", "Dec", "ren", "em", "cbefrom", "erEO"}
_NOT_A_ROW = ("Table", "Note", "TESTING", "STEERING", "FINDING", "Source", "Based",
              "The", "Spainis", "Fiscal", "usemoving", "aggregate", "moving")
_CAPTION = re.compile(r"^(Table \d+\.[^\n]*)", re.M)
_ROW_NAME = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9¹²³]{1,29}")
_VALUE = re.compile(r"-?\d+\.\d+")


def table_indicator(text: str) -> str | None:
    """표 제목으로 어느 지표인지 정한다. 근원물가 표는 우리 지표가 아니라 None."""
    caption = _CAPTION.search(text)
    if not caption:
        return None
    title = caption.group(1)
    if "Core inflation" in title:
        return None
    if "inflation" in title:
        return "cpi"
    if "growth" in title:
        return "gdp_growth"
    return None


def parse_rotated_table(text: str) -> tuple[list[str], list[list[float]]]:
    """(행 이름, 열 블록 4개) 로 편다.

    블록은 [전망연도1, 직전 EO 대비 차이, 전망연도2, 차이] 순서다. 첫 열(과거연도)은
    정수와 소수가 다른 줄로 쪼개져 나오는데, 발표연도보다 이전이라 쓰지 않으므로 버린다.
    """
    lines = [re.sub(r"\s+", "", line) for line in text.split("\n") if line.strip()]
    values = [float(line) for line in lines if _VALUE.fullmatch(line)]

    rows: list[str] = []
    for line in lines:
        if line in _COLUMN_WORDS:
            break
        if _ROW_NAME.fullmatch(line) and not line.startswith(_NOT_A_ROW):
            rows.append(line)

    if not rows or len(values) != 4 * len(rows):
        raise ValueError(
            f"표 구조 불일치: 행 {len(rows)}개 vs 값 {len(values)}개 (행×4 여야 한다)"
        )
    size = len(rows)
    return rows, [values[i * size:(i + 1) * size] for i in range(4)]


_UPRIGHT_KOREA = re.compile(r"^Korea((?:\s+-?\d+\.\d+){4,5})\s*$", re.M)


def korea_row_upright(text: str) -> list[float] | None:
    """표가 회전되지 않은 판에서는 한국 행이 한 줄로 그대로 나온다.

    회차마다 레이아웃이 섞여 있다(2025년 3월판 Table 1 은 평범한 행 배치,
    2026년 3월판 Table 1 은 90도 회전). 읽기 쉬운 쪽을 먼저 시도한다.
    """
    match = _UPRIGHT_KOREA.search(text)
    return [float(x) for x in match.group(1).split()] if match else None


def korea_values(text: str, published_at: date) -> dict[int, float]:
    """한국 행의 전망값을 {연도: 값} 으로 준다.

    Interim 은 발표연도와 그 다음 해를 전망하고, 각 전망연도마다 값과 '직전 EO
    대비 차이' 두 열이 붙는다. 앞에 과거연도 한 열이 더 붙기도 한다.
    """
    numbers = korea_row_upright(text)
    if numbers is not None:
        # 5개면 [과거연도, 전망1, 차이, 전망2, 차이], 4개면 과거연도가 없다
        start = 1 if len(numbers) == 5 else 0
        return {published_at.year: numbers[start],
                published_at.year + 1: numbers[start + 2]}

    rows, blocks = parse_rotated_table(text)
    if "Korea" not in rows:
        raise ValueError("표에서 Korea 행을 찾지 못했다")
    i = rows.index("Korea")
    return {published_at.year: blocks[0][i], published_at.year + 1: blocks[2][i]}


def parse(pages: Mapping[int, str], label: str, published_at: date,
          source_url: str) -> list[ForecastRecord]:
    issue = report.Issue(
        title=f"OECD Economic Outlook, Interim Report {label}",
        published_at=published_at,
        url=LANDING_URL,
    )
    values: dict[tuple[str, int, str], float] = {}
    page_of: dict[str, int] = {}
    for page_no, text in sorted(pages.items()):
        indicator = table_indicator(text)
        if indicator is None:
            continue
        try:
            found = korea_values(text, published_at)
        except ValueError:
            # 목차와 본문 참조에도 같은 캡션이 나온다 — 표가 아닌 페이지는 건너뛴다
            continue
        for year, value in found.items():
            values[(indicator, year, "annual")] = value
            page_of.setdefault(indicator, page_no)
    if not values:
        raise ValueError(f"{label}: 전망표를 찾지 못했다")

    page_no = min(page_of.values())
    return report.records_from_values(
        values, org="OECD", org_name_ko="OECD", issue=issue,
        source_url=source_url, source_page=page_no, confidence="extracted",
    )


def collect_edition(label: str) -> list[ForecastRecord]:
    published_at, url = EDITIONS[label]
    pages = pdf.page_texts(http.get(url).content)
    wanted = {n: t for n, t in enumerate(pages, 1) if table_indicator(t) is not None}
    return parse(wanted, label, published_at, url)


def _real_table_pages(pages: Mapping[int, str], published_at: date) -> dict[str, int]:
    """지표별로 실제 전망표가 실린 쪽을 찾는다. parse() 의 page_of 계산과 같은
    규칙을 쓰지만, page_of 는 parse() 안의 지역변수라 밖에서 못 쓰므로 여기서
    따로 계산한다.

    캡션만으로는 부족하다 — 목차와 본문 참조에도 같은 캡션이 나온다
    (table_indicator 문서 참고). korea_values 가 실제로 성공하는 쪽만
    "진짜 표"로 센다.
    """
    page_of: dict[str, int] = {}
    for page_no, text in sorted(pages.items()):
        indicator = table_indicator(text)
        if indicator is None or indicator in page_of:
            continue
        try:
            korea_values(text, published_at)
        except ValueError:
            # 목차와 본문 참조에도 같은 캡션이 나온다 — 표가 아닌 쪽은 건너뛴다
            continue
        page_of[indicator] = page_no
    return page_of


def collect_edition_rationales(label: str) -> list["Rationale"]:
    """그 회차의 근거 문장을 준다. 전망표를 못 찾으면 빈 리스트.

    성장률·물가 표가 각각 다른 쪽에 실릴 수 있으므로(_real_table_pages),
    지표마다 표 쪽 앞뒤 한 쪽씩을 창으로 잡는다. 다만 그 창들을 **하나로
    합쳐**(neighbors) 쪽 번호 오름차순으로 한 번씩만 읽고, 각 쪽에서 두
    지표(gdp_growth·cpi)를 함께 찾는다 — 지표별로 따로 훑지 않는다. 두
    표가 이웃한 쪽에 실리면 창이 겹치는데, 합치지 않으면 같은 쪽을 두 번
    읽고 같은 문장을 두 번 후보로 올리게 된다.

    지표를 쪽마다 함께 찾아도 결과가 섞이지 않는 것은 pick 이 지표별로
    따로 판정하기 때문이고, 같은 (기관·발표일·지표) 키가 여러 쪽에서 나오면
    rationale_store.merge 가 **먼저 온 쪽**(작은 쪽 번호)을 남긴다 —
    그래서 정렬해 읽는 순서가 곧 "보고서 앞쪽 우선"이 된다.

    이 창 밖으로 넓히지 않는다. Interim 보고서는 한국만 따로 짚어
    설명하는 서술이 없다(머리말 참고) — 국가명은 표에만 나오고, 본문은
    G20·미국처럼 큰 단위를 말한다. 실측(2026년 3월호, 28쪽짜리 PDF)으로
    확인했다: 본문 전체를 스캔하면 20쪽 "Economic growth in the G20
    emerging-market economies is projected to ease somewhat, largely due
    to a step down in growth in China and India."나 24쪽의 미국 정책금리
    문장처럼 한국과 무관한 문장이 gdp_growth·cpi 조건을 만족해 뽑힌다.
    이걸 한국 전망의 근거인 양 저장하면 표 쪽 번호를 잘못 인용하는 것보다
    더 나쁘다 — 아예 다른 나라 얘기를 이 기관의 한국 근거로 둔갑시키는
    것이기 때문이다. 표 쪽 앞뒤 한 쪽(4·6·7·10쪽)은 실측으로 이 위험이
    없음을 확인했다: 근거도 오탐도 없다.
    """
    published_at, url = EDITIONS[label]
    page_texts = pdf.page_texts(http.get(url).content)
    pages = {n: t for n, t in enumerate(page_texts, 1)}
    page_of = _real_table_pages(pages, published_at)
    if not page_of:
        return []

    issue = report.Issue(
        title=f"OECD Economic Outlook, Interim Report {label}",
        published_at=published_at,
        url=LANDING_URL,
    )
    neighbors: set[int] = set()
    for page_no in page_of.values():
        for candidate in (page_no - 1, page_no, page_no + 1):
            if 1 <= candidate <= len(page_texts):
                neighbors.add(candidate)

    collected: list["Rationale"] = []
    for page_no in sorted(neighbors):
        collected = rationale_store.merge(collected, report.rationales_from_text(
            page_texts[page_no - 1], org="OECD", issue=issue,
            indicators=("gdp_growth", "cpi"), source_url=url, source_page=page_no))
    return collected
