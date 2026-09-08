-- domains/ask/worker/migrations/0001_init.sql
-- 카탈로그 8표 + 데이터 4표 + 판정 뷰 1.
-- 인덱스를 미리 거는 이유: D1 과금이 반환행이 아니라 스캔행 기준이라는 근거가
-- 2차 출처다(스펙 §10-7). 사실이면 인덱스가 필수고, 아니어도 인덱스는 옳다.

CREATE TABLE source_catalog (
  id TEXT PRIMARY KEY, name_ko TEXT NOT NULL, agency TEXT, grade TEXT NOT NULL,
  axis TEXT, method TEXT, auth TEXT, endpoint TEXT, rate_limit TEXT,
  archived INTEGER NOT NULL DEFAULT 0, priority INTEGER,
  terms_of_use TEXT, body_storable INTEGER,
  evidence TEXT, verified_at TEXT, evidence_status TEXT NOT NULL DEFAULT '미확인'
);

CREATE TABLE capability (
  source_id TEXT PRIMARY KEY REFERENCES source_catalog(id),
  주제 TEXT, 집단축 TEXT, 지역입도 TEXT, 시간입도 TEXT,
  기간_from TEXT, 기간_to TEXT, 공표시차 TEXT,
  evidence TEXT, verified_at TEXT, evidence_status TEXT NOT NULL DEFAULT '미확인'
);

CREATE TABLE capability_limit (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES source_catalog(id),
  유형 TEXT NOT NULL CHECK (유형 IN ('커버리지','교차제한','입도','시의성','접근성','업데이트')),
  axis TEXT, category TEXT, 내용 TEXT NOT NULL, 사유 TEXT NOT NULL,
  evidence TEXT, verified_at TEXT, evidence_status TEXT NOT NULL DEFAULT '미확인'
);

CREATE TABLE source_conflict (
  id TEXT PRIMARY KEY,
  source_a TEXT NOT NULL REFERENCES source_catalog(id),
  source_b TEXT NOT NULL REFERENCES source_catalog(id),
  차이유형 TEXT NOT NULL CHECK (차이유형 IN ('개념','모집단','교차제한','산업커버리지','시의성')),
  설명 TEXT NOT NULL,
  비교가능 TEXT NOT NULL CHECK (비교가능 IN ('수준','증감률만','불가')),
  evidence TEXT, verified_at TEXT, evidence_status TEXT NOT NULL DEFAULT '미확인'
);

CREATE TABLE phenomenon (
  id TEXT PRIMARY KEY, name_ko TEXT NOT NULL, 정의 TEXT, 지역 TEXT, 기간 TEXT,
  time_grain TEXT NOT NULL CHECK (time_grain IN ('월','반기','연')),
  근거서술 TEXT
);

CREATE TABLE hypothesis (
  id TEXT PRIMARY KEY,
  phenomenon_id TEXT NOT NULL REFERENCES phenomenon(id),
  name_ko TEXT NOT NULL, 서술 TEXT,
  대립가설 TEXT NOT NULL CHECK (대립가설 <> '[]'),   -- §8 대립가설 없는 가설은 등록 거부
  missing_for_verdict TEXT, 우회경로 TEXT, 검정력_주석 TEXT
);

CREATE TABLE indicator (
  id TEXT PRIMARY KEY, name_ko TEXT NOT NULL,
  source_id TEXT NOT NULL REFERENCES source_catalog(id),
  정의 TEXT, 모집단 TEXT, 단위 TEXT, 공표시차 TEXT, 커버리지한계 TEXT,
  data_status TEXT NOT NULL CHECK (data_status IN ('보유','미보유')),
  time_grain TEXT NOT NULL CHECK (time_grain IN ('월','반기','연')),
  compare_basis TEXT NOT NULL CHECK (compare_basis IN ('수준','증감률만')),
  series_key TEXT
);

CREATE TABLE hyp_indicator (
  hypothesis_id TEXT NOT NULL REFERENCES hypothesis(id),
  indicator_id TEXT NOT NULL REFERENCES indicator(id),
  role TEXT NOT NULL CHECK (role IN ('지지','falsifies')),
  timing TEXT NOT NULL CHECK (timing IN ('선후검정','수준확인','특정성')),
  expected_sign TEXT, lead_lag TEXT, falsifies TEXT,
  PRIMARY KEY (hypothesis_id, indicator_id),
  -- lead_lag 는 선후검정에서만 읽는다
  CHECK (timing = '선후검정' OR lead_lag IS NULL)
);

CREATE TABLE observation (
  id TEXT PRIMARY KEY, source TEXT NOT NULL, series TEXT, breakdown TEXT,
  category TEXT, period TEXT NOT NULL, value REAL, unit TEXT, yoy REAL,
  status TEXT, rse REAL, rse_flag TEXT, released_at TEXT, release_url TEXT
);

CREATE TABLE forecast (
  id TEXT PRIMARY KEY, org TEXT NOT NULL, report_title TEXT, published_at TEXT,
  target_year INTEGER, target_period TEXT, indicator TEXT, value REAL, unit TEXT,
  prev_value REAL, revision REAL, source_url TEXT, landing_url TEXT
);

CREATE TABLE forecast_rationale (
  org TEXT NOT NULL, published_at TEXT NOT NULL, indicator TEXT NOT NULL,
  text TEXT, tags TEXT, source_url TEXT, source_page INTEGER,
  PRIMARY KEY (org, published_at, indicator)
);

CREATE TABLE release (
  id TEXT PRIMARY KEY, source TEXT, month TEXT, title TEXT,
  posted_at TEXT, url TEXT, attachments TEXT
);

CREATE INDEX idx_obs        ON observation(source, breakdown, category, period);
CREATE INDEX idx_obs_period ON observation(period);
CREATE INDEX idx_fc         ON forecast(indicator, target_year, published_at);
CREATE INDEX idx_lim        ON capability_limit(source_id, 유형);

CREATE VIEW hypothesis_verdict AS
WITH f AS (
  SELECT h.id AS hypothesis_id,
         COUNT(x.indicator_id)                                        AS n_falsify,
         SUM(CASE WHEN i.data_status <> '보유' THEN 1 ELSE 0 END)      AS n_missing,
         SUM(CASE WHEN i.time_grain <> p.time_grain
                    OR i.compare_basis = '증감률만' THEN 1 ELSE 0 END) AS n_weak
    FROM hypothesis h
    JOIN phenomenon p         ON p.id = h.phenomenon_id
    LEFT JOIN hyp_indicator x ON x.hypothesis_id = h.id AND x.role = 'falsifies'
    LEFT JOIN indicator i     ON i.id = x.indicator_id
   GROUP BY h.id
)
SELECT f.hypothesis_id AS id,
       (f.n_falsify > 0 AND f.n_missing = 0) AS verdict_capable,
       CASE
         WHEN NOT (f.n_falsify > 0 AND f.n_missing = 0) THEN NULL
         WHEN f.n_weak > 0                              THEN 'weak'
         ELSE 'strong'
       END AS verdict_strength,
       CASE
         WHEN f.n_falsify = 0 THEN '반증미설계'
         WHEN f.n_missing > 0 THEN '데이터미보유'
         ELSE NULL
       END AS verdict_blocked_by,
       f.n_falsify, f.n_missing
  FROM f;
