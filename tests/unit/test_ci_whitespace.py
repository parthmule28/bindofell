"""Run the workflow's real whitespace command against controlled Git histories."""

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def repository(path):
    git(path, "init", "--initial-branch=main")
    git(path, "config", "user.name", "Synthetic CI test")
    git(path, "config", "user.email", "ci@example.invalid")
    git(path, "config", "commit.gpgsign", "false")
    return commit(path, "file.txt", "clean base\n")


def commit(repo, name, content):
    (repo / name).write_text(content)
    git(repo, "add", name)
    git(repo, "commit", "-m", "synthetic fixture commit")
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def check_workflow(repo, base, head):
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    block = workflow.split("- name: Whitespace validation", 1)[1]
    command = next(
        line.removeprefix("        run: ")
        for line in block.splitlines()
        if line.startswith("        run: ")
    )
    script = ROOT / ".github/scripts/check-whitespace.sh"
    if script.is_file():
        target = repo / ".github/scripts/check-whitespace.sh"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(script, target)
    return subprocess.run(
        ["bash", "-c", command],
        cwd=repo,
        capture_output=True,
        text=True,
        env={**os.environ, "BASE_SHA": base, "HEAD_SHA": head},
    )


def test_workflow_rejects_committed_pr_whitespace_with_a_clean_worktree(tmp_path):
    base = repository(tmp_path)
    head = commit(tmp_path, "added.txt", "committed trailing spaces  \n")
    assert git(tmp_path, "diff", "--check").returncode == 0
    result = check_workflow(tmp_path, base, head)
    assert result.returncode != 0
    assert "added.txt:1:" in result.stdout


def test_workflow_checks_commits_instead_of_uncommitted_whitespace(tmp_path):
    base = repository(tmp_path)
    head = commit(tmp_path, "added.txt", "clean committed change\n")
    (tmp_path / "file.txt").write_text("uncommitted trailing spaces  \n")
    result = check_workflow(tmp_path, base, head)
    assert result.returncode == 0, result.stdout + result.stderr


def test_workflow_checks_only_pr_changes_since_the_merge_base(tmp_path):
    repository(tmp_path)
    git(tmp_path, "switch", "-c", "feature")
    head = commit(tmp_path, "added.txt", "clean feature\n")
    git(tmp_path, "switch", "main")
    main = commit(tmp_path, "file.txt", "base branch has whitespace  \n")
    result = check_workflow(tmp_path, main, head)
    assert result.returncode == 0, result.stdout + result.stderr


def test_workflow_fails_closed_when_a_commit_is_unavailable(tmp_path):
    base = repository(tmp_path)
    result = check_workflow(tmp_path, base, "f" * 40)
    assert result.returncode != 0


def test_initial_push_checks_committed_content_against_an_empty_tree(tmp_path):
    repository(tmp_path)
    head = commit(tmp_path, "added.txt", "bad initial push  \n")
    result = check_workflow(tmp_path, "0" * 40, head)
    assert result.returncode != 0
    assert "added.txt:1:" in result.stdout
