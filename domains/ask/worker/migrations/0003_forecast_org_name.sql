-- 전망 카드 머리에 기관 이름을 한글로 쓴다. `BOK` 보다 `한국은행` 이 읽힌다.
--
-- 정본은 domains/forecast/data/forecasts.json 의 org_name_ko 로, 이미 행마다
-- 들고 있는데 D1 표에만 없어서 화면이 영문 코드를 그대로 냈다. 다음 동기화가
-- 채운다 — 그전까지 API 는 org 로 떨어뜨린다(빈칸을 내지 않는다).
ALTER TABLE forecast ADD COLUMN org_name_ko TEXT;
