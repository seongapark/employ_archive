# A단계 플랫폼 리팩터 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 전망 전용 단일 앱을 도메인별 독립 앱 구조로 옮기고, 공유 `core/`·허브·사이트 조립 도구를 세워 이후 고용동향 도메인을 폴더 추가만으로 붙일 수 있게 한다.

**Architecture:** 저장소 하나에 `core/`(공유 껍데기 원본), `hub/`(4버튼 런처), `domains/<이름>/{app,data,pipeline,tests}`(수직 슬라이스)를 둔다. `tools/build.py`가 이 소스들을 `_site/`로 조립하며, GitHub Pages 배포와 로컬 개발 서버가 **같은 조립 함수**를 쓴다. 기능 추가는 없다 — 화면과 동작은 리팩터 전후로 동일해야 한다.

**Tech Stack:** Python 3.12 (pydantic, requests, curl_cffi, pytest), 바닐라 ES 모듈 + `node:test`, GitHub Actions / Pages

**Spec:** `docs/superpowers/specs/2026-08-29-고용데이터아카이브-플랫폼-design.md`

## Global Constraints

- **`git add -A` / `git commit -a` 를 쓰지 않는다.** 나중에 이 저장소에서 두 세션이
  병렬로 작업할 수 있고, 그때 `-A` 한 번이면 상대 세션의 작업 중인 파일이 통째로
  딸려 들어간다. 항상 그 태스크가 만든 경로만 명시해서 add 한다.

- **화면 변화 0.** 이 단계는 순수 리팩터다. 눈에 보이는 동작·레이아웃이 바뀌면 실패다.
- **절대경로 금지.** 배포 사이트 루트는 `/` 가 아니라 `/employ_archive/` 다(GitHub 저장소명이 `employ_archive`). `/core/tokens.css` 같은 절대경로는 전부 깨진다. 항상 상대경로를 쓴다.
- **`core/`는 작게 유지한다.** 도메인이 무엇을 다루는지 몰라도 되는 것만 넣는다. 라우터·차트·데이터 스키마·도메인 색 토큰은 넣지 않는다.
- **도메인 색 토큰은 도메인 CSS에서 선언한다.** 전망의 `--badge-verified-*` 등 confidence 배지 토큰은 `core/tokens.css`가 아니라 전망 앱 CSS가 갖는다.
- **테스트는 네트워크 없이 돈다.** 기존 원칙이며 이번에도 유지한다.
- **파이썬 실행 진입점은 `python -m <패키지경로>` 형식을 쓴다.** 이동 후 수집 명령은 `python -m domains.forecast.pipeline.collect` 다.
- **GitHub 저장소 이름은 바꾸지 않는다.** 로컬 폴더명만 바꾼다. 저장소명을 바꾸면 Pages URL이 바뀌어 이미 공유한 링크가 전부 깨진다.

## 설계 변경: core는 도메인마다 복사 배포한다

스펙 4장은 `core/*` → `/core/` 한 곳으로 배포하고 앱이 `../core/`로 참조한다고 썼다.
코드를 읽으며 이것이 **서비스워커 스코프와 충돌**함을 확인했다.

`domains/forecast/app/sw.js`는 `/employ_archive/forecast/sw.js`로 배포되므로 스코프가
`/employ_archive/forecast/` 다. 이 스코프 밖인 `/employ_archive/core/*` 요청은 이 SW의
`fetch` 핸들러를 타지 않는다. 즉 오프라인에서 스타일시트가 통째로 빠져 앱이 무너진다.
GitHub Pages에서는 `Service-Worker-Allowed` 헤더를 설정할 수 없어 스코프를 넓힐 수도 없다.

따라서 조립 규칙을 이렇게 바꾼다:

| 원본 | 배포 경로 |
|---|---|
| `hub/*` | `/` |
| `core/*` | `/core/` **그리고** `/<도메인>/core/` |
| `domains/<d>/app/*` | `/<d>/` |
| `domains/<d>/data/*` | `/<d>/data/` |

앱은 `./core/tokens.css`로 참조한다. 원본 파일은 여전히 `core/` 하나뿐이고 사람이 손대는
곳도 한 곳이므로 드리프트는 발생하지 않는다. 복사는 빌드 산출물에서만 일어난다.
**Task 5에서 스펙 문서의 4장·5장을 이 내용으로 갱신한다.**

---

## File Structure

**신규**

- `tools/__init__.py` — `tools`를 패키지로 만든다 (`python -m tools.build` 실행용)
- `tools/build.py` — 도메인 자동 발견 + `_site` 조립. 배포·로컬 공용 단일 원본
- `tools/serve.py` — `build_site` 호출 후 `_site`를 로컬 서빙
- `tools/tests/test_build.py` — 조립 규칙 검증 (임시 트리 사용, 저장소 상태와 무관)
- `core/tokens.css` — 색·타이포 토큰 (도메인 중립분만)
- `core/base.css` — body·헤더·카드·배지 골격·오프라인배너·고지문구·delta
- `core/shell.js` — `loadJson`, `hubHref`
- `core/tests/shell.test.mjs` — `loadJson` 동작 검증
- `hub/index.html` — 4버튼 런처
- `hub/css/hub.css` — 런처 전용 스타일
- `hub/js/state.js` — 도메인 목록과 상태 판정 순수 함수 (import 없음, 테스트 대상)
- `hub/js/hub.js` — `last_run.json` 조회 후 카드 렌더링
- `hub/sw.js` — 구 서비스워커 폐기용 kill-switch
- `hub/tests/state.test.mjs` — 상태 판정 순수 함수 검증
- `domains/__init__.py`, `domains/forecast/__init__.py` — 파이썬 패키지 경로 확보
- `.github/workflows/collect-forecast.yml` — 기존 `collect.yml` 대체

