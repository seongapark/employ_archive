# 고용동향 D단계 구현 플랜 — 화면 3개와 증감 비교 시트

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 고용동향 도메인에 총괄·단면별·출처비교 세 화면과 증감 비교 시트를 만들고, 그 화면이 요구하는 성별·연령별 데이터를 수집기에 추가한다.

**Architecture:** 전망 도메인과 같은 구조다 — 순수 함수(`data.js`·`chart.js`)와 렌더(`screens/*.js`)를 나누고, 순수 함수만 `node:test` 로 DOM 없이 검증한다. 시트는 화면이 아니라 셸(`app.js`+`sheet.js`)이 소유해 세그먼트를 옮겨도 살아 있다. 파이썬 쪽은 기존 수집기에 시트·표를 더할 뿐 산업 경로를 건드리지 않는다.

**Tech Stack:** 바닐라 ES 모듈 + 인라인 SVG(차트 라이브러리 없음), Python 3.14 + pydantic, `node:test`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-31-고용동향-화면-design.md`
(상위: `docs/superpowers/specs/2026-08-29-고용데이터아카이브-플랫폼-design.md` 7.5·7.6)

## Global Constraints

- **단위는 만명 소수 첫째자리.** 원자료는 천명이고 `yoy` 는 비율이 아니라 천명 단위 증감량이다. 화면 표기는 수준 `2,913.6만명`, 증감 `+10.8만명`.
- **집계 열·중첩 열을 레코드로 만들지 않는다.** 경활 `광공업`·`사회간접자본및기타서비스업`·`15∼19`·`20∼29`·`65/70/75세이상`, 고용행정 `서비스업`·`기타*`. 합 불변식 테스트가 지킨다.
- **값이 없는 칸은 네 상태로 구분한다:** `notProvided`(`―`) / `unpublished`(`미발표`) / `noDelta`(`증감없음`) / `value`. 판정은 이 순서로, `data.js` 한 곳에서만.
- **출처 색은 고정이며 순환하지 않는다:** `eaps #2a78d6` · `est #eb6834` · `ei #1baf7a`.
- **`#1baf7a` 대비 미달(2.82:1) 완화 조치는 의무다** — 모든 막대에 값 직접 라벨, `표로 보기` 토글. 제거 불가.
- **허브 코드(`hub/`)와 `tools/build.py` 를 고치지 않는다.** `domains/employment/app/` 이 생기는 것만으로 버튼이 켜져야 한다.
- **`core/` 에 고용동향 것을 올리지 않는다.** 3색 팔레트와 시트는 이 도메인 소유다.
- **판별력 왕복 확인:** 각 태스크에서 테스트를 통과시킨 뒤, 구현을 일부러 한 줄 망가뜨려 그 테스트가 **실제로 실패하는지** 확인하고 되돌린다. 확인 없이 다음 태스크로 가지 않는다.
- **커밋 범위:** `git add -A` 를 쓰지 않는다. 태스크에 적힌 경로만 스테이징한다.

---

## File Structure

| 파일 | 책임 |
|---|---|
| `domains/employment/pipeline/models.py` (수정) | `Breakdown` 에 `sex`·`age` 추가, `make_id` 일반화 |
| `domains/employment/pipeline/collectors/eaps.py` (수정) | 성 2 + 연령 5 시트 파싱 |
| `domains/employment/pipeline/collectors/ei.py` (수정) | 성 2 + 연령 5 표 파싱 |
| `domains/employment/data/segments.json` (생성) | 성·연령 분류 메타와 출처별 공표 여부 |
| `domains/employment/app/index.html` (생성) | 셸 — 헤더·세그먼트·시트 핸들 |
| `domains/employment/app/js/app.js` (생성) | 라우팅, 기준월 상태, 시트 상태 |
| `domains/employment/app/js/data.js` (생성) | 순수 조회·판정·포맷 |
| `domains/employment/app/js/chart.js` (생성) | 순수 SVG 문자열 생성 |
| `domains/employment/app/js/sheet.js` (생성) | 시트 렌더와 열고닫기 |
| `domains/employment/app/js/screens/overview.js` (생성) | 총괄 |
| `domains/employment/app/js/screens/breakdown.js` (생성) | 단면별 |
| `domains/employment/app/js/screens/sources.js` (생성) | 출처비교 |
| `domains/employment/app/css/app.css` (생성) | 이 앱 전용 스타일·3색 토큰 |
| `domains/employment/tests/web/data.test.mjs` (생성) | `data.js` 검증 |
| `domains/employment/tests/web/chart.test.mjs` (생성) | `chart.js` 검증 |

---

### Task 1: 스키마에 sex·age 단면을 연다

지금 `Breakdown` 은 `total`·`industry` 뿐이라 성·연령 레코드를 만들 수 없다. 먼저 열어야 수집기 두 개가 따라온다.

**Files:**
- Modify: `domains/employment/pipeline/models.py:21` (`Breakdown`), `:25-27` (`make_id`), `:60-66` (`check_category`)
- Test: `domains/employment/tests/test_models.py`

**Interfaces:**
- Consumes: 없음
- Produces: `Breakdown = Literal["total", "industry", "sex", "age"]`,
  `make_id(source: str, period: str, breakdown: str, category: str | None) -> str` —
  `total` 이면 `{source}-{period}-headcount-total`, 아니면 `{source}-{period}-headcount-{breakdown}-{category}`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`domains/employment/tests/test_models.py` 끝에 붙인다.

```python
def test_make_id_carries_category_for_every_breakdown_but_total():
    assert make_id("eaps", "2026-07", "total", None) == "eaps-2026-07-headcount-total"
    assert make_id("eaps", "2026-07", "industry", "A") == "eaps-2026-07-headcount-industry-A"
    assert make_id("eaps", "2026-07", "sex", "M") == "eaps-2026-07-headcount-sex-M"
    assert make_id("ei", "2026-07", "age", "60+") == "ei-2026-07-headcount-age-60+"


def test_sex_and_age_records_need_a_category():
    def build(**over):
        base = dict(
            id="x", source="eaps", breakdown="sex", category="M", period="2026-07",
            value=16079.5, released_at=date(2026, 8, 12),
            release_url="https://mods.go.kr/x", collected_at=datetime(2026, 8, 30, 9, 0),
        )
        return SeriesRecord(**{**base, **over})

    build()                       # 정상
    build(breakdown="age", category="15-29")
    with pytest.raises(ValidationError):
        build(category=None)
    with pytest.raises(ValidationError):
        build(breakdown="age", category=None)
```

파일 상단 import 에 `from pydantic import ValidationError` 와 `from domains.employment.pipeline.models import SeriesRecord, make_id` 가 이미 있는지 확인하고, 없으면 추가한다.

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest domains/employment/tests/test_models.py -q`
Expected: FAIL — `sex` 는 아직 `Breakdown` 에 없어 `ValidationError` 가 나고, `make_id` 는 `sex` 에 category 를 안 붙인다.

- [ ] **Step 3: 최소 구현**

`models.py` 를 이렇게 고친다.

```python
Breakdown = Literal["total", "industry", "sex", "age"]


def make_id(source: str, period: str, breakdown: str, category: Optional[str]) -> str:
    tail = "" if breakdown == "total" else f"-{category}"
    return f"{source}-{period}-headcount-{breakdown}{tail}"
```

```python
    @model_validator(mode="after")
    def check_category(self):
        if self.breakdown == "total" and self.category:
            raise ValueError("breakdown=total 은 category 를 가질 수 없다")
        if self.breakdown != "total" and not self.category:
            raise ValueError(f"breakdown={self.breakdown} 는 category 가 필요하다")
        return self
```

- [ ] **Step 4: 통과와 회귀를 확인한다**

Run: `python -m pytest -q`
Expected: PASS — 249 passed 이상. 기존 산업 id 형식이 그대로여야 한다(위 테스트 두 번째 줄이 그것을 잡는다).

- [ ] **Step 5: 판별력 왕복 확인**

`make_id` 의 `tail` 을 `""` 로 고정해 보고 `python -m pytest domains/employment/tests/test_models.py -q` 가 실패하는지 본다. 실패하면 되돌린다. 실패하지 않으면 테스트가 판별력이 없는 것이므로 테스트를 고친다.

- [ ] **Step 6: 커밋**

```bash
git add domains/employment/pipeline/models.py domains/employment/tests/test_models.py
git commit -m "feat(employment): 스키마에 성별·연령별 단면을 연다"
```

---

### Task 2: 경활 성·연령 수집

경활 보도자료 xlsx 는 시트가 42개이고 그중 `1.남자`·`1.여자`·`2.연령계층`(+각 증감)이 산업 시트와 같은 격자다. 픽스처에 이미 들어 있다.

**Files:**
- Modify: `domains/employment/pipeline/collectors/eaps.py`
- Test: `domains/employment/tests/test_eaps.py`

**Interfaces:**
- Consumes: Task 1 의 `make_id`, `Breakdown`
- Produces: `eaps.parse(...)` 가 `breakdown="sex"`(`M`,`F`)와 `breakdown="age"`(`15-29`,`30-39`,`40-49`,`50-59`,`60+`) 레코드를 함께 낸다. `eaps.SEX_SHEETS`, `eaps.AGE_TOKENS` 상수 공개.

**주의 — 왜 접두가 아니라 부분일치인가:** 수준 시트의 라벨은 `15∼29취업자$15-29세$계`, 증감 시트는 `15∼29증감{취업자,전년동기간비}$계$15-29세` 다. 앞부분의 `∼` 는 U+223C 라 소스에 적기 취약하다. 두 라벨 모두 ASCII 하이픈이 든 `15-29세` 를 포함하므로 그것을 쓴다. `60세이상` 은 `65/70/75세이상` 과 겹치지 않는다(실측 확인).

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`domains/employment/tests/test_eaps.py` 끝에 붙인다. `records` 픽스처는 이 파일에 이미 있다.

```python
def test_collects_sex_and_age_for_the_latest_month(records):
    latest = max(r.period for r in records)
    sex = {r.category: r for r in records if r.period == latest and r.breakdown == "sex"}
    age = {r.category: r for r in records if r.period == latest and r.breakdown == "age"}
    assert set(sex) == {"M", "F"}
    assert set(age) == {"15-29", "30-39", "40-49", "50-59", "60+"}
    assert sex["M"].value == 16079.5      # 2026-07 남자 취업자(천명)
    assert sex["M"].yoy == 47.9


def test_sex_and_age_sum_to_the_total(records):
    """부분집합 열(15∼19·20∼29·65/70/75세이상)을 넣으면 합이 깨진다."""
    for period in ("2026-07", "2025-12"):
        total = next(r for r in records if r.period == period and r.breakdown == "total")
        for breakdown in ("sex", "age"):
            parts = [r for r in records if r.period == period and r.breakdown == breakdown]
            assert parts, f"{period} {breakdown} 레코드가 없다"
            assert round(sum(p.value for p in parts), 1) == round(total.value, 1)


def test_coverage_guard_fails_when_an_age_band_is_missing(records):
    kept = [r for r in records if not (r.breakdown == "age" and r.category == "60+")]
    with pytest.raises(ValueError, match="연령"):
        eaps.check_coverage(kept)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest domains/employment/tests/test_eaps.py -q`
Expected: FAIL — 성·연령 레코드가 아직 없다.

- [ ] **Step 3: 최소 구현**

`eaps.py` 의 `LEVEL_SHEETS`/`DELTA_SHEETS` 아래에 상수를 더한다.

```python
# 성별은 시트가 갈려 있고 취업자 열 하나만 쓴다.
SEX_SHEETS: dict[str, tuple[str, str]] = {
    "M": ("1.남자", "1.남자증감"),
    "F": ("1.여자", "1.여자증감"),
}
SEX_COLUMN = "취업자"

