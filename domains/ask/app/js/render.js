// DOM 렌더러. badge.js 의 순수 함수만 쓰고, 여기 자체는 테스트 대상이 아니다
// (node --test 는 DOM 이 없다 — 그래서 render.test.mjs 는 badge.js 만 담는다).

import { isSampleErrorText, safeHref } from './badge.js';

function fmtVal(v) {
  return typeof v === 'number' ? v.toLocaleString('ko-KR') : String(v);
}

// 리뷰 라운드 2 판정 2: 전망 기관은 source_catalog 에 등재돼 있지 않다(출처가
// 없는 게 아니라 카탈로그가 없는 것 — forecast 행 자체가 org·source_url·
// landing_url 을 들고 있다. 그게 원문이다). 그래서 전망의 출처 블록은
// source_catalog 조회(카드.소스) 가 아니라 forecast 행에서 직접 그린다.
function 전망출처목록(전망행들) {
  const seen = new Map();
  for (const r of 전망행들 ?? []) {
    if (!r.org || seen.has(r.org)) continue;
    seen.set(r.org, { name_ko: r.org, endpoint: r.landing_url ?? r.source_url ?? null });
  }
  return [...seen.values()];
}

// Minor(리뷰 라운드 1): href 는 안전한 스킴일 때만 링크로 그리고, 아니면 평문으로
// 그린다 — 카탈로그가 오염돼도 클릭이 코드를 실행하면 안 된다.
function 링크또는텍스트(esc, url, label) {
  const safe = safeHref(url);
  return safe
    ? `<a href="${esc(safe)}" target="_blank" rel="noopener">${esc(label)}</a>`
    : `<span class="ev__nolink">${esc(label)}</span>`;
}

// 파생 수치를 표 형태로 그린다. **유의성사유(RSE)는 여기 안 넣는다** — 규칙 3:
// 관측값과 같은 자리·서식으로 그리면 사용자가 표본오차를 관측값으로 읽는다.
function 파생표(esc, 파생) {
  const 라벨 = { 합계: '합계', 차이: '차이', 증감률: '증감률(%)', 비중: '비중(%)', 기여도: '기여도(%)' };
  return Object.entries(파생 ?? {})
    .filter(([k]) => k in 라벨)
    .map(([k, v]) => `<span class="num-chip"><b>${esc(라벨[k])}</b> ${esc(fmtVal(v))}</span>`)
    .join('');
}

// 규칙 3: RSE(표본오차) 문구는 한계·주석 자리에, 시각적으로 다른 스타일로 둔다.
function 유의성주석(esc, e) {
  if (!e || e.유의성사유 == null) return '';
  const 표본오차 = isSampleErrorText(e.유의성사유);
  return `<p class="ev__sig${표본오차 ? ' ev__sig--rse' : ''}">
    표본오차 참고 — ${esc(e.유의성사유)}${e.유의성 === '불명' ? ' (유의성 불명)' : ''}
  </p>`;
}

function 근거행(esc, e) {
  const 이름 = e.name_ko ?? e.지표;
  if (e.data_status && e.data_status !== '보유') {
    return `<div class="ev ev--missing">
      <b>${esc(이름)}</b>
      <em>미보유 — ${esc(e.우회경로 ?? e.사유 ?? '수집기 추가로 해결')}</em>
    </div>`;
  }
  return `<div class="ev">
    <b>${esc(이름)}</b>
    <span class="ev__basis">${esc(e.compare_basis ?? '')}</span>
    <div class="ev__nums">${파생표(esc, e.파생)}</div>
    ${유의성주석(esc, e)}
  </div>`;
}

