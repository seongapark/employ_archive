import pytest
from pydantic import ValidationError
from domains.ask.pipeline.models import CapabilityLimit, HypIndicator, Indicator

LIMIT_TYPES = {"커버리지", "교차제한", "입도", "시의성", "접근성", "업데이트"}


def test_limit_types_are_exactly_six():
    assert set(CapabilityLimit.model_fields["유형"].annotation.__args__) == LIMIT_TYPES


def test_confirmed_evidence_requires_source_and_date():
    with pytest.raises(ValidationError, match="근거"):
        CapabilityLimit(id="L1", source_id="est", 유형="교차제한",
                        내용="성·연령 미제공", 사유="발표하지 않음",
                        evidence=None, verified_at=None, evidence_status="확인")


def test_semiannual_indicator_cannot_be_lead_lag_tested():
    # 반기 지표에 선후를 붙이는 실수는 데이터 단계에서 막힌다
    with pytest.raises(ValidationError, match="선후검정"):
        HypIndicator(hypothesis_id="H3_산업구조",
                     indicator_id="IND_청년사무직취업자",
                     role="falsifies", timing="선후검정",
                     expected_sign="-", lead_lag="선행 3개월",
                     falsifies="…", time_grain="반기")


def test_rate_only_indicator_rejects_level_comparison():
    ind = Indicator(id="IND_KGJ피보험자", name_ko="K·G·J 피보험자", source_id="ei",
                    정의="고용보험 상시가입자", 모집단="고용보험 가입자", 단위="천명",
                    공표시차="M+10일", 커버리지한계="미가입 제외",
                    data_status="보유", time_grain="월", compare_basis="증감률만",
                    series_key="ei:industry")
    assert ind.compare_basis == "증감률만"
