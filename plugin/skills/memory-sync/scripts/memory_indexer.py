"""Incremental file scanner, AST/regex symbol extractor, and Markdown chunker."""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

SUPPORTED_EXTS = {".py", ".dart", ".ts", ".tsx", ".js", ".jsx", ".md"}
IGNORED_DIRS = {".git", "node_modules", "build", ".dart_tool", "__pycache__", ".venv", "logs", "prompt"}

_DART_SKIP = {"if", "for", "while", "switch", "catch", "return", "else", "try", "assert"}
_DART_TYPE_RE = re.compile(
    r"^\s*(?:abstract\s+|base\s+|final\s+|sealed\s+|interface\s+|mixin\s+)*"
    r"(class|mixin|enum|extension|typedef)\s+([A-Za-z_]\w*)"
)
_DART_FN_RE = re.compile(
    r"^\s*(?:@[\w.()]+\s+)*(?:static\s+|external\s+|factory\s+|const\s+|async\s+)*"
    r"(?:[\w<>,?\[\]\s]+?\s+)?([A-Za-z_]\w*)\s*\([^;{]*\)\s*(?:async\s*)?(?:\{|=>)"
)
_TS_TYPE_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?(class|interface|type|enum)\s+([A-Za-z_$][\w$]*)"
)
_TS_FN_RE = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*[<(]")
_TS_ARROW_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*"
    r"(?::[^=]+)?=\s*(?:async\s+)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)"
)
_TS_METHOD_RE = re.compile(
    r"^\s*(?:public\s+|private\s+|protected\s+|static\s+|readonly\s+|async\s+)*"
    r"([A-Za-z_$][\w$]*)\s*\([^;]*\)\s*(?::\s*[^\{]+)?\{"
)
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def _sym(name: str, kind: str, file: str, start: int, end: int, sig: str) -> dict:
    return {"name": name, "kind": kind, "file": file, "start_line": start, "end_line": end, "signature": sig[:140]}


def scan_files(
    workspace: Path, paths: list[str] | None = None
) -> tuple[list[tuple[str, Path, int, int]], list[str]]:
    """Scan workspace (or targeted paths) for supported files."""
    ws_root = workspace.resolve()
    found: list[tuple[str, Path, int, int]] = []
    missing: list[str] = []

    if paths is not None:
        seen: set[str] = set()
        for raw in paths:
            candidate = Path(raw)
            abs_path = (candidate if candidate.is_absolute() else ws_root / candidate).resolve()
            try:
                rel = abs_path.relative_to(ws_root).as_posix()
            except ValueError:
                continue
            if rel in seen:
                continue
            seen.add(rel)
            if not abs_path.is_file():
                missing.append(rel)
                continue
            if abs_path.suffix.lower() in SUPPORTED_EXTS:
                st = abs_path.stat()
                found.append((rel, abs_path, st.st_mtime_ns, st.st_size))
        return found, missing

    for root, dirs, files in os.walk(ws_root):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS)
        root_path = Path(root)
        for fname in sorted(files):
            abs_path = root_path / fname
            if abs_path.suffix.lower() not in SUPPORTED_EXTS:
                continue
            try:
                rel = abs_path.relative_to(ws_root).as_posix()
                st = abs_path.stat()
            except OSError:
                continue
            found.append((rel, abs_path, st.st_mtime_ns, st.st_size))
    return found, missing


def _find_block_end(lines: list[str], start_idx: int) -> int:
    """Estimate 1-indexed end line for brace-delimited or arrow declarations."""
    depth = 0
    seen_brace = False
    for idx in range(start_idx, min(len(lines), start_idx + 400)):
        line = lines[idx]
        for ch in line:
            if ch == "{":
                depth += 1
                seen_brace = True
            elif ch == "}" and seen_brace:
                depth -= 1
                if depth <= 0:
                    return idx + 1
        if not seen_brace and (";" in line or ("=>" in line and line.rstrip().endswith(";"))):
            return idx + 1
    return start_idx + 1


