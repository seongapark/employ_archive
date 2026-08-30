from pathlib import Path

import pytest

from domains.forecast.pipeline import pdf

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


BOK_LABELS = {
    "GDP성장률": "gdp_growth",
    "소비자물가상승률": "cpi",
    "취업자수증감": "emp_change",
    "실업률": "unemp_rate",
    "고용률": "emp_rate",
}
KDI_LABELS = {
    "국내총생산": "gdp_growth",
    "소비자물가": "cpi",
    "취업자수(증감)": "emp_change",
    "실업률": "unemp_rate",
}


def test_normalize_bold_collapses_tripled_heading():
    assert pdf.normalize_bold("<<<국국국내내내경경경제제제 전전전망망망>>>") == "<국내경제 전망>"


def test_parses_bok_seven_column_layout():
    got = pdf.parse_summary_table(load("bok_2026-08_summary.txt"), BOK_LABELS)
    assert got[("emp_change", 2026, "annual")] == 14.0
    assert got[("emp_change", 2026, "h1")] == 11.0
    assert got[("emp_change", 2026, "h2")] == 18.0
    assert got[("emp_rate", 2027, "annual")] == 63.0
    assert got[("gdp_growth", 2026, "annual")] == 3.3


def test_parses_kdi_six_column_layout():
    got = pdf.parse_summary_table(load("kdi_2026-05_summary.txt"), KDI_LABELS)
    assert got[("emp_change", 2026, "annual")] == 17.0
    assert got[("gdp_growth", 2026, "annual")] == 2.5
    assert got[("cpi", 2027, "annual")] == 2.2
    assert got[("unemp_rate", 2024, "annual")] == 2.8


def test_kdi_revision_columns_are_not_read_as_values():
    got = pdf.parse_summary_table(load("kdi_2026-08_summary.txt"), KDI_LABELS)
    assert got[("gdp_growth", 2026, "annual")] == 3.2
    assert got[("gdp_growth", 2027, "annual")] == 2.2
    # 수정폭 열(0.7, 0.5)이 값으로 새어 들어오면 안 된다
    assert {year for _, year, _ in got} == {2025, 2026, 2027}
    assert {period for _, _, period in got} == {"annual", "h1", "h2"}


def test_bok_bracketed_revisions_are_not_read_as_values():
    got = pdf.parse_summary_table(load("bok_2026-08_summary.txt"), BOK_LABELS)
    assert got[("cpi", 2026, "annual")] == 2.7  # 뒤에 [ - ] 가 붙은 행
    assert {period for _, _, period in got} == {"annual", "h1", "h2"}


def test_strips_dot_leaders_left_by_bok_may_issue():
    # 5월호는 '....18' 처럼 점 리더가 숫자 앞에 붙어 추출된다
    got = pdf.parse_summary_table(load("bok_2026-05_summary.txt"), BOK_LABELS)
    assert got[("emp_change", 2026, "annual")] == 18.0
    assert got[("unemp_rate", 2027, "annual")] == 2.8


def test_raises_when_year_and_period_headers_disagree():
    broken = load("kdi_2026-05_summary.txt").replace(
        "2024p 2025p 2026 2027", "2024p 2025p 2026"
    )
    with pytest.raises(ValueError):
        pdf.parse_summary_table(broken, KDI_LABELS)


BOK_REQUIRED = {"gdp_growth", "cpi", "emp_change", "unemp_rate"}


def test_find_summary_table_returns_one_based_page_number():
    pages = ["표지", "머리말", load("bok_2026-08_summary.txt")]
    page_no, text = pdf.find_summary_table(pages, BOK_LABELS, BOK_REQUIRED)
    assert page_no == 3
    assert "취업자수증감" in text.replace(" ", "")


def test_find_summary_table_skips_partial_tables():
    # 성장률·물가만 실린 앞쪽 요약 표는 건너뛰고 지표가 다 있는 표를 찾아야 한다
    partial = (
        "2025 2026e) 2027e)\n"
        "연간 상반 하반 연간 상반 하반 연간\n"
        "GDP성장률(%) 1.1 3.8 3.0 3.3 2.5 3.2 2.9\n"
    )
    pages = [partial, load("bok_2026-08_summary.txt")]
    page_no, _ = pdf.find_summary_table(pages, BOK_LABELS, BOK_REQUIRED)
    assert page_no == 2


def test_find_summary_table_ignores_pages_whose_header_does_not_parse():
    pages = ["연간 상반기 하반기 없는 연도 헤더", load("kdi_2026-05_summary.txt")]
    page_no, _ = pdf.find_summary_table(pages, KDI_LABELS, {"emp_change"})
    assert page_no == 2


def test_find_summary_table_returns_none_when_no_page_qualifies():
    assert pdf.find_summary_table(["표지", "머리말"], BOK_LABELS, BOK_REQUIRED) is None


def _tiny_pdf(page_texts_):
    """텍스트 한 줄짜리 페이지들로 이루어진 최소 PDF 바이트를 만든다."""
    objects = ["<</Type/Catalog/Pages 2 0 R>>", None]  # 2번은 Kids 확정 후 채운다
    kids = []
    for i, body in enumerate(page_texts_):
        page_no = 3 + i * 2
        content = f"BT /F1 12 Tf 20 100 Td ({body}) Tj ET".encode()
        objects.append(
            f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/Contents {page_no + 1} 0 R"
            f"/Resources<</Font<</F1 {3 + len(page_texts_) * 2} 0 R>>>>>>"
        )
        objects.append(f"<</Length {len(content)}>>stream\n".encode() + content + b"\nendstream")
        kids.append(f"{page_no} 0 R")
    objects[1] = f"<</Type/Pages/Kids[{' '.join(kids)}]/Count {len(page_texts_)}>>"
    objects.append("<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        body = obj if isinstance(obj, bytes) else obj.encode()
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (f"trailer<</Size {len(objects) + 1}/Root 1 0 R>>\n"
            f"startxref\n{xref_at}\n%%EOF\n").encode()
    return bytes(out)


def test_page_texts_returns_one_string_per_page_in_order():
    assert pdf.page_texts(_tiny_pdf(["Page one", "Page two"])) == ["Page one", "Page two"]


def test_raises_when_a_period_column_has_no_year_to_attach_to():
    # 표가 아닌 페이지가 '하반기'로 시작하는 헤더처럼 보일 수 있다.
    # AttributeError로 터지면 페이지 탐색이 중단되므로 ValueError여야 한다.
    with pytest.raises(ValueError):
        pdf.parse_summary_table("2026\n하반기 연간\n국내총생산 1.0 2.0\n", KDI_LABELS)
