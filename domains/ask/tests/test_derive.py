import json
from pathlib import Path

from domains.ask.pipeline.derive import derive_capabilities, derive_conflicts, 은는

EMP = Path(__file__).resolve().parents[2] / "employment" / "data"


def emp(name):
    return json.loads((EMP / name).read_text(encoding="utf-8"))


def test_est_has_no_sex_or_age_axis():
    caps, _ = derive_capabilities(emp("segments.json"), emp("industries.json"),
                                  emp("sources.json"))
    est = {c["source_id"]: c for c in caps}["est"]
    assert "성" not in est["집단축"] and "연령" not in est["집단축"]
    assert "산업" in est["집단축"]


def test_est_missing_axes_become_cross_limits():
    _, limits = derive_capabilities(emp("segments.json"), emp("industries.json"),
                                    emp("sources.json"))
    rows = [l for l in limits if l["source_id"] == "est" and l["유형"] == "교차제한"]
    assert {r["axis"] for r in rows} == {"성", "연령"}


def test_ei_industry_gaps_become_granularity_limits():
    _, limits = derive_capabilities(emp("segments.json"), emp("industries.json"),
                                    emp("sources.json"))
    rows = [l for l in limits if l["source_id"] == "ei" and l["유형"] == "입도"]
    assert {r["category"] for r in rows} == {"B", "T", "U"}


def test_every_pair_is_rate_only():
    rows = derive_conflicts(emp("sources.json"))
    assert {(r["source_a"], r["source_b"]) for r in rows} == {
        ("eaps", "est"), ("eaps", "ei"), ("est", "ei")}
    assert {r["비교가능"] for r in rows} == {"증감률만"}


def test_particle_follows_final_consonant():
    # 이 설명 문장은 compare().설명 → 카드.한계 를 타고 화면과 LLM 프롬프트 양쪽에
    # 그대로 나간다. 받침 있는 이름 뒤에 `는` 이 붙던 자리("…노동시장 동향는…").
    assert 은는("고용행정 통계로 본 노동시장 동향") == "은"   # 향: 받침 있음
    assert 은는("경제활동인구조사") == "는"                    # 사: 받침 없음
    assert 은는("") == "는"
    assert 은는("KOSIS") == "는"                               # 한글이 아니면 판정 안 한다

    rows = derive_conflicts(emp("sources.json"))
    for r in rows:
        assert "동향는" not in r["설명"]
    개념 = [r for r in rows
            if (r["source_a"], r["source_b"]) == ("eaps", "ei") and r["차이유형"] == "개념"]
    assert "동향은 상시가입자수" in 개념[0]["설명"]


def test_concept_and_population_are_separate_rows():
    rows = [r for r in derive_conflicts(emp("sources.json"))
            if (r["source_a"], r["source_b"]) == ("eaps", "ei")]
    assert {r["차이유형"] for r in rows} == {"개념", "모집단"}
