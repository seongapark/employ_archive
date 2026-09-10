import pytest

from domains.forecast.pipeline import llm_verify as v

PAGE = ("하반기에는 건설경기 부진 완화와 내수 회복이 점진적으로 반영되고,\n"
        "상반기 고용 증가를 주도한 보건복지업 및 대면 서비스업의 노동 수요\n"
        "역시 지속될 것으로 예상")


def test_accepts_a_sentence_that_is_in_the_page():
    got = v.verify("하반기에는 건설경기 부진 완화와 내수 회복이 점진적으로 반영되고,", PAGE)
    assert got == "하반기에는 건설경기 부진 완화와 내수 회복이 점진적으로 반영되고,"


def test_accepts_across_a_line_wrap():
    # 원문은 세 줄이지만 LLM 은 한 문장으로 이어 돌려준다. 공백을 지우면 같다.
    joined = ("하반기에는 건설경기 부진 완화와 내수 회복이 점진적으로 반영되고, 상반기 고용 "
              "증가를 주도한 보건복지업 및 대면 서비스업의 노동 수요 역시 지속될 것으로 예상")
    assert v.verify(joined, PAGE) == joined


def test_accepts_closing_a_wrap_artifact_space():
    # pdfplumber 가 낱말 중간에 넣은 공백을 LLM 이 붙여 써도 통과한다.
    # 문장 머리("에너지 가격 상승이")부터 준다 — 시작 경계 검사(Fix 1)가
    # 들어온 뒤로 그 앞을 자른 조각은 머리 없는 조각으로 따로 걸리므로,
    # 이 테스트가 원래 확인하려던 것(낱말 중간 공백을 붙여도 통과한다)만
    # 남기려면 문장 전체를 후보로 줘야 한다.
    page = "에너지 가격 상승이 물가 부담으로 작용하 고, 회복세를 제한한다"
    candidate = "에너지 가격 상승이 물가 부담으로 작용하고, 회복세를 제한한다"
    assert v.verify(candidate, page) == candidate


def test_rejects_a_word_that_is_not_in_the_page():
    with pytest.raises(v.Rejected) as e:
        v.verify("하반기에는 건설경기 호황과 내수 회복이 반영되고,", PAGE)
    assert "원문에 없다" in e.value.reason


def test_rejects_an_invented_sentence():
    with pytest.raises(v.Rejected):
        v.verify("정부의 확장적 재정 기조가 고용을 뒷받침할 것으로 보인다.", PAGE)


def test_rejects_two_sentences_stitched_from_different_places():
    page = "가나다 라마바. 사아자 차카타."
    with pytest.raises(v.Rejected):
        v.verify("가나다 차카타.", page)


def test_rejects_a_candidate_over_the_length_limit():
    long_source = "가" * 400
    with pytest.raises(v.Rejected) as e:
        v.verify("가" * 350, long_source)
    assert "길다" in e.value.reason


def test_rejects_bold_overprint_debris():
    page = "낙낙낙관관관시시시나나나리리리오오오 중국과 진행 중인 협상이 타결될 것으로 예상"
    with pytest.raises(v.Rejected) as e:
        v.verify("낙낙낙관관관시시시나나나리리리오오오 중국과 진행 중인 협상이", page)
    assert "렌더링" in e.value.reason


def test_rejects_a_fragment_that_starts_mid_clause():
    # "완화와"는 PAGE 에서 "부진 " 뒤, 즉 절 한가운데서 시작한다.
    # 주어("하반기에는 건설경기 부진")가 잘려 나간 머리 없는 조각이다.
    with pytest.raises(v.Rejected) as e:
        v.verify("완화와 내수 회복이 점진적으로 반영되고, 상반기 고용", PAGE)
    assert "시작" in e.value.reason


