// sw.js 의 SHELL_ASSETS 는 첫 방문 때 프리캐시할 목록이다. app.js 가 정적으로
// import 하는 모듈 그래프 전체가 여기 없으면, 오프라인으로 다시 열었을 때
// 캐시에도 네트워크에도 없는 모듈이 생겨 ES 모듈 그래프가 통째로 실패한다
// (import 하나가 죽으면 그 파일을 부르는 화면은 물론 app.js 자체가 안 돈다).
//
// 이 사고가 이미 두 번 났다 — 리뷰가 screens/picks.js 누락을 잡았고(지금은
// 목록에 있다), route.js 는 도메인을 만들 때부터 빠진 채 발견되지 않았다.
// 사람이 파일을 하나 만들 때마다 이 목록을 기억해 갱신하는 데 기대지 않고,
// import 그래프를 실제로 훑어 빠진 게 있으면 테스트가 막는다.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP_DIR = path.resolve(HERE, '../../app');
// core/ 는 도메인 공통 셸이라 저장소 루트에 있고, 조립된 사이트에서만
// domains/reports/app/core/ 로 들어온다(app.js 의 '../core/...' 는 그 조립
// 결과 기준이다). 소스 트리에서 실제로 읽으려면 여기서 찾는다 — 다만 이건
// '어디서 읽을지' 문제일 뿐, SHELL_ASSETS 비교에 쓰는 논리 경로(app 루트
// 기준 './core/...')는 항상 app.js 의 import 문 그대로 계산한다.
const REPO_ROOT = path.resolve(APP_DIR, '../../..');

function readShellAssets() {
  const text = fs.readFileSync(path.join(APP_DIR, 'sw.js'), 'utf8');
  const block = text.match(/SHELL_ASSETS\s*=\s*\[([\s\S]*?)\]/);
  assert.ok(block, 'sw.js 에서 SHELL_ASSETS 배열을 못 찾았다');
  return [...block[1].matchAll(/'(\.\/[^']+)'/g)].map((m) => m[1]);
}

// 실제 파일을 읽을 디스크 경로. 조립 전 소스 트리에는 app/core/ 가 없고
// 저장소 루트 core/ 에 있으므로, app 아래서 못 찾으면 거기서 찾는다.
function diskPathFor(logicalPath) {
  const underApp = path.join(APP_DIR, logicalPath);
  if (fs.existsSync(underApp)) return underApp;
  const atRoot = path.join(REPO_ROOT, logicalPath);
  if (fs.existsSync(atRoot)) return atRoot;
  return underApp; // 못 찾아도 돌려준다 — 호출부가 존재 여부를 판단한다.
}

function importsOf(diskAbsFile) {
  const text = fs.readFileSync(diskAbsFile, 'utf8');
  // import 절의 세부 문법(중괄호·개행·* as 등)은 안 가린다 — 'from' 뒤 상대
  // 경로만 뽑으면 충분하고, 이러면 여러 줄에 걸친 import 도 놓치지 않는다.
  return [...text.matchAll(/from\s+['"](\.\.?\/[^'"]+)['"]/g)].map((m) => m[1]);
}

// app.js 에서 시작해 정적 import 그래프를 끝까지 따라간다. 노드마다
// '논리 경로'(app 루트 기준, sw.js 와 같은 좌표계)를 들고 다닌다 — 실제
// 파일을 core/ 처럼 저장소 루트에서 읽더라도 SHELL_ASSETS 비교는 이 좌표계로
// 해야 한다.
function walkModuleGraph(entryLogicalPath) {
  const visited = new Set();
  const queue = [entryLogicalPath];
  while (queue.length) {
    const logicalPath = queue.shift();
    if (visited.has(logicalPath)) continue;
    visited.add(logicalPath);
    const diskPath = diskPathFor(logicalPath);
    if (!fs.existsSync(diskPath)) continue; // 못 찾은 파일은 더 못 따라간다
    const logicalDir = path.posix.dirname(logicalPath);
    for (const spec of importsOf(diskPath)) {
      const nextLogical = path.posix.normalize(path.posix.join(logicalDir, spec));
      if (!visited.has(nextLogical)) queue.push(nextLogical);
    }
  }
  return visited;
}

test('app.js 가 정적 import 하는 모듈이 전부 SHELL_ASSETS 에 있다', () => {
  const shellAssets = new Set(readShellAssets());
  const graph = walkModuleGraph('js/app.js');
  const missing = [...graph]
    .map((logicalPath) => `./${logicalPath}`)
    .filter((shellPath) => !shellAssets.has(shellPath));
  assert.deepEqual(missing, [],
    `SHELL_ASSETS 에 없는 정적 import: ${missing.join(', ')} — ` +
    '오프라인 재방문 때 이 모듈을 못 받으면 ES 모듈 그래프가 통째로 실패한다.');
});

test('실제로 도는 화면 파일 여섯 개가 그래프 안에 있다 — 스캔 자체가 헛돌지 않았는지 확인', () => {
  const graph = walkModuleGraph('js/app.js');
  for (const p of ['js/route.js', 'js/screens/home.js', 'js/screens/picks.js',
    'js/screens/topics.js', 'js/screens/orgs.js', 'js/screens/report.js']) {
    assert.ok(graph.has(p), `${p} 가 그래프에 안 잡혔다 — 스캔 로직을 의심할 것`);
  }
});
