from pathlib import Path

import pytest

from domains.forecast.pipeline import rationale

# 아래 문장은 KEIS 2026년 제5호 20쪽에서 그대로 딴 것이다.
REASON = ("2026년 하반기 취업자 수 증가 배경에는 상반기 고용시장의 완만한 "
          "회복 흐름과 경기 개선 기대가 자리한 것으로 전망된다.")
RESTATEMENT = "하반기 취업자 수는 전년 동기 대비 약 18만 5천 명 증가할 것으로 예상되며"
OTHER_INDICATOR = ("생산가능인구는 하반기에도 전년 동기 대비 0.4% 증가세를 "
                   "이어갈 것으로 예상되나, 대부분은 60세 이상 고령층이다.")

FIXTURES = Path(__file__).parent / "fixtures"
# 2026년 제5호 20쪽을 400dpi·전처리로 실제 OCR 한 원문 그대로다(가공 없음).
# 위 REASON 은 이 쪽의 첫 항목을 손으로 옮겨 적은 것이지만, OCR 은 그 항목의
# 전망 어미("자리한 것으로 전망된다")를 "자요"로 망가뜨려 실제로는 못 건진다
# — 아래 bullets 테스트는 그 실물 원문을 그대로 쓴다.
KEIS_P20 = (FIXTURES / "keis_2026-08_p20.txt").read_text(encoding="utf-8")
# 텍스트 레이어가 있는 PDF 를 pdfplumber 로 읽은 실물 원문이다 — 한 문장이
# 여러 줄에 걸쳐 감겨 있고, 그 줄들은 마침표로 끝나지 않는다.
KLI_2026 = (FIXTURES / "kli_2026_forecast.txt").read_text(encoding="utf-8")
KIET_2026H2 = (FIXTURES / "kiet_2026h2_macro.txt").read_text(encoding="utf-8")
# OECD Interim Economic Outlook 2026-03 10쪽 원문이다 — 표 전체가 빈 줄도
# 항목 표지도 없이 한 유닛(723자)으로 남는다. 물가 지표("inflation")와 전망
# 표지("is projected")는 이미 갖췄고 인과 표지 하나만 없다.
OECD_P10 = (FIXTURES / "oecd_interim_2026-03_p10.txt").read_text(encoding="utf-8")
# KLI_2026 27~28행에서 그대로 딴 문장이다 — "인해" 가 인과 표지로 쓰인 실례다.
KLI_INHAE_SENTENCE = (
    "인구 증가폭이 일시적으로 확대되면서 인구효과로 인해 올해 나타난 "
    "취업자 감소(-2만 명)가 내년에는 사라질 전망(±0명)이다."
)
# 한국은행 2026년 8월 경제전망 요약표 원문이다 — 국문 표제어 항목마다
# '•' 로 시작한다(예: "•미국"·"•유로지역"). '•' 를 _WRAP_BOUNDARY_MARKERS
# 에서 빼면 이 항목들이 다시 한 덩어리로 뭉친다 — 이 픽스처로 그 표지가
# 실제로 일하고 있음을 못박는다.
BOK_2026_08 = (FIXTURES / "bok_2026-08_summary.txt").read_text(encoding="utf-8")


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


def test_tags_ignore_tongsang_trapped_inside_tongsangimgeum():
    # "통상임금" 은 초과근로수당 산정 기준이 되는 노동법 용어(정기적으로
    # 지급되는 통상의 급여)이지 무역 통상정책과 무관하다 — 이 아카이브는
    # 고용·임금 전망을 다루므로 이 낱말이 실제로 나타날 개연성이 낮지 않다.
    s = "통상임금 산정 기준 변경이 반영되어 인건비가 늘어날 것으로 전망된다."
    assert "통상정책" not in rationale.tags_for(s)


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


def test_tags_match_english_plurals_as_substrings():
    # IMF·OECD 원문은 복수형으로 쓰는 경우가 흔하다("exports"·"tariffs"·
    # "oil prices"·"exchange rates") — 낱말 경계를 두면 "s" 하나 때문에
    # 이런 흔한 영문 표현을 다 놓친다. 태그 낱말은 지표 낱말과 달리 서로
    # 경쟁하지 않으므로 경계 없이 부분열로 찾는다.
    assert "수출" in rationale.tags_for(
        "Exports are projected to rise, supported by strong global demand.")
    assert "통상정책" in rationale.tags_for(
        "Tariffs are expected to increase in the near term.")
    assert "유가" in rationale.tags_for(
        "Oil prices are expected to decline through the forecast horizon.")
    assert "환율" in rationale.tags_for(
        "Exchange rates are projected to remain broadly stable.")


