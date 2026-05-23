"""Repo cloning and git worktree management for the executor."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


def _sh(cmd: list[str], cwd: Path | None = None) -> str:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        # Surface stderr so the scheduler/log shows _why_ git failed.
        raise subprocess.CalledProcessError(
            r.returncode, cmd, output=r.stdout, stderr=r.stderr
        )
    return r.stdout.strip()


@dataclass
class Workspace:
    repo_root: Path  # main checkout, base branch
    worktree_path: Path  # per-group worktree
    branch: str


class WorkspaceManager:
    def __init__(self, workdir: str, github_repo: str, github_token: str, base_branch: str):
        # Resolve to absolute so subprocess calls don't fight relative paths
        # (git worktree add with a relative path resolves against repo_root,
        # putting the worktree somewhere unexpected; the SDK's later cwd then
        # can't find that location and CreateProcess fails on Windows).
        self.workdir = Path(workdir).expanduser().resolve()
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.github_repo = github_repo
        self.github_token = github_token
        self.base_branch = base_branch
        self.repo_root = self.workdir / "repo"

    def ensure_repo(self) -> None:
        if (self.repo_root / ".git").exists():
            _sh(["git", "fetch", "origin", self.base_branch], cwd=self.repo_root)
            _sh(["git", "checkout", self.base_branch], cwd=self.repo_root)
            _sh(["git", "reset", "--hard", f"origin/{self.base_branch}"], cwd=self.repo_root)
            return
        url = f"https://x-access-token:{self.github_token}@github.com/{self.github_repo}.git"
        _sh(["git", "clone", "--branch", self.base_branch, url, str(self.repo_root)])
        # Bot identity for commits.
        _sh(["git", "config", "user.email", "excalibur-bot@users.noreply.github.com"], cwd=self.repo_root)
        _sh(["git", "config", "user.name", "excalibur-bot"], cwd=self.repo_root)

    def create_worktree(self, group_name: str) -> Workspace:
        # Branch: excalibur/<group>-YYYY-MM-DD
        import datetime as dt
        date = dt.date.today().isoformat()
        branch = f"excalibur/{group_name}-{date}"
        wt_path = self.workdir / f"wt-{group_name}-{date}"

        if wt_path.exists():
            shutil.rmtree(wt_path)

        # Delete branch if it exists locally or remotely (idempotent re-runs).
        subprocess.run(
            ["git", "branch", "-D", branch],
            cwd=self.repo_root,
            check=False,
            capture_output=True,
        )

        _sh(
            ["git", "worktree", "add", "-b", branch, str(wt_path), f"origin/{self.base_branch}"],
            cwd=self.repo_root,
        )
        return Workspace(repo_root=self.repo_root, worktree_path=wt_path, branch=branch)

    def cleanup_worktree(self, ws: Workspace) -> None:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(ws.worktree_path)],
            cwd=self.repo_root,
            check=False,
            capture_output=True,
        )

    def push(self, ws: Workspace) -> None:
        _sh(["git", "push", "-u", "origin", ws.branch], cwd=ws.worktree_path)

    def has_commits(self, ws: Workspace) -> bool:
        try:
            out = _sh(
                ["git", "rev-list", "--count", f"origin/{self.base_branch}..HEAD"],
                cwd=ws.worktree_path,
            )
            return int(out) > 0
        except subprocess.CalledProcessError:
            return False