**이동 (git mv, 내용 대부분 그대로)**

- `src/` → `domains/forecast/pipeline/`
- `data/` → `domains/forecast/data/`
- `tests/` → `domains/forecast/tests/`
- `web/` → `domains/forecast/app/`

**수정**

- `domains/forecast/tests/*.py` — `src.` 접두 import 경로 갱신
- `domains/forecast/app/index.html` — core 참조, 홈 버튼 추가
- `domains/forecast/app/css/styles.css` → `app.css`로 개명, core로 뺀 규칙 제거
- `domains/forecast/app/js/app.js` — `loadJson` 제거하고 core의 것 사용
- `domains/forecast/app/sw.js` — 셸 자산 목록에 core 추가
- `domains/forecast/tests/web/data.test.mjs` — import 경로 갱신
- `tools/make_icons.py` — 출력 경로 갱신
- `.github/workflows/pages.yml` — `tools.build` 사용
- `README.md`, 스펙 문서 4·5장
- `.gitignore` — `_site/` 추가

**삭제**

- `.github/workflows/collect.yml` (collect-forecast.yml로 대체)

---

### Task 1: 사이트 조립·서빙 도구

가장 먼저 만든다. 이후 모든 이동 작업의 목표 레이아웃을 이 함수가 정의하며,
저장소 상태와 무관한 임시 트리로 테스트하므로 지금 시점에 독립적으로 검증 가능하다.

**Files:**
- Create: `tools/__init__.py`, `tools/build.py`, `tools/serve.py`
- Create: `tools/tests/__init__.py`, `tools/tests/test_build.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `tools.build.REPO: Path` — 저장소 루트
  - `tools.build.discover_domains(repo: Path) -> list[str]` — `domains/<이름>/app` 이 있는 이름들을 정렬해 반환
  - `tools.build.build_site(repo: Path, out: Path) -> Path` — `out`을 비우고 조립, `out` 반환

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tools/tests/test_build.py`:

```python
import json
from pathlib import Path

from tools.build import build_site, discover_domains


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "hub").mkdir(parents=True)
    (repo / "hub" / "index.html").write_text("hub", encoding="utf-8")
    (repo / "core").mkdir()
    (repo / "core" / "tokens.css").write_text(":root{}", encoding="utf-8")
    for name in ("forecast", "employment"):
        app = repo / "domains" / name / "app"
        app.mkdir(parents=True)
        (app / "index.html").write_text(name, encoding="utf-8")
        data = repo / "domains" / name / "data"
        data.mkdir()
        (data / "last_run.json").write_text(json.dumps({"errors": []}), encoding="utf-8")
    # app 디렉터리가 없는 폴더는 도메인이 아니다 (문서·작업용 폴더 등)
    (repo / "domains" / "notes").mkdir()
    return repo


def test_discover_domains_requires_app_dir(tmp_path):
    repo = make_repo(tmp_path)
    assert discover_domains(repo) == ["employment", "forecast"]


def test_build_site_places_hub_core_and_domains(tmp_path):
    repo = make_repo(tmp_path)
    out = build_site(repo, tmp_path / "_site")

    assert (out / "index.html").read_text(encoding="utf-8") == "hub"
    assert (out / "core" / "tokens.css").exists()
    assert (out / "forecast" / "index.html").read_text(encoding="utf-8") == "forecast"
    assert (out / "forecast" / "data" / "last_run.json").exists()
    assert (out / "employment" / "index.html").exists()


def test_build_site_copies_core_into_each_domain(tmp_path):
    # 서비스워커 스코프가 도메인 폴더로 제한되므로 core가 도메인 안에도 있어야
    # 오프라인에서 스타일이 유지된다.
    repo = make_repo(tmp_path)
    out = build_site(repo, tmp_path / "_site")

    assert (out / "forecast" / "core" / "tokens.css").exists()
    assert (out / "employment" / "core" / "tokens.css").exists()


def test_build_site_clears_previous_output(tmp_path):
    repo = make_repo(tmp_path)
    out_dir = tmp_path / "_site"
    out_dir.mkdir()
    (out_dir / "stale.html").write_text("old", encoding="utf-8")

    build_site(repo, out_dir)

    assert not (out_dir / "stale.html").exists()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `python -m pytest tools/tests/test_build.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.build'`

- [ ] **Step 3: 최소 구현을 쓴다**

`tools/__init__.py`, `tools/tests/__init__.py` 는 빈 파일로 만든다.

`tools/build.py`:

```python
"""사이트 조립. GitHub Pages 배포와 로컬 서버가 이 함수 하나를 공유한다.

core/ 는 사이트 루트와 각 도메인 폴더 양쪽에 복사한다. 도메인 앱의 서비스워커
스코프가 자기 폴더로 제한되기 때문에, 루트에만 두면 오프라인에서 스타일시트가
빠진다. 원본은 core/ 하나뿐이고 복사는 빌드 산출물에서만 일어난다.
"""
from __future__ import annotations

import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def discover_domains(repo: Path) -> list[str]:
    root = repo / "domains"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "app").is_dir())


def build_site(repo: Path, out: Path) -> Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    core = repo / "core"
    shutil.copytree(repo / "hub", out, dirs_exist_ok=True)
    shutil.copytree(core, out / "core")

    for name in discover_domains(repo):
        dest = out / name
        shutil.copytree(repo / "domains" / name / "app", dest)
        shutil.copytree(core, dest / "core")
        data = repo / "domains" / name / "data"
        if data.is_dir():
            shutil.copytree(data, dest / "data")

    return out


def main() -> int:
    out = build_site(REPO, REPO / "_site")
    print(f"built: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 통과를 확인한다**

Run: `python -m pytest tools/tests/test_build.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: 로컬 서버를 추가한다**

