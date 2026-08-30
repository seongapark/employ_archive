import io
import zipfile
from pathlib import Path

import pytest

from domains.employment.pipeline import hwpx

FIXTURE = Path(__file__).parent / "fixtures" / "ei_2026-07.hwpx"


@pytest.fixture(scope="module")
def data():
    return FIXTURE.read_bytes()


def test_reads_many_tables(data):
    tables = hwpx.tables(data)
    assert len(tables) > 50


def test_finds_the_industry_level_table(data):
    tables = hwpx.tables(data)
    # 헤더 라벨은 셀 안에서 두 문단으로 줄바꿈되기도 한다("농림"+"어업").
    # 문단은 이제 공백으로 이어지므로("농림 어업") 키워드 매칭 전에 셀 안
    # 공백만 지운다. 셀 사이는 띄운 채로 둔다 — 전부 이어붙이면 키워드가
    # 두 셀 경계를 걸쳐 가짜로 매칭될 수 있다(앞 셀 끝 '산' + 뒤 셀 시작 '업').
    def flat(header):
        return " ".join(cell.replace(" ", "") for cell in header)

    hits = [t for t in tables
            if t and len(t[0]) > 5
            and all(k in flat(t[0]) for k in ("전산업", "농림어업", "제조업"))]
    assert len(hits) >= 2          # 수준 표와 증감 표
    assert hits[0][-1][1].replace(",", "").isdigit()


def test_reads_every_section_not_just_the_first():
    # section0 만 읽으면 뒤 섹션의 표를 통째로 놓친다. 두 섹션짜리 문서를
    # 만들어 양쪽 표가 모두 나오는지 확인한다.
    def section(text):
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
            ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
            f'<hp:tbl><hp:tr><hp:tc><hp:t>{text}</hp:t></hp:tc></hp:tr></hp:tbl>'
            '</hs:sec>'
        ).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Contents/section0.xml", section("첫째"))
        z.writestr("Contents/section1.xml", section("둘째"))
    tables = hwpx.tables(buf.getvalue())
    assert [t[0][0] for t in tables] == ["첫째", "둘째"]


def test_orders_sections_numerically_not_alphabetically():
    # 문자열 정렬은 section10 을 section2 앞에 놓는다.
    def section(text):
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
            ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
            f'<hp:tbl><hp:tr><hp:tc><hp:t>{text}</hp:t></hp:tc></hp:tr></hp:tbl>'
            '</hs:sec>'
        ).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Contents/section10.xml", section("열"))
        z.writestr("Contents/section2.xml", section("둘"))
    assert [t[0][0] for t in hwpx.tables(buf.getvalue())] == ["둘", "열"]


def test_nested_tables_are_not_absorbed_into_the_outer_one():
    # .iter() 로 행을 모으면 바깥 표가 안쪽 행까지 가져가고, 안쪽 표는 또 따로 나온다.
    inner = ('<hp:tbl><hp:tr><hp:tc><hp:t>안쪽</hp:t></hp:tc></hp:tr></hp:tbl>')
    payload = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
        ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
        f'<hp:tbl><hp:tr><hp:tc><hp:t>바깥</hp:t>{inner}</hp:tc></hp:tr></hp:tbl>'
        '</hs:sec>'
    ).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Contents/section0.xml", payload)

    result = hwpx.tables(buf.getvalue())
    outer, nested = result[0], result[1]
    assert outer == [["바깥"]]      # 안쪽 행을 빨아들이지 않는다
    assert nested == [["안쪽"]]     # 중첩 표는 자기 항목으로 나온다


def test_paragraphs_in_a_cell_are_separated(data):
    # 구분자 없이 이으면 "(044-202-7256)(044-202-7247)…" 처럼 뭉쳐 값이 깨진다
    joined = " ".join(" ".join(" ".join(r) for r in t) for t in hwpx.tables(data))
    assert "(044-202-7256) (044-202-7247) (044-202-7287) (044-202-7255)" in joined
