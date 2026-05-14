import json
import os
import subprocess
import sys
from pathlib import Path


def run_cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    clean_env = os.environ.copy()
    clean_env.pop("QUACKIT_DATABASE_URL", None)
    clean_env.pop("AGENT_MEMORY_DATABASE_URL", None)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "quackit.cli",
            "--database-path",
            str(tmp_path / "cli.duckdb"),
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=clean_env,
    )


def test_cli_start_session_returns_json(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "start-session")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "open"
    assert payload["id"]


def test_cli_save_memory_with_metadata(tmp_path: Path) -> None:
    started = run_cli(tmp_path, "start-session")
    assert started.returncode == 0, started.stderr
    session_id = json.loads(started.stdout)["id"]

    saved = run_cli(
        tmp_path,
        "save-memory",
        "--session-id", session_id,
        "--type", "note",
        "--content", "skill content",
        "--content-type", "skill",
        "--title", "My Skill",
        "--metadata", '{"language":"python","framework":"pytest"}',
    )
    assert saved.returncode == 0, saved.stderr
    payload = json.loads(saved.stdout)
    assert payload["metadata"] == {"language": "python", "framework": "pytest"}


def test_cli_update_memory_metadata(tmp_path: Path) -> None:
    started = run_cli(tmp_path, "start-session")
    assert started.returncode == 0, started.stderr
    session_id = json.loads(started.stdout)["id"]

    saved = run_cli(tmp_path, "save-memory", "--session-id", session_id, "--type", "note", "--content", "original")
    assert saved.returncode == 0, saved.stderr
    mem_id = json.loads(saved.stdout)["mem_id"]

    updated = run_cli(tmp_path, "update-memory", mem_id, "--session-id", session_id, "--metadata", '{"language":"go"}')
    assert updated.returncode == 0, updated.stderr
    payload = json.loads(updated.stdout)
    assert payload["metadata"] == {"language": "go"}


def test_cli_save_and_search_memory_with_explicit_session_id(tmp_path: Path) -> None:
    started = run_cli(tmp_path, "start-session")

    assert started.returncode == 0, started.stderr
    session_id = json.loads(started.stdout)["id"]

    saved = run_cli(
        tmp_path,
        "save-memory",
        "--session-id",
        session_id,
        "--type",
        "note",
        "--content",
        "cli memory",
        "--tag",
        "cli",
    )
    searched = run_cli(tmp_path, "search-memory", "cli", "--session-id", session_id)

    assert saved.returncode == 0, saved.stderr
    assert searched.returncode == 0, searched.stderr
    search_payload = json.loads(searched.stdout)
    assert search_payload[0]["tags"] == ["cli"]


def test_cli_update_memory_updates_content(tmp_path: Path) -> None:
    started = run_cli(tmp_path, "start-session")
    assert started.returncode == 0, started.stderr
    session_id = json.loads(started.stdout)["id"]

    saved = run_cli(
        tmp_path,
        "save-memory",
        "--session-id", session_id,
        "--type", "note",
        "--content", "original content",
        "--tag", "a",
        "--title", "orig title",
        "--content-type", "note",
    )
    assert saved.returncode == 0, saved.stderr
    mem_id = json.loads(saved.stdout)["mem_id"]

    updated = run_cli(
        tmp_path,
        "update-memory",
        mem_id,
        "--session-id", session_id,
        "--content", "updated content",
        "--title", "new title",
        "--content-type", "code",
        "--tag", "b",
        "--tag", "c",
    )
    assert updated.returncode == 0, updated.stderr
    payload = json.loads(updated.stdout)
    assert payload["content"] == "updated content"
    assert payload["title"] == "new title"
    assert payload["content_type"] == "code"
    assert payload["tags"] == ["b", "c"]
    assert payload["mem_id"] == mem_id