`tools/serve.py`:

```python
"""로컬 개발 서버. 배포와 동일한 조립 결과를 서빙하므로 경로가 배포와 일치한다.

실행: python -m tools.serve  (기본 8642 포트)
"""
from __future__ import annotations

import argparse
import functools
import http.server
import socketserver

from .build import REPO, build_site


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8642)
    args = parser.parse_args()

    out = build_site(REPO, REPO / "_site")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"serving {out} at http://127.0.0.1:{args.port}/")
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: `_site/`를 무시 목록에 넣는다**

`.gitignore` 끝에 한 줄 추가:

```
_site/
```

- [ ] **Step 7: 전체 테스트를 돌린다**

Run: `python -m pytest -q`
Expected: PASS — 기존 테스트 전부 + 새 4개

- [ ] **Step 8: 커밋**

```bash
git add tools/ .gitignore
git commit -m "feat: 사이트 조립·서빙 도구 (배포·로컬 공용)"
```

---

### Task 2: 파이썬 파이프라인·데이터·테스트를 도메인으로 이동

**Files:**
- Move: `src/` → `domains/forecast/pipeline/`
- Move: `data/` → `domains/forecast/data/`
- Move: `tests/` → `domains/forecast/tests/`
- Create: `domains/__init__.py`, `domains/forecast/__init__.py`
- Modify: `domains/forecast/tests/test_collect.py`, `test_imf.py`, `test_models.py`, `test_oecd.py`, `test_store.py`

**Interfaces:**
- Consumes: 없음
- Produces: 파이썬 import 경로 `domains.forecast.pipeline.{collect,store,models}`,
  `domains.forecast.pipeline.collectors.{imf,oecd}`. 수집 진입점은
  `python -m domains.forecast.pipeline.collect`.

**주의:** `src/collect.py:14`의 `DATA_DIR`과 `src/models.py:15`의 `_INDICATORS_PATH`는
`Path(__file__).resolve().parent.parent / "data"` 형태라 이동 후에도
`domains/forecast/data`를 정확히 가리킨다. **건드리지 않는다.**
`domains/forecast/tests/test_metadata.py`의 `DATA`, `test_oecd.py`의 `FIXTURE`도
같은 이유로 수정이 필요 없다. `collect.py` 내부의 `from . import store` 같은
상대 import도 그대로 유효하다.

- [ ] **Step 1: 이동 전 기준선을 확인한다**

Run: `python -m pytest -q`
Expected: PASS — 이동 후 같은 결과가 나와야 하므로 통과 개수를 기록해 둔다.

- [ ] **Step 2: git mv로 옮긴다**

```bash
mkdir -p domains/forecast
git mv src domains/forecast/pipeline
git mv data domains/forecast/data
git mv tests domains/forecast/tests
```

- [ ] **Step 3: 패키지 초기화 파일을 만든다**

빈 파일 두 개를 만든다.

```bash
touch domains/__init__.py domains/forecast/__init__.py
git add domains/__init__.py domains/forecast/__init__.py
```

- [ ] **Step 4: 실패를 확인한다**

Run: `python -m pytest -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src'`

- [ ] **Step 5: 테스트의 import 경로를 고친다**

`domains/forecast/tests/test_collect.py` 3–4행:

```python
from domains.forecast.pipeline.models import ForecastRecord, make_id
from domains.forecast.pipeline import collect, store
```

`domains/forecast/tests/test_imf.py` 2행:

```python
from domains.forecast.pipeline.collectors import imf
```

`domains/forecast/tests/test_models.py` 3행:

```python
from domains.forecast.pipeline.models import ForecastRecord, make_id, VALUE_RANGES, INDICATOR_META
```

`domains/forecast/tests/test_oecd.py` 3행:

```python
from domains.forecast.pipeline.collectors import oecd
```

`domains/forecast/tests/test_store.py` 2–3행:

```python
from domains.forecast.pipeline.models import ForecastRecord, make_id
from domains.forecast.pipeline import store
```

- [ ] **Step 6: 통과를 확인한다**

Run: `python -m pytest -q`
Expected: PASS — Step 1과 동일한 통과 개수

- [ ] **Step 7: 수집 진입점이 살아 있는지 확인한다**

Run: `python -c "from domains.forecast.pipeline import collect; print(sorted(collect.COLLECTORS))"`
Expected: `['imf', 'oecd']`

Run: `python -c "from domains.forecast.pipeline.collect import DATA_DIR; print(DATA_DIR.name, (DATA_DIR / 'forecasts.json').exists())"`
Expected: `data True`

- [ ] **Step 8: 커밋**

```bash
git add domains/ .github/ README.md
git commit -m "refactor: 전망 파이프라인·데이터·테스트를 domains/forecast로 이동"
```

---

### Task 3: core 추출과 전망 웹앱 이동

**Files:**
- Move: `web/` → `domains/forecast/app/`
- Create: `core/tokens.css`, `core/base.css`, `core/shell.js`
- Create: `core/tests/shell.test.mjs`
- Rename: `domains/forecast/app/css/styles.css` → `domains/forecast/app/css/app.css`
- Modify: `domains/forecast/app/index.html`, `js/app.js`, `sw.js`
- Modify: `domains/forecast/tests/web/data.test.mjs`
- Modify: `tools/make_icons.py`

**Interfaces:**
- Consumes: `tools.build.build_site` (Task 1) — 로컬 확인에 사용
- Produces:
  - `core/shell.js` → `loadJson(path: string): Promise<object|null>`,
    `hubHref(): string`
  - CSS 계약: `core/tokens.css`가 CSS 변수를, `core/base.css`가 공통 골격을 정의하고
    도메인 앱 CSS가 그 위에 자기 화면 규칙만 얹는다.

