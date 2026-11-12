#!/usr/bin/env python3
"""Antigravity lifecycle hook handler for gravity-harness-fix.

Enforces low-overhead PreToolUse guardrails (blocking polling loops, broken
multiline quoting, POSIX-on-Windows failures, unguarded live exports, and blind
duplicate reads/edits), continues premature background-wait stops, injects
environment facts on SessionStart, and logs anomalies to JSONL + Markdown.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PLUGIN_ROOT / "harness_config.json"

_BIG_READ_SOURCE_SUFFIXES = frozenset({
    ".py", ".dart", ".ts", ".tsx", ".js", ".jsx",
    ".go", ".rs", ".java", ".kt", ".cpp", ".c", ".h",
})


def _load_memory_engine():
    """Fail-open lazy import of memory_engine from skills/memory-sync/scripts."""
    scripts_dir = str(PLUGIN_ROOT / "skills" / "memory-sync" / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        import memory_engine  # type: ignore[import-not-found]
        return memory_engine
    except ImportError:
        return None
    except Exception:
        return None


def _resolve_memory_workspace(payload: dict[str, Any], raw_fpath: str = "", *, require_db: bool = False) -> Path | None:
    """Resolve workspace containing .agents/memory (and memory.db if require_db)."""
    ws_first = str((payload.get("workspacePaths") or [""])[0] or "").strip()
    if ws_first:
        cand = Path(ws_first)
        marker = cand / ".agents" / "memory" / "memory.db" if require_db else cand / ".agents" / "memory"
        try:
            if marker.exists():
                return cand
        except OSError:
            pass
    if raw_fpath:
        try:
            cur = Path(raw_fpath).resolve()
            for parent in (cur, *cur.parents):
                marker = parent / ".agents" / "memory" / "memory.db" if require_db else parent / ".agents" / "memory"
                if marker.exists():
                    return parent
        except OSError:
            pass
    return None


def _force_utf8_stdio() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _resolve_logs_dir() -> Path:
    """Resolve active telemetry log directory with safe fallback."""
    candidates: list[Path] = []
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if cfg.get("logsDir"):
                candidates.append(Path(cfg["logsDir"]))
            if cfg.get("fallbackLogsDir"):
                candidates.append(Path(cfg["fallbackLogsDir"]))
        except Exception:
            pass
    candidates.append(PLUGIN_ROOT.parent.parent / "gravity-harness-logs")
    candidates.append(Path.home() / ".gemini" / "gravity-harness-logs")

    for cand in candidates:
        try:
            cand.mkdir(parents=True, exist_ok=True)
            return cand
        except OSError:
            continue
    return Path.cwd()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_state(logs_dir: Path, conv_id: str) -> dict[str, Any]:
    state_file = logs_dir / ".state" / f"{conv_id}.json"
    if state_file.exists():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "conv_id": conv_id,
        "polls": {},
        "recent_reads": [],
        "read_counts": {},
        "edit_error_files": {},
        "subagent_timestamps": [],
        "inherit_write_timestamps": [],
        "last_pytest_failed": False,
        "gate_running_ts": 0.0,
        "last_bloat_step_logged": 0,
        "issue_counts": {},
    }


def _save_state(logs_dir: Path, conv_id: str, state: dict[str, Any]) -> None:
    state_dir = logs_dir / ".state"
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        target = state_dir / f"{conv_id}.json"
        tmp = state_dir / f"{conv_id}.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tmp.replace(target)
    except OSError:
        pass


def _append_issue(
    logs_dir: Path,
    payload: dict[str, Any],
    *,
    severity: str,
    category: str,
    signature: str,
    detail: str,
    hint: str,
    state: dict[str, Any] | None = None,
) -> None:
    record = {
        "ts_utc": _utc_now_iso(),
        "conv_id": payload.get("conversationId", "unknown"),
        "workspace": (payload.get("workspacePaths") or [""])[0],
        "step_idx": payload.get("stepIdx"),
        "model": payload.get("modelName", ""),
        "severity": severity,
        "category": category,
        "signature": signature,
        "detail": detail[:400],
        "hint": hint[:300],
    }
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / "session-issues.jsonl"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        return

    if state is not None:
        counts = state.setdefault("issue_counts", {})
        counts[category] = int(counts.get(category, 0)) + 1

    # Refresh compact readable Markdown dashboard with last 25 issues
    _refresh_markdown_summary(logs_dir)


def _refresh_markdown_summary(logs_dir: Path) -> None:
    log_path = logs_dir / "session-issues.jsonl"
    summary_path = logs_dir / "latest-summary.md"
    if not log_path.exists():
        return
    try:
        # Read tail lines safely (max ~256KB)
        raw = log_path.read_bytes()
        if len(raw) > 262144:
            raw = raw[-262144:]
            lines = raw.decode("utf-8", errors="replace").splitlines()[1:]
        else:
            lines = raw.decode("utf-8", errors="replace").splitlines()

        records: list[dict[str, Any]] = []
        cats: Counter[str] = Counter()
        for ln in lines:
            if not ln.strip():
                continue
            try:
                rec = json.loads(ln)
                records.append(rec)
                cats[rec.get("category", "unknown")] += 1
            except json.JSONDecodeError:
                continue

        md: list[str] = [
            "# Gravity Harness Fix — Live Issue Telemetry",
            "",
            f"- **Updated (UTC):** `{_utc_now_iso()}`",
            f"- **Recent logged events:** `{len(records)}`",
            "",
            "## Category Counts",
            "",
            "| Category | Count |",
            "|---|---:|",
        ]
        for cat, cnt in cats.most_common():
            md.append(f"| `{cat}` | {cnt} |")
        md.extend(["", "## Latest 20 Events", "", "| Time (UTC) | Conv | Severity | Category | Detail |", "|---|---|---|---|---|"])
        for rec in reversed(records[-20:]):
            det = str(rec.get("detail", "")).replace("|", "/").replace("\n", " ")[:120]
            md.append(
                f"| `{rec.get('ts_utc','')}` | `{str(rec.get('conv_id',''))[:8]}` | `{rec.get('severity','')}` | `{rec.get('category','')}` | {det} |"
            )
        summary_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    except OSError:
        pass


def _extract_args(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    tc = payload.get("toolCall") or {}
    name = str(tc.get("name") or "")
    args = tc.get("args") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = {}
    return name, (args if isinstance(args, dict) else {})


def _normalize_path(raw: Any) -> str:
    s = str(raw or "").strip().strip('"').strip("'")
    if not s:
        return ""
    return os.path.normcase(os.path.normpath(s))


def _is_multiline_inline_script(cmd: str) -> bool:
    if "\n" not in cmd and "\r" not in cmd:
        return False
    low = cmd.lower()
    if re.search(r"(^|[;&|\s])(python3?|py)\s+(-[a-z]+\s+)*-c\s", low):
        return cmd.count("\n") >= 2 or len(cmd) > 180
    if re.search(r"(^|[;&|\s])node\s+(-[a-z]+\s+)*-e\s", low):
        return cmd.count("\n") >= 2 or len(cmd) > 180
    if "powershell" in low and "-command" in low:
        return cmd.count("\n") >= 2 or len(cmd) > 180
    if re.search(r"(^|[;&|\s])wsl(\.exe)?\b", low) and "@'" in cmd and len(cmd) > 300:
        return True
    return False


def _handle_pre_tool(payload: dict[str, Any], logs_dir: Path) -> dict[str, Any]:
    tool_name, args = _extract_args(payload)
    conv_id = str(payload.get("conversationId") or "unknown")
    state = _load_state(logs_dir, conv_id)
    now = time.time()

    if tool_name == "manage_task":
        action = str(args.get("Action") or "").strip().lower()
        task_id = str(args.get("TaskId") or "").strip()
        if action == "status" and task_id:
            polls = state.setdefault("polls", {})
            history: list[float] = [ts for ts in polls.get(task_id, []) if now - ts < 3600]
            if history and (now - history[-1] < 45.0 or len(history) >= 3):
                reason = (
                    f"Blocked manage_task(status) polling loop on {task_id} "
                    f"({len(history)} poll(s) already). Wait for SYSTEM_MESSAGE or use schedule()."
                )
                _append_issue(
                    logs_dir,
                    payload,
                    severity="prevented",
                    category="polling_loop_blocked",
                    signature=task_id,
                    detail=reason,
                    hint="Await SYSTEM_MESSAGE wakeup instead of polling manage_task(status).",
                    state=state,
                )
                _save_state(logs_dir, conv_id, state)
                return {"decision": "deny", "reason": reason}
            history.append(now)
            polls[task_id] = history[-10:]
            _save_state(logs_dir, conv_id, state)
        return {"decision": "allow"}

    if tool_name == "run_command":
        cmd = str(args.get("CommandLine") or "")
        low = cmd.lower()

        if _is_multiline_inline_script(cmd):
            reason = (
                "Blocked multiline inline script (-c / -e / PowerShell->WSL bridge). "
                "Write the script cleanly to a .py/.sh file with write_file and execute the file."
            )
            _append_issue(
                logs_dir,
                payload,
                severity="prevented",
                category="inline_quoting_blocked",
                signature="multiline_inline",
                detail=cmd[:200],
                hint="Use write_file to create a scratch script file instead of inline multiline quotes.",
                state=state,
            )
            _save_state(logs_dir, conv_id, state)
            return {"decision": "deny", "reason": reason}

        if os.name == "nt" and "unittest discover -s scripts" in low and not re.search(r"\bwsl(\.exe)?\b", low):
            reason = (
                "Blocked running POSIX-dependent scripts/test_*.py directly on Windows "
                "(slow failures). Run inside WSL2 instead."
            )
            _append_issue(
                logs_dir,
                payload,
                severity="prevented",
                category="wrong_os_test_blocked",
                signature="scripts_unittest_win",
                detail=cmd[:200],
                hint="Execute POSIX/Docker test suites inside WSL2 directly.",
                state=state,
            )
            _save_state(logs_dir, conv_id, state)
            return {"decision": "deny", "reason": reason}

        if re.search(r"\b(python3?|py|uv)\b[^\n;]*(db_export|dump_table|full_export)\b", low) and not any(
            f in low for f in ("--run-id", "--limit", "--dry-run", "--help", " -h")
        ):
            reason = (
                "Unguarded full DB export detected without --run-id, --limit, or --dry-run. "
                "Add --run-id / --limit to prevent slow full-table dumps, or approve explicitly."
            )
            _append_issue(
                logs_dir,
                payload,
                severity="prevented",
                category="unguarded_export_prompt",
                signature="db_export_no_filter",
                detail=cmd[:200],
                hint="Always scope live DB exports with --run-id or --limit.",
                state=state,
            )
            _save_state(logs_dir, conv_id, state)
            return {"decision": "ask", "reason": reason}

        if re.search(r"\b(python3?|py|uv)\b[^\n;]*(ci_gate|run_ci)\.py\b[^\n;]*--ci\b", low):
            gate_ts = float(state.get("gate_running_ts") or 0.0)
            if state.get("last_pytest_failed") or (gate_ts > 0 and now - gate_ts < 1200):
                reason = (
                    "Full CI gate requested while targeted pytest recently failed or another gate ran <20m ago. "
                    "Fix/pass targeted tests first or confirm."
                )
                _append_issue(
                    logs_dir,
                    payload,
                    severity="prevented",
                    category="premature_ci_gate_prompt",
                    signature="gate_ci_guard",
                    detail=cmd[:200],
                    hint="Run fast targeted tests first; keep full CI gate for the final milestone check.",
                    state=state,
                )
                _save_state(logs_dir, conv_id, state)
                return {"decision": "ask", "reason": reason}
            state["gate_running_ts"] = now
            _save_state(logs_dir, conv_id, state)

        return {"decision": "allow"}

    if tool_name in ("edit_file", "replace_file_content", "multi_replace_file_content"):
        fpath = _normalize_path(args.get("Path") or args.get("TargetFile"))
        if fpath and state.get("edit_error_files", {}).get(fpath):
            reason = (
                f"Blocked blind edit retry on {Path(fpath).name}: previous edit failed on target match. "
                "Inspect the exact lines with read_file/view_file first."
            )
            _append_issue(
                logs_dir,
                payload,
                severity="prevented",
                category="blind_edit_retry_blocked",
                signature=Path(fpath).name,
                detail=reason,
                hint="Read the exact target range before retrying failed edit_file.",
                state=state,
            )
            _save_state(logs_dir, conv_id, state)
            return {"decision": "deny", "reason": reason}
        return {"decision": "allow"}

    if tool_name in ("read_file", "view_file"):
        raw_path = str(args.get("Path") or args.get("AbsolutePath") or args.get("path") or "").strip().strip('"').strip("'")
        fpath = _normalize_path(raw_path)
        start = str(args.get("StartLine") or args.get("start_line") or "").strip()
        end = str(args.get("EndLine") or args.get("end_line") or "").strip()
        key = f"{fpath}:{start}:{end}"
        recent = state.get("recent_reads", [])
        if fpath and any(
            isinstance(item, dict) and item.get("k") == key and (now - float(item.get("ts", 0))) < 90.0
            for item in recent[-5:]
        ):
            reason = f"Blocked identical duplicate read of {Path(fpath).name} [{start or '1'}:{end or 'EOF'}]."
            _append_issue(
                logs_dir,
                payload,
                severity="prevented",
                category="duplicate_read_blocked",
                signature=Path(fpath).name,
                detail=reason,
                hint="Reuse prior read output or locate exact block with rg -n.",
                state=state,
            )
            _save_state(logs_dir, conv_id, state)
            return {"decision": "deny", "reason": reason}

        if not start and not end and raw_path:
            target = Path(raw_path)
            if not target.is_absolute():
                ws_first = str((payload.get("workspacePaths") or [""])[0] or "").strip()
                if ws_first:
                    cand = Path(ws_first) / target
                    if cand.is_file():
                        target = cand
            if target.suffix.lower() in _BIG_READ_SOURCE_SUFFIXES and target.is_file():
                try:
                    if target.stat().st_size > 2500:
                        with target.open("rb") as f:
                            line_count = sum(1 for _ in f)
                        if line_count > 260:
                            reason = (
                                f"Blocked un-ranged full-file read of {target.name} ({line_count} lines). "
                                "Use MCP `symbol_lookup` / `memory_search` (or `rg -n`) first, "
                                "then call `read_file` with explicit `StartLine` and `EndLine` (<= 200 lines)."
                            )
                            _append_issue(
                                logs_dir,
                                payload,
                                severity="prevented",
                                category="big_unranged_read_blocked",
                                signature=target.name,
                                detail=reason,
                                hint="Use symbol_lookup / memory_search (or rg -n) first, then read <= 200 lines with StartLine and EndLine.",
                                state=state,
                            )
                            _save_state(logs_dir, conv_id, state)
                            return {"decision": "deny", "reason": reason}
                except OSError:
                    pass
        return {"decision": "allow"}

    if tool_name == "invoke_subagent":
        type_name = str(args.get("TypeName") or "self").strip().lower()
        workspace = str(args.get("Workspace") or "inherit").strip().lower()
        is_readonly = type_name == "research"

        inherit_ts = [t for t in state.get("inherit_write_timestamps", []) if now - t < 30.0]
        if (not is_readonly) and workspace in ("", "inherit") and inherit_ts:
            reason = (
                "Blocked parallel write-capable subagent in Workspace='inherit' (prevents shared-folder file collisions). "
                "Retry immediately with Workspace='share' (git-worktree isolation) or 'branch', or use TypeName='research'."
            )
            _append_issue(
                logs_dir,
                payload,
                severity="prevented",
                category="parallel_inherit_subagent_blocked",
                signature=f"{type_name}:{workspace}",
                detail=reason,
                hint="Always isolate parallel coding subagents with Workspace='share' (Plan B agile-swarm).",
                state=state,
            )
            _save_state(logs_dir, conv_id, state)
            return {"decision": "deny", "reason": reason}

        ts_list = [t for t in state.get("subagent_timestamps", []) if now - t < 120.0]
        if len(ts_list) >= 3:
            reason = (
                f"Already launched {len(ts_list)} subagents in the last 2 minutes. "
                "Plan B single-account cap is <= 3 concurrent workers to avoid API/stream backoff; confirm if intentional."
            )
            _append_issue(
                logs_dir,
                payload,
                severity="prevented",
                category="subagent_flood_prompt",
                signature="invoke_subagent_burst",
                detail=reason,
                hint="Keep concurrent subagent spawns <= 3 to avoid stream exhaustion.",
                state=state,
            )
            _save_state(logs_dir, conv_id, state)
            return {"decision": "ask", "reason": reason}

        ts_list.append(now)
        state["subagent_timestamps"] = ts_list
        if (not is_readonly) and workspace in ("", "inherit"):
            inherit_ts.append(now)
            state["inherit_write_timestamps"] = inherit_ts
        _save_state(logs_dir, conv_id, state)
        return {"decision": "allow"}

    return {"decision": "allow"}


def _classify_cmd_error(err: str, cmd: str) -> str:
    low = f"{err} {cmd}".lower()
    if any(k in low for k in ("unicodeencodeerror", "unicodedecodeerror", "cp1252", "charmap")):
        return "encoding_cp1252"
    if any(k in low for k in ("parsererror", "unexpected token", "syntaxerror", "missing closing", "unterminated")):
        return "shell_or_syntax_quoting"
    if any(k in low for k in ("is not recognized", "command not found", "no module named", "uv: not found")):
        return "missing_binary_or_path"
    if any(k in low for k in ("cannot find path", "no such file", "does not exist", "filenotfounderror")):
        return "missing_file_or_wrong_path"
    if any(k in low for k in ("docker", "daemon", "postgres", "connection refused", "pipe")):
        return "docker_or_service_unavailable"
    if "git " in cmd.lower() and any(k in low for k in ("fatal:", "rejected", "conflict", "not a git repository")):
        return "git_error"
    return "test_or_runtime_failure"


def _handle_post_tool(payload: dict[str, Any], logs_dir: Path) -> dict[str, Any]:
    tool_name, args = _extract_args(payload)
    conv_id = str(payload.get("conversationId") or "unknown")
    err = str(payload.get("error") or "")
    step_idx = int(payload.get("stepIdx") or 0)
    state = _load_state(logs_dir, conv_id)

    if tool_name in ("read_file", "view_file"):
        fpath = _normalize_path(args.get("Path") or args.get("AbsolutePath"))
        start = str(args.get("StartLine") or "")
        end = str(args.get("EndLine") or "")
        if fpath and not err:
            state.setdefault("edit_error_files", {}).pop(fpath, None)
            recent = state.setdefault("recent_reads", [])
            recent.append({"k": f"{fpath}:{start}:{end}", "ts": time.time()})
            state["recent_reads"] = recent[-12:]
            rc = state.setdefault("read_counts", {})
            cnt = int(rc.get(fpath, 0)) + 1
            rc[fpath] = cnt
            if cnt in (8, 16, 25):
                _append_issue(
                    logs_dir,
                    payload,
                    severity="warning",
                    category="read_thrash",
                    signature=Path(fpath).name,
                    detail=f"File {Path(fpath).name} has been read {cnt} times in this session.",
                    hint="Use rg -n for symbol lookup and keep edits scoped to avoid re-reads.",
                    state=state,
                )

    elif tool_name in ("edit_file", "replace_file_content", "multi_replace_file_content", "write_file", "write_to_file"):
        raw_fpath = str(args.get("Path") or args.get("TargetFile") or args.get("path") or "").strip().strip('"').strip("'")
        fpath = _normalize_path(raw_fpath)
        if fpath:
            # Invalidate duplicate-read guard cache after file modification
            state["recent_reads"] = [
                r for r in state.get("recent_reads", [])
                if not (isinstance(r, dict) and str(r.get("k", "")).startswith(fpath + ":"))
            ]
            if err:
                state.setdefault("edit_error_files", {})[fpath] = True
                _append_issue(
                    logs_dir,
                    payload,
                    severity="error",
                    category="edit_mismatch",
                    signature=Path(fpath).name,
                    detail=f"{tool_name} failed on {Path(fpath).name}: {err}",
                    hint="Inspect surrounding lines before editing.",
                    state=state,
                )
            else:
                state.setdefault("edit_error_files", {}).pop(fpath, None)
                ws = _resolve_memory_workspace(payload, raw_fpath, require_db=True)
                if ws is not None:
                    mem = _load_memory_engine()
                    if mem is not None:
                        try:
                            mem.index_workspace(str(ws), paths=[raw_fpath or fpath])
                        except Exception:
                            pass

    elif tool_name == "run_command":
        cmd = str(args.get("CommandLine") or "")
        low = cmd.lower()
        if ("ci_gate.py" in low or "run_ci.py" in low) and "--ci" in low:
            state["gate_running_ts"] = 0.0
        if err:
            first_tok = cmd.strip().lower()
            is_empty_search = (
                "exit status 1" in err.lower() or "code 1" in err.lower()
            ) and bool(re.match(r"^(rg|git\s+grep|grep|findstr|select-string)\b", first_tok))
            if is_empty_search:
                _save_state(logs_dir, conv_id, state)
                return {}
            if "pytest" in low or "unittest" in low:
                state["last_pytest_failed"] = True
            if any(k in low for k in ("git checkout", "git reset", "git pull", "format", "ruff format", "dart format")):
                state["recent_reads"] = []
            subcat = _classify_cmd_error(err, cmd)
            _append_issue(
                logs_dir,
                payload,
                severity="error",
                category=f"cmd_fail:{subcat}",
                signature=cmd.strip().splitlines()[0][:60] if cmd.strip() else "run_command",
                detail=f"{err} | cmd={cmd[:180]}",
                hint=f"Classified as {subcat}; fix root environment/quoting before retrying.",
                state=state,
            )
        else:
            if "pytest" in low or "unittest" in low:
                state["last_pytest_failed"] = False

    if step_idx > 0 and step_idx % 150 == 0 and int(state.get("last_bloat_step_logged") or 0) < step_idx:
        state["last_bloat_step_logged"] = step_idx
        _append_issue(
            logs_dir,
            payload,
            severity="warning",
            category="long_session_bloat",
            signature=f"step_{step_idx}",
            detail=f"Session reached {step_idx} steps; compaction/re-read overhead rises rapidly.",
            hint="Consider running memory_checkpoint (/memory-sync) and continuing in a fresh chat to prevent costly compaction.",
            state=state,
        )

    _save_state(logs_dir, conv_id, state)
    return {}


def _probe_environment() -> list[str]:
    notes: list[str] = []
    notes.append(f"os={os.name}")
    notes.append(f"PYTHONIOENCODING={os.environ.get('PYTHONIOENCODING', '(unset)')}")
    for tool in ("python", "git", "uv", "wsl", "docker", "flutter"):
        if shutil.which(tool):
            notes.append(f"{tool}=ok")
    if os.name == "nt" and shutil.which("docker"):
        try:
            proc = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                text=True,
                timeout=1.5,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                notes.append(f"docker_daemon=running({proc.stdout.strip()})")
            else:
                notes.append("docker_daemon=stopped")
        except Exception:
            notes.append("docker_daemon=unknown")
    return notes


def _handle_session_start(payload: dict[str, Any], logs_dir: Path) -> dict[str, Any]:
    env_summary = ", ".join(_probe_environment())
    msg = (
        f"[gravity-harness-fix active] Telemetry logs: {logs_dir} | "
        f"Env: {env_summary}. Guardrails active: no polling manage_task, no multiline inline scripts, "
        f"no duplicate reads/blind edit retries, UTF-8 enforced."
    )
    ws_first = str((payload.get("workspacePaths") or [""])[0] or "").strip()
    if ws_first:
        try:
            has_mem_dir = (Path(ws_first) / ".agents" / "memory").is_dir()
        except OSError:
            has_mem_dir = False
        if has_mem_dir:
            brief = ""
            mem = _load_memory_engine()
            if mem is not None:
                try:
                    brief = str(mem.hydrate_brief(ws_first, max_chars=650) or "").strip()
                except Exception:
                    brief = ""
            if brief:
                msg = f"{msg}\n[L2 Memory] {brief}"
    return {
        "injectSteps": [
            {
                "systemMessage": {
                    "systemMessage": msg,
                }
            }
        ]
    }


def _handle_stop(payload: dict[str, Any], logs_dir: Path) -> dict[str, Any]:
    conv_id = str(payload.get("conversationId") or "unknown")
    term = str(payload.get("terminationReason") or "")
    err = str(payload.get("error") or "")
    fully_idle = payload.get("fullyIdle", True)
    state = _load_state(logs_dir, conv_id)

    if term == "NO_TOOL_CALL" and fully_idle is False:
        # Allow Antigravity to sleep and deliver async <SYSTEM_MESSAGE> wakeups cleanly
        # instead of forcing a busy-loop while subagents or background tasks finish.
        return {}

    if term in ("ERROR", "MAX_TOKEN_BUDGET_EXCEEDED", "MAX_INVOCATIONS") or err:
        _append_issue(
            logs_dir,
            payload,
            severity="error",
            category=f"session_stop_{term.lower() or 'error'}",
            signature=term or "STOP_ERROR",
            detail=err or f"Session stopped with reason={term}",
            hint="Review session-issues.jsonl or resume cleanly.",
            state=state,
        )
        _save_state(logs_dir, conv_id, state)

    return {}


def main() -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(description="Gravity Harness Fix hook handler")
    parser.add_argument("--event", required=True, choices=["SessionStart", "PreToolUse", "PostToolUse", "Stop"])
    args = parser.parse_args()

    try:
        raw_stdin = sys.stdin.read()
        payload = json.loads(raw_stdin) if raw_stdin.strip() else {}
    except Exception:
        payload = {}

    logs_dir = _resolve_logs_dir()

    try:
        if args.event == "SessionStart":
            out = _handle_session_start(payload, logs_dir)
        elif args.event == "PreToolUse":
            out = _handle_pre_tool(payload, logs_dir)
        elif args.event == "PostToolUse":
            out = _handle_post_tool(payload, logs_dir)
        elif args.event == "Stop":
            out = _handle_stop(payload, logs_dir)
        else:
            out = {}
    except Exception as exc:
        # Fail-open safety: log hook internal error cleanly and never break IDE execution
        _append_issue(
            logs_dir,
            payload if isinstance(payload, dict) else {},
            severity="warning",
            category="hook_internal_error",
            signature=type(exc).__name__,
            detail=str(exc),
            hint="Report bug in gravity_harnes_fix/plugin/hooks/guard_and_log.py",
        )
        out = {"decision": "allow"} if args.event == "PreToolUse" else {}

    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
