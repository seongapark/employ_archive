"""여섯 출처의 회차 목록과 본문 획득을 한 모양으로 묶는다.

수집기마다 목록을 얻는 방법이 다르다(게시판 HTML, 상설 목록, 상수 표).
그 차이를 여기서 한 번 흡수하면 도구는 출처를 몰라도 된다.

fetch_pages 를 지연 호출로 두는 이유는 목록만 보려 할 때 회차마다 PDF 를
끌어오지 않기 위해서다. BOK·KIET·KDI 는 PDF 주소를 상세 페이지에서 읽어야
알기 때문에, 주소를 즉시 필드로 두면 회차마다(30여 개) 상세 페이지를 받게
된다 — 그래서 주소도 본문과 함께 fetch_pages 안에서 지연시킨다. KEIS 는
텍스트 레이어가 없어 전문 OCR 에 회차당 1분 반이 걸리는데, 목록 단계에서
그것을 치르면 도구를 쓸 수 없다.

oecd(본편)는 수치를 CSV API 로 받지만 **근거는 보고서 PDF 에서 읽는다** —
API 에는 "왜 그렇게 전망했는가" 가 없기 때문이다. 수치 경로는 그대로 둔다:
API 값은 verified 이고 정확한데 같은 값을 PDF 에서 다시 읽으면 정확도만 떨어진다.

**imf 는 여기에 없다. 경로를 안 만든 것이 아니라 원문에 내용이 없다.**
WEO 전문 180쪽에서 Korea 가 나오는 자리를 전부 확인했다(2026년 4월판):
표 행 하나, 나라 나열 여럿, `Korean War`(6·25), 그리고
`Democratic People's Republic of Korea`(북한). **한국을 설명하는 문장이 한 줄도
없다** — WEO 는 세계·권역 서술에 국가별 수치는 표로만 싣는 보고서다. 억지로
붙이면 모델이 6·25 문장이나 다른 나라 서술을 한국 근거로 뽑을 위험만 생긴다.
IMF 가 한국을 서술하는 문서는 Article IV 협의 보고서인데, WEO 와 발표일도
전망치도 다른 별개 문서라 이 회차의 근거로 붙이면 뜻이 달라진다.
"""
from __future__ import annotations

from datetime import date
from typing import Callable, NamedTuple

import html as html_lib
import re

from . import http, ocr, pdf
from .collectors import bok, kdi, keis, kiet, kli, moef, oecd


class Listed(NamedTuple):
    org: str
    title: str
    published_at: date
    indicators: tuple[str, ...]
    fetch_pages: Callable[[], tuple[str, list[str]]]
    # 본문이 OCR 로 읽힌 출처인가. 참이면 도구가 OCR 잡음 검사를 더 건다 —
    # 검사기의 원문 대조는 깨진 원문을 그대로 통과시키기 때문이다.
    ocr: bool = False


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
                   _via_ocr(li.pdf_url), ocr=True)
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


# ── OECD 본편: 한국 국가노트만 잘라 준다 ─────────────────────────────
#
# **반드시 좁혀야 한다. BOK 을 앞 40쪽으로 자른 것과는 성격이 다르다.**
# 이 보고서는 300쪽이고 **대부분이 다른 나라 얘기**다. 전문을 주면 토큰 한도를
# 크게 넘길 뿐 아니라, 모델이 칠레나 일본 문장을 한국 근거로 뽑을 수 있다.
# 잘못된 나라의 문장이 근거로 저장되는 것은 빈 칸보다 훨씬 나쁘다.
#
# 다행히 이 보고서에는 나라마다 국가노트가 따로 있다. 실측(EO 119): 214쪽이
# `Korea` 한 줄로 시작하는 서술, 215쪽이 `Korea: Demand, output and prices` 표,
# 216쪽이 서술 이어짐. 세 쪽 모두 본문에 Korea 가 나온다.
#
# 목차의 쪽번호(`Korea 212`)를 믿지 않는다 — 그건 **인쇄 쪽번호**라 PDF 인덱스와
# 어긋난다(실측 +2). 대신 쪽 머리에 `Korea` 가 홀로 선 쪽을 찾는다.
_OECD_INDICATORS = ("cpi", "emp_change", "gdp_growth", "unemp_rate")
_OECD_COUNTRY = "Korea"
_OECD_NOTE_MAX_PAGES = 4
_PDF_LINK = re.compile(r'href="([^"]*\.pdf[^"]*)"')


def korea_note(pages: list[str]) -> list[str]:
    """국가노트 쪽들만 준다. 못 찾으면 실패시킨다.

    조용히 전문을 돌려주면 안 된다 — 다른 나라 문장이 한국 근거가 된다.
    """
    for index, text in enumerate(pages):
        # 쪽 머리 세 줄 안에 `Korea` 가 홀로 선 줄이 있으면 그 쪽이 시작이다.
        # 목차 줄은 `Korea 212` 라 홀로 서지 않아 걸리지 않는다.
        if _OECD_COUNTRY in [line.strip() for line in text.split("\n")[:3]]:
            note = [t for t in pages[index:index + _OECD_NOTE_MAX_PAGES]
                    if _OECD_COUNTRY in t]
            if note:
                return note
    raise ValueError(
        f"보고서에서 {_OECD_COUNTRY} 국가노트를 찾지 못했다 — 서식이 바뀌었다")


def _oecd_report(edition: int) -> Callable[[], tuple[str, list[str]]]:
    def fetch() -> tuple[str, list[str]]:
        page_html = http.get(oecd.report_url(edition)).text
        match = _PDF_LINK.search(page_html)
        if not match:
            raise ValueError(f"EO {edition} 회차 페이지에서 PDF 링크를 찾지 못했다")
        url = html_lib.unescape(match.group(1))
        if url.startswith("/"):
            url = "https://www.oecd.org" + url
        return url, korea_note(pdf.page_texts_with_breaks(http.get(url).content))
    return fetch


def _oecd() -> list[Listed]:
    return [Listed("OECD", f"OECD Economic Outlook {edition}", published_at,
                   _OECD_INDICATORS, _oecd_report(edition))
            for edition, published_at in sorted(oecd.EDITIONS.items())]


# **중간전망(Interim)은 근거 출처가 아니다 — 본편과 달리 한국 국가노트가 없다.**
# 실측(2026년 3월호, 28쪽): Korea 가 나오는 자리는 표 행 하나(10쪽), 출처
# 표기(`Statistics Korea`), 환율 서술 한 줄(16쪽)뿐이다. 한국의 전망을 설명하는
# 문장이 없다.
#
# 그런데도 예전에는 전문을 줘서 근거를 뽑았고, 그렇게 저장된 6건이 전부 한국이
# 아니라 **G20·세계** 얘기였다:
#   "Aggregate consumer price inflation for the G20 countries will be markedly
#    higher than previously expected"
# 화면에서는 이것이 "OECD 가 한국 물가를 그렇게 본 이유" 로 읽힌다. 틀린 근거는
# 빈 칸보다 나쁘다는 이 파일의 원칙에 어긋나므로 출처에서 뺐다(수치 수집은 그대로
# 돈다 — oecd_interim.py 는 건드리지 않았다).
#
# 되살리려면 한국 서술이 실린 구간을 먼저 찾아야 한다. 지금은 그런 구간이 없다.


SOURCES: dict[str, Callable[[], list[Listed]]] = {
    "bok": _bok,
    "kdi": _kdi,
    "kli": _kli,
    "kiet": _kiet,
    "keis": _keis,
    "moef": _moef,
    "oecd": _oecd,
}
