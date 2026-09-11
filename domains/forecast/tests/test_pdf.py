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


def test_unbold_line_restores_a_tripled_heading():
    assert pdf.unbold_line("<<<국국국내내내경경경제제제 전전전망망망>>>") == "<국내경제 전망>"


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


def _bolden(line: str) -> str:
    """PDF 가짜 볼드처럼 글자마다 3번씩 찍는다(공백은 그대로)."""
    return " ".join("".join(c * 3 for c in token) for token in line.split())


def test_parses_a_data_row_the_report_printed_in_bold():
    # 한국은행 추출본은 볼드를 글자 3중 인쇄로 내놓는다(픽스처의 제목 줄이 그렇다).
    # 지표 행이 볼드로 나오는 회차가 오면 라벨도 숫자도 못 읽어 수집이 통째로 실패한다.
    text = load("bok_2026-08_summary.txt")
    plain = [ln for ln in text.split("\n") if ln.startswith("취업자수증감")]
    assert plain, "픽스처에 취업자수증감 행이 있어야 한다"
    bolded = text.replace(plain[0], _bolden(plain[0]))

    got = pdf.parse_summary_table(bolded, BOK_LABELS)
    assert got[("emp_change", 2026, "annual")] == 14.0
    assert got[("emp_change", 2026, "h1")] == 11.0
    assert got[("emp_change", 2026, "h2")] == 18.0


def test_bold_undo_keeps_repeated_digits_of_a_thousands_separator():
    # 3중 인쇄를 되돌릴 때 000 을 0 으로 접으면 1,000 이 1,0 이 된다
    assert pdf.unbold_line(_bolden("경상수지(억달러) 1,231 1,910")) == "경상수지(억달러) 1,231 1,910"


def test_bold_undo_leaves_an_ordinary_line_alone():
    assert pdf.unbold_line("경상수지(억달러) 1,000 2,000") == "경상수지(억달러) 1,000 2,000"


def _lines(*rows):
    """(글, top) 들로 pdfplumber extract_text_lines 모양을 만든다(줄 높이 11)."""
    return [{"text": text, "top": top, "bottom": top + 11} for text, top in rows]


def test_paragraph_break_lands_between_items_not_inside_a_wrapped_one():
    # KDI 요약 쪽의 실측 모양 — 감김 6.5, 항목 사이 17. 표지도 마침표도 없다.
    got = pdf.text_with_paragraph_breaks(_lines(
        ("우리 경제는 반도체경기 호황에 힘입어", 100),
        ("2027년에도 2.2% 성장할 전망", 117.5),      # 감김(6.5)
        ("소비자물가는 국제유가 상승으로", 145),      # 새 항목(17)
        ("2.2%로 상승폭이 축소될 전망", 162.5),      # 감김(6.5)
    ))
    assert got == ("우리 경제는 반도체경기 호황에 힘입어\n"
                   "2027년에도 2.2% 성장할 전망\n"
                   "\n"
                   "소비자물가는 국제유가 상승으로\n"
                   "2.2%로 상승폭이 축소될 전망")


def test_no_break_when_the_page_has_no_clean_valley_between_the_two_gaps():
    # 간격이 7·9·11 로 이어져 감김과 문단 나눔이 안 갈린다. 이럴 때 빈 줄을
    # 넣으면 문장 한가운데를 항목 시작으로 만들 수 있다 — 아무것도 안 넣는다.
    got = pdf.text_with_paragraph_breaks(_lines(
        ("첫 줄", 100), ("둘째 줄", 118), ("셋째 줄", 138), ("넷째 줄", 160)))
    assert got == "첫 줄\n둘째 줄\n셋째 줄\n넷째 줄"


