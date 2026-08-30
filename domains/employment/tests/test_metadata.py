import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

SOURCES = {"eaps", "est", "ei"}
KSIC = list("ABCDEFGHIJKLMNOPQRSTU")


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def test_sources_has_the_three_sources_with_every_field():
    rows = load("sources.json")
    assert {r["code"] for r in rows} == SOURCES
    for r in rows:
        assert set(r) == {"code", "name_ko", "agency", "type", "headline_ko",
                          "coverage", "release_rule", "caveat", "board_url"}
        assert r["board_url"].startswith("https://")
        assert r["coverage"].strip()


def test_each_source_has_its_own_headline_name():
    rows = {r["code"]: r for r in load("sources.json")}
    names = {rows[c]["headline_ko"] for c in SOURCES}
    # 세 값을 같은 이름으로 부르면 이 앱의 존재 이유가 사라진다
    assert len(names) == 3
    assert rows["ei"]["headline_ko"] == "상시가입자수"


def test_industries_covers_every_ksic_major_division():
    rows = load("industries.json")
    assert [r["code"] for r in rows] == KSIC


def test_industries_declare_provision_per_source():
    for r in load("industries.json"):
        assert set(r["provided"]) == SOURCES
        assert all(isinstance(v, bool) for v in r["provided"].values())


def test_known_gaps_are_recorded():
    by_code = {r["code"]: r["provided"] for r in load("industries.json")}
    # 경활은 광업을 '광공업'에 묶어 단독 제공하지 않는다
    assert by_code["B"]["eaps"] is False
    # 사업체노동력조사는 농림어업·가구내고용·국제기관을 조사하지 않는다
    assert by_code["A"]["est"] is False
    assert by_code["T"]["est"] is False
    assert by_code["U"]["est"] is False
    # 고용행정통계는 광업·가구내고용·국제기관을 '기타'로 묶는다
    assert by_code["B"]["ei"] is False
    # 제조업·건설업·보건복지는 세 출처 모두 제공한다
    for code in ("C", "F", "Q"):
        assert all(by_code[code].values()), code
