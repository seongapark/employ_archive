"""여섯 출처의 회차 목록과 본문 획득을 한 모양으로 묶는다.

수집기마다 목록을 얻는 방법이 다르다(게시판 HTML, 상설 목록, 상수 표).
그 차이를 여기서 한 번 흡수하면 도구는 출처를 몰라도 된다.

fetch_pages 를 지연 호출로 두는 이유는 목록만 보려 할 때 회차마다 PDF 를
끌어오지 않기 위해서다. BOK·KIET·KDI 는 PDF 주소를 상세 페이지에서 읽어야
알기 때문에, 주소를 즉시 필드로 두면 회차마다(30여 개) 상세 페이지를 받게
된다 — 그래서 주소도 본문과 함께 fetch_pages 안에서 지연시킨다. KEIS 는
텍스트 레이어가 없어 전문 OCR 에 회차당 1분 반이 걸리는데, 목록 단계에서
그것을 치르면 도구를 쓸 수 없다.

imf·oecd(본편)는 여기에 없다 — SDMX·CSV API 로 수치만 받아 원문 텍스트가
없다.
"""
from __future__ import annotations

from datetime import date
from typing import Callable, NamedTuple

from . import http, ocr, pdf
from .collectors import bok, kdi, keis, kiet, kli, oecd_interim


class Listed(NamedTuple):
    org: str
    title: str
    published_at: date
    indicators: tuple[str, ...]
    fetch_pages: Callable[[], tuple[str, list[str]]]


def _via_detail(detail_url: str, find_pdf) -> Callable[[], tuple[str, list[str]]]:
    """주소를 상세 페이지에서 읽는 출처(BOK·KIET)용."""
    def fetch() -> tuple[str, list[str]]:
        url = find_pdf(http.get(detail_url).text)
        return url, pdf.page_texts(http.get(url).content)
    return fetch


def _direct(url: str) -> Callable[[], tuple[str, list[str]]]:
    """주소를 계산으로 아는 출처(KLI·OECD Interim)용."""
    return lambda: (url, pdf.page_texts(http.get(url).content))


def _via_ocr(pdf_url: str) -> Callable[[], tuple[str, list[str]]]:
    """텍스트 레이어가 없는 출처(KEIS)용 — 전문을 OCR 한다."""
    return lambda: (pdf_url, ocr.page_texts(
        http.get(pdf_url).content, None, dpi=400, preprocess=True))


def _via_kdi_chapters(issue) -> Callable[[], tuple[str, list[str]]]:
    """KDI 용 — 상세 페이지의 장(章)별 PDF 중 요약표가 실린 장을 찾아 그
    전문을 돌려준다. kdi.collect_issue 가 장을 훑는 것과 같은 경로를 그대로
    쓴다(수집기 안을 고치지 않고 이미 있는 함수를 조합한다).

    본문은 반드시 kdi._unfold_february_header 를 거친다 — 2월호는 수정폭
    헤더가 세로로 접혀 나와, 이걸 빠뜨리면 그 회차 본문이 어긋난다.
    """
    def fetch() -> tuple[str, list[str]]:
        page_html = http.get(issue.url).text
        for _, url in kdi.parse_chapters(page_html):
            try:
                pages = [kdi._unfold_february_header(t)
                         for t in pdf.page_texts(http.get(url).content)]
                found = pdf.find_summary_table(
                    pages, kdi.LABEL_TO_INDICATOR, kdi.REQUIRED_INDICATORS)
            except Exception:
                continue
            if found is None:
                continue
            return url, pages
        raise ValueError(f"{issue.title}: 요약표를 실은 장을 찾지 못했다")
    return fetch


def _bok() -> list[Listed]:
    indicators = tuple(sorted(bok.REQUIRED_INDICATORS))
    return [Listed("BOK", i.title, i.published_at, indicators,
                   _via_detail(i.url, bok.parse_pdf_link))
            for i in bok.list_issues()]


def _kdi() -> list[Listed]:
    indicators = tuple(sorted(kdi.REQUIRED_INDICATORS))
    return [Listed("KDI", i.title, i.published_at, indicators,
                   _via_kdi_chapters(i))
            for i in kdi.list_issues()]


def _kli() -> list[Listed]:
    indicators = tuple(sorted(kli.INDICATORS))
    return [Listed("KLI", i.title, i.published_at, indicators,
                   _direct(kli.DOWNLOAD_URL.format(no=kli._list_no(i.url))))
            for i in kli.list_issues()]


def _kiet() -> list[Listed]:
    indicators = tuple(sorted(set(kiet.LABEL_TO_INDICATOR.values())))
    return [Listed("KIET", i.title, i.published_at, indicators,
                   _via_detail(i.url, kiet.parse_pdf_link))
            for i in kiet.list_issues()]


def _keis() -> list[Listed]:
    indicators = tuple(sorted(keis.REQUIRED_INDICATORS))
    return [Listed("KEIS", li.issue.title, li.issue.published_at, indicators,
                   _via_ocr(li.pdf_url))
            for li in keis.list_issues()]


_OECD_INTERIM_INDICATORS = {"gdp_growth", "cpi"}


def _oecd_interim() -> list[Listed]:
    indicators = tuple(sorted(_OECD_INTERIM_INDICATORS))
    return [Listed("OECD", f"OECD Economic Outlook, Interim Report {label}",
                   published_at, indicators, _direct(url))
            for label, (published_at, url) in oecd_interim.EDITIONS.items()]


SOURCES: dict[str, Callable[[], list[Listed]]] = {
    "bok": _bok,
    "kdi": _kdi,
    "kli": _kli,
    "kiet": _kiet,
    "keis": _keis,
    "oecd_interim": _oecd_interim,
}