**중요 — `./core/`는 조립된 사이트에서만 해석된다.** 소스 트리에서 `core/`는 저장소
루트에 있고 앱 폴더 아래로는 `tools.build`가 복사할 때만 생긴다. 따라서
`domains/forecast/app/index.html`을 `file://`로 직접 열면 스타일과 모듈이 전부 깨진다.
**앱 확인은 반드시 `python -m tools.serve`로 한다.** 에디터가 `./core/tokens.css`를
"없는 파일"로 표시하는 것도 정상이며, 경로를 `../../../core/`로 "고치면" 배포본이 깨진다.

- [ ] **Step 1: 웹앱을 옮기고 CSS 파일명을 바꾼다**

```bash
git mv web domains/forecast/app
git mv domains/forecast/app/css/styles.css domains/forecast/app/css/app.css
mkdir -p core/tests
```

- [ ] **Step 2: `core/tokens.css`를 만든다**

`domains/forecast/app/css/app.css`의 1–36행(`:root` 블록과 다크모드 블록)을 옮기되,
**confidence 배지 토큰 6개는 남긴다**(전망 도메인 전용이므로).

`core/tokens.css` — 아래가 전체 내용이다. 원본 1–36행에서 `--badge-*` 여섯 개만 뺀 것이다.

```css
:root {
  --bg: #eef0f3;
  --card: #ffffff;
  --border: #e2e5ea;
  --text: #191d24;
  --text-secondary: #667085;
  --text-muted: #98a2b3;
  --accent: #23508f;
  --accent-light: #e7edf6;
  --link: #23508f;
  --link-hover: #1a3c6e;
  --up: #c73e3a;
  --down: #2f6bd0;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #15181d;
    --card: #1e232b;
    --border: #2c333d;
    --text: #e6e9ee;
    --text-secondary: #8b95a3;
    --accent-light: #1d2c42;
    --link: #7ea6dd;
    --link-hover: #9dbde8;
  }
}
```

- [ ] **Step 3: `core/base.css`를 만든다**

`app.css`에서 아래 선택자 규칙을 잘라내 옮긴다. 값은 한 글자도 바꾸지 않는다.

```
* (box-sizing) / body / button / a / a:hover / .num / .app
.header / .header__title / .header__meta
.offline-banner / .offline-banner[hidden]
.screen / .notice / .card
.badge (기본 규칙만)
.delta / .delta-up / .delta-down / .delta-flat
```

여기에 홈 버튼 규칙을 새로 추가한다:

```css
.header__home {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  margin-right: 8px;
  color: var(--text-secondary);
  flex: none;
}
```

- [ ] **Step 4: `app.css`에 남는 것을 정리한다**

`app.css`에는 전망 화면 전용 규칙만 남긴다:

```
.tabbar / .tab / .tab span / .tab--active / .tab--active span
.badge--verified / .badge--extracted / .badge--reviewed
.pill / .pill--active
.band / .band__title / .band__meta
.missing-row / .missing-row__names / .missing-row__label
```

그리고 파일 맨 위에 배지 토큰을 도메인 소유로 선언한다:

```css
/* confidence 배지는 전망 도메인 전용 개념이므로 토큰도 이 앱이 갖는다. */
:root {
  --badge-verified-fg: #17714a;
  --badge-verified-bg: #e5f3ec;
  --badge-extracted-fg: #9a6b15;
  --badge-extracted-bg: #faf0dc;
  --badge-reviewed-fg: #2458a6;
  --badge-reviewed-bg: #e5edfa;
}

@media (prefers-color-scheme: dark) {
  :root {
    --badge-verified-bg: #123526;
    --badge-extracted-bg: #3a2d10;
    --badge-reviewed-bg: #152b4a;
  }
}
```

- [ ] **Step 5: `core/shell.js`의 실패하는 테스트를 쓴다**

`core/tests/shell.test.mjs`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadJson, hubHref } from '../shell.js';

test('loadJson은 200 응답의 JSON을 반환한다', async () => {
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ a: 1 }) });
  assert.deepEqual(await loadJson('./data/x.json'), { a: 1 });
});

test('loadJson은 non-ok 응답에 null을 반환한다', async () => {
  globalThis.fetch = async () => ({ ok: false, json: async () => ({ a: 1 }) });
  assert.equal(await loadJson('./data/x.json'), null);
});

test('loadJson은 네트워크 예외를 삼키고 null을 반환한다', async () => {
  globalThis.fetch = async () => { throw new Error('offline'); };
  assert.equal(await loadJson('./data/x.json'), null);
});

test('hubHref는 상위 폴더를 가리킨다 (Pages 하위경로 배포 대응)', () => {
  assert.equal(hubHref(), '../');
});
```

- [ ] **Step 6: 실패를 확인한다**

Run: `node --test core/tests/`
Expected: FAIL — `Cannot find module .../core/shell.js`

- [ ] **Step 7: `core/shell.js`를 구현한다**

```javascript
// 도메인 공통 셸 유틸. 도메인이 무엇을 다루는지 몰라도 되는 것만 둔다.

// 조립된 사이트에서 앱과 데이터는 항상 같은 폴더 아래 있으므로 후보 경로 폴백이
// 필요 없다. 로컬(tools.serve)도 배포와 동일한 트리를 서빙한다.
export async function loadJson(path) {
  try {
    const res = await fetch(path, { cache: 'no-cache' });
    if (res.ok) return await res.json();
  } catch {
    /* 오프라인 등 네트워크 실패 */
  }
  return null;
}

