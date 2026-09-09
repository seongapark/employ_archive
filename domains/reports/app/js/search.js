// 역색인을 만들지 않는다. 2천 건 규모에서 문자열 스캔은 수십 밀리초다.
// 한국어 토큰화를 직접 하면 "청년고용"이 "청년 고용"에 안 걸리는 문제를
// 떠안는다 — 공백을 지워 그 문제를 아예 없앤다.
//
// 규칙이 둘이고 서로 다른 것이다. 헷갈리면 결과가 뒤집힌다.
//  · 폴백 순서(어느 본문을 볼 것인가): 초록 → 목차 → 제목
//  · 가중치(어디서 걸렸을 때 위로 올릴 것인가): 제목 > 저자 > 초록·목차

export function squash(s) {
  return String(s ?? '').replace(/\s+/g, '');
}

const W = { title: 100, authors: 50, abstract: 10, toc: 10 };

export function searchReports(query, reports, abstracts) {
  const q = squash(query);
  if (!q) return [];
  const out = [];
  for (const r of reports || []) {
    const body = (abstracts && abstracts[r.id]) || null;
    let score = 0;
    let hit = null;

    if (squash(r.title).includes(q)) {
      score += W.title;
      hit = { where: 'title', snippet: '' };
    }
    if ((r.authors || []).some((a) => squash(a).includes(q))) {
      score += W.authors;
      if (!hit) hit = { where: 'authors', snippet: '' };
    }

    // 본문 폴백: 초록 → 목차. 제목만 남는 경우는 위에서 이미 잡혔다.
    const sentence = body && sentenceWith(body.abstract, q);
    if (sentence) {
      score += W.abstract;
      hit = { where: 'abstract', snippet: sentence };
    } else if (body) {
      const line = (body.toc || []).find((t) => squash(t).includes(q));
      if (line) {
        score += W.toc;
        hit = { where: 'toc', snippet: line };
      }
    }
    if (hit) out.push({ report: r, score, hit });
  }
  return out.sort((a, b) => b.score - a.score
    || (a.report.published < b.report.published ? 1 : -1));
}

export function sortByDate(hits) {
  return [...hits].sort((a, b) => (a.report.published < b.report.published ? 1 : -1));
}

function sentenceWith(text, q) {
  if (!text) return '';
  for (const s of String(text).split(/(?<=[.!?。])\s+|\n+/)) {
    if (squash(s).includes(q)) return s.trim();
  }
  return '';
}
