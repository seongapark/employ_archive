# 고용전망 아카이브

국내외 주요 기관의 고용·성장·물가 전망치를 모아 발표 회차별 수정 이력과 함께
조회하는 비공식 개인 아카이브. 기획: `고용전망_아카이브_기획서.md`

> 본 서비스는 개인이 제작한 비공식 참고자료이며, 각 기관 원문이 정본입니다.

## 구조

- `core/` — 도메인 공통 껍데기(토큰·기본 스타일·셸 유틸). 원본은 여기 하나뿐이며
  빌드 시 사이트 루트와 각 도메인 폴더로 복사된다
- `hub/` — 4개 영역 런처. 도메인의 `data/last_run.json` 유무로 활성/준비중을 판정한다
- `domains/<이름>/` — 도메인 수직 슬라이스. `app/`(화면) `data/`(데이터)
  `pipeline/`(수집기) `tests/`
- `tools/build.py` — 사이트 조립. 배포와 로컬 서버가 이 함수를 공유한다
- `.github/workflows/` — 도메인별 수집 + Pages 배포

## 전망 수집기

| 기관 | 경로 | 비고 |
|---|---|---|
| OECD·IMF | 공개 API | 값이 그대로 오므로 `verified` |
| 한국은행 | 게시판 RSS → 본문 → 첨부 PDF | 목록 페이지는 JS로 그려져 RSS를 쓴다. RSS가 회차 제목·발표일시를 준다 |
| KDI | `/research/economy`(=최신호 본문) → 장별 PDF | PDF 표지에 발표일이 없어 날짜는 이 페이지에서 얻는다 |

PDF는 요약표 한 페이지만 읽는다(`pipeline/pdf.py`). 표의 열 구성이 기관·회차마다
다르므로(한국은행 7열, KDI 6열, KDI 수정호는 수정폭 2열 추가) 열 위치를 고정하지 않고
헤더의 연도·기간 토큰으로 열을 복원하며, 어긋나면 조용히 넘기지 않고 실패시킨다.
반기 전망도 함께 저장한다(연간 id는 그대로 두고 반기만 뒤에 `-h1`·`-h2`를 붙인다).
집계·비교·타임라인은 연간 기준이고, 반기는 홈 카드와 기관 상세에 참고로만 붙는다.
반기를 내지 않는 기관(IMF·OECD)은 `-` 로 표시한다.

수집 실패는 `data/last_run.json` 에 한 줄로 남고 워크플로가 그날 실행을 빨갛게 만든다.
원인을 이미 아는 외부 장애는 `collect-forecast.yml` 의 `KNOWN_DOWN` 에 적어 통과시킨다
— 오래 죽은 수집기 하나 때문에 매일 빨개지면 다른 수집기가 깨진 날을 놓친다.
적어둔 수집기가 되살아나면 워크플로가 지우라고 알린다(`pipeline/check_run.py`).

## 실행

```bash
pip install -r requirements.txt
python -m pytest                              # 파이썬 테스트 (네트워크 불필요)
node --test "core/tests/*.mjs" "hub/tests/*.mjs" "domains/forecast/tests/web/*.mjs"   # 웹 테스트
python -m tools.serve                         # 로컬 서버 (http://127.0.0.1:8642/)
python -m domains.forecast.pipeline.collect   # 전망 수집 1회
```

웹앱은 `python -m tools.serve` 로 조립된 사이트를 그대로 띄운다. 앱 폴더의 `index.html`을
`file://`로 직접 열면 `./core/` 참조가 깨지므로 반드시 이 서버를 쓴다.
