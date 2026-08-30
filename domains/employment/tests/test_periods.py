from domains.employment.pipeline.periods import month_rows, squash


def test_squash_removes_every_space():
    assert squash(" 농림 어업 ") == "농림어업"
    assert squash(None) == ""


def test_reads_a_month_start_row_and_the_bare_months_after_it():
    rows = [["2024.  7", "a"], ["8", "b"], ["9", "c"]]
    assert [p for p, _ in month_rows(rows)] == ["2024-07", "2024-08", "2024-09"]


def test_a_new_year_row_switches_the_year():
    rows = [["2025.  12", "a"], ["2026.  1", "b"], ["2", "c"]]
    assert [p for p, _ in month_rows(rows)] == ["2025-12", "2026-01", "2026-02"]


def test_annual_and_quarterly_rows_are_dropped():
    rows = [["2021", "a"], ["2025", "b"], ["2026.1/4", "c"], ["2/4", "d"]]
    assert month_rows(rows) == []


def test_a_blank_row_ends_the_year_context():
    # 표의 블록 경계다. 이어지면 연평균 블록 뒤의 숫자가 엉뚱한 해에 붙는다.
    rows = [["2024.  7", "a"], ["", ""], ["8", "b"]]
    assert [p for p, _ in month_rows(rows)] == ["2024-07"]


def test_a_bare_month_before_any_year_is_ignored():
    assert month_rows([["8", "a"]]) == []