def test_tags_do_not_guess_beyond_the_sentence_in_english():
    # 한국어 문장에서와 같은 원칙이 영문 문장에도 그대로 적용된다.
    assert rationale.tags_for("Semiconductor conditions are expected to improve.") == []


def test_tags_catch_construction_investment_in_english():
    # "construction investment" 는 한국은행·통계청이 건설투자를 영문으로
    # 낼 때 쓰는 공식 명칭이다.
    s = "Construction investment is projected to weaken further amid high borrowing costs."
    assert "건설투자" in rationale.tags_for(s)


def test_tags_catch_facility_investment_in_english():
    # "facility investment" 는 설비투자의 공식 영문 명칭이다.
    s = "Facility investment is expected to recover gradually as external demand improves."
    assert "설비투자" in rationale.tags_for(s)


def test_tags_catch_demographic_in_english():
    s = "Demographic headwinds are expected to weigh on potential growth."
    assert "인구구조" in rationale.tags_for(s)


def test_tags_catch_working_age_population_in_english():
    s = "The working-age population is projected to decline through the decade."
    assert "인구구조" in rationale.tags_for(s)


def test_tags_catch_every_aging_population_phrase_variant():
    # OECD 는 영국식 철자(ageing)를, IMF 는 미국식 철자(aging)를 쓰고,
    # "aging population"·"population aging" 두 어순 모두 이 프로즈에
    # 나온다 — 네 구 형태 모두 인구구조를 잡아야 한다.
    for phrase in ("aging population", "ageing population",
                   "population aging", "population ageing"):
        s = f"A rapidly changing {phrase} weighs on potential growth."
        assert "인구구조" in rationale.tags_for(s), phrase


def test_tags_do_not_flag_demographics_from_ordinary_aging_suffixed_words():
    # "aging" 을 낱말 하나로 두면 damaging·encouraging·averaging·managing·
    # packaging 처럼 거시경제 서술에 흔한 낱말 안에도 부분열로 걸린다 —
    # en_US 사전(로컬 Hunspell 사전) 전수 대조로 확인한 문제다. 구 형태로
    # 바꾼 뒤에는 이런 문장에 인구구조가 붙으면 안 된다.
    sentences = [
        "Trade tensions are damaging the export outlook.",
        "There are encouraging signs in private consumption.",
        "Growth is averaging 2 percent over the period.",
        "Managing inflation expectations remains the priority.",
        "Packaging costs rose sharply.",
    ]
    for s in sentences:
        assert "인구구조" not in rationale.tags_for(s), s


def test_tags_still_catch_a_real_aging_population_sentence():
    # 함정을 막는다고 진짜 인구구조 문장까지 놓치면 안 된다.
    s = "A rapidly aging population weighs on labour supply."
    assert "인구구조" in rationale.tags_for(s)


def test_tags_catch_manufacturing_employment_in_english():
    # OECD Economic Surveys: Korea 가 부문별 고용을 말할 때 쓰는 표현이다.
    s = "Manufacturing employment is expected to contract further."
    assert "제조업고용" in rationale.tags_for(s)


def test_tags_catch_construction_employment_in_english():
    s = "Construction employment is expected to remain weak."
    assert "건설업고용" in rationale.tags_for(s)


def test_tags_catch_agricultural_prices_in_english():
    # IMF 가 한국 물가를 요인별로 분해할 때 쓰는 표현이다.
    s = "Agricultural prices are projected to ease in the second half."
    assert "농산물" in rationale.tags_for(s)


def test_tags_catch_administered_prices_in_english():
    s = "Administered prices are expected to rise following utility rate hikes."
    assert "공공요금" in rationale.tags_for(s)


