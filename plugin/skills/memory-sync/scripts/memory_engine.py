"""SQLite WAL + FTS5 (BM25) persistent agent memory engine and CLI."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import memory_indexer  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SHARD_LINE_LIMIT = 120
INDEX_LINE_LIMIT = 60
_SCHEMA_SQL = (
    "CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, mtime_ns INTEGER NOT NULL, size INTEGER NOT NULL);"
    "CREATE TABLE IF NOT EXISTS symbols (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, kind TEXT NOT NULL, "
    "file TEXT NOT NULL, start_line INTEGER NOT NULL, end_line INTEGER NOT NULL, signature TEXT NOT NULL);"
    "CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file);"
    "CREATE TABLE IF NOT EXISTS docs_chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, heading TEXT NOT NULL, "
    "start_line INTEGER NOT NULL, content TEXT NOT NULL);CREATE INDEX IF NOT EXISTS idx_chunks_source ON docs_chunks(source);"
)


def _mem_paths(workspace: str | Path) -> tuple[Path, Path, Path, Path, Path]:
    ws = Path(workspace).resolve()
    mem_dir = ws / ".agents" / "memory"
    return ws, mem_dir, mem_dir / "memory.db", mem_dir / "state.json", mem_dir / "MEMORY_INDEX.md"


@contextmanager
def _connect(db_path: Path):
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _has_fts5(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='docs_fts'").fetchone() is not None


def init_memory(workspace: str | Path) -> dict:
    """Initialize .agents/memory/, .gitignore, MEMORY_INDEX.md, and SQLite tables."""
    _, mem_dir, db_path, _, index_path = _mem_paths(workspace)
    mem_dir.mkdir(parents=True, exist_ok=True)
    gi = mem_dir / ".gitignore"
    existing = gi.read_text(encoding="utf-8", errors="replace") if gi.exists() else ""
    missing = [ln for ln in ("memory.db*", "state.json") if ln not in existing.splitlines()]
    if missing:
        gi.write_text(existing + ("" if not existing or existing.endswith("\n") else "\n") + "\n".join(missing) + "\n", encoding="utf-8")
    if not index_path.exists():
        index_path.write_text("# Memory Index\n\n- Status: initialized\n- Active Task: (none)\n- Shards: `decisions`, `solved_bugs`, `architecture`, `active_task`\n", encoding="utf-8")
    fts5_ok = False
    with _connect(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)
        try:
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(source, heading, start_line UNINDEXED, content, tokenize='unicode61')")
            fts5_ok = True
        except sqlite3.OperationalError:
            fts5_ok = False
        conn.commit()
    return {"memory_dir": str(mem_dir), "db_path": str(db_path), "fts5": fts5_ok, "initialized": True}


def _delete_file_rows(conn: sqlite3.Connection, rel_path: str, has_fts: bool) -> None:
    for tbl, col in (("files", "path"), ("symbols", "file"), ("docs_chunks", "source")):
        conn.execute(f"DELETE FROM {tbl} WHERE {col} = ?", (rel_path,))
    if has_fts:
        conn.execute("DELETE FROM docs_fts WHERE source = ?", (rel_path,))


def index_workspace(workspace: str | Path, paths: list[str] | None = None) -> dict:
    """Incrementally index workspace files (or specified paths) into SQLite."""
    t0 = time.perf_counter()
    ws, _, db_path, _, _ = _mem_paths(workspace)
    if not db_path.exists():
        init_memory(ws)
    found, missing = memory_indexer.scan_files(ws, paths)
    files_indexed = symbols_indexed = fts_chunks = 0

    with _connect(db_path) as conn:
        has_fts = _has_fts5(conn)
        existing = (
            {r["path"]: (r["mtime_ns"], r["size"]) for r in conn.execute("SELECT path, mtime_ns, size FROM files")}
            if paths is None else {}
        )
        for dead in (set(existing) - {item[0] for item in found}) if paths is None else missing:
            _delete_file_rows(conn, dead, has_fts)

        for rel, abs_path, mtime_ns, size in found:
            if paths is None and existing.get(rel) == (mtime_ns, size):
                continue
            syms, chunks = memory_indexer.extract_file(rel, abs_path.read_text(encoding="utf-8", errors="replace"))
            _delete_file_rows(conn, rel, has_fts)
            conn.execute("INSERT INTO files(path, mtime_ns, size) VALUES (?, ?, ?)", (rel, mtime_ns, size))
            if syms:
                conn.executemany(
                    "INSERT INTO symbols(name, kind, file, start_line, end_line, signature) VALUES (?, ?, ?, ?, ?, ?)",
                    [(s["name"], s["kind"], s["file"], s["start_line"], s["end_line"], s["signature"]) for s in syms],
                )
            if chunks:
                rows = [(c["source"], c["heading"], c["start_line"], c["content"]) for c in chunks]
                conn.executemany("INSERT INTO docs_chunks(source, heading, start_line, content) VALUES (?, ?, ?, ?)", rows)
                if has_fts:
                    conn.executemany("INSERT INTO docs_fts(source, heading, start_line, content) VALUES (?, ?, ?, ?)", rows)
            files_indexed += 1
            symbols_indexed += len(syms)
            fts_chunks += len(chunks)
        conn.commit()
    return {
        "files_indexed": files_indexed, "symbols_indexed": symbols_indexed,
        "fts_chunks": fts_chunks, "elapsed_ms": int(round((time.perf_counter() - t0) * 1000)),
    }


def _ensure_indexed(workspace: str | Path, table: str) -> Path:
    ws, _, db_path, _, _ = _mem_paths(workspace)
    needs = not db_path.exists()
    if not needs:
        with _connect(db_path) as conn:
            needs = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    if needs:
        index_workspace(ws)
    return db_path


def lookup_symbol(workspace: str | Path, query: str, limit: int = 15) -> list[dict]:
    """Lookup indexed symbols by name (exact/prefix/substring ranked)."""
    db_path, q = _ensure_indexed(workspace, "symbols"), query.strip()
    sql = "SELECT name, kind, file, start_line, end_line, signature FROM symbols "
    with _connect(db_path) as conn:
        if not q:
            rows = conn.execute(sql + "ORDER BY file, start_line LIMIT ?", (limit,)).fetchall()
        else:
            rows = conn.execute(
                sql + "WHERE lower(name) LIKE lower(?) ORDER BY CASE WHEN lower(name)=lower(?) THEN 0 "
                "WHEN lower(name) LIKE lower(?) THEN 1 ELSE 2 END, length(name), file, start_line LIMIT ?",
                (f"%{q}%", q, f"{q}%", limit),
            ).fetchall()
    return [dict(r) for r in rows]


def _make_snippet(content: str, tokens: list[str], max_len: int = 260) -> str:
    flat = re.sub(r"\s+", " ", content).strip()
    if len(flat) <= max_len:
        return flat
    lower = flat.lower()
    pos = min((lower.find(t.lower()) for t in tokens if t.lower() in lower), default=0)
    start = max(0, pos - 60)
    snip = ("..." if start > 0 else "") + flat[start : start + max_len - 3].strip()
    return (snip[: max_len - 3].rstrip() + "...") if start + max_len - 3 < len(flat) else snip[:max_len]


def _chunk_hit(row: sqlite3.Row, tokens: list[str], score: float) -> dict:
    return {"source": row["source"], "heading": row["heading"], "start_line": int(row["start_line"]), "snippet": _make_snippet(row["content"], tokens), "score": score}


def search_memory(workspace: str | Path, query: str, limit: int = 8) -> list[dict]:
    """BM25 search via FTS5 with punctuation sanitization and LIKE fallback."""
    tokens = re.findall(r"\w+", query, flags=re.UNICODE)
    if not tokens:
        return []
    db_path = _ensure_indexed(workspace, "docs_chunks")
    with _connect(db_path) as conn:
        if _has_fts5(conn):
            for joiner in (" ", " OR "):
                if joiner == " OR " and len(tokens) <= 1:
                    continue
                try:
                    rows = conn.execute(
                        "SELECT source, heading, start_line, content, bm25(docs_fts) AS rank "
                        "FROM docs_fts WHERE docs_fts MATCH ? ORDER BY rank ASC LIMIT ?",
                        (joiner.join(f'"{t}"' for t in tokens), limit),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
                if rows:
                    return [_chunk_hit(r, tokens, round(-float(r["rank"]), 4)) for r in rows]
        where = " OR ".join("(lower(heading) LIKE ? OR lower(content) LIKE ?)" for _ in tokens)
        params: list[object] = [p for tok in tokens for p in (f"%{tok.lower()}%", f"%{tok.lower()}%")] + [limit]
        rows = conn.execute(f"SELECT source, heading, start_line, content FROM docs_chunks WHERE {where} LIMIT ?", params).fetchall()
        return [_chunk_hit(r, tokens, 1.0) for r in rows]


def _active_shards(mem_dir: Path) -> list[Path]:
    return sorted(p for p in mem_dir.glob("*.md") if p.name != "MEMORY_INDEX.md" and not p.name.startswith("archive_"))


def _git_info(ws: Path) -> dict[str, str]:
    info: dict[str, str] = {}
    for key, args in (("branch", ["rev-parse", "--abbrev-ref", "HEAD"]), ("commit", ["rev-parse", "--short", "HEAD"])):
        try:
            proc = subprocess.run(["git", *args], cwd=str(ws), capture_output=True, text=True, timeout=3)
            if proc.returncode == 0 and proc.stdout.strip():
                info[key] = proc.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return info


def _roll_shard(shard_path: Path, archive_path: Path, slug: str) -> None:
    lines = shard_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) <= SHARD_LINE_LIMIT:
        return
    first_sec = next((i for i, ln in enumerate(lines) if ln.startswith("## ")), len(lines))
    header = lines[:first_sec] or [f"# {slug.replace('_', ' ').title()}", ""]
    sections: list[list[str]] = []
    for ln in lines[first_sec:]:
        (sections.append([ln]) if (ln.startswith("## ") or not sections) else sections[-1].append(ln))
    rolled: list[list[str]] = []
    while len(sections) > 1 and len(header) + sum(len(s) for s in sections) > SHARD_LINE_LIMIT:
        rolled.append(sections.pop(0))
    if rolled:
        arch = archive_path.read_text(encoding="utf-8", errors="replace") if archive_path.exists() else f"# Archive: {slug}\n\n"
        body = "\n".join("\n".join(sec).rstrip() for sec in rolled) + "\n"
        archive_path.write_text(arch + ("" if arch.endswith("\n") else "\n") + body, encoding="utf-8")
    kept = (header + [ln for sec in sections for ln in sec])[:SHARD_LINE_LIMIT]
    shard_path.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")


def _write_memory_index(mem_dir: Path, db_path: Path, state: dict) -> Path:
    index_path = mem_dir / "MEMORY_INDEX.md"
    with _connect(db_path) as conn:
        sym_cnt = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        chk_cnt = conn.execute("SELECT COUNT(*) FROM docs_chunks").fetchone()[0]
    shards = _active_shards(mem_dir)
    lines = [
        "# Memory Index", "", f"- Updated: {state.get('updated_at', '')}",
        f"- Git: {state.get('branch', '')} {state.get('commit', '')}".strip(),
        f"- Status: {state.get('status', '') or 'active'}",
        f"- Active Task: {state.get('active_task', '') or '(none)'}",
        f"- Verified Tests: {state.get('verified_tests', '') or '(none)'}",
        f"- Index: {sym_cnt} symbols, {chk_cnt} chunks", "", "## Blockers",
        *[f"- {b}" for b in (state.get("blockers") or ["(none)"])[:8]], "", "## Next Steps",
        *[f"- {n}" for n in (state.get("next_steps") or ["(none)"])[:8]], "", "## Shards",
        *([f"- [{sp.name}](./{sp.name}) ({len(sp.read_text(encoding='utf-8', errors='replace').splitlines())} lines)" for sp in shards] or ["- (no shards yet)"]),
    ]
    index_path.write_text("\n".join(lines[:INDEX_LINE_LIMIT]).rstrip() + "\n", encoding="utf-8")
    return index_path


def checkpoint_state(
    workspace: str | Path, *, active_task: str = "", status: str = "", verified_tests: str = "",
    blockers: list[str] | None = None, next_steps: list[str] | None = None,
    note_shard: str = "", note_title: str = "", note_body: str = "", tags: list[str] | None = None,
) -> dict:
    """Update state.json, MEMORY_INDEX.md, optional bounded shard, and re-index."""
    ws, mem_dir, db_path, state_path, _ = _mem_paths(workspace)
    init_memory(ws)
    state: dict = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    state["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state.update(_git_info(ws))
    for k, val in (("active_task", active_task), ("status", status), ("verified_tests", verified_tests)):
        if val:
            state[k] = val
    if blockers is not None:
        state["blockers"] = blockers
    if next_steps is not None:
        state["next_steps"] = next_steps
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    reindexed: list[str] = []
    shard_path_str = ""
    if note_shard and (note_title or note_body):
        slug = re.sub(r"[^a-z0-9_]+", "_", note_shard.removesuffix(".md").lower()).strip("_") or "active_task"
        shard_path, archive_path = mem_dir / f"{slug}.md", mem_dir / f"archive_{slug}.md"
        prev = shard_path.read_text(encoding="utf-8", errors="replace") if shard_path.exists() else f"# {slug.replace('_', ' ').title()}\n\n"
        tag_line = f"Tags: {', '.join(tags)}\n" if tags else ""
        entry = f"## {state['updated_at']} — {note_title or 'Note'}\n{tag_line}{note_body.strip()}\n\n"
        shard_path.write_text(prev + ("" if prev.endswith("\n") else "\n") + entry, encoding="utf-8")
        _roll_shard(shard_path, archive_path, slug)
        shard_path_str = str(shard_path)
        reindexed.extend(p.relative_to(ws).as_posix() for p in (shard_path, archive_path) if p.exists())
    index_path = _write_memory_index(mem_dir, db_path, state)
    reindexed.append(index_path.relative_to(ws).as_posix())
    return {"state_path": str(state_path), "index_path": str(index_path), "shard_path": shard_path_str, "state": state, "reindexed": index_workspace(ws, paths=reindexed)}


def hydrate_brief(workspace: str | Path, max_chars: int = 650) -> str:
    """Return compact <= max_chars L2 Memory summary, or '' if uninitialized."""
    _, mem_dir, db_path, state_path, _ = _mem_paths(workspace)
    if not mem_dir.is_dir():
        return ""
    state: dict = json.loads(state_path.read_text(encoding="utf-8", errors="replace")) if state_path.exists() else {}
    sym_cnt = 0
    if db_path.exists():
        with _connect(db_path) as conn:
            sym_cnt = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
    shards = [p.stem for p in _active_shards(mem_dir)]
    brief = "\n".join([
        f"L2 Memory ({state.get('branch', '-') or '-'}@{state.get('commit', '-') or '-'})",
        f"Task: {state.get('active_task') or '(none)'} [{state.get('status') or 'active'}]",
        f"Tests: {state.get('verified_tests') or '(none)'}",
        f"Blockers: {', '.join(state.get('blockers') or []) or 'none'}",
        f"Next: {', '.join(state.get('next_steps') or []) or 'none'}",
        f"Symbols: {sym_cnt} | Shards: {', '.join(shards) or 'none'}",
    ])
    return brief if len(brief) <= max_chars else brief[: max(0, max_chars - 3)].rstrip() + "..."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Memory Engine CLI")
    parser.add_argument("--workspace", default=".", help="Workspace root directory")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("index").add_argument("--paths", nargs="+", default=None)
    for name, dlim in (("symbol", 15), ("search", 8)):
        p = sub.add_parser(name)
        p.add_argument("query", nargs="+")
        p.add_argument("--limit", type=int, default=dlim)
    p_chk = sub.add_parser("checkpoint")
    for flag in ("--task", "--status", "--tests", "--shard", "--title", "--body"):
        p_chk.add_argument(flag, default="")
    p_chk.add_argument("--blocker", action="append", default=None)
    p_chk.add_argument("--next", dest="next_steps", action="append", default=None)
    p_chk.add_argument("--tag", action="append", default=None)
    sub.add_parser("hydrate").add_argument("--max-chars", type=int, default=650)
    args = parser.parse_args(argv)
    if args.cmd == "hydrate":
        print(hydrate_brief(args.workspace, max_chars=args.max_chars))
        return 0
    dispatch = {
        "init": lambda: init_memory(args.workspace),
        "index": lambda: index_workspace(args.workspace, paths=args.paths),
        "symbol": lambda: lookup_symbol(args.workspace, " ".join(args.query), limit=args.limit),
        "search": lambda: search_memory(args.workspace, " ".join(args.query), limit=args.limit),
        "checkpoint": lambda: checkpoint_state(
            args.workspace, active_task=args.task, status=args.status, verified_tests=args.tests,
            blockers=args.blocker, next_steps=args.next_steps, note_shard=args.shard,
            note_title=args.title, note_body=args.body, tags=args.tag,
        ),
    }
    print(json.dumps(dispatch[args.cmd](), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
