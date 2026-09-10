"""IMF WEO 과거 전망 엑셀 판독.

이 경로가 있는 이유: SDMX 아카이브에는 vintage 가 하나뿐이고(다른 이름은 전부
404) DataMapper 는 현행 회차만 준다. 지난 회차는 이 엑셀에서만 온다.

xlsx 는 zip 안의 XML 이라 표준 라이브러리로 읽는다(openpyxl 을 의존성에 넣지
않는다). 그래서 여기 픽스처도 그 XML 을 직접 만든다 — 실물의 열 규칙을 그대로
본떴다: 열 이름이 `S<연도>`(4월판)·`F<연도>`(10월판)이고, 값이 없는 칸은 `.` 다.
"""
import io
import zipfile

import pytest

from domains.forecast.pipeline.collectors import imf

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
REL = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'

HEADERS = ["country", "WEO_Country_Code", "ISOAlpha_3Code", "year",
           "F2024ngdp_rpch", "S2025ngdp_rpch", "S2026ngdp_rpch"]
COLUMNS = "ABCDEFG"


def _row(index, values, string_index):
    cells = []
    for col, value in zip(COLUMNS, values):
        if value is None:
            continue
        if value in string_index:
            cells.append(f'<c r="{col}{index}" t="s"><v>{string_index[value]}</v></c>')
        else:
            cells.append(f'<c r="{col}{index}" ><v>{value}</v></c>')
    return f'<row r="{index}">{"".join(cells)}</row>'


def build_xlsx(rows, sheet_name="ngdp_rpch"):
    """헤더 + rows 로 최소한의 xlsx 를 만든다. rows 는 문자열 리스트의 리스트."""
    strings = list(dict.fromkeys(
        [sheet_name, *HEADERS] + [v for row in rows for v in row if not _is_number(v)]
    ))
    index = {s: i for i, s in enumerate(strings)}
    body = [_row(1, HEADERS, index)]
    body += [_row(i, row, index) for i, row in enumerate(rows, start=2)]

    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as zf:
        zf.writestr("xl/sharedStrings.xml",
                    f'<sst {NS}>' + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
        zf.writestr("xl/_rels/workbook.xml.rels",
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        zf.writestr("xl/workbook.xml",
                    f'<workbook {NS} {REL}><sheets>'
                    f'<sheet name="{sheet_name}" r:id="rId1"/></sheets></workbook>')
        zf.writestr("xl/worksheets/sheet1.xml",
                    f'<worksheet {NS}><sheetData>{"".join(body)}</sheetData></worksheet>')
    return data.getvalue()


def _is_number(value):
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


KOREA = [
    ["Korea", "542", "KOR", "2025", "2.1661", "1.0274", "1.0070"],
    ["Korea", "542", "KOR", "2026", "2.1594", "1.4474", "1.8623"],
]
JAPAN = [["Japan", "158", "JPN", "2025", "1.1", "0.6", "0.7"]]


def test_회차_열을_전망연도별로_읽는다():
    got = imf.read_historical(build_xlsx(KOREA + JAPAN), "ngdp_rpch")
    assert got["S2025"] == {2025: 1.0274, 2026: 1.4474}
    assert got["F2024"] == {2025: 2.1661, 2026: 2.1594}


def test_다른_나라_행을_섞지_않는다():
    got = imf.read_historical(build_xlsx(KOREA + JAPAN), "ngdp_rpch")
    # 일본의 0.6 이 S2025 에 섞이면 안 된다
    assert 0.6 not in got["S2025"].values()


def test_값이_없는_칸은_점으로_온다():
    rows = [["Korea", "542", "KOR", "2027", ".", "2.0988", "2.1235"]]
    got = imf.read_historical(build_xlsx(rows), "ngdp_rpch")
    assert "F2024" not in got, "'.' 을 값으로 읽으면 float() 에서 죽는다"
    assert got["S2025"] == {2027: 2.0988}


def test_없는_시트는_시끄럽게_실패한다():
    with pytest.raises(ValueError, match="시트가 없다"):
        imf.read_historical(build_xlsx(KOREA), "pcpi_pch")


def test_머리글이_바뀌면_실패한다():
    global HEADERS
    original = HEADERS
    HEADERS = ["country", "code", "iso", "yr", "F2024x", "S2025x", "S2026x"]
    try:
        with pytest.raises(ValueError, match="머리글이 바뀌었다"):
            imf.read_historical(build_xlsx(KOREA), "ngdp_rpch")
    finally:
        HEADERS = original


def test_한국_행이_없으면_실패한다():
    with pytest.raises(ValueError, match="행을 찾지 못했다"):
        imf.read_historical(build_xlsx(JAPAN), "ngdp_rpch")


def test_회차표는_기재부로_확인한_것만_싣는다():
    # 발표일을 짐작해 넣으면 그 회차의 수정 이력이 통째로 어긋난다.
    assert imf.HISTORICAL_VINTAGES["F2024"][1].isoformat() == "2024-10-22"
    assert imf.HISTORICAL_VINTAGES["S2025"][1].isoformat() == "2025-04-22"


def test_과거_엑셀에는_실업률이_없다():
    # 시트가 성장률·물가·경상수지뿐이다. 실업률까지 채워진다고 착각하면
    # IMF 실업률이 한 회차뿐인 이유를 다음 사람이 버그로 오해한다.
    assert set(imf.HISTORICAL_SHEETS.values()) == {"gdp_growth", "cpi"}