def test_tags_leave_care_jobs_without_an_english_word():
    # 돌봄일자리는 정부가 재정으로 보건복지 부문에 만드는 한국 특유의 일자리
    # 정책 용어라 IMF·OECD 문서에서 이 개념 하나를 가리키는 표준 영문
    # 표현을 찾지 못했다 — 없는 것을 지어내 붙이지 않았으므로 영문
    # 문장에서는 이 태그가 걸리지 않는다.
    s = "Public health and welfare spending is expected to expand."
    assert "돌봄일자리" not in rationale.tags_for(s)


def test_sentences_bullets_true_cuts_real_keis_ocr_text_into_seven_units():
    # 텍스트 레이어 없는 PDF 를 OCR 로 읽은 실물 원문이다 — 줄바꿈만으로는
    # 이 표지들이 있는 자리조차 알 수 없어, 합성 문장이 아니라 이 픽스처로
    # 검증한다. 캡션("| 통계포커스 |")과 쪽 하단 장식(점선·워터마크 URL)은
    # 표지가 아니므로 단위로 세지 않는다.
    units = rationale.sentences(KEIS_P20, bullets=True)
    assert len(units) == 7


def test_sentences_bullets_true_drops_the_page_furniture():
    # 쪽 하단 장식 줄 자체는 버린다 — 안 그러면 마지막 문장이 각주까지
    # 통째로 삼킨다.
    units = rationale.sentences(KEIS_P20, bullets=True)
    assert not any("www." in u for u in units)
    assert not any("_" in u for u in units)


def test_sentences_bullets_true_does_not_flush_across_furniture_mid_bullet():
    # 장식 줄은 문단 경계가 아니다 — 문장 한가운데 우연히 끼어든 쓰레기일
    # 뿐이다. 예전 구현은 장식을 만나면 지금까지 모은 문장을 닫아버렸는데,
    # 그러면 이어지는 진짜 continuation 이 이미 빈 current 에 도착해
    # 조용히 사라지고, 앞 반쪽만 완결된 문장처럼 남는다 — KEIS 를 근거로
    # 인용하는 이 아카이브가 정확히 피해야 할 실패 모양이다.
    text = ("- 하반기에는 건설경기 부진 완화와\n"
            "www.keis.or.kr\n"
            "내수 회복이 반영될 것으로 예상")
    assert rationale.sentences(text, bullets=True) == [
        "하반기에는 건설경기 부진 완화와 내수 회복이 반영될 것으로 예상",
    ]


def test_sentences_bullets_true_drops_empty_fragments():
    # "빈 조각은 버린다"는 기본 분리와 같은 약속이다. 표지만 있고 내용이
    # 없는 줄(예: '- ' 한 줄로 끝나는 불릿)이 바로 다음 표지로 닫히면
    # 빈 문자열이 그대로 유닛이 될 수 있다 — 그 조각을 걸러야 한다.
    assert rationale.sentences("- \n- 내용", bullets=True) == ["내용"]


def test_sentences_bullets_true_recovers_the_causal_bullet_whole():
    # 이 문장은 두 줄에 걸쳐 줄바꿈으로 감겨 있다("...주도한" / "보건복지업
    # ...예상") — 불릿 표지가 아니라 줄바꿈을 경계로 쓰면 반 토막 난다.
    units = rationale.sentences(KEIS_P20, bullets=True)
    assert (
        "하반기에는 건설경기 부진 완화와 내수 회복이 점진적으로 반영되고, "
        "상반기 고용 증가를 주도한 보건복지업 및 대면 서비스업의 노동 수요 "
        "역시 지속될 것으로 예상"
    ) in units


def test_pick_finds_the_emp_change_rationale_in_real_keis_ocr_text():
    # bullets=True 를 pick 에 그대로 넘기면, 표 다음 쪽 실물 원문에서 지표·
    # 인과·전망 세 조건을 모두 만족하는 문장 하나를 그대로(가공 없이) 찾는다.
    got = rationale.pick(KEIS_P20, "emp_change", bullets=True)
    assert got == (
        "하반기에는 건설경기 부진 완화와 내수 회복이 점진적으로 반영되고, "
        "상반기 고용 증가를 주도한 보건복지업 및 대면 서비스업의 노동 수요 "
        "역시 지속될 것으로 예상"
    )


