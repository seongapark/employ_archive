-- 방문 기록. 한 줄이 조회 한 번이다.
--
-- `day` 는 KST 기준 날짜를 **쓸 때** 박아 둔 것이다. 집계가 인덱스를 타야 하고
-- ("오늘" 을 datetime(ts,'+9 hours') 로 계산하면 인덱스를 못 쓴다), 이 저장소의
-- "오늘" 은 한국 오늘이기 때문이다.
CREATE TABLE hit (
  id       INTEGER PRIMARY KEY,
  ts       TEXT NOT NULL,
  day      TEXT NOT NULL,
  domain   TEXT NOT NULL,
  path     TEXT NOT NULL,
  visitor  TEXT NOT NULL,
  session  TEXT NOT NULL,
  ref      TEXT,
  ref_kind TEXT NOT NULL,
  mode     TEXT NOT NULL,
  device   TEXT NOT NULL,
  country  TEXT
);
CREATE INDEX hit_day        ON hit(day);
CREATE INDEX hit_domain_day ON hit(domain, day);

-- 방문자 요약. 보관이 무기한이라 "이 기간에 처음 온 사람" 을 hit 만으로 구하면
-- 해가 갈수록 전 기간을 훑게 된다. 첫 방문일을 쓸 때 한 번 적어 두면 신규/재방문
-- 판정이 인덱스 조회 하나가 된다. day_hits 는 일일 상한 판정용이다.
CREATE TABLE visitor (
  id        TEXT PRIMARY KEY,
  first_day TEXT NOT NULL,
  last_day  TEXT NOT NULL,
  hits      INTEGER NOT NULL,
  day_hits  INTEGER NOT NULL
);
CREATE INDEX visitor_first ON visitor(first_day);
