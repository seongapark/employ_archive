import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

def test_indicators_has_seven_codes():
    rows = json.loads((DATA / "indicators.json").read_text(encoding="utf-8"))
    codes = {r["code"] for r in rows}
    assert codes == {"emp_change", "emp_rate", "unemp_rate", "gdp_growth",
                     "cpi", "emp_rate_youth", "labor_force"}
    for r in rows:
        assert set(r) == {"code", "name_ko", "unit", "decimals", "range"}
        lo, hi = r["range"]
        assert lo < hi

def test_orgs_has_nine_orgs_with_tracks():
    rows = json.loads((DATA / "orgs.json").read_text(encoding="utf-8"))
    assert {r["org"] for r in rows} == {"BOK", "KDI", "KLI", "MOEF", "IMF",
                                        "OECD", "ADB", "KIET", "KEIS"}
    assert all(r["track"] in ("A", "B") for r in rows)
