// 질문을 색인에 던져 **"이런 출처가 답이 될 수 있다"** 를 도메인별로 낸다.
//
// 문장으로 답하지 않는다. **LLM 을 부르지 않는다** — `deps.llm` 을 아예 안 봐야
// 언젠가 슬그머니 쓰게 되는 일이 없다.
//
// 고용동향만 색인이 아니라 `observation` 조회다. 관측은 문장이 아니라 수치라
// 색인할 본문이 없다 — 대신 같은 모양(제목·스니펫·링크)으로 접어 낸다. 화면이
// 도메인마다 다른 그림을 그리지 않게 하려는 것이다.

import { queryObservations } from '../core/query.mjs';
import { slotsFromText, 도메인적용 } from './applies.mjs';

const squash = (s) => String(s ?? '').replace(/\s+/g, '');

// trigram 은 세 글자가 최소 단위다(2026-09-10 실물 D1 실측: '고용'·'임금' 이 0건).
const MIN = 3;
// 도메인당 몇 건까지 보여줄 것인가. 더 보고 싶으면 그 도메인 앱으로 간다.
const LIMIT = 5;
const 폭 = 70;

// 한국어 조사. trigram 은 글자 그대로 맞춰서 '고용률이' 로 던지면 '고용률을' 이
// 안 걸린다 — 뒤에 붙은 조사를 떼야 한다. 긴 것부터 뗀다('에서' 가 '서' 에 먹히지
// 않게). 형태소 분석기를 넣지 않는다: 워커에 무게를 더할 값이 아니고, 덜 떼도
// 부분일치라 대개 걸린다.
const 조사 = ['으로써', '에서는', '으로는', '에게서', '이라는', '에서', '으로', '에게',
              '까지', '부터', '보다', '이나', '이란', '라는', '와의', '과의',
              '은', '는', '이', '가', '을', '를', '의', '에', '도', '만', '와', '과', '로'];

// 글로 찾는 세 도메인. 순서가 곧 화면 순서다.
const 글도메인 = ['reports', 'forecast', 'catalog'];

export function 용어뽑기(질문) {
  const out = [];
  for (const raw of String(질문 ?? '').split(/[^가-힣A-Za-z0-9]+/)) {
    let t = squash(raw);
    if (!t) continue;
    for (const j of 조사) {
      // 조사를 떼고도 두 글자는 남아야 한다 — '의' 를 떼서 한 글자만 남으면 말이 아니다.
      if (t.length > j.length + 1 && t.endsWith(j)) { t = t.slice(0, -j.length); break; }
    }
    if (t.length < 2) continue;
    if (!out.includes(t)) out.push(t);
  }
  return out;
}

export function 매치식(용어들) {
  // 따옴표로 감싸지 않으면 FTS5 가 용어를 문법으로 읽어 구문 오류를 낸다.
  // 따옴표는 두 번 써서 이스케이프한다.
  return (용어들 ?? [])
    .map((t) => `"${String(t).replace(/"/g, '""')}"`)
    .join(' OR ');
}

export function 스니펫(본문, 용어들, w = 폭) {
  const s = String(본문 ?? '');
  if (!s) return '';
  // 색인은 공백을 지운 사본이라 "청년 고용" 이 "청년고용" 으로 걸린다. 원문에서
  // 그 자리를 찾으려면 공백을 지운 위치 → 원문 위치 대응표가 필요하다.
  const map = [];
  let 압축 = '';
  for (let i = 0; i < s.length; i += 1) {
    if (!/\s/.test(s[i])) { 압축 += s[i]; map.push(i); }
  }
  let hit = -1;
  for (const t of 용어들 ?? []) {
    const i = 압축.indexOf(squash(t));
    if (i >= 0 && (hit < 0 || i < hit)) hit = i;
  }
  if (hit < 0) return s.length <= w * 2 ? s : `${s.slice(0, w * 2).trim()}…`;
  const at = map[hit];
  const from = Math.max(0, at - Math.floor(w / 2));
  const to = Math.min(s.length, at + w);
  return `${from > 0 ? '…' : ''}${s.slice(from, to).trim()}${to < s.length ? '…' : ''}`;
}

