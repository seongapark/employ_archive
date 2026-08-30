# C단계 고용동향 데이터 파이프라인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 경제활동인구조사·사업체노동력조사·고용행정통계 세 출처의 월별 고용 수치를 산업 대분류까지 자동 수집해 `domains/employment/data/series.json` 에 최근 24개월치를 적재한다.

**Architecture:** 전망 도메인의 파이프라인 구조(`models` / `store` / `collectors` / `collect` 오케스트레이터 + `last_run.json` + `check_run` CI 게이트)를 그대로 따른다. 다만 실적 통계는 회차 이력을 쌓지 않고 **같은 키를 덮어쓴다**(과거 수치가 개정되기 때문). 수집 경로는 출처마다 다르지만(게시판 xlsx / KOSIS API / 게시판 hwpx) 산출 레코드는 하나의 스키마로 수렴한다. 새 서드파티 의존성은 없다 — xlsx·hwpx 모두 ZIP+XML 이라 표준 라이브러리로 읽는다.

**Tech Stack:** Python 3.12, pydantic v2, requests, pytest (전부 `requirements.txt` 에 이미 있음). 표준 라이브러리 `zipfile` + `xml.etree.ElementTree` 로 xlsx·hwpx 파싱.

**Spec:** `docs/superpowers/specs/2026-08-29-고용데이터아카이브-플랫폼-design.md` (7장)
**스파이크:** `docs/superpowers/spikes/2026-08-30-고용행정통계-보도자료-파싱.md` — 아래 모든 URL·파라미터·표 구조는 이 문서에서 실측된 값이다. 추측이 아니다.

## Global Constraints

- **`git add -A` / `git commit -a` 를 쓰지 않는다.** 이 저장소에서 다른 세션이 병렬 작업 중이다. 항상 그 태스크가 만든 경로만 명시해서 add 한다.
- **새 서드파티 의존성을 추가하지 않는다.** `requirements.txt` 를 건드리지 마라. xlsx·hwpx 는 표준 라이브러리로 읽는다.
- **테스트는 네트워크 없이 돈다.** 모든 파싱 테스트는 저장소에 커밋된 픽스처를 쓴다. 네트워크를 타는 코드는 테스트에서 호출하지 않는다.
- **`domains/employment/` 밖을 건드리지 않는다.** 단, Task 8 이 `.github/workflows/collect-employment.yml` 을 새로 만든다.
- **단위는 천명으로 통일한다.** KOSIS 사업체노동력조사는 `명` 으로 주므로 1000 으로 나눠 소수 첫째자리로 반올림한다.
- **`last_run.json` 은 저장소에 커밋된다.** 예외 트레이스백을 담지 마라 — 돌린 사람의 절대경로가 함께 실린다. `f"{name}: {type(exc).__name__}: {exc}"` 한 줄만 남긴다(전망 도메인과 동일).
- **파이썬 실행 진입점은 `python -m domains.employment.pipeline.<모듈>` 형식이다.**

---

## File Structure

**신규 — 데이터**
- `domains/employment/data/sources.json` — 세 출처의 정의(화면에 상시 노출)
- `domains/employment/data/industries.json` — 표준산업분류 대분류 × 출처별 제공 여부
- `domains/employment/data/series.json` — 시계열 레코드 (수집기가 생성)
- `domains/employment/data/last_run.json` — 실행 요약 (수집기가 생성)
- `domains/employment/data/manual/` — 수기 입력 폴백 (`.gitkeep` 만 먼저)

**신규 — 파이프라인**
- `domains/employment/pipeline/__init__.py`
- `domains/employment/pipeline/models.py` — `SeriesRecord`, `Attachment`, `make_id`
- `domains/employment/pipeline/store.py` — 적재·병합(덮어쓰기 의미론)
- `domains/employment/pipeline/xlsx.py` — xlsx 시트를 2차원 문자열 배열로
- `domains/employment/pipeline/hwpx.py` — hwpx 표를 2차원 문자열 배열로 (전 섹션)
- `domains/employment/pipeline/collectors/__init__.py`
- `domains/employment/pipeline/collectors/eaps.py` — 경제활동인구조사
- `domains/employment/pipeline/collectors/est.py` — 사업체노동력조사
- `domains/employment/pipeline/collectors/ei.py` — 고용행정통계
- `domains/employment/pipeline/collect.py` — 오케스트레이터
- `domains/employment/pipeline/check_run.py` — CI 게이트

**신규 — 테스트**
- `domains/employment/__init__.py`, `domains/employment/pipeline/__init__.py`
- `domains/employment/tests/__init__.py` (**필수** — 없으면 전망 도메인의 동명 테스트 모듈과 충돌한다)
- `domains/employment/tests/fixtures/` — 실제 받은 xlsx·hwpx (Task 3·4 에서 만든다)
- `domains/employment/tests/test_models.py`, `test_store.py`, `test_xlsx.py`, `test_hwpx.py`, `test_eaps.py`, `test_est.py`, `test_ei.py`, `test_metadata.py`, `test_collect.py`

**신규 — CI**
- `.github/workflows/collect-employment.yml`

---

### Task 1: 스키마와 저장소

**Files:**
- Create: `domains/employment/__init__.py`, `domains/employment/pipeline/__init__.py`, `domains/employment/tests/__init__.py`
- Create: `domains/employment/pipeline/models.py`, `domains/employment/pipeline/store.py`
- Create: `domains/employment/tests/test_models.py`, `domains/employment/tests/test_store.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `models.SeriesRecord` (pydantic BaseModel) — 필드는 아래 코드 참조
  - `models.Attachment` (pydantic BaseModel) — `type: Literal["hwpx","pdf","xlsx"]`, `url: str`
  - `models.make_id(source: str, period: str, breakdown: str, category: str | None) -> str`
  - `store.load_series(path) -> list[SeriesRecord]`
  - `store.save_series(path, records) -> None`
  - `store.upsert(existing: list[SeriesRecord], incoming: list[SeriesRecord]) -> UpsertResult`
  - `store.UpsertResult` — `records: list[SeriesRecord]`, `added: list[str]`, `updated: list[str]`, `unchanged: list[str]`

**왜 덮어쓰기인가:** 스파이크 7장에서 확인했다 — 2026년 6월 상시가입자 수준이 6월 발표본에서 `15,855`, 7월 발표본에서 `15,856` 이었다. 잠정치가 나중에 조정된다. 전망 도메인은 회차별 이력이 곧 콘텐츠라 append 하지만, 실적 통계에서 중요한 것은 최신 확정값이다.

- [ ] **Step 1: 패키지 초기화 파일 3개를 만든다**

```bash
mkdir -p domains/employment/pipeline domains/employment/tests domains/employment/data/manual
touch domains/employment/__init__.py domains/employment/pipeline/__init__.py domains/employment/tests/__init__.py
touch domains/employment/data/manual/.gitkeep
```

`domains/employment/tests/__init__.py` 는 반드시 만든다. 전망 도메인에도 있으며, 없으면 두 도메인의 동명 테스트 모듈이 최상위 이름으로 충돌해 pytest 수집이 중단된다.

- [ ] **Step 2: 실패하는 모델 테스트를 쓴다**

`domains/employment/tests/test_models.py`:

```python
from datetime import date, datetime

import pytest
from pydantic import ValidationError

from domains.employment.pipeline.models import Attachment, SeriesRecord, make_id


def rec(**over):
    base = dict(
        id="ei-2026-07-headcount-total",
        source="ei", series="headcount", breakdown="total", category=None,
        period="2026-07", value=15877.0, unit="천명", yoy=277.0, status="잠정",
        released_at=date(2026, 8, 11),
        release_url="https://www.moel.go.kr/news/enews/report/enewsView.do?news_seq=19759",
        attachments=[], collected_at=datetime(2026, 8, 30, 9, 0),
    )
    base.update(over)
    return SeriesRecord(**base)


def test_accepts_a_total_record():
    assert rec().breakdown == "total"


def test_industry_record_requires_a_category():
    with pytest.raises(ValidationError):
        rec(breakdown="industry", category=None)


def test_total_record_rejects_a_category():
    with pytest.raises(ValidationError):
        rec(breakdown="total", category="C")


def test_period_must_be_year_month():
    with pytest.raises(ValidationError):
        rec(period="2026-7")


def test_release_url_must_be_http():
    with pytest.raises(ValidationError):
        rec(release_url="javascript:alert(1)")


def test_attachments_carry_type_and_url():
    r = rec(attachments=[Attachment(type="hwpx", url="https://x/a.hwpx")])
    assert r.attachments[0].type == "hwpx"


def test_make_id_includes_category_only_for_industry():
    assert make_id("eaps", "2026-07", "total", None) == "eaps-2026-07-headcount-total"
    assert make_id("eaps", "2026-07", "industry", "C") == "eaps-2026-07-headcount-industry-C"
```

- [ ] **Step 3: 실패를 확인한다**

Run: `python -m pytest domains/employment/tests/test_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'domains.employment.pipeline.models'`

- [ ] **Step 4: `models.py` 를 구현한다**

```python
"""고용동향 시계열 레코드.

전망 도메인과 달리 회차 이력을 쌓지 않는다. 실적 통계는 과거 수치가 개정되므로
같은 키(id)를 덮어쓰고 released_at 을 갱신한다.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

Source = Literal["eaps", "est", "ei"]
Breakdown = Literal["total", "industry"]
Status = Literal["잠정", "확정"]

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def make_id(source: str, period: str, breakdown: str, category: Optional[str]) -> str:
    tail = f"-{category}" if breakdown == "industry" else ""
    return f"{source}-{period}-headcount-{breakdown}{tail}"


class Attachment(BaseModel):
    type: Literal["hwpx", "pdf", "xlsx"]
    url: str


class SeriesRecord(BaseModel):
    id: str
    source: Source
    series: Literal["headcount"] = "headcount"
    breakdown: Breakdown
    category: Optional[str] = None
    period: str
    value: float
    unit: Literal["천명"] = "천명"
    yoy: Optional[float] = None
    status: Status = "잠정"
    released_at: date
    release_url: str
    attachments: list[Attachment] = Field(default_factory=list)
    collected_at: datetime

    @field_validator("period")
    @classmethod
    def check_period(cls, v: str) -> str:
        if not PERIOD_RE.match(v):
            raise ValueError(f"period 는 YYYY-MM 이어야 한다: {v!r}")
        return v

    @field_validator("release_url")
    @classmethod
    def check_url_scheme(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"release_url 은 http(s) 여야 한다: {v!r}")
        return v

    @model_validator(mode="after")
    def check_category(self):
        if self.breakdown == "industry" and not self.category:
            raise ValueError("breakdown=industry 는 category 가 필요하다")
        if self.breakdown == "total" and self.category:
            raise ValueError("breakdown=total 은 category 를 가질 수 없다")
        return self
```

- [ ] **Step 5: 모델 테스트 통과를 확인한다**

Run: `python -m pytest domains/employment/tests/test_models.py -q`
Expected: PASS (7 passed)

- [ ] **Step 6: 실패하는 저장소 테스트를 쓴다**

`domains/employment/tests/test_store.py`:

```python
from datetime import date, datetime

from domains.employment.pipeline.models import SeriesRecord
from domains.employment.pipeline import store


def rec(period="2026-07", value=15877.0, yoy=277.0, released=date(2026, 8, 11),
        breakdown="total", category=None, source="ei"):
    from domains.employment.pipeline.models import make_id
    return SeriesRecord(
        id=make_id(source, period, breakdown, category),
        source=source, breakdown=breakdown, category=category, period=period,
        value=value, yoy=yoy, released_at=released,
        release_url="https://x/view?news_seq=1",
        collected_at=datetime(2026, 8, 30, 9, 0),
    )


def test_upsert_adds_new_records():
    r = store.upsert([], [rec()])
    assert r.added == ["ei-2026-07-headcount-total"]
    assert len(r.records) == 1


def test_upsert_leaves_identical_records_alone():
    first = [rec()]
    r = store.upsert(first, [rec()])
    assert r.unchanged == ["ei-2026-07-headcount-total"]
    assert r.added == [] and r.updated == []


def test_upsert_overwrites_a_revised_value():
    # 6월 수치가 7월 발표본에서 15855 -> 15856 으로 조정된 실제 사례
    old = [rec(period="2026-06", value=15855.0, released=date(2026, 7, 14))]
    new = [rec(period="2026-06", value=15856.0, released=date(2026, 8, 11))]
    r = store.upsert(old, new)
    assert r.updated == ["ei-2026-06-headcount-total"]
    assert len(r.records) == 1
    assert r.records[0].value == 15856.0
    assert r.records[0].released_at == date(2026, 8, 11)


def test_upsert_ignores_a_stale_release():
    # 더 오래된 발표본이 뒤늦게 들어와도 최신 수치를 덮지 않는다
    new_first = [rec(period="2026-06", value=15856.0, released=date(2026, 8, 11))]
    stale = [rec(period="2026-06", value=15855.0, released=date(2026, 7, 14))]
    r = store.upsert(new_first, stale)
    assert r.records[0].value == 15856.0
    assert r.updated == []


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "series.json"
    store.save_series(path, [rec(), rec(period="2026-06")])
    back = store.load_series(path)
    assert [b.id for b in back] == [
        "ei-2026-06-headcount-total", "ei-2026-07-headcount-total"
    ]


def test_load_returns_empty_when_the_file_is_missing(tmp_path):
    assert store.load_series(tmp_path / "nope.json") == []
```

- [ ] **Step 7: 실패를 확인한다**

Run: `python -m pytest domains/employment/tests/test_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'domains.employment.pipeline.store'`

- [ ] **Step 8: `store.py` 를 구현한다**

```python
"""시계열 적재. 같은 id 는 덮어쓴다 — 실적 통계는 과거 수치가 개정된다."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import SeriesRecord


