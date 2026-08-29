# Phase 1: 데이터 파이프라인 (스키마 + IMF·OECD 수집기) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `forecasts.json` 스키마를 코드로 확정하고, IMF·OECD API에서 한국 전망치를 수집해 실데이터를 쌓는 파이프라인 + GitHub Actions 일일 실행을 구축한다.

**Architecture:** 데이터는 저장소 내 JSON 파일(서버·DB 없음). 수집기는 "순수 fetch+파싱 → 후보 레코드" 만 만들고, 오케스트레이터(`collect.py`)가 기존 저장값과 비교해 **값이 바뀐 것만 신규 레코드로 추가**(변화 감지 = 회차 감지). `prev_value`/`revision`은 저장 시점에 store가 자동 연결한다.

**Tech Stack:** Python 3.11+, pydantic v2 (스키마 검증), requests (OECD), curl_cffi (IMF — Akamai TLS 핑거프린트 차단 우회, 사전 검증됨), pytest, GitHub Actions.

**Spec:** `고용전망_아카이브_기획서.md` (특히 2장 대상 데이터, 3장 스키마, 4.3 이상치 규칙, 6장 감지)

## Global Constraints

- Python 3.11 이상. 의존성은 `pydantic>=2.7`, `requests>=2.32`, `curl_cffi>=0.7`, `pytest>=8` 4개만.
- 모든 JSON 파일은 UTF-8, `ensure_ascii=False`, `indent=2`, 파일 끝 개행.
- 시각은 전부 KST(`timezone(timedelta(hours=9))`).
- 지표 코드는 7종 고정: `emp_change`, `emp_rate`, `unemp_rate`, `gdp_growth`, `cpi`, `emp_rate_youth`, `labor_force`.
- 레코드 id 형식: `{org소문자}-{YYYY-MM}-{indicator}-{target_year}` (예: `oecd-2026-08-gdp_growth-2027`).
- 값 검증 범위(기획서 4.3, 벗어나면 레코드 생성 자체가 실패해야 함):
  emp_change ±100(만명), emp_rate 40~80, unemp_rate 0~15, gdp_growth -10~10, cpi -5~15, emp_rate_youth 0~80, labor_force 40~80.
- 동일 id 충돌 시 덮어쓰기 금지, 충돌 로그 기록 (기획서 4.3).
- 실패는 무음 통과 금지 — `last_run.json`에 명시 기록 (기획서 9.3).
- 테스트는 네트워크를 쓰지 않는다 (fixture 기반). 실제 API 호출은 Task 8 스모크 테스트에서만.
- 커밋 메시지 끝에 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` 한 줄 추가.

## 사전 검증된 API 사실 (2026-08-29 확인)

- **OECD**: `https://sdmx.oecd.org/public/rest/data/OECD.ECO.MAD,DSD_EO@DF_EO,/KOR.GDPV_ANNPCT+UNR+CPI_YTYPCT+ET.A?startPeriod=2025&endPeriod=2027&format=csvfilewithlabels`
  → CSV 반환. 버전 자리를 비우면 최신 회차(현재 1.5 = EO119). `STRUCTURE_NAME` 컬럼에 "Economic Outlook 119" 회차명 포함.
  컬럼: `STRUCTURE,STRUCTURE_ID,STRUCTURE_NAME,ACTION,REF_AREA,Reference area,MEASURE,Measure,FREQ,Frequency of observation,TIME_PERIOD,Time period,OBS_VALUE,...`
  KOR 실측값 예: GDPV_ANNPCT 2026=2.630..., 2027=1.941...; UNR 2026=2.809...; CPI_YTYPCT 2026=2.623...; ET 2025=28769250, 2026=28974095.855..., 2027=29097415.152...
- **IMF**: `https://www.imf.org/external/datamapper/api/v1/{지표코드}/KOR` → JSON `{"values":{"<코드>":{"KOR":{"1980":..., "2031":...}}}}` (연도별 값, 전망 연도 포함). 지표코드: `NGDP_RPCH`(성장률), `PCPIPCH`(물가), `LUR`(실업률).
  ⚠ 일반 curl/requests는 Akamai가 403 차단 — 반드시 `curl_cffi`의 `impersonate="chrome"` 사용 (브라우저에서는 정상 응답 확인됨).
- **취업자 증감**: OECD `ET`(취업자 수, 명)의 연차 차분 ÷ 10000 = 만명. 예: 2026년 (28974095.855−28769250)/10000 = **20.5만명**.

## File Structure

```
고용전망아카이브/
├─ conftest.py                  # pytest가 저장소 루트를 sys.path에 올리도록 (빈 파일)
├─ requirements.txt
├─ .gitignore
├─ README.md                    # Task 7
├─ data/
│  ├─ orgs.json                 # 기관 메타 9개
│  ├─ indicators.json           # 지표 메타 7개 (범위·단위·소수점의 단일 출처)
│  ├─ forecasts.json            # 수집 결과 (Task 8에서 생성)
│  └─ last_run.json             # 실행 로그 (실행 시 생성)
├─ src/
│  ├─ __init__.py
│  ├─ models.py                 # ForecastRecord, make_id, INDICATOR_META, VALUE_RANGES
│  ├─ store.py                  # load/save/merge/latest_record
│  ├─ collect.py                # 오케스트레이터 + CLI (python -m src.collect)
│  └─ collectors/
│     ├─ __init__.py
│     ├─ oecd.py                # fetch_raw / parse / collect
│     └─ imf.py                 # fetch_raw / parse / collect
├─ tests/
│  ├─ test_models.py
│  ├─ test_store.py
│  ├─ test_oecd.py
│  ├─ test_imf.py
│  ├─ test_collect.py
│  └─ fixtures/
│     └─ oecd_eo119_kor.csv
└─ .github/workflows/collect.yml
```