// 사이트가 /employ_archive/ 하위에 배포되므로 절대경로를 쓰면 안 된다.
export function hubHref() {
  return '../';
}
```

- [ ] **Step 8: 통과를 확인한다**

Run: `node --test core/tests/`
Expected: PASS (4 tests)

- [ ] **Step 9: `index.html`을 갱신한다**

`domains/forecast/app/index.html`에서 스타일시트 링크를 셋으로 바꾼다.
기존 `<link rel="stylesheet" href="./css/styles.css">` 한 줄을 아래로 교체한다:

```html
  <link rel="stylesheet" href="./core/tokens.css">
  <link rel="stylesheet" href="./core/base.css">
  <link rel="stylesheet" href="./css/app.css">
```

그리고 헤더에 홈 버튼을 추가한다. `<header class="header">` 안 맨 앞에 넣는다:

```html
      <a class="header__home" href="../" aria-label="홈으로">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"></path><path d="M5 9.5V21h14V9.5"></path></svg>
      </a>
```

- [ ] **Step 10: `app.js`에서 `loadJson`을 걷어낸다**

`domains/forecast/app/js/app.js` 최상단 import 블록에 한 줄을 더한다:

```javascript
import { loadJson } from '../core/shell.js';
```

그리고 파일 안의 `loadJson` 함수 정의(주석 포함 `async function loadJson(path) { … }` 전체)를
삭제한다. 호출부 `loadJson('data/forecasts.json')` 등 네 곳은 상대경로를 명시하도록 바꾼다:

```javascript
  const [records, orgs, indicators, schedule] = await Promise.all([
    loadJson('./data/forecasts.json'),
    loadJson('./data/orgs.json'),
    loadJson('./data/indicators.json'),
    loadJson('./data/schedule.json'),
  ]);
```

- [ ] **Step 11: `sw.js`의 셸 자산 목록을 갱신한다**

`domains/forecast/app/sw.js`의 `SHELL_ASSETS` 배열을 교체한다.
`./css/styles.css` 항목을 지우고 core 세 파일을 넣는다:

```javascript
const SHELL_ASSETS = [
  './',
  './index.html',
  './core/tokens.css',
  './core/base.css',
  './core/shell.js',
  './css/app.css',
  './js/app.js',
  './js/data.js',
  './js/screens/home.js',
  './js/screens/org.js',
  './js/screens/compare.js',
  './js/screens/timeline.js',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
];
```

`CACHE` 상수는 `'forecast-v1'` 그대로 둔다. 이 SW는 network-first라 버전 상수를
올릴 필요가 없다(파일 상단 주석이 그 이유를 설명한다).

- [ ] **Step 12: 웹 테스트의 import 경로를 고친다**

`domains/forecast/tests/web/data.test.mjs` 6행:

```javascript
} from '../../app/js/data.js';
```

- [ ] **Step 13: 아이콘 스크립트 출력 경로를 고친다**

`tools/make_icons.py`에서 `web/icons` 를 가리키는 경로 상수를
`domains/forecast/app/icons` 로 바꾼다. 파일 상단 docstring의 실행 예시도 함께 고친다.

- [ ] **Step 14: 자동 테스트를 돌린다**

Run: `node --test core/tests/ domains/forecast/tests/web/`
Expected: PASS — 기존 data.js 테스트 전부 + shell 4개

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 15: 실제 화면을 확인한다**

Run: `python -m tools.serve`

브라우저에서 `http://127.0.0.1:8642/forecast/` 를 연다. 확인 항목:

1. 홈·기관·비교·타임라인 네 탭이 리팩터 전과 동일하게 그려지는가
2. 색·간격·다크모드가 그대로인가 (OS 다크모드를 켜고 한 번 더 본다)
3. confidence 배지 색이 살아 있는가 (기관 화면)
4. 콘솔에 404나 모듈 로드 오류가 없는가
5. 헤더 왼쪽 홈 버튼이 보이는가 (누르면 아직 404 — Task 4에서 허브를 만든다)

**하나라도 어긋나면 다음 단계로 가지 않는다.** 이 단계의 완료 기준은 화면 변화 0이다.

- [ ] **Step 16: 커밋**

```bash
git add core/ domains/ tools/
git commit -m "refactor: core 추출 + 전망 웹앱을 domains/forecast/app으로 이동"
```

---

### Task 4: 허브와 구 서비스워커 폐기

**Files:**
- Create: `hub/index.html`, `hub/css/hub.css`, `hub/js/state.js`, `hub/js/hub.js`, `hub/sw.js`
- Create: `hub/tests/state.test.mjs`

**Interfaces:**
- Consumes: `core/shell.js`의 `loadJson` (Task 3)
- Produces: `hub/js/state.js` → `DOMAINS: Array<{slug,name,desc}>`,
  `domainState(lastRun: object|null): 'ready'|'pending'`,
  `updatedLabel(lastRun: object|null): string`

**왜 `state.js`를 따로 두는가:** `core/`는 소스 트리에서 저장소 루트에 있고 각 앱 폴더
아래로는 **빌드할 때만** 복사된다. 따라서 `hub/js/hub.js`가 쓰는 `../core/shell.js`는
조립된 `_site`에서만 해석되고 소스 트리에서는 존재하지 않는다. 순수 함수를 import 없는
`state.js`로 분리해야 `node --test`가 소스 트리에서 그대로 돈다. 전망 앱의
`data.js`(순수) / `app.js`(셸) 분리와 같은 패턴이다.

**배경 — kill-switch가 필요한 이유:** 현재 배포본은 `/employ_archive/sw.js`에 스코프 `/`
서비스워커를 등록해 두었다. 리팩터 후 그 자리는 허브가 된다. 옛 SW를 그대로 두면
허브와 모든 도메인 요청을 계속 가로채고 옛 전망 앱 셸을 오프라인 캐시로 물고 있는다.
같은 URL에 자기를 해제하는 SW를 올려두면 브라우저가 다음 방문 때 업데이트를 확인하며
이 파일을 받아 스스로 등록을 지운다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`hub/tests/state.test.mjs`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { domainState, updatedLabel, DOMAINS } from '../js/state.js';

