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

def test_orgs_has_eight_orgs_with_tracks():
    rows = json.loads((DATA / "orgs.json").read_text(encoding="utf-8"))
    # ADB 는 2026-09-10 에 출처 대상에서 뺐다(사용자 결정) — 고용 지표가 없고
    # 한국 페이지가 JS 렌더링이라 ADO 본편 PDF 를 따로 파싱해야 했다.
    assert {r["org"] for r in rows} == {"BOK", "KDI", "KLI", "MOEF", "IMF",
                                        "OECD", "KIET", "KEIS"}
    assert all(r["track"] in ("A", "B") for r in rows)

def test_every_org_has_a_short_name_that_fits_a_bar_label():
    # 홈의 기관별 막대그래프는 막대 아래에 기관명을 적는다. 여섯 기관이면
    # 한 칸이 55px 뿐이라 긴 이름은 옆 칸을 침범한다(5자 이하로 못박는다).
    # 약칭은 화면이 지어내지 않고 여기 데이터가 갖는다 — 고용동향 도메인의
    # sources.json/industries.json 과 같은 규칙이다.
    rows = json.loads((DATA / "orgs.json").read_text(encoding="utf-8"))
    for r in rows:
        assert r["short_ko"], r["org"]
        assert len(r["short_ko"]) <= 5, (r["org"], r["short_ko"])