---

### Task 1: 저장소 초기화 + 메타데이터 파일

**Files:**
- Create: `.gitignore`, `requirements.txt`, `conftest.py`, `src/__init__.py`, `src/collectors/__init__.py`, `data/orgs.json`, `data/indicators.json`, `tests/test_metadata.py`

**Interfaces:**
- Produces: `data/indicators.json` — 이후 모든 태스크가 지표 메타(단위·소수점·범위)의 단일 출처로 사용. 각 항목: `{"code": str, "name_ko": str, "unit": str, "decimals": int, "range": [lo, hi]}`

- [ ] **Step 1: git 저장소 초기화**

```bash
git init -b main
```

- [ ] **Step 2: 기반 파일 작성**

`.gitignore`:
```
__pycache__/
*.pyc
.venv/
.pytest_cache/
```

`requirements.txt`:
```
pydantic>=2.7
requests>=2.32
curl_cffi>=0.7
pytest>=8
```

`conftest.py`, `src/__init__.py`, `src/collectors/__init__.py`: 빈 파일.

- [ ] **Step 3: 의존성 설치**

Run: `pip install -r requirements.txt`

- [ ] **Step 4: 실패하는 테스트 작성** — `tests/test_metadata.py`

```python
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

def test_indicators_has_seven_codes():
    rows = json.loads((DATA / "indicators.json").read_text(encoding="utf-8"))
    codes = {r["code"] for r in rows}
    assert codes == {"emp_change", "emp_rate", "unemp_rate", "gdp_growth",
                     "cpi", "emp_rate_youth", "labor_force"}
    for r in rows:
        assert set(r) == {"code", "name_ko", "unit", "decimals", "range"}
        lo, hi = r["range"]
        assert lo < hi

def test_orgs_has_nine_orgs_with_tracks():
    rows = json.loads((DATA / "orgs.json").read_text(encoding="utf-8"))
    assert {r["org"] for r in rows} == {"BOK", "KDI", "KLI", "MOEF", "IMF",
                                        "OECD", "ADB", "KIET", "KEIS"}
    assert all(r["track"] in ("A", "B") for r in rows)
```

- [ ] **Step 5: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_metadata.py -v`
Expected: FAIL (FileNotFoundError — indicators.json 없음)

- [ ] **Step 6: 메타데이터 파일 작성**

`data/indicators.json`:
```json
[
  {"code": "emp_change", "name_ko": "취업자 증감", "unit": "만명", "decimals": 1, "range": [-100, 100]},
  {"code": "emp_rate", "name_ko": "고용률", "unit": "%", "decimals": 1, "range": [40, 80]},
  {"code": "unemp_rate", "name_ko": "실업률", "unit": "%", "decimals": 1, "range": [0, 15]},
  {"code": "gdp_growth", "name_ko": "경제성장률", "unit": "%", "decimals": 1, "range": [-10, 10]},
  {"code": "cpi", "name_ko": "소비자물가 상승률", "unit": "%", "decimals": 1, "range": [-5, 15]},
  {"code": "emp_rate_youth", "name_ko": "청년 고용률", "unit": "%", "decimals": 1, "range": [0, 80]},
  {"code": "labor_force", "name_ko": "경제활동참가율", "unit": "%", "decimals": 1, "range": [40, 80]}
]
```

`data/orgs.json`:
```json
[
  {"org": "BOK", "name_ko": "한국은행", "homepage": "https://www.bok.or.kr", "report": "경제전망보고서", "track": "A", "method": "pdf"},
  {"org": "KDI", "name_ko": "KDI", "homepage": "https://www.kdi.re.kr", "report": "경제전망", "track": "A", "method": "pdf"},
  {"org": "KLI", "name_ko": "한국노동연구원", "homepage": "https://www.kli.re.kr", "report": "고용전망(노동리뷰)", "track": "A", "method": "pdf"},
  {"org": "MOEF", "name_ko": "기획재정부", "homepage": "https://www.moef.go.kr", "report": "경제정책방향", "track": "A", "method": "hwp"},
  {"org": "IMF", "name_ko": "IMF", "homepage": "https://www.imf.org", "report": "WEO / WEO Update", "track": "A", "method": "api"},
  {"org": "OECD", "name_ko": "OECD", "homepage": "https://www.oecd.org", "report": "Economic Outlook / Interim", "track": "A", "method": "api"},
  {"org": "ADB", "name_ko": "ADB", "homepage": "https://www.adb.org", "report": "Asian Development Outlook", "track": "A", "method": "pdf"},
  {"org": "KIET", "name_ko": "산업연구원", "homepage": "https://www.kiet.re.kr", "report": "경제·산업전망", "track": "A", "method": "pdf"},
  {"org": "KEIS", "name_ko": "한국고용정보원", "homepage": "https://www.keis.or.kr", "report": "고용리뷰 / 고용브리프", "track": "B", "method": "llm"}
]
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `python -m pytest tests/test_metadata.py -v`
Expected: PASS (2 passed)

- [ ] **Step 8: 커밋**

