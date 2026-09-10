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
const 글도메인 = ['reports', 'forecast', 'press', 'catalog'];

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
      `SELECT doc_id, 종류, 제목, 본문, 링크 FROM doc_fts
        WHERE doc_fts MATCH ? AND 도메인 = ?
        ORDER BY bm25(doc_fts, 0,0,0,0,0,0, 10, 1) LIMIT ?`,
      [식, 도메인, limit]));
  }

  if (짧은것.length) {
    const like = 짧은것.map(() => '본문색인 LIKE ?');
    // **걸린 낱말 수로 세운다.** 두 글자 낱말 중에는 '고용' 처럼 거의 모든 글에
    // 있는 말이 섞여 있어, 정렬하지 않으면 그 하나만 걸린 글이 여러 낱말이 다
    // 걸린 글보다 위로 온다(실측: "정년 연장이 고용에 미치는 영향").
    const 점수 = like.map((c) => `(${c})`).join(' + ');
    const 값 = 짧은것.map((x) => `%${squash(x)}%`);
    // 낱말이 셋 이상이면 **둘 이상 걸려야** 낸다. '고용' 처럼 거의 모든 글에 있는
    // 말 하나만 걸린 글을 "정년 연장" 질문의 답으로 내밀면 묻지 않은 것을 답한
    // 셈이다(실측). 낱말이 한둘뿐이면 그대로 하나만 걸려도 낸다.
    const 최소 = 짧은것.length >= 3 ? 2 : 1;
    rows.push(...await deps.db.all(
      `SELECT doc_id, 종류, 제목, 본문, 링크 FROM doc_fts
        WHERE 도메인 = ? AND (${like.join(' OR ')}) AND (${점수}) >= ?
        ORDER BY ${점수} DESC LIMIT ?`,
      [도메인, ...값, ...값, 최소, ...값, limit]));
  }

  // **문서 단위로 추린다.** 초록 한 건이 여러 청크로 쪼개져 있어, 조각 단위로
  // 추리면 다섯 자리가 같은 보고서로 다 차서 다른 보고서를 볼 기회가 사라진다
  // (실측). 두 길로 같은 글이 걸리는 것도 여기서 함께 걸러진다 — 색인 쪽이 순위를
  // 갖고 있으므로 먼저 온 것을 남긴다.
  const 본것 = new Set();
  const out = [];
  for (const r of rows) {
    // doc_id 는 `reports:kli-10303:초록:0` 꼴이다. 앞 두 마디가 문서를 가리킨다.
    const key = String(r.doc_id ?? `${r.종류}|${r.제목}`).split(':').slice(0, 2).join(':');
    // **제목으로도 추린다.** 같은 보고서가 게시판 둘에 올라가 id 는 다른데 제목이
    // 같은 경우가 있다(실측: "고령 노동과 소득 크레바스" 가 두 번 나왔다).
    const 이름 = `${r.도메인 ?? ''}|${r.제목 ?? ''}`;
    if (본것.has(key) || 본것.has(이름)) continue;
    본것.add(key);
    본것.add(이름);
    out.push(r);
    if (out.length >= limit) break;
  }
  return out;
}

// observation 의 breakdown 열은 이 셋뿐이다(실측). 직업 축은 값이 한 건도 없다.
const 축_BREAKDOWN = { 연령: 'age', 성: 'sex', 산업: 'industry' };

// 고용동향: 색인이 아니라 관측 조회. 같은 모양으로 접는다.
//
// **관측이 가진 축을 고른다.** 첫 축만 보면 "청년 사무직" 처럼 축이 둘인 질문에서
// 관측에 없는 직업 축을 집어 고용동향이 통째로 0건이 된다 — 연령으로는 낼 수
// 있는데도. 못 내는 축은 버리지 않고 말한다(못 준다와 못 알아들었다는 다르다).
async function 관측조회(deps, 슬롯, limit) {
  const 됨 = (슬롯.집단축 ?? []).filter((a) => a in 축_BREAKDOWN);
  const 안됨 = (슬롯.집단축 ?? []).filter((a) => !(a in 축_BREAKDOWN));
  const 축 = 됨[0] ?? null;
  const 한계 = [];
  if (안됨.length) 한계.push(`${안됨.join('·')}별 관측은 적재돼 있지 않다`);
  if (됨.length > 1) 한계.push(`${됨[0]} 축만 본다 — ${됨.slice(1).join('·')} 과의 교차는 못 낸다`);

  const rows = await queryObservations(deps, {
    source: 'eaps', breakdown: 축 ? 축_BREAKDOWN[축] : 'total',
    category: 축 ? (슬롯.category[축] ?? null) : null,
    from: 슬롯.기간.from, to: 슬롯.기간.to, 최신만: true,
  });
  return {
    결과: rows.slice(0, limit).map((o) => ({
      제목: `${o.period} ${축 ? `${축} ${o.category}` : '전체'}`,
      스니펫: `${o.value}${o.unit ?? ''}${o.yoy != null ? ` (전년대비 ${o.yoy})` : ''}`,
      링크: o.release_url ?? '',
      근거유형: '관측',
    })),
    한계,
  };
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
    const { 결과, 한계 } = await 관측조회(deps, 슬롯, limit);
    const 사유 = [...한계, ...(결과.length ? [] : ['이 조건의 관측이 적재돼 있지 않다'])];
    묶음.unshift({
      도메인: 'employment', 결과,
      ...(사유.length ? { 사유: 사유.join(' · ') } : {}),
    });
  }

  return { 질문: String(질문 ?? ''), 슬롯, 묶음, 해당없음 };
}