def _extract_python_symbols(rel_path: str, text: str, lines: list[str]) -> list[dict]:
    symbols: list[dict] = []
    try:
        tree = ast.parse(text, filename=rel_path)
    except SyntaxError:
        pat = re.compile(r"^\s*(?:async\s+)?(def|class)\s+([A-Za-z_]\w*)")
        for idx, line in enumerate(lines):
            m = pat.match(line)
            if m:
                kind = "class" if m.group(1) == "class" else "function"
                symbols.append(_sym(m.group(2), kind, rel_path, idx + 1, idx + 1, line.strip()))
        return symbols

    def visit(node: ast.AST, prefix: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                sig = lines[child.lineno - 1].strip() if child.lineno <= len(lines) else f"class {child.name}"
                end = getattr(child, "end_lineno", child.lineno) or child.lineno
                symbols.append(_sym(f"{prefix}{child.name}", "class", rel_path, child.lineno, end, sig))
                visit(child, f"{prefix}{child.name}.")
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "method" if prefix else "function"
                sig = lines[child.lineno - 1].strip() if child.lineno <= len(lines) else f"def {child.name}"
                end = getattr(child, "end_lineno", child.lineno) or child.lineno
                symbols.append(_sym(f"{prefix}{child.name}", kind, rel_path, child.lineno, end, sig))

    visit(tree)
    return symbols


def _extract_dart_symbols(rel_path: str, lines: list[str]) -> list[dict]:
    symbols: list[dict] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "/*", "*", "import ", "export ", "part ")):
            continue
        m_type = _DART_TYPE_RE.match(line)
        if m_type:
            symbols.append(_sym(m_type.group(2), m_type.group(1), rel_path, idx + 1, _find_block_end(lines, idx), stripped))
            continue
        m_fn = _DART_FN_RE.match(line)
        if m_fn and m_fn.group(1) not in _DART_SKIP:
            symbols.append(_sym(m_fn.group(1), "function", rel_path, idx + 1, _find_block_end(lines, idx), stripped))
    return symbols


def _extract_ts_js_symbols(rel_path: str, lines: list[str]) -> list[dict]:
    symbols: list[dict] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "/*", "*", "import ", "return ")):
            continue
        for regex, default_kind in (
            (_TS_TYPE_RE, None),
            (_TS_FN_RE, "function"),
            (_TS_ARROW_RE, "function"),
            (_TS_METHOD_RE, "method"),
        ):
            m = regex.match(line)
            if not m:
                continue
            kind, name = (m.group(1), m.group(2)) if default_kind is None else (default_kind, m.group(1))
            if name not in _DART_SKIP:
                symbols.append(_sym(name, kind, rel_path, idx + 1, _find_block_end(lines, idx), stripped))
            break
    return symbols


def _extract_markdown_chunks(rel_path: str, lines: list[str]) -> list[dict]:
    chunks: list[dict] = []
    heading = Path(rel_path).name
    start_line = 1
    buf: list[str] = []
    in_fence = False

    for idx, line in enumerate(lines, start=1):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        if not in_fence:
            m = _MD_HEADING_RE.match(line)
            if m:
                text_block = "\n".join(buf).strip()
                if text_block:
                    chunks.append({"source": rel_path, "heading": heading, "start_line": start_line, "content": text_block})
                heading = m.group(2).strip()
                start_line = idx
                buf = [line]
                continue
        buf.append(line)

    tail = "\n".join(buf).strip()
    if tail:
        chunks.append({"source": rel_path, "heading": heading, "start_line": start_line, "content": tail})
    return chunks


def _extract_code_chunks(rel_path: str, lines: list[str], window: int = 80) -> list[dict]:
    chunks: list[dict] = []
    name = Path(rel_path).name
    for start in range(0, len(lines), window):
        block = "\n".join(lines[start : start + window]).strip()
        if block:
            chunks.append({"source": rel_path, "heading": f"{name}:L{start + 1}", "start_line": start + 1, "content": block})
    return chunks


def extract_file(rel_path: str, text: str) -> tuple[list[dict], list[dict]]:
    """Extract symbols and searchable FTS chunks for a single file."""
    if not text.strip():
        return [], []
    lines = text.splitlines()
    ext = Path(rel_path).suffix.lower()
    if ext == ".md":
        return [], _extract_markdown_chunks(rel_path, lines)
    if ext == ".py":
        symbols = _extract_python_symbols(rel_path, text, lines)
    elif ext == ".dart":
        symbols = _extract_dart_symbols(rel_path, lines)
    elif ext in {".ts", ".tsx", ".js", ".jsx"}:
        symbols = _extract_ts_js_symbols(rel_path, lines)
    else:
        symbols = []
    return symbols, _extract_code_chunks(rel_path, lines)