// 지지·반증을 좌우 두 열로 병치한다 — 위아래로 쌓지 않는다. 이 병치 자체가
// "H1 을 주장하려면 H2 를 먼저 기각해야 한다"는 이 프로젝트의 주장이다.
function 가설카드(esc, h, columns) {
  const c = columns(h);
  const col = (rows, 비었음, 제목) => `<div class="col">
    <h4>${esc(제목)}</h4>
    ${비었음 ? '<p class="col__empty">비었음 — 지표 없음</p>' : rows.map((r) => 근거행(esc, r)).join('')}
  </div>`;
  const 판정 = h.판정 ?? {};
  const 판정문 = 판정.verdict_capable
    ? `판정 가능${판정.verdict_strength ? ` · ${esc(판정.verdict_strength)}` : ''}`
    : `판정 불가${판정.verdict_blocked_by ? ` · ${esc(판정.verdict_blocked_by)}` : ''}`;
  return `<article class="hyp">
    <h3>${esc(h.name_ko)}</h3>
    <p class="hyp__verdict">${판정문}</p>
    <div class="hyp__cols">${col(c.지지, c.지지비었음, '지지 증거')}${col(c.반증, c.반증비었음, '반증 증거')}</div>
    ${(h.missing_for_verdict ?? []).length
      ? `<p class="hyp__missing">판정에 필요한 것: ${esc(h.missing_for_verdict.join(', '))}</p>` : ''}
    ${h.우회경로 ? `<p class="hyp__detour">우회: ${esc(h.우회경로)}</p>` : ''}
  </article>`;
}

function 지표폴백(esc, 카드) {
  return `<p class="fallback__note">
    현상이 등록돼 있지 않아 판정은 건너뛰고, 무엇을 봐야 하는지만 보여준다
    (보유 ${카드.보유수 ?? 0} · 미보유 ${카드.미보유수 ?? 0})
  </p>` + (카드.지표 ?? []).map((i) => 근거행(esc, i)).join('');
}

// Important 4(리뷰 라운드 1): 몇 년도 전망인지·단위가 뭔지 없으면 숫자가 뜻을
// 잃는다. target_year·target_period·unit 을 함께 그리고, 연도로 묶어 보여준다
// (ask.mjs 도 슬롯이 연도를 지목하면 그 범위로 조회를 좁히도록 같이 고쳤다).
function 전망행(esc, r) {
  const 시점 = [r.target_year != null ? `${r.target_year}년` : null, r.target_period]
    .filter((x) => x != null && x !== '').join(' ');
  return `<div class="ev">
    <b>${esc(r.org ?? r.기관 ?? '')}</b>
    <span class="ev__basis">${esc(시점)}${r.published_at ? ` · 발표 ${esc(r.published_at)}` : ''}</span>
    <div class="ev__nums"><span class="num-chip">${esc(fmtVal(r.value ?? r.값 ?? ''))}${r.unit ? ` ${esc(r.unit)}` : ''}</span></div>
  </div>`;
}

function 전망블록(esc, 카드) {
  const 연도별 = new Map();
  for (const r of 카드.전망 ?? []) {
    const key = r.target_year != null ? String(r.target_year) : '연도 미상';
    if (!연도별.has(key)) 연도별.set(key, []);
    연도별.get(key).push(r);
  }
  const rows = [...연도별.entries()].map(([year, items]) => `
    <div class="forecast-year">
      <h4>${esc(year === '연도 미상' ? year : `${year}년 전망`)}</h4>
      ${items.map((r) => 전망행(esc, r)).join('')}
    </div>`).join('');
  const 근거서술 = (카드.근거서술 ?? []).map((r) => `<blockquote class="rationale">
    ${esc(r.text ?? r.내용 ?? '')}
    ${r.url ? 링크또는텍스트(esc, r.url, '원문') : ''}
  </blockquote>`).join('');
  return rows + 근거서술;
}

function 비교블록(esc, 비교) {
  if (!비교) return '';
  return `<div class="compare">
    <p class="compare__basis"><b>비교 가능</b> ${esc(비교.비교가능)}</p>
    ${(비교.차이유형 ?? []).length ? `<p>차이 유형: ${esc(비교.차이유형.join(' · '))}</p>` : ''}
    ${(비교.설명 ?? []).map((s) => `<p class="compare__note">${esc(s)}</p>`).join('')}
    ${(비교.근거 ?? []).length ? `<ul class="compare__refs">${(비교.근거 ?? []).map((g) =>
      `<li>${esc(g.id)} — ${esc(g.evidence ?? '')}${g.verified_at ? ` (확인 ${esc(g.verified_at)})` : ''}</li>`).join('')}</ul>` : ''}
  </div>`;
}