```bash
git add .gitignore requirements.txt conftest.py src/ data/ tests/ 고용전망_아카이브_기획서.md 고용전망_아카이브_화면기획서.md docs/
git commit -m "chore: 저장소 초기화 + 기관·지표 메타데이터

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: 전망 레코드 모델 (`models.py`)

**Files:**
- Create: `src/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: `data/indicators.json` (Task 1)
- Produces:
  - `class ForecastRecord(pydantic.BaseModel)` — 기획서 3.1 스키마 그대로. 필드와 타입은 Step 3 코드가 정본.
  - `make_id(org: str, published_at: date, indicator: str, target_year: int) -> str`
  - `INDICATOR_META: dict[str, dict]` — code → `{"code","name_ko","unit","decimals","range"}`
  - `VALUE_RANGES: dict[str, tuple[float, float]]`
  - `Indicator` — 7개 코드의 `Literal` 타입

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_models.py`

```python
from datetime import date, datetime
import pytest
from src.models import ForecastRecord, make_id, VALUE_RANGES, INDICATOR_META


def base_kwargs(**over):
    kw = dict(
        id="oecd-2026-08-gdp_growth-2027", org="OECD", org_name_ko="OECD",
        report_title="Economic Outlook 119", published_at=date(2026, 8, 29),
        target_year=2027, indicator="gdp_growth", value=1.9, unit="%",
        source_url="https://sdmx.oecd.org/example",
        landing_url="https://www.oecd.org/economic-outlook",
        confidence="verified", collected_at=datetime(2026, 8, 29, 16, 0),
    )
    kw.update(over)
    return kw


def test_valid_record_with_defaults():
    r = ForecastRecord(**base_kwargs())
    assert r.target_period == "annual"
    assert r.prev_value is None
    assert r.revision is None
    assert r.rationale == ""
    assert r.rationale_tags == []
    assert r.source_page is None


def test_value_out_of_range_rejected():
    with pytest.raises(ValueError):
        ForecastRecord(**base_kwargs(value=12.5))  # gdp_growth 범위는 -10~10


def test_unknown_indicator_rejected():
    with pytest.raises(ValueError):
        ForecastRecord(**base_kwargs(indicator="gdp"))


def test_make_id():
    assert make_id("OECD", date(2026, 8, 29), "gdp_growth", 2027) == \
        "oecd-2026-08-gdp_growth-2027"


def test_meta_loaded_from_indicators_json():
    assert set(VALUE_RANGES) == set(INDICATOR_META)
    assert VALUE_RANGES["gdp_growth"] == (-10, 10)
    assert INDICATOR_META["emp_change"]["unit"] == "만명"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL (ModuleNotFoundError: src.models)

- [ ] **Step 3: 구현** — `src/models.py`

```python
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

Indicator = Literal[
    "emp_change", "emp_rate", "unemp_rate", "gdp_growth",
    "cpi", "emp_rate_youth", "labor_force",
]

_INDICATORS_PATH = Path(__file__).resolve().parent.parent / "data" / "indicators.json"
INDICATOR_META: dict[str, dict] = {
    row["code"]: row
    for row in json.loads(_INDICATORS_PATH.read_text(encoding="utf-8"))
}
VALUE_RANGES: dict[str, tuple[float, float]] = {
    code: (meta["range"][0], meta["range"][1])
    for code, meta in INDICATOR_META.items()
}


def make_id(org: str, published_at: date, indicator: str, target_year: int) -> str:
    return f"{org.lower()}-{published_at:%Y-%m}-{indicator}-{target_year}"


class ForecastRecord(BaseModel):
    id: str
    org: str
    org_name_ko: str
    report_title: str
    published_at: date
    target_year: int = Field(ge=2000, le=2100)
    target_period: Literal["annual", "h1", "h2"] = "annual"
    indicator: Indicator
    value: float
    unit: str
    prev_value: Optional[float] = None
    revision: Optional[float] = None
    rationale: str = ""
    rationale_tags: list[str] = Field(default_factory=list)
    source_url: str
    source_page: Optional[int] = None
    landing_url: str
    confidence: Literal["verified", "extracted", "reviewed"]
    collected_at: datetime

    @model_validator(mode="after")
    def check_value_range(self):
        lo, hi = VALUE_RANGES[self.indicator]
        if not (lo <= self.value <= hi):
            raise ValueError(
                f"{self.indicator} value {self.value} out of range [{lo}, {hi}]"
            )
        return self
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: ForecastRecord 스키마 + 범위 검증

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: 저장소 계층 (`store.py`)

**Files:**
- Create: `src/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `ForecastRecord`, `make_id` (Task 2)
- Produces:
  - `load_forecasts(path: Path | str) -> list[ForecastRecord]` (파일 없으면 `[]`)
  - `save_forecasts(path: Path | str, records: list[ForecastRecord]) -> None`
  - `latest_record(records, org, indicator, target_year, target_period="annual") -> ForecastRecord | None`
  - `merge(existing: list[ForecastRecord], new: list[ForecastRecord]) -> MergeResult`
  - `@dataclass MergeResult`: `records: list[ForecastRecord]`, `added: list[str]`, `skipped: list[str]`, `conflicts: list[str]`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_store.py`

```python
from datetime import date, datetime
from src.models import ForecastRecord, make_id
from src import store


