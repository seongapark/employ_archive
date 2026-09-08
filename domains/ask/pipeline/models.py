"""질의응답 카탈로그 모델.

시계열이 아니라 **카탈로그**다. 무엇을 줄 수 있고 무엇을 못 주는지를 담는다.
`evidence`·`verified_at` 이 필수인 이유는 기획서 §2-2 의 "미확인 제약은 등재 금지"
규율 때문이다 — 추측이 섞이면 "못 한다" 는 답 자체를 신뢰할 수 없게 된다.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, model_validator

Grade = Literal["A", "B", "C", "X"]
Axis = Literal["A", "B", "C", "D", "E"]
EvidenceStatus = Literal["확인", "미확인"]
LimitType = Literal["커버리지", "교차제한", "입도", "시의성", "접근성", "업데이트"]
TimeGrain = Literal["월", "반기", "연"]
CompareBasis = Literal["수준", "증감률만"]
Role = Literal["지지", "falsifies"]
Timing = Literal["선후검정", "수준확인", "특정성"]
Comparable = Literal["수준", "증감률만", "불가"]
DataStatus = Literal["보유", "미보유"]


class Evidenced(BaseModel):
    evidence: Optional[str] = None
    verified_at: Optional[str] = None
    evidence_status: EvidenceStatus = "미확인"

    @model_validator(mode="after")
    def confirmed_needs_evidence(self):
        if self.evidence_status == "확인" and not (self.evidence and self.verified_at):
            raise ValueError("근거: evidence_status='확인' 이면 evidence 와 verified_at 이 있어야 한다")
        return self


class SourceCatalog(Evidenced):
    id: str
    name_ko: str
    agency: str
    grade: Grade
    axis: Axis
    method: str
    auth: str
    endpoint: Optional[str] = None
    rate_limit: Optional[str] = None
    archived: bool = False
    priority: Optional[int] = None
    terms_of_use: Optional[str] = None
    body_storable: Optional[bool] = None


class Capability(Evidenced):
    source_id: str
    주제: list[str] = []
    집단축: list[str] = []
    지역입도: list[str] = []
    시간입도: list[str] = []
    기간_from: Optional[str] = None
    기간_to: Optional[str] = None
    공표시차: Optional[str] = None


class CapabilityLimit(Evidenced):
    id: str
    source_id: str
    유형: LimitType
    axis: Optional[str] = None
    category: Optional[str] = None
    내용: str
    사유: str


class SourceConflict(Evidenced):
    id: str
    source_a: str
    source_b: str
    차이유형: Literal["개념", "모집단", "교차제한", "산업커버리지", "시의성"]
    설명: str
    비교가능: Comparable


class Phenomenon(BaseModel):
    id: str
    name_ko: str
    정의: str
    지역: str
    기간: str
    time_grain: TimeGrain
    근거서술: str


class Hypothesis(BaseModel):
    id: str
    phenomenon_id: str
    name_ko: str
    서술: str
    대립가설: list[str]
    missing_for_verdict: list[str] = []
    우회경로: Optional[str] = None
    검정력_주석: Optional[str] = None

    @model_validator(mode="after")
    def needs_counter_hypothesis(self):
        # 기획서 §8 — 대립가설 없는 가설은 등록 거부
        if not self.대립가설:
            raise ValueError("대립가설: 대립가설 없는 가설은 등록하지 않는다")
        return self


class Indicator(BaseModel):
    id: str
    name_ko: str
    source_id: str
    정의: str
    모집단: str
    단위: str
    공표시차: str
    커버리지한계: str
    data_status: DataStatus
    time_grain: TimeGrain
    compare_basis: CompareBasis
    series_key: Optional[str] = None


class HypIndicator(BaseModel):
    hypothesis_id: str
    indicator_id: str
    role: Role
    timing: Timing
    expected_sign: Optional[Literal["+", "-", "0"]] = None
    lead_lag: Optional[str] = None
    falsifies: Optional[str] = None
    # 지표의 주기를 함께 받아 체크 제약을 데이터 단계에서 건다
    time_grain: TimeGrain

    @model_validator(mode="after")
    def lead_lag_needs_monthly(self):
        if self.timing == "선후검정" and self.time_grain != "월":
            raise ValueError("선후검정: 월별 지표에만 붙일 수 있다")
        if self.timing != "선후검정" and self.lead_lag:
            raise ValueError("선후검정: lead_lag 는 timing='선후검정' 에서만 읽는다")
        return self
