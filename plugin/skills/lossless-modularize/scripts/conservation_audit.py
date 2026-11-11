#!/usr/bin/env python3
"""Lossless modularization verifier: line conservation, symbol accounting & size gate.

Captures a pre-refactor baseline snapshot of symbols and code volume, then verifies
that modularized output preserves every symbol, avoids unexpected code loss, stays
within file-line caps, and introduces no obvious local import cycles.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CODE_EXTS = {".py", ".dart", ".ts", ".tsx", ".js", ".jsx"}
IGNORE_DIRS = {".git", ".dart_tool", "build", "dist", "node_modules", "__pycache__", ".venv", "venv"}

DART_SYMBOL_RE = re.compile(
    r"^\s*(?:abstract\s+|sealed\s+|base\s+|final\s+|interface\s+|mixin\s+)?class\s+([A-Za-z_]\w*)|"
    r"^\s*enum\s+([A-Za-z_]\w*)|"
    r"^\s*extension\s+([A-Za-z_]\w*)|"
    r"^\s*typedef\s+([A-Za-z_]\w*)|"
    r"^\s*(?:Future<[^>]+>|Stream<[^>]+>|Widget|void|bool|int|double|String|dynamic|[A-Z][A-Za-z0-9_<>?]*)\s+([a-z_]\w*)\s*\(",
    re.MULTILINE,
)

TS_SYMBOL_RE = re.compile(
    r"^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)|"
    r"^\s*(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)|"
    r"^\s*(?:export\s+)?(?:interface|type|enum)\s+([A-Za-z_$][\w$]*)|"
    r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>",
    re.MULTILINE,
)

IMPORT_RE = re.compile(
    r"""^\s*(?:import\s+[^'"]*['"]([^'"]+)['"]|from\s+(\.[A-Za-z0-9_.]*)\s+import\b)""",
    re.MULTILINE,
)


def _iter_source_files(targets: list[Path]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        if target.is_file() and target.suffix.lower() in CODE_EXTS:
            files.append(target)
        elif target.is_dir():
            for root, dirnames, filenames in os.walk(target):
                dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS and not d.startswith("."))
                for fn in sorted(filenames):
                    p = Path(root) / fn
                    if p.suffix.lower() in CODE_EXTS:
                        files.append(p)
    return sorted({p.resolve() for p in files})


def _extract_symbols(path: Path, text: str) -> list[str]:
    ext = path.suffix.lower()
    if ext == ".py":
        try:
            tree = ast.parse(text)
            return sorted(
                {
                    node.name
                    for node in tree.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                }
            )
        except SyntaxError:
            pass
    pattern = DART_SYMBOL_RE if ext == ".dart" else TS_SYMBOL_RE
    found = set()
    for match in pattern.finditer(text):
        for group in match.groups():
            if group and group not in {"if", "for", "while", "switch", "catch", "return"}:
                found.add(group)
    return sorted(found)


