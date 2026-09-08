// 유형별로 core 함수를 부르고 카드를 만든다. **유형 분기는 코드가 한다.**
// 여기서는 답변 문장을 만들지 않는다 — `답변` 은 항상 null 로 나가고, 2패스 LLM 을
// 태우는 것은 호출부(Task 12)의 몫이다. 그래서 골든 세트가 결정적으로 돈다.

import { route } from './route.mjs';
import { meta } from './meta.mjs';
import { compare } from './compare.mjs';
import { evidence, indicatorFallback } from './evidence.mjs';
import { queryObservations, buildEvidence } from './query.mjs';
import { verify } from './verify.mjs';
import { 주제_SYN } from './classify.mjs';

// ── 매핑표 셋. 전부 코드에 명시한다 — "조용히 빈손" 이 가장 나쁜 실패다 ──────────

// 1) 집단축 → observation.breakdown.
//    실측(2026-09-08, domains/employment/data/series.json)상 breakdown 은
//    total · age · sex · industry 넷뿐이다. `직업` 은 카탈로그 어휘(classify.축_SYN)에는
//    있지만 관측 축으로는 없다 — 여기 넣어 두면 조회가 빈손이 되고, 빼고 total 로
//    떨어뜨리면 물은 것과 다른 값을 보여준다. 그래서 **매핑 실패를 한계로 낸다.**
export const 축_BREAKDOWN = { 연령: 'age', 성: 'sex', 산업: 'industry' };

// 2) 슬롯 주제 → forecast.indicator 코드.
//    코드는 domains/forecast/data/indicators.json 의 `code` 필드다(2026-09-08 실측:
//    emp_change · emp_rate · unemp_rate · gdp_growth · cpi · emp_rate_youth · labor_force).
//    `슬롯.주제 === '취업자' ? 'emp_change' : 슬롯.주제` 로는 안 된다 — 슬롯 주제는
//    카탈로그 원어(`취업자수`)라 그 비교가 항상 거짓이 되고 `취업자수` 가 지표 코드로
//    넘어가 빈손이 된다. 매핑에 없으면 빈 결과가 아니라 한계를 낸다.
//    지금 classify 어휘가 낼 수 있는 주제 셋 중 전망 지표가 있는 것은 취업자수뿐이고,
//    종사자수·상시가입자수는 전망 기관이 발표하지 않는다 — 그래서 여기 없다.
export const 전망지표 = {
  취업자수: 'emp_change',       // 취업자 증감
  고용률: 'emp_rate',
  실업률: 'unemp_rate',
  청년고용률: 'emp_rate_youth',
  경제활동참가율: 'labor_force',
};

// 3) 주제 동의어. 슬롯은 classify.normalize() 를 거쳐 카탈로그 원어로 오는 것이
//    원칙이지만, 골든처럼 1패스를 건너뛴 입력은 짧은 정규형(`취업자`)으로도 들어온다.
//    classify 와 **같은 표**로 한 번 더 접는다 — 표를 두 벌 두지 않는다.
const 주제원어 = (주제) => 주제_SYN[주제] ?? 주제 ?? '';

const 배지 = (r) => {
  const b = [];
  if (r.저확신) b.push('저확신');
  if (r.한도초과) b.push('한도초과');
  if (r.검증실패) b.push('검증실패');
  for (const h of r.가설 ?? []) {
    if (h.판정.verdict_blocked_by) b.push(h.판정.verdict_blocked_by);
  }
  if ((r.근거 ?? []).some((e) => e.유의성 === '불명')) b.push('유의성: 불명');
  if ((r.미확인 ?? []).length) b.push('근거 미확인');
  return [...new Set(b)];
};

// 우리가 실제로 LLM 에게 넘긴 **카드의 텍스트 필드**만 모은다. verify 의 세 번째
// 인자로 그대로 넘어간다(Task 12). 현상 근거서술의 "4반기 연속 감소" 처럼 우리가 준
// 문장의 숫자는 인용이지 환각이라서, 근거 집합에 없다는 이유만으로 튕기면 정상 답변이
// 버려진다. 반대로 아무 문자열이나 담으면 검증이 무의미해진다 —
// **담는 것은 현상 근거서술 · 한계 · 우회경로 · compare 설명 · missing_for_verdict 뿐이다.**
function 허용텍스트(r) {
  const t = [];
  if (r.현상?.근거서술) t.push(r.현상.근거서술);
  for (const l of r.한계 ?? []) t.push(l);
  for (const u of r.우회경로 ?? []) {
    t.push(typeof u === 'string' ? u : [u.경로, u.제약].filter(Boolean).join(' '));
  }
  for (const s of r.비교?.설명 ?? []) t.push(s);
  for (const h of r.가설 ?? []) {
    if (h.우회경로) t.push(h.우회경로);
    for (const m of h.missing_for_verdict ?? []) t.push(m);
    // 지표 미보유 행이 달고 나오는 확보 경로도 우리가 넘긴 문장이다
    for (const x of [...(h.지지 ?? []), ...(h.반증 ?? [])]) if (x.우회경로) t.push(x.우회경로);
  }
  for (const x of r.지표 ?? []) if (x.우회경로) t.push(x.우회경로);
  return [...new Set(t.filter((s) => typeof s === 'string' && s))];
}

