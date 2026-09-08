// 가설 판정. counter_evidence 와 unknown 은 선택 필드가 아니라 필수다(기획서 §6) —
// "다른 요인은 검토했나?" 를 선제 차단하는 것이 이 도구의 실무 가치다.

import { buildEvidence, queryObservations } from './query.mjs';

const J = (s) => { try { return JSON.parse(s ?? '[]'); } catch { return []; } };

async function loadIndicator(deps, hi, ind, 기간) {
  const i = ind.find((x) => x.id === hi.indicator_id);
  const base = {
    지표: i.id, name_ko: i.name_ko, 출처: i.source_id, role: hi.role,
    timing: hi.timing, expected_sign: hi.expected_sign, lead_lag: hi.lead_lag,
    data_status: i.data_status, time_grain: i.time_grain,
    compare_basis: i.compare_basis,
  };
  if (i.data_status !== '보유') {
    return { ...base, 우회경로: '수집기 추가(승인 불요)', 사유: '지표 미보유' };
  }
  const [source, breakdown, category] = (i.series_key ?? '').split(':');
  const rows = await queryObservations(deps, {
    source, breakdown, category, from: 기간?.from, to: 기간?.to });
  const 관측 = rows.map((r) => ({ 기간: r.period, 값: r.value }));
  const last = rows[rows.length - 1] ?? {};
  return { ...base,
    ...buildEvidence({ 지표: i.id, compare_basis: i.compare_basis,
                       ...(last.unit ? { 단위: last.unit } : {}),
                       rse: last.rse ?? null, rse_flag: last.rse_flag ?? null,
                       출처: i.source_id }, 관측) };
}

export async function evidence(deps, { phenomenon_id, 기간 } = {}) {
  const [ph] = (await deps.db.all(
    'SELECT * FROM phenomenon WHERE id = ?', [phenomenon_id])).filter(
      (p) => p.id === phenomenon_id);
  if (!ph) return null;

  const hyps = (await deps.db.all(
    'SELECT * FROM hypothesis WHERE phenomenon_id = ?', [phenomenon_id]))
    .filter((h) => h.phenomenon_id === phenomenon_id);
  const verdicts = await deps.db.all('SELECT * FROM hypothesis_verdict');
  const his = await deps.db.all('SELECT * FROM hyp_indicator');
  const ind = await deps.db.all('SELECT * FROM indicator');

  const 가설 = [];
  for (const h of hyps) {
    const mine = his.filter((x) => x.hypothesis_id === h.id);
    const rows = [];
    for (const hi of mine) rows.push(await loadIndicator(deps, hi, ind, 기간));

    const v = verdicts.find((x) => x.id === h.id) ?? {};
    const 한계 = [];
    if (rows.some((r) => r.time_grain !== '월' && r.role === 'falsifies'))
      한계.push('선후관계는 검정하지 않음 — 반기 지표로는 선후를 볼 수 없다');
    // 사유를 고정 문자열로 박지 않는다. buildEvidence 가 rse_flag 유무로 이미
    // `RSE 미공표(${rse_flag})` 와 `RSE 미보유` 를 갈라 놨다 — 그것을 그대로 인용한다.
    // 그래서 오늘은 "RSE 미보유 — …" 이고, 수집기가 붙어 rse_flag 가 들어오는 날
    // 저절로 "RSE 미공표(*) — …" 가 된다. data_status 하나로 판정이 켜지는 것과 같은 계열이다.
    for (const 사유 of new Set(
      rows.filter((r) => r.유의성 === '불명').map((r) => r.유의성사유))) {
      한계.push(`${사유} — 표본오차 안인지 알 수 없다`);
    }
    if (rows.some((r) => r.compare_basis === '증감률만'))
      한계.push('모집단이 달라 수준 비교 불가 — 증감 방향만');
    if (h.검정력_주석) 한계.push(h.검정력_주석);

    가설.push({
      id: h.id, name_ko: h.name_ko, 대립가설: J(h.대립가설),
      판정: {
        verdict_capable: !!v.verdict_capable,
        verdict_strength: v.verdict_strength ?? null,
        verdict_blocked_by: v.verdict_blocked_by ?? null,
      },
      지지: rows.filter((r) => r.role === '지지'),
      반증: rows.filter((r) => r.role === 'falsifies'),
      missing_for_verdict: J(h.missing_for_verdict),
      우회경로: h.우회경로 ?? null,
      한계,
    });
  }
  return {
    현상: ph, 가설,
    // 가설없음(카탈로그가 비어 우리 쪽이 미비)과 판정없음(가설은 있으나 전부 판정 불가,
    // 지표를 수집하면 풀린다)은 서로 다른 신호다 — verdict_blocked_by 가 반증미설계 와
    // 데이터미보유 를 가른 것과 같은 구분을, 위 층에서 every() 로 뭉개면 안 된다.
    가설없음: 가설.length === 0,
    판정없음: 가설.length > 0 && 가설.every((h) => !h.판정.verdict_capable),
  };
}

export async function indicatorFallback(deps, 슬롯) {
  // 현상이 미등록이면 판정을 건너뛰고 "무엇을 봐야 하는가" 만 낸다
  const ind = await deps.db.all('SELECT * FROM indicator');
  const 축 = 슬롯.집단축 ?? [];
  const 말뭉치 = (i) => `${i.name_ko} ${i.정의 ?? ''} ${i.모집단 ?? ''}`;
  // 축이 비면 전부, 아니면 축 이름이 걸리는 지표만. 하나도 안 걸리면 전부로 되돌린다
  const 걸린 = 축.length ? ind.filter((i) => 축.some((a) => 말뭉치(i).includes(a))) : ind;
  const 지표 = 걸린.length ? 걸린 : ind;
  return {
    지표: 지표.map((i) => ({ 지표: i.id, name_ko: i.name_ko, 출처: i.source_id,
      data_status: i.data_status,
      우회경로: i.data_status === '보유' ? null : '수집기 추가(승인 불요)' })),
    보유수: 지표.filter((i) => i.data_status === '보유').length,
    미보유수: 지표.filter((i) => i.data_status !== '보유').length,
    판정없음: true,
  };
}
