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


def test_pick_keeps_a_sentence_whole_across_a_decimal_point():
    # 소수점(0.3%p)을 문장 끝으로 착각하면 인용문이 숫자 한가운데서 끊겨
    # 주어를 잃는다 — 전망 보고서는 이런 소수 표기가 흔하다
    s = ("2026년 하반기 취업자 수는 상반기 대비 0.3%p 개선되었으며 이는 "
         "고용시장 회복 흐름에 힘입어 확대될 것으로 전망된다.")
    assert rationale.pick(s, "emp_change") == s


def test_pick_does_not_let_emp_rate_and_emp_change_share_a_sentence():
    # "고용" 은 "고용률" 안에 들어 있다 — 두 지표가 같은 문장을 훔치면 안 된다
    s = "고용률 상승은 서비스업 고용 확대 흐름을 반영해 개선될 것으로 전망된다."
    assert rationale.pick(s, "emp_rate") == s
    assert rationale.pick(s, "emp_change") is None


def test_pick_does_not_let_emp_change_steal_an_emp_rate_sentence_in_english():
    # "employment" 는 "employment rate" 안에도 들어 있다 — 같은 겹침이 영문
    # 보고서에서도 나므로 낱말 목록을 좁히는 것만으로는 못 막고, 더 구체적인
    # 낱말에 양보하는 규칙이 따로 필요하다
    en = "The employment rate is projected to fall, driven by strong hiring."
    assert rationale.pick(en, "emp_rate") == en
    assert rationale.pick(en, "emp_change") is None


def test_pick_does_not_let_gdp_growth_steal_an_employment_sentence():
    # 맨 "growth" 는 "employment growth"·"export growth" 등 아무 데나 붙는다
    en = ("Employment growth is projected to remain solid, supported by "
          "resilient domestic demand.")
    assert rationale.pick(en, "gdp_growth") is None
    assert rationale.pick(en, "emp_change") == en


def test_pick_rejects_a_retrospective_finding_despite_geoseuro():
    # "것으로 나타났다" 는 이미 드러난 사실이지 전망이 아니다
    s = "상반기 취업자 증가는 건설경기 부진 완화에 기인한 것으로 나타났다."
    assert rationale.pick(s, "emp_change") is None


def test_pick_rejects_a_procedural_e_ttara():
    # "~에 따라" 는 "…에 의하면" 이지 "…때문에" 가 아니다
    s = "정부 지침에 따라 취업자 수 집계 방식이 하반기부터 변경될 것으로 예상된다."
    assert rationale.pick(s, "emp_change") is None