// **두 길로 찾아 합친다.**
//
// trigram 은 세 글자가 최소 단위인데, 한국어에서 가장 중요한 낱말이 하필 두
// 글자다 — 청년·정년·임금·여성·고용. 색인만 쓰면 "청년 고용률" 이라는 질문에서
// `청년` 이 통째로 사라진다. 그래서 세 글자 이상은 색인(MATCH)으로, 두 글자는
// LIKE 로 훑어 합친다. 지금 색인이 1,084행·3MB 라 전수 훑기가 감당된다 —
// 데이터가 열 배가 되면 다시 잰다.
async function 글조회(deps, 도메인, 용어들, limit) {
  const 긴것 = (용어들 ?? []).filter((x) => x.length >= MIN);
  const 짧은것 = (용어들 ?? []).filter((x) => x.length < MIN);
  const rows = [];

  const 식 = 매치식(긴것);
  if (식) {
    // bm25 는 색인 열에만 걸린다 — 제목색인(7번째)에 무게를 더 준다.
    rows.push(...await deps.db.all(
      `SELECT 종류, 제목, 본문, 링크 FROM doc_fts
        WHERE doc_fts MATCH ? AND 도메인 = ?
        ORDER BY bm25(doc_fts, 0,0,0,0,0,0, 10, 1) LIMIT ?`,
      [식, 도메인, limit]));
  }

  if (짧은것.length) {
    const cond = 짧은것.map(() => '본문색인 LIKE ?').join(' OR ');
    rows.push(...await deps.db.all(
      `SELECT 종류, 제목, 본문, 링크 FROM doc_fts
        WHERE 도메인 = ? AND (${cond}) LIMIT ?`,
      [도메인, ...짧은것.map((x) => `%${squash(x)}%`), limit]));
  }

  // 두 길로 같은 글이 걸릴 수 있다. 색인 쪽이 순위를 갖고 있으므로 먼저 온 것을 남긴다.
  const 본것 = new Set();
  const out = [];
  for (const r of rows) {
    const key = `${r.종류}|${r.제목}|${r.본문}`;
    if (본것.has(key)) continue;
    본것.add(key);
    out.push(r);
    if (out.length >= limit) break;
  }
  return out;
}

// 고용동향: 색인이 아니라 관측 조회. 같은 모양으로 접는다.
async function 관측조회(deps, 슬롯, limit) {
  const 축 = 슬롯.집단축[0] ?? null;
  const breakdown = { 연령: 'age', 성: 'sex', 산업: 'industry' }[축] ?? 'total';
  const rows = await queryObservations(deps, {
    source: 'eaps', breakdown,
    category: 축 ? (슬롯.category[축] ?? null) : null,
    from: 슬롯.기간.from, to: 슬롯.기간.to, 최신만: true,
  });
  return rows.slice(0, limit).map((o) => ({
    제목: `${o.period} ${축 ? `${축} ${o.category}` : '전체'}`,
    스니펫: `${o.value}${o.unit ?? ''}${o.yoy != null ? ` (전년대비 ${o.yoy})` : ''}`,
    링크: o.release_url ?? '',
    근거유형: '관측',
  }));
}

export async function lookup(deps, 질문, { limit = LIMIT } = {}) {
  const 용어들 = 용어뽑기(질문);
  const 슬롯 = slotsFromText(질문);
  const 적용 = 도메인적용(질문);

  const 묶음 = [];
  const 해당없음 = 적용.filter((a) => !a.적용).map((a) => ({ 도메인: a.도메인, 사유: a.사유 }));
  const 켜진 = new Set(적용.filter((a) => a.적용).map((a) => a.도메인));

  for (const 도메인 of 글도메인) {
    if (!켜진.has(도메인)) continue;
    const rows = await 글조회(deps, 도메인, 용어들, limit);
    묶음.push({
      도메인,
      결과: rows.map((r) => ({
        제목: r.제목, 스니펫: 스니펫(r.본문, 용어들),
        링크: r.링크 ?? '', 근거유형: r.종류,
      })),
      ...(rows.length ? {} : { 사유: '이 질문으로 걸리는 글이 없다' }),
    });
  }

  if (켜진.has('employment')) {
    const 결과 = await 관측조회(deps, 슬롯, limit);
    묶음.unshift({
      도메인: 'employment', 결과,
      ...(결과.length ? {} : { 사유: '이 조건의 관측이 적재돼 있지 않다' }),
    });
  }

  return { 질문: String(질문 ?? ''), 슬롯, 묶음, 해당없음 };
}