@dataclass
class UpsertResult:
    records: list[SeriesRecord]
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)


def load_series(path: Path | str) -> list[SeriesRecord]:
    p = Path(path)
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    return [SeriesRecord.model_validate(row) for row in raw]


def save_series(path: Path | str, records: list[SeriesRecord]) -> None:
    ordered = sorted(records, key=lambda r: (r.period, r.source, r.id))
    rows = [r.model_dump(mode="json") for r in ordered]
    Path(path).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def upsert(existing: list[SeriesRecord],
           incoming: list[SeriesRecord]) -> UpsertResult:
    by_id = {r.id: r for r in existing}
    result = UpsertResult(records=list(existing))

    for cand in incoming:
        stored = by_id.get(cand.id)
        if stored is None:
            result.records.append(cand)
            by_id[cand.id] = cand
            result.added.append(cand.id)
            continue
        # 더 오래된 발표본이 뒤늦게 도착해도 최신 수치를 덮지 않는다.
        if cand.released_at < stored.released_at:
            continue
        if (stored.value, stored.yoy, stored.status) == (cand.value, cand.yoy, cand.status):
            result.unchanged.append(cand.id)
            continue
        result.records[result.records.index(stored)] = cand
        by_id[cand.id] = cand
        result.updated.append(cand.id)

    return result
```

- [ ] **Step 9: 저장소 테스트 통과와 전체 스위트를 확인한다**

Run: `python -m pytest domains/employment/tests/ -q`
Expected: PASS (13 passed)

Run: `python -m pytest -q`
Expected: PASS — 기존 테스트가 하나도 깨지지 않아야 한다

- [ ] **Step 10: 커밋**

```bash
git add domains/employment/__init__.py domains/employment/pipeline/ domains/employment/tests/ domains/employment/data/manual/.gitkeep
git commit -m "feat(employment): 시계열 스키마와 덮어쓰기 저장소"
```

---

### Task 2: 출처·산업 메타데이터

**Files:**
- Create: `domains/employment/data/sources.json`, `domains/employment/data/industries.json`
- Create: `domains/employment/tests/test_metadata.py`

**Interfaces:**
- Consumes: 없음
- Produces: 두 JSON 파일. 수집기(Task 5~7)와 화면(D단계)이 읽는다.
  - `sources.json` — 객체 배열, 키: `code`, `name_ko`, `agency`, `type`, `headline_ko`, `coverage`, `release_rule`, `caveat`, `board_url`
  - `industries.json` — 객체 배열, 키: `code`(A~U), `name_ko`, `provided`(객체: `eaps`/`est`/`ei` → bool)

**`provided` 값의 근거 (스파이크 실측):**
- `eaps` — 보도자료 xlsx 의 산업 열에 **광업(B)이 단독으로 없다.** `광공업` 이라는 집계 열에 제조업과 함께 묶여 있다.
- `est` — KOSIS `118/DT_118N_MON066` 의 대분류 18개를 확인했다. **A(농림어업)·T(가구내 고용)·U(국제기관)가 없다.** 사업체 조사라 조사대상이 아니다.
- `ei` — 보도자료 표의 산업 열에 B·T·U 가 없고 `기타*` 로 묶여 있다.

- [ ] **Step 1: 실패하는 메타데이터 테스트를 쓴다**

`domains/employment/tests/test_metadata.py`:

```python
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

SOURCES = {"eaps", "est", "ei"}
KSIC = list("ABCDEFGHIJKLMNOPQRSTU")


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def test_sources_has_the_three_sources_with_every_field():
    rows = load("sources.json")
    assert {r["code"] for r in rows} == SOURCES
    for r in rows:
        assert set(r) == {"code", "name_ko", "agency", "type", "headline_ko",
                          "coverage", "release_rule", "caveat", "board_url"}
        assert r["board_url"].startswith("https://")
        assert r["coverage"].strip()


def test_each_source_has_its_own_headline_name():
    rows = {r["code"]: r for r in load("sources.json")}
    names = {rows[c]["headline_ko"] for c in SOURCES}
    # 세 값을 같은 이름으로 부르면 이 앱의 존재 이유가 사라진다
    assert len(names) == 3
    assert rows["ei"]["headline_ko"] == "상시가입자수"


def test_industries_covers_every_ksic_major_division():
    rows = load("industries.json")
    assert [r["code"] for r in rows] == KSIC


def test_industries_declare_provision_per_source():
    for r in load("industries.json"):
        assert set(r["provided"]) == SOURCES
        assert all(isinstance(v, bool) for v in r["provided"].values())


def test_known_gaps_are_recorded():
    by_code = {r["code"]: r["provided"] for r in load("industries.json")}
    # 경활은 광업을 '광공업'에 묶어 단독 제공하지 않는다
    assert by_code["B"]["eaps"] is False
    # 사업체노동력조사는 농림어업·가구내고용·국제기관을 조사하지 않는다
    assert by_code["A"]["est"] is False
    assert by_code["T"]["est"] is False
    assert by_code["U"]["est"] is False
    # 고용행정통계는 광업·가구내고용·국제기관을 '기타'로 묶는다
    assert by_code["B"]["ei"] is False
    # 제조업·건설업·보건복지는 세 출처 모두 제공한다
    for code in ("C", "F", "Q"):
        assert all(by_code[code].values()), code
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest domains/employment/tests/test_metadata.py -q`
Expected: FAIL — `FileNotFoundError: ...sources.json`

- [ ] **Step 3: `sources.json` 을 만든다**

```json
[
  {
    "code": "eaps",
    "name_ko": "경제활동인구조사",
    "agency": "국가데이터처",
    "type": "가구조사",
    "headline_ko": "취업자수",
    "coverage": "15세 이상 인구 · 조사대상주간 1시간 이상 취업",
    "release_rule": "매월 중순, 전월 기준",
    "caveat": "자영업자·무급가족종사자를 포함한다",
    "board_url": "https://mods.go.kr/board.es?mid=a10301030100&bid=a103010301&ref_bid=210,211,11109,11113,11814"
  },
  {
    "code": "est",
    "name_ko": "사업체노동력조사",
    "agency": "고용노동부",
    "type": "사업체조사",
    "headline_ko": "종사자수",
    "coverage": "1인 이상 사업체 · 농림어업 등 제외",
    "release_rule": "매월 말, 전전월 기준",
    "caveat": "사업체 조사이므로 자영업자·무급가족종사자는 포함되지 않는다",
    "board_url": "https://kosis.kr/statHtml/statHtml.do?orgId=118&tblId=DT_118N_MON066"
  },
  {
    "code": "ei",
    "name_ko": "고용행정 통계로 본 노동시장 동향",
    "agency": "고용노동부",
    "type": "행정자료",
    "headline_ko": "상시가입자수",
    "coverage": "고용보험 가입 상시가입자",
    "release_rule": "매월 초, 전월 기준",
    "caveat": "고용보험 미가입 자영업자·특수형태근로 등은 포함되지 않는다",
    "board_url": "https://www.moel.go.kr/news/enews/report/enewsList.do"
  }
]
```

- [ ] **Step 4: `industries.json` 을 만든다**

```json
[
  {"code": "A", "name_ko": "농업, 임업 및 어업", "provided": {"eaps": true, "est": false, "ei": true}},
  {"code": "B", "name_ko": "광업", "provided": {"eaps": false, "est": true, "ei": false}},
  {"code": "C", "name_ko": "제조업", "provided": {"eaps": true, "est": true, "ei": true}},
  {"code": "D", "name_ko": "전기, 가스, 증기 및 공기조절 공급업", "provided": {"eaps": true, "est": true, "ei": true}},
  {"code": "E", "name_ko": "수도, 하수 및 폐기물 처리, 원료 재생업", "provided": {"eaps": true, "est": true, "ei": true}},
  {"code": "F", "name_ko": "건설업", "provided": {"eaps": true, "est": true, "ei": true}},
  {"code": "G", "name_ko": "도매 및 소매업", "provided": {"eaps": true, "est": true, "ei": true}},
  {"code": "H", "name_ko": "운수 및 창고업", "provided": {"eaps": true, "est": true, "ei": true}},
  {"code": "I", "name_ko": "숙박 및 음식점업", "provided": {"eaps": true, "est": true, "ei": true}},
  {"code": "J", "name_ko": "정보통신업", "provided": {"eaps": true, "est": true, "ei": true}},
  {"code": "K", "name_ko": "금융 및 보험업", "provided": {"eaps": true, "est": true, "ei": true}},
  {"code": "L", "name_ko": "부동산업", "provided": {"eaps": true, "est": true, "ei": true}},
  {"code": "M", "name_ko": "전문, 과학 및 기술 서비스업", "provided": {"eaps": true, "est": true, "ei": true}},
  {"code": "N", "name_ko": "사업시설 관리, 사업 지원 및 임대 서비스업", "provided": {"eaps": true, "est": true, "ei": true}},
  {"code": "O", "name_ko": "공공행정, 국방 및 사회보장 행정", "provided": {"eaps": true, "est": true, "ei": true}},
  {"code": "P", "name_ko": "교육 서비스업", "provided": {"eaps": true, "est": true, "ei": true}},
  {"code": "Q", "name_ko": "보건업 및 사회복지 서비스업", "provided": {"eaps": true, "est": true, "ei": true}},
  {"code": "R", "name_ko": "예술, 스포츠 및 여가관련 서비스업", "provided": {"eaps": true, "est": true, "ei": true}},
  {"code": "S", "name_ko": "협회 및 단체, 수리 및 기타 개인 서비스업", "provided": {"eaps": true, "est": true, "ei": true}},
  {"code": "T", "name_ko": "가구내 고용활동 및 달리 분류되지 않은 자가소비 생산활동", "provided": {"eaps": true, "est": false, "ei": false}},
  {"code": "U", "name_ko": "국제 및 외국기관", "provided": {"eaps": true, "est": false, "ei": false}}
]
```

- [ ] **Step 5: 통과를 확인한다**

Run: `python -m pytest domains/employment/tests/test_metadata.py -q`
Expected: PASS (5 passed)

- [ ] **Step 6: 커밋**

```bash
git add domains/employment/data/sources.json domains/employment/data/industries.json domains/employment/tests/test_metadata.py
git commit -m "feat(employment): 출처·산업 메타데이터"
```

---

### Task 3: xlsx 리더

**Files:**
- Create: `domains/employment/pipeline/xlsx.py`
- Create: `domains/employment/tests/test_xlsx.py`
- Create: `domains/employment/tests/fixtures/eaps_2026-07.xlsx` (실제 파일을 내려받아 커밋)

**Interfaces:**
- Consumes: 없음
- Produces:
  - `xlsx.sheet_names(data: bytes) -> list[str]`
  - `xlsx.read_sheet(data: bytes, name: str) -> list[list[str]]` — 셀 값을 문자열로. 빈 셀은 `""`.

**왜 직접 만드나:** `openpyxl` 을 쓰면 의존성이 늘어난다. xlsx 는 ZIP 안의 XML 이고 우리가 필요한 것은 "시트를 문자열 격자로 읽기" 하나뿐이라 40 줄이면 된다.

**주의 — 열 위치를 잃지 마라.** xlsx 는 빈 셀을 생략한다. `<c r="D5">` 처럼 셀마다 좌표가 붙어 있으므로 그 좌표로 격자에 배치해야 한다. 순서대로 이어붙이면 빈 셀만큼 열이 밀려 산업이 통째로 어긋난다.

- [ ] **Step 1: 픽스처를 내려받는다**

```bash
mkdir -p domains/employment/tests/fixtures
python - <<'EOF'
import re, requests
from pathlib import Path
H = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}
LIST = "https://mods.go.kr/board.es"
P = {"mid": "a10301030100", "bid": "a103010301",
     "ref_bid": "210,211,11109,11113,11814"}
html = requests.get(LIST, params=P, headers=H, timeout=30).text.replace("&amp;", "&")
m = re.search(r'href="(/boardDownload\.es\?[^"]+)"\s+class="bf_xlsx">'
              r'<span class="hdn">([^<]*?고용동향)의 xlsx파일', html)
assert m, "고용동향 xlsx 링크를 찾지 못했다"
data = requests.get("https://mods.go.kr" + m.group(1),
                    headers={**H, "Referer": LIST}, timeout=90).content
Path("domains/employment/tests/fixtures/eaps_2026-07.xlsx").write_bytes(data)
print(m.group(2), len(data), "bytes")
EOF
```

내려받은 파일이 `26년 7월 고용동향` 이 아니면(더 최신 회차가 나왔다면) 그대로 두고, Step 2 의 기대값을 그 회차의 실제 값으로 바꾼다. 기대값은 Step 4 에서 실제로 읽어 확인한다.

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`domains/employment/tests/test_xlsx.py`:

```python
from pathlib import Path

