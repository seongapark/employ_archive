import pytest

from domains.forecast.pipeline import rationale

# 아래 문장은 KEIS 2026년 제5호 20쪽에서 그대로 딴 것이다.
REASON = ("2026년 하반기 취업자 수 증가 배경에는 상반기 고용시장의 완만한 "
          "회복 흐름과 경기 개선 기대가 자리한 것으로 전망된다.")
RESTATEMENT = "하반기 취업자 수는 전년 동기 대비 약 18만 5천 명 증가할 것으로 예상되며"
OTHER_INDICATOR = ("생산가능인구는 하반기에도 전년 동기 대비 0.4% 증가세를 "
                   "이어갈 것으로 예상되나, 대부분은 60세 이상 고령층이다.")


def test_pick_takes_the_sentence_that_gives_a_reason():
    assert rationale.pick(REASON, "emp_change") == REASON.strip()


def test_pick_rejects_a_restatement_of_the_number():
    # 지표와 전망 표지는 있으나 인과 표지가 없다
    assert rationale.pick(RESTATEMENT, "emp_change") is None


def test_pick_rejects_a_sentence_about_another_indicator():
    assert rationale.pick(OTHER_INDICATOR, "emp_change") is None


def test_pick_rejects_a_sentence_with_cause_and_forecast_for_another_indicator():
    # 인과·전망 표지는 다 있으나 지표 표제어가 없다 — 지표 조건 하나만 따로 지킨다.
    # (위 test_pick_rejects_a_sentence_about_another_indicator 의 문장은 인과 표지도
    # 없어 지표 조건을 빼도 통과하므로, 그 조건만 걸러내는 문장을 따로 둔다.)
    other = "소비자물가는 국제유가 하락 영향으로 하락할 것으로 전망된다."
    assert rationale.pick(other, "emp_change") is None


def test_pick_needs_a_forecast_marker():
    # 인과 표지는 있으나 지난 일을 말한다
    past = "상반기 취업자 증가는 건설경기 부진 완화에 기인했다."
    assert rationale.pick(past, "emp_change") is None


def test_pick_takes_the_first_when_several_qualify():
    first = "취업자 증가는 내수 회복에 힘입어 이어질 것으로 전망된다."
    second = "취업자 증가는 수출 호조를 반영해 확대될 것으로 예상된다."
    assert rationale.pick(f"{first} {second}", "emp_change") == first


def test_pick_reads_english_reports():
    en = ("Employment growth is projected to remain solid, supported by "
          "resilient domestic demand.")
    assert rationale.pick(en, "emp_change") == en


def test_pick_returns_none_for_text_without_any_reason():
    assert rationale.pick("표는 다음과 같다.", "emp_change") is None
