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
from .collectors import bok, kdi, keis, kiet, kli, moef, oecd_interim


class Listed(NamedTuple):
    org: str
    title: str
    published_at: date
    indicators: tuple[str, ...]
    fetch_pages: Callable[[], tuple[str, list[str]]]


def _via_detail(detail_url: str, find_pdf, *, max_pages: int | None = None
                ) -> Callable[[], tuple[str, list[str]]]:
    """주소를 상세 페이지에서 읽는 출처(BOK·KIET·MOEF)용.

    max_pages 는 **앞에서 그만큼만** 준다. 기본은 전문이다 — 쪽을 좁히면
    규칙 시절의 실패(표 ±1 쪽만 보다가 집필진 명단을 근거로 뽑던 일)로
    돌아갈 여지가 생기므로, 좁혀야만 하는 출처에만 값을 준다(BOK_MAX_PAGES 참고).
    """
    def fetch() -> tuple[str, list[str]]:
        url = find_pdf(http.get(detail_url).text)
        pages = pdf.page_texts_with_breaks(http.get(url).content)
        return url, pages if max_pages is None else pages[:max_pages]
    return fetch


def _direct(url: str) -> Callable[[], tuple[str, list[str]]]:
    """주소를 계산으로 아는 출처(KLI·OECD Interim)용."""
    return lambda: (url, pdf.page_texts_with_breaks(http.get(url).content))


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
            content = http.get(url).content
            try:
                # 장을 고르는 일은 빈 줄이 없는 원문으로 한다 —
                # _unfold_february_header 는 접힌 네 줄이 잇달아 있을 때만
                # 손대므로, 문단 나눔이 그 사이에 빈 줄을 넣으면 2월호가
                # 조용히 안 펴져 요약표를 실은 장을 못 찾는다.
                plain = [kdi._unfold_february_header(t)
                         for t in pdf.page_texts(content)]
                found = pdf.find_summary_table(
                    plain, kdi.LABEL_TO_INDICATOR, kdi.REQUIRED_INDICATORS)
            except Exception:
                continue
            if found is None:
                continue
            # LLM 에게는 문단 나눔이 든 원문을 준다. 같은 바이트를 두 번
            # 읽지만, 이 도구는 사람이 돌리는 것이라 정확도가 먼저다.
            return url, pdf.page_texts_with_breaks(content)
        raise ValueError(f"{issue.title}: 요약표를 실은 장을 찾지 못했다")
    return fetch


# **BOK 만 쪽을 좁힌다 — 안 좁히면 절반이 아예 안 들어간다.**
# 회차 분량 편차가 크다(실측 69·93·150·168쪽). 전문을 주면 프롬프트가
# 85k~276k 토큰이 되는데, 이 계정의 분당 한도가 200k 라 큰 회차는 요청
# 자체가 거부된다(429 "Request too large"). 앞 40쪽이면 전 회차가
# 46~55k 토큰으로 들어간다.
#
# 40 을 고른 근거는 **관측된 깊이의 3.6배**다. BOK 근거는 지금까지 전부
# 11쪽에서 나왔고(2건), 이전 세션도 "전망 문장은 늘 앞 5~11쪽"을 4회차에서
# 확인했다. 그래도 좁힘은 좁힘이다 — 어떤 회차가 더 뒤에 근거를 두면 그
# 회차는 조용히 0건이 된다(틀린 근거가 들어오는 것보다는 낫다).
# 한도가 올라가면 이 값을 None 으로 돌리는 것이 옳다.
BOK_MAX_PAGES = 40


def _bok() -> list[Listed]:
    indicators = tuple(sorted(bok.REQUIRED_INDICATORS))
    return [Listed("BOK", i.title, i.published_at, indicators,
                   _via_detail(i.url, bok.parse_pdf_link,
                               max_pages=BOK_MAX_PAGES))
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


def _moef() -> list[Listed]:
    """경제성장전략/경제정책방향. 첨부가 여럿이라 본문 PDF 를 골라 준다.

    수집기(collect_issue)는 전망표를 실은 PDF 를 찾을 때까지 첨부를 차례로
    열어 보지만, 근거는 문서 하나를 가리켜야 하므로 여기서는 **첫 후보**만
    쓴다(parse_attachments 가 보도자료·모두발언을 뒤로 미뤄 둔다).
    """
    def first_pdf(html: str) -> str:
        attachments = moef.parse_attachments(html)
        if not attachments:
            # 첨부가 없는 회차가 실제로 있다(참고자료만 올린 글 등).
            # [0] 을 그냥 집으면 IndexError 가 나서 무엇이 문제인지 안 보인다.
            raise ValueError("상세 페이지에 PDF 첨부가 없다")
        return attachments[0][1]

    indicators = tuple(sorted(set(moef.LABEL_TO_INDICATOR.values())))
    return [Listed("MOEF", i.title, i.published_at, indicators,
                   _via_detail(i.url, first_pdf))
            for i in moef.list_issues()]


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
    "moef": _moef,
}