import pytest

from domains.employment.pipeline import xlsx

FIXTURE = Path(__file__).parent / "fixtures" / "eaps_2026-07.xlsx"


@pytest.fixture(scope="module")
def data():
    return FIXTURE.read_bytes()


def test_lists_the_industry_sheets(data):
    names = xlsx.sheet_names(data)
    for wanted in ["3.산업(신)", "3.산업(신) (2)", "3.산업증감(신)", "3.산업증감(신) (2)"]:
        assert wanted in names


def test_reads_the_industry_level_sheet(data):
    rows = xlsx.read_sheet(data, "3.산업(신)")
    joined = " ".join(" ".join(r) for r in rows[:8])
    assert "산업별 취업자" in joined
    assert "제조업" in joined
    assert "건설업" in joined


def test_keeps_empty_cells_in_place(data):
    # 빈 셀을 건너뛰면 산업 열이 통째로 밀린다. 헤더 행에 빈 칸이 남아 있어야 한다.
    rows = xlsx.read_sheet(data, "3.산업(신)")
    header = rows[3]
    assert "" in header


def test_unknown_sheet_raises(data):
    with pytest.raises(KeyError):
        xlsx.read_sheet(data, "없는시트")
```

- [ ] **Step 3: 실패를 확인한다**

Run: `python -m pytest domains/employment/tests/test_xlsx.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'domains.employment.pipeline.xlsx'`

- [ ] **Step 4: `xlsx.py` 를 구현한다**

```python
"""xlsx 를 문자열 격자로 읽는다.

openpyxl 을 쓰지 않는 이유는 의존성을 늘리지 않기 위해서다. xlsx 는 ZIP 안의
XML 이고 우리가 필요한 것은 시트 하나를 격자로 읽는 것뿐이다.
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"m": NS_MAIN, "r": NS_REL}

_CELL_REF = re.compile(r"^([A-Z]+)(\d+)$")


def _col_index(ref: str) -> int:
    """'A' -> 0, 'B' -> 1, 'AA' -> 26."""
    m = _CELL_REF.match(ref)
    letters = m.group(1) if m else ref
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(f"{{{NS_MAIN}}}t"))
            for si in root.findall("m:si", NS)]


def _sheet_paths(z: zipfile.ZipFile) -> dict[str, str]:
    rels = {r.get("Id"): r.get("Target")
            for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    paths = {}
    for sh in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", NS):
        target = rels[sh.get(f"{{{NS_REL}}}id")].lstrip("/")
        paths[sh.get("name")] = target if target.startswith("xl/") else "xl/" + target
    return paths


def sheet_names(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return list(_sheet_paths(z))


def read_sheet(data: bytes, name: str) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        paths = _sheet_paths(z)
        if name not in paths:
            raise KeyError(f"시트가 없다: {name!r}")
        sst = _shared_strings(z)
        root = ET.fromstring(z.read(paths[name]))

    rows: list[list[str]] = []
    for row in root.iter(f"{{{NS_MAIN}}}row"):
        cells: list[str] = []
        for c in row.findall("m:c", NS):
            # 빈 셀은 생략되므로 좌표로 자리를 맞춘다. 순서대로 이어붙이면
            # 빈 칸만큼 열이 밀려 산업이 통째로 어긋난다.
            idx = _col_index(c.get("r") or "")
            while len(cells) < idx:
                cells.append("")
            v = c.find("m:v", NS)
            if v is None or v.text is None:
                cells.append("")
            elif c.get("t") == "s":
                cells.append(sst[int(v.text)])
            else:
                cells.append(v.text)
        rows.append(cells)
    return rows
```

- [ ] **Step 5: 통과를 확인한다**

Run: `python -m pytest domains/employment/tests/test_xlsx.py -q`
Expected: PASS (4 passed)

- [ ] **Step 6: 커밋**

```bash
git add domains/employment/pipeline/xlsx.py domains/employment/tests/test_xlsx.py domains/employment/tests/fixtures/eaps_2026-07.xlsx
git commit -m "feat(employment): xlsx 리더 (표준 라이브러리)"
```

---

### Task 4: hwpx 리더

**Files:**
- Create: `domains/employment/pipeline/hwpx.py`
- Create: `domains/employment/tests/test_hwpx.py`
- Create: `domains/employment/tests/fixtures/ei_2026-07.hwpx` (이미지 제거해 경량화한 것)

**Interfaces:**
- Consumes: 없음
- Produces: `hwpx.tables(data: bytes) -> list[list[list[str]]]` — 문서 전체의 표를 순서대로. 각 표는 행 × 셀 문자열.

**반드시 지킬 것 — 섹션을 전부 읽어라.** hwpx 는 `Contents/section0.xml` 하나가 아닐 수 있다. 경활 보도자료는 `section0`·`section1`·`section2` 세 개이고 본문 표는 3.1MB 짜리 `section2` 에 있다. `section0` 만 읽으면 표지·일러두기·목차만 나온다(스파이크 10장에서 실제로 이 함정에 빠졌다). 파일 이름 순이 아니라 **번호 순**으로 정렬해 이어붙인다 — 문자열 정렬은 `section10` 을 `section2` 앞에 놓는다.

- [ ] **Step 1: 픽스처를 만든다 (이미지 제거)**

원본은 1.4MB 인데 대부분이 BinData 이미지다. 표만 필요하므로 XML 만 남겨 다시 압축한다.

```bash
python - <<'EOF'
import io, re, requests, zipfile
from pathlib import Path
H = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}
URL = "https://www.moel.go.kr/news/enews/report/enewsList.do"
data = {"pageIndex": "1", "bbs_id": "12", "searchField": "1",
        "searchText": "고용행정통계", "pageUnit": "30"}
html = requests.post(URL, data=data, headers={**H, "Referer": URL}, timeout=30).text
seq = re.search(r"news_seq=(\d+)", html).group(1)
view = f"https://www.moel.go.kr/news/enews/report/enewsView.do?news_seq={seq}"
v = requests.get(view, headers=H, timeout=30).text.replace("&amp;", "&")
link = re.search(r'href="(/common/downloadFile\.do\?[^"]*file_ext=hwpx)"', v).group(1)
raw = requests.get("https://www.moel.go.kr" + link,
                   headers={**H, "Referer": view}, timeout=90).content

src = zipfile.ZipFile(io.BytesIO(raw))
out = io.BytesIO()
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
    for n in src.namelist():
        if n.startswith("BinData/"):
            continue          # 표만 필요하다 — 이미지는 픽스처를 무겁게 할 뿐이다
        dst.writestr(n, src.read(n))
p = Path("domains/employment/tests/fixtures/ei_2026-07.hwpx")
p.write_bytes(out.getvalue())
print(f"news_seq={seq}  {len(raw):,} -> {p.stat().st_size:,} bytes")
EOF
```

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`domains/employment/tests/test_hwpx.py`:

```python
import io
import zipfile
from pathlib import Path

import pytest

from domains.employment.pipeline import hwpx

FIXTURE = Path(__file__).parent / "fixtures" / "ei_2026-07.hwpx"


@pytest.fixture(scope="module")
def data():
    return FIXTURE.read_bytes()


def test_reads_many_tables(data):
    tables = hwpx.tables(data)
    assert len(tables) > 50


def test_finds_the_industry_level_table(data):
    tables = hwpx.tables(data)
    hits = [t for t in tables
            if t and len(t[0]) > 5
            and all(k in " ".join(t[0]) for k in ("전산업", "농림어업", "제조업"))]
    assert len(hits) >= 2          # 수준 표와 증감 표
    assert hits[0][-1][1].replace(",", "").isdigit()


def test_reads_every_section_not_just_the_first():
    # section0 만 읽으면 뒤 섹션의 표를 통째로 놓친다. 두 섹션짜리 문서를
    # 만들어 양쪽 표가 모두 나오는지 확인한다.
    def section(text):
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
            ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
            f'<hp:tbl><hp:tr><hp:tc><hp:t>{text}</hp:t></hp:tc></hp:tr></hp:tbl>'
            '</hs:sec>'
        ).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Contents/section0.xml", section("첫째"))
        z.writestr("Contents/section1.xml", section("둘째"))
    tables = hwpx.tables(buf.getvalue())
    assert [t[0][0] for t in tables] == ["첫째", "둘째"]


def test_orders_sections_numerically_not_alphabetically():
    # 문자열 정렬은 section10 을 section2 앞에 놓는다.
    def section(text):
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'
            ' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
            f'<hp:tbl><hp:tr><hp:tc><hp:t>{text}</hp:t></hp:tc></hp:tr></hp:tbl>'
            '</hs:sec>'
        ).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Contents/section10.xml", section("열"))
        z.writestr("Contents/section2.xml", section("둘"))
    assert [t[0][0] for t in hwpx.tables(buf.getvalue())] == ["둘", "열"]
```

- [ ] **Step 3: 실패를 확인한다**

Run: `python -m pytest domains/employment/tests/test_hwpx.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'domains.employment.pipeline.hwpx'`

- [ ] **Step 4: `hwpx.py` 를 구현한다**

```python
"""hwpx 문서의 표를 문자열 격자로 읽는다.

hwpx 는 ZIP + XML 이므로 표준 라이브러리로 충분하다. 표는
<hp:tbl> → <hp:tr> → <hp:tc> 이고 텍스트는 <hp:t> 에 들어 있다.
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET

_SECTION = re.compile(r"^Contents/section(\d+)\.xml$")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _cell_text(el) -> str:
    joined = "".join(n.text or "" for n in el.iter() if _local(n.tag) == "t")
    return re.sub(r"\s+", " ", joined).strip()


def tables(data: bytes) -> list[list[list[str]]]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        # 섹션이 여러 개일 수 있다. 경활 보도자료는 section0~2 이고 본문 표가
        # section2 에 있다 — section0 만 읽으면 표지만 나온다.
        # 번호로 정렬한다. 문자열 정렬은 section10 을 section2 앞에 놓는다.
        sections = sorted(
            (int(m.group(1)), n)
            for n in z.namelist() if (m := _SECTION.match(n))
        )
        payloads = [z.read(n) for _, n in sections]

    out: list[list[list[str]]] = []
    for payload in payloads:
        root = ET.fromstring(payload)
        for tbl in (e for e in root.iter() if _local(e.tag) == "tbl"):
            rows = [
                [_cell_text(tc) for tc in tr if _local(tc.tag) == "tc"]
                for tr in (e for e in tbl.iter() if _local(e.tag) == "tr")
            ]
            out.append(rows)
    return out
```

- [ ] **Step 5: 통과를 확인한다**

Run: `python -m pytest domains/employment/tests/test_hwpx.py -q`
Expected: PASS (4 passed)

- [ ] **Step 6: 커밋**

```bash
git add domains/employment/pipeline/hwpx.py domains/employment/tests/test_hwpx.py domains/employment/tests/fixtures/ei_2026-07.hwpx
git commit -m "feat(employment): hwpx 리더 (전 섹션)"
```

---

### Task 5: 경제활동인구조사 수집기

**Files:**
- Create: `domains/employment/pipeline/collectors/__init__.py`
- Create: `domains/employment/pipeline/collectors/eaps.py`
- Create: `domains/employment/tests/test_eaps.py`

**Interfaces:**
- Consumes: `xlsx.read_sheet`, `xlsx.sheet_names` (Task 3), `models.SeriesRecord`·`make_id` (Task 1)
- Produces:
  - `eaps.INDUSTRY_COLUMNS: dict[str, str]` — 보도자료 열 이름 → KSIC 코드
  - `eaps.parse(data: bytes, *, released_at, release_url, attachments, collected_at) -> list[SeriesRecord]`
  - `eaps.latest_issue() -> tuple[str, date, str, bytes, list[Attachment]]` — (제목, 게시일, 상세URL, xlsx 바이트, 첨부목록). 네트워크를 탄다.
  - `eaps.collect(today: date) -> list[SeriesRecord]`

**열 매핑 (스파이크 실측).** 시트 `3.산업(신)` 의 헤더는 4~6행에 걸친 다단이고, **집계 열 두 개(`광공업`, `사회간접자본 및 기타서비스`)가 섞여 있다.** 이 둘은 대분류가 아니므로 건너뛴다. 광업(B)은 `광공업` 에 묶여 단독으로 없다.

| 시트 | 열 이름 | KSIC |
|---|---|---|
| `3.산업(신)` | 농림어업 | A |
| | 제조업 | C |
| | 전기,가스 | D |
| | 수도,하수,폐기물 | E |
| | 건설업 | F |
| | 도매 및 소매업 | G |
| | 운수 및 창고업 | H |
| | 숙박 및 음식점업 | I |
| `3.산업(신) (2)` | 정보통신업 | J |
| | 금융 및 보험업 | K |
| | 부동산업 | L |
| | 전문,과학 기술 | M |
| | 사업시설 | N |
| | 공공행정 사회보장 | O |
| | 교육 서비스업 | P |
| | 보건업 및 사회복지 | Q |
| | 예술,스포츠 여가관련 | R |
| | 협회및단체 개인서비스 | S |
| | 가구내 고용 | T |
| | 국제및 외국기관 | U |

증감 시트는 `3.산업증감(신)` / `3.산업증감(신) (2)` 로 이름만 다르고 구조가 같다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`domains/employment/tests/test_eaps.py`:

```python
from datetime import date, datetime
from pathlib import Path

