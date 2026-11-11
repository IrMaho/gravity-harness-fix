#!/usr/bin/env python3
"""Manage clean sibling git worktrees for Agile parallel execution or CI offloading."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _run_git(repo: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc


def _validate_repo(repo_arg: str) -> Path:
    repo = Path(repo_arg).resolve()
    top = _run_git(repo, ["rev-parse", "--show-toplevel"]).stdout.strip()
    return Path(top).resolve()


def _sanitize_slug(raw: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw.strip()).strip("-.")
    if not slug:
        raise ValueError(f"Invalid slice name: {raw!r}")
    return slug


def parse_worktree_porcelain(repo: Path) -> list[dict[str, Any]]:
    proc = _run_git(repo, ["worktree", "list", "--porcelain"])
    entries: list[dict[str, Any]] = []
    cur: dict[str, Any] = {}
    for line in proc.stdout.splitlines():
        if not line.strip():
            if cur:
                entries.append(cur)
                cur = {}
            continue
        if line.startswith("worktree "):
            cur["path"] = str(Path(line[9:].strip()).resolve())
        elif line.startswith("HEAD "):
            cur["head"] = line[5:].strip()
        elif line.startswith("branch "):
            ref = line[7:].strip()
            cur["branch_ref"] = ref
            cur["branch"] = ref.removeprefix("refs/heads/")
        elif line == "detached":
            cur["detached"] = True
        elif line == "bare":
            cur["bare"] = True
    if cur:
        entries.append(cur)

    for item in entries:
        wt_path = Path(item["path"])
        if wt_path.exists():
            st = _run_git(wt_path, ["status", "--porcelain"], check=False)
            item["dirty"] = bool(st.stdout.strip()) if st.returncode == 0 else False
        else:
            item["missing"] = True
            item["dirty"] = False
    return entries


def create_worktrees(
    repo_arg: str,
    slices: list[str],
    *,
    prefix: str = "agile/",
    base: str = "HEAD",
) -> list[dict[str, str]]:
    repo = _validate_repo(repo_arg)
    existing = {os.path.normcase(e["path"]): e for e in parse_worktree_porcelain(repo)}
    existing_branches = {e.get("branch"): e["path"] for e in existing.values() if e.get("branch")}

    created: list[dict[str, str]] = []
    for raw_slice in slices:
        slug = _sanitize_slug(raw_slice)
        branch = f"{prefix}{slug}"
        wt_path = repo.parent / f"{repo.name}-wt-{slug}"
        norm_wt = os.path.normcase(str(wt_path.resolve()))

        if norm_wt in existing:
            created.append({"slice": slug, "branch": branch, "path": str(wt_path), "status": "already_exists"})
            continue

        if branch in existing_branches:
            raise RuntimeError(f"Branch {branch} is already checked out at {existing_branches[branch]}")

        branch_exists = _run_git(repo, ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], check=False).returncode == 0
        if branch_exists:
            _run_git(repo, ["worktree", "add", str(wt_path), branch])
            status = "attached_existing_branch"
        else:
            _run_git(repo, ["worktree", "add", "-b", branch, str(wt_path), base])
            status = "created"

        created.append({"slice": slug, "branch": branch, "path": str(wt_path), "status": status})
    return created


def cleanup_worktrees(
    repo_arg: str,
    *,
    prefix: str = "agile/",
    force: bool = False,
    delete_branches: bool = False,
) -> list[dict[str, str]]:
    repo = _validate_repo(repo_arg)
    main_norm = os.path.normcase(str(repo))
    results: list[dict[str, str]] = []

    for item in parse_worktree_porcelain(repo):
        wt_path = Path(item["path"])
        branch = item.get("branch", "")
        if os.path.normcase(str(wt_path)) == main_norm:
            continue
        if not branch.startswith(prefix):
            continue
        if item.get("dirty") and not force:
            results.append({"path": str(wt_path), "branch": branch, "status": "skipped_dirty"})
            continue

        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(wt_path))
        _run_git(repo, args)
        status = "removed"

        if delete_branches and branch:
            del_flag = "-D" if force else "-d"
            del_proc = _run_git(repo, ["branch", del_flag, branch], check=False)
            status = f"{status}+branch_deleted" if del_proc.returncode == 0 else f"{status}+branch_kept"
        results.append({"path": str(wt_path), "branch": branch, "status": status})

    _run_git(repo, ["worktree", "prune"], check=False)
    return results


def main() -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(description="Create, list, or clean up sibling git worktrees for parallel tasks.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", help="Create sibling worktrees for parallel slices")
    p_create.add_argument("repo", help="Path inside the target git repository")
    p_create.add_argument("slices", nargs="+", help="Slice names (e.g. slice-ui slice-api wt-ci)")
    p_create.add_argument("--prefix", default="agile/", help="Git branch prefix (default: agile/)")
    p_create.add_argument("--base", default="HEAD", help="Base ref for new slice branches (default: HEAD)")
    p_create.add_argument("--json", action="store_true", help="Emit JSON output")

    p_list = sub.add_parser("list", help="List active worktrees and clean/dirty state")
    p_list.add_argument("repo", help="Path inside the target git repository")
    p_list.add_argument("--json", action="store_true", help="Emit JSON output")

    p_clean = sub.add_parser("cleanup", help="Remove finished slice worktrees safely")
    p_clean.add_argument("repo", help="Path inside the target git repository")
    p_clean.add_argument("--prefix", default="agile/", help="Only clean worktrees with branches matching prefix")
    p_clean.add_argument("--force", action="store_true", help="Remove even if worktree has uncommitted changes")
    p_clean.add_argument("--delete-branches", action="store_true", help="Also delete slice branches after removal")
    p_clean.add_argument("--json", action="store_true", help="Emit JSON output")

    args = parser.parse_args()
    try:
        if args.cmd == "create":
            out = create_worktrees(args.repo, args.slices, prefix=args.prefix, base=args.base)
            if args.json:
                print(json.dumps(out, indent=2, ensure_ascii=False))
            else:
                for row in out:
                    print(f"[{row['status']}] {row['branch']} -> {row['path']}")
            return 0

        if args.cmd == "list":
            repo = _validate_repo(args.repo)
            out = parse_worktree_porcelain(repo)
            if args.json:
                print(json.dumps(out, indent=2, ensure_ascii=False))
            else:
                for row in out:
                    flag = "DIRTY" if row.get("dirty") else "clean"
                    print(f"- {row.get('branch', '(detached)')} | {flag} | {row['path']}")
            return 0

        if args.cmd == "cleanup":
            out = cleanup_worktrees(
                args.repo,
                prefix=args.prefix,
                force=args.force,
                delete_branches=args.delete_branches,
            )
            if args.json:
                print(json.dumps(out, indent=2, ensure_ascii=False))
            else:
                if not out:
                    print("No matching agile worktrees to clean.")
                for row in out:
                    print(f"[{row['status']}] {row['branch']} | {row['path']}")
            return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