def test_rejects_a_splice_across_a_sentence_boundary():
    # "전망이다."로 앞 문장을 끝내고 "정부는"으로 다음 문장 머리를 잇는다 —
    # 화면에는 한 기관이 실제로는 하지 않은 하나의 주장처럼 보인다.
    page = "성장률 3% 전망이다. 정부는 확장적 재정을 유지한다."
    with pytest.raises(v.Rejected) as e:
        v.verify("전망이다. 정부는", page)
    assert "시작" in e.value.reason


def test_rejects_an_empty_candidate():
    with pytest.raises(v.Rejected) as e:
        v.verify("", PAGE)
    assert "빈 문장" in e.value.reason


def test_rejects_a_whitespace_only_candidate():
    with pytest.raises(v.Rejected) as e:
        v.verify("   ", PAGE)
    assert "빈 문장" in e.value.reason


def test_rejects_a_fragment_starting_inside_a_negative_number():
    # "-" 는 불릿이자 음수 부호다 — 표지는 줄의 첫 내용일 때만 표지로
    # 인정한다. 줄 첫머리가 아니라 "성장률은 " 뒤에 온 "-" 는 표지가 아니라
    # 부호이므로 그 뒤에서 시작하는 조각은 "성장률은" 이라는 주어를 자른 것이다.
    with pytest.raises(v.Rejected) as e:
        v.verify("0.3%p 감소했다고 밝혔다", "성장률은 -0.3%p 감소했다고 밝혔다")
    assert "시작" in e.value.reason


def test_rejects_a_fragment_starting_after_a_parenthesis():
    # ")" 는 번호 붙은 항목("1)")의 일부일 때만 표지다. 문장 중간의 여는
    # 괄호를 닫는 ")" 뒤에서 시작하면 주어를 자른 조각이 된다.
    with pytest.raises(v.Rejected) as e:
        v.verify("상승이 예상된다", "가격(예: 100원) 상승이 예상된다")
    assert "시작" in e.value.reason


def test_accepts_a_sentence_after_a_terminator_then_newline():
    page = "앞 문장이 있다.\n뒤 문장이 이어진다"
    candidate = "뒤 문장이 이어진다"
    assert v.verify(candidate, page) == candidate


def test_accepts_a_sentence_after_an_indented_bullet():
    page = "개요\n  - 항목 내용입니다 계속된다"
    candidate = "항목 내용입니다 계속된다"
    assert v.verify(candidate, page) == candidate


def test_accepts_a_sentence_after_a_numbered_paren_item():
    page = "1) 취업자는 증가했다"
    candidate = "취업자는 증가했다"
    assert v.verify(candidate, page) == candidate


def test_accepts_a_sentence_after_a_numbered_dot_item():
    page = "3. 전망의 위험요인은 다음과 같다"
    candidate = "전망의 위험요인은 다음과 같다"
    assert v.verify(candidate, page) == candidate


def test_rejects_a_fragment_starting_inside_a_decimal_number():
    # "." 는 문장 종결부호이자 소수점이다(v._looks_like_a_decimal_point 참고).
    # 숫자 사이에 오면 문장이 끝난 게 아니라 소수점이므로, 그 뒤에서
    # 시작하는 조각은 "성장률은" 이라는 주어를 자른 것이다.
    with pytest.raises(v.Rejected) as e:
        v.verify("5% 상승할 것으로 전망된다", "성장률은 3.5% 상승할 것으로 전망된다")
    assert "시작" in e.value.reason


def test_rejects_a_fragment_starting_inside_a_decimal_percentage_point():
    with pytest.raises(v.Rejected) as e:
        v.verify("3%p 낮아질 것으로 예상된다", "물가는 0.3%p 낮아질 것으로 예상된다")
    assert "시작" in e.value.reason


def test_accepts_a_sentence_after_a_terminator_then_space():
    # 개행이 아니라 그냥 띄어쓰기로 이어지는 경우도 종결부호 판정이 걸린다.
    page = "앞 문장이다. 취업자는 증가했다"
    candidate = "취업자는 증가했다"
    assert v.verify(candidate, page) == candidate


