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

## 실행

```bash
pip install -r requirements.txt
python -m pytest                              # 파이썬 테스트 (네트워크 불필요)
node --test core/tests/ hub/tests/ domains/forecast/tests/web/   # 웹 테스트
python -m tools.serve                         # 로컬 서버 (http://127.0.0.1:8642/)
python -m domains.forecast.pipeline.collect   # 전망 수집 1회
```

웹앱은 `python -m tools.serve` 로 조립된 사이트를 그대로 띄운다. 앱 폴더의 `index.html`을
`file://`로 직접 열면 `./core/` 참조가 깨지므로 반드시 이 서버를 쓴다.