def rec(month: int, value: float, year: int = 2027, org: str = "OECD",
        indicator: str = "gdp_growth") -> ForecastRecord:
    pub = date(2026, month, 15)
    return ForecastRecord(
        id=make_id(org, pub, indicator, year), org=org, org_name_ko=org,
        report_title="test", published_at=pub, target_year=year,
        indicator=indicator, value=value, unit="%",
        source_url="https://example.com/a", landing_url="https://example.com",
        confidence="verified", collected_at=datetime(2026, month, 15, 16, 0),
    )


def test_first_insert_has_no_prev():
    result = store.merge([], [rec(6, 2.0)])
    assert result.added == ["oecd-2026-06-gdp_growth-2027"]
    assert result.records[0].prev_value is None
    assert result.records[0].revision is None


def test_second_edition_links_prev_and_revision():
    first = store.merge([], [rec(6, 2.0)]).records
    result = store.merge(first, [rec(8, 2.3)])
    added = [r for r in result.records if r.id == "oecd-2026-08-gdp_growth-2027"][0]
    assert added.prev_value == 2.0
    assert added.revision == 0.3


def test_same_id_same_value_skipped():
    first = store.merge([], [rec(6, 2.0)]).records
    result = store.merge(first, [rec(6, 2.0)])
    assert result.skipped == ["oecd-2026-06-gdp_growth-2027"]
    assert len(result.records) == 1


def test_same_id_different_value_is_conflict_not_overwrite():
    first = store.merge([], [rec(6, 2.0)]).records
    result = store.merge(first, [rec(6, 2.5)])
    assert len(result.conflicts) == 1
    assert result.records[0].value == 2.0  # 덮어쓰지 않음


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "forecasts.json"
    records = store.merge([], [rec(6, 2.0), rec(8, 2.3)]).records
    store.save_forecasts(path, records)
    loaded = store.load_forecasts(path)
    assert [r.id for r in loaded] == [r.id for r in records]
    assert loaded[1].prev_value == 2.0


def test_load_missing_file_returns_empty(tmp_path):
    assert store.load_forecasts(tmp_path / "nope.json") == []
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL (ModuleNotFoundError: src.store)

- [ ] **Step 3: 구현** — `src/store.py`

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import ForecastRecord


@dataclass
class MergeResult:
    records: list[ForecastRecord]
    added: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def load_forecasts(path: Path | str) -> list[ForecastRecord]:
    p = Path(path)
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    return [ForecastRecord.model_validate(row) for row in raw]


def save_forecasts(path: Path | str, records: list[ForecastRecord]) -> None:
    ordered = sorted(records, key=lambda r: (r.published_at.isoformat(), r.id))
    rows = [r.model_dump(mode="json") for r in ordered]
    Path(path).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def latest_record(records, org, indicator, target_year, target_period="annual"):
    matches = [
        r for r in records
        if r.org == org and r.indicator == indicator
        and r.target_year == target_year and r.target_period == target_period
    ]
    return max(matches, key=lambda r: r.published_at) if matches else None


def merge(existing: list[ForecastRecord], new: list[ForecastRecord]) -> MergeResult:
    result = MergeResult(records=list(existing))
    by_id = {r.id: r for r in result.records}
    for cand in sorted(new, key=lambda r: r.published_at):
        stored = by_id.get(cand.id)
        if stored is not None:
            if stored.value == cand.value:
                result.skipped.append(cand.id)
            else:
                result.conflicts.append(
                    f"{cand.id}: stored={stored.value} incoming={cand.value}"
                )
            continue
        prev = latest_record(
            result.records, cand.org, cand.indicator,
            cand.target_year, cand.target_period,
        )
        if prev is not None and prev.published_at < cand.published_at:
            cand = cand.model_copy(update={
                "prev_value": prev.value,
                "revision": round(cand.value - prev.value, 2),
            })
        result.records.append(cand)
        by_id[cand.id] = cand
        result.added.append(cand.id)
    return result
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_store.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: 커밋**