AGE_LEVEL_SHEET = "2.연령계층"
AGE_DELTA_SHEET = "2.연령계층증감"
# 라벨 부분일치용 토큰 → 분류 코드. 수준 시트와 증감 시트의 라벨 형태가
# 다르지만(`취업자$15-29세$계` vs `증감{…}$계$15-29세`) 둘 다 이 토큰을 품는다.
# 15∼19·20∼29·65/70/75세이상은 각각 15∼29·60세이상의 부분집합이라 뺀다 —
# 넣으면 합 불변식이 깨지고 화면에서 이중 계상된다.
AGE_TOKENS: dict[str, str] = {
    "15-29세": "15-29", "30-39세": "30-39", "40-49세": "40-49",
    "50-59세": "50-59", "60세이상": "60+",
}
```

`_collect_sheets` 아래에 헬퍼를 더한다.

```python
def _by_token(data: bytes, sheet: str) -> dict[str, dict[str, float]]:
    """{기간: {분류코드: 값}} — 라벨에 AGE_TOKENS 가 들어간 열만."""
    rows = xlsx.read_sheet(data, sheet)
    labels = _header_labels(rows)
    picked = {col: code for col, label in labels.items()
              for token, code in AGE_TOKENS.items() if token in label}
    out: dict[str, dict[str, float]] = {}
    for period, row in month_rows(rows):
        bucket = out.setdefault(period, {})
        for col, code in picked.items():
            if col >= len(row):
                continue
            raw = (row[col] or "").replace(",", "").strip()
            if not raw:
                continue
            try:
                bucket[code] = round(float(raw), 1)
            except ValueError:
                continue
    return out
```

`parse()` 의 산업 루프 뒤에 성·연령 루프를 더한다(기존 코드는 건드리지 않는다).

```python
    def emit(breakdown: str, code: str, period: str,
             value: float, yoy: float | None) -> None:
        records.append(SeriesRecord(
            id=make_id("eaps", period, breakdown, code), source="eaps",
            breakdown=breakdown, category=code, period=period,
            value=value, yoy=yoy,
            released_at=released_at, release_url=release_url,
            attachments=attachments, collected_at=collected_at,
        ))

    for code, (level_sheet, delta_sheet) in SEX_SHEETS.items():
        levels_s = _collect_sheets(data, (level_sheet,))
        deltas_s = _collect_sheets(data, (delta_sheet,))
        for period, values in levels_s.items():
            if SEX_COLUMN not in values:
                continue
            emit("sex", code, period, values[SEX_COLUMN],
                 deltas_s.get(period, {}).get(SEX_COLUMN))

    age_levels = _by_token(data, AGE_LEVEL_SHEET)
    age_deltas = _by_token(data, AGE_DELTA_SHEET)
    for period, values in age_levels.items():
        for code, value in values.items():
            emit("age", code, period, value, age_deltas.get(period, {}).get(code))
```

`check_coverage` 에 성·연령 검사를 더한다.

```python
    for breakdown, expected in (("sex", set(SEX_SHEETS)),
                                ("age", set(AGE_TOKENS.values()))):
        got = {r.category for r in records
               if r.period == latest and r.breakdown == breakdown}
        missing = expected - got
        if missing:
            name = "성별" if breakdown == "sex" else "연령"
            raise ValueError(f"{latest} 에 빠진 {name} 분류: {sorted(missing)}")
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python -m pytest domains/employment/tests/test_eaps.py -q`
Expected: PASS

- [ ] **Step 5: 판별력 왕복 확인**

`AGE_TOKENS` 에 `"15-19세": "15-19"` 를 임시로 넣고 `python -m pytest domains/employment/tests/test_eaps.py -q` 를 돌린다. 합 불변식 테스트가 **실패해야 한다**. 확인 후 되돌린다.

- [ ] **Step 6: 커밋**

```bash
git add domains/employment/pipeline/collectors/eaps.py domains/employment/tests/test_eaps.py
git commit -m "feat(employment): 경활 성별·연령별 취업자 수집"
```

---

### Task 3: 고용행정 성·연령 수집

hwpx 통계표에 `전체·남성·여성·29세이하·30대·40대·50대·60세이상` 열의 표가 **셋** 있다 — 수준·증감·증감률이고 헤더가 같다. 증감률을 증감으로 착각하면 값이 100배 작아진다.

**Files:**
- Modify: `domains/employment/pipeline/collectors/ei.py`
- Test: `domains/employment/tests/test_ei.py`

**Interfaces:**
- Consumes: Task 1 의 `make_id`; 같은 파일의 `_flat`, `_num`, `month_rows`, `TOTAL_KEY`
- Produces: `ei.find_demo_tables(tables) -> tuple[list, list]` (수준, 증감), `ei.DEMO_COLUMNS: dict[int, tuple[str, str]]`

**대조점:** 이 문서는 스스로 검증 수단을 갖고 있다. 성·연령 표의 `전체` 열은 산업 표의 `전산업` 과 같은 값이어야 한다(2026-07 수준 15,877 · 증감 277). 증감률 표(1.8)를 집으면 이 대조가 즉시 깨진다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_demo_tables_are_level_and_delta_not_rate(data):
    level, delta = ei.find_demo_tables(hwpx.tables(data))
    assert level[-1][1] == "15,877"
    assert delta[-1][1] == "277"


def test_demo_total_matches_the_industry_total(records):
    latest = max(r.period for r in records)
    total = next(r for r in records if r.period == latest and r.breakdown == "total")
    for breakdown in ("sex", "age"):
        parts = [r for r in records if r.period == latest and r.breakdown == breakdown]
        assert parts, f"{latest} {breakdown} 레코드가 없다"
        assert round(sum(p.value for p in parts), 1) == round(total.value, 1)
        assert round(sum(p.yoy for p in parts), 1) == round(total.yoy, 1)


def test_collects_five_age_bands_and_two_sexes(records):
    latest = max(r.period for r in records)
    sex = {r.category: r for r in records if r.period == latest and r.breakdown == "sex"}
    age = {r.category: r for r in records if r.period == latest and r.breakdown == "age"}
    assert set(sex) == {"M", "F"}
    assert set(age) == {"15-29", "30-39", "40-49", "50-59", "60+"}
    assert sex["F"].value == 7205.0
    assert age["60+"].yoy == 209.0


def test_demo_series_covers_every_month_not_just_the_latest(records):
    periods = {r.period for r in records if r.breakdown == "age"}
    assert "2024-07" in periods and "2026-07" in periods
    assert len(periods) >= 24
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest domains/employment/tests/test_ei.py -q`
Expected: FAIL — `find_demo_tables` 가 없다(`AttributeError`).

- [ ] **Step 3: 최소 구현**

`ei.py` 의 `CONT_COLUMNS` 아래에 더한다.

```python
DEMO_HEADER_KEYS = ("전체", "남성", "여성", "29세이하", "60세이상")
# 열 위치 → (단면, 분류코드). 1번 열(전체)은 산업 표에서 이미 total 로 나오므로 뺀다.
DEMO_COLUMNS: dict[int, tuple[str, str]] = {
    2: ("sex", "M"), 3: ("sex", "F"),
    4: ("age", "15-29"), 5: ("age", "30-39"), 6: ("age", "40-49"),
    7: ("age", "50-59"), 8: ("age", "60+"),
}
DEMO_TOTAL_COLUMN = 1


def find_demo_tables(tables) -> tuple[list, list]:
    """성·연령 통계표의 수준·증감 표. 증감률 표가 같은 헤더로 뒤따른다.

    셋 다 헤더가 같아 순서로만 구분된다. 크기로 뒤바뀜을 잡는다 —
    수준은 만 단위, 증감은 백 단위, 증감률은 한 자릿수다. 증감률을 증감으로
    집으면 값이 100배 작아지는데 조용히 그럴듯해 보인다.
    """
    cand = [i for i, g in enumerate(tables)
            if g and len(g[0]) > 5 and all(k in _flat(g[0]) for k in DEMO_HEADER_KEYS)]
    if len(cand) < 2:
        raise ValueError(f"성·연령 수준·증감 표를 찾지 못했다 (후보 {cand})")
    level, delta = tables[cand[0]], tables[cand[1]]
    lv, dv = _num(level[-1][DEMO_TOTAL_COLUMN]), _num(delta[-1][DEMO_TOTAL_COLUMN])
    if lv is None or lv < 10000:
        raise ValueError(f"성·연령 수준 표의 전체가 이상하다: {lv}")
    if dv is None or abs(dv) >= 1000 or abs(dv) < 10:
        raise ValueError(f"성·연령 증감 표의 전체가 이상하다(증감률을 집었을 수 있다): {dv}")
    return level, delta


def _demo_by_period(table) -> dict[str, dict[tuple[str, str], float]]:
    out: dict[str, dict[tuple[str, str], float]] = {}
    for period, row in month_rows(table):
        bucket = out.setdefault(period, {})
        for col, key in DEMO_COLUMNS.items():
            if col < len(row):
                value = _num(row[col])
                if value is not None:
                    bucket[key] = value
    return out
```

`parse()` 안, 산업 레코드 루프 뒤에 더한다.

```python
    demo_level, demo_delta = find_demo_tables(tables)
    demo_levels = _demo_by_period(demo_level)
    demo_deltas = _demo_by_period(demo_delta)

    # 문서가 스스로 갖는 대조점: 성·연령의 전체는 산업 표의 전산업과 같아야 한다.
    demo_total = sum(v for (bd, _), v in demo_levels.get(latest, {}).items() if bd == "sex")
    if abs(demo_total - levels[latest][TOTAL_KEY]) > 1.0:
        raise ValueError(
            f"성별 합이 전산업과 다르다: {demo_total} vs {levels[latest][TOTAL_KEY]}")

    for period, values in demo_levels.items():
        delta = demo_deltas.get(period, {})
        for (breakdown, code), value in values.items():
            records.append(SeriesRecord(
                id=make_id("ei", period, breakdown, code), source="ei",
                breakdown=breakdown, category=code, period=period,
                value=value, yoy=delta.get((breakdown, code)),
                released_at=released_at, release_url=release_url,
                attachments=attachments, collected_at=collected_at,
            ))
```

`check_coverage` 에 Task 2 와 같은 모양의 검사를 더한다.

```python
    for breakdown, expected in (("sex", {"M", "F"}),
                                ("age", {"15-29", "30-39", "40-49", "50-59", "60+"})):
        got = {r.category for r in records
               if r.period == latest and r.breakdown == breakdown}
        missing = expected - got
        if missing:
            name = "성별" if breakdown == "sex" else "연령"
            raise ValueError(f"{latest} 에 빠진 {name} 분류: {sorted(missing)}")
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python -m pytest domains/employment/tests/test_ei.py -q`
Expected: PASS

- [ ] **Step 5: 판별력 왕복 확인**

`find_demo_tables` 의 반환을 `tables[cand[1]], tables[cand[2]]`(증감·증감률)로 바꿔 본다. `test_demo_tables_are_level_and_delta_not_rate` 와 대조 검증이 **실패해야 한다**. 확인 후 되돌린다.

- [ ] **Step 6: 커밋**

```bash
git add domains/employment/pipeline/collectors/ei.py domains/employment/tests/test_ei.py
git commit -m "feat(employment): 고용행정 성별·연령별 가입자 수집"
```

---

### Task 4: `segments.json` 과 메타 가드

화면이 "사업체노동력조사는 성·연령을 공표하지 않는다"를 알아야 `notProvided` 를 판정할 수 있다. 그 사실을 코드가 아니라 데이터에 적는다.

**Files:**
- Create: `domains/employment/data/segments.json`
- Test: `domains/employment/tests/test_metadata.py` (수정)

**Interfaces:**
- Consumes: 없음
- Produces: `segments.json` — `[{breakdown, name_ko, categories: [{code, name_ko, provided: {eaps, est, ei}}]}]`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`domains/employment/tests/test_metadata.py` 끝에 붙인다.

