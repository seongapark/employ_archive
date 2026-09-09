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

// ── Task 13 리뷰 대응(Important 1·5): 소스는 유형을 안 가린다 ──────────────
// `메타한계`·`범위밖` 은 이미 meta() 로 소스를 채우지만, 수치조회·출처비교·
// 원인탐색은 여태 안 채워서 화면이 "소스 없음"으로 그렸다(근거는 있는데 출처가
// 없다고 말하는 셈). 실제로 쓰인 소스 id(근거[].출처 ∪ 지표[].출처 ∪ 라우팅.가능)를
// 모아 한 번만 source_catalog 를 조회한다.
function 사용된소스id(r) {
  const ids = new Set();
  for (const e of r.근거 ?? []) if (e.출처) ids.add(e.출처);
  for (const i of r.지표 ?? []) if (i.출처) ids.add(i.출처);
  for (const s of r.라우팅?.가능 ?? []) ids.add(s);
  return [...ids];
}

// breakdown(관측 축) → 한글 축 이름. 축_BREAKDOWN 의 반대 방향이다 — 표를 두 벌
// 두지 않으려고 여기서 뒤집는다.
const 축한글 = Object.fromEntries(Object.entries(축_BREAKDOWN).map(([k, v]) => [v, k]));

// 수치조회·출처비교의 근거는 `지표` 가 "eaps:age:30-39" 같은 내부 합성키다(원인탐색
// 쪽 근거는 loadIndicator 가 이미 name_ko 를 붙여 온다 — 그래서 여기선 손대지 않는다).
// segments.json(카테고리 코드 → "30대" 같은 한글명)은 D1 에 없어 Worker 가 못 읽는다
// — 그래서 **없는 이름을 지어내지 않고**, 가진 것(소스 name_ko + 한글 축 + 코드)만으로
// 조립한다. 소스 이름조차 없으면(카탈로그에 없는 id) 합성키를 그대로 둔다 — 화면이
// `·` 로 끊어 읽기 쉽게 그린다.
function 지표이름조립(e, 소스이름표) {
  if (e.name_ko) return; // 이미 사람이 읽을 이름이 있으면 덮지 않는다
  const [src, breakdown, ...rest] = String(e.지표 ?? '').split(':');
  const 소스이름 = 소스이름표[src];
  if (!소스이름) return; // 조립 불가 — 합성키를 그대로 둔다
  const category = rest.join(':') || null;
  const 축 = breakdown === 'total' ? null : (축한글[breakdown] ?? breakdown);
  e.name_ko = 축 ? `${소스이름} · ${축}${category ? ` ${category}` : ''}` : 소스이름;
}

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