def test_pick_rejects_the_garbled_lead_bullet_despite_cause_and_indicator():
    # 이 쪽의 첫 항목은 배경·취업자를 다 담고 있지만, OCR 이 전망 어미를
    # "자요"로 망가뜨려 전망 표지가 없다 — 규칙을 늦추지 않고 그대로 걸러야
    # 한다. 값은 위 test_pick_finds_the_emp_change_rationale_in_real_keis_ocr_text
    # 에서 이미 확인한 문장이므로, 여기서는 첫 항목이 아니라는 것만 본다.
    got = rationale.pick(KEIS_P20, "emp_change", bullets=True)
    assert not got.startswith("2026년 하반기 취업자 수 증가 배경")


def test_pick_does_not_use_bullets_by_default_on_the_same_ocr_text():
    # 두 경로는 여전히 다른 경로다 — bullets 기본값이 조용히 True 로 바뀌는
    # 회귀를 잡는 게 이 테스트의 목적이다. '-' 를 기본 경로의 표지 집합에서
    # 뺀 뒤(_WRAP_BOUNDARY_MARKERS, "Fix 2")로 두 경로의 유닛 수가 우연히
    # 다시 7개로 같아졌다 — 예전엔 기본 경로가 12개를 남겨 수만으로도
    # 구분이 됐지만, 지금은 숫자가 같으니 수를 규제 신호로 못 쓴다. 구조는
    # 여전히 다르다: 기본 경로는 '-' 를 표지로 안 보므로 그때 '-' 로
    # 갈라지던 문장들이 지금은 한 덩어리로 뭉치고(그 결과로 emp_change 를
    # 못 찾는다 — 아래
    # test_pick_needs_bullets_true_for_keis_after_fix_2 참고), 캡션
    # ("통계포커스") 도 여전히 기본 경로에만 남는다. 이 캡션 검사가 이
    # 테스트의 진짜 회귀 감지기다 — bullets 가 조용히 True 로 새면 기본
    # 경로 호출도 캡션을 버려 이 단언이 깨진다.
    assert len(rationale.sentences(KEIS_P20)) == 7
    assert len(rationale.sentences(KEIS_P20, bullets=True)) == 7
    assert any("통계포커스" in s for s in rationale.sentences(KEIS_P20))
    assert not any("통계포커스" in s
                   for s in rationale.sentences(KEIS_P20, bullets=True))


def test_bullets_true_does_not_split_a_wrapped_negative_percentage_line():
    # KEIS 실물 OCR 은 값이 음수면 그 값이 줄 맨 앞으로 감기는 일이 흔하다
    # ('-0.3%p 하락'). '-' 뒤에 단위 붙은 숫자가 곧바로 오면 새 불릿이
    # 아니라 줄 감김으로 본다 — 그렇지 않으면 앞 문장의 나머지를 잃고,
    # 부호까지 함께 잘려 나가 수치의 뜻이 뒤집힌 인용문이 저장된다.
    text = ("- 2026년 하반기 성장률은 상반기 대비 개선되었으나 물가는\n"
            "-0.3%p 하락한 것으로 전망된다.")
    assert rationale.sentences(text, bullets=True) == [
        "2026년 하반기 성장률은 상반기 대비 개선되었으나 물가는 "
        "-0.3%p 하락한 것으로 전망된다.",
    ]


def test_bullets_true_still_splits_a_dash_bullet_that_starts_with_content():
    # 반대 방향도 지켜야 한다 — '-' 뒤에 단위 붙은 숫자가 아니라 보통
    # 낱말이 오면(연도·"또한" 등, 실제 KEIS 20쪽 원문의 "-또한 최근 AI
    # 수요..."가 실례다) 여전히 새 불릿으로 본다. 음수 판정을 숫자+단위로
    # 좁혀 두지 않으면 이런 흔한 불릿까지 줄 감김으로 오인해 잃는다.
    text = ("- 2026년 하반기 취업자 수는 증가했다\n"
            "-또한 반도체 수출 확대가 국내 경제를 견인할 것으로 전망된다.")
    assert rationale.sentences(text, bullets=True) == [
        "2026년 하반기 취업자 수는 증가했다",
        "또한 반도체 수출 확대가 국내 경제를 견인할 것으로 전망된다.",
    ]


