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
    hits = [t for t in tables
            if t and len(t[0]) > 5
            and all(k in " ".join(t[0]) for k in ("전산업", "농림어업", "제조업"))]
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