// 우리가 실제로 LLM 에게 넘긴 **카드의 산문 필드**만 모은다. verify 의 세 번째 인자로
// 그대로 넘어간다(Task 12). 현상 근거서술의 "4반기 연속 감소" 처럼 우리가 준 문장의
// 숫자는 인용이지 환각이라서, 근거 집합에 없다는 이유만으로 튕기면 정상 답변이 버려진다.
// 반대로 아무 문자열이나 담으면 검증이 무의미해진다.
//
// **경계는 하나다 — 우리가 LLM 에게 넘기는 문장이면 담고, 아니면 뺀다.**
//   담는다: 현상 근거서술·정의 · 한계 · 우회경로(라우팅·가설·지표) · 지표 미보유 사유 ·
//           compare 설명 · missing_for_verdict · 라우팅 불가/부분 사유 · 유의성사유 ·
//           범위밖의 답할수있는질문
//   뺀다:   식별자(id·source_id·limit_id·series_key) · URL·endpoint · 열거값
//           (compare_basis·유의성·data_status·time_grain) · 소스 카탈로그 메타 ·
//           관측·파생 수치(numbersIn 이 근거묶음에서 이미 모은다)
function 허용텍스트(r) {
  const t = [];
  // 현상은 근거서술만이 아니다 — 정의에도 숫자가 있다("15~29세 사무 종사자 …")
  if (r.현상?.근거서술) t.push(r.현상.근거서술);
  if (r.현상?.정의) t.push(r.현상.정의);
  for (const l of r.한계 ?? []) t.push(l);
  for (const u of r.우회경로 ?? []) {
    t.push(typeof u === 'string' ? u : [u.경로, u.제약].filter(Boolean).join(' '));
  }
  for (const s of r.비교?.설명 ?? []) t.push(s);
  // 라우팅 사유는 수치조회에서만 한계로 접히고, 메타한계·범위밖 카드에서는 라우팅 안에
  // 그대로 실려 나간다 — 그쪽 경로에서도 우리가 준 문장이다
  for (const x of [...(r.라우팅?.불가 ?? []), ...(r.라우팅?.부분 ?? [])]) t.push(x.사유);
  for (const e of r.근거 ?? []) { t.push(e.유의성사유); t.push(e.우회경로); t.push(e.사유); }
  for (const h of r.가설 ?? []) {
    if (h.우회경로) t.push(h.우회경로);
    for (const m of h.missing_for_verdict ?? []) t.push(m);
    // 지표 미보유 행이 달고 나오는 확보 경로·사유도 우리가 넘긴 문장이다
    for (const x of [...(h.지지 ?? []), ...(h.반증 ?? [])]) { t.push(x.우회경로); t.push(x.사유); }
  }
  for (const x of r.지표 ?? []) if (x.우회경로) t.push(x.우회경로);
  // 범위밖의 예시 질문은 우리가 만들어 카드에 실은 문장이다 — "2026년 7월 30대 취업자는
  // 몇 명인가" 를 그대로 인용하면 7·30 이 위반으로 잡힌다(2026년은 기간 토큰이라 마스킹된다)
  for (const q of r.답할수있는질문 ?? []) t.push(q);
  return [...new Set(t.filter((s) => typeof s === 'string' && s))];
}

// 집단축을 관측 축으로 접는다. observation 은 breakdown 열이 하나뿐이라 축 하나만
// 조회할 수 있다 — 나머지는 못 한다고 말한다.
// 축을 지목하지 못했을 때 무엇을 함께 보여주게 되는지 축마다 밝힌다(조사 때문에 표로 둔다)
const 축_지목없음 = {
  연령: '연령대를 지목하지 못해 전 구간을 함께 보여준다',
  성: '성별을 지목하지 못해 남녀를 함께 보여준다',
  산업: '산업을 지목하지 못해 전 산업을 함께 보여준다',
};

export function 관측축(집단축 = []) {
  if (!집단축.length) return { breakdown: 'total', 축: null, 한계: [] };
  const 됨 = 집단축.filter((a) => a in 축_BREAKDOWN);
  const 안됨 = 집단축.filter((a) => !(a in 축_BREAKDOWN));
  const 한계 = [];
  if (안됨.length) {
    한계.push(`${안됨.join('·')}별 관측은 적재돼 있지 않다 — 전체값으로 대신 답하지 않는다`);
  }
  if (됨.length > 1) 한계.push(`${됨[0]} 축만 조회한다 — ${됨.slice(1).join('·')} 과의 교차는 못 낸다`);
  return { breakdown: 됨.length ? 축_BREAKDOWN[됨[0]] : null, 축: 됨[0] ?? null, 한계 };
}

// 둘 중 더 보수적인 쪽. 하나라도 수준이 아니면 수준으로 인용하지 않는다.
const 보수적 = (...xs) => (xs.some((x) => x && x !== '수준') ? '증감률만' : '수준');