// Important 3(리뷰 라운드 1): 답변 문장이 검증실패·한도초과·할당량확인불가로
// 사라지면, 원인탐색에서 "무슨 현상을 판정하려던 건지" 조차 모른 채 가설 카드만
// 보이던 문제. 현상(name_ko·정의·근거서술)을 가설 열 위에 항상 그린다 — 근거서술은
// 관측만 담긴 문장이니 그대로 보여준다.
function 현상블록(esc, 현상) {
  if (!현상) return '';
  return `<div class="phenomenon">
    <h3>${esc(현상.name_ko ?? '')}</h3>
    ${현상.정의 ? `<p class="phenomenon__def">${esc(현상.정의)}</p>` : ''}
    ${현상.근거서술 ? `<p class="phenomenon__evidence">${esc(현상.근거서술)}</p>` : ''}
  </div>`;
}

// 메타한계·범위밖: 근거가 아니라 "무엇을 낼 수 있고 무엇을 못 내는지" 가 내용이다.
function 라우팅블록(esc, 라우팅) {
  if (!라우팅) return '';
  const 목록 = (title, rows, withReason) => rows.length
    ? `<p class="routing__group"><b>${esc(title)}</b> ${rows.map((r) => (
        withReason ? `${esc(r.source)}(${esc(r.사유)})` : esc(r))).join(' · ')}</p>`
    : '';
  return `<div class="routing">
    ${목록('가능', 라우팅.가능 ?? [], false)}
    ${목록('부분', 라우팅.부분 ?? [], true)}
    ${목록('불가', 라우팅.불가 ?? [], true)}
  </div>`;
}

// Minor(리뷰 라운드 1): `가설없음`·`판정없음`을 배열 길이로 간접 추론하지 않고
// 카드가 실어 준 그 필드를 그대로 읽는다 — 둘은 서로 다른 신호이고, 필드가 있는데
// 배열 길이로 재추론하면 필드가 바뀔 때 조용히 어긋난다.
function evidenceHtml(esc, 카드, columns) {
  if (카드.가설 || 카드.가설없음) {
    const 현상 = 현상블록(esc, 카드.현상);
    if (카드.가설없음) {
      return `${현상}<p class="col__empty">비었음 — 이 현상에 등록된 가설이 없다</p>`;
    }
    const 전부판정불가 = 카드.판정없음
      ? '<p class="hyp__all-blocked">이 현상에 등록된 가설은 아직 전부 판정할 수 없다</p>' : '';
    return 현상 + 전부판정불가 + (카드.가설 ?? []).map((h) => 가설카드(esc, h, columns)).join('');
  }
  if (카드.지표) return 지표폴백(esc, 카드);
  if (카드.전망 || 카드.근거서술) return 전망블록(esc, 카드);
  if (카드.비교) return 비교블록(esc, 카드.비교) + (카드.근거 ?? []).map((e) => 근거행(esc, e)).join('');
  if ((카드.근거 ?? []).length) return (카드.근거 ?? []).map((e) => 근거행(esc, e)).join('');
  return 라우팅블록(esc, 카드.라우팅);
}

// Important 2(리뷰 라운드 1): meta() 가 만들고 ask.mjs 가 싣는 `충돌`(출처 간 상충
// 기록)을 화면이 한 번도 안 읽었다 — 여러 출처가 걸릴 때 "왜 서로 다른지" 를 보여줄
// 자리가 통째로 빠져 있었다.
function 충돌블록(esc, 충돌) {
  return (충돌 ?? []).map((c) => `<div class="conflict">
    <b>${esc(c.source_a)} ↔ ${esc(c.source_b)}</b>
    <span class="conflict__basis">${esc(c.비교가능 ?? '')}</span>
    <p>${esc(c.차이유형 ?? '')} — ${esc(c.설명 ?? '')}</p>
  </div>`).join('');
}

