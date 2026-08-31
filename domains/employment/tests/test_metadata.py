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


def test_industries_metadata_matches_what_the_collectors_produce():
    # provided 가 화면의 '미제공' 판정 근거다. 수집기와 어긋나면 실제 공백이
    # 허깨비 공백으로, 또는 그 반대로 표시된다.
    from domains.employment.pipeline.collectors import eaps, est, ei
    provided = {s: {r["code"] for r in load("industries.json") if r["provided"][s]}
                for s in SOURCES}
    assert provided["eaps"] == set(eaps.INDUSTRY_COLUMNS.values())
    assert provided["est"] == est.EXPECTED_CODES
    assert provided["ei"] == ei.EXPECTED_CODES


def test_segments_cover_sex_and_age_with_every_source_flagged():
    segments = load("segments.json")
    by_breakdown = {s["breakdown"]: s for s in segments}
    assert set(by_breakdown) == {"sex", "age"}
    assert [c["code"] for c in by_breakdown["sex"]["categories"]] == ["M", "F"]
    assert [c["code"] for c in by_breakdown["age"]["categories"]] == [
        "15-29", "30-39", "40-49", "50-59", "60+"]
    for segment in segments:
        for category in segment["categories"]:
            assert set(category["provided"]) == {"eaps", "est", "ei"}
            assert category["provided"]["est"] is False, "사업체노동력조사는 공표하지 않는다"
            assert category["provided"]["eaps"] and category["provided"]["ei"]


def test_segment_codes_match_the_collected_records():
    series = load("series.json")
    segments = load("segments.json")
    for segment in segments:
        declared = {c["code"] for c in segment["categories"]}
        collected = {r["category"] for r in series if r["breakdown"] == segment["breakdown"]}
        assert collected <= declared, f"{segment['breakdown']}: 선언되지 않은 분류 {collected - declared}"