// 집단축을 관측 축으로 접는다. observation 은 breakdown 열이 하나뿐이라 축 하나만
// 조회할 수 있다 — 나머지는 못 한다고 말한다.
export function 관측축(집단축 = []) {
  if (!집단축.length) return { breakdown: 'total', 한계: [] };
  const 됨 = 집단축.filter((a) => a in 축_BREAKDOWN);
  const 안됨 = 집단축.filter((a) => !(a in 축_BREAKDOWN));
  const 한계 = [];
  if (안됨.length) {
    한계.push(`${안됨.join('·')}별 관측은 적재돼 있지 않다 — 전체값으로 대신 답하지 않는다`);
  }
  if (됨.length > 1) 한계.push(`${됨[0]} 축만 조회한다 — ${됨.slice(1).join('·')} 과의 교차는 못 낸다`);
  return { breakdown: 됨.length ? 축_BREAKDOWN[됨[0]] : null, 한계 };
}

// 비교기준은 소스가 아니라 **지표 카탈로그**가 정한다. `src === 'eaps' ? '수준' : '증감률만'`
// 처럼 소스 id 를 코드에 박으면 소스가 늘 때마다 조용히 틀린다.
function 비교기준(지표들, src, breakdown) {
  const 정확 = 지표들.find((i) => i.series_key === `${src}:${breakdown}`);
  if (정확) return { compare_basis: 정확.compare_basis, 근거: 정확.id };
  const 같은소스 = 지표들.filter((i) => i.source_id === src);
  if (같은소스.length) {
    // 같은 소스 안에서 가장 보수적인 쪽을 고른다 — 하나라도 증감률만이면 수준으로 안 낸다
    const 보수 = 같은소스.some((i) => i.compare_basis === '증감률만') ? '증감률만' : '수준';
    return { compare_basis: 보수, 근거: 같은소스.map((i) => i.id).join('·') };
  }
  return { compare_basis: '수준', 근거: null };
}

async function 수치조회(deps, 슬롯, { 출처 } = {}) {
  const 라우팅 = await route(deps, 슬롯);
  // 출처비교는 사용자가 출처를 직접 지목한다 — 그때는 라우팅 대신 지목된 출처를 읽는다.
  const 대상 = 출처?.length ? 출처 : 라우팅.가능;
  const 지표들 = await deps.db.all('SELECT * FROM indicator');
  const { breakdown, 한계: 축한계 } = 관측축(슬롯.집단축);

  const 근거 = [];
  const 한계 = [...축한계];
  if (대상.length > 1) 한계.push('모집단이 달라 수준 비교 불가 — 증감 방향만');

  if (breakdown) {
    for (const src of 대상) {
      const rows = await queryObservations(deps, {
        source: src, breakdown, category: 슬롯.category ?? null,
        from: 슬롯.기간?.from, to: 슬롯.기간?.to,
      });
      if (!rows.length) {
        // 빈손을 조용히 넘기지 않는다
        한계.push(`${src}: 이 조건(${breakdown}${슬롯.기간?.from ? ` ${슬롯.기간.from}~${슬롯.기간.to}` : ''})의 관측이 아직 적재돼 있지 않다`);
        continue;
      }
      const 끝 = rows[rows.length - 1];
      const { compare_basis, 근거: 기준근거 } = 비교기준(지표들, src, breakdown);
      if (!기준근거) 한계.push(`${src}: 비교기준이 지표 카탈로그에 없어 수준으로 인용한다`);
      근거.push(buildEvidence(
        {
          지표: `${src}:${breakdown}`,
          compare_basis,
          // 단위는 **데이터가 준 것만** 싣는다. 지표에 %·건·지수가 섞여 있어
          // '천명' 을 박으면 틀린 단위가 답변에 나간다(Task 6).
          ...(끝.unit ? { 단위: 끝.unit } : {}),
          rse: 끝.rse ?? null, rse_flag: 끝.rse_flag ?? null,
          출처: src,
        },
        rows.map((r) => ({ 기간: r.period, 값: r.value }))));
    }
  }
  for (const x of 라우팅.불가) 한계.push(`${x.source}: ${x.사유}`);
  return { 라우팅, 근거, 한계, 우회경로: 라우팅.우회 };
}