// 비교기준은 소스가 아니라 **지표 카탈로그**가 정한다. `src === 'eaps' ? '수준' : '증감률만'`
// 처럼 소스 id 를 코드에 박으면 소스가 늘 때마다 조용히 틀린다.
function 비교기준(지표들, src, breakdown) {
  const 정확 = 지표들.find((i) => i.series_key === `${src}:${breakdown}`);
  if (정확) return { compare_basis: 정확.compare_basis, 근거: 정확.id };
  const 같은소스 = 지표들.filter((i) => i.source_id === src);
  if (같은소스.length) {
    // 같은 소스 안에서 가장 보수적인 쪽을 고른다 — 하나라도 증감률만이면 수준으로 안 낸다
    const 보수 = 보수적(...같은소스.map((i) => i.compare_basis));
    return { compare_basis: 보수, 근거: 같은소스.map((i) => i.id).join('·') };
  }
  // 모르면 관대한 쪽이 아니라 보수적인 쪽으로 떨어진다 — compare.mjs 의 "모르면 비교를
  // 허용하지 않는다" 와 같은 규율이다. est 처럼 지표 행이 없는 소스가 실제로 여기 온다.
  return { compare_basis: '증감률만', 근거: null };
}

async function 수치조회(deps, 슬롯, { 출처, 비교하한 } = {}) {
  const 라우팅 = await route(deps, 슬롯);
  // 출처비교는 사용자가 출처를 직접 지목한다 — 그때는 라우팅 대신 지목된 출처를 읽는다.
  const 대상 = 출처?.length ? 출처 : 라우팅.가능;
  const 지표들 = await deps.db.all('SELECT * FROM indicator');
  const { breakdown, 축, 한계: 축한계 } = 관측축(슬롯.집단축);
  const category = 축 ? (슬롯.category?.[축] ?? null) : null;

  const 근거 = [];
  const 한계 = [...축한계];
  if (대상.length > 1) 한계.push('모집단이 달라 수준 비교 불가 — 증감 방향만');
  // 축은 집었는데 그 축의 어느 값인지를 못 집으면 전 구간이 함께 나온다. 밝힌다.
  if (축 && !category) 한계.push(축_지목없음[축] ?? `${축} 값을 지목하지 못해 전 구간을 함께 보여준다`);
  // 라우팅이 통째로 비면 카드가 아무 말도 안 하게 된다 — 그 자체가 답이다
  if (!라우팅.가능.length && !라우팅.부분.length && !라우팅.불가.length) {
    한계.push('이 주제·축 조합을 내는 출처가 카탈로그에 없다');
  }

  if (breakdown) {
    for (const src of 대상) {
      const rows = await queryObservations(deps, {
        source: src, breakdown, category,
        from: 슬롯.기간?.from, to: 슬롯.기간?.to,
      });
      if (!rows.length) {
        // 빈손을 조용히 넘기지 않는다
        한계.push(`${src}: 이 조건(${breakdown}${category ? `=${category}` : ''}${슬롯.기간?.from ? ` ${슬롯.기간.from}~${슬롯.기간.to}` : ''})의 관측이 아직 적재돼 있지 않다`);
        continue;
      }
      const 끝 = rows[rows.length - 1];
      const { compare_basis: 카탈로그기준, 근거: 기준근거 } = 비교기준(지표들, src, breakdown);
      if (!기준근거) 한계.push(`${src}: 비교기준이 지표 카탈로그에 없어 증감률만으로 인용한다`);
      // 쌍 판정(출처비교의 compare 결과)이 더 보수적이면 그쪽을 따른다 — 소스별 카탈로그
      // 기준과 쌍 단위 판정이 따로 놀면, 증감률만으로 못박은 쌍에 수준값이 실려 나간다.
      const compare_basis = 보수적(카탈로그기준, 비교하한);
      근거.push(buildEvidence(
        {
          // 카테고리까지 키에 넣는다 — 안 넣으면 카드가 "eaps:age" 라고만 말해
          // 이 숫자가 어느 연령대인지 LLM 도 화면도 알 수 없다.
          // 골든이 문서용으로 적어 둔 근거지표 형식(`eaps:age:30-39:2026-07`)과도 같다.
          지표: [src, breakdown, category].filter(Boolean).join(':'),
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
  // **시간입도·기간으로 거르지 않는다.** 현상의 관측 주기(반기)는 데이터의 성질이지
  // 질문의 성질이 아니다 — "왜 줄었어?" 라고 묻는 사람이 그걸 알 리 없다. 실제로
  // 그 조건 때문에 간판 질문("청년 사무직은 왜 줄었어")이 현상을 못 찾고 지표
  // 폴백으로 떨어졌다(2026-09-09 배포 후 실측). 어긋나는 주기는 거부 사유가 아니라
  // 답변에 **알려줄 사실**이라, 호출부가 한계로 낸다.
  // 기간 비교도 뺐다 — 현상은 "2023S1~2025S2", 슬롯은 "2023" 처럼 형식이 달라
  // 문자열 비교가 거짓 거부를 한다.
  const 후보 = phs.filter((p) => {
    if (슬롯.지역입도 && p.지역 && p.지역 !== 슬롯.지역입도) return false;
    return true;
  });
  // 주제는 매핑된 값과 원문 둘 다로 맞춰 본다 — 카탈로그 문구가 어느 쪽을 담을지 모른다.
  const 열쇠 = [주제, 슬롯.주제, ...(슬롯.집단축 ?? [])].filter(Boolean);
  const 맞는것 = 후보.find((p) => {
    const 말뭉치 = `${p.name_ko} ${p.정의 ?? ''}`;
    return 열쇠.length ? 열쇠.some((k) => 말뭉치.includes(k)) : true;
  });
  return 맞는것 ?? null;
}

export async function ask(deps, { 유형, 슬롯: 입력슬롯 = {}, 저확신 = false, 한도초과 = false } = {}) {
  // 주제를 **한 번만, 맨 앞에서** 카탈로그 원어로 접는다. 전망·원인탐색에서만 접고
  // route() 앞에서는 안 접으면, 짧은 정규형으로 들어온 질문이 후보 없음으로 떨어져
  // 라우팅이 통째로 비고 카드가 아무 말도 못 하게 된다.
  const 슬롯 = { ...입력슬롯, 주제: 주제원어(입력슬롯.주제) };
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
      // 쌍 판정을 근거 생성에 그대로 물린다. 출처비교는 이 규율이 가장 중요한 유형이다 —
      // 증감률만·불가로 못박은 쌍인데 소스별 카탈로그 기준만 보고 수준값을 실으면
      // compare() 가 낸 판정이 장식이 된다.
      const q = await 수치조회(deps, { ...슬롯, 집단축: [] },
                               { 출처: [a, b], 비교하한: c.비교가능 });
      r = { ...base, ...q, 비교: c, 한계: [...c.설명, ...q.한계] };
    }
  } else if (유형 === '전망') {
    const ind = 전망지표[슬롯.주제] ?? null;   // 주제는 ask() 맨 앞에서 이미 접혔다
    if (!ind) {
      r = { ...base, 전망: [], 근거서술: [], 지표코드: null,
            한계: [`'${슬롯.주제}' 의 전망은 아직 다루지 않는다 — 전망 지표 카탈로그(${Object.values(전망지표).join('·')})에 대응 코드가 없다`] };
    } else {
      // Task 13 리뷰 대응(Important 4): 연도 필터가 없으면 여러 연도의 전망이
      // 섞여 나올 수 있다 — 슬롯이 연도를 지목했으면(수치조회처럼 강제는 아니지만)
      // 그 범위로 좁힌다. 못 지목하면(연/기간이 비거나 연도가 아니면) 전부 낸다 —
      // 못 좁혔다는 사실 자체를 화면이 안 숨기면 된다(연도별로 묶어 그린다).
      const 연도from = Number(슬롯.기간?.from) || null;
      const 연도to = Number(슬롯.기간?.to) || null;
      const rows = (연도from && 연도to)
        ? await deps.db.all(
            `SELECT * FROM forecast WHERE indicator = ?
               AND target_year >= ? AND target_year <= ?
              ORDER BY target_year, published_at`,
            [ind, 연도from, 연도to])
        : await deps.db.all(
            'SELECT * FROM forecast WHERE indicator = ? ORDER BY target_year, published_at',
            [ind]);
      // 근거 블록이 rationale 인용을 요구한다(스펙 §6) — 원문 페이지까지 함께 낸다
      const 근거서술 = await deps.db.all(
        'SELECT * FROM forecast_rationale WHERE indicator = ? ORDER BY published_at', [ind]);
      const 한계 = [
        '기관마다 발표 시점이 달라 같은 시점의 전망이 아니다',
        // 리뷰 라운드 2 판정 2: 출처가 없는 게 아니라(forecast 행 자체가 org·
        // source_url·landing_url 을 들고 있다) 그 기관이 source_catalog 에 없을
        // 뿐이다 — 조용히 비우지 않고 그 사실을 말한다(등급·한계 정보를 못 낸다는 뜻).
        '전망 기관은 소스 카탈로그에 등재돼 있지 않아 등급·한계 정보가 없다',
      ];
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
      // 질문의 시간입도와 현상의 관측 주기가 다르면 거부하지 말고 밝힌다.
      if (슬롯.시간입도 && ph.time_grain && ph.time_grain !== 슬롯.시간입도) {
        r.한계.push(`이 현상은 ${ph.time_grain} 단위로 관측된다 — 물으신 ${슬롯.시간입도} 단위로는 볼 수 없다`);
      }
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

  // Task 13 리뷰 대응(Important 1·5, 라운드 2 판정 1): 메타한계·범위밖은 위에서
  // 이미 `소스` 를 채웠다(r.소스 가 배열로 존재 — 비어 있어도 존재한다는 사실
  // 자체가 다르다). 나머지 유형(수치조회·출처비교·원인탐색)은 여기서 한 번만 채운다.
  //
  // **미확인 소스도 감추지 않는다.** 라운드 1에서는 골든의 배지 집합 단언이 깨진다는
  // 이유로 병합을 뺐는데, 조정자가 방향이 거꾸로라고 판정했다 — 실제로 미확인 소스의
  // 지표가 근거에 실린다면 `근거 미확인` 배지는 참이고, 배지를 감춰 골든을 초록으로
  // 유지하는 건 동작을 테스트에 맞추는 것이다. 그래서 여기서도 meta()·메타한계와
  // 같은 경로로 미확인을 `카드.미확인`에 합친다 — 골든(원인탐색-청년사무직)의 기대
  // 배지를 바로잡는 쪽으로 고쳤다(아래, 그리고 골든 파일의 `_비고` 참고).
  if (!r.소스) {
    const ids = 사용된소스id(r);
    if (ids.length) {
      const m = await meta(deps, { 출처: ids });
      r.소스 = m.소스;
      if (m.미확인.length) r.미확인 = [...(r.미확인 ?? []), ...m.미확인];
      // Minor(최종 리뷰): `충돌` 도 같은 meta() 호출에서 나온다. 여기서 안 옮기면
      // 출처비교 화면이 위(비교 블록)에서는 "개념이 다르다" 고 하고 아래
      // "출처 간 상충" 에는 `.conflicts:empty::after` 때문에 "없음" 이라 쓴다 —
      // 같은 화면이 스스로 모순된다. 카드.충돌 이 메타한계·범위밖에서만 채워졌기
      // 때문이었다. 소스를 옮기는 자리에서 충돌도 같이 옮긴다.
      r.충돌 = m.충돌;
      const 소스이름표 = Object.fromEntries(
        [...m.소스, ...m.미확인].map((s) => [s.id, s.name_ko]));
      for (const e of r.근거 ?? []) 지표이름조립(e, 소스이름표);
    }
  }

  r.배지 = 배지(r);
  r.허용텍스트 = 허용텍스트(r);
  return r;
}

export { verify };
