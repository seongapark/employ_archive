# 질의응답(ask) 배포 절차

이 문서가 없어서 생기는 사고는 하나다. **허브 첫 카드가 질의응답인데 워커가 없으면,
질문을 넣는 순간 "서버에 연결하지 못했다 — 네트워크 상태를 확인한다" 만 나온다.**
`domains/ask/app/js/ask.js` 의 `API` 상수가 아직 자리표시자
(`https://REPLACE-AFTER-DEPLOY.workers.dev/api/ask`)이기 때문이고, 이건 네트워크 문제가
아니라 배포가 안 끝난 상태다. 아래 순서를 끝까지 밟거나, §4 의 "허브에서 ask 를 빼 두는"
선택지를 쓴다.

> 이 문서의 `wrangler` 명령은 **사람이 로컬에서 한 번 돌리는 것**이다. GitHub Actions 가
> 대신 해 주지 않는다 — 워크플로가 하는 일은 이미 서 있는 D1 에 데이터를 미는 것뿐이다.

---

## 1. 순서

이 순서를 지켜야 한다. 특히 **3번(스키마 적용)이 빠지면 세 워크플로가 전부
`no such table` 로 죽는데, 그중 둘은 `continue-on-error: true` 라 초록으로 죽는다**(§5).

### 1) 병합

`ask/qa-design` → `main`. 병합하는 순간 `pages.yml` 이 돌아 `https://<user>.github.io/<repo>/ask/`
가 생기고, 허브 첫 카드가 질의응답을 가리킨다. 이때부터 §4 의 시계가 돈다.

### 2) 원격 D1 · KV 를 만든다

```bash
cd domains/ask/worker

wrangler d1 create employ-archive-ask
# → database_id 를 출력한다. 받아 적는다.

wrangler kv namespace create QUOTA
# → id 를 출력한다. 받아 적는다.
```

두 값을 `domains/ask/worker/wrangler.jsonc` 의 자리표시자에 넣는다(§3).

### 3) **`0001_init.sql` 을 원격에 적용한다** ← 가장 잘 빠지는 단계

`wrangler d1 create` 는 **빈 데이터베이스**를 만든다. 표는 하나도 없다.

```bash
wrangler d1 execute employ-archive-ask --remote \
  --config domains/ask/worker/wrangler.jsonc \
  --file=domains/ask/worker/migrations/0001_init.sql
```

확인:

```bash
wrangler d1 execute employ-archive-ask --remote \
  --config domains/ask/worker/wrangler.jsonc \
  --command "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
```

`capability` · `capability_limit` · `forecast` · `forecast_rationale` · `hyp_indicator` ·
`hypothesis` · `indicator` · `observation` · `phenomenon` · `release` · `source_catalog` ·
`source_conflict` 가 나와야 한다.

이 단계를 건너뛰면 `sync-catalog` · `collect-employment` · `collect-forecast` 의 D1 스텝이
전부 `no such table: source_catalog` 류로 죽는다. `sync-catalog` 는 빨갛게 죽어서 눈에
띄지만, 나머지 둘은 `continue-on-error: true` 라 **초록으로 죽는다.**

### 4) 시크릿을 넣는다

```bash
wrangler secret put ASK_API_KEY --config domains/ask/worker/wrangler.jsonc
# 프롬프트에 키를 붙여 넣는다. 이 값은 저장소 어디에도 커밋하지 않는다.
```

`ASK_API_BASE` · `ASK_MODEL` · `ASK_DAILY_QUOTA` · `ASK_ALLOWED_ORIGIN` 은 secret 이 **아니다** —
`wrangler.jsonc` 의 `vars` 에 평문으로 둔다(§3).

### 5) 워커를 배포한다

```bash
wrangler deploy --config domains/ask/worker/wrangler.jsonc
# → https://employ-archive-ask.<subdomain>.workers.dev 를 출력한다
```

바로 확인한다:

```bash
curl https://employ-archive-ask.<subdomain>.workers.dev/api/health
# {"ok":true}
```