def test_rejects_a_fragment_starting_inside_a_decimal_split_by_a_line_wrap():
    # pdfplumber 의 줄 감김이 소수점 한가운데를 지날 수 있다 — 이 모듈이
    # 애초에 공백(개행 포함)을 무시하는 이유(엉뚱한 공백)와 같은 현상이다.
    # 앞뒤가 줄로 떨어져 있어도 숫자 사이의 마침표는 소수점이지 문장
    # 끝이 아니다.
    with pytest.raises(v.Rejected) as e:
        v.verify("5% 상승할 것으로 전망된다", "성장률은 3.\n5% 상승할 것으로 전망된다")
    assert "시작" in e.value.reason


def test_accepts_a_sentence_starting_with_a_digit_after_a_real_terminator():
    # 마침표 앞이 숫자가 아니면(문장이 실제로 끝난 것이면) 뒤에 숫자로
    # 시작하는 문장이 와도 소수점으로 오인하지 않고 경계로 인정해야 한다.
    page = "앞 문장이 있다. 5% 성장이 예상된다"
    candidate = "5% 성장이 예상된다"
    assert v.verify(candidate, page) == candidate


def test_rejects_a_numbered_heading_starting_with_a_digit_as_an_accepted_trade():
    # "3. 5%…" 처럼 번호 붙은 항목의 내용이 우연히 숫자로 시작하면, 마침표
    # 앞뒤가 모두 숫자라는 이유로 소수점으로 오인해 항목 경계를 놓친다.
    # 이것은 버그가 아니라 일부러 받아들이는 손해다 — 근거를 하나 놓쳐
    # 빈 칸으로 남는 편이, 두 자리를 이어 붙여 기관이 하지 않은 문장을
    # 내보내는 것보다 낫다.
    page = "3. 5% 성장률의 배경"
    candidate = "5% 성장률의 배경"
    with pytest.raises(v.Rejected):
        v.verify(candidate, page)


def test_rejects_a_fragment_starting_after_a_decimal_point_split_by_a_space():
    # pdfplumber 는 페이지 여백 위치로 줄을 감으므로, 숫자 뒤에서 마침표가
    # 다음 줄로 넘어가는 것("3.\n5%")과 마침표 뒤에서 숫자가 넘어가는 것
    # ("3 .5%") 둘 다 물리적으로 똑같이 있을 법하다 — 거울상이다.
    with pytest.raises(v.Rejected) as e:
        v.verify("5% 상승할 것으로 전망된다", "성장률은 3 .5% 상승할 것으로 전망된다")
    assert "시작" in e.value.reason


def test_rejects_a_fragment_starting_after_a_decimal_point_split_by_a_line_wrap():
    with pytest.raises(v.Rejected) as e:
        v.verify("5% 상승할 것으로 전망된다", "성장률은 3\n. 5% 상승할 것으로 전망된다")
    assert "시작" in e.value.reason


def test_rejects_a_fragment_starting_after_a_line_leading_minus_sign():
    # pdfplumber 는 배치 위치로 줄을 감으므로, 줄 첫머리가 음수로 시작하는
    # 것("-0.3%p")도 마이너스 부호로 시작하는 줄만큼 있을 법하다 — 줄
    # 첫머리라는 조건만으로는 표지와 음수 부호를 못 가른다.
    page = "물가 상승률이 둔화되면서 실질소득이 늘어\n-0.3%p 낮아질 것으로 예상된다"
    with pytest.raises(v.Rejected) as e:
        v.verify("0.3%p 낮아질 것으로 예상된다", page)
    assert "시작" in e.value.reason


def test_rejects_a_fragment_starting_after_a_line_leading_equals_sign():
    # '=' 도 _WRAP_BOUNDARY_MARKERS 를 통해 같은 모양의 구멍이다.
    page = "고용 흐름 요약\n=2026년 취업자는 크게 늘어날 것으로 보인다"
    with pytest.raises(v.Rejected) as e:
        v.verify("2026년 취업자는 크게 늘어날 것으로 보인다", page)
    assert "시작" in e.value.reason


