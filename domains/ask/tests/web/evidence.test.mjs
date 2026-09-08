import { test } from 'node:test';
import assert from 'node:assert/strict';
import { evidence, indicatorFallback } from '../../worker/src/core/evidence.mjs';

const T = {
  phenomenon: [{ id: '청년사무직감소', name_ko: '청년 사무직 취업자 감소',
    time_grain: '반기', 근거서술: '2023하 818.3천명 → 2025하 727.4천명, 4반기 연속 감소' }],
  hypothesis: [{ id: 'H3_산업구조', phenomenon_id: '청년사무직감소', name_ko: '산업구조',
    대립가설: '["H1_AI대체","H2_경기순환"]',
    missing_for_verdict: '["IND_청년사무직취업자"]',
    우회경로: '지역별고용조사 수집기 추가(승인 불요)',
    검정력_주석: '모집단 상이 → 증감 방향만. 산업 내 직종 대체 미포착' }],
  hypothesis_verdict: [{ id: 'H3_산업구조', verdict_capable: 0, verdict_strength: null,
    verdict_blocked_by: '데이터미보유', n_falsify: 1, n_missing: 1 }],
  hyp_indicator: [
    { hypothesis_id: 'H3_산업구조', indicator_id: 'IND_KGJ피보험자',
      role: '지지', timing: '수준확인', expected_sign: '-', lead_lag: null },
    { hypothesis_id: 'H3_산업구조', indicator_id: 'IND_청년사무직취업자',
      role: 'falsifies', timing: '특정성', expected_sign: null, lead_lag: null },
  ],
  indicator: [
    { id: 'IND_KGJ피보험자', name_ko: 'K·G·J 피보험자', source_id: 'ei',
      data_status: '보유', time_grain: '월', compare_basis: '증감률만',
      series_key: 'ei:industry:K', 커버리지한계: '미가입 제외' },
    { id: 'IND_청년사무직취업자', name_ko: '청년 사무직 취업자', source_id: 'kosis_지역별고용조사',
      data_status: '미보유', time_grain: '반기', compare_basis: '수준',
      series_key: null, 커버리지한계: 'RSE 미공표' },
  ],
  observation: [
    { source: 'ei', breakdown: 'industry', category: 'K', period: '2026-06', value: 100, unit: '천명', rse: null, rse_flag: null },
    { source: 'ei', breakdown: 'industry', category: 'K', period: '2026-07', value: 98, unit: '천명', rse: null, rse_flag: null },
  ],
};
const db = {
  // 단어 경계로 맞춘다 — 순진한 substring 비교는 'hypothesis' 가 'hypothesis_verdict' 의
  // 접두어라서, 또 'phenomenon' 이 WHERE 절의 'phenomenon_id' 안에 들어 있어서 오매칭된다.
  all: async (sql) => {
    for (const t of Object.keys(T)) if (new RegExp(`\\b${t}\\b`).test(sql)) return T[t];
    return [];
  },
};

test('지지와 반증을 갈라 담는다', async () => {
  const r = await evidence({ db }, { phenomenon_id: '청년사무직감소' });
  const h = r.가설[0];
  assert.equal(h.지지.length, 1);
  assert.equal(h.반증.length, 1);
});

test('판정 불가면 사유를 함께 낸다', async () => {
  const r = await evidence({ db }, { phenomenon_id: '청년사무직감소' });
  assert.equal(r.가설[0].판정.verdict_capable, false);
  assert.equal(r.가설[0].판정.verdict_blocked_by, '데이터미보유');
  assert.equal(r.가설[0].판정.verdict_strength, null);
});

test('미보유 지표는 값 대신 확보 경로를 낸다', async () => {
  const r = await evidence({ db }, { phenomenon_id: '청년사무직감소' });
  const 반증 = r.가설[0].반증[0];
  assert.equal(반증.data_status, '미보유');
  assert.equal(반증.관측, undefined);
  assert.match(반증.우회경로, /수집기 추가/);
});

test('반기 지표를 쓰면 선후 미검정을 한계에 자동으로 넣는다', async () => {
  const r = await evidence({ db }, { phenomenon_id: '청년사무직감소' });
  assert.ok(r.가설[0].한계.some((l) => l.includes('선후관계는 검정하지 않음')));
});

test('현상의 근거서술에 해석이 섞이지 않는다', async () => {
  const r = await evidence({ db }, { phenomenon_id: '청년사무직감소' });
  assert.match(r.현상.근거서술, /4반기 연속 감소/);
  assert.doesNotMatch(r.현상.근거서술, /표본오차로 설명하기 어렵/);
});

test('현상이 미등록이면 지표만 제시하는 폴백으로 간다', async () => {
  const r = await indicatorFallback({ db }, { 주제: '취업자', 집단축: ['직업'] });
  assert.equal(r.판정없음, true);
  assert.equal(r.보유수 + r.미보유수, r.지표.length);
});

test('관측의 unit 을 파생에 단위로 싣는다 — 하드코딩하지 않는다', async () => {
  const r = await evidence({ db }, { phenomenon_id: '청년사무직감소' });
  const 지지 = r.가설[0].지지[0];
  assert.equal(지지.파생.단위, '천명');
});
