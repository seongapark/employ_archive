import json
from pathlib import Path

from tools.build import build_site, discover_domains


def make_repo(tmp_path: Path, with_hub: bool = True) -> Path:
    repo = tmp_path / "repo"
    if with_hub:
        (repo / "hub").mkdir(parents=True)
        (repo / "hub" / "index.html").write_text("hub", encoding="utf-8")
    (repo / "core").mkdir(parents=True)
    (repo / "core" / "tokens.css").write_text(":root{}", encoding="utf-8")
    for name in ("forecast", "employment"):
        app = repo / "domains" / name / "app"
        app.mkdir(parents=True)
        (app / "index.html").write_text(name, encoding="utf-8")
        data = repo / "domains" / name / "data"
        data.mkdir()
        (data / "last_run.json").write_text(json.dumps({"errors": []}), encoding="utf-8")
    # app 디렉터리가 없는 폴더는 도메인이 아니다 (문서·작업용 폴더 등)
    (repo / "domains" / "notes").mkdir()
    return repo


def test_discover_domains_requires_app_dir(tmp_path):
    repo = make_repo(tmp_path)
    assert discover_domains(repo) == ["employment", "forecast"]


def test_build_site_places_hub_core_and_domains(tmp_path):
    repo = make_repo(tmp_path)
    out = build_site(repo, tmp_path / "_site")

    assert (out / "index.html").read_text(encoding="utf-8") == "hub"
    assert (out / "core" / "tokens.css").exists()
    assert (out / "forecast" / "index.html").read_text(encoding="utf-8") == "forecast"
    assert (out / "forecast" / "data" / "last_run.json").exists()
    assert (out / "employment" / "index.html").exists()


def test_build_site_copies_core_into_each_domain(tmp_path):
    # 서비스워커 스코프가 도메인 폴더로 제한되므로 core가 도메인 안에도 있어야
    # 오프라인에서 스타일이 유지된다.
    repo = make_repo(tmp_path)
    out = build_site(repo, tmp_path / "_site")

    assert (out / "forecast" / "core" / "tokens.css").exists()
    assert (out / "employment" / "core" / "tokens.css").exists()


def test_build_site_clears_previous_output(tmp_path):
    repo = make_repo(tmp_path)
    out_dir = tmp_path / "_site"
    out_dir.mkdir()
    (out_dir / "stale.html").write_text("old", encoding="utf-8")

    build_site(repo, out_dir)

    assert not (out_dir / "stale.html").exists()


def test_build_site_without_hub_still_builds_domains(tmp_path):
    # hub/ 가 아직 없는 저장소(예: Task 3 시점)에서도 도메인만으로 조립이
    # 성공해야 한다.
    repo = make_repo(tmp_path, with_hub=False)
    out = build_site(repo, tmp_path / "_site")

    assert not (out / "index.html").exists()
    assert (out / "core" / "tokens.css").exists()
    assert (out / "forecast" / "index.html").read_text(encoding="utf-8") == "forecast"
    assert (out / "forecast" / "core" / "tokens.css").exists()
    assert (out / "employment" / "index.html").exists()