def test_accepts_a_sentence_that_includes_its_own_bullet_marker():
    # LLM 이 표지까지 포함해 후보를 돌려줄 수 있다. 이 경우 표지 앞은 앞
    # 줄의 마지막 글자라 뒤를 보는 판정으로는 절대 못 찾는다 — 국문 보고서
    # 불릿은 마침표 없이 끝나는 게 보통이기 때문이다.
    page = "고용 전망\nㅇ 소비가 회복되면서 취업자가 늘어날 것으로 예상된다\nㅇ 건설투자는 부진하다"
    candidate = "ㅇ 소비가 회복되면서 취업자가 늘어날 것으로 예상된다"
    assert v.verify(candidate, page) == candidate


def test_accepts_a_sentence_that_includes_its_own_dash_marker():
    page = "개요\n- 항목 내용입니다 계속된다"
    candidate = "- 항목 내용입니다 계속된다"
    assert v.verify(candidate, page) == candidate


# 표지도 마침표도 없이 세로 간격으로만 갈리는 항목(KDI 요약 쪽) — pdf 가
# 그 자리에 빈 줄을 넣어 주므로, 빈 줄을 항목 시작으로 인정한다.
FUSED = ("우리 경제는 반도체경기 호황에 힘입어\n"
         "2027년에도 2.2% 성장할 전망\n"
         "\n"
         "취업자 수는 내수 개선세가 파급되면서\n"
         "20만명으로 확대될 전망")


def test_accepts_an_item_that_starts_after_a_blank_line():
    candidate = "취업자 수는 내수 개선세가 파급되면서 20만명으로 확대될 전망"
    assert v.verify(candidate, FUSED) == candidate


def test_still_rejects_a_fragment_starting_at_a_wrapped_line_without_a_blank_line():
    with pytest.raises(v.Rejected):
        v.verify("20만명으로 확대될 전망", FUSED)


def test_rejects_a_candidate_that_welds_two_items_across_a_blank_line():
    """지어낸 문장은 아니지만 기관이 한 문장으로 말한 것도 아니다. 실측:
    KDI 2025-08 4쪽에서 물가 항목과 고용 항목이 한 근거로 붙어 저장됐다.
    공백을 지우고 대조하므로 빈 줄을 건너뛴 후보도 부분열로 통과한다 —
    시작 자리만 보고 끝을 안 보기 때문이다."""
    welded = ("우리 경제는 반도체경기 호황에 힘입어 2027년에도 2.2% 성장할 전망 "
              "취업자 수는 내수 개선세가 파급되면서 20만명으로 확대될 전망")
    with pytest.raises(v.Rejected):
        v.verify(welded, FUSED)


def test_still_accepts_a_candidate_that_spans_an_ordinary_line_wrap():
    """빈 줄이 아닌 줄바꿈 하나는 감김이다 — 막으면 안 된다."""
    candidate = "우리 경제는 반도체경기 호황에 힘입어 2027년에도 2.2% 성장할 전망"
    assert v.verify(candidate, FUSED) == candidate


# BOK 정기 보고서가 쓰는 표지 — 실측(2026년 8월호): ▢ 15줄, ▪ 25줄.
# 둘 다 지금 표지 집합에 없어 그 항목의 근거가 통째로 거절됐다.
BOK_PAGE = ("▢ [반도체 경기] 글로벌 AI 인프라 투자가 지속적으로 확대됨에 따라 반도체\n"
            "수출이 높은 증가세를 이어갈 전망\n"
            "▪견조한 반도체 수요가 지속되는 가운데 생산능력은 점진적으로 증대")