import pytest

from domains.employment.pipeline.collectors import eaps

FIXTURE = Path(__file__).parent / "fixtures" / "eaps_2026-07.xlsx"


@pytest.fixture(scope="module")
def records():
    return eaps.parse(
        FIXTURE.read_bytes(),
        released_at=date(2026, 8, 12),
        release_url="https://mods.go.kr/board.es?mid=a10301030100&bid=a103010301&list_no=446465&act=view",
        attachments=[],
        collected_at=datetime(2026, 8, 30, 9, 0),
    )


def test_every_record_is_eaps_in_thousands(records):
    assert records
    assert {r.source for r in records} == {"eaps"}
    assert {r.unit for r in records} == {"천명"}


def test_produces_a_total_for_the_latest_month(records):
    totals = [r for r in records if r.breakdown == "total"]
    assert totals
    newest = max(totals, key=lambda r: r.period)
    # 2026년 취업자는 2,800만명대 — 천명 단위로 28,000 언저리
    assert 26000 < newest.value < 30000


def test_industry_categories_are_ksic_major_codes(records):
    codes = {r.category for r in records if r.breakdown == "industry"}
    assert codes <= set("ACDEFGHIJKLMNOPQRSTU")
    assert {"C", "F", "Q"} <= codes


def test_mining_is_absent_because_the_release_folds_it_into_manufacturing(records):
    # 보도자료는 광업을 '광공업'에 묶어 단독 제공하지 않는다
    assert "B" not in {r.category for r in records if r.breakdown == "industry"}


def test_industry_values_do_not_double_count(records):
    # '광공업'과 '사회간접자본및기타서비스업'은 집계 열이다. 산업으로 새어들면
    # 제조업·서비스업이 이중 계상되어 산업 합이 전체를 넘어선다.
    # 경활은 광업(B)만 빠지므로 정상이면 합이 전체보다 아주 조금 작다.
    latest = max(r.period for r in records)
    total = next(r.value for r in records
                 if r.breakdown == "total" and r.period == latest)
    parts = sum(r.value for r in records
                if r.breakdown == "industry" and r.period == latest)
    assert parts < total, f"산업 합 {parts} 이 전체 {total} 을 넘었다 — 집계 열이 섞였다"
    assert parts > total * 0.99


def test_reads_monthly_rows_not_annual_or_quarterly(records):
    # 연평균·분기 행이 섞이거나 월 시작 행을 놓치면 같은 기간이 중복되고
    # 최신월이 과거로 주저앉는다.
    totals = [r for r in records if r.breakdown == "total"]
    periods = [r.period for r in totals]
    assert len(periods) == len(set(periods)), "같은 기간이 여러 번 나왔다"
    assert len(set(periods)) >= 24
    assert max(periods) >= "2026-01"


def test_carries_year_over_year_change(records):
    industry = [r for r in records if r.breakdown == "industry" and r.yoy is not None]
    assert industry
    assert any(r.yoy < 0 for r in industry)   # 감소한 산업이 있다


def test_ids_are_unique(records):
    ids = [r.id for r in records]
    assert len(ids) == len(set(ids))
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest domains/employment/tests/test_eaps.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'domains.employment.pipeline.collectors'`

- [ ] **Step 3: `eaps.py` 를 구현한다**

```python
"""경제활동인구조사(고용동향) 수집기.

국가데이터처 고용·노동 보도자료 게시판에서 최신 회차의 xlsx 첨부를 받아
'3.산업(신)' 계열 시트를 읽는다. KOSIS API 를 쓰지 않는 이유는 원계열 월별
산업별 취업자 표가 2024년 12월에서 끊겼기 때문이다(스파이크 9장).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

import requests

from .. import xlsx
from ..models import Attachment, SeriesRecord, make_id

KST = timezone(timedelta(hours=9))
BOARD = "https://mods.go.kr/board.es"
BOARD_PARAMS = {"mid": "a10301030100", "bid": "a103010301",
                "ref_bid": "210,211,11109,11113,11814"}
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}

LEVEL_SHEETS = ("3.산업(신)", "3.산업(신) (2)")
DELTA_SHEETS = ("3.산업증감(신)", "3.산업증감(신) (2)")

# 보도자료 열 이름 → 한국표준산업분류 대분류.
# '광공업'과 '사회간접자본 및 기타서비스'는 집계 열이라 일부러 뺐다. 넣으면
# 제조업·서비스업이 이중 계상된다. 광업(B)은 '광공업'에 묶여 단독 제공되지 않는다.
INDUSTRY_COLUMNS: dict[str, str] = {
    "농림어업": "A", "제조업": "C", "전기,가스": "D", "수도,하수폐기물": "E",
    "건설업": "F", "도매및소매업": "G", "운수및창고업": "H", "숙박및음식점업": "I",
    "정보통신업": "J", "금융및보험업": "K", "부동산업": "L", "전문,과학기술": "M",
    "사업시설": "N", "공공행정사회보장": "O", "교육서비스업": "P",
    "보건업및사회복지": "Q", "예술,스포츠여가관련": "R",
    "협회및단체개인서비스": "S", "가구내고용": "T", "국제및외국기관": "U",
}
TOTAL_COLUMN = "전체취업자"


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _header_labels(rows: list[list[str]]) -> dict[int, str]:
    """헤더가 4~6행에 걸쳐 있으므로 열마다 위아래 조각을 이어붙인다."""
    width = max((len(r) for r in rows[:8]), default=0)
    labels: dict[int, str] = {}
    for col in range(width):
        parts = []
        for row in rows[3:7]:
            if col < len(row) and row[col]:
                parts.append(_norm(row[col]))
        if parts:
            labels[col] = "".join(parts)
    return labels


_MONTH_START = re.compile(r"^(\d{4})\.(\d{1,2})$")
_MONTH_ONLY = re.compile(r"^(\d{1,2})$")


def _period_rows(rows: list[list[str]]) -> list[tuple[str, list[str]]]:
    """월 행만 (YYYY-MM, 행) 으로 바꾼다.

    기간 칸에는 세 가지가 섞여 있다(실측):

        '2021'…'2025'          연평균
        '2024.2/4' '3/4' …     분기
        '2021.  7' … '2024.  7' '8' '9' … '2026.  1' '2' … '7'   월

    월은 연도가 바뀔 때만 '2026.  1' 처럼 연도를 달고 그다음부터 숫자만 온다.
    "4자리면 연도, 1~2자리면 그 연도의 월" 로 읽으면 세 가지가 다 어긋난다 —
    월 시작 행을 통째로 건너뛰고, 뒤따르는 숫자가 마지막으로 본 연평균 연도에
    붙어 2026년 데이터가 2025년으로 기록되며, 같은 기간이 중복 생성된다.
    연평균과 분기는 버린다.
    """
    out: list[tuple[str, list[str]]] = []
    year: str | None = None
    for row in rows:
        first = _norm(row[0]) if row else ""
        started = _MONTH_START.match(first)
        if started:
            year, month = started.group(1), int(started.group(2))
        else:
            only = _MONTH_ONLY.match(first)
            if only is None or year is None:
                continue
            month = int(only.group(1))
        if 1 <= month <= 12:
            out.append((f"{year}-{month:02d}", row))
    return out


def _numbers(rows: list[list[str]], labels: dict[int, str]) -> dict[str, dict[str, float]]:
    """{기간: {열이름: 값}}"""
    table: dict[str, dict[str, float]] = {}
    for period, row in _period_rows(rows):
        bucket = table.setdefault(period, {})
        for col, name in labels.items():
            if col >= len(row):
                continue
            raw = (row[col] or "").replace(",", "").strip()
            if not raw:
                continue
            try:
                bucket[name] = round(float(raw), 1)
            except ValueError:
                continue
    return table


def _collect_sheets(data: bytes, names) -> dict[str, dict[str, float]]:
    merged: dict[str, dict[str, float]] = {}
    for name in names:
        rows = xlsx.read_sheet(data, name)
        for period, values in _numbers(rows, _header_labels(rows)).items():
            merged.setdefault(period, {}).update(values)
    return merged


def parse(data: bytes, *, released_at: date, release_url: str,
          attachments: list[Attachment], collected_at: datetime) -> list[SeriesRecord]:
    levels = _collect_sheets(data, LEVEL_SHEETS)
    deltas = _collect_sheets(data, DELTA_SHEETS)

    records: list[SeriesRecord] = []
    for period, values in levels.items():
        delta = deltas.get(period, {})

        if TOTAL_COLUMN in values:
            records.append(SeriesRecord(
                id=make_id("eaps", period, "total", None), source="eaps",
                breakdown="total", category=None, period=period,
                value=values[TOTAL_COLUMN], yoy=delta.get(TOTAL_COLUMN),
                released_at=released_at, release_url=release_url,
                attachments=attachments, collected_at=collected_at,
            ))

        for column, code in INDUSTRY_COLUMNS.items():
            if column not in values:
                continue
            records.append(SeriesRecord(
                id=make_id("eaps", period, "industry", code), source="eaps",
                breakdown="industry", category=code, period=period,
                value=values[column], yoy=delta.get(column),
                released_at=released_at, release_url=release_url,
                attachments=attachments, collected_at=collected_at,
            ))
    return records


def latest_issue() -> tuple[str, date, str, bytes, list[Attachment]]:
    html = requests.get(BOARD, params=BOARD_PARAMS, headers=HEADERS,
                        timeout=30).text.replace("&amp;", "&")
    m = re.search(
        r'href="(/boardDownload\.es\?[^"]*?list_no=(\d+)[^"]*)"\s+class="bf_xlsx">'
        r'<span class="hdn">([^<]*?고용동향)의 xlsx파일', html)
    if m is None:
        raise ValueError("게시판에서 고용동향 xlsx 첨부를 찾지 못했다")
    href, list_no, title = m.group(1), m.group(2), m.group(3)

    posted = re.search(
        rf"list_no={list_no}.{{0,4000}}?<strong>게시일</strong><span>(\d{{4}}-\d{{2}}-\d{{2}})</span>",
        html, re.S)
    if posted is None:
        raise ValueError(f"게시일을 찾지 못했다: {title}")
    released_at = date.fromisoformat(posted.group(1))

    view_url = (f"https://mods.go.kr/board.es?mid=a10301030100&bid=a103010301"
                f"&list_no={list_no}&act=view")
    data = requests.get("https://mods.go.kr" + href,
                        headers={**HEADERS, "Referer": BOARD}, timeout=90).content
    attachments = [Attachment(type="xlsx", url="https://mods.go.kr" + href)]
    return title, released_at, view_url, data, attachments


def collect(today: date) -> list[SeriesRecord]:
    title, released_at, view_url, data, attachments = latest_issue()
    return parse(data, released_at=released_at, release_url=view_url,
                 attachments=attachments, collected_at=datetime.now(KST))
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python -m pytest domains/employment/tests/test_eaps.py -q`
Expected: PASS (7 passed)

열 이름 정규화(`_norm` 이 공백을 지운다) 때문에 `INDUSTRY_COLUMNS` 의 키도 공백이 없다. 테스트가 특정 산업을 못 찾으면 아래로 실제 헤더를 찍어 키를 맞춘다:

```bash
python -c "
from pathlib import Path
from domains.employment.pipeline import xlsx
from domains.employment.pipeline.collectors.eaps import _header_labels
d=Path('domains/employment/tests/fixtures/eaps_2026-07.xlsx').read_bytes()
for s in ['3.산업(신)','3.산업(신) (2)']:
    print(s, _header_labels(xlsx.read_sheet(d,s)))
"
```

- [ ] **Step 5: 실제 수집을 한 번 돌려 본다 (네트워크)**

Run: `python -c "from datetime import date; from domains.employment.pipeline.collectors import eaps; rs=eaps.collect(date.today()); print(len(rs), max(r.period for r in rs))"`
Expected: 레코드 수백 개와 최신 기간이 출력된다. 실패하면 게시판 마크업이 바뀐 것이므로 보고한다.

- [ ] **Step 6: 커밋**

```bash
git add domains/employment/pipeline/collectors/ domains/employment/tests/test_eaps.py
git commit -m "feat(employment): 경제활동인구조사 수집기 (보도자료 xlsx)"
```

---

### Task 6: 사업체노동력조사 수집기

**Files:**
- Create: `domains/employment/pipeline/collectors/est.py`
- Create: `domains/employment/tests/test_est.py`
- Create: `domains/employment/tests/fixtures/est_kosis.json` (KOSIS 응답을 저장)

**Interfaces:**
- Consumes: `models.SeriesRecord`·`make_id` (Task 1)
- Produces:
  - `est.MAJOR_CODE_RE` — 대분류 판별 정규식
  - `est.parse(rows: list[dict], *, released_at, release_url, collected_at) -> list[SeriesRecord]`
  - `est.EXPECTED_CODES: set[str]`, `est.check_coverage(records) -> None` — 최신월에 기대한 대분류가 다 왔는지 검증, 아니면 `ValueError`
  - `est.fetch(api_key: str, months: int = 24) -> list[dict]` — 네트워크
  - `est.collect(today: date) -> list[SeriesRecord]`

**대분류 판별은 이름이 아니라 코드로 한다 (스파이크 실측).** `C1_NM` 은 `B.광업(05~08)` 처럼 코드범위가 붙기도 하고 `D.전기 가스…(35)` 처럼 단일이기도 해서 이름 규칙이 흔들린다. `C1` 코드는 일정하다:

```
260225INDUSTRY_11SD     ← 대분류 (끝이 알파벳 한 글자)
260225INDUSTRY_11SD35   ← 중분류 (뒤에 숫자)
```

이 규칙으로 18개 대분류(A·T·U 제외)가 정확히 잡힌다.

**단위 변환.** KOSIS 는 `명` 으로 준다. 1000 으로 나눠 소수 첫째자리로 반올림해 `천명` 으로 맞춘다.

**증감.** 이 표에는 전년동월대비 증감 항목이 없다. 12개월 전 같은 키의 수준에서 직접 계산한다. 12개월 전 값이 없으면 `yoy=None` 으로 둔다.

- [ ] **Step 1: 픽스처를 내려받는다**

```bash
python - <<'EOF'
import json, requests
from pathlib import Path
key = dict(l.split("=", 1) for l in
           Path(".env").read_text(encoding="utf-8").strip().splitlines())["KOSIS_API_KEY"]
p = {"method": "getList", "apiKey": key, "orgId": "118", "tblId": "DT_118N_MON066",
     "itmId": "ALL", "objL1": "ALL", "objL2": "ALL", "prdSe": "M",
     "newEstPrdCnt": "36", "format": "json", "jsonVD": "Y"}
rows = requests.get("https://kosis.kr/openapi/Param/statisticsParameterData.do",
                    params=p, timeout=120).json()
keep = [r for r in rows if r.get("C2_NM") == "전체" and r.get("ITM_NM") == "종사자_전체"]
out = Path("domains/employment/tests/fixtures/est_kosis.json")
out.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(rows), "->", len(keep), "행", out.stat().st_size, "bytes")
EOF
```

`newEstPrdCnt=36` 이다. 증감은 12개월 전 값에서 계산하므로 26개월만 받으면 증감이 붙는 달이 14개뿐이라 24개월 시계열을 못 그린다. 36개월이면 24개월치 증감이 나온다.
저장 시 규모(`C2_NM`)와 항목(`ITM_NM`)을 좁히지 않으면 픽스처가 수십 MB 가 된다.

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`domains/employment/tests/test_est.py`:

```python
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from domains.employment.pipeline.collectors import est

FIXTURE = Path(__file__).parent / "fixtures" / "est_kosis.json"


@pytest.fixture(scope="module")
def records():
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return est.parse(
        rows,
        released_at=date(2026, 7, 29),
        release_url="https://kosis.kr/statHtml/statHtml.do?orgId=118&tblId=DT_118N_MON066",
        collected_at=datetime(2026, 8, 30, 9, 0),
    )


def test_major_code_regex_separates_divisions_from_subclasses():
    assert est.MAJOR_CODE_RE.search("260225INDUSTRY_11SD")
    assert not est.MAJOR_CODE_RE.search("260225INDUSTRY_11SD35")


def test_values_are_converted_to_thousands(records):
    totals = [r for r in records if r.breakdown == "total"]
    assert totals
    newest = max(totals, key=lambda r: r.period)
    # 종사자 2,070만명 -> 20,700 천명 언저리
    assert 19000 < newest.value < 22000
    assert newest.unit == "천명"


def test_industry_codes_match_what_the_survey_covers(records):
    codes = {r.category for r in records if r.breakdown == "industry"}
    assert codes == set("BCDEFGHIJKLMNOPQRS")
    # 사업체 조사라 농림어업·가구내고용·국제기관은 없다
    assert not ({"A", "T", "U"} & codes)


def test_subclasses_are_excluded(records):
    # 중분류가 섞이면 대분류가 이중 계상된다
    for r in records:
        assert r.category is None or len(r.category) == 1


def test_year_over_year_is_computed_from_twelve_months_earlier(records):
    manufacturing = sorted(
        (r for r in records if r.breakdown == "industry" and r.category == "C"),
        key=lambda r: r.period)
    assert len(manufacturing) >= 13
    by_period = {r.period: r for r in manufacturing}
    newest = manufacturing[-1]
    year, month = newest.period.split("-")
    prior = by_period.get(f"{int(year) - 1}-{month}")
    assert prior is not None
    assert newest.yoy == pytest.approx(round(newest.value - prior.value, 1))


def test_oldest_records_have_no_year_over_year(records):
    oldest = min(r.period for r in records)
    assert all(r.yoy is None for r in records if r.period == oldest)


def test_coverage_check_passes_on_a_complete_month(records):
    est.check_coverage(records)          # 예외가 나면 실패


def test_coverage_check_fails_loudly_when_an_industry_vanishes(records):
    # 코드 체계가 바뀌어 산업이 조용히 빠지면 화면에서 빈 칸으로만 보인다.
    latest = max(r.period for r in records)
    thinned = [r for r in records
               if not (r.period == latest and r.category == "C")]
    with pytest.raises(ValueError, match="빠진 산업"):
        est.check_coverage(thinned)
```

- [ ] **Step 3: 실패를 확인한다**

Run: `python -m pytest domains/employment/tests/test_est.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'domains.employment.pipeline.collectors.est'`

- [ ] **Step 4: `est.py` 를 구현한다**

```python
"""사업체노동력조사 수집기 (KOSIS OpenAPI).

