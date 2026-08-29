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
