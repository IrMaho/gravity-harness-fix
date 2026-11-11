#!/usr/bin/env python3
"""Verify Figma-to-Production UI hygiene: file line caps, SVG asset discipline, icon centralization."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UI_EXTS = {".dart", ".ts", ".tsx", ".js", ".jsx"}
IGNORE_DIRS = {".git", ".dart_tool", "build", "dist", "node_modules", "__pycache__", ".next"}

INLINE_SVG_RE = re.compile(r"<svg\b", re.IGNORECASE)
DART_PATH_RE = re.compile(r"\b(?:CustomPainter|Path\s*\(\s*\))\b")
DART_DRAW_RE = re.compile(r"\.(?:moveTo|lineTo|cubicTo|quadraticBezierTo)\s*\(")
BROWSER_PREVIEW_RE = re.compile(r"browser_preview|openBrowserPreview", re.IGNORECASE)


def _is_icon_module(rel: str) -> bool:
    low = rel.replace("\\", "/").lower()
    return any(tok in low for tok in ("/icons/", "/svg/", "/tokens/", "/atoms/", "app_icon", "icon_registry", "design_token"))


def _is_chart_or_canvas(rel: str) -> bool:
    low = rel.replace("\\", "/").lower()
    return any(tok in low for tok in ("chart", "canvas", "graph", "paint_canvas", "signature"))


def scan_ui(
    root: Path,
    *,
    max_lines: int = 400,
    icon_max_lines: int = 200,
    strict_no_inline_svg: bool = True,
) -> dict[str, Any]:
    oversized: list[dict[str, Any]] = []
    inline_svg_hits: list[dict[str, Any]] = []
    manual_path_hits: list[dict[str, Any]] = []
    browser_hits: list[dict[str, Any]] = []
    duplicate_svgs: dict[str, list[str]] = {}
    scanned_files = 0

    for cur, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            full = Path(cur) / fn
            rel = str(full.relative_to(root)).replace("\\", "/")
            ext = full.suffix.lower()

            if ext == ".svg":
                duplicate_svgs.setdefault(fn.lower(), []).append(rel)
                continue
            if ext not in UI_EXTS:
                continue

            scanned_files += 1
            text = full.read_text(encoding="utf-8-sig", errors="replace")
            lines = text.splitlines()
            cap = icon_max_lines if _is_icon_module(rel) else max_lines
            if len(lines) > cap:
                oversized.append({"file": rel, "lines": len(lines), "limit": cap})

            if strict_no_inline_svg and not _is_icon_module(rel) and INLINE_SVG_RE.search(text):
                inline_svg_hits.append({"file": rel, "issue": "Inline <svg> outside centralized icon/svg module"})

            if ext == ".dart" and not _is_chart_or_canvas(rel):
                if DART_PATH_RE.search(text) and DART_DRAW_RE.search(text):
                    manual_path_hits.append({"file": rel, "issue": "Manual Path()/CustomPainter geometry outside chart/canvas"})

            if BROWSER_PREVIEW_RE.search(text):
                browser_hits.append({"file": rel, "issue": "Prohibited browser preview hook in UI code"})

    dups = {name: paths for name, paths in sorted(duplicate_svgs.items()) if len(paths) > 1}
    passed = not oversized and not inline_svg_hits and not manual_path_hits and not browser_hits and not dups

    return {
        "status": "PASS" if passed else "FAIL",
        "scanned_ui_files": scanned_files,
        "oversized_files": oversized,
        "inline_svg_violations": inline_svg_hits,
        "manual_path_violations": manual_path_hits,
        "browser_preview_hits": browser_hits,
        "duplicate_svg_assets": dups,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Figma-to-Production UI architecture and SVG hygiene.")
    parser.add_argument("root", nargs="?", default=".", help="Project or src/lib root directory")
    parser.add_argument("--max-lines", type=int, default=400, help="Max lines per standard UI file")
    parser.add_argument("--icon-max-lines", type=int, default=200, help="Max lines per icon/token/atom file")
    parser.add_argument("--allow-inline-svg", action="store_true", help="Disable inline <svg> violation check")
    args = parser.parse_args()

    res = scan_ui(
        Path(args.root).resolve(),
        max_lines=args.max_lines,
        icon_max_lines=args.icon_max_lines,
        strict_no_inline_svg=not args.allow_inline_svg,
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0 if res["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
