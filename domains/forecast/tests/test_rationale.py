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


def test_pick_no_longer_suppresses_employment_when_unemployment_is_also_present():
    # "employment" 는 "unemployment" 안에도 부분열로 들어 있지만 "un-" 부정
    # 접두사일 뿐이다 — 실업이 고용의 더 구체적인 형태가 아니므로 emp_change 의
    # "employment" 는 더 이상 억눌리지 않는다. (이 문장은 "unemployment"도
    # 진짜 독립된 낱말로 담고 있어 unemp_rate 역시 같은 문장을 정당하게 얻지만,
    # 그 매칭은 여기서 고친 어떤 것에도 좌우되지 않으므로 따로 단언하지 않는다.)
    s = ("Employment growth remains solid even as unemployment stays low, "
         "driven by strong hiring, and is projected to continue.")
    assert rationale.pick(s, "emp_change") == s


def test_pick_does_not_let_a_pure_unemployment_sentence_trigger_emp_change():
    # 앞의 문장과 달리 "employment" 가 독립된 낱말로 한 번도 안 나오면(오직
    # "unemployment" 안의 부분열로만 우연히 걸릴 뿐이면) emp_change 는 걸리지
    # 않아야 한다 — 실업만 말하는 문장이 고용 증감의 근거가 되면 안 된다.
    s = "Unemployment is projected to rise, driven by weak demand."
    assert rationale.pick(s, "emp_change") is None


def test_pick_recovers_a_plain_employment_sentence_without_chwieopja():
    # "고용" 을 빼지 않고 그대로 두었으므로 "취업자" 가 없어도 "고용"만으로
    # 흔한 문장을 잡아야 한다.
    s1 = "내수 회복과 서비스업 개선에 힘입어 고용 증가세가 이어질 것으로 전망된다."
    s2 = "수출 호조에 힘입어 하반기 고용 확대가 지속될 것으로 예상된다."
    assert rationale.pick(s1, "emp_change") == s1
    assert rationale.pick(s2, "emp_change") == s2


def test_pick_rejects_retrospective_verbs_not_on_any_deny_list():
    # 금지 목록은 새 회고 동사가 나올 때마다 하나씩 뚫린다 — 허용 목록으로
    # 돌았으니 목록에 없는 낯선 회고 동사도 실패로 닫혀야 한다.
    for verb in ("확인됐다", "드러났다", "알려졌다", "집계됐다"):
        s = f"상반기 취업자 증가는 건설경기 부진 완화에 기인한 것으로 {verb}"
        assert rationale.pick(s, "emp_change") is None, verb


def test_pick_rejects_the_emphatic_procedural_e_ttaraseo():
    # "~에 따라서" 는 "~에 따라" 의 강조형일 뿐 여전히 "…에 의하면" 이다
    s = "정부 지침에 따라서 취업자 수 집계 방식이 하반기부터 변경될 것으로 예상된다."
    assert rationale.pick(s, "emp_change") is None


def test_pick_does_not_borrow_a_cause_from_the_previous_sentence():
    # 문장 맨 앞의 "따라서" 가 가리키는 원인은 이 문장이 아니라 앞 문장에
    # 있다 — 저장되는 인용문은 그 원인을 설명하지 못한다.
    s = "수출 회복세가 이어지고 있다. 따라서 취업자 수는 증가할 것으로 전망된다."
    assert rationale.pick(s, "emp_change") is None


def test_pick_accepts_gwanchugdoenda_and_yechukdoenda_as_forecast_markers():
    # "관측된다"·"예측된다" 도 "보인다"·"기대된다" 와 같은 자리에 오는 전망
    # 어미다. 허용 목록에서 빠지면 이런 흔한 서술까지 근거 없이 비게 된다.
    observed = "설비투자 회복과 수출 개선에 힘입어 성장률이 확대될 것으로 관측된다."
    predicted = "설비투자 회복과 수출 개선에 힘입어 성장률이 확대될 것으로 예측된다."
    assert rationale.pick(observed, "gdp_growth") == observed
    assert rationale.pick(predicted, "gdp_growth") == predicted


def test_tags_come_only_from_words_in_the_sentence():
    s = "반도체 수출 호조와 설비투자 확대가 성장세를 뒷받침할 것으로 전망된다."
    assert rationale.tags_for(s) == ["수출", "설비투자"]


def test_tags_are_empty_when_nothing_matches():
    assert rationale.tags_for("경기 흐름이 이어질 것으로 전망된다.") == []


def test_tags_do_not_guess_beyond_the_sentence():
    # '반도체' 는 수출을 함의하지만 태그 낱말이 아니다 — 지어내지 않는다
    assert rationale.tags_for("반도체 경기가 회복될 것으로 예상된다.") == []


def test_tags_keep_the_declared_order():
    s = "유가 하락과 내수 회복이 물가를 낮출 것으로 전망된다."
    assert rationale.tags_for(s) == ["내수", "유가"]


def test_tags_ignore_tongsang_trapped_inside_tongsangjeok():
    # "통상적으로" 는 "평소·으레" 라는 뜻이지 통상정책과 무관하다 — "통상" 이
    # 그 안에 부분열로 들어 있다고 해서 통상정책 태그가 붙으면 안 된다.
    s = "통상적으로 하반기에는 내수 회복이 반영되어 취업자가 늘어날 것으로 전망된다."
    tags = rationale.tags_for(s)
    assert "통상정책" not in tags
    assert "내수" in tags


def test_tags_ignore_yuga_trapped_inside_yugajeunggwon():
    # "유가증권" 은 증권 용어이지 원유 가격과 무관하다.
    s = "유가증권 시장 회복을 반영해 설비투자가 확대될 것으로 전망된다."
    tags = rationale.tags_for(s)
    assert "유가" not in tags
    assert "설비투자" in tags


def test_tags_still_catch_tongsangjeongchaek_when_genuinely_present():
    # 함정을 막는다고 진짜 통상정책 문장까지 놓치면 안 된다.
    s = "통상정책 불확실성이 수출에 영향을 미칠 것으로 전망된다."
    tags = rationale.tags_for(s)
    assert "통상정책" in tags


def test_tags_still_catch_yuga_when_genuinely_present():
    # 함정을 막는다고 진짜 유가 문장까지 놓치면 안 된다 — 순서 테스트와
    # 같은 문장이지만 이 파일이 이 목적으로도 계속 통과해야 함을 못박아 둔다.
    s = "유가 하락과 내수 회복이 물가를 낮출 것으로 전망된다."
    tags = rationale.tags_for(s)
    assert "유가" in tags
