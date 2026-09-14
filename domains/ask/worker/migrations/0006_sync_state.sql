-- 적재 지문. "저 DB 에 이미 이 내용이 들어 있나" 하나만 답한다.
--
-- 적재기 둘 다 내용이 그대로여도 전량을 다시 쓴다 — d1_sync 는 모든 행에
-- upsert 를 내고, fts_load 는 FTS5 가 upsert 를 못 받아 DELETE 후 전량 INSERT
-- 한다. D1 은 값이 같아도 쓰기로 세므로 아무것도 안 바뀐 날에도 고용동향
-- 8,823행이 나갔다. 2026-09-13 에 하루 10만행 한도를 넘겼다.
--
-- 지문을 저장소가 아니라 여기에 두는 이유는 §tools/d1_gate.py 에 적어 뒀다:
-- 적재가 반만 들어간 회차 뒤에 저장소의 기록과 DB 가 어긋날 수 있고, 그때
-- 건너뛰면 깨진 채로 굳는다. 도장은 적재·검증이 끝난 뒤에만 찍는다.
--
-- tools/d1_gate.py 도 CREATE TABLE IF NOT EXISTS 를 직접 낸다. 이 파일은 새 DB
-- 를 세울 때의 정본이고, 그쪽은 마이그레이션을 손으로 돌리기 전에도 게이트가
-- 도는 데 필요하다(DEPLOY.md §1-3 은 사람이 실행한다).
CREATE TABLE IF NOT EXISTS sync_state (
  키    TEXT PRIMARY KEY,
  지문  TEXT NOT NULL,
  시각  TEXT NOT NULL
);