```bash
git add src/store.py tests/test_store.py
git commit -m "feat: forecasts.json 저장·병합 (prev_value 자동 연결, 충돌 보호)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: OECD 수집기 (`collectors/oecd.py`)

**Files:**
- Create: `src/collectors/oecd.py`, `tests/fixtures/oecd_eo119_kor.csv`
- Test: `tests/test_oecd.py`

**Interfaces:**
- Consumes: `ForecastRecord`, `make_id`, `INDICATOR_META` (Task 2)
- Produces:
  - `fetch_raw(today: date) -> str` (네트워크 — CSV 텍스트)
  - `parse(raw_csv: str, today: date) -> list[ForecastRecord]` (순수 함수)
  - `collect(today: date) -> list[ForecastRecord]` — 오케스트레이터가 호출하는 진입점

- [ ] **Step 1: fixture 작성** — `tests/fixtures/oecd_eo119_kor.csv`

(실제 응답에서 파싱에 쓰는 컬럼만 남긴 축약본. 값은 2026-08-29 실측값)

```csv
STRUCTURE,STRUCTURE_ID,STRUCTURE_NAME,ACTION,REF_AREA,Reference area,MEASURE,Measure,FREQ,Frequency of observation,TIME_PERIOD,Time period,OBS_VALUE
DATAFLOW,OECD.ECO.MAD:DSD_EO@DF_EO(1.5),Economic Outlook 119,I,KOR,Korea,GDPV_ANNPCT,"Gross domestic product, volume, growth",A,Annual,2026,,2.63042316286754
DATAFLOW,OECD.ECO.MAD:DSD_EO@DF_EO(1.5),Economic Outlook 119,I,KOR,Korea,GDPV_ANNPCT,"Gross domestic product, volume, growth",A,Annual,2027,,1.94194557395251
DATAFLOW,OECD.ECO.MAD:DSD_EO@DF_EO(1.5),Economic Outlook 119,I,KOR,Korea,UNR,Unemployment rate,A,Annual,2026,,2.80954835858754
DATAFLOW,OECD.ECO.MAD:DSD_EO@DF_EO(1.5),Economic Outlook 119,I,KOR,Korea,UNR,Unemployment rate,A,Annual,2027,,2.70743323396456
DATAFLOW,OECD.ECO.MAD:DSD_EO@DF_EO(1.5),Economic Outlook 119,I,KOR,Korea,CPI_YTYPCT,Headline inflation,A,Annual,2026,,2.62332364473214
DATAFLOW,OECD.ECO.MAD:DSD_EO@DF_EO(1.5),Economic Outlook 119,I,KOR,Korea,CPI_YTYPCT,Headline inflation,A,Annual,2027,,2.24154762674348
DATAFLOW,OECD.ECO.MAD:DSD_EO@DF_EO(1.5),Economic Outlook 119,I,KOR,Korea,ET,Total employment (labour force survey basis),A,Annual,2025,,28769250
DATAFLOW,OECD.ECO.MAD:DSD_EO@DF_EO(1.5),Economic Outlook 119,I,KOR,Korea,ET,Total employment (labour force survey basis),A,Annual,2026,,28974095.8552047
DATAFLOW,OECD.ECO.MAD:DSD_EO@DF_EO(1.5),Economic Outlook 119,I,KOR,Korea,ET,Total employment (labour force survey basis),A,Annual,2027,,29097415.1525657
```

- [ ] **Step 2: 실패하는 테스트 작성** — `tests/test_oecd.py`

```python
from datetime import date
from pathlib import Path
from src.collectors import oecd

FIXTURE = (Path(__file__).parent / "fixtures" / "oecd_eo119_kor.csv").read_text(
    encoding="utf-8"
)
TODAY = date(2026, 8, 29)


def by_key(records):
    return {(r.indicator, r.target_year): r for r in records}


def test_parse_maps_measures_and_rounds():
    got = by_key(oecd.parse(FIXTURE, TODAY))
    assert got[("gdp_growth", 2026)].value == 2.6
    assert got[("gdp_growth", 2027)].value == 1.9
    assert got[("unemp_rate", 2026)].value == 2.8
    assert got[("cpi", 2027)].value == 2.2


def test_parse_derives_emp_change_from_et_levels():
    got = by_key(oecd.parse(FIXTURE, TODAY))
    assert got[("emp_change", 2026)].value == 20.5  # (28974095.855-28769250)/1e4
    assert got[("emp_change", 2027)].value == 12.3
    assert got[("emp_change", 2026)].unit == "만명"


def test_parse_record_fields():
    r = by_key(oecd.parse(FIXTURE, TODAY))[("gdp_growth", 2027)]
    assert r.id == "oecd-2026-08-gdp_growth-2027"
    assert r.report_title == "Economic Outlook 119"
    assert r.org == "OECD"
    assert r.confidence == "verified"
    assert r.published_at == TODAY


def test_parse_covers_current_and_next_year_only():
    years = {r.target_year for r in oecd.parse(FIXTURE, TODAY)}
    assert years == {2026, 2027}
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_oecd.py -v`
Expected: FAIL (ModuleNotFoundError: src.collectors.oecd)

- [ ] **Step 4: 구현** — `src/collectors/oecd.py`

```python
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone

import requests

from ..models import ForecastRecord, INDICATOR_META, make_id

KST = timezone(timedelta(hours=9))

DATA_URL = (
    "https://sdmx.oecd.org/public/rest/data/OECD.ECO.MAD,DSD_EO@DF_EO,/"
    "KOR.GDPV_ANNPCT+UNR+CPI_YTYPCT+ET.A"
    "?startPeriod={start}&endPeriod={end}&format=csvfilewithlabels"
)
LANDING_URL = "https://www.oecd.org/en/topics/economic-outlook.html"

MEASURE_TO_INDICATOR = {
    "GDPV_ANNPCT": "gdp_growth",
    "UNR": "unemp_rate",
    "CPI_YTYPCT": "cpi",
}


def _data_url(today: date) -> str:
    # ET 차분에 전년(today.year-1) 값이 필요해 start를 1년 앞당긴다
    return DATA_URL.format(start=today.year - 1, end=today.year + 1)


def fetch_raw(today: date) -> str:
    resp = requests.get(_data_url(today), timeout=60)
    resp.raise_for_status()
    return resp.text


def parse(raw_csv: str, today: date) -> list[ForecastRecord]:
    rows = list(csv.DictReader(io.StringIO(raw_csv)))
    report_title = rows[0]["STRUCTURE_NAME"] if rows else "OECD Economic Outlook"
    values: dict[tuple[str, int], float] = {}
    for row in rows:
        if row["REF_AREA"] != "KOR" or row["FREQ"] != "A":
            continue
        values[(row["MEASURE"], int(row["TIME_PERIOD"]))] = float(row["OBS_VALUE"])

    target_years = [today.year, today.year + 1]
    records: list[ForecastRecord] = []
    for (measure, year), val in values.items():
        indicator = MEASURE_TO_INDICATOR.get(measure)
        if indicator is None or year not in target_years:
            continue
        records.append(_record(indicator, val, year, report_title, today))
    # 취업자 증감(만명) = ET(t) − ET(t−1)
    for year in target_years:
        cur = values.get(("ET", year))
        prev = values.get(("ET", year - 1))
        if cur is not None and prev is not None:
            records.append(
                _record("emp_change", (cur - prev) / 10000, year, report_title, today)
            )
    return records