def test_one_unusually_tight_pair_does_not_define_the_wrap_gap():
    # 위첨자·겹친 줄처럼 유난히 붙은 자리가 하나 있으면, 그것을 감김 간격으로
    # 삼는 순간 임계가 바닥으로 내려가 감긴 줄마다 빈 줄이 들어간다.
    got = pdf.text_with_paragraph_breaks(_lines(
        ("본문 첫 줄", 100),
        ("유난히 붙은 줄", 112),      # 1.0 — 이상치
        ("감긴 줄 하나", 129.5),      # 6.5
        ("감긴 줄 둘", 147),          # 6.5
        ("새 항목이 시작한다", 175),   # 17
        ("그 항목의 감긴 줄", 192.5),  # 6.5
    ))
    assert got == ("본문 첫 줄\n유난히 붙은 줄\n감긴 줄 하나\n감긴 줄 둘\n"
                   "\n"
                   "새 항목이 시작한다\n그 항목의 감긴 줄")


def _tiny_pdf_placed(pages):
    """페이지마다 (글, y) 를 그 자리에 찍은 최소 PDF — 줄 간격을 시험한다."""
    objects = ["<</Type/Catalog/Pages 2 0 R>>", None]
    kids = []
    for i, placements in enumerate(pages):
        page_no = 3 + i * 2
        content = " ".join(
            f"BT /F1 12 Tf 20 {y} Td ({text}) Tj ET" for text, y in placements
        ).encode()
        objects.append(
            f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents {page_no + 1} 0 R"
            f"/Resources<</Font<</F1 {3 + len(pages) * 2} 0 R>>>>>>"
        )
        objects.append(f"<</Length {len(content)}>>stream\n".encode() + content + b"\nendstream")
        kids.append(f"{page_no} 0 R")
    objects[1] = f"<</Type/Pages/Kids[{' '.join(kids)}]/Count {len(pages)}>>"
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


def test_page_texts_with_breaks_takes_the_gaps_from_the_pdf_itself():
    # 12pt 글자라 줄 높이가 12 다 — y 를 15 씩 띄우면 간격 3(감김),
    # 35 씩 띄우면 간격 23(문단 나눔) 이 된다.
    data = _tiny_pdf_placed([[("Item one head", 180), ("wrapped tail", 165),
                              ("Item two head", 130), ("its wrapped tail", 115)]])
    assert pdf.page_texts_with_breaks(data) == [
        "Item one head\nwrapped tail\n\nItem two head\nits wrapped tail"]


def test_nul_characters_become_spaces_not_deletions():
    """실측: KDI 2024 상반기 PDF 는 공백 자리에 U+0000 을 내놓는다(그 회차에
    67개, 다른 문서엔 0개). 파이썬에서 NUL 은 공백이 아니라서 llm_verify 가
    경계를 뒤로 훑다 거기서 멈추고, 모델이 그 자리를 보통 공백으로 옮겨
    적으면 대조도 어긋난다. 지우면 낱말이 붙으므로 공백으로 바꾼다.
    """
    nul = chr(0)  # 테스트 파일 자체에는 진짜 NUL 을 넣지 않는다
    got = pdf.text_with_paragraph_breaks(_lines(
        (f"{nul}최근 우리 경제는{nul}높은 수출 증가세에", 100),
        ("힘입어 경기 부진이 완화되는 모습", 117.5),
        ("1/4분기 국내총생산은 수출 회복세가", 145),
        ("지속된 가운데 3.4% 증가", 162.5),
    ))
    assert got.startswith(" 최근 우리 경제는 높은 수출 증가세에")
    assert nul not in got


def _lines_at(*rows):
    """(글, top, bottom) 을 그대로 준다 — 줄이 겹치는 쪽을 만들 수 있다."""
    return [{"text": t, "top": top, "bottom": bottom} for t, top, bottom in rows]


# BOK 2026년 8월호 28쪽에서 그대로 읽은 줄 간격이다. 겹친 줄이 음수로
# 나오고(-7.1 등), 그것이 사분위를 끌어내려 임계가 감김(5.4~6.0)보다 낮아졌다.
# 그 결과 감긴 줄마다 문단 나눔이 들어가 문장 한가운데가 끊겼고
# ("…반도체 경기 호황과 그에 ‖ 따른 파급효과의…") 멀쩡한 한 문장이
# "여러 항목을 이어 붙였다" 로 거절됐다.
BOK_PAGE28_GAPS = [27.16, 18.94, 5.99, -7.1, 5.41, 5.98, -7.09, 5.41,
                   5.98, 5.99, 5.98, -7.1, 5.41, -7.1, 3.6, 5.99]


