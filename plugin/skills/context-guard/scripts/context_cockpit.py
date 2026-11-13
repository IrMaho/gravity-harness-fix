#!/usr/bin/env python3
"""Context Budget Guard & Cockpit for Antigravity conversations.

Monitors real-time token volume, tracks active isolated task worktrees,
warns when context approaches or exceeds 80% capacity, and generates a
standalone interactive dark-mode HTML dashboard.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent.parent
AGILE_SCRIPTS = PLUGIN_ROOT / "skills" / "agile-swarm" / "scripts"
if str(AGILE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(AGILE_SCRIPTS))

try:
    import worktree_team  # noqa: E402
except ImportError:
    worktree_team = None  # type: ignore


def _resolve_app_data_dir() -> Path:
    """Resolve Antigravity appDataDir across environment candidates."""
    candidates = [
        Path(r"C:\Gravity-5-1\home\.gemini\antigravity"),
        Path.home() / ".gemini" / "antigravity",
        Path(os.environ.get("APPDATA", "")) / "Google" / "Antigravity",
    ]
    for c in candidates:
        if c.exists() and (c / "brain").is_dir():
            return c
    return candidates[0]


def find_latest_conversation(app_data_dir: Path | None = None) -> tuple[str, Path] | None:
    """Find the most recently modified conversation directory in brain."""
    app_dir = app_data_dir or _resolve_app_data_dir()
    brain_dir = app_dir / "brain"
    if not brain_dir.is_dir():
        return None

    best_conv = None
    best_mtime = -1.0
    for child in brain_dir.iterdir():
        if child.is_dir():
            transcript = child / ".system_generated" / "logs" / "transcript.jsonl"
            if transcript.is_file():
                try:
                    mtime = transcript.stat().st_mtime
                    if mtime > best_mtime:
                        best_mtime = mtime
                        best_conv = (child.name, transcript)
                except OSError:
                    continue
    return best_conv


def analyze_conversation_context(
    conv_id: str | None = None,
    app_data_dir: Path | None = None,
    max_tokens: int = 200000,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """Parse transcript and evaluate exact token volume and 80% threshold status."""
    app_dir = app_data_dir or _resolve_app_data_dir()
    transcript_path: Path | None = None
    resolved_conv_id = conv_id or ""

    if conv_id:
        cand = app_dir / "brain" / conv_id / ".system_generated" / "logs" / "transcript.jsonl"
        if cand.is_file():
            transcript_path = cand
    if transcript_path is None:
        latest = find_latest_conversation(app_dir)
        if latest:
            resolved_conv_id, transcript_path = latest

    total_steps = 0
    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    error_steps = 0
    checkpoint_steps = 0
    user_inputs = 0
    planner_responses = 0

    if transcript_path and transcript_path.is_file():
        try:
            for line in transcript_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                total_steps += 1
                stype = row.get("type")
                if stype == "ERROR_MESSAGE":
                    error_steps += 1
                elif stype == "CHECKPOINT":
                    checkpoint_steps += 1
                elif stype == "USER_INPUT":
                    user_inputs += 1
                elif stype == "PLANNER_RESPONSE":
                    planner_responses += 1
                    # Extract latest token counts
                    if "input_tokens" in row:
                        input_tokens = int(row.get("input_tokens") or 0)
                    if "output_tokens" in row:
                        output_tokens = int(row.get("output_tokens") or 0)
                    if "cache_read_tokens" in row:
                        cache_read_tokens = int(row.get("cache_read_tokens") or 0)
        except OSError:
            pass

    current_tokens = input_tokens + output_tokens
    usage_pct = round((current_tokens / max(1, max_tokens)) * 100.0, 1)

    if usage_pct >= 80.0:
        status = "CRITICAL_THROTTLE_REQUIRED"
        badge = "🔴 CRITICAL (>80%)"
    elif usage_pct >= 60.0:
        status = "ELEVATED_MONITOR"
        badge = "🟡 ELEVATED (60-80%)"
    else:
        status = "HEALTHY"
        badge = "🟢 HEALTHY (<60%)"

    # Worktree inspection for task isolation
    worktree_slices: list[dict[str, Any]] = []
    if workspace and worktree_team and workspace.is_dir():
        try:
            porcelain = worktree_team.parse_worktree_porcelain(workspace)
            main_norm = os.path.normcase(str(workspace.resolve()))
            for item in porcelain:
                w_path = Path(item["path"])
                if os.path.normcase(str(w_path)) != main_norm:
                    worktree_slices.append({
                        "branch": item.get("branch", "(detached)"),
                        "path": str(w_path),
                        "dirty": item.get("dirty", False),
                    })
        except Exception:
            pass

    return {
        "conversation_id": resolved_conv_id,
        "transcript_path": str(transcript_path) if transcript_path else "",
        "max_tokens": max_tokens,
        "current_tokens": current_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "remaining_tokens": max(0, max_tokens - current_tokens),
        "usage_pct": usage_pct,
        "status": status,
        "badge": badge,
        "total_steps": total_steps,
        "user_inputs": user_inputs,
        "planner_responses": planner_responses,
        "error_steps": error_steps,
        "checkpoint_compactions": checkpoint_steps,
        "isolated_worktree_count": len(worktree_slices),
        "isolated_worktrees": worktree_slices,
        "recommendation": (
            "Context above 80% threshold! Snapshot state to L2 (.agents/memory), compact chat (/compact), "
            "and offload all coding/testing into isolated subagent worktrees (/agile-swarm)."
            if usage_pct >= 80.0
            else (
                "Context elevated. Keep main chat lean: delegate heavy multi-file edits to isolated worktrees."
                if usage_pct >= 60.0
                else "Context healthy. Main chat operating smoothly."
            )
        ),
    }


def generate_html_cockpit(data: dict[str, Any], output_path: Path) -> Path:
    """Generate dark-mode interactive HTML Context Cockpit."""
    pct = data["usage_pct"]
    bar_color = "#ef4444" if pct >= 80 else ("#f59e0b" if pct >= 60 else "#10b981")
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    slices_html = ""
    if data["isolated_worktrees"]:
        for s in data["isolated_worktrees"]:
            flag = "<span class='badge dirty'>DIRTY (Uncommitted)</span>" if s["dirty"] else "<span class='badge clean'>CLEAN</span>"
            slices_html += f"""
            <div class="slice-card">
              <div class="slice-header">
                <strong>{s['branch']}</strong>
                {flag}
              </div>
              <div class="slice-path">{s['path']}</div>
            </div>
            """
    else:
        slices_html = "<div class='empty-note'>No isolated task worktrees currently active. All work is concentrated in the main context.</div>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Antigravity Context Cockpit</title>
  <style>
    :root {{
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #38bdf8;
      --danger: #ef4444;
      --warning: #f59e0b;
      --success: #10b981;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 24px;
      line-height: 1.5;
    }}
    .container {{
      max-width: 900px;
      margin: 0 auto;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
    }}
    h1 {{ font-size: 24px; font-weight: 700; color: #fff; }}
    .time {{ color: var(--text-muted); font-size: 13px; font-family: monospace; }}
    .alert-banner {{
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid var(--danger);
      padding: 16px;
      border-radius: 8px;
      margin-bottom: 24px;
      display: {"block" if pct >= 80 else "none"};
    }}
    .alert-banner h3 {{ color: var(--danger); font-size: 16px; margin-bottom: 6px; }}
    .gauge-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 24px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}
    .gauge-header {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
    }}
    .gauge-title {{ font-size: 18px; font-weight: 600; }}
    .gauge-pct {{ font-size: 36px; font-weight: 800; color: {bar_color}; }}
    .progress-bar-bg {{
      background: #334155;
      height: 14px;
      border-radius: 7px;
      overflow: hidden;
      position: relative;
    }}
    .progress-bar-fill {{
      background: {bar_color};
      width: {min(100.0, pct)}%;
      height: 100%;
      border-radius: 7px;
      transition: width 0.3s ease;
    }}
    .thresh-marker {{
      position: absolute;
      left: 80%;
      top: 0;
      bottom: 0;
      width: 2px;
      background: #ffffff;
      opacity: 0.8;
    }}
    .thresh-label {{
      display: flex;
      justify-content: space-between;
      color: var(--text-muted);
      font-size: 12px;
      margin-top: 4px;
    }}
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .metric-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
    }}
    .metric-label {{ font-size: 13px; color: var(--text-muted); margin-bottom: 6px; }}
    .metric-value {{ font-size: 22px; font-weight: 700; color: #fff; font-family: monospace; }}
    .section-title {{
      font-size: 18px;
      font-weight: 600;
      margin-bottom: 12px;
      color: var(--accent);
    }}
    .isolation-container {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 24px;
    }}
    .slice-card {{
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      margin-bottom: 10px;
    }}
    .slice-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 6px;
    }}
    .slice-path {{
      font-size: 12px;
      color: var(--text-muted);
      font-family: monospace;
    }}
    .badge {{
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 12px;
      font-weight: 600;
    }}
    .badge.dirty {{ background: rgba(239, 68, 68, 0.2); color: var(--danger); border: 1px solid var(--danger); }}
    .badge.clean {{ background: rgba(16, 185, 129, 0.2); color: var(--success); border: 1px solid var(--success); }}
    .empty-note {{ color: var(--text-muted); font-size: 14px; text-align: center; padding: 12px; }}
    .action-box {{
      background: #1e1e38;
      border: 1px solid #4338ca;
      border-radius: 10px;
      padding: 16px;
    }}
    .action-box h4 {{ color: #a5b4fc; margin-bottom: 8px; }}
    .action-box ul {{ padding-left: 20px; color: #cbd5e1; font-size: 14px; }}
    .action-box li {{ margin-bottom: 6px; }}
    code {{ background: #0f172a; padding: 2px 6px; border-radius: 4px; font-family: monospace; color: #38bdf8; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>🛡️ Antigravity Context Cockpit</h1>
        <div class="time">Conversation: {data['conversation_id'][:12]}... | Updated: {now_utc}</div>
      </div>
      <div>{data['badge']}</div>
    </header>

    <div class="alert-banner">
      <h3>⚠️ High Context Warning (Exceeds 80% Safety Ceiling)</h3>
      <p>{data['recommendation']}</p>
    </div>

    <div class="gauge-card">
      <div class="gauge-header">
        <div class="gauge-title">Total Context Window Utilization</div>
        <div class="gauge-pct">{pct}%</div>
      </div>
      <div class="progress-bar-bg">
        <div class="progress-bar-fill"></div>
        <div class="thresh-marker" title="80% Safety Threshold"></div>
      </div>
      <div class="thresh-label">
        <span>0 tokens</span>
        <span style="margin-left: 60%;">80% Threshold</span>
        <span>{data['max_tokens']:,} max tokens</span>
      </div>
    </div>

    <div class="metrics-grid">
      <div class="metric-card">
        <div class="metric-label">Current Active Tokens</div>
        <div class="metric-value">{data['current_tokens']:,}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Input / Output Tokens</div>
        <div class="metric-value">{data['input_tokens']:,} / {data['output_tokens']:,}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Remaining Safe Budget</div>
        <div class="metric-value">{data['remaining_tokens']:,}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Total Steps / Compactions</div>
        <div class="metric-value">{data['total_steps']} / {data['checkpoint_compactions']}</div>
      </div>
    </div>

    <div class="section-title">🛡️ Task Context Isolation Matrix</div>
    <div class="isolation-container">
      {slices_html}
    </div>

    <div class="action-box">
      <h4>⚡ Recommended Multi-Context Architecture (How to stay &lt;80%):</h4>
      <ul>
        <li><strong>Level 1 (Main Chat Cockpit):</strong> Keep for architecture decisions, review, and user direction. Never dump huge multi-file reads here.</li>
        <li><strong>Level 2 (Isolated Subagent Worktrees):</strong> Use <code>/agile-swarm</code> with <code>Workspace="share"</code>. Each subagent gets its own clean branch and isolated temporary context.</li>
        <li><strong>Zero-Loss Safety:</strong> If an isolated subagent is interrupted by network drop, run <code>python .../worktree_team.py rescue .</code> to adopt files without data loss.</li>
        <li><strong>Level 3 (Handoff Checkpoint):</strong> When main chat hits 80%, persist state via <code>memory_checkpoint</code> and open a fresh chat or type <code>/compact</code>.</li>
      </ul>
    </div>
  </div>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Antigravity Context Cockpit & Budget Guard")
    parser.add_argument("--conv-id", help="Conversation ID (default: auto-detect latest)")
    parser.add_argument("--workspace", default=os.getcwd(), help="Workspace path to inspect worktrees")
    parser.add_argument("--max-tokens", type=int, default=200000, help="Maximum context token capacity")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("--html", action="store_true", help="Generate HTML dashboard")
    parser.add_argument("--output", help="HTML dashboard output path")
    args = parser.parse_args(argv)

    ws_path = Path(args.workspace).resolve() if args.workspace else None
    report = analyze_conversation_context(
        conv_id=args.conv_id,
        max_tokens=args.max_tokens,
        workspace=ws_path,
    )

    if args.html or args.output:
        out_path = Path(args.output).resolve() if args.output else (ws_path or Path.cwd()) / "CONTEXT_COCKPIT.html"
        generate_html_cockpit(report, out_path)
        if not args.json:
            print(f"[OK] Generated Context Cockpit dashboard: {out_path}")

    if args.json or not (args.html or args.output):
        print(json.dumps(report, indent=2, ensure_ascii=False))

    return 1 if report["usage_pct"] >= 80.0 else 0


if __name__ == "__main__":
    raise SystemExit(main())