def test_cli_update_memory_partial(tmp_path: Path) -> None:
    started = run_cli(tmp_path, "start-session")
    assert started.returncode == 0, started.stderr
    session_id = json.loads(started.stdout)["id"]

    saved = run_cli(tmp_path, "save-memory", "--session-id", session_id, "--type", "note", "--content", "original", "--tag", "keep")
    assert saved.returncode == 0, saved.stderr
    mem_id = json.loads(saved.stdout)["mem_id"]

    updated = run_cli(tmp_path, "update-memory", mem_id, "--session-id", session_id, "--content", "only content changed")
    assert updated.returncode == 0, updated.stderr
    payload = json.loads(updated.stdout)
    assert payload["content"] == "only content changed"
    assert payload["tags"] == ["keep"]


def test_cli_search_memory_filters_by_content_type(tmp_path: Path) -> None:
    started = run_cli(tmp_path, "start-session")
    assert started.returncode == 0, started.stderr
    session_id = json.loads(started.stdout)["id"]

    run_cli(
        tmp_path,
        "save-memory",
        "--session-id", session_id,
        "--type", "note",
        "--content", "def foo(): pass",
        "--tag", "python",
        "--title", "func",
        "--content-type", "code",
    )
    run_cli(
        tmp_path,
        "save-memory",
        "--session-id", session_id,
        "--type", "note",
        "--content", "# Heading",
        "--tag", "docs",
        "--title", "readme",
        "--content-type", "markdown",
    )
    run_cli(
        tmp_path,
        "save-memory",
        "--session-id", session_id,
        "--type", "note",
        "--content", "plain note",
        "--tag", "misc",
    )

    code_results = run_cli(tmp_path, "search-memory", "", "--session-id", session_id, "--content-type", "code")
    assert code_results.returncode == 0, code_results.stderr
    code_payload = json.loads(code_results.stdout)
    assert len(code_payload) == 1
    assert code_payload[0]["content_type"] == "code"

    md_results = run_cli(tmp_path, "search-memory", "", "--session-id", session_id, "--content-type", "markdown")
    assert md_results.returncode == 0, md_results.stderr
    md_payload = json.loads(md_results.stdout)
    assert len(md_payload) == 1
    assert md_payload[0]["content_type"] == "markdown"

    skill_results = run_cli(tmp_path, "search-memory", "", "--session-id", session_id, "--content-type", "skill")
    assert skill_results.returncode == 0, skill_results.stderr
    assert json.loads(skill_results.stdout) == []


def test_cli_create_project_and_list(tmp_path: Path) -> None:
    created = run_cli(tmp_path, "create-project", "my-project", "--description", "test")
    assert created.returncode == 0, created.stderr
    payload = json.loads(created.stdout)
    assert payload["name"] == "my-project"
    assert payload["description"] == "test"

    listed = run_cli(tmp_path, "list-projects")
    assert listed.returncode == 0, listed.stderr
    projects = json.loads(listed.stdout)
    assert len(projects) == 1


def test_cli_consolidate_projects(tmp_path: Path) -> None:
    target = run_cli(tmp_path, "create-project", "target")
    source = run_cli(tmp_path, "create-project", "source")
    target_id = json.loads(target.stdout)["id"]
    source_id = json.loads(source.stdout)["id"]

    started = run_cli(tmp_path, "start-session", "--project-id", source_id)
    session_id = json.loads(started.stdout)["id"]
    run_cli(
        tmp_path,
        "save-memory",
        "--session-id", session_id,
        "--type", "note",
        "--content", "cli consolidate test",
    )

    result = run_cli(
        tmp_path,
        "consolidate-projects",
        "--source-ids", source_id,
        "--target-id", target_id,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["id"] == target_id

    projects = run_cli(tmp_path, "list-projects")
    assert json.loads(projects.stdout) == [payload]


def test_cli_start_session_with_project(tmp_path: Path) -> None:
    created = run_cli(tmp_path, "create-project", "proj")
    project_id = json.loads(created.stdout)["id"]

    started = run_cli(tmp_path, "start-session", "--project-id", project_id)
    assert started.returncode == 0, started.stderr
    payload = json.loads(started.stdout)
    assert payload["project_id"] == project_id