def _lines_from_gaps(gaps, height=11.0, top=100.0):
    lines = [{"text": "L0", "top": top, "bottom": top + height}]
    for i, gap in enumerate(gaps, start=1):
        top = lines[-1]["bottom"] + gap
        lines.append({"text": f"L{i}", "top": top, "bottom": top + height})
    return lines


def test_overlapping_lines_do_not_drag_the_wrap_gap_below_the_real_line_spacing():
    """음수 간격은 줄 간격이 아니다 — 겹쳐 나온 줄이다. 감김 간격을 고를 때
    빼야, 진짜 감김(5.4~6.0)이 문단 나눔으로 넘어가지 않는다."""
    got = pdf.text_with_paragraph_breaks(_lines_from_gaps(BOK_PAGE28_GAPS))

    # 큰 간격 두 곳(27.16, 18.94)에서만 갈린다
    assert got.count("\n\n") == 2
    assert got.startswith("L0\n\nL1\n\nL2\nL3\nL4")
    assert got.endswith("L15\nL16")


# ── 2단 편집 가르기 ───────────────────────────────────────────────────
# 왜 필요한가: 추출은 2단을 **한 줄에 이어 붙인다**. 실측(KLI 고용·노동브리프
# 제115호 2쪽) —
#     다. 성장의 대부분이 고용창출이 미미한 반도체 부문 화된 것으로 볼 수 있다.
# 앞이 왼쪽 단, 뒤가 오른쪽 단이다. 이런 원문에서 모델이 뜻이 통하는 문장을
# 만들면 원문의 부분열이 아니라 llm_verify 가 전부 '원문에 없다'로 거절한다
# (KLI 21자리 중 20이 그렇게 떨어졌다).

def _chars(spans, step=1.0):
    """(x0, x1) 구간들을 글자로 촘촘히 채운다.

    step 을 작게 둬 글자 수가 판정 하한(200)을 넘게 한다 — 그 하한은 표지처럼
    글자가 몇 개뿐인 쪽에서 우연한 공백을 단으로 보지 않으려는 것이다.
    """
    out = []
    for x0, x1 in spans:
        x = float(x0)
        while x < x1:
            out.append({"x0": x, "x1": min(x + step, x1)})
            x += step
    return out


def test_두_단_사이의_빈_띠를_찾는다():
    # 실측값: 쪽 폭 595, 단 사이가 x 350~361 로 **11pt** 뿐이다.
    chars = _chars([(30, 350), (361, 565)])
    assert 350 <= pdf.column_split(chars, 595.0) <= 361


def test_단_간격이_좁아도_잡는다():
    # 처음에 40pt 로 잡았다가 2단인데도 1단으로 읽혔다. 단 간격은 좁다.
    chars = _chars([(30, 292), (302, 565)])
    assert pdf.column_split(chars, 595.0) is not None


def test_한_단_쪽은_가르지_않는다():
    # 글자가 폭을 가로질러 이어지면 가운데에 빈 띠가 없다.
    assert pdf.column_split(_chars([(30, 565)]), 595.0) is None


def test_가장자리_여백은_단_경계가_아니다():
    # 바깥 여백(0~30)과 왼쪽 단 안의 들여쓰기는 가운데 구역 밖이라 안 걸린다.
    # 실측에서 x 128~141 에도 13pt 짜리 띠가 있었는데 그건 들여쓰기였다.
    chars = _chars([(30, 128), (141, 565)])
    assert pdf.column_split(chars, 595.0) is None


def test_글자가_적은_쪽은_판정하지_않는다():
    # 표지·간지처럼 글자가 몇 개뿐인 쪽에서 우연한 공백을 단으로 보면 안 된다.
    sparse = _chars([(30, 100), (400, 470)], step=5.0)
    assert len(sparse) < 200
    assert pdf.column_split(sparse, 595.0) is None