def _analyze_file(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    non_blank = sum(1 for ln in lines if ln.strip())
    return {
        "path": str(path),
        "name": path.name,
        "total_lines": len(lines),
        "non_blank_lines": non_blank,
        "sha256": hashlib.sha256(raw).hexdigest()[:16],
        "symbols": _extract_symbols(path, text),
    }


def _resolve_import_target(src: Path, spec: str, by_norm: dict[str, Path]) -> str | None:
    if spec.startswith(".") and "/" not in spec and "\\" not in spec:
        # Python dot-relative module syntax: .core -> src.parent/core, ..pkg.mod -> src.parent.parent/pkg/mod
        dots = len(spec) - len(spec.lstrip("."))
        base_dir = src.parent
        for _ in range(dots - 1):
            base_dir = base_dir.parent
        mod_rel = spec[dots:].replace(".", "/")
        cand_base = (base_dir / mod_rel).resolve() if mod_rel else base_dir.resolve()
    elif spec.startswith(".") or (src.suffix.lower() == ".dart" and not spec.startswith(("package:", "dart:"))):
        cand_base = (src.parent / spec).resolve()
    else:
        return None

    for suffix in ("", ".py", ".dart", ".ts", ".tsx", ".js", ".jsx"):
        cand = Path(str(cand_base) + suffix)
        c_key = str(cand)
        if c_key in by_norm:
            return c_key
    for idx_name in ("__init__.py", "index.ts", "index.tsx", "index.js"):
        c_key = str((cand_base / idx_name).resolve())
        if c_key in by_norm:
            return c_key
    return None


def _find_import_cycles(files: list[Path]) -> list[list[str]]:
    by_norm = {str(p.resolve()): p.resolve() for p in files}
    adj: dict[str, set[str]] = {k: set() for k in by_norm}
    for key, src in by_norm.items():
        text = src.read_text(encoding="utf-8-sig", errors="replace")
        for m in IMPORT_RE.finditer(text):
            spec = m.group(1) or m.group(2) or ""
            target = _resolve_import_target(src, spec, by_norm)
            if target and target != key:
                adj[key].add(target)

    cycles: list[list[str]] = []
    state: dict[str, int] = {}
    stack: list[str] = []

    def dfs(node: str) -> None:
        state[node] = 1
        stack.append(node)
        for nxt in sorted(adj.get(node, ())):
            st = state.get(nxt, 0)
            if st == 1:
                idx = stack.index(nxt)
                cycles.append([Path(p).name for p in stack[idx:] + [nxt]])
            elif st == 0:
                dfs(nxt)
        stack.pop()
        state[node] = 2

    for node in sorted(adj):
        if state.get(node, 0) == 0:
            dfs(node)
    return cycles


def cmd_baseline(targets: list[str], output: str) -> int:
    files = _iter_source_files([Path(t) for t in targets])
    if not files:
        print("ERROR: No source files matched targets.", file=sys.stderr)
        return 1
    entries = [_analyze_file(f) for f in files]
    all_symbols = sorted({sym for e in entries for sym in e["symbols"]})
    payload = {
        "files": entries,
        "total_lines": sum(e["total_lines"] for e in entries),
        "total_non_blank": sum(e["non_blank_lines"] for e in entries),
        "symbols": all_symbols,
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Baseline written: {output} ({len(entries)} files, {payload['total_lines']} lines, {len(all_symbols)} symbols)")
    return 0


def cmd_verify(baseline_path: str, targets: list[str], max_lines: int, ui_max_lines: int, min_retention: float) -> int:
    baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8-sig"))
    files = _iter_source_files([Path(t) for t in targets])
    if not files:
        print("ERROR: No target files matched.", file=sys.stderr)
        return 1

    entries = [_analyze_file(f) for f in files]
    orig_non_blank = max(1, int(baseline["total_non_blank"]))
    new_non_blank = sum(e["non_blank_lines"] for e in entries)
    retention = new_non_blank / orig_non_blank

    orig_symbols = set(baseline.get("symbols", []))
    new_symbols = {sym for e in entries for sym in e["symbols"]}
    # Fallback plain-identifier scan inside target texts for symbols rewritten into methods/lambdas
    joined_text = "\n".join(Path(e["path"]).read_text(encoding="utf-8-sig", errors="replace") for e in entries)
    missing_symbols = sorted(
        sym for sym in orig_symbols if sym not in new_symbols and not re.search(rf"\b{re.escape(sym)}\b", joined_text)
    )

    oversized: list[dict[str, Any]] = []
    for e in entries:
        low = e["name"].lower()
        cap = ui_max_lines if any(k in low for k in ("icon", "token", "atom", "svg")) else max_lines
        if e["total_lines"] > cap:
            oversized.append({"file": e["path"], "lines": e["total_lines"], "limit": cap})

    cycles = _find_import_cycles(files)
    passed = not missing_symbols and not oversized and not cycles and retention >= min_retention

    report = {
        "status": "PASS" if passed else "FAIL",
        "baseline_non_blank_lines": baseline["total_non_blank"],
        "resulting_non_blank_lines": new_non_blank,
        "retention_ratio": round(retention, 3),
        "min_retention_required": min_retention,
        "original_symbol_count": len(orig_symbols),
        "missing_symbols": missing_symbols,
        "oversized_files": oversized,
        "import_cycles": cycles,
        "resulting_file_count": len(entries),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Lossless modularization conservation & size auditor.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_base = sub.add_parser("baseline", help="Capture pre-refactor symbol & line baseline")
    p_base.add_argument("--out", required=True, help="Output JSON snapshot path")
    p_base.add_argument("targets", nargs="+", help="Source files or directories")

    p_ver = sub.add_parser("verify", help="Verify refactored modules against baseline")
    p_ver.add_argument("--baseline", required=True, help="Baseline JSON path")
    p_ver.add_argument("--max-lines", type=int, default=400, help="Max lines per standard source file")
    p_ver.add_argument("--ui-max-lines", type=int, default=200, help="Max lines for icon/token/atom files")
    p_ver.add_argument("--min-retention", type=float, default=0.90, help="Min non-blank line conservation ratio")
    p_ver.add_argument("targets", nargs="+", help="Refactored target files or directories")

    args = parser.parse_args()
    if args.cmd == "baseline":
        return cmd_baseline(args.targets, args.out)
    return cmd_verify(args.baseline, args.targets, args.max_lines, args.ui_max_lines, args.min_retention)


if __name__ == "__main__":
    raise SystemExit(main())
