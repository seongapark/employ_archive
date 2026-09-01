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
