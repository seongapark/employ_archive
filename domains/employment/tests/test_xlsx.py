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


def test_places_cells_by_coordinate_not_document_order(data):
    # 빈 셀을 건너뛰고 순서대로 이어붙이는 리더는 이 셀을 앞으로 당겨 놓는다.
    # 값이 어딘가에 있는지가 아니라 '몇 번 열에 있는지'를 봐야 판별이 된다.
    rows = xlsx.read_sheet(data, "3.산업(신)")
    assert rows[2][11] == "(단위: 천명)"


def test_unknown_sheet_raises(data):
    with pytest.raises(KeyError):
        xlsx.read_sheet(data, "없는시트")


def test_malformed_cell_reference_fails_loudly():
    from domains.employment.pipeline.xlsx import _col_index
    with pytest.raises(ValueError, match="셀 참조"):
        _col_index("")
