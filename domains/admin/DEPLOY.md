# 방문 통계(admin) 배포 절차

이 문서가 없어서 생기는 사고는 조용하다. **`core/track.js` 의 `ENDPOINT` 가
자리표시자(`https://REPLACE-AFTER-DEPLOY.workers.dev/api/hit`)인 채로 병합되면,
비콘은 매 화면 전환마다 조용히 실패한다.** track.js 의 불변식이 "통계가 화면을
못 건드린다"이기 때문에 던지지도 않고 콘솔에도 안 남는다 — 앱은 멀쩡히 도는데
통계만 영영 0 이다. 관리자 화면(`domains/admin/app/js/admin.js`)이 띄우는
"워커가 아직 배포되지 않았다 — domains/admin/DEPLOY.md 의 절차를 끝내야 한다"가
이 상태를 알려 주는 유일한 신호다. `domains/admin/app/js/api.js` 의 `API` 상수도
같은 이유로 자리표시자인 채면 안 된다.

> 이 문서의 `wrangler` 명령은 **사람이 로컬에서 한 번 돌리는 것**이다. GitHub
> Actions 는 아무것도 안 해 준다 — 이 도메인은 워크플로를 아예 갖지 않는다.

---

## 1. 순서

```bash
cd domains/admin/worker

wrangler d1 create employ-archive-metrics
# → database_id 를 출력한다. wrangler.jsonc 의 REPLACE-AFTER-D1-CREATE 에 넣는다.

wrangler d1 execute employ-archive-metrics --remote \
  --config wrangler.jsonc --file=migrations/0001_init.sql

wrangler secret put METRICS_TOKEN
# 관리자 화면 로그인 비밀번호다. 저장소 어디에도 커밋하지 않는다.

wrangler deploy
# → https://employ-archive-metrics.<계정>.workers.dev 를 출력한다
```

받은 주소는 바로 확인한다.

```bash
curl https://employ-archive-metrics.<계정>.workers.dev/api/health
# {"ok":true}
```

`/api/health` 는 D1 을 안 건드린다. 여기가 초록인데 `/api/hit`·`/api/stats` 가
죽으면 원인은 마이그레이션(1번 두 번째 명령)이 빠졌거나 `METRICS_TOKEN` 쪽이다.

### 받은 주소를 두 군데에 넣는다

- `core/track.js` 의 `ENDPOINT` → `<주소>/api/hit`
- `domains/admin/app/js/api.js` 의 `API` → `<주소>/api/stats`

이 두 줄을 고쳐 `main` 에 올리면 `pages.yml` 이 다시 돌아 여섯 앱 전부(허브 +
도메인 다섯 + admin)의 `core/track.js` 가 새 주소로 갱신된다 — `tools/build.py`
가 `core/` 를 각 앱 폴더로 복사하기 때문에 한 곳만 고치면 된다.

### 배포 후 확인

1. 배포된 아무 앱이나(허브도 좋다) 한 번 열어 화면을 한 번 전환한다.
2. `domains/admin/` 화면을 열어 토큰을 넣고, 조회 수가 1(방금 낸 것) 이상
   잡히는지 본다.

여기서 관리자 화면이 계속 "워커가 아직 배포되지 않았다"를 띄우면 `api.js` 의
`API` 상수를 실제 주소로 바꾸지 않은 것이다.

---

## 2. 마이그레이션 표

| 파일 | 무엇을 만드나 |
|---|---|
| `0001_init.sql` | `hit`·`visitor` 두 표와 인덱스 셋(`hit_day`·`hit_domain_day`·`visitor_first`) |

---

## 3. `wrangler.jsonc` 의 자리표시자

`domains/admin/worker/wrangler.jsonc`:

| 자리표시자 | 채울 값 |
|---|---|
| `d1_databases[0].database_id` = `"REPLACE-AFTER-D1-CREATE"` | 1번의 `wrangler d1 create employ-archive-metrics` 가 출력한 **database_id**(UUID) |

`METRICS_TOKEN` 은 이 파일에 **적지 않는다** — `wrangler secret put` 으로만
들어가는 시크릿이다. `vars.ALLOWED_ORIGIN` 은 실제 Pages 오리진과 같아야
한다(지금 값은 `https://seongapark.github.io`) — 다르면 비콘·집계 요청이
CORS 로 조용히 막힌다(`src/index.mjs` 의 `수집()` 은 오리진이 안 맞으면
204 를 그냥 돌려주므로 브라우저 콘솔에도 안 남을 수 있다).

---

## 4. 주의 둘

- **`hit`·`visitor` 는 어떤 워크플로도 건드리지 않는다.** `tools/d1_sync.py` ·
  `tools/fts_load.py` 는 ask 의 D1(`employ-archive-ask`)만 본다. 이 워커의 D1
  (`employ-archive-metrics`)은 완전히 다른 데이터베이스이고, 워커 파일 맨 위
  주석에도 적혀 있듯 **일부러 갈라 세웠다** — ask 쪽 동기화 워크플로가 표를
  주기적으로 지우고 다시 채우는데, 같은 DB 를 썼다면 방문 기록이 어느 날
  통째로 사라졌을 것이다. `d1_sync`·`fts_load` 를 이 DB 에 겨누면 실제로 그
  일이 일어난다 — 방문 기록은 보관 기간이 무기한이라 복구할 원본이 없다.
- **토큰을 바꾸려면** `wrangler secret put METRICS_TOKEN` 을 다시 돌리고,
  브라우저에서 관리자 화면의 **토큰 지우기**를 누른 뒤 새 값을 넣는다. 옛
  토큰을 브라우저에 남겨 두면 `/api/stats` 가 401 을 내고, `api.js` 의
  `불러오기()` 가 그 토큰을 지우고 "인증" 상태로 돌아간다 — 다시 넣어야 한다.
