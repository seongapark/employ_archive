-- domains/ask/worker/migrations/0005_fts_date.sql
-- 색인에 **날짜**를 더한다. 0004 에 열을 하나 얹은 것 말고는 같다.
--
-- 왜 필요한가: "최근 고용상황은?" 같은 질문에서 2014년 초록이 2026년 기사보다
-- 위에 오는 것을 막을 방법이 없었다. 날짜가 색인에 없으니 최신성으로 정렬할 수도,
-- "작년" 으로 걸러낼 수도 없었다 — 순위가 걸린 낱말 수만으로 정해졌다.
--
-- 날짜는 **UNINDEXED** 다. 검색어로 쓰는 값이 아니라 정렬·필터에 쓰는 값이다
-- (색인에 넣으면 trigram 이 '2026' 같은 조각을 본문 낱말처럼 취급한다).
--
-- 형식은 `YYYY-MM-DD` 또는 `YYYY-MM`. 문자열 비교로 기간을 거르므로 자리수가
-- 어긋나면 안 된다. **없는 것은 빈 문자열**이다 — 카탈로그의 한계·충돌은 특정
-- 시점의 글이 아니라 상시 사실이라 날짜가 없고, 기간 필터에서도 빠지지 않는다
-- (`''` 를 "오래된 것" 으로 취급하면 상시 사실이 조용히 사라진다).
--
-- FTS5 가상표는 열을 추가하는 ALTER 를 못 받는다. 적재가 애초에 전량
-- 재적재(DELETE 후 INSERT)라 지우고 다시 세우는 것이 같은 일이다.
DROP TABLE IF EXISTS doc_fts;

CREATE VIRTUAL TABLE doc_fts USING fts5(
  doc_id UNINDEXED,
  도메인 UNINDEXED,
  종류   UNINDEXED,
  링크   UNINDEXED,
  제목   UNINDEXED,
  본문   UNINDEXED,
  날짜   UNINDEXED,
  제목색인,
  본문색인,
  tokenize = 'trigram'
);