`/api/health` 는 D1 을 안 건드리므로, 여기가 초록인데 `/api/ask` 가 죽으면 원인은
D1 쪽(3번)이다.

### 6) 카탈로그를 민다

```bash
python -m tools.d1_sync catalog > catalog.sql
wrangler d1 execute employ-archive-ask --remote \
  --config domains/ask/worker/wrangler.jsonc --file=catalog.sql
```

`sync-catalog` 워크플로가 `domains/ask/data/**` 가 바뀔 때마다 이걸 대신 해 주지만,
**첫 회는 사람이 민다** — 병합 시점에 그 경로가 안 바뀌었으면 워크플로가 안 돌기 때문이다.
관측·전망도 채우려면 `collect-employment` · `collect-forecast` 를 `workflow_dispatch` 로
한 번씩 돌린다.

### 7) `API` 상수를 교체한다

`domains/ask/app/js/ask.js`:

```js
const API = 'https://REPLACE-AFTER-DEPLOY.workers.dev/api/ask';   // ← 이 줄을
const API = 'https://employ-archive-ask.<subdomain>.workers.dev/api/ask';  // ← 5번의 실제 주소로
```

이 줄을 커밋해 `main` 에 올리면 `pages.yml` 이 다시 돌아 화면이 갱신된다.

### 8) 재배포 후 확인

- 화면에서 "2026년 7월 30대 취업자는 몇 명인가" 를 물어 카드가 나오는지
- 워커 쪽 `ASK_ALLOWED_ORIGIN` 이 실제 Pages 오리진과 **정확히** 같은지
  (다르면 브라우저 콘솔에 CORS 오류가 뜬다. 지금 값은 `https://seongapark.github.io` 다 —
  사용자·저장소 이름이 다르면 여기서 걸린다)

---

## 2. GitHub Secret 둘

**저장소 → Settings → Secrets and variables → Actions → Repository secrets** 에 넣는다.

| 이름 | 무엇 | 쓰는 곳 |
|---|---|---|
| `CLOUDFLARE_API_TOKEN` | D1 편집 권한이 있는 API 토큰 (Cloudflare 대시보드 → My Profile → API Tokens. `D1:Edit` 권한이면 충분하다) | `sync-catalog` · `collect-employment` · `collect-forecast` 의 D1 스텝 |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare 계정 ID (대시보드 우측, 또는 `wrangler whoami`) | 같음 |

`ASK_API_KEY` 는 **GitHub Secret 이 아니다** — 워커 런타임에서만 필요하므로
`wrangler secret put` 으로만 들어간다(1-4). GitHub Actions 는 LLM 을 부르지 않는다.

---

## 3. `wrangler.jsonc` 의 자리표시자 둘

`domains/ask/worker/wrangler.jsonc`:

| 자리표시자 | 채울 값 |
|---|---|
| `d1_databases[0].database_id` = `"<wrangler d1 create 후 채운다>"` | 1-2 의 `wrangler d1 create employ-archive-ask` 가 출력한 **database_id**(UUID) |
| `kv_namespaces[0].id` = `"<wrangler kv namespace create QUOTA 후 채운다>"` | 1-2 의 `wrangler kv namespace create QUOTA` 가 출력한 **id**(32자 hex) |

같이 확인할 것: `vars.ASK_ALLOWED_ORIGIN` 이 실제 Pages 오리진과 같은지(1-8),
`vars.ASK_API_BASE`(공급자 주소) · `vars.ASK_MODEL`(품질이 모자라면 이 값만 바꾼다) ·
`vars.ASK_DAILY_QUOTA`(IP 별 하루 한도).

**`ASK_DAILY_QUOTA` 는 지금 `500` 이다 — 링크를 남에게 공유하기 전까지의 값이다.**
질문 한 건이 LLM 호출 두 번(슬롯 분해·문장 작성)을 쓰고 그 비용이 `ASK_API_KEY` 주인에게
간다. 공개 링크를 돌리는 시점에 **다시 조인다**(직접 개발·시연 기준으로 `30` 이 원래 값).
바꾸는 방법은 이 줄 하나 고치고 `wrangler deploy` 다.