```python
SEGMENTS = Path(__file__).parent.parent / "data" / "segments.json"


def test_segments_cover_sex_and_age_with_every_source_flagged():
    segments = json.loads(SEGMENTS.read_text(encoding="utf-8"))
    by_breakdown = {s["breakdown"]: s for s in segments}
    assert set(by_breakdown) == {"sex", "age"}
    assert [c["code"] for c in by_breakdown["sex"]["categories"]] == ["M", "F"]
    assert [c["code"] for c in by_breakdown["age"]["categories"]] == [
        "15-29", "30-39", "40-49", "50-59", "60+"]
    for segment in segments:
        for category in segment["categories"]:
            assert set(category["provided"]) == {"eaps", "est", "ei"}
            assert category["provided"]["est"] is False, "사업체노동력조사는 공표하지 않는다"
            assert category["provided"]["eaps"] and category["provided"]["ei"]


def test_segment_codes_match_the_collected_records():
    series = json.loads(SERIES.read_text(encoding="utf-8"))
    segments = json.loads(SEGMENTS.read_text(encoding="utf-8"))
    for segment in segments:
        declared = {c["code"] for c in segment["categories"]}
        collected = {r["category"] for r in series if r["breakdown"] == segment["breakdown"]}
        assert collected <= declared, f"{segment['breakdown']}: 선언되지 않은 분류 {collected - declared}"
```

`SERIES` 상수가 이 파일에 이미 있는지 확인하고, 없으면 `SERIES = Path(__file__).parent.parent / "data" / "series.json"` 를 더한다.

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest domains/employment/tests/test_metadata.py -q`
Expected: FAIL — `segments.json` 이 없다(`FileNotFoundError`).

- [ ] **Step 3: 파일을 만든다**

`domains/employment/data/segments.json`:

```json
[
  {
    "breakdown": "sex",
    "name_ko": "성별",
    "categories": [
      {"code": "M", "name_ko": "남자", "provided": {"eaps": true, "est": false, "ei": true}},
      {"code": "F", "name_ko": "여자", "provided": {"eaps": true, "est": false, "ei": true}}
    ]
  },
  {
    "breakdown": "age",
    "name_ko": "연령별",
    "categories": [
      {"code": "15-29", "name_ko": "29세 이하", "provided": {"eaps": true, "est": false, "ei": true}},
      {"code": "30-39", "name_ko": "30대", "provided": {"eaps": true, "est": false, "ei": true}},
      {"code": "40-49", "name_ko": "40대", "provided": {"eaps": true, "est": false, "ei": true}},
      {"code": "50-59", "name_ko": "50대", "provided": {"eaps": true, "est": false, "ei": true}},
      {"code": "60+", "name_ko": "60세 이상", "provided": {"eaps": true, "est": false, "ei": true}}
    ]
  }
]
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python -m pytest domains/employment/tests/test_metadata.py -q`
Expected: PASS (두 번째 테스트는 series.json 에 성·연령이 아직 없어도 `collected ⊆ declared` 이므로 통과한다. Task 5 이후에 실질 검증이 된다.)

- [ ] **Step 5: 커밋**

```bash
git add domains/employment/data/segments.json domains/employment/tests/test_metadata.py
git commit -m "data(employment): 성·연령 분류 메타 — est 는 공표하지 않음"
```

---

### Task 5: 실제 수집 1회와 적재

수집기가 성·연령을 낼 수 있게 됐으니 실제로 받아 `series.json` 에 채운다. 화면 태스크가 진짜 데이터 위에서 진행되어야 한다.

**Files:**
- Modify: `domains/employment/data/series.json`, `domains/employment/data/last_run.json`

**Interfaces:**
- Consumes: Task 2·3 의 수집기, Task 4 의 메타
- Produces: `series.json` 에 `breakdown` 이 `sex`·`age` 인 레코드

**전제:** `.env` 에 `KOSIS_API_KEY` 가 있어야 한다(`est` 수집용). 없으면 `est` 만 실패하고 나머지는 진행되지만, 이 태스크는 세 수집기가 모두 초록일 때만 완료로 친다.

- [ ] **Step 1: 수집 전 상태를 기록한다**

```bash
python -c "import json,io;s=json.load(io.open('domains/employment/data/series.json',encoding='utf-8'));print(len(s))"
```
현재 레코드 수를 적어 둔다(현재 1,690).

- [ ] **Step 2: 수집을 1회 돌린다**

Run: `python -m domains.employment.pipeline.collect`
Expected: 세 수집기 모두 `"ok": true`. 출력의 `added` 합이 성·연령 레코드 수만큼 늘어야 한다(경활 7분류 × 기간 + 고용행정 7분류 × 기간).

- [ ] **Step 3: 적재 결과를 확인한다**

```bash
python - <<'PY'
import json, io, collections
s = json.load(io.open('domains/employment/data/series.json', encoding='utf-8'))
print('총', len(s))
print(collections.Counter((r['source'], r['breakdown']) for r in s))
latest = max(r['period'] for r in s if r['source'] == 'eaps')
for bd in ('sex', 'age'):
    rows = [r for r in s if r['period'] == latest and r['breakdown'] == bd]
    for src in ('eaps', 'ei'):
        part = [r for r in rows if r['source'] == src]
        total = next(r for r in s if r['period'] == latest and r['source'] == src and r['breakdown'] == 'total')
        print(bd, src, round(sum(p['value'] for p in part), 1), 'vs total', total['value'])
PY
```
Expected: `est` 에는 `sex`·`age` 가 없고, `eaps`·`ei` 는 각 단면 합이 `total` 과 일치한다.

- [ ] **Step 4: 전체 테스트**

Run: `python -m pytest -q`
Expected: PASS. Task 4 의 `test_segment_codes_match_the_collected_records` 가 이제 실질 검증이 된다.

- [ ] **Step 5: 커밋**

```bash
git add domains/employment/data/series.json domains/employment/data/last_run.json
git commit -m "data(employment): 성별·연령별 시계열 적재"
```

---

### Task 6: `data.js` — 기간·포맷·출처 카드

여기부터 웹이다. `data.js` 는 DOM 도 네트워크도 모른다.

**Files:**
- Create: `domains/employment/app/js/data.js`
- Create: `domains/employment/tests/web/data.test.mjs`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `SOURCE_ORDER = ['eaps', 'est', 'ei']`, `SOURCE_COLORS = {eaps:'#2a78d6', est:'#eb6834', ei:'#1baf7a'}`
  - `monthOptions(series) -> {years: number[], monthsByYear: {[year]: number[]}, latest: string}`
  - `overviewCards(series, sources, period) -> [{code, name_ko, headline_ko, coverage, caveat, boardUrl, state, value, yoy, releasedAt, releaseUrl, attachments, fallback}]`
    - `state` 는 `'value'` 또는 `'unpublished'`
    - `fallback` 은 `state==='unpublished'` 일 때 `{period, value, yoy, releasedAt, releaseUrl}`, 아니면 `null`
  - `fmtLevel(cheonMyeong) -> string` (`'2,913.6만명'`), `fmtDelta(cheonMyeong) -> string` (`'+10.8만명'`, 0 이면 `'0.0만명'`), `monthLabel('2026-07') -> '2026.07'`, `esc(text) -> string`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`domains/employment/tests/web/data.test.mjs`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { monthOptions, overviewCards, fmtLevel, fmtDelta, monthLabel, esc } from '../../app/js/data.js';

function rec(over = {}) {
  return {
    id: 'x', source: 'eaps', series: 'headcount', breakdown: 'total', category: null,
    period: '2026-07', value: 29136.1, unit: '천명', yoy: 107.6, status: '잠정',
    released_at: '2026-08-12', release_url: 'https://mods.go.kr/x', attachments: [],
    collected_at: '2026-08-30T20:56:40+09:00', ...over,
  };
}

const SOURCES = [
  { code: 'eaps', name_ko: '경제활동인구조사', headline_ko: '취업자수', coverage: 'c1', caveat: 'v1', board_url: 'https://a' },
  { code: 'est', name_ko: '사업체노동력조사', headline_ko: '종사자수', coverage: 'c2', caveat: 'v2', board_url: 'https://b' },
  { code: 'ei', name_ko: '고용행정통계', headline_ko: '상시가입자수', coverage: 'c3', caveat: 'v3', board_url: 'https://c' },
];

test('monthOptions starts where all three sources have a total', () => {
  const series = [
    rec({ source: 'eaps', period: '2023-07' }), rec({ source: 'ei', period: '2023-07' }),
    rec({ source: 'eaps', period: '2024-06' }), rec({ source: 'ei', period: '2024-06' }),
    rec({ source: 'eaps', period: '2024-07' }), rec({ source: 'ei', period: '2024-07' }),
    rec({ source: 'est', period: '2024-07' }),
    rec({ source: 'eaps', period: '2026-07' }), rec({ source: 'ei', period: '2026-07' }),
  ];
  const opts = monthOptions(series);
  assert.deepEqual(opts.years, [2024, 2025, 2026]);
  assert.deepEqual(opts.monthsByYear[2024], [7, 8, 9, 10, 11, 12]);
  assert.deepEqual(opts.monthsByYear[2026], [1, 2, 3, 4, 5, 6, 7]);
  assert.equal(opts.latest, '2026-07');
});

test('monthOptions ignores non-total records when finding the floor', () => {
  const series = [
    rec({ source: 'eaps', period: '2024-01', breakdown: 'industry', category: 'C' }),
    rec({ source: 'est', period: '2024-01', breakdown: 'industry', category: 'C' }),
    rec({ source: 'ei', period: '2024-01', breakdown: 'industry', category: 'C' }),
    rec({ source: 'eaps', period: '2024-07' }), rec({ source: 'est', period: '2024-07' }),
    rec({ source: 'ei', period: '2024-07' }),
  ];
  assert.deepEqual(monthOptions(series).years, [2024]);
  assert.deepEqual(monthOptions(series).monthsByYear[2024], [7]);
});

test('overviewCards marks a source unpublished and carries its latest month', () => {
  const series = [
    rec({ source: 'eaps', period: '2026-07', value: 29136.1, yoy: 107.6 }),
    rec({ source: 'ei', period: '2026-07', value: 15877.0, yoy: 277.0 }),
    rec({ source: 'est', period: '2026-06', value: 20714.2, yoy: 248.0, released_at: '2026-08-31' }),
  ];
  const cards = overviewCards(series, SOURCES, '2026-07');
  assert.deepEqual(cards.map(c => c.code), ['eaps', 'est', 'ei']);
  const est = cards[1];
  assert.equal(est.state, 'unpublished');
  assert.equal(est.value, null);
  assert.deepEqual(
    { period: est.fallback.period, value: est.fallback.value, yoy: est.fallback.yoy },
    { period: '2026-06', value: 20714.2, yoy: 248.0 },
  );
  assert.equal(cards[0].state, 'value');
  assert.equal(cards[0].fallback, null);
});

test('formatters convert 천명 to 만명', () => {
  assert.equal(fmtLevel(29136.1), '2,913.6만명');
  assert.equal(fmtDelta(107.6), '+10.8만명');
  assert.equal(fmtDelta(-57.2), '-5.7만명');
  assert.equal(fmtDelta(0), '0.0만명');
  assert.equal(monthLabel('2026-07'), '2026.07');
  assert.equal(esc('<b>&'), '&lt;b&gt;&amp;');
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `node --test "domains/employment/tests/web/data.test.mjs"`
Expected: FAIL — `data.js` 가 없다.

- [ ] **Step 3: 최소 구현**

`domains/employment/app/js/data.js`:

```javascript
// 고용동향 순수 로직. DOM 도 네트워크도 모른다.
// 원자료 단위는 천명이고 yoy 는 비율이 아니라 천명 단위 증감량이다.