세 출처 중 유일하게 API 로 얻는다. 표는 대분류와 중분류가 한 축에 섞여
90여 항목으로 나오므로 코드로 대분류만 걸러낸다.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta, timezone

import requests

from ..models import SeriesRecord, make_id

KST = timezone(timedelta(hours=9))
API = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
ORG_ID = "118"
TBL_ID = "DT_118N_MON066"
STAT_URL = f"https://kosis.kr/statHtml/statHtml.do?orgId={ORG_ID}&tblId={TBL_ID}"

# 대분류는 코드가 알파벳으로 끝나고(...11SD), 중분류는 뒤에 숫자가 붙는다(...11SD35).
# 이름(C1_NM)은 코드범위 표기가 흔들려 판별 기준으로 못 쓴다.
MAJOR_CODE_RE = re.compile(r"INDUSTRY_\w*?S([A-Z])$")

TOTAL_NAME = "전체"


def _period(prd_de: str) -> str:
    return f"{prd_de[:4]}-{prd_de[4:6]}"


def _thousands(raw: str) -> float:
    return round(float(str(raw).replace(",", "")) / 1000, 1)


def parse(rows: list[dict], *, released_at: date, release_url: str,
          collected_at: datetime) -> list[SeriesRecord]:
    # (breakdown, category) -> {period: value}
    levels: dict[tuple[str, str | None], dict[str, float]] = {}
    for row in rows:
        if row.get("C2_NM") != TOTAL_NAME or row.get("ITM_NM") != "종사자_전체":
            continue
        name = str(row.get("C1_NM", "")).strip()
        code = str(row.get("C1", ""))
        period = _period(str(row.get("PRD_DE", "")))
        try:
            value = _thousands(row.get("DT"))
        except (TypeError, ValueError):
            continue

        if name == TOTAL_NAME:
            key = ("total", None)
        else:
            m = MAJOR_CODE_RE.search(code)
            if m is None:
                continue          # 중분류는 버린다 — 넣으면 대분류가 이중 계상된다
            key = ("industry", m.group(1))
        levels.setdefault(key, {})[period] = value

    records: list[SeriesRecord] = []
    for (breakdown, category), series in levels.items():
        for period, value in series.items():
            year, month = period.split("-")
            prior = series.get(f"{int(year) - 1}-{month}")
            records.append(SeriesRecord(
                id=make_id("est", period, breakdown, category), source="est",
                breakdown=breakdown, category=category, period=period,
                value=value,
                yoy=None if prior is None else round(value - prior, 1),
                released_at=released_at, release_url=release_url,
                attachments=[], collected_at=collected_at,
            ))
    return records


def fetch(api_key: str, months: int = 36) -> list[dict]:
    params = {"method": "getList", "apiKey": api_key, "orgId": ORG_ID,
              "tblId": TBL_ID, "itmId": "ALL", "objL1": "ALL", "objL2": "ALL",
              "prdSe": "M", "newEstPrdCnt": str(months),
              "format": "json", "jsonVD": "Y"}
    payload = requests.get(API, params=params, timeout=120).json()
    if isinstance(payload, dict):
        raise ValueError(f"KOSIS 오류: {payload.get('errMsg', payload)}")
    return payload


EXPECTED_CODES = set("BCDEFGHIJKLMNOPQRS")


def check_coverage(records: list[SeriesRecord]) -> None:
    """최신월에 기대한 대분류가 다 왔는지 본다.

    KOSIS 의 분류 코드 체계가 바뀌면 MAJOR_CODE_RE 가 산업을 조용히 흘린다.
    빠진 산업은 화면에서 그냥 없는 칸으로 보일 뿐 아무 오류도 남기지 않는다.
    """
    if not records:
        raise ValueError("수집된 레코드가 없다")
    latest = max(r.period for r in records)
    got = {r.category for r in records
           if r.period == latest and r.breakdown == "industry"}
    missing = EXPECTED_CODES - got
    if missing:
        raise ValueError(f"{latest} 에 빠진 산업 대분류: {sorted(missing)}")