def _record(indicator: str, value: float, year: int,
            report_title: str, today: date) -> ForecastRecord:
    meta = INDICATOR_META[indicator]
    return ForecastRecord(
        id=make_id("OECD", today, indicator, year),
        org="OECD",
        org_name_ko="OECD",
        report_title=report_title,
        published_at=today,
        target_year=year,
        indicator=indicator,
        value=round(value, meta["decimals"]),
        unit=meta["unit"],
        source_url=_data_url(today),
        landing_url=LANDING_URL,
        confidence="verified",
        collected_at=datetime.now(KST),
    )


def collect(today: date) -> list[ForecastRecord]:
    return parse(fetch_raw(today), today)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/test_oecd.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: 커밋**

```bash
git add src/collectors/oecd.py tests/test_oecd.py tests/fixtures/oecd_eo119_kor.csv
git commit -m "feat: OECD Economic Outlook 수집기 (성장률·실업률·물가·취업자증감)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: IMF 수집기 (`collectors/imf.py`)

**Files:**
- Create: `src/collectors/imf.py`
- Test: `tests/test_imf.py`

**Interfaces:**
- Consumes: `ForecastRecord`, `make_id`, `INDICATOR_META` (Task 2)
- Produces:
  - `fetch_raw(imf_code: str) -> dict` (네트워크 — curl_cffi 사용, 일반 requests는 403)
  - `parse(imf_code: str, payload: dict, today: date) -> list[ForecastRecord]` (순수 함수)
  - `collect(today: date) -> list[ForecastRecord]`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_imf.py`

```python
from datetime import date
from src.collectors import imf

TODAY = date(2026, 8, 29)

PAYLOAD = {
    "values": {
        "NGDP_RPCH": {
            "KOR": {"2024": 2.0, "2025": 0.9, "2026": 1.8, "2027": 2.1, "2028": 2.2}
        }
    }
}


def test_parse_picks_current_and_next_year():
    records = imf.parse("NGDP_RPCH", PAYLOAD, TODAY)
    got = {r.target_year: r for r in records}
    assert set(got) == {2026, 2027}
    assert got[2026].value == 1.8
    assert got[2027].value == 2.1


def test_parse_record_fields():
    r = imf.parse("NGDP_RPCH", PAYLOAD, TODAY)[0]
    assert r.org == "IMF"
    assert r.indicator == "gdp_growth"
    assert r.id.startswith("imf-2026-08-gdp_growth-")
    assert r.confidence == "verified"
    assert r.unit == "%"


def test_parse_missing_years_returns_partial():
    payload = {"values": {"LUR": {"KOR": {"2026": 3.1}}}}
    records = imf.parse("LUR", payload, TODAY)
    assert len(records) == 1
    assert records[0].indicator == "unemp_rate"
    assert records[0].target_year == 2026


def test_parse_empty_payload_returns_nothing():
    assert imf.parse("PCPIPCH", {"values": {}}, TODAY) == []
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_imf.py -v`
Expected: FAIL (ModuleNotFoundError: src.collectors.imf)

- [ ] **Step 3: 구현** — `src/collectors/imf.py`

```python
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from curl_cffi import requests as cf_requests

from ..models import ForecastRecord, INDICATOR_META, make_id

KST = timezone(timedelta(hours=9))

API_BASE = "https://www.imf.org/external/datamapper/api/v1"
LANDING_URL = "https://www.imf.org/external/datamapper/profile/KOR"

# IMF DataMapper 코드 → 내부 지표코드
IMF_CODE_TO_INDICATOR = {
    "NGDP_RPCH": "gdp_growth",
    "PCPIPCH": "cpi",
    "LUR": "unemp_rate",
}


def fetch_raw(imf_code: str) -> dict:
    # www.imf.org는 Akamai가 일반 HTTP 클라이언트를 403 차단하므로
    # 브라우저 TLS 핑거프린트로 위장해야 한다
    resp = cf_requests.get(
        f"{API_BASE}/{imf_code}/KOR", impersonate="chrome", timeout=60
    )
    resp.raise_for_status()
    return resp.json()


def parse(imf_code: str, payload: dict, today: date) -> list[ForecastRecord]:
    indicator = IMF_CODE_TO_INDICATOR[imf_code]
    meta = INDICATOR_META[indicator]
    series = payload.get("values", {}).get(imf_code, {}).get("KOR", {})
    records: list[ForecastRecord] = []
    for year in (today.year, today.year + 1):
        val = series.get(str(year))
        if val is None:
            continue
        records.append(ForecastRecord(
            id=make_id("IMF", today, indicator, year),
            org="IMF",
            org_name_ko="IMF",
            report_title=f"IMF WEO ({today:%Y.%m} 조회 기준)",
            published_at=today,
            target_year=year,
            indicator=indicator,
            value=round(float(val), meta["decimals"]),
            unit=meta["unit"],
            source_url=f"{API_BASE}/{imf_code}/KOR",
            landing_url=LANDING_URL,
            confidence="verified",
            collected_at=datetime.now(KST),
        ))
    return records


def collect(today: date) -> list[ForecastRecord]:
    records: list[ForecastRecord] = []
    for code in IMF_CODE_TO_INDICATOR:
        records.extend(parse(code, fetch_raw(code), today))
    return records
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/test_imf.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add src/collectors/imf.py tests/test_imf.py
git commit -m "feat: IMF WEO 수집기 (curl_cffi로 Akamai 차단 우회)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: 오케스트레이터 (`collect.py`)

**Files:**
- Create: `src/collect.py`
- Test: `tests/test_collect.py`

**Interfaces:**
- Consumes: `store.load_forecasts/save_forecasts/merge/latest_record` (Task 3), `oecd.collect`/`imf.collect` (Task 4·5)
- Produces:
  - `main(data_dir: Path = DATA_DIR, collectors: dict[str, Callable[[date], list[ForecastRecord]]] = COLLECTORS) -> int` — 항상 0 반환(부분 실패는 last_run.json에 기록)
  - `drop_unchanged(existing, candidates) -> list[ForecastRecord]` — 저장된 최신값과 동일한 후보 제거 (= 회차 변화 감지)
  - `data/last_run.json` 형식: `{"run_at": iso, "collectors": {이름: {"ok": bool, "fetched": int, "added": int}}, "conflicts": [str], "errors": [str]}`

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_collect.py`