export const SOURCE_ORDER = ['eaps', 'est', 'ei'];

// 색은 출처 정체성만 나른다. 부호는 0선 기준 막대 방향이 말한다.
// 고정 배정이며 순환하지 않는다 — 출처가 빠져도 남은 색은 그대로다.
export const SOURCE_COLORS = { eaps: '#2a78d6', est: '#eb6834', ei: '#1baf7a' };

export function esc(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

export function monthLabel(period) {
  return `${period.slice(0, 4)}.${period.slice(5, 7)}`;
}

function toMan(cheon) {
  return Math.round(cheon) / 10;
}

export function fmtLevel(cheon) {
  const man = toMan(cheon);
  return `${man.toLocaleString('ko-KR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}만명`;
}

export function fmtDelta(cheon) {
  const man = toMan(cheon);
  const sign = man > 0 ? '+' : man < 0 ? '-' : '';
  return `${sign}${Math.abs(man).toFixed(1)}만명`;
}

// 기준월 하한은 세 출처의 total 이 모두 있는 첫 달이다. 단면으로 재면
// 성·연령에는 사업체노동력조사가 아예 없어 하한이 단면마다 달라진다.
export function monthOptions(series) {
  const totals = series.filter(r => r.breakdown === 'total');
  const bySources = new Map();
  for (const r of totals) {
    if (!bySources.has(r.period)) bySources.set(r.period, new Set());
    bySources.get(r.period).add(r.source);
  }
  const complete = Array.from(bySources.entries())
    .filter(([, sources]) => SOURCE_ORDER.every(s => sources.has(s)))
    .map(([period]) => period)
    .sort();
  const floor = complete[0];
  const periods = Array.from(bySources.keys()).filter(p => floor && p >= floor).sort();

  const monthsByYear = {};
  for (const p of periods) {
    const year = Number(p.slice(0, 4));
    (monthsByYear[year] ||= []).push(Number(p.slice(5, 7)));
  }
  for (const year of Object.keys(monthsByYear)) {
    monthsByYear[year] = Array.from(new Set(monthsByYear[year])).sort((a, b) => a - b);
  }
  return {
    years: Object.keys(monthsByYear).map(Number).sort((a, b) => a - b),
    monthsByYear,
    latest: periods.length ? periods[periods.length - 1] : null,
  };
}

export function overviewCards(series, sources, period) {
  const byCode = new Map(sources.map(s => [s.code, s]));
  return SOURCE_ORDER.filter(code => byCode.has(code)).map(code => {
    const meta = byCode.get(code);
    const totals = series.filter(r => r.source === code && r.breakdown === 'total');
    const here = totals.find(r => r.period === period) || null;
    const newest = totals.slice().sort((a, b) => a.period.localeCompare(b.period)).pop() || null;
    const base = {
      code,
      name_ko: meta.name_ko,
      headline_ko: meta.headline_ko,
      coverage: meta.coverage,
      caveat: meta.caveat,
      boardUrl: meta.board_url,
    };
    if (here) {
      return {
        ...base, state: 'value', value: here.value, yoy: here.yoy, status: here.status,
        releasedAt: here.released_at, releaseUrl: here.release_url,
        attachments: here.attachments || [], fallback: null,
      };
    }
    return {
      ...base, state: 'unpublished', value: null, yoy: null, status: null,
      releasedAt: null, releaseUrl: meta.board_url, attachments: [],
      fallback: newest && {
        period: newest.period, value: newest.value, yoy: newest.yoy,
        releasedAt: newest.released_at, releaseUrl: newest.release_url,
      },
    };
  });
}
```

- [ ] **Step 4: 통과를 확인한다**

Run: `node --test "domains/employment/tests/web/data.test.mjs"`
Expected: PASS (5 tests)

- [ ] **Step 5: 판별력 왕복 확인**

`monthOptions` 의 `SOURCE_ORDER.every` 를 `.some` 으로 바꿔 본다. 첫 테스트가 **실패해야 한다**(하한이 2023-07 로 내려간다). 확인 후 되돌린다.

- [ ] **Step 6: 커밋**

```bash
git add domains/employment/app/js/data.js domains/employment/tests/web/data.test.mjs
git commit -m "feat(employment): 기간·포맷·출처 카드 조회 함수"
```

---

### Task 7: `data.js` — 단면 정규화와 매트릭스

산업·성·연령이 한 코드를 타게 만드는 지점이다.

**Files:**
- Modify: `domains/employment/app/js/data.js`
- Modify: `domains/employment/tests/web/data.test.mjs`

**Interfaces:**
- Consumes: Task 6 의 `SOURCE_ORDER`
- Produces:
  - `segmentsOf(industries, segments) -> [{breakdown, name_ko, categories: [{code, name_ko, provided}]}]` — `industry` 가 항상 첫 항목
  - `breakdownMatrix(series, categories, period, {sort}) -> [{code, name_ko, cells: {eaps, est, ei}}]`
    - 각 cell 은 `{state: 'value'|'notProvided'|'unpublished'|'noDelta', yoy: number|null}`
    - `sort` 는 `'delta'`(증감 절대값 내림차순, 값 없는 행은 뒤) 또는 `'code'`(선언 순서)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`data.test.mjs` 에 붙인다(상단 import 에 `segmentsOf, breakdownMatrix` 추가).

```javascript
const INDUSTRIES = [
  { code: 'A', name_ko: '농업, 임업 및 어업', provided: { eaps: true, est: false, ei: true } },
  { code: 'C', name_ko: '제조업', provided: { eaps: true, est: true, ei: true } },
];
const SEGMENTS = [
  { breakdown: 'sex', name_ko: '성별', categories: [
    { code: 'M', name_ko: '남자', provided: { eaps: true, est: false, ei: true } },
    { code: 'F', name_ko: '여자', provided: { eaps: true, est: false, ei: true } },
  ] },
];

test('segmentsOf puts industry first and keeps the rest', () => {
  const segments = segmentsOf(INDUSTRIES, SEGMENTS);
  assert.deepEqual(segments.map(s => s.breakdown), ['industry', 'sex']);
  assert.equal(segments[0].name_ko, '산업별');
  assert.deepEqual(segments[0].categories.map(c => c.code), ['A', 'C']);
});

test('breakdownMatrix tells the four empty states apart', () => {
  const series = [
    // A: est 는 미제공, eaps 는 값, ei 는 그 달 미발표
    rec({ source: 'eaps', breakdown: 'industry', category: 'A', period: '2026-07', yoy: 11.5 }),
    rec({ source: 'ei', breakdown: 'industry', category: 'A', period: '2026-06', yoy: 3.0 }),
    // C: est 는 값이 있지만 증감을 낼 수 없다
    rec({ source: 'eaps', breakdown: 'industry', category: 'C', period: '2026-07', yoy: -20.1 }),
    rec({ source: 'est', breakdown: 'industry', category: 'C', period: '2026-07', yoy: null }),
    rec({ source: 'ei', breakdown: 'industry', category: 'C', period: '2026-07', yoy: 5.5 }),
  ];
  const rows = breakdownMatrix(series, INDUSTRIES, '2026-07', { sort: 'code' });
  assert.deepEqual(rows.map(r => r.code), ['A', 'C']);
  assert.deepEqual(rows[0].cells.est, { state: 'notProvided', yoy: null });
  assert.deepEqual(rows[0].cells.ei, { state: 'unpublished', yoy: null });
  assert.deepEqual(rows[0].cells.eaps, { state: 'value', yoy: 11.5 });
  assert.deepEqual(rows[1].cells.est, { state: 'noDelta', yoy: null });
});

test('breakdownMatrix sorts by delta magnitude, empty rows last', () => {
  const series = [
    rec({ source: 'eaps', breakdown: 'industry', category: 'A', period: '2026-07', yoy: 11.5 }),
    rec({ source: 'eaps', breakdown: 'industry', category: 'C', period: '2026-07', yoy: -200.3 }),
  ];
  const rows = breakdownMatrix(series, INDUSTRIES, '2026-07', { sort: 'delta' });
  assert.deepEqual(rows.map(r => r.code), ['C', 'A']);
});

test('breakdownMatrix works unchanged for sex', () => {
  const series = [
    rec({ source: 'eaps', breakdown: 'sex', category: 'M', period: '2026-07', yoy: 47.9 }),
    rec({ source: 'ei', breakdown: 'sex', category: 'M', period: '2026-07', yoy: 90.0 }),
  ];
  const rows = breakdownMatrix(series, SEGMENTS[0].categories, '2026-07', { sort: 'code' });
  assert.equal(rows[0].cells.est.state, 'notProvided');
  assert.equal(rows[0].cells.eaps.yoy, 47.9);
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `node --test "domains/employment/tests/web/data.test.mjs"`
Expected: FAIL — `segmentsOf is not a function`

- [ ] **Step 3: 최소 구현**

`data.js` 에 붙인다.

```javascript
export function segmentsOf(industries, segments) {
  return [
    { breakdown: 'industry', name_ko: '산업별', categories: industries },
    ...segments,
  ];
}

// 없는 이유가 다른 것도 정보다. 미제공이면 발표 여부를 따질 이유가 없으므로
// 이 판정 순서를 지킨다. 이 함수 밖에서 상태를 다시 판정하지 않는다.
function cellState(record, provided) {
  if (provided === false) return { state: 'notProvided', yoy: null };
  if (!record) return { state: 'unpublished', yoy: null };
  if (record.yoy === null || record.yoy === undefined) return { state: 'noDelta', yoy: null };
  return { state: 'value', yoy: record.yoy };
}

export function breakdownMatrix(series, categories, period, { sort = 'delta' } = {}) {
  const byKey = new Map();
  for (const r of series) {
    if (r.period !== period) continue;
    byKey.set(`${r.source}|${r.breakdown}|${r.category}`, r);
  }
  const rows = categories.map(category => {
    const cells = {};
    for (const source of SOURCE_ORDER) {
      const record = Array.from(byKey.values()).find(
        r => r.source === source && r.category === category.code);
      cells[source] = cellState(record, category.provided ? category.provided[source] : true);
    }
    return { code: category.code, name_ko: category.name_ko, cells };
  });

  if (sort === 'code') return rows;

  const magnitude = row => {
    const values = SOURCE_ORDER
      .map(s => row.cells[s].yoy)
      .filter(v => v !== null);
    return values.length ? Math.max(...values.map(Math.abs)) : -1;
  };
  return rows.slice().sort((a, b) => magnitude(b) - magnitude(a));
}
```

- [ ] **Step 4: 통과를 확인한다**

Run: `node --test "domains/employment/tests/web/data.test.mjs"`
Expected: PASS (9 tests)

- [ ] **Step 5: 판별력 왕복 확인**

`cellState` 의 첫 두 줄 순서를 바꿔(레코드 유무를 먼저 보게) 본다. `breakdownMatrix tells the four empty states apart` 가 **실패해야 한다**. 확인 후 되돌린다.

- [ ] **Step 6: 커밋**

```bash
git add domains/employment/app/js/data.js domains/employment/tests/web/data.test.mjs
git commit -m "feat(employment): 단면 정규화와 3출처 매트릭스"
```

---

### Task 8: `data.js` — 시계열과 시트 데이터

**Files:**
- Modify: `domains/employment/app/js/data.js`
- Modify: `domains/employment/tests/web/data.test.mjs`

**Interfaces:**
- Consumes: Task 6·7
- Produces:
  - `categoryTimeline(series, {breakdown, category, months}) -> {eaps: [{period, value, yoy}], est: [...], ei: [...]}` — 기간 오름차순, `months` 기본 24, 최신월 기준으로 자른다
  - `sheetData(series, {period, breakdown, category, months}) -> {snapshot: [{source, state, yoy}], timeline: {...}, latest: string}`
    - `breakdown` 이 `null` 이면 전체(`breakdown: 'total'`) 단면
    - `snapshot` 은 `SOURCE_ORDER` 순서를 유지하며 미제공 출처도 자리를 지킨다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```javascript
test('categoryTimeline keeps the last N months per source, ascending', () => {
  const series = [];
  for (const m of [5, 6, 7]) {
    series.push(rec({ source: 'eaps', breakdown: 'industry', category: 'C', period: `2026-0${m}`, yoy: m }));
  }
  series.push(rec({ source: 'est', breakdown: 'industry', category: 'C', period: '2026-06', yoy: 1 }));
  const t = categoryTimeline(series, { breakdown: 'industry', category: 'C', months: 2 });
  assert.deepEqual(t.eaps.map(p => p.period), ['2026-06', '2026-07']);
  assert.deepEqual(t.est.map(p => p.period), ['2026-06']);
  assert.deepEqual(t.ei, []);
});

test('sheetData snapshot keeps every source in fixed order, notProvided included', () => {
  const series = [
    rec({ source: 'eaps', breakdown: 'sex', category: 'F', period: '2026-07', yoy: 59.7 }),
    rec({ source: 'ei', breakdown: 'sex', category: 'F', period: '2026-07', yoy: 188.0 }),
  ];
  const segments = [{ code: 'F', name_ko: '여자', provided: { eaps: true, est: false, ei: true } }];
  const d = sheetData(series, { period: '2026-07', breakdown: 'sex', category: 'F', categories: segments });
  assert.deepEqual(d.snapshot.map(s => s.source), ['eaps', 'est', 'ei']);
  assert.equal(d.snapshot[1].state, 'notProvided');
  assert.equal(d.snapshot[2].yoy, 188.0);
});

test('sheetData falls back to the total cut when no category is given', () => {
  const series = [
    rec({ source: 'eaps', breakdown: 'total', category: null, period: '2026-07', yoy: 107.6 }),
    rec({ source: 'ei', breakdown: 'total', category: null, period: '2026-07', yoy: 277.0 }),
    rec({ source: 'est', breakdown: 'total', category: null, period: '2026-06', yoy: 248.0 }),
  ];
  const d = sheetData(series, { period: '2026-07', breakdown: null, category: null });
  assert.equal(d.snapshot[0].yoy, 107.6);
  assert.equal(d.snapshot[1].state, 'unpublished');
  assert.equal(d.latest, '2026-07');
});

test('timeline always runs to the newest month even when an older month is selected', () => {
  const series = [
    rec({ source: 'eaps', breakdown: 'total', category: null, period: '2026-05', yoy: 1 }),
    rec({ source: 'eaps', breakdown: 'total', category: null, period: '2026-07', yoy: 3 }),
  ];
  const d = sheetData(series, { period: '2026-05', breakdown: null, category: null });
  assert.deepEqual(d.timeline.eaps.map(p => p.period), ['2026-05', '2026-07']);
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `node --test "domains/employment/tests/web/data.test.mjs"`
Expected: FAIL — `categoryTimeline is not a function`

- [ ] **Step 3: 최소 구현**

```javascript
export function categoryTimeline(series, { breakdown, category, months = 24 } = {}) {
  const out = {};
  for (const source of SOURCE_ORDER) {
    const points = series
      .filter(r => r.source === source
        && r.breakdown === (breakdown || 'total')
        && (r.category ?? null) === (category ?? null))
      .sort((a, b) => a.period.localeCompare(b.period))
      .map(r => ({ period: r.period, value: r.value, yoy: r.yoy }));
    out[source] = points.slice(-months);
  }
  return out;
}

// 시계열은 선택월과 무관하게 항상 최신월까지 그린다. 선택월 수치와 그 이후
// 흐름이 한 화면에 같이 와야 하기 때문이다(스펙 7.6).
export function sheetData(series, {
  period, breakdown = null, category = null, categories = null, months = 24,
} = {}) {
  const meta = categories && categories.find(c => c.code === category);
  const snapshot = SOURCE_ORDER.map(source => {
    const record = series.find(r => r.source === source && r.period === period
      && r.breakdown === (breakdown || 'total')
      && (r.category ?? null) === (category ?? null));
    const provided = meta && meta.provided ? meta.provided[source] : true;
    const cell = provided === false
      ? { state: 'notProvided', yoy: null }
      : !record ? { state: 'unpublished', yoy: null }
      : record.yoy === null || record.yoy === undefined ? { state: 'noDelta', yoy: null }
      : { state: 'value', yoy: record.yoy };
    return { source, ...cell };
  });
  const timeline = categoryTimeline(series, { breakdown, category, months });
  const all = Object.values(timeline).flat().map(p => p.period).sort();
  return { snapshot, timeline, latest: all.length ? all[all.length - 1] : period };
}
```

- [ ] **Step 4: 통과를 확인한다**

Run: `node --test "domains/employment/tests/web/data.test.mjs"`
Expected: PASS (13 tests)

- [ ] **Step 5: 판별력 왕복 확인**

`categoryTimeline` 의 `slice(-months)` 를 `slice(0, months)` 로 바꿔 본다. 첫 테스트가 **실패해야 한다**. 확인 후 되돌린다.

- [ ] **Step 6: 커밋**

```bash
git add domains/employment/app/js/data.js domains/employment/tests/web/data.test.mjs
git commit -m "feat(employment): 시계열과 증감 비교 시트 데이터"
```

---

### Task 9: `chart.js` — 막대·시계열 SVG

차트 라이브러리를 쓰지 않는다. 문자열을 만드는 순수 함수라 테스트가 가능하다.

**Files:**
- Create: `domains/employment/app/js/chart.js`
- Create: `domains/employment/tests/web/chart.test.mjs`

**Interfaces:**
- Consumes: `SOURCE_ORDER`, `SOURCE_COLORS`, `fmtDelta` (from `./data.js`)
- Produces:
  - `barsSvg(snapshot, {width, sourceNames}) -> string` — 0 기준선 가로 막대. 미제공/미발표/증감없음 행은 막대 없이 `― 미제공` 등 텍스트로 자리를 지킨다
  - `timelineSvg(timeline, {width, height, selected}) -> string` — 출처별 폴리라인 + 0선 + 선택월 수직 표식
  - `sheetTable(snapshot, timeline, {sourceNames}) -> string` — `표로 보기` 대체 뷰(HTML `<table>`)

**세로 막대를 쓰지 않는 이유:** 출처명이 길어 축 라벨이 회전·절단된다(스펙 7.6).

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`domains/employment/tests/web/chart.test.mjs`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { barsSvg, timelineSvg, sheetTable } from '../../app/js/chart.js';

const NAMES = { eaps: '경제활동인구조사', est: '사업체노동력조사', ei: '고용행정통계' };

test('every bar carries its value label — the contrast mitigation is not optional', () => {
  const snapshot = [
    { source: 'eaps', state: 'value', yoy: 107.6 },
    { source: 'est', state: 'notProvided', yoy: null },
    { source: 'ei', state: 'value', yoy: 277.0 },
  ];
  const svg = barsSvg(snapshot, { width: 320, sourceNames: NAMES });
  assert.match(svg, /\+10\.8만명/);
  assert.match(svg, /\+27\.7만명/);
  assert.match(svg, /― 미제공/);
});

test('bars extend both ways from the zero line', () => {
  const svg = barsSvg([
    { source: 'eaps', state: 'value', yoy: -200 },
    { source: 'ei', state: 'value', yoy: 100 },
  ], { width: 300, sourceNames: NAMES });
  const rects = [...svg.matchAll(/<rect[^>]*x="([\d.]+)"[^>]*width="([\d.]+)"/g)]
    .map(m => ({ x: Number(m[1]), w: Number(m[2]) }));
  assert.equal(rects.length, 2);
  assert.ok(rects[0].x < rects[1].x, '음수 막대는 0선 왼쪽에서 시작한다');
});

test('a source with no points draws no polyline but keeps its color assignment', () => {
  const svg = timelineSvg(
    { eaps: [{ period: '2026-06', yoy: 1 }, { period: '2026-07', yoy: 2 }], est: [], ei: [] },
    { width: 320, height: 160, selected: '2026-07' },
  );
  assert.match(svg, /#2a78d6/);
  assert.doesNotMatch(svg, /#eb6834/);
});

test('the selected month gets a marker line', () => {
  const svg = timelineSvg(
    { eaps: [{ period: '2026-05', yoy: 1 }, { period: '2026-07', yoy: 2 }], est: [], ei: [] },
    { width: 320, height: 160, selected: '2026-05' },
  );
  assert.match(svg, /class="chart__marker"/);
});

test('sheetTable is a real table with every source as a row', () => {
  const html = sheetTable(
    [{ source: 'eaps', state: 'value', yoy: 107.6 }, { source: 'est', state: 'notProvided', yoy: null }],
    { eaps: [{ period: '2026-07', yoy: 107.6 }], est: [] },
    { sourceNames: NAMES },
  );
  assert.match(html, /<table/);
  assert.match(html, /경제활동인구조사/);
  assert.match(html, /사업체노동력조사/);
  assert.match(html, /미제공/);
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `node --test "domains/employment/tests/web/chart.test.mjs"`
Expected: FAIL — `chart.js` 가 없다.

- [ ] **Step 3: 최소 구현**

`domains/employment/app/js/chart.js`:

```javascript
// 증감 비교 시트의 그림. SVG 문자열만 만든다 — DOM 을 만지지 않아 테스트가 된다.
import { SOURCE_ORDER, SOURCE_COLORS, fmtDelta, monthLabel, esc } from './data.js';

const EMPTY_LABEL = {
  notProvided: '― 미제공',
  unpublished: '― 미발표',
  noDelta: '― 증감없음',
};

const ROW_H = 34;
const LABEL_W = 96;

export function barsSvg(snapshot, { width = 320, sourceNames = {} } = {}) {
  const rows = snapshot.filter(s => SOURCE_ORDER.includes(s.source));
  const height = rows.length * ROW_H + 8;
  const plotW = width - LABEL_W - 8;
  const max = Math.max(1, ...rows.map(r => Math.abs(r.yoy ?? 0)));
  const zero = LABEL_W + plotW / 2;

  const parts = [
    `<line class="chart__zero" x1="${zero}" y1="0" x2="${zero}" y2="${height}" stroke="#e2e5ea" stroke-width="1"></line>`,
  ];

  rows.forEach((row, i) => {
    const y = i * ROW_H + 6;
    const name = sourceNames[row.source] || row.source;
    parts.push(`<text x="0" y="${y + 15}" font-size="11" fill="#667085">${esc(name)}</text>`);

    if (row.state !== 'value') {
      parts.push(`<text x="${zero + 6}" y="${y + 15}" font-size="11" fill="#98a2b3">${esc(EMPTY_LABEL[row.state] || '―')}</text>`);
      return;
    }
    const w = (Math.abs(row.yoy) / max) * (plotW / 2 - 44);
    const x = row.yoy >= 0 ? zero : zero - w;
    parts.push(
      `<rect x="${x.toFixed(1)}" y="${y}" width="${Math.max(w, 1).toFixed(1)}" height="20" rx="4" fill="${SOURCE_COLORS[row.source]}"></rect>`,
      // 값은 막대 끝에 직접 붙인다. #1baf7a 의 대비 미달에 대한 완화 조치이므로
      // 지울 수 없다(스펙 7.6). 글자에는 계열 색을 입히지 않는다.
      `<text x="${(row.yoy >= 0 ? x + w + 5 : x - 5).toFixed(1)}" y="${y + 15}" font-size="11" fill="#191d24" text-anchor="${row.yoy >= 0 ? 'start' : 'end'}">${esc(fmtDelta(row.yoy))}</text>`,
    );
  });

  return `<svg class="chart chart--bars" viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img">${parts.join('')}</svg>`;
}

export function timelineSvg(timeline, { width = 320, height = 160, selected = null } = {}) {
  const periods = Array.from(new Set(
    SOURCE_ORDER.flatMap(s => (timeline[s] || []).map(p => p.period)))).sort();
  if (!periods.length) return '';

  const pad = { l: 8, r: 8, t: 10, b: 18 };
  const plotW = width - pad.l - pad.r;
  const plotH = height - pad.t - pad.b;
  const values = SOURCE_ORDER.flatMap(s => (timeline[s] || []).map(p => p.yoy)).filter(v => v !== null);
  const max = Math.max(1, ...values.map(Math.abs));
  const x = period => pad.l + (periods.indexOf(period) / Math.max(1, periods.length - 1)) * plotW;
  const y = value => pad.t + plotH / 2 - (value / max) * (plotH / 2);

  const parts = [
    `<line x1="${pad.l}" y1="${y(0)}" x2="${width - pad.r}" y2="${y(0)}" stroke="#e2e5ea" stroke-width="1"></line>`,
  ];

  if (selected && periods.includes(selected)) {
    parts.push(`<line class="chart__marker" x1="${x(selected)}" y1="${pad.t}" x2="${x(selected)}" y2="${pad.t + plotH}" stroke="#98a2b3" stroke-width="1" stroke-dasharray="3 3"></line>`);
  }

  for (const source of SOURCE_ORDER) {
    const points = (timeline[source] || []).filter(p => p.yoy !== null);
    if (!points.length) continue;   // 출처가 빠져도 남은 색은 바뀌지 않는다
    const d = points.map(p => `${x(p.period).toFixed(1)},${y(p.yoy).toFixed(1)}`).join(' ');
    parts.push(`<polyline points="${d}" fill="none" stroke="${SOURCE_COLORS[source]}" stroke-width="2" stroke-linejoin="round"></polyline>`);
    const hit = selected && points.find(p => p.period === selected);
    if (hit) {
      parts.push(`<circle cx="${x(hit.period).toFixed(1)}" cy="${y(hit.yoy).toFixed(1)}" r="4.5" fill="${SOURCE_COLORS[source]}"></circle>`);
    }
  }

  parts.push(
    `<text x="${pad.l}" y="${height - 4}" font-size="10" fill="#98a2b3">${esc(monthLabel(periods[0]))}</text>`,
    `<text x="${width - pad.r}" y="${height - 4}" font-size="10" fill="#98a2b3" text-anchor="end">${esc(monthLabel(periods[periods.length - 1]))}</text>`,
  );

  return `<svg class="chart chart--line" viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img">${parts.join('')}</svg>`;
}

export function sheetTable(snapshot, timeline, { sourceNames = {} } = {}) {
  const rows = snapshot.map(s => {
    const label = s.state === 'value' ? esc(fmtDelta(s.yoy)) : esc(EMPTY_LABEL[s.state] || '―');
    const points = (timeline[s.source] || []).length;
    return `<tr><th scope="row">${esc(sourceNames[s.source] || s.source)}</th><td class="num">${label}</td><td class="num">${points}개월</td></tr>`;
  }).join('');
  return `<table class="sheet__table"><caption class="sr-only">출처별 전년동월대비 증감</caption>` +
    `<thead><tr><th scope="col">출처</th><th scope="col">증감</th><th scope="col">시계열</th></tr></thead>` +
    `<tbody>${rows}</tbody></table>`;
}
```

- [ ] **Step 4: 통과를 확인한다**

Run: `node --test "domains/employment/tests/web/chart.test.mjs"`
Expected: PASS (5 tests)

- [ ] **Step 5: 판별력 왕복 확인**

`barsSvg` 에서 값 라벨 `<text>` 를 만드는 줄을 지워 본다. 첫 테스트가 **실패해야 한다**. 확인 후 되돌린다.

- [ ] **Step 6: 커밋**

```bash
git add domains/employment/app/js/chart.js domains/employment/tests/web/chart.test.mjs
git commit -m "feat(employment): 증감 비교 차트 SVG 생성기"
```

---

### Task 10: 앱 셸과 총괄 화면

여기서 `app/` 이 생긴다 — 허브 버튼이 켜지는 순간이다.

**Files:**
- Create: `domains/employment/app/index.html`, `css/app.css`, `manifest.webmanifest`, `sw.js`, `js/app.js`, `js/screens/overview.js`
- Create: `domains/employment/app/icons/icon-192.png`, `icon-512.png`
- Modify: `tools/make_icons.py` (출력 경로와 색을 인자로)

**Interfaces:**
- Consumes: `data.js` 의 `monthOptions`, `overviewCards`, `fmtLevel`, `fmtDelta`, `monthLabel`, `esc`; `core/shell.js` 의 `loadJson`
- Produces: `screens/overview.js` 의 `render(el, ctx)`; `ctx` 는 `{series, sources, industries, segments, state:{period, breakdown, category, sheetOpen}, navigate, rerender}`

**셸 구조** — `index.html` 은 전망 앱과 같은 뼈대에 하단 탭바 대신 **상단 세그먼트 3개**와 **하단 시트 핸들**을 둔다.

```html
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#23508f">
  <title>고용동향</title>
  <link rel="manifest" href="./manifest.webmanifest">
  <link rel="icon" href="./icons/icon-192.png">
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap">
  <link rel="stylesheet" href="./core/tokens.css">
  <link rel="stylesheet" href="./core/base.css">
  <link rel="stylesheet" href="./css/app.css">
</head>
<body>
  <div class="app">
    <header class="header">
      <a class="header__home" href="../" aria-label="홈으로">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"></path><path d="M5 9.5V21h14V9.5"></path></svg>
      </a>
      <div class="header__title">고용동향</div>
      <div class="header__meta"><span class="num" id="headerDate"></span></div>
    </header>
    <nav class="segments" id="segments" role="tablist">
      <a class="segment" href="#/" data-route="overview" role="tab">총괄</a>
      <a class="segment" href="#/b/industry" data-route="breakdown" role="tab">단면별</a>
      <a class="segment" href="#/sources" data-route="sources" role="tab">출처비교</a>
    </nav>
    <div id="offlineBanner" class="offline-banner" hidden>오프라인 · 마지막으로 받은 데이터를 표시 중</div>
    <main id="screen" class="screen"></main>
    <div class="notice">본 서비스는 개인이 제작한 비공식 참고자료이며, 각 기관 원문이 정본입니다.</div>
    <button type="button" class="sheet__handle" id="sheetHandle" aria-expanded="false" aria-controls="sheet">
      <span id="sheetHandleLabel">증감 비교</span> <span aria-hidden="true">▲</span>
    </button>
    <section class="sheet" id="sheet" hidden aria-label="증감 비교"></section>
  </div>
  <script type="module" src="./js/app.js"></script>
</body>
</html>
```

- [ ] **Step 1: 아이콘을 만든다**

`tools/make_icons.py` 의 `OUT_DIR`·`BG_COLOR` 를 인자로 받게 고친다.

```python
import sys

OUT_DIR = Path(__file__).resolve().parent.parent / "domains" / (
    sys.argv[1] if len(sys.argv) > 1 else "forecast") / "app" / "icons"
BG_COLOR = sys.argv[2] if len(sys.argv) > 2 else "#23508f"
```

Run: `pip install pillow && python tools/make_icons.py employment "#1f6f4a"`
Expected: `domains/employment/app/icons/icon-192.png`·`icon-512.png` 생성

- [ ] **Step 2: 셸과 총괄 화면을 만든다**

`index.html` 은 위 블록 그대로. `manifest.webmanifest` 는 전망 것을 복사해 이름을 바꾼다.

```json
{
  "name": "고용동향 아카이브",
  "short_name": "고용동향",
  "start_url": "./",
  "display": "standalone",
  "background_color": "#eef0f3",
  "theme_color": "#23508f",
  "icons": [
    { "src": "./icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "./icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable" }
  ]
}
```

`sw.js` 는 `domains/forecast/app/sw.js` 를 복사하고 `CACHE = 'employment-v1'` 과 `SHELL_ASSETS` 의 파일 목록만 이 앱 것으로 바꾼다. **network-first 전략과 그 위 주석은 그대로 둔다** — 이유가 그 주석에 적혀 있다.

`js/app.js`:

```javascript
import { render as overview } from './screens/overview.js';
import { render as breakdown } from './screens/breakdown.js';
import { render as sources } from './screens/sources.js';
import { mountSheet } from './sheet.js';
import { monthOptions } from './data.js';
import { loadJson } from '../core/shell.js';

const screens = { overview, breakdown, sources };

export function parseRoute(hash) {
  const h = (hash || '').replace(/^#/, '') || '/';
  if (h === '/' || h === '') return { name: 'overview', params: {} };
  if (h === '/sources') return { name: 'sources', params: {} };
  const m = h.match(/^\/b\/(industry|sex|age)(?:\/(.+))?$/);
  if (m) {
    let category = null;
    if (m[2]) { try { category = decodeURIComponent(m[2]); } catch { category = null; } }
    return { name: 'breakdown', params: { breakdown: m[1], category } };
  }
  return { name: 'overview', params: {} };
}

async function boot() {
  const screenEl = document.getElementById('screen');
  const segmentsEl = document.getElementById('segments');
  const headerDateEl = document.getElementById('headerDate');
  const offlineBanner = document.getElementById('offlineBanner');

  const [series, sourcesMeta, industries, segments, lastRun] = await Promise.all([
    loadJson('./data/series.json'),
    loadJson('./data/sources.json'),
    loadJson('./data/industries.json'),
    loadJson('./data/segments.json'),
    loadJson('./data/last_run.json'),
  ]);

  if (!navigator.onLine) offlineBanner.hidden = false;
  window.addEventListener('offline', () => { offlineBanner.hidden = false; });
  window.addEventListener('online', () => { offlineBanner.hidden = true; });

  if (series === null) {
    screenEl.textContent = '데이터를 불러올 수 없습니다. 네트워크 연결을 확인한 뒤 다시 시도해 주세요.';
    return;
  }

  if (lastRun && lastRun.run_at) {
    headerDateEl.textContent = `${lastRun.run_at.slice(5, 7)}.${lastRun.run_at.slice(8, 10)} 갱신`;
  }

  const months = monthOptions(series);
  const ctx = {
    series,
    sources: sourcesMeta || [],
    industries: industries || [],
    segments: segments || [],
    months,
    state: { period: months.latest, breakdown: null, category: null },
    rerender: () => route(),
  };

  const sheet = mountSheet(document.getElementById('sheet'),
    document.getElementById('sheetHandle'),
    document.getElementById('sheetHandleLabel'), ctx);

  function route() {
    const parsed = parseRoute(location.hash);
    ctx.params = parsed.params;
    ctx.state.breakdown = parsed.name === 'breakdown' ? parsed.params.breakdown : null;
    ctx.state.category = parsed.name === 'breakdown' ? parsed.params.category : null;
    segmentsEl.querySelectorAll('.segment').forEach(el => {
      el.classList.toggle('segment--active', el.dataset.route === parsed.name);
    });
    screenEl.innerHTML = '';
    (screens[parsed.name] || overview)(screenEl, ctx);
    sheet.refresh();
  }

  window.addEventListener('hashchange', route);
  route();
}

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('./sw.js').catch(() => {});
}

boot();
```

`js/screens/overview.js` — 연·월 스위처와 카드 3장.

```javascript
import { overviewCards, fmtLevel, fmtDelta, monthLabel, esc } from '../data.js';

function switcher(ctx) {
  const { years, monthsByYear } = ctx.months;
  const year = Number(ctx.state.period.slice(0, 4));
  const month = Number(ctx.state.period.slice(5, 7));
  const yearOpts = years.map(y =>
    `<option value="${y}"${y === year ? ' selected' : ''}>${y}년</option>`).join('');
  const monthOpts = (monthsByYear[year] || []).map(m =>
    `<option value="${m}"${m === month ? ' selected' : ''}>${m}월</option>`).join('');
  return `<div class="switcher">
    <select id="yearSelect" aria-label="기준 연도">${yearOpts}</select>
    <select id="monthSelect" aria-label="기준 월">${monthOpts}</select>
  </div>`;
}

// 사업체노동력조사의 released_at 은 보도자료 발표일이 아니라 KOSIS 표 갱신일이다.
// 다른 둘과 뜻이 다르므로 라벨을 달리 쓴다.
function releaseLabel(card) {
  const at = card.releasedAt;
  if (!at) return '';
  const when = `${at.slice(5, 7)}.${at.slice(8, 10)}`;
  return card.code === 'est' ? `KOSIS 갱신 ${when}` : `발표 ${when}`;
}

function attachmentLinks(card) {
  return (card.attachments || [])
    .map(a => `<a href="${esc(a.url)}" rel="noopener">${esc(a.type)}</a>`).join(' · ');
}

function cardHtml(card) {
  const head = `<div class="card__head"><span class="card__name">${esc(card.name_ko)}</span>
    <span class="card__meta num">${esc(releaseLabel(card))}</span></div>`;

  const body = card.state === 'value'
    ? `<div class="card__value num">${esc(fmtLevel(card.value))}</div>
       <div class="card__delta num ${card.yoy >= 0 ? 'is-up' : 'is-down'}">${esc(fmtDelta(card.yoy))} <span class="card__deltaNote">전년동월대비</span></div>`
    : `<div class="card__value card__value--empty">${esc(monthLabel(card.fallback ? card.fallback.period : ''))} 기준 미발표</div>` +
      (card.fallback
        ? `<div class="card__fallback num">최신 ${esc(monthLabel(card.fallback.period))} · ${esc(fmtLevel(card.fallback.value))} (${esc(fmtDelta(card.fallback.yoy))})</div>`
        : '');

  // coverage 는 접히지 않는다. 정의 차이의 인지가 이 앱의 핵심 가치다(스펙 7.5).
  const coverage = `<div class="card__coverage">${esc(card.coverage)}</div>`;
  const links = `<div class="card__links"><a href="${esc(card.releaseUrl)}" rel="noopener">원문보기</a>${
    attachmentLinks(card) ? ' · ' + attachmentLinks(card) : ''}</div>`;

  return `<article class="card" data-source="${esc(card.code)}">${head}${body}${coverage}${links}</article>`;
}

export function render(el, ctx) {
  const cards = overviewCards(ctx.series, ctx.sources, ctx.state.period);
  el.innerHTML = switcher(ctx) + `<div class="cards">${cards.map(cardHtml).join('')}</div>`;

  el.querySelector('#yearSelect').addEventListener('change', e => {
    const year = Number(e.target.value);
    const months = ctx.months.monthsByYear[year] || [];
    const month = months[months.length - 1];
    ctx.state.period = `${year}-${String(month).padStart(2, '0')}`;
    ctx.rerender();
  });
  el.querySelector('#monthSelect').addEventListener('change', e => {
    ctx.state.period = `${ctx.state.period.slice(0, 4)}-${String(e.target.value).padStart(2, '0')}`;
    ctx.rerender();
  });
}
```

`css/app.css` 에 `.segments`·`.segment`·`.switcher`·`.sheet` 스타일을 쓴다.
`.card`·`.num`·`.header`·`.screen`·`.notice`·`.offline-banner` 는 **`core/base.css` 에
이미 있으므로 다시 정의하지 않는다** — 카드의 하위 요소(`.card__value` 등)만 이
파일이 갖는다. 색 토큰도 이 파일이 갖는다(`core/` 에 올리지 않는다):

```css
:root {
  --src-eaps: #2a78d6;
  --src-est: #eb6834;
  --src-ei: #1baf7a;
}
```

- [ ] **Step 3: 빌드하고 눈으로 확인한다**

```bash
python -m tools.build
python -m tools.serve
```
브라우저에서 `http://127.0.0.1:8642/employment/` 를 연다.
Expected: 카드 3장, 사업체노동력조사는 `2026.07 기준 미발표` + 회색 직전달 값.

- [ ] **Step 4: 허브가 저절로 켜졌는지 확인한다**

`http://127.0.0.1:8642/` 에서 고용동향 버튼이 활성 상태여야 한다.
**허브 코드나 `build.py` 를 고쳐서 켜면 안 된다** — 고쳐야 한다면 A단계 설계가 실패한 것이므로 멈추고 보고한다.

- [ ] **Step 5: 커밋**

```bash
git add domains/employment/app tools/make_icons.py
git commit -m "feat(employment): 앱 셸과 총괄 화면"
```

---

### Task 11: 단면별 화면

**Files:**
- Create: `domains/employment/app/js/screens/breakdown.js`
- Modify: `domains/employment/app/css/app.css`, `domains/employment/app/sw.js` (SHELL_ASSETS)

**Interfaces:**
- Consumes: `segmentsOf`, `breakdownMatrix`, `categoryTimeline`, `fmtDelta`, `esc`
- Produces: `render(el, ctx)`; 라우트 `#/b/<breakdown>[/<category>]`

- [ ] **Step 1: 화면을 만든다**

```javascript
import { segmentsOf, breakdownMatrix, categoryTimeline, fmtDelta, monthLabel, esc, SOURCE_ORDER } from '../data.js';

const EMPTY_LABEL = { notProvided: '―', unpublished: '미발표', noDelta: '증감없음' };

// 사업체노동력조사가 성·연령에서 통째로 비는 이유를 화면이 말한다.
// 열을 지우면 "안 잡는다"는 사실 자체가 사라진다.
const EST_NOTE = '사업체노동력조사는 성·연령별 종사자수를 공표하지 않습니다.';

function tabs(segments, current) {
  return `<div class="btabs">${segments.map(s =>
    `<a class="btab${s.breakdown === current ? ' btab--active' : ''}" href="#/b/${s.breakdown}">${esc(s.name_ko)}</a>`
  ).join('')}</div>`;
}

function cell(state, yoy) {
  if (state === 'value') {
    return `<td class="num ${yoy >= 0 ? 'is-up' : 'is-down'}">${esc(fmtDelta(yoy))}</td>`;
  }
  return `<td class="cell--empty">${esc(EMPTY_LABEL[state])}</td>`;
}

export function render(el, ctx) {
  const segments = segmentsOf(ctx.industries, ctx.segments);
  const current = ctx.state.breakdown || 'industry';
  const segment = segments.find(s => s.breakdown === current) || segments[0];
  const sort = ctx.state.sort || 'delta';
  const rows = breakdownMatrix(ctx.series, segment.categories, ctx.state.period, { sort });

  const note = current === 'industry' ? '' : `<p class="note note--est">${esc(EST_NOTE)}</p>`;
  const head = `<thead><tr><th scope="col">${esc(segment.name_ko)}</th>${
    SOURCE_ORDER.map(s => `<th scope="col"><a href="${esc(
      (ctx.sources.find(m => m.code === s) || {}).board_url || '#')}" rel="noopener">${esc(
      (ctx.sources.find(m => m.code === s) || {}).name_ko || s)}</a></th>`).join('')
  }</tr></thead>`;

  const body = rows.map(row => `
    <tr class="row" data-code="${esc(row.code)}">
      <th scope="row">${esc(row.name_ko)}</th>
      ${SOURCE_ORDER.map(s => cell(row.cells[s].state, row.cells[s].yoy)).join('')}
    </tr>
    ${ctx.state.category === row.code ? expanded(ctx, current, row) : ''}`).join('');

  el.innerHTML = tabs(segments, current) + note + `
    <div class="sortbar">
      <button type="button" class="sortbtn${sort === 'delta' ? ' is-on' : ''}" data-sort="delta">증감순</button>
      <button type="button" class="sortbtn${sort === 'code' ? ' is-on' : ''}" data-sort="code">분류순</button>
    </div>
    <table class="matrix">${head}<tbody>${body}</tbody></table>
    <p class="legend">― 미제공 · 미발표 = 아직 그 달을 내지 않음 · 증감없음 = 전년동월대비를 낼 수 없음</p>`;

  el.querySelectorAll('.sortbtn').forEach(btn => btn.addEventListener('click', () => {
    ctx.state.sort = btn.dataset.sort;
    ctx.rerender();
  }));
  el.querySelectorAll('.row').forEach(tr => tr.addEventListener('click', () => {
    const code = tr.dataset.code;
    location.hash = ctx.state.category === code ? `#/b/${current}` : `#/b/${current}/${encodeURIComponent(code)}`;
  }));
}

