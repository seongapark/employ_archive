# 고용전망 아카이브

국내외 주요 기관의 고용·성장·물가 전망치를 모아 발표 회차별 수정 이력과 함께
조회하는 비공식 개인 아카이브. 기획: `고용전망_아카이브_기획서.md`

> 본 서비스는 개인이 제작한 비공식 참고자료이며, 각 기관 원문이 정본입니다.

## 구조

- `data/forecasts.json` — 전망치 레코드 (스키마: `src/models.py`)
- `data/orgs.json`, `data/indicators.json` — 기관·지표 메타
- `src/collect.py` — 수집 오케스트레이터. 저장된 최신값과 다를 때만 신규 레코드 추가
- `src/collectors/` — 기관별 수집기 (현재 IMF·OECD API)
- `.github/workflows/collect.yml` — 매일 16:00 KST 자동 수집

## 실행

```bash
pip install -r requirements.txt
python -m pytest        # 테스트 (네트워크 불필요)
python -m src.collect   # 실제 수집 1회
```

웹앱: `web/` (GitHub Pages 자동 배포, 로컬은 `python -m http.server` 후 `/web/` 접속)
