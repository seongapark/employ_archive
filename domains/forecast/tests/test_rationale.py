from pathlib import Path

from domains.forecast.pipeline import rationale

FIXTURES = Path(__file__).parent / "fixtures"
# KDI 2025-08-12호 4쪽(source_page=4) — 아래 "건설업체" 함정 테스트가 이
# 실물 픽스처에도 그 겹침이 있다는 것을 못박는 데 쓴다.
KDI_2025_08_P4 = (FIXTURES / "kdi_2025-08_p4.txt").read_text(encoding="utf-8")


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


def test_duplicated_hangul_guard_ignores_runs_of_repeated_digits():
    # 한글 음절에만 건다 — "1000"은 "0"이 세 번 이어지는 정당한 수치
    # 표기이고, "222000222666" 처럼 숫자만 삼중 반복돼도 그 자체는 결함이
    # 아니다(둘레 텍스트가 결함이라 결함처럼 '보일' 뿐이다).
    assert rationale._DUPLICATED_HANGUL.search("222000222666") is None
    assert rationale._DUPLICATED_HANGUL.search("1000") is None


# ---------------------------------------------------------------------------
# 최종 검토 Fix 1 — _FALSE_CONTAINMENT 에 "이유"·"건설업체" 를 더한다.
# ---------------------------------------------------------------------------

def test_tags_ignore_yuga_trapped_inside_iyu():
    # 배포된 데이터에서 실제로 잡은 오탐이다 — rationales.json 의 KLI
    # 2025-08-29 emp_change 근거가 ["인구구조", "유가"] 로 저장돼 화면에
    # "요인은 유가" 가 떴는데, 그 문장에 원유 가격 얘기는 한 글자도 없다.
    # 걸린 건 "컸던 이유가" 의 "이유가" 안에 든 부분열이다.
    s = ("그보다는 상반기에 취업자 수 증가가 예상보다 컸던 이유가 예상을 "
         "넘어선 고령층 취업자 수 증가에 힘입었던 것처럼 하반 기에도 이러한 "
         "경향이 지속된다면 그로 인해 20만 명을 상회하는 취업자 증가도 "
         "실현될 수 있다.")
    tags = rationale.tags_for(s)
    assert "유가" not in tags
    assert "인구구조" in tags   # "고령" 은 진짜다 — 함정만 막고 진짜는 남긴다


def test_tags_still_catch_yuga_in_a_sentence_that_also_says_iyu():
    # "이유" 를 지운다고 같은 문장의 진짜 "유가" 까지 잃으면 안 된다 —
    # 인과를 말하는 문장에는 둘이 함께 나올 개연성이 높다.
    s = "국제유가 상승이 물가가 오른 이유가 되어 상승률이 확대될 전망이다."
    assert "유가" in rationale.tags_for(s)


def test_tags_ignore_geonseoleop_trapped_inside_geonseoleopche():
    # kdi_2025-08_p4.txt 의 "건설업체의 재무건전성 악화" 가 실례다 —
    # 건설회사의 재무 상태를 말하는 문장이지 건설업 '고용' 얘기가 아니다.
    s = "건설업체의 재무건전성 악화가 반영되어 공사 진행에 차질이 발생할 전망이다."
    assert "건설업고용" not in rationale.tags_for(s)


def test_tags_still_catch_geonseoleop_when_genuinely_present():
    s = "건설업 고용 감소가 하반기에도 이어질 것으로 전망된다."
    assert "건설업고용" in rationale.tags_for(s)


def test_the_kdi_p4_fixture_really_contains_the_geonseoleopche_trap():
    # 전제 확인 — 위 합성 문장이 아니라 실물 픽스처에도 이 겹침이 있다는
    # 것을 먼저 못박는다(안 그러면 위 테스트는 코퍼스와 무관한 방어가 된다).
    # 이 쪽에서 "건설업" 이 나오는 자리는 "건설업체" 뿐이다 — 그래서 맨
    # "건설업" 을 세면 이 쪽의 태그가 통째로 틀린다.
    assert "건설업체" in KDI_2025_08_P4
    assert "건설업" not in KDI_2025_08_P4.replace("건설업체", "")
