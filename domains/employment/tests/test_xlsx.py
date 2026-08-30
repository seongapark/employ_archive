from pathlib import Path

import pytest

from domains.employment.pipeline import xlsx

FIXTURE = Path(__file__).parent / "fixtures" / "eaps_2026-07.xlsx"


@pytest.fixture(scope="module")
def data():
    return FIXTURE.read_bytes()


def test_lists_the_industry_sheets(data):
    names = xlsx.sheet_names(data)
    for wanted in ["3.산업(신)", "3.산업(신) (2)", "3.산업증감(신)", "3.산업증감(신) (2)"]:
        assert wanted in names


def test_reads_the_industry_level_sheet(data):
    rows = xlsx.read_sheet(data, "3.산업(신)")
    joined = " ".join(" ".join(r) for r in rows[:8])
    assert "산업별 취업자" in joined
    assert "제조업" in joined
    assert "건설업" in joined


def test_keeps_empty_cells_in_place(data):
    # 빈 셀을 건너뛰면 산업 열이 통째로 밀린다. 헤더 행에 빈 칸이 남아 있어야 한다.
    rows = xlsx.read_sheet(data, "3.산업(신)")
    header = rows[3]
    assert "" in header


def test_unknown_sheet_raises(data):
    with pytest.raises(KeyError):
        xlsx.read_sheet(data, "없는시트")