function expanded(ctx, breakdown, row) {
  const timeline = categoryTimeline(ctx.series, { breakdown, category: row.code, months: 24 });
  const lines = SOURCE_ORDER.map(s => {
    const points = timeline[s];
    if (!points.length) return '';
    const last = points[points.length - 1];
    const name = (ctx.sources.find(m => m.code === s) || {}).name_ko || s;
    return `<li><span class="dot" style="background:${esc({ eaps: '#2a78d6', est: '#eb6834', ei: '#1baf7a' }[s])}"></span>
      ${esc(name)} · ${esc(monthLabel(last.period))} ${esc(last.yoy === null ? '증감없음' : fmtDelta(last.yoy))}</li>`;
  }).join('');
  return `<tr class="expand"><td colspan="4"><ul class="expand__list">${lines}</ul></td></tr>`;
}
```

- [ ] **Step 2: sw.js 의 `SHELL_ASSETS` 에 새 파일을 더한다**

`'./js/screens/breakdown.js'` 를 목록에 넣는다. 빠뜨리면 오프라인에서 이 화면만 빈다.

- [ ] **Step 3: 확인한다**

`python -m tools.build && python -m tools.serve` 후 `#/b/sex` 로 이동.
Expected: 사업체노동력조사 열이 전부 `―` 이고 위에 안내 문장이 있다. 행을 탭하면 시계열이 펼쳐진다.