export function renderAll(카드, { esc, badgeLabel, understandLine, evidenceColumns, go }) {
  const $ = (id) => document.getElementById(id);

  // ── 이해 카드: 슬롯(매핑됨)과 원문슬롯(LLM 원문)을 둘 다 쓴다 ──────────────
  // 원문슬롯이 null 이면(할당량이 막혀 1패스를 못 돌린 경우) 접거나 생략한다 —
  // 없는 걸 지어내지 않는다.
  const u = $('understand');
  if (카드.원문슬롯 == null) {
    u.hidden = true;
  } else {
    u.hidden = false;
    u.querySelector('summary').textContent = understandLine(카드.유형);
    // 기본은 접힘 — 저확신일 때만 펼친다. 정상 케이스에서 펼쳐져 있으면 답을 가린다.
    u.open = !!카드.저확신;
    const raw = Object.entries(카드.원문슬롯 ?? {})
      .filter(([, v]) => v != null && v !== '' && !(Array.isArray(v) && v.length === 0))
      .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join('·') : (typeof v === 'object' ? JSON.stringify(v) : v)}`)
      .join(', ');
    $('raw').textContent = raw ? `질문 원문 이해: ${raw}` : '';
    $('slots').innerHTML = Object.entries(카드.슬롯 ?? {})
      .map(([k, v]) => `<span class="chip">${esc(k)}: ${esc(
        Array.isArray(v) ? (v.length ? v.join('·') : '(없음)')
          : (typeof v === 'object' ? JSON.stringify(v) : (v || '(없음)')))}</span>`)
      .join('');
  }

  // ── 배지: 전부 카드.배지 배열에서 나온다. 화면이 지어내지 않는다 ─────────
  $('badges').innerHTML = (카드.배지 ?? []).map((c) => {
    const b = badgeLabel(c);
    return `<span class="badge badge--${b.색}">${esc(b.라벨)}</span>`;
  }).join('');

  // ── 답변: 검증실패·한도초과·할당량확인불가면 이 블록만 사라진다. 근거는 남는다 ──
  $('answer').innerHTML = 카드.답변 ? `<p class="answer__text">${esc(카드.답변)}</p>` : '';

  // ── 근거: 유형별로 모양이 다르다 ──────────────────────────────────────
  $('evidence').innerHTML = evidenceHtml(esc, 카드, evidenceColumns);

  // ── 한계·미확인 ──────────────────────────────────────────────────────
  $('limits').innerHTML = [
    ...(카드.한계 ?? []),
    ...(카드.미확인 ?? []).map((m) => `근거 미확인: ${typeof m === 'string' ? m : (m.name_ko ?? JSON.stringify(m))}`),
  ].map((l) => `<li>${esc(l)}</li>`).join('');

  // ── 소스 ── 스펙 §6: 원문 링크 + 확인일 + evidence_status. 링크는 http/https
  // 화이트리스트일 때만 그린다(Minor: href 스킴 검증). 전망은 source_catalog 가
  // 아니라 forecast 행(org·landing_url·source_url)에서 직접 그린다(판정 2) ──────
  const 소스행 = (카드.전망 || 카드.근거서술) ? 전망출처목록(카드.전망) : (카드.소스 ?? []);
  $('sources').innerHTML = 소스행.map((s) =>
    `<div class="source">${링크또는텍스트(esc, s.endpoint, s.name_ko ?? s.id)}
     <small>${esc(s.verified_at ?? '')} ${esc(s.evidence_status ?? '')}</small></div>`).join('');

  // ── 충돌: 소스가 둘 이상 걸릴 때 "왜 서로 다른지" ───────────────────
  $('conflicts').innerHTML = 충돌블록(esc, 카드.충돌);

  // ── 범위밖: "이건 못 하지만 이건 됩니다" ────────────────────────────
  $('followups').innerHTML = '';
  const 후속 = [...(카드.후속질문 ?? []), ...(카드.답할수있는질문 ?? [])];
  for (const s of 후속) {
    const b = document.createElement('button');
    b.className = 'chip chip--btn';
    b.type = 'button';
    b.textContent = s;
    b.addEventListener('click', () => { location.hash = `#/q=${encodeURIComponent(s)}`; });
    $('followups').appendChild(b);
  }

  // "· 수정" — 슬롯을 항목별로 고치는 UI 대신, 가장 정직한 수정 창구인 질문
  // 입력창에 포커스를 돌려준다(사용자가 다시 쓴 문장이 그대로 1패스로 다시 간다).
  // go 는 이 지점을 확장할 자리로 받아 두되 지금은 쓰지 않는다.
  void go;
  const editBtn = $('understand-edit');
  if (editBtn) {
    editBtn.onclick = () => { $('q').focus(); $('q').select(); };
  }
}