def test_default_path_keeps_a_wrapped_negative_percentage_whole():
    # 예전에는 기본 경로가 마침표 없이 끝나는 1행("...물가는")을 통째로
    # 버려 "-0.3%p 하락한 것으로 전망된다." 만 남겼다 — 주어를 잃은 반
    # 토막이 완결된 인용문처럼 저장되는 모양이다. 줄 감김을 펴게 된 지금은
    # 두 줄이 한 문장으로 돌아온다.
    #
    # (이 테스트는 예전에 "- 2026년..." 처럼 문장 맨 앞에 '-' 불릿을 얹어,
    # 소수점 가리기와 줄 감김의 순서까지 함께 지켰다. '-' 를 기본 경로의
    # 표지 집합에서 뺀 뒤(_WRAP_BOUNDARY_MARKERS, "Fix 2")로는 그 순서가
    # 더는 결과를 바꾸지 않는다 — '-' 로 시작하는 줄은 표지 판정 자체를
    # 거치지 않으므로 _NEGATIVE_NUMBER 도 안 거친다. 그래서 이 테스트는
    # '-' 불릿 없이, KDI·OECD 실제 표에 실제로 나오는 모양 그대로 줄 앞으로
    # 감긴 음수만 확인한다.)
    text = ("2026년 하반기 성장률은 상반기 대비 개선되었으나 물가는\n"
            "-0.3%p 하락한 것으로 전망된다.")
    assert rationale.sentences(text) == [
        "2026년 하반기 성장률은 상반기 대비 개선되었으나 물가는 "
        "-0.3%p 하락한 것으로 전망된다.",
    ]


def test_sentences_join_a_prose_sentence_wrapped_across_three_lines():
    # KLI 2026년 전망(픽스처 2~4행)에서 그대로 딴 것이다. pdfplumber 는
    # PDF 가 오른쪽 여백에서 접은 자리마다 줄바꿈을 내므로 앞 두 줄이
    # 마침표 없이 끝난다 — 줄바꿈을 문장 경계로 보면 그 두 줄이 조용히
    # 사라지고 마지막 줄("뒷받침된 결과이다.")만 남아, 주어도 전망 표지도
    # 없는 조각이 문장 행세를 한다.
    assert (
        "2025년 하반기 고용 증가폭은 20만 명을 상회할 것으로 예상되는데, "
        "이는 보건업 및 사회복지 서비스업, 정보통신업, 전문ㆍ과학 및 "
        "기술서비스업 등 서비스업 전반의 견조한 고용 증가가 뒷받침된 결과이다."
    ) in rationale.sentences(KLI_2026)


def test_sentences_do_not_run_across_a_blank_line():
    # 빈 줄은 문단(또는 쪽) 경계다. 여기서 끊지 않으면 줄 감김을 펴는 일이
    # 글 전체로 번져, 서로 다른 문단이 한 인용문으로 붙는다 — 마침표를
    # 쓰지 않는 국문 보고서 문체에서는 그 덩어리가 쪽 하나만큼 커진다.
    text = ("내수 회복에 힘입어 취업자 증가세가 이어질 전망\n"
            "\n"
            "수출 호조를 반영해 성장률이 확대될 전망")
    assert rationale.sentences(text) == [
        "내수 회복에 힘입어 취업자 증가세가 이어질 전망",
        "수출 호조를 반영해 성장률이 확대될 전망",
    ]


def test_sentences_start_a_new_unit_at_a_bullet_marker_in_the_default_path():
    # 빈 줄만으로는 부족하다 — KIET·BOK·KDI 픽스처에는 빈 줄이 하나도 없다.
    # 국문 보고서는 서술 항목 끝에 마침표를 쓰지 않는 문체라, 표지를 경계로
    # 보지 않으면 서술과 그 아래 표가 한 덩어리가 된다.
    text = ("○ 내수 회복에 힘입어 취업자 증가세가 이어질 전망\n"
            "○ 수출 호조를 반영해 성장률이 확대될 전망")
    assert rationale.sentences(text) == [
        "내수 회복에 힘입어 취업자 증가세가 이어질 전망",
        "수출 호조를 반영해 성장률이 확대될 전망",
    ]


