#!/usr/bin/env python3
"""Verify README / Markdown truthfulness: local links, heading anchors & placeholder traps."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
PLACEHOLDER_RE = re.compile(r"(?:\bTODO\b|\bTBD\b|<your[-_ ][a-z0-9_-]+>|<insert\s+[^>]+>)", re.IGNORECASE)


def _slugify(heading: str) -> str:
    clean = re.sub(r"[`*_~]", "", heading.strip().lower())
    clean = re.sub(r"[^\w\s-]", "", clean, flags=re.UNICODE)
    return re.sub(r"\s+", "-", clean).strip("-")


def verify_markdown(md_path: Path, repo_root: Path | None = None) -> dict[str, Any]:
    md_path = md_path.resolve()
    root = repo_root.resolve() if repo_root else md_path.parent
    text = md_path.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()

    anchors: set[str] = set()
    in_fence = False
    for ln in lines:
        if ln.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            m = HEADING_RE.match(ln)
            if m:
                anchors.add(_slugify(m.group(2)))

    broken_links: list[dict[str, Any]] = []
    placeholders: list[dict[str, Any]] = []
    in_fence = False

    for idx, ln in enumerate(lines, 1):
        if ln.strip().startswith("```"):
            in_fence = not in_fence
            continue
        for m in PLACEHOLDER_RE.finditer(ln):
            if not in_fence:
                placeholders.append({"line": idx, "match": m.group(0)})
        if in_fence:
            continue
        for lm in LINK_RE.finditer(ln):
            target = lm.group(1).strip().strip("<>")
            if not target or target.startswith(("http://", "https://", "mailto:", "tel:", "file://", "customization://", "conversation://")):
                continue
            if target.startswith("#"):
                slug = unquote(target[1:]).lower()
                if slug not in anchors:
                    broken_links.append({"line": idx, "target": target, "reason": "missing_anchor"})
                continue
            rel_part = unquote(target.split("#", 1)[0])
            resolved = (md_path.parent / rel_part).resolve()
            if not resolved.exists() and not (root / rel_part).resolve().exists():
                broken_links.append({"line": idx, "target": target, "reason": "missing_path"})

    passed = not broken_links and not placeholders
    return {
        "status": "PASS" if passed else "FAIL",
        "file": str(md_path),
        "lines": len(lines),
        "anchors_indexed": len(anchors),
        "broken_links": broken_links,
        "placeholders": placeholders,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify README local links, anchors, and placeholders.")
    parser.add_argument("markdown", nargs="?", default="README.md", help="Markdown file to audit")
    parser.add_argument("--repo-root", default="", help="Repository root for root-relative fallback")
    args = parser.parse_args()

    md = Path(args.markdown)
    if not md.exists():
        print(json.dumps({"status": "FAIL", "error": f"File not found: {md}"}))
        return 1
    res = verify_markdown(md, Path(args.repo_root) if args.repo_root else None)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0 if res["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