def collect(today: date) -> list[SeriesRecord]:
    api_key = os.environ.get("KOSIS_API_KEY", "").strip()
    if not api_key:
        raise ValueError("KOSIS_API_KEY 가 없다")
    rows = fetch(api_key)
    latest = max(_period(str(r.get("PRD_DE", ""))) for r in rows)
    year, month = (int(x) for x in latest.split("-"))
    # 표에 발표일이 없다. 해당 월 다음다음 달 말에 공표되므로 근사치를 쓴다.
    released = date(year + (month + 1) // 12, (month + 1) % 12 + 1, 1) - timedelta(days=1)
    records = parse(rows, released_at=released, release_url=STAT_URL,
                    collected_at=datetime.now(KST))
    check_coverage(records)
    return records
```

- [ ] **Step 5: 통과를 확인한다**

Run: `python -m pytest domains/employment/tests/test_est.py -q`
Expected: PASS (6 passed)

- [ ] **Step 6: 커밋**

```bash
git add domains/employment/pipeline/collectors/est.py domains/employment/tests/test_est.py domains/employment/tests/fixtures/est_kosis.json
git commit -m "feat(employment): 사업체노동력조사 수집기 (KOSIS API)"
```

---

### Task 7: 고용행정통계 수집기

**Files:**
- Create: `domains/employment/pipeline/periods.py` — 기간 칸 파싱 공유 모듈
- Create: `domains/employment/pipeline/collectors/ei.py`
- Create: `domains/employment/tests/test_ei.py`
- Create: `domains/employment/tests/test_periods.py`
- Modify: `domains/employment/pipeline/collectors/eaps.py` — 자체 `_period_rows`·`_norm` 을 지우고 공유 모듈을 쓴다

**왜 공유 모듈인가.** 경활 xlsx 와 고용행정 hwpx 가 기간 칸에 **같은 관례**를 쓴다 — 연평균·분기·월이 한 열에 섞이고, 월은 연도가 바뀔 때만 연도를 단다(`2026. 1` 다음은 `2`, `3` …). Task 5 가 이 규칙을 어렵게 알아냈다(처음엔 2026년 데이터를 2025년으로 기록했다). 두 번째 수집기에 복사하면 한쪽만 고쳐지는 날이 온다.

`periods.py` 의 내용은 Task 5 가 이미 검증한 `eaps._period_rows` 를 그대로 옮긴 것이다. 옮긴 뒤 `eaps.py` 가 공유 모듈을 쓰도록 바꾸고, **Task 5 의 테스트 10개가 전부 그대로 통과해야 한다.**

**Interfaces:**
- Consumes: `hwpx.tables` (Task 4), `models.SeriesRecord`·`make_id` (Task 1)
- Produces:
  - `ei.LEAD_COLUMNS: dict[int, str]`, `ei.CONT_COLUMNS: dict[int, str]` — 열 위치 → KSIC 코드
  - `ei.check_layout(lead, cont) -> None` — 헤더 이름이 기대 위치에 있는지 검증, 아니면 `ValueError`
  - `periods.squash(text) -> str`, `periods.month_rows(rows, column=0) -> list[tuple[str, list[str]]]` — 기간 칸 파싱 공유 모듈
  - `ei.find_tables(tables) -> tuple[list, list, list, list]` — (수준, 수준이어짐, 증감, 증감이어짐)
  - `ei.TOTAL_KEY`, `ei._series_by_period(lead, cont) -> dict[str, dict[str, float]]`
  - `ei.EXPECTED_CODES: set[str]`, `ei.check_coverage(records) -> None`
  - `ei.headline_delta(tables) -> float | None` — p1 요약문에서 총량 증감(천명)을 뽑는다
  - `ei.parse(data: bytes, *, released_at, release_url, attachments, collected_at) -> list[SeriesRecord]`
  - `ei.latest_issue() -> tuple[str, date, str, bytes, list[Attachment]]`
  - `ei.collect(today: date) -> list[SeriesRecord]`

**표를 인덱스로 찾지 마라 (스파이크 5장).** 회차마다 표 개수가 달라 인덱스가 밀린다(2026-05 는 107개, 06·07 은 108개). 헤더에 `전산업`·`농림어업`·`제조업` 이 모두 있는 표를 찾는다. 2026-07 기준 후보는 8개(64, 66, 84, 86, 88, 90, 95, 97)인데 뒤쪽은 구직급여·구인구직 표다. **첫 둘이 상시가입자 수준·증감**이고, 크기 검증이 순서 뒤바뀜을 잡는다(수준의 전산업 ≥ 10,000, 증감의 전산업 절댓값 < 1,000).

**헤더를 이름으로 재구성하지 마라 — 열 위치를 쓴다.** 이 표는 헤더가 0행과 1행에 나뉘어 있고, 병합셀 때문에 1행에는 0행의 빈 자리를 채우는 셀만 들어 있다(0행이 `['', '전산업', '농림어업', '제조업', '전기·가스', '건설업', '서비스업', '', '', '', '']`, 1행이 `['수도·하수·폐기업', '도소매', '운수창고', '숙박음식']`). 이름으로 짜맞추는 것보다 **고정 인덱스로 읽고 헤더 이름을 검증**하는 편이 단순하고, 서식이 바뀌면 조용히 틀리는 대신 즉시 실패한다.

**헤더 비교는 공백을 지우고 한다.** hwpx 리더(Task 4)가 셀 안 문단을 공백으로 이어붙이므로, 두 줄로 접힌 헤더가 `농림 어업`·`정보 통신업`·`전기· 가스` 처럼 나온다. 실측으로 확인했다 — 공백을 그대로 두고 `농림어업` 을 찾으면 **상시가입자 표(64·66)가 후보에서 빠지고 뒤쪽 구직급여 표가 첫 후보가 된다.** 크기 검증이 막아줄 수도 있지만 기대지 마라.

**집계 열 두 개를 반드시 뺀다.** 앞 표의 `서비스업`(6번 열)과 이어지는 표의 `기타*`(11번 열)는 대분류가 아니라 집계다. 넣으면 서비스 산업들이 이중 계상된다. 경활의 `광공업`과 같은 함정이다.

**대조 검증 (스파이크 6장).** p1 `<주요 특징>` 박스에 총량 증감이 문장으로 나온다("‘26.7월 고용보험 가입자는 27만 7천명 증가"). 증감 표의 전산업 값과 일치해야 한다. 어긋나면 서식이 바뀐 것이므로 **조용히 잘못된 숫자를 넣지 말고 실패시킨다.**

- [ ] **Step 0: 기간 파싱을 공유 모듈로 옮긴다**

Task 5 가 알아낸 기간 칸 규칙을 두 수집기가 함께 쓴다. 먼저 테스트를 쓴다.

`domains/employment/tests/test_periods.py`:

```python
from domains.employment.pipeline.periods import month_rows, squash


def test_squash_removes_every_space():
    assert squash(" 농림 어업 ") == "농림어업"
    assert squash(None) == ""


def test_reads_a_month_start_row_and_the_bare_months_after_it():
    rows = [["2024.  7", "a"], ["8", "b"], ["9", "c"]]
    assert [p for p, _ in month_rows(rows)] == ["2024-07", "2024-08", "2024-09"]


def test_a_new_year_row_switches_the_year():
    rows = [["2025.  12", "a"], ["2026.  1", "b"], ["2", "c"]]
    assert [p for p, _ in month_rows(rows)] == ["2025-12", "2026-01", "2026-02"]


def test_annual_and_quarterly_rows_are_dropped():
    rows = [["2021", "a"], ["2025", "b"], ["2026.1/4", "c"], ["2/4", "d"]]
    assert month_rows(rows) == []


def test_a_blank_row_ends_the_year_context():
    # 표의 블록 경계다. 이어지면 연평균 블록 뒤의 숫자가 엉뚱한 해에 붙는다.
    rows = [["2024.  7", "a"], ["", ""], ["8", "b"]]
    assert [p for p, _ in month_rows(rows)] == ["2024-07"]


def test_a_bare_month_before_any_year_is_ignored():
    assert month_rows([["8", "a"]]) == []
```

Run: `python -m pytest domains/employment/tests/test_periods.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'domains.employment.pipeline.periods'`

그다음 `domains/employment/pipeline/periods.py` 를 만든다. 내용은 Task 5 가 이미 검증한 `eaps._period_rows` 를 그대로 옮긴 것이다 — 로직을 새로 쓰지 말고 **현재 `eaps.py` 의 것을 읽어 옮겨라**:

```python
"""보도자료 표의 기간 칸을 읽는다.

경활 xlsx 와 고용행정 hwpx 가 같은 관례를 쓴다 — 연평균·분기·월이 한 열에 섞이고,
월은 연도가 바뀔 때만 연도를 단다. 두 수집기에 복사하면 한쪽만 고쳐지는 날이 온다.
"""
from __future__ import annotations

import re

_MONTH_START = re.compile(r"^(\d{4})\.(\d{1,2})$")
_MONTH_ONLY = re.compile(r"^(\d{1,2})$")


def squash(text: str | None) -> str:
    """공백을 모두 지운다. 두 줄로 접힌 셀을 한 낱말로 되돌린다."""
    return re.sub(r"\s+", "", text or "")


def month_rows(rows: list[list[str]], *,
               column: int = 0) -> list[tuple[str, list[str]]]:
    """월 행만 (YYYY-MM, 행) 으로. 연평균·분기·주석은 버린다."""
    out: list[tuple[str, list[str]]] = []
    year: str | None = None
    for row in rows:
        first = squash(row[column]) if len(row) > column else ""
        if not first:
            year = None            # 빈 행은 표의 블록 경계다
            continue
        started = _MONTH_START.fullmatch(first)
        if started:
            year, month = started.group(1), int(started.group(2))
            if 1 <= month <= 12:
                out.append((f"{year}-{month:02d}", row))
            continue
        only = _MONTH_ONLY.fullmatch(first)
        if year and only:
            month = int(only.group(1))
            if 1 <= month <= 12:
                out.append((f"{year}-{month:02d}", row))
    return out
```

Run: `python -m pytest domains/employment/tests/test_periods.py -q`
Expected: PASS (6 passed)

이제 `eaps.py` 가 공유 모듈을 쓰게 한다 — `_MONTH_START`·`_MONTH_ONLY`·`_period_rows`·`_norm` 을 지우고 `from ..periods import month_rows, squash` 로 바꾼다. `_norm` 을 쓰던 자리는 `squash` 로 바꾼다.

Run: `python -m pytest domains/employment/tests/test_eaps.py -q`
Expected: PASS (10 passed) — **Task 5 의 테스트가 하나도 바뀌지 않고 그대로 통과해야 한다.** 하나라도 깨지면 옮기는 과정에서 동작이 달라진 것이므로 멈추고 보고하라.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`domains/employment/tests/test_ei.py`:

```python
from datetime import date, datetime
from pathlib import Path

import pytest

from domains.employment.pipeline import hwpx
from domains.employment.pipeline.collectors import ei

FIXTURE = Path(__file__).parent / "fixtures" / "ei_2026-07.hwpx"


@pytest.fixture(scope="module")
def data():
    return FIXTURE.read_bytes()


@pytest.fixture(scope="module")
def records(data):
    return ei.parse(
        data,
        released_at=date(2026, 8, 11),
        release_url="https://www.moel.go.kr/news/enews/report/enewsView.do?news_seq=19759",
        attachments=[],
        collected_at=datetime(2026, 8, 30, 9, 0),
    )


def test_finds_the_four_tables_by_content_not_position(data):
    level, level2, delta, delta2 = ei.find_tables(hwpx.tables(data))
    for t in (level, level2, delta, delta2):
        assert len(t) > 30
    # 수준은 크고 증감은 작다 — 순서가 뒤집히면 여기서 잡힌다
    assert float(level[-1][1].replace(",", "")) > 10000
    assert abs(float(delta[-1][1].replace(",", ""))) < 1000


def test_headline_delta_is_read_from_the_summary_box(data):
    # 픽스처가 다음 회차로 바뀌어도 깨지지 않도록 고정값 대신 자릿수로 본다.
    # 상시가입자 증감은 월 수십만명 규모라 천명 단위로 세 자리다.
    stated = ei.headline_delta(hwpx.tables(data))
    assert stated is not None
    assert 50 < abs(stated) < 900


def test_total_matches_the_summary_box(data, records):
    # 문서가 스스로 검증 대조점을 갖고 있다: 요약문의 증감 = 증감표의 전산업.
    stated = ei.headline_delta(hwpx.tables(data))
    totals = [r for r in records if r.breakdown == "total"]
    newest = max(totals, key=lambda r: r.period)
    assert newest.yoy == pytest.approx(stated, abs=1.0)
    assert 15000 < newest.value < 17000


def test_industry_codes_match_what_the_release_covers(records):
    codes = {r.category for r in records if r.breakdown == "industry"}
    assert codes == set("ACDEFGHIJKLMNOPQRS")
    # 광업·가구내고용·국제기관은 '기타'로 묶여 단독 제공되지 않는다
    assert not ({"B", "T", "U"} & codes)


def test_aggregate_columns_are_excluded(data):
    # '서비스업'과 '기타*'는 집계 열이다. 대분류로 넣으면 이중 계상된다.
    level, cont, _, _ = ei.find_tables(hwpx.tables(data))
    assert level[0][6] == "서비스업"          # 앞 표 6번 열은 집계
    assert 6 not in ei.LEAD_COLUMNS
    assert cont[1][11] == "기타*"             # 이어지는 표 11번 열은 집계
    assert 11 not in ei.CONT_COLUMNS


def test_layout_check_rejects_a_changed_header(data):
    level, cont, _, _ = ei.find_tables(hwpx.tables(data))
    broken = [list(r) for r in level]
    broken[0][2] = "뭔가다른것"
    with pytest.raises(ValueError, match="열 배치"):
        ei.check_layout(broken, cont)


def test_every_record_is_ei_in_thousands(records):
    assert {r.source for r in records} == {"ei"}
    assert {r.unit for r in records} == {"천명"}


def test_ids_are_unique(records):
    ids = [r.id for r in records]
    assert len(ids) == len(set(ids))


def test_reads_every_month_in_the_table_not_just_the_latest(records):
    # 표는 28개월치를 담고 있다. 마지막 행만 읽으면 24개월 시계열을 모으는 데
    # 2년이 걸린다.
    totals = [r for r in records if r.breakdown == "total"]
    periods = [r.period for r in totals]
    assert len(periods) == len(set(periods)), "같은 기간이 여러 번 나왔다"
    assert len(periods) >= 24
    assert max(periods) >= "2026-01"


def test_industry_sum_tracks_the_total(records):
    # 열이 밀리거나 집계 열('서비스업', '기타*')이 섞이면 합이 전체에서 벗어난다.
    latest = max(r.period for r in records)
    total = next(r.value for r in records
                 if r.breakdown == "total" and r.period == latest)
    parts = sum(r.value for r in records
                if r.breakdown == "industry" and r.period == latest)
    # 광업·가구내고용·국제기관이 '기타'로 빠지므로 합이 전체보다 조금 작다
    assert 0.97 < parts / total < 1.0


def test_coverage_check_passes_on_a_complete_month(records):
    ei.check_coverage(records)


def test_coverage_check_fails_loudly_when_an_industry_vanishes(records):
    latest = max(r.period for r in records)
    thinned = [r for r in records
               if not (r.period == latest and r.category == "C")]
    with pytest.raises(ValueError, match="빠진 산업"):
        ei.check_coverage(thinned)


def test_parse_fails_loudly_when_the_summary_disagrees(data, monkeypatch):
    # 서식이 바뀌어 표를 잘못 읽으면 조용히 틀린 숫자를 넣지 말고 실패해야 한다
    monkeypatch.setattr(ei, "headline_delta", lambda tables: 999.0)
    with pytest.raises(ValueError, match="대조"):
        ei.parse(data, released_at=date(2026, 8, 11),
                 release_url="https://x/view", attachments=[],
                 collected_at=datetime(2026, 8, 30, 9, 0))
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest domains/employment/tests/test_ei.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'domains.employment.pipeline.collectors.ei'`

- [ ] **Step 3: `ei.py` 를 구현한다**

```python
"""고용행정 통계로 본 노동시장 동향 수집기.

고용노동부 보도자료 게시판에서 최신 회차의 hwpx 첨부를 받아 상시가입자
수준·증감 표를 읽는다. 표는 인덱스가 아니라 헤더 내용으로 찾는다 —
회차마다 표 개수가 달라 인덱스가 밀린다.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

import requests

from .. import hwpx
from ..models import Attachment, SeriesRecord, make_id
from ..periods import month_rows, squash

KST = timezone(timedelta(hours=9))
LIST_URL = "https://www.moel.go.kr/news/enews/report/enewsList.do"
VIEW_URL = "https://www.moel.go.kr/news/enews/report/enewsView.do"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}
SEARCH = {"pageIndex": "1", "bbs_id": "12", "searchField": "1",
          "searchText": "고용행정통계", "pageUnit": "30"}

HEADER_KEYS = ("전산업", "농림어업", "제조업")

# 열 위치 → 한국표준산업분류 대분류.
# 헤더가 0행·1행에 나뉘고 병합셀이 섞여 이름으로 짜맞추기 어렵다. 위치로 읽고
# check_layout 이 이름을 검증한다 — 서식이 바뀌면 조용히 틀리는 대신 실패한다.
#
# 앞 표(11열): 0=월 1=전산업 2=농림어업 3=제조업 4=전기·가스 5=건설업
#              6=서비스업(집계) 7=수도·하수·폐기업 8=도소매 9=운수창고 10=숙박음식
LEAD_COLUMNS: dict[int, str] = {
    2: "A", 3: "C", 4: "D", 5: "F", 7: "E", 8: "G", 9: "H", 10: "I",
}
# 이어지는 표(12열): 0=월 1=정보통신업 … 10=협회·개인서비스 11=기타*(집계)
CONT_COLUMNS: dict[int, str] = {
    1: "J", 2: "K", 3: "L", 4: "M", 5: "N", 6: "O", 7: "P", 8: "Q", 9: "R", 10: "S",
}
TOTAL_COLUMN = 1

# 6(서비스업)과 11(기타*)은 일부러 뺐다. 집계 열이라 넣으면 이중 계상된다.

_LEAD_HEADER = {1: "전산업", 2: "농림어업", 3: "제조업", 6: "서비스업"}
_CONT_HEADER = {1: "정보통신업", 8: "보건복지", 11: "기타*"}


def check_layout(lead: list[list[str]], cont: list[list[str]]) -> None:
    # 비교 전에 공백을 지운다 — 헤더가 두 줄로 접히면 '정보 통신업' 처럼 온다.
    for col, expected in _LEAD_HEADER.items():
        got = lead[0][col] if col < len(lead[0]) else ""
        if squash(got) != expected:
            raise ValueError(f"앞 표의 열 배치가 바뀌었다: {col}번은 {expected!r} 여야 하는데 {got!r}")
    header = cont[1] if len(cont) > 1 else []
    for col, expected in _CONT_HEADER.items():
        got = header[col] if col < len(header) else ""
        if squash(got) != expected:
            raise ValueError(f"이어지는 표의 열 배치가 바뀌었다: {col}번은 {expected!r} 여야 하는데 {got!r}")


def _num(cell: str) -> float | None:
    raw = (cell or "").replace(",", "").strip()
    if not re.fullmatch(r"-?\d+(\.\d+)?", raw):
        return None
    return float(raw)


def _flat(cells) -> str:
    """헤더 비교용. 공백을 지운다.

    hwpx 리더가 셀 안 문단을 공백으로 잇기 때문에 두 줄로 접힌 헤더가
    '농림 어업', '정보 통신업' 처럼 나온다. 공백을 그대로 두고 매칭하면
    상시가입자 표를 놓치고 뒤쪽 구직급여 표를 집는다.

    셀 안 공백만 지우고 셀 사이는 띄운다. 전부 이어붙이면 키워드가 두 셀
    경계를 걸쳐 가짜로 매칭될 수 있다 — 앞 셀 끝 '산' + 뒤 셀 시작 '업'.
    """
    return " ".join(squash(c) for c in cells)


def find_tables(tables) -> tuple[list, list, list, list]:
    cand = [
        i for i, g in enumerate(tables)
        if g and len(g[0]) > 5 and all(k in _flat(g[0]) for k in HEADER_KEYS)
    ]
    if len(cand) < 2:
        raise ValueError(f"수준·증감 표를 찾지 못했다 (후보 {cand})")
    level_i, delta_i = cand[0], cand[1]

    level, delta = tables[level_i], tables[delta_i]
    lv, dv = _num(level[-1][1]), _num(delta[-1][1])
    # 헤더가 같아 순서로만 구분된다. 크기로 뒤바뀜을 잡는다.
    if lv is None or lv < 10000:
        raise ValueError(f"수준 표의 전산업이 이상하다: {lv}")
    if dv is None or abs(dv) >= 1000:
        raise ValueError(f"증감 표의 전산업이 이상하다: {dv}")

    return level, tables[level_i + 1], delta, tables[delta_i + 1]


def headline_delta(tables) -> float | None:
    """p1 <주요 특징> 박스의 '27만 7천명 증가' 를 천명 단위 부호값으로."""
    for g in tables:
        text = " ".join(" ".join(r) for r in g)
        if "주요 특징" not in text and "고용보험" not in text:
            continue
        m = re.search(r"고용보험\s*가입자는\s*([\d,]+)\s*만\s*([\d,]+)?\s*천?명\s*(증가|감소)", text)
        if m is None:
            m2 = re.search(r"고용보험\s*가입자는\s*([\d,]+)\s*천명\s*(증가|감소)", text)
            if m2 is None:
                continue
            value = float(m2.group(1).replace(",", ""))
            return value if m2.group(2) == "증가" else -value
        man = float(m.group(1).replace(",", ""))
        cheon = float((m.group(2) or "0").replace(",", ""))
        value = man * 10 + cheon
        return value if m.group(3) == "증가" else -value
    return None


TOTAL_KEY = "__total__"


def _series_by_period(lead, cont) -> dict[str, dict[str, float]]:
    """{기간: {KSIC 코드 또는 TOTAL_KEY: 값}}.

    마지막 행만 읽지 않는다. 이 표는 28개월치를 담고 있고, 한 회차에서 전 기간을
    가져와야 24개월 시계열이 첫 수집만으로 채워진다. 최신월만 읽으면 24개월을
    모으는 데 2년이 걸린다.
    """
    out: dict[str, dict[str, float]] = {}

    for period, row in month_rows(lead):
        bucket = out.setdefault(period, {})
        if TOTAL_COLUMN < len(row):
            value = _num(row[TOTAL_COLUMN])
            if value is not None:
                bucket[TOTAL_KEY] = value
        for col, code in LEAD_COLUMNS.items():
            if col < len(row):
                value = _num(row[col])
                if value is not None:
                    bucket[code] = value

    for period, row in month_rows(cont):
        bucket = out.setdefault(period, {})
        for col, code in CONT_COLUMNS.items():
            if col < len(row):
                value = _num(row[col])
                if value is not None:
                    bucket[code] = value

    return out


def parse(data: bytes, *, released_at: date, release_url: str,
          attachments: list[Attachment], collected_at: datetime) -> list[SeriesRecord]:
    tables = hwpx.tables(data)
    level_a, level_b, delta_a, delta_b = find_tables(tables)
    check_layout(level_a, level_b)
    check_layout(delta_a, delta_b)

    levels = _series_by_period(level_a, level_b)
    deltas = _series_by_period(delta_a, delta_b)
    if not levels:
        raise ValueError("수준 표에서 월 행을 찾지 못했다")

    # 문서가 스스로 검증 대조점을 갖고 있다 — 최신월 총량 증감이 요약문에 문장으로
    # 나온다. 어긋나면 서식이 바뀐 것이므로 조용히 틀린 숫자를 넣지 않고 실패한다.
    latest = max(levels)
    stated = headline_delta(tables)
    total_delta = deltas.get(latest, {}).get(TOTAL_KEY)
    if stated is not None and total_delta is not None and abs(stated - total_delta) > 1.0:
        raise ValueError(
            f"요약문과 증감표가 대조에 실패했다: 요약 {stated} vs 표 {total_delta}")

    records: list[SeriesRecord] = []
    for period, values in levels.items():
        delta = deltas.get(period, {})
        if TOTAL_KEY in values:
            records.append(SeriesRecord(
                id=make_id("ei", period, "total", None), source="ei",
                breakdown="total", category=None, period=period,
                value=values[TOTAL_KEY], yoy=delta.get(TOTAL_KEY),
                released_at=released_at, release_url=release_url,
                attachments=attachments, collected_at=collected_at,
            ))
        for code, value in values.items():
            if code == TOTAL_KEY:
                continue
            records.append(SeriesRecord(
                id=make_id("ei", period, "industry", code), source="ei",
                breakdown="industry", category=code, period=period,
                value=value, yoy=delta.get(code),
                released_at=released_at, release_url=release_url,
                attachments=attachments, collected_at=collected_at,
            ))
    return records


EXPECTED_CODES = set("ACDEFGHIJKLMNOPQRS")


def check_coverage(records: list[SeriesRecord]) -> None:
    """최신월에 기대한 대분류가 다 왔는지 본다.

    열 위치가 밀리거나 값이 비면 그 산업이 조용히 빠진다. 화면에서는 그냥
    없는 칸으로 보일 뿐 아무 흔적도 남지 않는다. 형제 수집기 둘도 같은 가드를 갖는다.
    """
    if not records:
        raise ValueError("수집된 레코드가 없다")
    latest = max(r.period for r in records)
    got = {r.category for r in records
           if r.period == latest and r.breakdown == "industry"}
    missing = EXPECTED_CODES - got
    if missing:
        raise ValueError(f"{latest} 에 빠진 산업 대분류: {sorted(missing)}")


def latest_issue() -> tuple[str, date, str, bytes, list[Attachment]]:
    html = requests.post(LIST_URL, data=SEARCH,
                         headers={**HEADERS, "Referer": LIST_URL}, timeout=30).text
    m = re.search(r'news_seq=(\d+)[^>]*>(.*?)</a>', html, re.S)
    if m is None:
        raise ValueError("게시판에서 회차를 찾지 못했다")
    seq = m.group(1)
    title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(2))).strip()

    view = f"{VIEW_URL}?news_seq={seq}"
    detail = requests.get(view, headers=HEADERS, timeout=30).text.replace("&amp;", "&")
    link = re.search(r'href="(/common/downloadFile\.do\?[^"]*file_ext=hwpx)"', detail)
    if link is None:
        raise ValueError(f"hwpx 첨부를 찾지 못했다: {title}")

    posted = re.search(r"(\d{4})[.\-](\d{1,2})[.\-](\d{1,2})", detail)
    if posted is None:
        raise ValueError(f"발표일을 찾지 못했다: {title}")
    released_at = date(int(posted.group(1)), int(posted.group(2)), int(posted.group(3)))

    data = requests.get("https://www.moel.go.kr" + link.group(1),
                        headers={**HEADERS, "Referer": view}, timeout=120).content
    attachments = [Attachment(type="hwpx", url="https://www.moel.go.kr" + link.group(1))]
    return title, released_at, view, data, attachments


def collect(today: date) -> list[SeriesRecord]:
    # today 는 쓰지 않는다 — 기준월은 보도자료 표 자체가 갖고 있다.
    # 오케스트레이터가 세 수집기를 같은 시그니처로 부르므로 인자는 유지한다.
    title, released_at, view, data, attachments = latest_issue()
    records = parse(data, released_at=released_at, release_url=view,
                    attachments=attachments, collected_at=datetime.now(KST))
    check_coverage(records)
    return records
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python -m pytest domains/employment/tests/test_ei.py -q`
Expected: PASS (7 passed)

열 배치가 바뀌어 `check_layout` 이 실패하면 실제 헤더를 찍어 `LEAD_COLUMNS`/`CONT_COLUMNS` 와 `_LEAD_HEADER`/`_CONT_HEADER` 를 맞춘다:

```bash
python -c "
from pathlib import Path
from domains.employment.pipeline import hwpx
from domains.employment.pipeline.collectors.ei import find_tables
t=hwpx.tables(Path('domains/employment/tests/fixtures/ei_2026-07.hwpx').read_bytes())
a,b,c,d=find_tables(t)
print('앞 0행:', a[0]); print('앞 1행:', a[1]); print('앞 데이터:', a[-1])
print('이어짐 1행:', b[1]); print('이어짐 데이터:', b[-1])
"
```

- [ ] **Step 5: 커밋**

```bash
git add domains/employment/pipeline/collectors/ei.py domains/employment/tests/test_ei.py
git commit -m "feat(employment): 고용행정통계 수집기 (보도자료 hwpx + 대조 검증)"
```

---

### Task 8: 오케스트레이터와 워크플로

**Files:**
- Create: `domains/employment/pipeline/collect.py`, `domains/employment/pipeline/check_run.py`
- Create: `domains/employment/tests/test_collect.py`
- Create: `.github/workflows/collect-employment.yml`
- Modify: `README.md` (실행 절에 고용동향 수집 명령 한 줄 추가)

**Interfaces:**
- Consumes: `store.upsert`·`load_series`·`save_series` (Task 1), 세 수집기의 `collect(today)` (Task 5~7)
- Produces: `python -m domains.employment.pipeline.collect` 진입점, `domains/employment/data/series.json`, `last_run.json`

**전망 도메인과 같은 규약을 지킨다:** 수집기 하나가 실패해도 나머지는 진행하고, 실패는 `last_run.json` 의 `errors` 에 한 줄로 남긴다. 트레이스백을 담지 않는다.

**수기 입력 폴백 (스펙 7.7).** `data/manual/<YYYY-MM>.json` 이 있으면 그 달 레코드는 수집기 결과보다 우선한다. 파싱이 깨진 달에도 손으로 채워 서비스가 멈추지 않게 한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`domains/employment/tests/test_collect.py`:

```python
import json
from datetime import date, datetime
from pathlib import Path

from domains.employment.pipeline import collect
from domains.employment.pipeline.models import SeriesRecord, make_id


def rec(source="ei", period="2026-07", value=15877.0):
    return SeriesRecord(
        id=make_id(source, period, "total", None), source=source,
        breakdown="total", category=None, period=period, value=value, yoy=1.0,
        released_at=date(2026, 8, 11), release_url="https://x/view",
        collected_at=datetime(2026, 8, 30, 9, 0),
    )


def test_writes_records_and_a_run_summary(tmp_path):
    code = collect.main(tmp_path, {"ei": lambda today: [rec()]})
    assert code == 0
    rows = json.loads((tmp_path / "series.json").read_text(encoding="utf-8"))
    assert [r["id"] for r in rows] == ["ei-2026-07-headcount-total"]
    summary = json.loads((tmp_path / "last_run.json").read_text(encoding="utf-8"))
    assert summary["collectors"]["ei"]["ok"] is True
    assert summary["errors"] == []


def test_one_broken_collector_does_not_stop_the_others(tmp_path):
    def boom(today):
        raise ValueError("표를 찾지 못했다")

    collect.main(tmp_path, {"ei": boom, "est": lambda today: [rec(source="est")]})
    summary = json.loads((tmp_path / "last_run.json").read_text(encoding="utf-8"))
    assert summary["collectors"]["ei"]["ok"] is False
    assert summary["collectors"]["est"]["ok"] is True
    assert summary["errors"] == ["ei: ValueError: 표를 찾지 못했다"]


def test_the_summary_never_carries_a_traceback(tmp_path):
    def boom(today):
        raise ValueError("실패")

    collect.main(tmp_path, {"ei": boom})
    text = (tmp_path / "last_run.json").read_text(encoding="utf-8")
    assert "Traceback" not in text and "File \"" not in text


def test_manual_entries_win_over_collected_ones(tmp_path):
    manual = tmp_path / "manual"
    manual.mkdir()
    override = rec(value=99999.0).model_dump(mode="json")
    (manual / "2026-07.json").write_text(
        json.dumps([override], ensure_ascii=False), encoding="utf-8")

    collect.main(tmp_path, {"ei": lambda today: [rec(value=15877.0)]})
    rows = json.loads((tmp_path / "series.json").read_text(encoding="utf-8"))
    assert rows[0]["value"] == 99999.0


def test_revised_values_replace_the_old_ones(tmp_path):
    collect.main(tmp_path, {"ei": lambda today: [rec(period="2026-06", value=15855.0)]})
    collect.main(tmp_path, {"ei": lambda today: [rec(period="2026-06", value=15856.0)]})
    rows = json.loads((tmp_path / "series.json").read_text(encoding="utf-8"))
    assert len(rows) == 1
    assert rows[0]["value"] == 15856.0
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest domains/employment/tests/test_collect.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'domains.employment.pipeline.collect'`

- [ ] **Step 3: `collect.py` 를 구현한다**

```python
"""고용동향 수집 오케스트레이터.

수집기 하나가 실패해도 나머지는 진행한다. 실패는 last_run.json 에 한 줄로
남긴다 — 이 파일은 저장소에 커밋되므로 트레이스백을 담으면 돌린 사람의
절대경로까지 함께 실린다.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import store
from .collectors import eaps, ei, est
from .models import SeriesRecord

KST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

COLLECTORS: dict[str, Callable[[date], list[SeriesRecord]]] = {
    "eaps": eaps.collect,
    "est": est.collect,
    "ei": ei.collect,
}


def load_manual(data_dir: Path) -> list[SeriesRecord]:
    """수기 입력 폴백. 파싱이 깨진 달을 손으로 채울 수 있게 한다."""
    manual_dir = data_dir / "manual"
    if not manual_dir.is_dir():
        return []
    records: list[SeriesRecord] = []
    for path in sorted(manual_dir.glob("*.json")):
        rows = json.loads(path.read_text(encoding="utf-8"))
        records.extend(SeriesRecord.model_validate(row) for row in rows)
    return records


def main(data_dir: Path = DATA_DIR,
         collectors: dict[str, Callable[[date], list[SeriesRecord]]] | None = None,
         ) -> int:
    collectors = COLLECTORS if collectors is None else collectors
    series_path = data_dir / "series.json"
    last_run_path = data_dir / "last_run.json"
    today = datetime.now(KST).date()

    merged = store.load_series(series_path)
    summary = {
        "run_at": datetime.now(KST).isoformat(),
        "collectors": {},
        "conflicts": [],
        "errors": [],
    }

    for name, collect_fn in collectors.items():
        try:
            candidates = collect_fn(today)
            result = store.upsert(merged, candidates)
            merged = result.records
            summary["collectors"][name] = {
                "ok": True, "fetched": len(candidates),
                "added": len(result.added), "updated": len(result.updated),
            }
        except Exception as exc:
            summary["collectors"][name] = {
                "ok": False, "fetched": 0, "added": 0, "updated": 0,
            }
            summary["errors"].append(f"{name}: {type(exc).__name__}: {exc}")

    # 수기 입력은 마지막에 얹어 수집 결과를 이긴다.
    manual = load_manual(data_dir)
    if manual:
        merged = store.upsert(merged, manual).records

    store.save_series(series_path, merged)
    last_run_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary["collectors"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**주의:** `store.upsert` 는 `released_at` 이 더 오래된 레코드를 무시한다. 수기 입력이 항상 이기려면 수기 파일의 `released_at` 을 수집분과 같거나 더 나중으로 적어야 한다. `data/manual/README.md` 에 이 규칙을 한 줄 남긴다.

- [ ] **Step 4: 수기 입력 안내를 남긴다**

`domains/employment/data/manual/README.md`:

```markdown
# 수기 입력 폴백

보도자료 서식이 바뀌어 파싱이 깨진 달을 손으로 채우는 자리다.
`<YYYY-MM>.json` 에 `series.json` 과 같은 모양의 레코드 배열을 넣는다.

수집 결과보다 나중에 얹히지만, `released_at` 이 이미 저장된 레코드보다
오래되면 무시된다. 수집분과 같거나 더 나중 날짜를 적을 것.
```

- [ ] **Step 5: 통과를 확인한다**

Run: `python -m pytest domains/employment/tests/test_collect.py -q`
Expected: PASS (5 passed)

- [ ] **Step 6: `check_run.py` 를 만든다**

전망 도메인의 것과 같은 규약이다(`KNOWN_DOWN` 으로 아는 장애를 넘기고 나머지만 실패시킨다).

```python
"""수집 결과를 보고 그날 실행을 실패로 볼지 판정한다(워크플로 마지막 스텝).

수집기 하나가 오래 죽어 있으면 매일 빨개져서, 정작 다른 수집기가 깨진 날을
알아채지 못한다. 원인을 이미 아는 장애는 KNOWN_DOWN 에 적어 로그로만 남긴다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def known_down_from_env() -> set[str]:
    return {n.strip() for n in os.environ.get("KNOWN_DOWN", "").split(",") if n.strip()}


def main(last_run_path: Path = DATA_DIR / "last_run.json", *,
         known_down: set[str] | None = None) -> int:
    known = known_down_from_env() if known_down is None else known_down
    run = json.loads(Path(last_run_path).read_text(encoding="utf-8"))

    unexpected = []
    for error in run["errors"]:
        name = error.split(":", 1)[0].strip()
        if name in known:
            print(f"::notice::알고 있는 장애라 넘어간다 — {error}")
        else:
            unexpected.append(error)
            print(f"::error::{error}")

    for name in sorted(known):
        if run["collectors"].get(name, {}).get("ok"):
            print(f"::warning::{name} 가 다시 수집됐다 — 워크플로의 KNOWN_DOWN 에서 지울 것")

    return 1 if unexpected else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 7: 워크플로를 만든다**

`.github/workflows/collect-employment.yml`:

```yaml
name: collect-employment

on:
  schedule:
    - cron: "10 7 * * *" # 07:10 UTC = 16:10 KST — 전망 수집(16:00)과 겹치지 않게
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: collect-employment
  cancel-in-progress: false

jobs:
  collect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python -m pytest -q domains/employment
      - run: python -m domains.employment.pipeline.collect
        env:
          KOSIS_API_KEY: ${{ secrets.KOSIS_API_KEY }}
      - name: Commit data
        run: |
          git config user.name "employment-bot"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add domains/employment/data/
          git diff --cached --quiet || git commit -m "data: employment collect $(date -u +%F)"
          git push
      - name: Fail on collector errors
        env:
          KNOWN_DOWN: ""
        run: python -m domains.employment.pipeline.check_run
```

테스트 범위를 `domains/employment` 으로 좁힌 것은 전망 도메인과 같은 이유다 — 한 도메인의 테스트가 깨져도 다른 도메인의 수집이 멈추면 안 된다.

- [ ] **Step 8: README 실행 절에 한 줄 더한다**

```
python -m domains.employment.pipeline.collect   # 고용동향 수집 1회 (KOSIS_API_KEY 필요)
```

- [ ] **Step 9: YAML 문법과 전체 테스트를 확인한다**

Run: `python -c "import yaml,glob;[yaml.safe_load(open(f,encoding='utf-8')) for f in glob.glob('.github/workflows/*.yml')];print('ok')"`
Expected: `ok`

Run: `python -m pytest -q`
Expected: PASS — 기존 전망 테스트가 하나도 깨지지 않아야 한다

- [ ] **Step 10: 커밋**

```bash
git add domains/employment/pipeline/collect.py domains/employment/pipeline/check_run.py domains/employment/tests/test_collect.py domains/employment/data/manual/README.md .github/workflows/collect-employment.yml README.md
git commit -m "feat(employment): 수집 오케스트레이터와 워크플로"
```

- [ ] **Step 11: CI 시크릿을 등록한다 (사람이 확인)**

Run: `gh secret set KOSIS_API_KEY < <(grep '^KOSIS_API_KEY=' .env | cut -d= -f2-)`

등록 후 확인: `gh secret list | grep KOSIS_API_KEY`

이 스텝은 저장소 설정을 바꾼다. 실행 전에 사람에게 확인받는다.

- [ ] **Step 12: 실제 수집을 한 번 돌려 초기 적재를 만든다**

Run: `python -m domains.employment.pipeline.collect`
Expected: 세 수집기가 모두 `ok: true` 이고 `series.json` 이 생성된다

확인:

```bash
python -c "
import json
rows=json.load(open('domains/employment/data/series.json',encoding='utf-8'))
periods=sorted({r['period'] for r in rows})
print(len(rows),'레코드', periods[0],'~',periods[-1])
for s in ('eaps','est','ei'):
    sub=[r for r in rows if r['source']==s]
    print(f'  {s}: {len(sub)}개, 최신 {max(r[\"period\"] for r in sub)}')
"
```

**출처마다 최신월이 다른 것이 정상이다** — 고용행정통계가 가장 빠르고 사업체노동력조사가 가장 늦다(스파이크 10장). 같은 최신월을 기대하지 마라.

- [ ] **Step 13: 데이터를 커밋한다**

```bash
git add domains/employment/data/series.json domains/employment/data/last_run.json
git commit -m "data(employment): 초기 적재"
```

---

## 완료 기준

- `python -m pytest -q` 통과 (전망 도메인 테스트가 하나도 깨지지 않음)
- `python -m domains.employment.pipeline.collect` 가 세 수집기 모두 `ok: true` 로 끝남
- `domains/employment/data/series.json` 에 세 출처 × 최근 24개월 × (총량 + 산업 대분류) 레코드가 적재됨
- ~~허브의 고용동향 버튼 자동 활성화~~ — **C단계에서는 확인되지 않는다.** `tools/build.py` 의 `discover_domains()` 가 `domains/<이름>/app/` 이 있어야 도메인으로 인정하는데, 고용동향은 아직 화면이 없다(D단계 몫). 그래서 `_site` 에 배포되지 않고 허브는 계속 "준비중" 으로 둔다.

  **이것이 옳은 동작이다.** 화면 없는 도메인의 버튼을 켜면 눌렀을 때 404 가 난다. 데이터만 있는 상태에서 "준비중" 은 거짓이 아니라 사실이다. `build.py` 를 넓혀 데이터만 있는 도메인을 배포하게 만들지 마라 — 그러면 갈 곳 없는 버튼이 생긴다.

  느슨한 결합이 실제로 작동하는지는 **D단계에서** 확인된다. `domains/employment/app/` 이 생기는 순간 허브 코드를 한 줄도 안 고쳤는데 버튼이 켜져야 한다
- `.github/workflows/collect-employment.yml` 이 등록되고 `KOSIS_API_KEY` 시크릿이 있음

## D단계로 넘길 것

- **허브 자동 활성화 확인.** `domains/employment/app/` 이 생기면 `tools/build.py` 가 도메인을 인식해 `_site/employment/` 를 배포하고, 허브가 `data/last_run.json` 을 받아 버튼을 켠다. **허브 코드를 고쳐야 한다면 A단계의 느슨한 결합이 실패한 것이다.**

- 화면 3개(총괄·산업별·출처비교)와 증감 비교 시트 — 스펙 7.5·7.6
- **미발표와 미제공의 구분** — 스펙 11장. 출처마다 최신월이 달라, 아직 안 나온 달은
  "미발표", 그 출처가 원래 안 잡는 산업은 "미제공"으로 다르게 표시해야 한다.
  `industries.json` 의 `provided` 가 후자를, `series.json` 에 그 달 레코드가 없는 것이
  전자를 판정한다