// 현상은 고르는 것이지 박아 두는 것이 아니다 — id 를 코드에 박으면 어떤 원인탐색
// 질문에도 같은 현상을 답하게 된다. 시간입도·지역·기간·주제로 대조해 고르고,
// 걸리는 현상이 없으면 판정을 건너뛰고 지표 폴백으로 간다.
async function 현상찾기(deps, 슬롯) {
  const phs = await deps.db.all('SELECT * FROM phenomenon');
  const 주제 = 주제원어(슬롯.주제);
  const [pf, pt] = String(슬롯.기간?.from ?? '') && String(슬롯.기간?.to ?? '')
    ? [슬롯.기간.from, 슬롯.기간.to] : [null, null];
  return phs.find((p) => {
    if (슬롯.시간입도 && p.time_grain && p.time_grain !== 슬롯.시간입도) return false;
    if (슬롯.지역입도 && p.지역 && p.지역 !== 슬롯.지역입도) return false;
    if (주제 && !`${p.name_ko} ${p.정의 ?? ''}`.includes(주제)) return false;
    if (pf && p.기간) {
      const [f, t] = String(p.기간).split('~');
      if (f && t && !(f <= pt && pf <= t)) return false;
    }
    return true;
  }) ?? null;
}

export async function ask(deps, { 유형, 슬롯 = {}, 저확신 = false, 한도초과 = false } = {}) {
  const base = {
    유형, 슬롯, 저확신, 한도초과, 답변: null, 근거: [], 한계: [],
    미확인: [], 가설없음: false, 판정없음: false, 후속질문: [],
  };
  let r = base;

  if (유형 === '수치조회') {
    r = { ...base, ...(await 수치조회(deps, 슬롯)) };
  } else if (유형 === '출처비교') {
    const [a, b] = 슬롯.출처 ?? [];
    if (!a || !b) {
      r = { ...base, 한계: ['비교하려면 출처가 둘 필요하다 — 하나만 지목됐다'] };
    } else {
      const c = await compare(deps, { source_a: a, source_b: b });
      const q = await 수치조회(deps, { ...슬롯, 집단축: [] }, { 출처: [a, b] });
      r = { ...base, ...q, 비교: c, 한계: [...c.설명, ...q.한계] };
    }
  } else if (유형 === '전망') {
    const 주제 = 주제원어(슬롯.주제);
    const ind = 전망지표[주제] ?? null;
    if (!ind) {
      r = { ...base, 전망: [], 근거서술: [], 지표코드: null,
            한계: [`'${슬롯.주제}' 의 전망은 아직 다루지 않는다 — 전망 지표 카탈로그(${Object.values(전망지표).join('·')})에 대응 코드가 없다`] };
    } else {
      const rows = await deps.db.all(
        'SELECT * FROM forecast WHERE indicator = ? ORDER BY published_at', [ind]);
      // 근거 블록이 rationale 인용을 요구한다(스펙 §6) — 원문 페이지까지 함께 낸다
      const 근거서술 = await deps.db.all(
        'SELECT * FROM forecast_rationale WHERE indicator = ? ORDER BY published_at', [ind]);
      const 한계 = ['기관마다 발표 시점이 달라 같은 시점의 전망이 아니다'];
      if (!rows.length) 한계.push(`${ind} 전망이 아직 적재돼 있지 않다`);
      r = { ...base, 전망: rows, 근거서술, 지표코드: ind, 한계 };
    }
  } else if (유형 === '원인탐색') {
    const ph = await 현상찾기(deps, 슬롯);
    const ev = ph ? await evidence(deps, { phenomenon_id: ph.id, 기간: 슬롯.기간 }) : null;
    if (ev) {
      r = {
        ...base, 현상: ev.현상, 가설: ev.가설,
        가설없음: ev.가설없음, 판정없음: ev.판정없음,
        근거: ev.가설.flatMap((h) => [...h.지지, ...h.반증]),
        한계: [...new Set(ev.가설.flatMap((h) => h.한계))],
      };
      if (ev.가설없음) r.한계.push('이 현상에 등록된 가설이 없다 — 판정 이전의 문제다');
    } else {
      const fb = await indicatorFallback(deps, 슬롯);
      r = { ...base, ...fb, 한계: ['현상이 등록돼 있지 않아 판정하지 않는다'] };
    }
  } else {
    // 메타한계 · 범위밖 — 소스 단위 필터만
    const m = await meta(deps, { 출처: 슬롯.출처 ?? [] });
    const 라우팅 = await route(deps, 슬롯);
    r = {
      ...base, 라우팅, 소스: m.소스, 미확인: m.미확인, 충돌: m.충돌,
      한계: 유형 === '범위밖'
        ? ['이 아카이브는 고용 통계만 다룬다']
        : m.한계.map((l) => `${l.내용} (${l.사유})`),
      우회경로: 라우팅.우회,
    };
    if (유형 === '범위밖') {
      r.답할수있는질문 = ['2026년 7월 30대 취업자는 몇 명인가',
                         '경활과 고용행정통계는 왜 숫자가 다른가',
                         '내년 취업자 전망은 어떤가'];
    }
  }

  r.배지 = 배지(r);
  r.허용텍스트 = 허용텍스트(r);
  return r;
}

export { verify };
