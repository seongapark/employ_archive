"""전망 근거를 LLM 으로 골라 rationales.json 에 넣는다.

CI 가 이 도구를 부르지 않는다. 근거는 회차당 한 번 정해지면 되는 것이라
매일 돌 이유가 없고, 도구로 두면 LLM 이 죽든 키가 만료되든 매일 도는
수치 수집과 배포는 그대로 돈다.

이미 있는 항목은 덮지 않는다 — 사람이 문장을 다듬었을 수 있다. 일부러
다시 만들려면 --refresh 로 대상을 명시해야 한다.

--only 와 --refresh 는 서로 다른 이름 공간을 쓴다. --only 는
documents.SOURCES 의 키(소문자, 예: "bok"·"kdi"·"oecd_interim" — "본문을
어떻게 가져오는가"를 가르는 기술적 경로 이름)를 받고, --refresh 는
rationales.json 안의 키(Rationale.org·published_at·indicator)를 그대로
받는다. org 은 보통 "BOK"·"KDI"·"KEIS"·"KLI"·"KIET"·"OECD" 처럼 기관을
표시하는 이름이다("oecd_interim" 소스가 만드는 근거의 org 은 "OECD" 다 —
소스 키와 표시 이름이 케이스도 다르고 글자 수도 다르다). 하나로 합치지
않는다 — 뜻이 다른 두 이름을 같은 낱말로 쓰면 다음에 소스가 하나 더
생길 때 그 소스의 org 이 소스 키와 우연히 같을 거라고 짐작하게 된다.
대신 --refresh 오타(기관 철자·발표일·지표 어디든)를 여기서 미리 막지
않는다 — run() 이 existing 과 실제로 맞대 보고 하나도 안 맞으면 그 사실을
보고서에 그대로 남긴다. 그러면 무엇이 왜 안 맞았는지 실행 결과만 보고도
알 수 있다.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from domains.forecast.pipeline import llm_select, llm_verify, rationale
from domains.forecast.pipeline import rationale_store as rs
from domains.forecast.pipeline.documents import SOURCES

DATA_DIR = Path(__file__).resolve().parent.parent / "domains" / "forecast" / "data"


@dataclass
class Report:
    saved: int = 0
    skipped: int = 0
    rejected: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    # refresh 대상인데 existing 의 어떤 키와도 안 맞는 것들 — 기관 철자·
    # 발표일·지표 표기 오타가 이 자리에 걸린다. lines 안의 한국어 문장으로만
    # 남기면 main() 이 그 사실을 알려면 문자열을 뒤져야 한다 — 구조화된
    # 필드를 따로 둬서 종료 코드 판정이 문자열 매칭에 기대지 않게 한다.
    # "대상은 있는데 이번 실행이 대체물을 못 만든" 경우는 여기 들어가지
    # 않는다 — 그건 오타가 아니라 정상적인 재시도 대상이라 exit 0 을
    # 유지한다(모듈 main() 문서 참고).
    unmatched_refresh: list[tuple[str, date, str]] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)


def run(data_dir, *, sources=None, select=None, only=None, refresh=()) -> Report:
    """근거를 새로 뽑아 rationales.json 에 병합한다.

    refresh 는 (org, published_at, indicator) 키의 모음이다 — "이번 실행이
    다시 만들 수 있으면 다시 만들어도 좋다"는 허락이지, "지워라"는 명령이
    아니다. 그래서 순서가 중요하다: fresh(이번에 실제로 검증까지 통과한 새
    근거)를 다 만든 **다음에야** existing 에서 무엇을 뺄지 정한다.

    거꾸로 먼저 지우고 나중에 채우면, 이번 실행이 그 기관을 건드리지
    않았거나(--only 가 그 소스를 뺐거나), 모델이 그 회차에서 아무것도
    못 찾았거나, 대조에서 떨어졌을 때 — 지운 자리를 아무도 다시 채우지
    못한다. 그 결과가 조용한 손실이다: rep.saved 는 (지운 뒤의) existing
    을 기준으로 세므로 개수에 구멍이 드러나지 않고, exit code 도 0 이다.
    그래서 이 함수는 실제로 새 대체물을 손에 쥐었을 때만(그 키가 fresh
    에 있을 때만) existing 에서 그 키를 뺀다. 대체물을 못 만든 refresh
    대상은 그대로 남기고, 왜 남았는지(대체물을 못 만들었는지, 애초에 그런
    키가 없는지)를 rep.lines 에 적는다.
    """
    sources = SOURCES if sources is None else sources
    select = select or llm_select.select
    refresh = set(refresh)
    path = Path(data_dir) / "rationales.json"
    existing, load_error = rs.load_or_empty(path)
    rep = Report()
    if load_error:
        rep.failures.append(f"rationales.json 을 읽지 못했다: {load_error}")
        return rep  # 사람이 고치던 파일을 기계 파일로 덮지 않는다

    existing_keys = {r.key for r in existing}

    fresh: list[rs.Rationale] = []
    for name, listing in sources.items():
        if only and name not in only:
            continue
        try:
            listed_all = listing()
        except Exception as exc:
            rep.failures.append(f"{name} 목록: {type(exc).__name__}: {exc}")
            continue
        for listed in listed_all:
            # fetch_pages·select 뿐 아니라 후보를 거르는 아래 루프까지
            # 통째로 이 try 안에 둔다 — 이 회차가 무엇 때문에 죽든(본문
            # 획득 실패든, 모델 응답이든, 예상 못 한 다른 무엇이든) 이미
            # 이 함수가 다른 회차에서 쌓은 fresh 를 잃지 않고 다음 회차로
            # 넘어가야 한다. 후보 루프 자체가 지금은 예외를 던질 이유가
            # 실측으로 없지만(llm_select 가 반환값 형식을 이미 검증한다),
            # 그 안전은 이 함수가 아니라 llm_select 가 지키는 것이므로
            # 여기서도 감싸 둔다 — 한 회차의 사고가 그 뒤 회차까지
            # 끌고 내려가면 안 된다는 규칙에 예외를 두지 않는다.
            try:
                source_url, pages = listed.fetch_pages()
                picked = select(listed.org, listed.title, listed.indicators, pages)
                stored = 0
                rejected_here = 0
                for p in picked:
                    if p.indicator not in listed.indicators:
                        rep.rejected.append(
                            f"{listed.org} {listed.title} {p.indicator}: "
                            "이 기관이 전망하지 않는 지표다")
                        rejected_here += 1
                        continue
                    if not (0 < p.source_page <= len(pages)):
                        # verify() 에 넘기지 않는다 — page_text 를 ""로 두고
                        # 넘기면 verify 가 "원문에 없다"로 거절해, 모델이
                        # 잘못된 쪽번호를 댔을 뿐인데 문장을 지어낸 것처럼
                        # 보고서에 남는다. 원인이 다르면 메시지도 달라야
                        # 사람이 엉뚱한 가설(프롬프트가 새어나갔다)로
                        # 새지 않는다.
                        rep.rejected.append(
                            f"{listed.org} {listed.title} {p.indicator}: "
                            f"source_page {p.source_page} 이(가) 본문 쪽수"
                            f"(1~{len(pages)}) 범위를 벗어난다")
                        rejected_here += 1
                        continue
                    page_text = pages[p.source_page - 1]
                    try:
                        text = llm_verify.verify(p.text, page_text)
                    except llm_verify.Rejected as exc:
                        rep.rejected.append(
                            f"{listed.org} {listed.title} {p.indicator}: {exc.reason}")
                        rejected_here += 1
                        continue
                    fresh.append(rs.Rationale(
                        org=listed.org, published_at=listed.published_at,
                        indicator=p.indicator, text=text, tags=rationale.tags_for(text),
                        source_url=source_url, source_page=p.source_page))
                    stored += 1
                rep.lines.append(
                    f"{listed.org} {listed.title}: 후보 {len(picked)}건 / "
                    f"저장 {stored}건 / 거절 {rejected_here}건")
            except Exception as exc:
                rep.failures.append(
                    f"{name} {listed.title}: {type(exc).__name__}: {exc}")
                continue

    # 이번에 실제로 대체물을 만든 키만 existing 에서 뺀다 — 위 문서주석
    # 참고. replaced 는 fresh 를 다 만든 지금에야 정해진다.
    replaced = {r.key for r in fresh}
    kept = existing
    if refresh:
        kept = [r for r in existing if not (r.key in refresh and r.key in replaced)]
        for key in sorted(k for k in refresh if k not in replaced):
            if key in existing_keys:
                # 대상은 실재한다 — 이번 실행이 다시 만들지 못했을 뿐이다.
                # 잃은 것이 없고 다시 돌리면 되므로 오류로 세지 않는다.
                rep.lines.append(
                    f"refresh {_format_refresh_key(key)}: 이번 실행에서 대체물을 "
                    "못 만들어 기존 항목을 그대로 둔다")
            else:
                # existing 의 어떤 키와도 안 맞는다 — 기관 철자·발표일·지표
                # 표기 중 하나가 틀렸다는 뜻이라 오타로 본다. main() 이 이
                # 목록을 보고 종료 코드를 정한다.
                rep.unmatched_refresh.append(key)
                rep.lines.append(
                    f"refresh {_format_refresh_key(key)}: 일치하는 기존 항목이 "
                    "없다 — 기관·발표일·지표 표기를 확인한다")

    merged = rs.merge(kept, fresh)
    rep.saved = len(merged) - len(kept)
    rep.skipped = len(fresh) - rep.saved
    if merged != existing:
        rs.save(path, merged)
    return rep


def _format_refresh_key(key: tuple[str, date, str]) -> str:
    """(org, published_at, indicator) 를 --refresh 가 받는 그 표기로 되돌린다.

    보고서 메시지 전체의 목적이 "무엇을 잘못 적었는지 확인하라"는 것인데,
    파이썬 튜플을 그대로 찍으면(`('KDI', datetime.date(2026, 8, 19),
    'emp_change')`) 사람이 입력한 문자열과 안 닮아 대조하기 더 어렵다 —
    입력 형식 그대로("KDI:2026-08-19:emp_change") 돌려준다.
    """
    org, published_at, indicator = key
    return f"{org}:{published_at.isoformat()}:{indicator}"


def _parse_refresh(item: str) -> tuple[str, date, str]:
    """'<기관>:<발표일>:<지표>' 를 rs.Rationale.key 와 같은 모양으로 읽는다.

    형식만 본다 — <기관>이 실제 Rationale.org 표기와 맞는지, <지표>가 이
    기관이 다루는 지표인지는 여기서 대조하지 않는다. 그 대조는 run() 이
    existing 과 실제로 맞대 보고 하나도 안 맞으면 보고서에 남긴다(모듈
    문서주석 참고) — 여기서 미리 막으려 하면 무엇을 기준으로 "틀렸다"고
    판정할지 이 함수는 알 방법이 없다(existing 을 모른다). 발표일에 ':'
    가 없으므로 최대 두 번만 자른다("KDI:2026-08-19:emp_change").
    """
    parts = item.split(":", 2)
    if len(parts) != 3:
        raise ValueError(f"'<기관>:<발표일>:<지표>' 형식이 아니다: {item!r}")
    org, date_str, indicator = parts
    try:
        published_at = date.fromisoformat(date_str)
    except ValueError as exc:
        raise ValueError(f"발표일을 읽지 못했다({date_str!r}) — YYYY-MM-DD 로 적는다") from exc
    return (org, published_at, indicator)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(
        description="전망 근거를 LLM 으로 골라 rationales.json 에 병합한다.")
    parser.add_argument(
        "--only", action="append", default=None, metavar="소스키",
        help="이 소스만 수집한다(반복 가능, documents.SOURCES 의 키 — "
             "예: bok, kdi, oecd_interim)")
    parser.add_argument(
        "--refresh", action="append", default=[], metavar="기관:발표일:지표",
        help="이미 있는 근거를 다시 만들어 본다(반복 가능하고, 명시한 대상만 "
             "대상이 된다 — 이번 실행이 대체물을 못 만들면 기존 항목은 "
             "그대로 남는다). <기관>은 Rationale.org 표기(BOK·KDI·KEIS·"
             "KLI·KIET·OECD)로 적는다 — --only 의 소스키와는 다른 이름 "
             "공간이다. 예: --refresh KDI:2026-08-19:emp_change")
    args = parser.parse_args(argv)

    unknown = [name for name in (args.only or []) if name not in SOURCES]
    if unknown:
        print(f"모르는 소스키: {unknown} — 쓸 수 있는 것: {sorted(SOURCES)}")
        return 1

    try:
        refresh = {_parse_refresh(item) for item in args.refresh}
    except ValueError as exc:
        print(f"--refresh 를 읽지 못했다: {exc}")
        return 1

    rep = run(DATA_DIR, only=args.only, refresh=refresh)

    for line in rep.lines:
        print(line)
    print(f"\n요약: 저장 {rep.saved}건 / 건너뜀 {rep.skipped}건 / "
          f"거절 {len(rep.rejected)}건 / 실패 {len(rep.failures)}건")
    for line in rep.rejected:
        print(f"  거절 — {line}")
    for line in rep.failures:
        print(f"  실패 — {line}")
    # 거절만 있는 실행과, refresh 대상이 있는데 이번엔 대체물을 못 만든
    # 실행은 exit 0 을 유지한다 — 둘 다 아무것도 잃지 않았고(거절은 검증이
    # 설계대로 작동한 것이고, 재시도가 그 대상의 정상적인 다음 수순이다)
    # 실패를 여기서 세면 사람이 종료 코드를 무시하는 법을 배운다. 반면
    # unmatched_refresh(존재하지 않는 키를 --refresh 로 지정한 경우)는
    # 오타이므로 실패로 센다 — 그래야 ~180줄짜리 실행 로그 맨 아래
    # 한 줄에 묻히지 않고 exit code 로도 드러난다.
    return 1 if rep.failures or rep.unmatched_refresh else 0


if __name__ == "__main__":
    # 워크플로가 아니라 사람이 콘솔에서 돌린다 — 로컬 콘솔은 UTF-8 이
    # 아닐 수 있다(윈도우 cp949).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