def test_pick_does_not_hand_back_a_whole_table_page_as_a_rationale():
    # KIET 2026년 하반기 거시 전망 쪽은 빈 줄도 본문 마침표도 없다. 표지를
    # 경계로 보지 않으면 서술 네 항목과 표 전체가 1,039자 한 덩어리가 되고,
    # 그 덩어리가 인과·전망 표지를 모두 갖춰 근거로 뽑힌다 — 숫자 한 쪽을
    # 기관의 설명인 양 사용자에게 보여주는 셈이다.
    #
    # 이 인용문의 "작용하 고," 는 오탈자가 아니다 — _unwrap 이 줄 감김을
    # 공백으로 이어 붙이면서 생긴 것이다. pdfplumber 는 줄 끝 공백을 지워
    # 넘기므로, 이 공백이 원래 낱말 중간의 줄 감김("작용하"|"고,")이었는지
    # 진짜 낱말 경계("사회복지"|"서비스업,")였는지 원문 자체에 아무 표시도
    # 남지 않는다 — 어느 쪽으로 처리해도 반대쪽 경우에서는 틀린다. 그래서
    # sentences() 는 이 흔적을 지우려 하지 않고 그대로 남긴다(sentences()
    # 문서주석 참고). 이 단언은 그 인공물을 의도적으로 못박는다.
    got = rationale.pick(KIET_2026H2, "cpi")
    assert got == (
        "민간소비는 실질소득 증가와 정부의 확장적 재정 기조, 금융시장(증시 등) "
        "호조세 등을 배경으로 점차 개선될 전망이나, 에너지 가격 상승과 고환율 "
        "등이 물가 부담으로 작용하 고, 금리 인하 지연 등이 회복세를 제한하면서 "
        "전년 대비 2.2% 증가할 것으로 예상"
    )
    assert "실질GDP" not in got


def test_pick_needs_bullets_true_for_keis_after_fix_2():
    # 예전엔 두 경로가 이 쪽에서 우연히 같은 문장을 골랐다 — 기본 경로도
    # 그때는 '-' 를 표지로 보고 KEIS 항목들을 갈랐기 때문이다. '-' 를 기본
    # 경로의 표지 집합에서 뺀 뒤(_WRAP_BOUNDARY_MARKERS, "Fix 2")로는 그
    # 갈림이 사라져, '-' 로 갈리던 항목들이 다시 한 덩어리로 뭉치고
    # emp_change 의 세 조건을 못 채운다. 이래도 된다 — KEIS 수집기는
    # production 에서 언제나 bullets=True 를 넘긴다(설계 문서 3.3). 이
    # 테스트는 그 전제, 즉 "두 경로가 우연히 같아지는 일에 기대면 안 된다"
    # 는 것 자체를 못박는다.
    assert rationale.pick(KEIS_P20, "emp_change", bullets=True) is not None
    assert rationale.pick(KEIS_P20, "emp_change", bullets=False) is None


# ---------------------------------------------------------------------------
# Change 1 — _CAUSE 에 "원인"·"인해"·"결과이다"·"결과다" 를 더한다.
# ---------------------------------------------------------------------------

def test_pick_finds_the_kli_gdp_growth_reason_via_wonin():
    # KLI_2026 11~13행(줄 감김을 편 뒤 한 문장)에서 그대로 나오는 문장이다.
    # "원인" 이 _CAUSE 에 없으면 지표(성장률)·전망(전망)은 있어도 인과 표지가
    # 없어 떨어진다 — 이 테스트가 그 실측(98자)을 못박는다.
    assert rationale.pick(KLI_2026, "gdp_growth") == (
        "이러한 긍정적 전망의 주요 원인으로는 올해보다 나은 내년 경제 "
        "성장률 전망과 함께 인구효과의 변화, 정부 직접일자리사업 참여자 "
        "증가, 산업별 고용의 메가트 렌드 지속이 꼽힌다."
    )


def test_pick_finds_the_kli_emp_change_reason_via_gyeolgwaida():
    # KLI_2026 3~5행(줄 감김을 편 뒤 한 문장)에서 그대로 나오는 문장이다.
    # "결과이다" 가 _CAUSE 에 없으면 지표(고용)·전망(예상)은 있어도 인과
    # 표지가 없어 떨어진다 — 이 테스트가 그 실측(114자)을 못박는다.
    assert rationale.pick(KLI_2026, "emp_change") == (
        "2025년 하반기 고용 증가폭은 20만 명을 상회할 것으로 예상되는데, "
        "이는 보건업 및 사회복지 서비스업, 정보통신업, 전문ㆍ과학 및 "
        "기술서비스업 등 서비스업 전반의 견조한 고용 증가가 뒷받침된 결과이다."
    )