def test_accepts_an_item_after_a_bok_square_marker():
    candidate = ("[반도체 경기] 글로벌 AI 인프라 투자가 지속적으로 확대됨에 따라 "
                 "반도체 수출이 높은 증가세를 이어갈 전망")
    assert v.verify(candidate, BOK_PAGE) == candidate


def test_accepts_an_item_after_a_bok_marker_with_no_space_behind_it():
    """▪ 는 뒤에 공백 없이 붙는다("▪견조한"). 표지 한 글자짜리에 공백을
    요구하는 규칙은 '-0.3%p' 를 불릿으로 오인하지 않으려던 것인데, ▪·▢ 는
    숫자나 낱말의 일부가 될 수 없어 그 조건이 필요 없다."""
    candidate = "견조한 반도체 수요가 지속되는 가운데 생산능력은 점진적으로 증대"
    assert v.verify(candidate, BOK_PAGE) == candidate


# 모델은 맞는 문장을 찾고도 쪽번호를 틀리게 댄다 — 실측(BOK 2026년 8월):
# cpi 를 8쪽이라 했는데 실제로는 11쪽, emp_change 를 23쪽이라 했는데 39쪽.
# 같은 회차를 다시 돌리면 다른 쪽번호가 나온다(KLI 는 24↔23 으로 흔들렸다).
PAGES = ["첫 쪽에는 아무것도 없다.",
         "둘째 쪽이다. 취업자 수는 내수 개선세가 파급되면서 늘어날 전망",
         "셋째 쪽이다."]


def test_finds_the_page_the_sentence_is_actually_on():
    got, page = v.verify_in_pages("취업자 수는 내수 개선세가 파급되면서 늘어날 전망",
                                  PAGES, hinted_page=1)
    assert page == 2
    assert got == "취업자 수는 내수 개선세가 파급되면서 늘어날 전망"


def test_keeps_the_hinted_page_when_the_sentence_is_really_there():
    _, page = v.verify_in_pages("취업자 수는 내수 개선세가 파급되면서 늘어날 전망",
                                PAGES, hinted_page=2)
    assert page == 2


def test_searches_even_when_the_hinted_page_is_out_of_range():
    _, page = v.verify_in_pages("취업자 수는 내수 개선세가 파급되면서 늘어날 전망",
                                PAGES, hinted_page=99)
    assert page == 2


def test_rejects_when_the_sentence_is_on_no_page():
    with pytest.raises(v.Rejected) as e:
        v.verify_in_pages("이 문장은 어느 쪽에도 없다", PAGES, hinted_page=1)
    assert "원문에 없다" in e.value.reason


def test_reports_the_real_reason_when_the_sentence_exists_but_fails_a_check():
    """어느 쪽에도 안 걸릴 때만 '원문에 없다' 다. 있는데 다른 검사에 걸린
    것이면 그 사유를 그대로 줘야 사람이 엉뚱한 가설로 새지 않는다."""
    with pytest.raises(v.Rejected) as e:
        v.verify_in_pages("내수 개선세가 파급되면서 늘어날 전망", PAGES, hinted_page=1)
    assert "시작하는 자리" in e.value.reason


def test_matching_ignores_private_use_glyphs():
    """실측: BOK 본문에 사설영역 글자가 섞여 나온다(2026년 8월호에서 U+E0F8
    30줄, U+F000 25줄). 글꼴이 유니코드로 안 매핑해 남은 자국이라 뜻이 없고,
    모델은 그것을 옮겨 적지 않는다 — 원문에만 남아 대조를 깨뜨린다."""
    pua = chr(0xE0F8)
    page = f"취업자 수는{pua} 내수 개선세가 파급되면서 늘어날 전망"
    candidate = "취업자 수는 내수 개선세가 파급되면서 늘어날 전망"
    assert v.verify(candidate, page) == candidate


def test_matching_normalizes_compatibility_forms():
    """전각 숫자·괄호 같은 호환 문자를 모델이 보통 형태로 옮겨 적어도 통과한다."""
    page = "취업자 수는 ２０만명으로 확대될 전망"
    candidate = "취업자 수는 20만명으로 확대될 전망"
    assert v.verify(candidate, page) == candidate


