#!/usr/bin/env python3
"""Forensic auditor across all Antigravity conversation transcripts.

Scans every .gemini root on the machine (e.g. ~/.gemini and custom Gravity
sandbox homes), inspects every conversation and subagent transcript.jsonl, and
quantifies bottlenecks, failed commands, polling loops, edit thrashing, API
stalls, context compactions, and premature stops.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def discover_gemini_roots(extra_roots: list[str] | None = None) -> list[Path]:
    """Return unique existing .gemini root directories on this machine."""
    candidates: list[Path] = []
    for env_var in ("USERPROFILE", "HOME"):
        val = os.environ.get(env_var)
        if val:
            candidates.append(Path(val) / ".gemini")

    # Standard Windows user profile even when running inside sandboxed HOME
    username = os.environ.get("USERNAME")
    if username:
        candidates.append(Path("C:/Users") / username / ".gemini")

    # Sandboxed Gravity-X-Y/home/.gemini installations if present on C:\
    for p in Path("C:/").glob("Gravity-*/home/.gemini"):
        candidates.append(p)

    for raw in extra_roots or []:
        candidates.append(Path(raw))

    unique: list[Path] = []
    seen: set[str] = set()
    for cand in candidates:
        try:
            resolved = str(cand.resolve())
        except OSError:
            resolved = str(cand)
        key = resolved.lower()
        if key not in seen and cand.exists():
            seen.add(key)
            unique.append(cand)
    return unique


def parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def safe_args(tc: dict[str, Any]) -> dict[str, Any]:
    raw = tc.get("args") or tc.get("arguments") or tc.get("arguments_json") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return {}
    return raw if isinstance(raw, dict) else {}


def clean_str(val: Any) -> str:
    if val is None:
        return ""
    s = str(val)
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            return json.loads(s)
        except Exception:
            return s.strip('"')
    return s


def classify_command_error(output_text: str, cmd_text: str) -> str:
    low = output_text.lower()
    cmd_low = cmd_text.lower()
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
    if "git " in cmd_low and any(k in low for k in ("fatal:", "rejected", "conflict", "not a git repository")):
        return "git_error"
    if any(k in low for k in ("failed", "assertionerror", "traceback", "error:", "exception")):
        return "test_or_runtime_failure"
    return "nonzero_exit_other"


def analyze_transcript(conv_id: str, root_label: str, path: Path) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                steps.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not steps:
        return {"conv_id": conv_id, "root": root_label, "empty": True, "steps": 0}

    first_user = ""
    user_turns = 0
    tool_counts: Counter[str] = Counter()
    read_targets: Counter[str] = Counter()
    poll_tasks: Counter[str] = Counter()
    edit_errors = 0
    cmd_exit_nonzero = 0
    cmd_error_types: Counter[str] = Counter()
    api_error_steps = 0
    api_backoff_s = 0.0
    checkpoints = 0
    subagent_spawns = 0
    premature_stop_prompts = 0
    llm_stream_s = 0.0
    sync_tool_s = 0.0
    user_wait_s = 0.0
    bg_wait_s = 0.0

    # Walk steps
    last_planner_tools: list[dict[str, Any]] = []
    prev_was_assistant_stop = False

    timestamps = [parse_ts(s.get("created_at")) for s in steps]
    valid_ts = [t for t in timestamps if t is not None]
    span_s = (valid_ts[-1] - valid_ts[0]).total_seconds() if len(valid_ts) >= 2 else 0.0

    bg_task_canceled = 0
    bg_task_failed = 0
    windows_paths_detected: Counter[str] = Counter()

    for i, s in enumerate(steps):
        stype = s.get("type", "")
        status = s.get("status", "")
        content = s.get("content") or ""

        if stype == "USER_INPUT":
            user_turns += 1
            if not first_user:
                first_user = content.replace("\r", "").replace("\n", " ")[:110]
            if prev_was_assistant_stop and any(
                k in content for k in ("ادامه", "چرا متوقف", "چی شد", "متوقف شدی", "continue", "why did you stop")
            ):
                premature_stop_prompts += 1

        if stype == "CHECKPOINT":
            checkpoints += 1

        if stype == "ERROR_MESSAGE" or status == "ERROR":
            api_error_steps += 1
            if "unable to find" in content.lower() or "edit_file" in str(last_planner_tools):
                if "edit" in content.lower() or "target" in content.lower() or "replace" in content.lower():
                    edit_errors += 1

        if stype == "SYSTEM_MESSAGE":
            if "was canceled" in content:
                bg_task_canceled += 1
            elif re.search(r"exited with code [1-9]", content):
                bg_task_failed += 1

        if stype == "PLANNER_RESPONSE":
            tcs = s.get("tool_calls") or []
            last_planner_tools = tcs
            prev_was_assistant_stop = (len(tcs) == 0)
            for tc in tcs:
                tname = tc.get("name", "unknown")
                tool_counts[tname] += 1
                args = safe_args(tc)
                if tname in ("read_file", "view_file"):
                    p = clean_str(args.get("Path") or args.get("AbsolutePath") or "")
                    if p:
                        read_targets[p] += 1
                elif tname == "manage_task":
                    act = clean_str(args.get("Action") or "")
                    tid = clean_str(args.get("TaskId") or "")
                    if act == "status" and tid:
                        poll_tasks[tid] += 1
                elif tname == "invoke_subagent":
                    subagent_spawns += 1
                elif tname == "run_command":
                    cmd = clean_str(args.get("CommandLine") or "")
                    m_proj = re.search(r"[A-Za-z]:\\(?:Users|home)\\[^\\\"'\s]+\\(?:Desktop\\)?([^\\\"'\s]+)", cmd)
                    if m_proj:
                        windows_paths_detected[m_proj.group(1)] += 1
        elif stype == "GENERIC":
            if "Command exited with code" in content and "Command exited with code 0" not in content:
                cmd_exit_nonzero += 1
                # try grab nearest preceding run_command
                cmd_text = ""
                for k in range(i - 1, max(-1, i - 6), -1):
                    if steps[k].get("type") == "PLANNER_RESPONSE":
                        for tc in (steps[k].get("tool_calls") or []):
                            if tc.get("name") == "run_command":
                                cmd_text = clean_str(safe_args(tc).get("CommandLine") or "")
                                break
                        if cmd_text:
                            break
                cmd_error_types[classify_command_error(content, cmd_text)] += 1
            elif "Target" in content and ("not found" in content.lower() or "occurred 0 times" in content.lower() or "failed" in content.lower()):
                edit_errors += 1

        if i + 1 < len(steps):
            t0 = parse_ts(s.get("created_at"))
            t1 = parse_ts(steps[i + 1].get("created_at"))
            if t0 and t1:
                dt = max(0.0, (t1 - t0).total_seconds())
                s1 = steps[i + 1]
                s1_type = s1.get("type", "")
                if (stype == "ERROR_MESSAGE" or s1_type == "ERROR_MESSAGE") and dt >= 10:
                    api_backoff_s += dt
                elif s1_type == "USER_INPUT" and dt >= 10:
                    user_wait_s += dt
                elif s1_type == "SYSTEM_MESSAGE":
                    bg_wait_s += dt
                elif stype == "PLANNER_RESPONSE" and s1_type == "GENERIC":
                    llm_stream_s += dt
                elif s1_type == "GENERIC":
                    sync_tool_s += dt
                elif s1_type == "PLANNER_RESPONSE" and stype == "GENERIC":
                    sync_tool_s += dt

    total_reads = tool_counts["read_file"] + tool_counts["view_file"]
    repeated_reads = sum(cnt - 2 for cnt in read_targets.values() if cnt > 2)
    top_read = read_targets.most_common(3)
    top_polls = poll_tasks.most_common(3)
    is_user_chat = user_turns > 0
    is_subagent = not is_user_chat

    return {
        "conv_id": conv_id,
        "root": root_label,
        "empty": False,
        "kind": "user_chat" if is_user_chat else "subagent",
        "start_utc": valid_ts[0].isoformat() if valid_ts else "",
        "end_utc": valid_ts[-1].isoformat() if valid_ts else "",
        "span_min": round(span_s / 60.0, 2),
        "steps": len(steps),
        "user_turns": user_turns,
        "first_user": first_user,
        "checkpoints": checkpoints,
        "tools": dict(tool_counts),
        "total_reads": total_reads,
        "repeated_reads_over_2": repeated_reads,
        "top_reads": [(Path(p).name, c) for p, c in top_read],
        "manage_task_polls": sum(poll_tasks.values()),
        "top_poll_tasks": top_polls,
        "run_command_total": tool_counts["run_command"],
        "cmd_exit_nonzero": cmd_exit_nonzero,
        "cmd_error_types": dict(cmd_error_types),
        "edit_calls": tool_counts["edit_file"] + tool_counts["replace_file_content"] + tool_counts["multi_replace_file_content"],
        "edit_errors": edit_errors,
        "write_calls": tool_counts["write_file"] + tool_counts["write_to_file"],
        "api_error_steps": api_error_steps,
        "api_backoff_min": round(api_backoff_s / 60.0, 2),
        "bg_task_canceled": bg_task_canceled,
        "bg_task_failed": bg_task_failed,
        "premature_stop_prompts": premature_stop_prompts,
        "subagent_spawns": subagent_spawns,
        "llm_stream_min": round(llm_stream_s / 60.0, 2),
        "sync_tool_min": round(sync_tool_s / 60.0, 2),
        "bg_wait_min": round(bg_wait_s / 60.0, 2),
        "user_wait_min": round(user_wait_s / 60.0, 2),
    }


def scan_all(roots: list[Path]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for root in roots:
        brain = root / "antigravity" / "brain"
        if not brain.exists():
            continue
        root_label = str(root)
        for item in sorted(brain.iterdir()):
            if not item.is_dir() or item.name == "tempmediaStorage":
                continue
            tf = item / ".system_generated" / "logs" / "transcript.jsonl"
            if not tf.exists():
                tf = item / "transcript.jsonl"
            if not tf.exists():
                continue
            results.append(analyze_transcript(item.name, root_label, tf))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit all Antigravity conversation transcripts.")
    parser.add_argument("--extra-root", action="append", default=[], help="Extra .gemini root path to scan")
    parser.add_argument("--json-out", type=str, default="", help="Optional JSON output file path")
    args = parser.parse_args()

    roots = discover_gemini_roots(args.extra_root)
    print(f"Discovered {len(roots)} .gemini root(s):")
    for r in roots:
        print(f"  - {r}")

    results = scan_all(roots)
    non_empty = [r for r in results if not r.get("empty")]
    user_chats = [r for r in non_empty if r["kind"] == "user_chat"]
    subagents = [r for r in non_empty if r["kind"] == "subagent"]

    print(f"\nScanned transcripts: {len(non_empty)} non-empty ({len(user_chats)} user_chats, {len(subagents)} subagents)")
    print("\n=== PRIMARY USER CHATS ===")
    agg_err_types: Counter[str] = Counter()
    for r in sorted(user_chats, key=lambda x: x["steps"], reverse=True):
        print(
            f"- {r['conv_id'][:8]} | root={Path(r['root']).parent.name} | steps={r['steps']:4d} | "
            f"span={r['span_min']:7.1f}m | turns={r['user_turns']:2d} | ckpt={r['checkpoints']:2d} | "
            f"cmds={r['run_command_total']:3d} (fail={r['cmd_exit_nonzero']:3d}, bg_fail={r['bg_task_failed']}, cancel={r['bg_task_canceled']}) | "
            f"reads={r['total_reads']:3d} (repeat>2={r['repeated_reads_over_2']:3d}) | polls={r['manage_task_polls']:3d} | "
            f"edits={r['edit_calls']:3d} (err={r['edit_errors']}) | api_err={r['api_error_steps']:2d} ({r['api_backoff_min']:.1f}m) | "
            f"stops={r['premature_stop_prompts']}"
        )
        print(f"    prompt={r['first_user']!r}")
        if r["cmd_error_types"]:
            print(f"    cmd_errors={r['cmd_error_types']}")
        if r["top_reads"]:
            print(f"    top_reads={r['top_reads']}")

    # Aggregate across ALL transcripts (user chats + subagents)
    tot_steps = sum(r["steps"] for r in non_empty)
    tot_cmds = sum(r["run_command_total"] for r in non_empty)
    tot_cmd_fail = sum(r["cmd_exit_nonzero"] for r in non_empty)
    tot_bg_fail = sum(r["bg_task_failed"] for r in non_empty)
    tot_bg_cancel = sum(r["bg_task_canceled"] for r in non_empty)
    tot_reads = sum(r["total_reads"] for r in non_empty)
    tot_rep_reads = sum(r["repeated_reads_over_2"] for r in non_empty)
    tot_polls = sum(r["manage_task_polls"] for r in non_empty)
    tot_edits = sum(r["edit_calls"] for r in non_empty)
    tot_edit_err = sum(r["edit_errors"] for r in non_empty)
    tot_api_err = sum(r["api_error_steps"] for r in non_empty)
    tot_api_min = sum(r["api_backoff_min"] for r in non_empty)
    tot_ckpt = sum(r["checkpoints"] for r in non_empty)
    subagent_err_deaths = sum(1 for r in subagents if r["api_error_steps"] > 0)

    for r in non_empty:
        for k, v in r["cmd_error_types"].items():
            agg_err_types[k] += v

    print("\n=== AGGREGATE ACROSS ALL 100% OF TRANSCRIPTS (USER + SUBAGENTS) ===")
    print(f"  Total non-empty transcripts : {len(non_empty)} ({len(user_chats)} user + {len(subagents)} subagents)")
    print(f"  Total steps                 : {tot_steps}")
    print(f"  Context checkpoints         : {tot_ckpt}")
    print(f"  run_command total / failed  : {tot_cmds} / {tot_cmd_fail} sync fail ({(tot_cmd_fail/max(1,tot_cmds))*100:.1f}%), bg_fail={tot_bg_fail}, bg_cancel={tot_bg_cancel}")
    print(f"  read_file/view_file total   : {tot_reads} (redundant >2 reads of same file: {tot_rep_reads})")
    print(f"  manage_task(status) polls   : {tot_polls}")
    print(f"  edit calls / edit errors    : {tot_edits} / {tot_edit_err}")
    print(f"  API/stream error steps/time : {tot_api_err} steps, {tot_api_min:.1f} min backoff | subagents hitting errors: {subagent_err_deaths}/{len(subagents)}")
    print(f"  Command failure breakdown   : {dict(agg_err_types.most_common())}")

    # Show top failing/erroneous subagents
    bad_subs = [r for r in subagents if r["api_error_steps"] > 0 or r["cmd_exit_nonzero"] >= 5 or r["edit_errors"] > 0]
    print(f"\n=== SUBAGENTS WITH SIGNIFICANT ERRORS/FRICTION ({len(bad_subs)}/{len(subagents)}) ===")
    for r in sorted(bad_subs, key=lambda x: (x["api_error_steps"] + x["cmd_exit_nonzero"]), reverse=True)[:20]:
        print(
            f"  sub={r['conv_id'][:8]} | {r['root'].split('\\')[-2]} | steps={r['steps']:3d} | "
            f"cmds={r['run_command_total']:2d} (fail={r['cmd_exit_nonzero']:2d}) | reads={r['total_reads']:2d} | "
            f"edits={r['edit_calls']:2d} (err={r['edit_errors']}) | api_err={r['api_error_steps']} ({r['api_backoff_min']:.1f}m) | {r['cmd_error_types']}"
        )

    if args.json_out:
        out_p = Path(args.json_out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(non_empty, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nSaved full JSON report to: {out_p}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

