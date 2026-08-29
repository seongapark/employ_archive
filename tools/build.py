"""사이트 조립. GitHub Pages 배포와 로컬 서버가 이 함수 하나를 공유한다.

core/ 는 사이트 루트와 각 도메인 폴더 양쪽에 복사한다. 도메인 앱의 서비스워커
스코프가 자기 폴더로 제한되기 때문에, 루트에만 두면 오프라인에서 스타일시트가
빠진다. 원본은 core/ 하나뿐이고 복사는 빌드 산출물에서만 일어난다.

hub/ 는 있으면 복사하고 없으면 건너뛴다: 도메인만 있는 저장소도 조립 가능해야
하고, hub/ 가 아직 만들어지기 전 단계(Task 3)에서도 앱을 확인할 수 있어야
한다. core/ 는 사이트의 최소 요건이므로 없으면 예외를 낸다(조용히 넘어가면
깨진 산출물이 만들어진다).
"""
from __future__ import annotations

import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def discover_domains(repo: Path) -> list[str]:
    root = repo / "domains"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "app").is_dir())


def build_site(repo: Path, out: Path) -> Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    core = repo / "core"
    hub = repo / "hub"
    if hub.is_dir():
        shutil.copytree(hub, out, dirs_exist_ok=True)
    shutil.copytree(core, out / "core")

    for name in discover_domains(repo):
        dest = out / name
        shutil.copytree(repo / "domains" / name / "app", dest)
        shutil.copytree(core, dest / "core")
        data = repo / "domains" / name / "data"
        if data.is_dir():
            shutil.copytree(data, dest / "data")

    return out


def main() -> int:
    out = build_site(REPO, REPO / "_site")
    print(f"built: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