def test_accepts_an_item_after_a_marker_that_is_on_no_whitelist():
    """표지 목록을 유한하게 두면 회차마다 새 기호가 나와 깨진다(실측: BOK 의
    ▢·▪). 목록 대신 '줄머리에서 글자가 시작하기 전까지의 기호 무리' 로 본다 —
    ◈ 는 이 저장소가 한 번도 본 적 없는 기호다."""
    page = "◈ 금년 국내경제는 반도체 경기 호황으로 높은 성장세를 나타낼 전망"
    candidate = "금년 국내경제는 반도체 경기 호황으로 높은 성장세를 나타낼 전망"
    assert v.verify(candidate, page) == candidate


def test_accepts_an_item_after_a_private_use_marker():
    """사설영역 글머리표도 같은 규칙으로 처리된다 — 따로 등록할 것이 없다."""
    page = f"{chr(0xF000)} 금년 취업자수는 건설업 부진으로 증가폭이 축소될 전망"
    candidate = "금년 취업자수는 건설업 부진으로 증가폭이 축소될 전망"
    assert v.verify(candidate, page) == candidate


def test_still_rejects_a_fragment_after_a_line_leading_minus_even_without_a_whitelist():
    """목록을 지워도 이 사례는 막혀야 한다 — 줄머리 기호 뒤가 숫자면
    글머리표가 아니라 음수 부호다."""
    page = "취업자 수는 예상보다 늘어\n-0.3%p 낮아질 것으로 보인다"
    with pytest.raises(v.Rejected):
        v.verify("0.3%p 낮아질 것으로 보인다", page)


def test_still_rejects_a_wrapped_continuation_line_that_has_no_marker():
    """줄머리라는 것만으로는 항목 시작이 아니다 — 감긴 줄도 줄머리다."""
    page = "우리 경제는 반도체경기 호황에 힘입어\n기록한 뒤 2.2% 성장할 전망"
    with pytest.raises(v.Rejected):
        v.verify("기록한 뒤 2.2% 성장할 전망", page)


# ── OCR 잡음 ──────────────────────────────────────────────────────────
# 검사기의 원문 대조로는 못 잡는 결함이다: OCR 원문 자체가 깨져 있으면
# 깨진 그대로가 '원문에 있는' 문장이라 통과한다. 실제로 KEIS 근거 열넷 중
# 일곱이 그렇게 들어왔다.

@pytest.mark.parametrize("text, noise", [
    ("2026년 고용의 OF 확대 SS 제한적인 모습", "OF"),
    ("경제활동 참여가 지속 SOTA 노동공급 기반이 유지되고", "SOTA"),
    ("‘AWS’ 인구는 증가하고 있으며", "AWS"),
    ("취업 경험이 없는 APE 대다수가 청년층에 해당하며", "APE"),
    ("임시직 SHS 증가한 것으로 확인", "SHS"),
])
def test_OCR_가_한글을_대문자로_잘못_읽은_자국을_잡는다(text, noise):
    assert v.ocr_noise(text) == noise


@pytest.mark.parametrize("text", [
    "하반기에는 건설경기 부진 완화와 내수 회복이 점진적으로 반영되고",
    "만성적인 인력 공급제약(인력 부족)은 취업자 수 감소에 영향을 미칠 것으로 예상됨",
    # 이 도메인 글에 정말로 나오는 약어는 통과해야 한다 — 안 그러면
    # 멀쩡한 근거가 통째로 걸린다.
    "OECD 와 IMF 는 2026년 GDP 성장률을 상향 조정했다",
    "AI 반도체 호조로 IT 수출이 늘었다",
    "R&D 투자와 FTA 효과가 성장을 뒷받침",
])
def test_멀쩡한_문장과_아는_약어는_통과한다(text):
    assert v.ocr_noise(text) is None
