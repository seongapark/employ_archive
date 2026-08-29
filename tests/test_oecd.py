from datetime import date
from pathlib import Path
from src.collectors import oecd

FIXTURE = (Path(__file__).parent / "fixtures" / "oecd_eo119_kor.csv").read_text(
    encoding="utf-8"
)
TODAY = date(2026, 8, 29)


def by_key(records):
    return {(r.indicator, r.target_year): r for r in records}


def test_parse_maps_measures_and_rounds():
    got = by_key(oecd.parse(FIXTURE, TODAY))
    assert got[("gdp_growth", 2026)].value == 2.6
    assert got[("gdp_growth", 2027)].value == 1.9
    assert got[("unemp_rate", 2026)].value == 2.8
    assert got[("cpi", 2027)].value == 2.2


def test_parse_derives_emp_change_from_et_levels():
    got = by_key(oecd.parse(FIXTURE, TODAY))
    assert got[("emp_change", 2026)].value == 20.5  # (28974095.855-28769250)/1e4
    assert got[("emp_change", 2027)].value == 12.3
    assert got[("emp_change", 2026)].unit == "만명"


def test_parse_record_fields():
    r = by_key(oecd.parse(FIXTURE, TODAY))[("gdp_growth", 2027)]
    assert r.id == "oecd-2026-08-gdp_growth-2027"
    assert r.report_title == "Economic Outlook 119"
    assert r.org == "OECD"
    assert r.confidence == "verified"
    assert r.published_at == TODAY


def test_parse_covers_current_and_next_year_only():
    years = {r.target_year for r in oecd.parse(FIXTURE, TODAY)}
    assert years == {2026, 2027}


def test_parse_skips_blank_obs_value():
    blank_row = (
        "DATAFLOW,OECD.ECO.MAD:DSD_EO@DF_EO(1.5),Economic Outlook 119,I,KOR,Korea,"
        "CPI_YTYPCT,Headline inflation,A,Annual,2026,,\n"
    )
    augmented = FIXTURE + blank_row
    got = by_key(oecd.parse(augmented, TODAY))
    assert got[("gdp_growth", 2026)].value == 2.6
    assert got[("gdp_growth", 2027)].value == 1.9
    assert got[("unemp_rate", 2026)].value == 2.8
    assert got[("cpi", 2027)].value == 2.2
    assert got[("cpi", 2026)].value == 2.6  # unaffected by the blank row
