#!/usr/bin/env python3
"""Summarize live Antigravity telemetry logs recorded by gravity-harness-fix."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


SKILL_DIR = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = SKILL_DIR.parent.parent
CONFIG_FILE = PLUGIN_ROOT / "harness_config.json"


def resolve_logs_dir(explicit: str = "") -> Path:
    if explicit:
        return Path(explicit)
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if cfg.get("logsDir") and Path(cfg["logsDir"]).exists():
                return Path(cfg["logsDir"])
            if cfg.get("fallbackLogsDir") and Path(cfg["fallbackLogsDir"]).exists():
                return Path(cfg["fallbackLogsDir"])
        except Exception:
            pass
    for fallback in (
        PLUGIN_ROOT.parent.parent / "gravity-harness-logs",
        Path.home() / ".gemini" / "gravity-harness-logs",
    ):
        if fallback.exists():
            return fallback
    return PLUGIN_ROOT / "logs"


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect gravity-harness-fix telemetry logs.")
    parser.add_argument("--logs-dir", default="", help="Override telemetry logs directory")
    parser.add_argument("--tail", type=int, default=25, help="Number of latest events to show")
    args = parser.parse_args()

    logs_dir = resolve_logs_dir(args.logs_dir)
    log_file = logs_dir / "session-issues.jsonl"
    print(f"Telemetry directory: {logs_dir}")

    if not log_file.exists():
        print("No session-issues.jsonl recorded yet (no anomalies detected or plugin not yet triggered).")
        return 0

    records: list[dict[str, Any]] = []
    with log_file.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    cats = Counter(r.get("category", "unknown") for r in records)
    sevs = Counter(r.get("severity", "unknown") for r in records)
    print(f"Total logged events: {len(records)} | severities: {dict(sevs)}")
    print("\n=== Top Issue Categories ===")
    for cat, cnt in cats.most_common(15):
        print(f"  {cat:32s}: {cnt}")

    print(f"\n=== Latest {min(args.tail, len(records))} Events ===")
    for r in records[-args.tail :]:
        print(
            f"  [{r.get('ts_utc','')}] ({r.get('severity','')}) {r.get('category','')} | "
            f"conv={str(r.get('conv_id',''))[:8]} | {str(r.get('detail',''))[:110]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