```python
import json
from datetime import date, datetime
from src.models import ForecastRecord, make_id
from src import collect, store


def fake_record(value: float, pub: date) -> ForecastRecord:
    return ForecastRecord(
        id=make_id("OECD", pub, "gdp_growth", 2027), org="OECD", org_name_ko="OECD",
        report_title="test", published_at=pub, target_year=2027,
        indicator="gdp_growth", value=value, unit="%",
        source_url="https://example.com/a", landing_url="https://example.com",
        confidence="verified", collected_at=datetime(2026, 8, 29, 16, 0),
    )


def test_main_saves_new_records_and_last_run(tmp_path):
    collectors = {"fake": lambda today: [fake_record(2.0, today)]}
    rc = collect.main(data_dir=tmp_path, collectors=collectors)
    assert rc == 0
    saved = store.load_forecasts(tmp_path / "forecasts.json")
    assert len(saved) == 1
    summary = json.loads((tmp_path / "last_run.json").read_text(encoding="utf-8"))
    assert summary["collectors"]["fake"]["ok"] is True
    assert summary["collectors"]["fake"]["added"] == 1


def test_main_skips_unchanged_values(tmp_path):
    collectors = {"fake": lambda today: [fake_record(2.0, today)]}
    collect.main(data_dir=tmp_path, collectors=collectors)
    collect.main(data_dir=tmp_path, collectors=collectors)  # 같은 값 재수집
    saved = store.load_forecasts(tmp_path / "forecasts.json")
    assert len(saved) == 1  # 값이 안 바뀌었으므로 신규 레코드 없음


def test_main_records_collector_failure_and_continues(tmp_path):
    def boom(today):
        raise RuntimeError("site down")

    collectors = {
        "bad": boom,
        "good": lambda today: [fake_record(2.0, today)],
    }
    rc = collect.main(data_dir=tmp_path, collectors=collectors)
    assert rc == 0  # 부분 실패해도 나머지는 저장
    saved = store.load_forecasts(tmp_path / "forecasts.json")
    assert len(saved) == 1
    summary = json.loads((tmp_path / "last_run.json").read_text(encoding="utf-8"))
    assert summary["collectors"]["bad"]["ok"] is False
    assert len(summary["errors"]) == 1
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python -m pytest tests/test_collect.py -v`
Expected: FAIL (ModuleNotFoundError: src.collect)

- [ ] **Step 3: 구현** — `src/collect.py`

```python
from __future__ import annotations

import json
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import store
from .collectors import imf, oecd
from .models import ForecastRecord

KST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

COLLECTORS: dict[str, Callable[[date], list[ForecastRecord]]] = {
    "oecd": oecd.collect,
    "imf": imf.collect,
}


def drop_unchanged(existing: list[ForecastRecord],
                   candidates: list[ForecastRecord]) -> list[ForecastRecord]:
    fresh = []
    for cand in candidates:
        latest = store.latest_record(
            existing, cand.org, cand.indicator, cand.target_year, cand.target_period
        )
        if latest is not None and latest.value == cand.value:
            continue
        fresh.append(cand)
    return fresh


def main(data_dir: Path = DATA_DIR,
         collectors: dict[str, Callable[[date], list[ForecastRecord]]] = COLLECTORS,
         ) -> int:
    forecasts_path = data_dir / "forecasts.json"
    last_run_path = data_dir / "last_run.json"
    today = datetime.now(KST).date()

    existing = store.load_forecasts(forecasts_path)
    merged = existing
    summary = {
        "run_at": datetime.now(KST).isoformat(),
        "collectors": {},
        "conflicts": [],
        "errors": [],
    }

    for name, collect_fn in collectors.items():
        try:
            candidates = collect_fn(today)
            fresh = drop_unchanged(merged, candidates)
            result = store.merge(merged, fresh)
            merged = result.records
            summary["conflicts"].extend(result.conflicts)
            summary["collectors"][name] = {
                "ok": True, "fetched": len(candidates), "added": len(result.added),
            }
        except Exception:
            summary["collectors"][name] = {"ok": False, "fetched": 0, "added": 0}
            summary["errors"].append(f"{name}: {traceback.format_exc(limit=3)}")

    if len(merged) != len(existing):
        store.save_forecasts(forecasts_path, merged)
    last_run_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary["collectors"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 테스트 통과 확인 (전체 스위트)**

Run: `python -m pytest -v`
Expected: PASS (전체 통과 — metadata 2, models 5, store 6, oecd 4, imf 4, collect 3)

- [ ] **Step 5: 커밋**

```bash
git add src/collect.py tests/test_collect.py
git commit -m "feat: 수집 오케스트레이터 (변화 감지, 부분 실패 허용, last_run 기록)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: GitHub Actions 워크플로 + README