def test_pick_recognizes_inhae_as_a_cause_marker():
    # KLI_2026 27~28행에서 그대로 딴 문장이다(위 KLI_INHAE_SENTENCE) — 이
    # 문장 하나만으로는 pick(KLI_2026, ...) 전체 호출에서 앞서 매칭되는 다른
    # 문장에 가려 드러나지 않으므로, 문장을 따로 떼어 "로 인해" 자체를
    # 검증한다.
    assert rationale.pick(KLI_INHAE_SENTENCE, "emp_change") == KLI_INHAE_SENTENCE


def test_cause_uses_ro_inhae_not_bare_inhae():
    # 맨 "인해"는 "확인해"·"승인해"·"부인해" 안에도 부분열로 들어 있다 —
    # "확인·승인·부인" 동사 어간에 우연히 "인해"가 걸릴 뿐, "그것 때문에"
    # 라는 뜻이 아니다. "확인해 보면"은 "만약 확인하면"이라는 조건절이지
    # 인과 서술이 아니다. "결과"를 "결과이다"·"결과다"로만 두는 것과 정확히
    # 같은 부류의 함정이다. 이 코퍼스 23개 픽스처에는 이런 문장이 없어
    # 합성 문장으로 검증한다.
    s = "통계청 자료를 확인해 보면 취업자 수는 늘어날 것으로 전망된다."
    assert rationale.pick(s, "emp_change") is None


def test_pick_recognizes_gyeolgwada_without_the_ida_ending():
    # "결과다" 는 "결과이다" 의 해요체가 아닌 축약형이다 — 이 코퍼스
    # 픽스처에는 이 어미로 끝나는 문장이 없어 합성 문장으로 확인한다.
    s = "취업자 증가세가 이어질 것으로 전망되는 것은 서비스업 고용 확대의 결과다."
    assert rationale.pick(s, "emp_change") == s


def test_cause_uses_gyeolgwaida_not_bare_gyeolgwa():
    # "결과" 를 그대로 쓰면 "조사 결과"·"설문 결과"·"그 결과" 처럼 원인이
    # 아니라 "조사해 보니" 라는 뜻의 문장까지 인과로 오인한다 — "것으로
    # 나타났다" 를 빼야 했던 것과 같은 부류의 실패다. 이 코퍼스 23개
    # 픽스처에는 이런 문장이 없어(측정으로 확인했다) 합성 문장으로
    # 검증한다: 실업률 통계는 언급하지만 그 조사 결과를 전할 뿐 원인을
    # 말하지 않는다.
    s = "실업률 조사 결과, 하반기에는 고용 지표가 개선될 것으로 전망된다."
    assert rationale.pick(s, "emp_change") is None
    assert rationale.pick(s, "unemp_rate") is None


# ---------------------------------------------------------------------------
# Change 2 — 근거 문장에 상한 길이를 둔다.
# ---------------------------------------------------------------------------

def test_pick_never_returns_a_table_page_longer_than_the_declared_maximum(monkeypatch):
    # OECD_P10 은 물가 지표("inflation")와 전망 표지("is projected")를 이미
    # 갖춘 723자짜리 표 한 덩어리다 — 인과 표지 하나만 없어서 지금은 안
    # 뽑힌다. 이게 바로 상한을 두는 이유인 "한 낱말 차이" 위험이다. 그
    # 위험을 실제로 확인하려면 인과 표지가 하나 있어야 하는데, 이 표
    # 원문에는(측정으로 확인한 대로) 아직 없다. 그래서 이 테스트만 표
    # 원문에 이미 있는 낱말("difference from")을 임시로 _CAUSE 에 얹는다 —
    # 표 본문 자체는 실제 픽스처 그대로이고 한 글자도 손대지 않는다. 어떤
    # 낱말이 우연히 인과 표지 목록에 걸리든, 상한이 없으면 그 순간 표
    # 전체가 "근거"로 뽑힌다는 사실은 똑같다.
    monkeypatch.setattr(rationale, "_CAUSE", rationale._CAUSE + ("difference from",))
    # 전제 확인: 이 몽키패치가 실제로 723자 이상이면서 인과 표지("difference
    # from")를 담은 유닛을 만드는지 먼저 본다 — 안 그러면 아래 단언은 빈
    # 픽스처에 대해서도 통과해 아무것도 안 지킨다.
    assert any(
        len(u) > rationale._MAX_RATIONALE_LENGTH and "difference from" in u.lower()
        for u in rationale.sentences(OECD_P10)
    )
    assert rationale.pick(OECD_P10, "cpi") is None