**공급자를 갈아끼울 때는 코드가 아니라 `ASK_API_BASE`·`ASK_MODEL` 두 줄과 `ASK_API_KEY`
시크릿만 바꾼다.** 요청·응답 형식이 OpenAI 호환이면 그대로 붙는다 — 실제로 한 번
갈아끼웠다(OpenRouter → OpenAI). 다만 **공급자를 바꾸면 모델 선정 근거가 같이 옮겨가지
않는다**: 구조화 출력 지원 여부·유형 분류 정확도·응답 지연을 스파이크로 다시 재고
`ASK_MODEL` 을 정해야 한다.

---

## 4. 워커가 서기 전에는 허브에서 ask 를 빼 두는 선택지

병합과 워커 배포 사이에 시차가 있으면(§1-1 ~ §1-8), 그동안 허브 첫 카드가 오류만 낸다.
그게 싫으면 **`hub/js/state.js` 의 `DOMAINS` 에서 한 줄을 지운다:**

```js
export const DOMAINS = [
  { slug: 'ask', name: '질의응답', desc: '질문으로 찾고, 못 주는 이유까지 답한다' },  // ← 이 줄
  ...
```

지우면 허브 테스트(`hub/tests/state.test.mjs` 의 "DOMAINS는 다섯 영역을 고정 순서로
갖는다")가 빨개진다 — **그게 의도다.** 되돌리는 것을 잊지 않게 해 주는 알람이므로,
빼 두는 동안에는 그 테스트의 기대도 같이 줄이고, 워커가 서면 두 곳을 같이 되돌린다.

허브 입력창 자체(`askHref`)는 `./ask/#/q=...` 로 문자열만 넘기므로, 카드를 빼도
직접 URL 로 들어가면 화면은 그대로 뜬다.

---

## 5. **동기화 실패는 조용하다** — 초록이라고 성공이 아니다

`collect-employment` · `collect-forecast` 의 `D1 동기화` 스텝은 `continue-on-error: true` 다.
의도한 설계다 — D1 이 죽어도 Pages 와 수집(정본 JSON 커밋)은 멀쩡히 돌아야 한다.
그 대가로 **D1 동기화가 며칠째 실패해도 워크플로 실행은 초록으로 끝난다.**

| 워크플로 | D1 스텝 실패 시 | 어떻게 알아채나 |
|---|---|---|
| `sync-catalog` | 실행이 **빨갛게** 죽는다 | 실행 목록에서 바로 보인다 |
| `collect-employment` | 실행은 **초록** | 실행 페이지 상단 요약의 ⚠️ 줄, 또는 `D1 동기화` 스텝 로그 |
| `collect-forecast` | 실행은 **초록** | 같음 |

확인하려면 **실행 로그의 그 스텝을 직접 펼쳐 봐야 한다.** 최소한의 눈에 띄는 장치로,
두 워크플로의 D1 스텝 바로 뒤에 `D1 동기화 실패를 요약에 남긴다` 스텝을 뒀다
(`if: always()` + `steps.d1.outcome` 검사). 실패했으면 실행 페이지 상단 Summary 에
한 줄이 남는다. 그 스텝 자체는 절대 실패하지 않는다 — 실패시키면 `continue-on-error` 의
뜻이 사라진다.

증상별 원인:

- `no such table: …` → §1-3 이 안 됐다. 원격 D1 에 `0001_init.sql` 을 적용한다.
- `Authentication error` / `not found` → §2 의 시크릿 둘을 확인한다.
- 화면은 "서버에 연결하지 못했다" 인데 워커는 살아 있다 → `ASK_ALLOWED_ORIGIN`(CORS) 또는
  `ask.js` 의 `API` 상수(§1-7).
- 카드는 나오는데 근거가 비어 있다 → 워커·D1 은 멀쩡하고 **데이터가 안 밀렸다**. §1-6.