- [ ] **Step 4: 커밋**

```bash
git add domains/employment/app/js/screens/breakdown.js domains/employment/app/css/app.css domains/employment/app/sw.js
git commit -m "feat(employment): 단면별 화면 — 산업·성·연령"
```

---

### Task 12: 출처비교 화면

세 숫자가 왜 다른지 답하는 화면이고, 시트의 짧은 선을 설명하는 자리이기도 하다.

**Files:**
- Create: `domains/employment/app/js/screens/sources.js`
- Modify: `domains/employment/app/sw.js` (SHELL_ASSETS)

**Interfaces:**
- Consumes: `esc`, `SOURCE_ORDER`, `ctx.sources`
- Produces: `render(el, ctx)`

- [ ] **Step 1: 화면을 만든다**

```javascript
import { esc, SOURCE_ORDER, SOURCE_COLORS } from '../data.js';

// 시트에서 사업체노동력조사 선이 늦게 시작하는 이유는 결함이 아니라 사실이다.
// 근거를 이 화면에 둔다(상위 스펙 11장).
const NOTES = [
  ['시계열이 시작하는 달이 다르다',
   '사업체노동력조사의 전년동월대비는 2025년 1월부터다. 2024년 1월 이전은 다른 산업분류 체계의 별도 표에 있고, 이어붙이면 재분류 효과가 고용 변화로 둔갑하므로 잇지 않는다. 짧은 선이 틀린 선보다 낫다.'],
  ['성·연령별은 두 출처만 있다',
   '사업체노동력조사는 성·연령별 종사자수를 공표하지 않는다. 그 단면에서는 경제활동인구조사와 고용행정통계 둘만 비교된다.'],
  ['같은 분류를 다르게 부른다',
   '경제활동인구조사는 남자·여자·15∼29세로, 고용행정통계는 남성·여성·29세이하로 쓴다. 이 앱은 남자·여자·29세 이하로 통일해 표기한다.'],
];

export function render(el, ctx) {
  const cards = SOURCE_ORDER.map(code => {
    const meta = ctx.sources.find(s => s.code === code);
    if (!meta) return '';
    return `<article class="scard">
      <div class="scard__head"><span class="swatch" style="background:${esc(SOURCE_COLORS[code])}"></span>
        <span class="scard__name">${esc(meta.name_ko)}</span>
        <span class="scard__agency">${esc(meta.agency)}</span></div>
      <dl class="scard__defs">
        <dt>대표 지표</dt><dd>${esc(meta.headline_ko)}</dd>
        <dt>조사 성격</dt><dd>${esc(meta.type)}</dd>
        <dt>포괄 범위</dt><dd>${esc(meta.coverage)}</dd>
        <dt>발표 주기</dt><dd>${esc(meta.release_rule)}</dd>
        <dt>유의사항</dt><dd>${esc(meta.caveat)}</dd>
      </dl>
      <a class="scard__link" href="${esc(meta.board_url)}" rel="noopener">게시판 바로가기</a>
    </article>`;
  }).join('');

  const notes = NOTES.map(([title, body]) =>
    `<section class="note"><h3>${esc(title)}</h3><p>${esc(body)}</p></section>`).join('');

  el.innerHTML = `<div class="scards">${cards}</div>${notes}`;
}
```