test('DOMAINS는 네 영역을 고정 순서로 갖는다', () => {
  assert.deepEqual(DOMAINS.map(d => d.slug),
    ['forecast', 'employment', 'supply', 'economy']);
});

test('last_run이 없으면 준비중이다', () => {
  assert.equal(domainState(null), 'pending');
});

test('last_run이 있으면 준비됨이다', () => {
  assert.equal(domainState({ run_at: '2026-08-29T15:06:55.311583+09:00' }), 'ready');
});

test('updatedLabel은 월.일 갱신 형태를 만든다', () => {
  assert.equal(updatedLabel({ run_at: '2026-08-29T15:06:55.311583+09:00' }), '08.29 갱신');
});

test('updatedLabel은 값이 없으면 준비중을 돌려준다', () => {
  assert.equal(updatedLabel(null), '준비중');
});

test('updatedLabel은 날짜 필드가 비어도 준비중으로 떨어진다', () => {
  assert.equal(updatedLabel({}), '준비중');
});
```

- [ ] **Step 2: 실패를 확인한다**

Run: `node --test hub/tests/`
Expected: FAIL — `Cannot find module .../hub/js/state.js`

- [ ] **Step 3: `hub/js/state.js`를 구현한다**

import이 없어야 한다. 이 파일은 소스 트리에서 그대로 테스트된다.

```javascript
// 허브의 순수 로직. DOM도 네트워크도 건드리지 않는다.

// 허브는 도메인 목록만 알고 내용은 모른다. 도메인이 사라지면 last_run.json이
// 404가 되어 자동으로 '준비중'이 되고, 붙으면 자동으로 살아난다.
export const DOMAINS = [
  { slug: 'forecast', name: '전망', desc: '기관별 고용·거시 전망치와 수정 이력' },
  { slug: 'employment', name: '고용동향', desc: '경활·사업체노동력·고용행정 3출처 비교' },
  { slug: 'supply', name: '인력수급', desc: '중장기 인력수급전망' },
  { slug: 'economy', name: '경제동향', desc: '거시 지표 동향' },
];

export function domainState(lastRun) {
  return lastRun ? 'ready' : 'pending';
}

// last_run.json의 실제 필드명은 run_at 이다 (수집기가 기록하는 실행 시각).
export function updatedLabel(lastRun) {
  const at = lastRun && lastRun.run_at;
  if (!at) return '준비중';
  return `${at.slice(5, 7)}.${at.slice(8, 10)} 갱신`;
}
```

- [ ] **Step 4: 통과를 확인한다**

Run: `node --test hub/tests/`
Expected: PASS (6 tests)

- [ ] **Step 4b: `hub/js/hub.js`를 구현한다**

렌더링 전용. `../core/shell.js`는 조립된 사이트에서만 해석되므로 이 파일은
`node --test` 대상이 아니다 — Step 8의 브라우저 확인으로 검증한다.

```javascript
import { loadJson } from '../core/shell.js';
import { DOMAINS, domainState, updatedLabel } from './state.js';

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

async function render() {
  const list = document.getElementById('domains');
  if (!list) return;

  for (const d of DOMAINS) {
    const lastRun = await loadJson(`./${d.slug}/data/last_run.json`);
    const ready = domainState(lastRun) === 'ready';

    const el = document.createElement(ready ? 'a' : 'div');
    el.className = ready ? 'domain' : 'domain domain--pending';
    if (ready) el.href = `./${d.slug}/`;
    el.innerHTML = `
      <div class="domain__name">${esc(d.name)}</div>
      <div class="domain__desc">${esc(d.desc)}</div>
      <div class="domain__meta num">${esc(updatedLabel(lastRun))}</div>`;
    list.appendChild(el);
  }
}

render();
```

- [ ] **Step 5: `hub/index.html`을 만든다**

```html
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#23508f">
  <title>고용데이터 아카이브</title>
  <link rel="icon" href="./forecast/icons/icon-192.png">
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap">
  <link rel="stylesheet" href="./core/tokens.css">
  <link rel="stylesheet" href="./core/base.css">
  <link rel="stylesheet" href="./css/hub.css">
</head>
<body>
  <div class="app">
    <header class="header">
      <div class="header__title">고용데이터 아카이브</div>
    </header>
    <main class="screen">
      <div id="domains" class="domains"></div>
    </main>
    <div class="notice">본 서비스는 개인이 제작한 비공식 참고자료이며, 각 기관 원문이 정본입니다.</div>
  </div>
  <script type="module" src="./js/hub.js"></script>
</body>
</html>
```

- [ ] **Step 6: `hub/css/hub.css`를 만든다**

```css
.domains {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.domain {
  display: block;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  color: var(--text);
}

.domain__name {
  font-size: 17px;
  font-weight: 600;
}

.domain__desc {
  margin-top: 4px;
  font-size: 13px;
  color: var(--text-secondary);
}

.domain__meta {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-muted);
}

