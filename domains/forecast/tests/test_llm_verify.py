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
    # "-" 는 불릿이자 음수 부호다(rationale._is_bullet_marker_line 참고).
    # 줄 첫머리가 아니라 "성장률은 " 뒤에 온 "-" 는 표지가 아니라 부호이므로
    # 그 뒤에서 시작하는 조각은 "성장률은" 이라는 주어를 자른 것이다.
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
    # "." 는 문장 종결부호이자 소수점이다(rationale._DECIMAL_POINT 참고).
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