**Files:**
- Create: `.github/workflows/collect.yml`, `README.md`

**Interfaces:**
- Consumes: `python -m src.collect` CLI (Task 6)
- Produces: 매일 16:00 KST 자동 실행 워크플로 (GitHub에 push 후 활성화됨)

- [ ] **Step 1: 워크플로 작성** — `.github/workflows/collect.yml`

```yaml
name: collect

on:
  schedule:
    - cron: "0 7 * * *" # 07:00 UTC = 16:00 KST
  workflow_dispatch:

permissions:
  contents: write

jobs:
  collect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python -m pytest -q
      - run: python -m src.collect
      - name: Commit data
        run: |
          git config user.name "forecast-bot"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/
          git diff --cached --quiet || git commit -m "data: daily collect $(date -u +%F)"
          git push
```

- [ ] **Step 2: README 작성** — `README.md`

```markdown
# 고용전망 아카이브

국내외 주요 기관의 고용·성장·물가 전망치를 모아 발표 회차별 수정 이력과 함께
조회하는 비공식 개인 아카이브. 기획: `고용전망_아카이브_기획서.md`

> 본 서비스는 개인이 제작한 비공식 참고자료이며, 각 기관 원문이 정본입니다.

## 구조

- `data/forecasts.json` — 전망치 레코드 (스키마: `src/models.py`)
- `data/orgs.json`, `data/indicators.json` — 기관·지표 메타
- `src/collect.py` — 수집 오케스트레이터. 저장된 최신값과 다를 때만 신규 레코드 추가
- `src/collectors/` — 기관별 수집기 (현재 IMF·OECD API)
- `.github/workflows/collect.yml` — 매일 16:00 KST 자동 수집

## 실행

```bash
pip install -r requirements.txt
python -m pytest        # 테스트 (네트워크 불필요)
python -m src.collect   # 실제 수집 1회
```
```

- [ ] **Step 3: 워크플로 문법 검증**

Run: `python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/collect.yml').read_text(encoding='utf-8')); print('yaml ok')"`
(yaml 모듈이 없으면 `pip install pyyaml` 후 재실행. requirements.txt에는 추가하지 않는다 — 검증 전용)
Expected: `yaml ok`

- [ ] **Step 4: 커밋**

```bash
git add .github/workflows/collect.yml README.md
git commit -m "ci: 매일 16시 KST 자동 수집 워크플로 + README

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: 라이브 스모크 테스트 (실데이터 첫 수집)

**Files:**
- Create: `data/forecasts.json`, `data/last_run.json` (실행 산출물)

**Interfaces:**
- Consumes: 전체 파이프라인

- [ ] **Step 1: 실제 수집 실행**

Run: `python -m src.collect`
Expected: 표준출력에 `{"oecd": {"ok": true, "fetched": 8, "added": 8}, "imf": {"ok": true, "fetched": 6, "added": 6}}` 형태 요약. (fetched 수는 API 데이터 가용성에 따라 ±)

- [ ] **Step 2: 산출물 검수 (사람 눈으로)**

`data/forecasts.json`을 열어 확인:
- OECD 레코드: gdp_growth 2026≈2.6 / 2027≈1.9, emp_change 2026≈20.5만명 (EO119 실측 기준)
- IMF 레코드: gdp_growth·cpi·unemp_rate × 2026·2027
- 모든 레코드 `confidence: "verified"`, `prev_value: null`(최초 수집이므로)
- `data/last_run.json`의 `errors`가 빈 배열

IMF가 403으로 실패하면: `last_run.json`에 오류가 기록되고 OECD만 저장되는 것이 정상 동작. curl_cffi 버전을 올리고(`pip install -U curl_cffi`) 재실행 후, 그래도 실패하면 실패 상태 그대로 커밋하고 이슈로 남긴다 (무음 통과 금지 원칙).

- [ ] **Step 3: 재실행 멱등성 확인**

Run: `python -m src.collect`
Expected: 두 번째 실행에서 `added: 0` (값 변화 없음 → 신규 레코드 없음), `forecasts.json` 변화 없음

- [ ] **Step 4: 커밋**

```bash
git add data/forecasts.json data/last_run.json
git commit -m "data: 최초 수집 (IMF WEO + OECD EO119, 한국 2026·2027 전망)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Phase 1 이후 (이 플랜 범위 밖)

- GitHub 저장소 생성·push·Pages 설정 — 사용자 계정 작업 필요
- Phase 2: PWA 화면 (별도 플랜)
- OECD 회차별 아카이브 dataflow(DF_EO_114~118)로 과거 이력 소급 — Phase 5에서 활용 가능 (수동 소급을 크게 줄여줌)
- IMF 발표월 정밀 판별(4·10월 본편, 1·7월 Update) — 현재는 조회 시점 기준 report_title로 충분