.domain--pending {
  opacity: 0.5;
}
```

- [ ] **Step 7: `hub/sw.js`에 kill-switch를 넣는다**

```javascript
// 구 서비스워커 폐기용.
//
// 리팩터 전 배포본은 이 URL(/employ_archive/sw.js)에 전망 앱의 서비스워커를
// 스코프 '/'로 등록해 두었다. 그 등록이 남아 있으면 허브와 모든 도메인 요청을
// 계속 가로채고 옛 앱 셸을 오프라인 캐시로 물고 있는다.
//
// 브라우저는 기존 등록이 있으면 다음 방문 때 이 URL의 업데이트를 확인하므로,
// 자기를 해제하고 캐시를 비우는 이 파일을 올려두면 옛 등록이 스스로 정리된다.
// 각 도메인 앱은 자기 폴더 아래 자기 서비스워커를 따로 갖는다.
//
// 이 파일은 지우지 말 것 — 지우면 404가 되어 옛 등록이 그대로 살아남는다.

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.map((name) => caches.delete(name)));
    await self.registration.unregister();
    const clients = await self.clients.matchAll({ type: 'window' });
    for (const client of clients) client.navigate(client.url);
  })());
});
```

**허브는 이 파일을 `register()` 하지 않는다.** 등록된 적 있는 브라우저만 이 파일을
받아 스스로 정리하면 되고, 새 방문자에게 새 등록을 만들 이유가 없다.

- [ ] **Step 8: 조립 결과를 확인한다**

Run: `python -m pytest tools/tests/test_build.py -q`
Expected: PASS — 허브가 생겼으므로 조립 테스트가 여전히 통과해야 한다

Run: `python -m tools.serve`

브라우저에서 `http://127.0.0.1:8642/` 를 연다. 확인 항목:

1. 네 개 카드가 보이고, **전망만 활성**이며 나머지 셋은 흐리게 '준비중'인가
2. 전망 카드에 `MM.DD 갱신`이 표시되는가
3. 전망 카드를 누르면 `/forecast/`로 들어가는가
4. 전망 앱 헤더의 홈 버튼을 누르면 허브로 돌아오는가
5. 다크모드에서도 정상인가

- [ ] **Step 9: 커밋**

```bash
git add hub/
git commit -m "feat: 허브 런처 + 구 서비스워커 폐기"
```

---

### Task 5: 워크플로 분리와 문서 갱신

**Files:**
- Create: `.github/workflows/collect-forecast.yml`
- Delete: `.github/workflows/collect.yml`
- Modify: `.github/workflows/pages.yml`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-29-고용데이터아카이브-플랫폼-design.md` (4장·5장)

**Interfaces:**
- Consumes: `python -m domains.forecast.pipeline.collect` (Task 2), `python -m tools.build` (Task 1)
- Produces: 없음 (CI 설정)

- [ ] **Step 1: 수집 워크플로를 도메인용으로 바꾼다**

`.github/workflows/collect-forecast.yml` 을 만든다:

```yaml
name: collect-forecast

on:
  schedule:
    - cron: "0 7 * * *" # 07:00 UTC = 16:00 KST
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: collect-forecast
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
      - run: python -m pytest -q
      - run: python -m domains.forecast.pipeline.collect
      - name: Commit data
        run: |
          git config user.name "forecast-bot"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add domains/forecast/data/
          git diff --cached --quiet || git commit -m "data: daily collect $(date -u +%F)"
          git push
      - name: Fail on collector errors
        run: |
          python -c "import json,sys; errs=json.load(open('domains/forecast/data/last_run.json',encoding='utf-8'))['errors']; print('\n'.join(errs)); sys.exit(1 if errs else 0)"
```

그리고 옛 파일을 지운다:

```bash
git rm .github/workflows/collect.yml
```

**도메인별 분리의 요점:** 고용동향 수집기가 추가되면 `collect-employment.yml`을
같은 형태로 하나 더 만든다. 한 도메인의 수집 실패가 다른 도메인의 잡을 빨간불로
만들지 않는다.

- [ ] **Step 2: 배포 워크플로를 조립 도구로 바꾼다**

`.github/workflows/pages.yml` 의 `paths`와 `Build site` 스텝을 교체한다.
나머지(권한·concurrency·업로드·배포 스텝)는 그대로 둔다.

```yaml
on:
  push:
    branches: [main]
    paths:
      - "hub/**"
      - "core/**"
      - "domains/**"
      - "tools/build.py"
      - ".github/workflows/pages.yml"
  schedule:
    - cron: "20 7 * * *" # 16:20 KST — 일일 수집(16:00) 20분 후 재배포
  workflow_dispatch:
```

`Build site` 스텝:

```yaml
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Build site
        run: python -m tools.build
```

`upload-pages-artifact` 의 `path: _site` 는 그대로다.

- [ ] **Step 3: 워크플로 문법을 검증한다**

Run: `python -c "import yaml,glob;[yaml.safe_load(open(f,encoding='utf-8')) for f in glob.glob('.github/workflows/*.yml')];print('ok')"`
Expected: `ok`

(`yaml`이 없으면 `pip install pyyaml` 후 실행한다. 요구사항 파일에는 추가하지 않는다.)

- [ ] **Step 4: README를 갱신한다**

`## 구조` 절과 `## 실행` 절의 본문을 아래 내용으로 교체한다.

구조 절 본문:

````
- `core/` — 도메인 공통 껍데기(토큰·기본 스타일·셸 유틸). 원본은 여기 하나뿐이며
  빌드 시 사이트 루트와 각 도메인 폴더로 복사된다
- `hub/` — 4개 영역 런처. 도메인의 `data/last_run.json` 유무로 활성/준비중을 판정한다
- `domains/<이름>/` — 도메인 수직 슬라이스. `app/`(화면) `data/`(데이터)
  `pipeline/`(수집기) `tests/`
- `tools/build.py` — 사이트 조립. 배포와 로컬 서버가 이 함수를 공유한다
- `.github/workflows/` — 도메인별 수집 + Pages 배포
````

실행 절 본문 (bash 코드블록):

