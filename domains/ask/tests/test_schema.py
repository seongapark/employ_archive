import re
from pathlib import Path

SQL = (Path(__file__).resolve().parent.parent / "worker" / "migrations"
       / "0001_init.sql").read_text(encoding="utf-8")

TABLES = {"source_catalog", "capability", "capability_limit", "source_conflict",
          "phenomenon", "hypothesis", "indicator", "hyp_indicator",
          "observation", "forecast", "forecast_rationale", "release"}


def test_twelve_tables():
    found = set(re.findall(r"CREATE TABLE (?:IF NOT EXISTS )?(\w+)", SQL))
    assert found == TABLES
    assert len(found) == 12


def test_observation_separates_rse_value_from_flag():
    # 기호를 안 담으면 "공표 안 함" 과 "아직 안 긁음" 이 둘 다 NULL 로 뭉개진다
    body = re.search(r"CREATE TABLE observation(.*?);", SQL, re.S).group(1)
    assert "rse REAL" in body
    assert "rse_flag TEXT" in body


def test_verdict_view_exposes_blocked_by():
    assert "CREATE VIEW hypothesis_verdict" in SQL
    assert "verdict_blocked_by" in SQL
    assert "반증미설계" in SQL and "데이터미보유" in SQL


def test_verdict_strength_is_null_when_incapable():
    view = SQL[SQL.index("CREATE VIEW hypothesis_verdict"):]
    # 판정 불가면 weak 이 아니라 NULL 이어야 한다
    assert re.search(r"WHEN NOT \(f\.n_falsify > 0 AND f\.n_missing = 0\) THEN NULL", view)


def test_indexes_exist():
    idx = set(re.findall(r"CREATE INDEX (?:IF NOT EXISTS )?(\w+)", SQL))
    assert {"idx_obs", "idx_obs_period", "idx_fc", "idx_lim"} <= idx