- [ ] **Step 2: sw.js 의 `SHELL_ASSETS` 에 `'./js/screens/sources.js'` 를 더한다**

- [ ] **Step 3: 확인한다**

`#/sources` 에서 카드 3장과 주석 3개가 보인다.

- [ ] **Step 4: 커밋**

```bash
git add domains/employment/app/js/screens/sources.js domains/employment/app/sw.js
git commit -m "feat(employment): 출처비교 화면"
```

---

### Task 13: 증감 비교 시트 배선

**Files:**
- Create: `domains/employment/app/js/sheet.js`
- Modify: `domains/employment/app/css/app.css`, `domains/employment/app/sw.js`

**Interfaces:**
- Consumes: `sheetData` (data.js), `barsSvg`·`timelineSvg`·`sheetTable` (chart.js)
- Produces: `mountSheet(sheetEl, handleEl, labelEl, ctx) -> {refresh(): void}`

**동작:** 핸들은 상시 노출. 탭하면 열리고 다시 탭·배경 탭으로 닫힌다. 열림 상태는 `localStorage['employment.sheet']` 에 남아 세그먼트를 옮겨도 유지된다.

- [ ] **Step 1: 만든다**

```javascript
import { sheetData, segmentsOf, monthLabel, esc } from './data.js';
import { barsSvg, timelineSvg, sheetTable } from './chart.js';

const KEY = 'employment.sheet';
const TABLE_KEY = 'employment.sheet.table';

function read(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function write(key, value) {
  try { localStorage.setItem(key, value); } catch { /* 사파리 프라이빗 등 */ }
}

export function mountSheet(sheetEl, handleEl, labelEl, ctx) {
  let open = read(KEY) === '1';
  let asTable = read(TABLE_KEY) === '1';

  function cut() {
    const segments = segmentsOf(ctx.industries, ctx.segments);
    const breakdown = ctx.state.category ? ctx.state.breakdown : null;
    const segment = segments.find(s => s.breakdown === breakdown);
    const category = ctx.state.category || null;
    const label = category && segment
      ? (segment.categories.find(c => c.code === category) || {}).name_ko || category
      : '전체';
    return { breakdown, category, categories: segment ? segment.categories : null, label };
  }

  function refresh() {
    const { breakdown, category, categories, label } = cut();
    const data = sheetData(ctx.series, { period: ctx.state.period, breakdown, category, categories });
    const names = Object.fromEntries(ctx.sources.map(s => [s.code, s.name_ko]));

    labelEl.textContent = `증감 비교 · ${monthLabel(ctx.state.period)} · ${label}`;
    handleEl.setAttribute('aria-expanded', String(open));
    sheetEl.hidden = !open;
    if (!open) return;

    sheetEl.innerHTML = `
      <div class="sheet__head">
        <span>증감 비교 · ${esc(monthLabel(ctx.state.period))} · ${esc(label)}</span>
        <button type="button" class="sheet__toggle" id="sheetTableToggle">${asTable ? '그래프로 보기' : '표로 보기'}</button>
      </div>
      ${asTable
        ? sheetTable(data.snapshot, data.timeline, { sourceNames: names })
        : barsSvg(data.snapshot, { width: 320, sourceNames: names }) +
          timelineSvg(data.timeline, { width: 320, height: 160, selected: ctx.state.period })}
      <ul class="sheet__legend">${
        data.snapshot.map(s => `<li><span class="dot" data-source="${esc(s.source)}"></span>${esc(names[s.source] || s.source)}</li>`).join('')
      }</ul>`;

    sheetEl.querySelector('#sheetTableToggle').addEventListener('click', () => {
      asTable = !asTable;
      write(TABLE_KEY, asTable ? '1' : '0');
      refresh();
    });
  }

  handleEl.addEventListener('click', () => {
    open = !open;
    write(KEY, open ? '1' : '0');
    refresh();
  });

  refresh();
  return { refresh };
}
```