````
pip install -r requirements.txt
python -m pytest                              # 파이썬 테스트 (네트워크 불필요)
node --test core/tests/ hub/tests/ domains/forecast/tests/web/   # 웹 테스트
python -m tools.serve                         # 로컬 서버 (http://127.0.0.1:8642/)
python -m domains.forecast.pipeline.collect   # 전망 수집 1회
````

그리고 실행 절 마지막의 "웹앱: `web/` (GitHub Pages 자동 배포, 로컬은
`python -m http.server` 후 `/web/` 접속)" 문장을 아래로 바꾼다:

````
웹앱은 `python -m tools.serve` 로 조립된 사이트를 그대로 띄운다. 앱 폴더의 `index.html`을
`file://`로 직접 열면 `./core/` 참조가 깨지므로 반드시 이 서버를 쓴다.
````

- [ ] **Step 5: 스펙 문서를 실제 구조에 맞춘다**

`docs/superpowers/specs/2026-08-29-고용데이터아카이브-플랫폼-design.md` 4장의
배포 경로 표에서 `core/*` 행을 아래로 바꾼다:

```markdown
| `core/*` | `/core/` 및 `/<d>/core/` |
```

그리고 그 표 아래 문단 "각 앱은 `<link rel="stylesheet" href="../core/tokens.css">` 로
core를 참조한다. 배포본에서 `/employment/` 기준 `../core/`는 `/core/`로 해석된다."를
아래로 교체한다:

```markdown
각 앱은 `./core/tokens.css` 로 자기 폴더 아래의 복사본을 참조한다. core를 루트 한 곳에만
두지 않는 이유는 서비스워커 스코프다. 도메인 앱의 SW는 `/<d>/` 스코프로 제한되므로
`/core/` 요청을 가로챌 수 없고, 그러면 오프라인에서 스타일시트가 통째로 빠진다.
GitHub Pages에서는 `Service-Worker-Allowed` 헤더를 설정할 수 없어 스코프를 넓힐 수도 없다.
사람이 편집하는 원본은 `core/` 하나뿐이며 복사는 빌드 산출물에서만 일어나므로
드리프트 위험은 없다.
```

5장 `core에 넣는 것` 목록의 `shell.js` 항목을 실제 구현에 맞춘다:

```markdown
- `shell.js` — JSON 로더(`loadJson`), 허브 경로(`hubHref`). 화면 요소는 각 앱이 그린다
```

- [ ] **Step 6: 전체 검증**

Run: `python -m pytest -q`
Expected: PASS

Run: `node --test core/tests/ hub/tests/ domains/forecast/tests/web/`
Expected: PASS

Run: `python -m tools.build && ls _site && ls _site/forecast`
Expected: `_site`에 `index.html`, `core`, `forecast` / `_site/forecast`에 `index.html`, `core`, `css`, `js`, `data`, `sw.js`

- [ ] **Step 7: 커밋**

```bash
git add .github/ README.md docs/
git commit -m "ci: 도메인별 수집 워크플로 분리 + 조립 도구 기반 배포"
```

---

### Task 6: 로컬 폴더명 변경

마지막에 한다. 셸의 작업 디렉터리가 바뀌므로 다른 작업 중에 하면 안 된다.
**GitHub 저장소 이름(`employ_archive`)은 바꾸지 않는다** — 바꾸면 Pages URL이 바뀌어
이미 공유한 링크가 전부 깨진다.

**Files:**
- Rename: `C:\Users\seong\Desktop\고용전망아카이브` → `C:\Users\seong\Desktop\고용데이터아카이브`

**Interfaces:**
- Consumes: 없음
- Produces: 없음

- [ ] **Step 1: 워킹트리가 깨끗한지 확인한다**

Run: `git status --short`
Expected: 출력 없음. 남은 변경이 있으면 먼저 커밋한다.

- [ ] **Step 2: 폴더를 옮긴다**

셸을 상위 폴더로 옮긴 뒤 이름을 바꾼다.

```bash
cd /c/Users/seong/Desktop
mv 고용전망아카이브 고용데이터아카이브
cd 고용데이터아카이브
```

- [ ] **Step 3: 저장소가 멀쩡한지 확인한다**

Run: `git status --short && git log --oneline -1`
Expected: 변경 없음, 최신 커밋이 Task 5의 것

Run: `python -m pytest -q`
Expected: PASS

Run: `python -m tools.build`
Expected: `built: .../고용데이터아카이브/_site`

- [ ] **Step 4: 커밋할 것이 없음을 확인한다**

폴더명은 저장소 바깥의 이름이므로 git에 남는 변경이 없다.

Run: `git status --short`
Expected: 출력 없음

**남은 수동 정리 (사용자가 할 일):**

1. 바탕화면·탐색기 고정 등 수동 바로가기를 새 경로로 다시 건다
2. Claude Desktop에서 이 폴더를 직접 지정해 쓰고 있었다면 새 경로로 다시 지정한다
3. 새 폴더에서 `claude`를 처음 실행할 때 신뢰 대화상자를 한 번 다시 승인한다
   (옛 경로의 세션 이력은 `~/.claude/projects/` 아래 옛 키로 남아 있다)

---

## 완료 기준

이 플랜이 끝나면 아래가 모두 참이어야 한다.

- `python -m pytest -q` 통과 (기존 테스트 + 조립 테스트)
- `node --test core/tests/ hub/tests/ domains/forecast/tests/web/` 통과
- `python -m tools.serve` 후 `/` 에서 허브가, `/forecast/` 에서 전망 앱이
  **리팩터 전과 동일한 화면**으로 뜬다 (라이트·다크 양쪽)
- 전망 앱 헤더의 홈 버튼으로 허브에 돌아온다
- 고용동향을 붙일 때 필요한 작업이 `domains/employment/` 폴더 추가와
  `collect-employment.yml` 한 개뿐이다 — 허브·조립·배포는 손대지 않는다
