"""Worktree tests use a real local git repo as the 'remote' so we exercise
the actual subprocess paths the worker takes on Railway."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from excalibur.worktree import WorkspaceManager


def _git(args, cwd: Path):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def remote(tmp_path) -> Path:
    """A bare repo with one initial commit on `dev`."""
    bare = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(["init", "-b", "dev"], cwd=seed)
    _git(["config", "user.email", "test@example.com"], cwd=seed)
    _git(["config", "user.name", "test"], cwd=seed)
    (seed / "README.md").write_text("seed\n")
    _git(["add", "README.md"], cwd=seed)
    _git(["commit", "-m", "init"], cwd=seed)
    _git(["clone", "--bare", str(seed), str(bare)], cwd=tmp_path)
    return bare


@pytest.fixture
def wm(tmp_path, remote, monkeypatch):
    """A WorkspaceManager pointing at the bare remote via file:// URL."""
    workdir = tmp_path / "work"
    mgr = WorkspaceManager(
        workdir=str(workdir),
        github_repo="local/repo",  # not used because we monkeypatch ensure_repo's URL
        github_token="t",
        base_branch="dev",
    )

    # Stub ensure_repo to clone from the local bare remote instead of github.com.
    real = mgr.ensure_repo

    def patched_ensure():
        if (mgr.repo_root / ".git").exists():
            return real()
        subprocess.run(
            ["git", "clone", "--branch", "dev", str(remote), str(mgr.repo_root)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "bot@example.com"],
            cwd=mgr.repo_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "bot"],
            cwd=mgr.repo_root,
            check=True,
            capture_output=True,
        )
        # ensure origin == bare remote (it should already, but be explicit)
        subprocess.run(
            ["git", "remote", "set-url", "origin", str(remote)],
            cwd=mgr.repo_root,
            check=True,
            capture_output=True,
        )

    monkeypatch.setattr(mgr, "ensure_repo", patched_ensure)
    return mgr


def test_ensure_repo_clones_then_idempotent(wm):
    wm.ensure_repo()
    assert (wm.repo_root / ".git").exists()
    # Second call must not re-clone.
    wm.ensure_repo()
    assert (wm.repo_root / "README.md").exists()


def test_create_worktree_creates_branch(wm):
    wm.ensure_repo()
    ws = wm.create_worktree("feature-x")
    assert ws.worktree_path.exists()
    assert ws.branch.startswith("excalibur/feature-x-")
    head = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=ws.worktree_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert head == ws.branch
    wm.cleanup_worktree(ws)


def test_has_commits_false_on_empty_branch(wm):
    wm.ensure_repo()
    ws = wm.create_worktree("nothing")
    assert wm.has_commits(ws) is False
    wm.cleanup_worktree(ws)


def test_has_commits_true_after_commit(wm):
    wm.ensure_repo()
    ws = wm.create_worktree("something")
    (ws.worktree_path / "new.txt").write_text("hi\n")
    subprocess.run(["git", "add", "new.txt"], cwd=ws.worktree_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "test"],
        cwd=ws.worktree_path,
        check=True,
        capture_output=True,
    )
    assert wm.has_commits(ws) is True
    wm.cleanup_worktree(ws)


def test_push_then_reuse_branch(wm):
    """Second create_worktree for the same group should not crash even after a push."""
    wm.ensure_repo()
    ws1 = wm.create_worktree("payment-retry")
    (ws1.worktree_path / "x.txt").write_text("a\n")
    subprocess.run(["git", "add", "x.txt"], cwd=ws1.worktree_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "x"], cwd=ws1.worktree_path, check=True, capture_output=True)
    wm.push(ws1)
    wm.cleanup_worktree(ws1)
    # Same day, same group — must be idempotent.
    ws2 = wm.create_worktree("payment-retry")
    assert ws2.branch == ws1.branch
    wm.cleanup_worktree(ws2)


def test_sh_failure_surfaces_stderr(tmp_path):
    """A bad git command must raise with the real stderr in the exception."""
    from excalibur.worktree import _sh

    not_a_repo = tmp_path / "empty"
    not_a_repo.mkdir()
    with pytest.raises(subprocess.CalledProcessError) as ex:
        _sh(["git", "rev-parse", "HEAD"], cwd=not_a_repo)
    assert ex.value.stderr  # non-empty stderr captured
