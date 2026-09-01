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
    # pdfplumber 가 낱말 중간에 넣은 공백을 LLM 이 붙여 써도 통과한다
    page = "에너지 가격 상승이 물가 부담으로 작용하 고, 회복세를 제한한다"
    assert v.verify("물가 부담으로 작용하고, 회복세를 제한한다", page)


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
