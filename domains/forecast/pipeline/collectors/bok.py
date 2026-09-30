"""한국은행 경제전망보고서 수집기.

목록 페이지는 자바스크립트로 그려져 긁을 수 없으나, 같은 게시판의 RSS가
회차 제목·발표일시·본문 링크를 그대로 준다. 거기서 최신 회차를 찾아
본문에 붙은 PDF를 받고 요약표 페이지를 읽는다.
"""
from __future__ import annotations

import re
from datetime import date
from email.utils import parsedate_to_datetime

from .. import http, pdf, report
from ..models import ForecastRecord
from ..report import Issue  # 두 수집기가 같은 회차 표현을 쓴다

BASE = "https://www.bok.or.kr"
RSS_URL = f"{BASE}/portal/bbs/P0002359/news.rss?menuNo=200066"

# 요약표로 인정하는 최소 지표. 앞쪽에 실린 부분 표(성장률·물가만 있는 표 등)를 거른다
REQUIRED_INDICATORS = {"gdp_growth", "cpi", "emp_change", "unemp_rate"}

# 요약표 행 이름(공백·단위·각주 제거) → 내부 지표코드
LABEL_TO_INDICATOR = {
    "GDP성장률": "gdp_growth",
    "소비자물가상승률": "cpi",
    "취업자수증감": "emp_change",
    "실업률": "unemp_rate",
    "고용률": "emp_rate",
}

_ITEM = re.compile(r"<item>(.*?)</item>", re.S)
_ISSUE_TITLE = re.compile(r"경제전망보고서\(\s*\d{4}년\s*\d{1,2}월\s*\)")
_PDF_HREF = re.compile(r'href="(/fileSrc/[^"]+\.pdf)"')


def _tag(item: str, name: str) -> str:
    match = re.search(rf"<{name}>(.*?)</{name}>", item, re.S)
    if not match:
        return ""
    value = match.group(1).strip()
    cdata = re.fullmatch(r"<!\[CDATA\[(.*?)\]\]>", value, re.S)
    return (cdata.group(1) if cdata else value).strip()


def parse_rss(xml: str) -> list[Issue]:
    """회차 항목만 최신순으로 돌려준다(발표시점 변경 안내 등 공지는 버린다)."""
    issues = []
    for raw in _ITEM.findall(xml):
        title = _tag(raw, "title")
        if not _ISSUE_TITLE.fullmatch(title):
            continue
        issues.append(Issue(
            title=title,
            published_at=parsedate_to_datetime(_tag(raw, "pubDate")).date(),
            url=_tag(raw, "link"),
        ))
    return sorted(issues, key=lambda i: i.published_at, reverse=True)


def parse_pdf_link(html: str) -> str:
    match = _PDF_HREF.search(html)
    if not match:
        raise ValueError("본문에서 PDF 첨부를 찾지 못했다")
    return BASE + match.group(1)


def parse(text: str, issue: Issue, source_url: str, source_page: int) -> list[ForecastRecord]:
    return report.records_from_table(
        text, LABEL_TO_INDICATOR,
        org="BOK", org_name_ko="BOK",
        issue=issue, source_url=source_url, source_page=source_page,
    )


def list_issues() -> list[Issue]:
    """게시판에 남아 있는 회차를 최신순으로 준다(2014년까지 남는다)."""
    issues = parse_rss(http.get(RSS_URL).text)
    if not issues:
        raise ValueError("RSS에서 경제전망보고서 회차를 찾지 못했다")
    return issues


# 이미지로 박힌 행 이름 끝에 각주 번호가 괄호 없이 붙어 읽힌다('GDP 성장률(%)4').
_OCR_FOOTNOTE = re.compile(r"(?<=\))\d+$")
_OCR_BULLET = re.compile(r"^[*•·ㆍ⋅©\s]+")
# 행 이름이 이미지인 쪽으로 볼 최소 이미지 수(요약표 행이 20개 남짓이다)
_MIN_LABEL_IMAGES = 15


def label_image_rows(page, read_label) -> str | None:
    """행 이름이 이미지로 박힌 요약표를, 행 이름을 붙인 텍스트로 되살린다.

    2025년 11월판은 요약표의 행 이름 23개가 전부 그림이라 텍스트로 뽑으면 숫자
    줄만 남는다. 순서로 짐작하지 않는다 — 그림마다 OCR 로 이름을 읽고, 세로
    위치가 겹치는 숫자 줄 앞에 붙인다. 이름을 못 읽은 줄은 그대로 두므로
    parse_summary_table 이 모르는 행으로 버린다.
    """
    if len(page.images) < _MIN_LABEL_IMAGES:
        return None
    lines = page.extract_text_lines()
    out = []
    for line in lines:
        middle = (line["top"] + line["bottom"]) / 2
        image = next((im for im in page.images if im["top"] - 2 <= middle <= im["bottom"] + 2), None)
        if image is None:
            out.append(line["text"])
            continue
        label = read_label(page.crop((image["x0"] - 1, image["top"] - 1,
                                      image["x1"] + 1, image["bottom"] + 1)))
        label = _OCR_FOOTNOTE.sub("", _OCR_BULLET.sub("", label.strip()))
        out.append(f"{label} {line['text']}")
    return "\n".join(out)


def _ocr_label(cropped) -> str:
    import pytesseract
    image = cropped.to_image(resolution=400).original
    return pytesseract.image_to_string(image, lang="kor+eng", config="--psm 7")


def find_image_labeled_table(data: bytes, read_label=_ocr_label) -> tuple[int, str] | None:
    import io
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as doc:
        for page_no, page in enumerate(doc.pages, start=1):
            if len(page.images) < _MIN_LABEL_IMAGES or "[" not in (page.extract_text() or ""):
                continue
            text = label_image_rows(page, read_label)
            if text and pdf.find_summary_table([text], LABEL_TO_INDICATOR, REQUIRED_INDICATORS):
                return page_no, text
    return None


def collect_issue(issue: Issue) -> list[ForecastRecord]:
    """회차 하나의 본문에서 PDF를 받아 요약표를 읽는다."""
    pdf_url = parse_pdf_link(http.get(issue.url).text)
    data = http.get(pdf_url).content
    found = pdf.find_summary_table(pdf.page_texts(data), LABEL_TO_INDICATOR, REQUIRED_INDICATORS)
    if found is None:
        found = find_image_labeled_table(data)
    if found is None:
        raise ValueError(f"{issue.title}: 요약표 페이지를 찾지 못했다")
    page_no, text = found
    return parse(text, issue, pdf_url, page_no)


def collect(today: date) -> list[ForecastRecord]:
    return collect_issue(list_issues()[0])