- [ ] **Step 2: sw.js 의 `SHELL_ASSETS` 에 `'./js/sheet.js'`·`'./js/chart.js'` 를 더한다**

- [ ] **Step 3: 확인한다**

- 총괄에서 핸들을 열고 `단면별 → 성별 → 여자` 로 이동해도 시트가 **열린 채** 남고 헤더가 `증감 비교 · 2026.07 · 여자` 로 바뀐다
- 사업체노동력조사 행이 `― 미제공` 으로 자리를 지킨다
- `표로 보기` 를 누르면 표가 나오고 다시 누르면 그래프로 돌아온다
- 기준월을 2025-03 으로 바꿔도 시계열은 2026-07 까지 그려지고 2025-03 에 표식선이 선다

- [ ] **Step 4: 전체 테스트**

Run: `python -m pytest -q && node --test "core/tests/*.mjs" "hub/tests/*.mjs" "domains/forecast/tests/web/*.mjs" "domains/employment/tests/web/*.mjs"`
Expected: 모두 PASS

- [ ] **Step 5: 커밋**

```bash
git add domains/employment/app/js/sheet.js domains/employment/app/css/app.css domains/employment/app/sw.js
git commit -m "feat(employment): 증감 비교 시트"
```

---

### Task 14: 빌드·워크플로·실기기 확인

**Files:**
- Modify: `README.md`, `.github/workflows/deploy.yml`(웹 테스트 경로가 도메인별로 열거돼 있다면)

- [ ] **Step 1: 웹 테스트를 CI 에 넣는다**

**현재 어떤 워크플로도 `node --test` 를 돌리지 않는다.** `node --test` 는 README 58줄에만
있고 `pages.yml`·`collect-*.yml` 어디에도 없다 — 전망 도메인의 웹 테스트도 지금까지
CI 에서 한 번도 돌지 않았다. 고용동향 웹 테스트를 새로 만들었으니 여기서 함께 연다.

`.github/workflows/pages.yml` 의 `- run: python -m pytest -q tools` 아래에 넣는다.

```yaml
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
      - name: Web tests
        run: >-
          node --test "core/tests/*.mjs" "hub/tests/*.mjs"
          "domains/forecast/tests/web/*.mjs" "domains/employment/tests/web/*.mjs"
```

`collect-employment.yml` 은 데이터 수집용이므로 건드리지 않는다 — 웹 테스트는
데이터와 무관하고, 매일 밤 실패를 두 곳에서 보고받을 이유가 없다.

Run: `node --test "domains/employment/tests/web/*.mjs"`
Expected: PASS — 워크플로에 넣기 전에 로컬에서 같은 명령이 통과해야 한다.

- [ ] **Step 2: 빌드 산출물을 확인한다**

```bash
python -m tools.build
ls _site/employment
```
Expected: `index.html`·`js/`·`css/`·`data/`·`core/` 가 있다.

- [ ] **Step 3: 허브 활성화를 다시 확인한다**

```bash
git diff --stat HEAD~13 -- hub tools/build.py
```
Expected: **빈 출력**. 허브 코드와 `build.py` 를 고치지 않고 버튼이 켜졌다는 증거다.

- [ ] **Step 4: 실기기 확인**

`python -m tools.serve` 를 띄우고 같은 네트워크의 휴대폰에서 `http://<PC IP>:8642/employment/` 를 연다. 확인 항목:
1. 세그먼트 3개 전환
2. 연·월 스위처로 2025-03 선택 → 카드 세 장이 그 달로 바뀐다
3. 사업체노동력조사 미발표 카드에 직전달 값이 회색으로 붙는다
4. 단면별 → 성별에서 사업체노동력조사 열이 `―` 이고 안내 문장이 보인다
5. 시트를 열고 세그먼트를 옮겨도 열린 채 유지된다
6. `표로 보기` 가 동작한다

- [ ] **Step 5: README 를 갱신한다**

수집기 표에 고용동향 성·연령 추가를 반영하고, 실행 명령에 웹 테스트 경로를 더한다.

- [ ] **Step 6: 커밋**

```bash
git add README.md .github/workflows
git commit -m "docs: 고용동향 화면 공개 반영"
```

---

## Self-Review

**1. 스펙 커버리지**

| 스펙 절 | 태스크 |
|---|---|
| 2.1 만명 단위 | Task 6 (`fmtLevel`·`fmtDelta`) |
| 2.2 연·월 스위처, 하한 규칙 | Task 6 (`monthOptions`), Task 10 (스위처 UI) |
| 2.3 네 상태 | Task 7 (`cellState`), Task 11 (표기·범례) |
| 3.1 성·연령 수집 가능성 | Task 2·3 |
| 3.2 `segments.json` | Task 4 |
| 4 `data.js` 함수 표면 | Task 6·7·8 |
| 5 총괄 화면(미발표 카드·KOSIS 갱신일·coverage 상시) | Task 10 |
| 6 단면별 화면(토글·정렬·펼침·안내문) | Task 11 |
| 7 출처비교 화면 | Task 12 |
| 8 시트(셸 소유·기준 단면·색·값 라벨·표로 보기) | Task 9·13 |
| 9 수집기 확장(중첩 열 배제·세 표 판별·커버리지) | Task 2·3 |
| 10 앱 셸·허브 무수정 | Task 10 Step 4, Task 14 Step 3 |
| 11 테스트(판별력 왕복) | 전 태스크 Step 5 |
| 12 완료 기준 | Task 14 |

**2. 이름 일관성**

`SOURCE_ORDER`·`SOURCE_COLORS`·`monthOptions`·`overviewCards`·`segmentsOf`·`breakdownMatrix`·`categoryTimeline`·`sheetData`·`barsSvg`·`timelineSvg`·`sheetTable`·`mountSheet` 가 정의 태스크와 소비 태스크에서 같은 철자로 쓰였음을 확인했다. 상태 문자열은 `value`/`notProvided`/`unpublished`/`noDelta` 넷으로 고정이며 Task 7·8·9·11 이 같은 값을 쓴다.

**3. 남은 위험**

- Task 5 는 네트워크와 `KOSIS_API_KEY` 가 필요하다. 실패하면 Task 6 이후를 진행할 수는 있으나(테스트는 픽스처 기반) 화면 확인이 부실해진다.
- Task 10 의 `make_icons.py` 수정은 전망 도메인의 기존 아이콘 생성을 깨지 않아야 한다 — 인자 없이 실행하면 예전과 같게 동작하도록 기본값을 유지한다.