def test_pick_keeps_a_real_sentence_well_under_the_maximum():
    # 실측한 가장 긴 실제 문장(kiet cpi, 143자)은 상한(300)의 절반에도 못
    # 미친다 — 상한이 진짜 문장을 자르지 않는다는 것을 다시 못박는다. (길이
    # 자체를 다시 재는 건 상한 로직을 그대로 되풀이하는 동어반복이라 뺐다 —
    # 여기서 지킬 것은 "None 이 아니다"뿐이다.)
    assert rationale.pick(KIET_2026H2, "cpi") is not None


def test_pick_rejects_a_unit_one_character_over_the_maximum():
    # 정확히 경계에서 상한이 동작하는지를 합성 문장으로 확인한다 — 300자를
    # 한 글자 넘기면(301자) 더는 문장으로 보지 않는다.
    filler = "가" * (301 - len(
        "내수 회복() 에 힘입어 취업자 증가세가 이어질 것으로 전망된다."))
    s = f"내수 회복({filler}) 에 힘입어 취업자 증가세가 이어질 것으로 전망된다."
    assert len(s) == 301
    assert rationale.pick(s, "emp_change") is None


def test_pick_accepts_a_unit_exactly_at_the_maximum():
    # 300자는 여전히 문장으로 본다 — 상한은 "300자보다 길면" 이지 "300자
    # 이상이면" 이 아니다.
    filler = "가" * (300 - len(
        "내수 회복() 에 힘입어 취업자 증가세가 이어질 것으로 전망된다."))
    s = f"내수 회복({filler}) 에 힘입어 취업자 증가세가 이어질 것으로 전망된다."
    assert len(s) == 300
    assert rationale.pick(s, "emp_change") == s


def test_pick_skips_an_over_length_unit_instead_of_giving_up_on_the_whole_text():
    # 상한을 넘는 유닛은 "건너뛸 뿐 순회를 멈추지 않는다" — pick() 문서주석의
    # 그 약속을 직접 확인한다. continue 를 return None 으로 바꿔도 기존
    # 테스트는 하나도 안 깨진다(어떤 픽스처도 상한을 넘는 유닛보다 앞에
    # 짧고 진짜인 문장을 두고 있지 않다) — 그래서 합성 텍스트로 검증한다:
    # 300자를 넘는 무관한 유닛(310자 채움) 바로 뒤에 emp_change 의 세
    # 조건을 모두 만족하는 진짜 짧은 문장을 둔다. continue 라면 앞 유닛을
    # 넘기고 뒤 문장을 찾아 돌려주지만, return None 으로 바뀌면 앞 유닛의
    # 길이만 보고 즉시 포기해 뒤의 진짜 문장을 놓친다 — 다음 디스패치가
    # 표 쪽을 먼저 넘기기 시작하면 실제로 벌어질 순서다.
    filler = "가" * 310 + "."
    real = "내수 회복에 힘입어 취업자 증가세가 이어질 것으로 전망된다."
    text = f"{filler} {real}"
    assert rationale.pick(text, "emp_change") == real


def test_pick_never_drops_below_two_units_when_the_wrap_boundary_bullet_is_removed():
    # BOK_2026_08 은 '•' 로 시작하는 항목이 16유닛으로 갈리는 실물 원문이다
    # — '•' 를 _WRAP_BOUNDARY_MARKERS 에서 빼면 이 항목들이 다시 한
    # 덩어리로 뭉친다(실측: 16유닛 → 2유닛). 이 테스트가 없으면 '•' 를
    # 빼도 test_rationale.py 전체가 그대로 통과한다 — BOK 픽스처를 쓰는
    # 테스트가 이것 말고 없었기 때문이다. 다음 디스패치의 일곱 수집기 중
    # 하나가 BOK 이므로, 이 표지가 실제로 일하고 있다는 것을 이 픽스처로
    # 못박아 둔다.
    assert len(rationale.sentences(BOK_2026_08)) == 16
