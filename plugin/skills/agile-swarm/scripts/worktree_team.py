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
            st = _run_git(wt_path, ["status", "--porcelain", "-uall"], check=False)
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


def rescue_worktrees(
    repo_arg: str,
    *,
    slices: list[str] | None = None,
    prefix: str = "agile/",
    commit: bool = True,
    commit_msg_prefix: str = "chore(rescue): adopt subagent footprint for",
) -> list[dict[str, Any]]:
    """Inspect and rescue uncommitted files left behind by interrupted/dropped subagents."""
    repo = _validate_repo(repo_arg)
    main_norm = os.path.normcase(str(repo))
    slice_filter = set(slices) if slices else None
    results: list[dict[str, Any]] = []

    for item in parse_worktree_porcelain(repo):
        wt_path = Path(item["path"])
        branch = item.get("branch", "")
        if os.path.normcase(str(wt_path)) == main_norm:
            continue
        if not branch.startswith(prefix):
            continue
        slice_slug = branch.removeprefix(prefix)
        if slice_filter and slice_slug not in slice_filter:
            continue

        st = _run_git(wt_path, ["status", "--porcelain", "-uall"], check=False)
        dirty_lines = [l for l in st.stdout.splitlines() if l.strip()]
        dirty_files = [l[3:].strip() for l in dirty_lines]

        if dirty_files:
            if commit:
                _run_git(wt_path, ["add", "-A"])
                msg = f"{commit_msg_prefix} {slice_slug}"
                _run_git(wt_path, ["commit", "-m", msg])
                head_rev = _run_git(wt_path, ["rev-parse", "--short", "HEAD"]).stdout.strip()
                results.append({
                    "slice": slice_slug,
                    "branch": branch,
                    "path": str(wt_path),
                    "status": "rescued_and_committed",
                    "rescued_files": dirty_files,
                    "commit": head_rev,
                })
            else:
                results.append({
                    "slice": slice_slug,
                    "branch": branch,
                    "path": str(wt_path),
                    "status": "dirty_footprint_detected",
                    "rescued_files": dirty_files,
                })
        else:
            log_proc = _run_git(wt_path, ["log", "-1", "--format=%h %s"], check=False)
            last_commit = log_proc.stdout.strip() if log_proc.returncode == 0 else ""
            results.append({
                "slice": slice_slug,
                "branch": branch,
                "path": str(wt_path),
                "status": "clean",
                "rescued_files": [],
                "last_commit": last_commit,
            })
    return results


def diff_worktrees(
    repo_arg: str,
    *,
    prefix: str = "agile/",
    stat_only: bool = False,
    base: str = "HEAD",
) -> list[dict[str, Any]]:
    """Inspect active diffs across all agile slice worktrees against a base ref."""
    repo = _validate_repo(repo_arg)
    main_norm = os.path.normcase(str(repo))
    results: list[dict[str, Any]] = []

    for item in parse_worktree_porcelain(repo):
        wt_path = Path(item["path"])
        branch = item.get("branch", "")
        if os.path.normcase(str(wt_path)) == main_norm:
            continue
        if not branch.startswith(prefix):
            continue
        slice_slug = branch.removeprefix(prefix)

        diff_args = ["diff", "--stat" if stat_only else "--patch", f"{base}...{branch}"]
        diff_proc = _run_git(repo, diff_args, check=False)
        st_proc = _run_git(wt_path, ["status", "--short"], check=False)

        results.append({
            "slice": slice_slug,
            "branch": branch,
            "path": str(wt_path),
            "uncommitted": st_proc.stdout.strip(),
            "diff": diff_proc.stdout.strip(),
        })
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

    p_rescue = sub.add_parser("rescue", help="Rescue and adopt uncommitted files from dropped subagents")
    p_rescue.add_argument("repo", help="Path inside the target git repository")
    p_rescue.add_argument("slices", nargs="*", help="Optional slice names to rescue (default: all)")
    p_rescue.add_argument("--prefix", default="agile/", help="Git branch prefix (default: agile/)")
    p_rescue.add_argument("--no-commit", dest="commit", action="store_false", help="Detect dirty files without committing")
    p_rescue.add_argument("--message-prefix", default="chore(rescue): adopt subagent footprint for", help="Commit message prefix")
    p_rescue.add_argument("--json", action="store_true", help="Emit JSON output")

    p_diff = sub.add_parser("diff", help="Show active diffs across all agile slice worktrees")
    p_diff.add_argument("repo", help="Path inside the target git repository")
    p_diff.add_argument("--prefix", default="agile/", help="Git branch prefix (default: agile/)")
    p_diff.add_argument("--base", default="HEAD", help="Base ref for diff comparison (default: HEAD)")
    p_diff.add_argument("--stat", dest="stat_only", action="store_true", help="Show diff --stat summary only")
    p_diff.add_argument("--json", action="store_true", help="Emit JSON output")

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

        if args.cmd == "rescue":
            out = rescue_worktrees(
                args.repo,
                slices=args.slices or None,
                prefix=args.prefix,
                commit=args.commit,
                commit_msg_prefix=args.message_prefix,
            )
            if args.json:
                print(json.dumps(out, indent=2, ensure_ascii=False))
            else:
                if not out:
                    print("No agile worktrees found to rescue.")
                for row in out:
                    files_str = f" ({len(row.get('rescued_files', []))} files)" if row.get("rescued_files") else ""
                    commit_str = f" [{row.get('commit')}]" if row.get("commit") else ""
                    print(f"[{row['status']}] {row['branch']}{commit_str}{files_str} | {row['path']}")
            return 0

        if args.cmd == "diff":
            out = diff_worktrees(
                args.repo,
                prefix=args.prefix,
                stat_only=args.stat_only,
                base=args.base,
            )
            if args.json:
                print(json.dumps(out, indent=2, ensure_ascii=False))
            else:
                if not out:
                    print("No agile worktrees found.")
                for row in out:
                    print(f"=== {row['branch']} ({row['slice']}) ===")
                    if row.get("uncommitted"):
                        print(f"Uncommitted in worktree:\n{row['uncommitted']}")
                    print(row.get("diff") or "(no committed diff vs base)")
                    print()
            return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

