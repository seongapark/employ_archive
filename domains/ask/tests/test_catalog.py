import json
from pathlib import Path

from domains.ask.pipeline.models import (
    Capability, CapabilityLimit, Hypothesis, HypIndicator, Indicator,
    Phenomenon, SourceCatalog, SourceConflict)

DATA = Path(__file__).resolve().parent.parent / "data"


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def test_every_row_validates():
    for r in load("sources.json"):
        SourceCatalog(**r)
    cap = load("capabilities.json")
    for r in cap["capabilities"]:
        Capability(**r)
    for r in cap["limits"]:
        CapabilityLimit(**r)
    for r in load("conflicts.json"):
        SourceConflict(**r)
    o = load("ontology.json")
    for r in o["phenomena"]:
        Phenomenon(**r)
    for r in o["hypotheses"]:
        Hypothesis(**r)
    for r in o["indicators"]:
        Indicator(**r)
    for r in o["hyp_indicators"]:
        HypIndicator(**r)


def test_all_source_references_resolve():
    ids = {r["id"] for r in load("sources.json")}
    cap = load("capabilities.json")
    for r in cap["capabilities"] + cap["limits"]:
        assert r["source_id"] in ids, r["source_id"]
    for r in load("conflicts.json"):
        assert r["source_a"] in ids and r["source_b"] in ids
    for r in load("ontology.json")["indicators"]:
        assert r["source_id"] in ids, r["source_id"]


def test_three_archived_sources_are_the_ones_we_actually_collect():
    archived = {r["id"] for r in load("sources.json") if r["archived"]}
    assert archived == {"eaps", "est", "ei"}


def test_no_hypothesis_without_counter():
    # 기획서 §8 — 확증편향 기계화를 막는 등록 조건
    for h in load("ontology.json")["hypotheses"]:
        assert h["대립가설"], h["id"]


def test_rate_only_indicators_are_marked():
    ind = {r["id"]: r for r in load("ontology.json")["indicators"]}
    assert ind["IND_KGJ피보험자"]["compare_basis"] == "증감률만"
    assert ind["IND_사무직신규구인"]["compare_basis"] == "증감률만"


def test_youth_clerical_indicator_is_semiannual_and_unheld():
    ind = {r["id"]: r for r in load("ontology.json")["indicators"]}
    i = ind["IND_청년사무직취업자"]
    assert i["time_grain"] == "반기"
    assert i["data_status"] == "미보유"
