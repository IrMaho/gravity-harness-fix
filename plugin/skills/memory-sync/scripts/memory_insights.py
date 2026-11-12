"""DeepSift-inspired memory helpers: TOON serialization, path priority, conflict checks, and decaying lessons."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

HALF_LIFE_SECONDS = 30.0 * 86400.0
MIN_DECAY_WEIGHT = 0.1
VALID_OUTCOMES = ("useful", "dead_end", "corrected")
LESSONS_SCHEMA_SQL = (
    "CREATE TABLE IF NOT EXISTS lessons ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, outcome TEXT NOT NULL, query TEXT NOT NULL, "
    "paths_json TEXT NOT NULL, correction TEXT NOT NULL, created_ts REAL NOT NULL);"
    "CREATE INDEX IF NOT EXISTS idx_lessons_ts ON lessons(created_ts DESC);"
)
_MODEL_PATH_MARKERS = ("model", "entity", "schema", "type", "types")
_TEST_PATH_MARKERS = (".test.", ".spec.", "_test.", "/tests/", "/test/", "/mocks/", "/fixtures/")
_STOP_WORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "over", "when",
    "only", "must", "should", "will", "have", "been", "use", "using", "not",
}


def path_priority(rel_path: str) -> float:
    """Rank production state/service modules higher and down-weight test files."""
    low = "/" + rel_path.replace("\\", "/").lower().lstrip("/")
    name = low.rsplit("/", 1)[-1]
    score = 1.0
    if any(k in low for k in ("store", "state", "bloc", "cubit", "provider", "reducer")):
        score += 3.0
    elif any(k in low for k in ("handler", "controller", "service", "repository", "engine", "mcp", "hook", "router")):
        score += 2.5
    elif any(k in low for k in _MODEL_PATH_MARKERS):
        score += 1.5
    if name.startswith("test_") or any(m in low for m in _TEST_PATH_MARKERS):
        score *= 0.3
    return round(score, 3)


def _toon_cell(val: object) -> str:
    if val is None:
        return ""
    s = json.dumps(val, ensure_ascii=False) if isinstance(val, (list, dict)) else str(val)
    s = s.replace("\r", " ").replace("\n", " ").strip()
    if any(ch in s for ch in (",", '"', ":")):
        return json.dumps(s, ensure_ascii=False)
    return s


def to_toon(rows: list[dict]) -> str:
    """Serialize uniform list of dicts in compact Token-Oriented Object Notation (TOON)."""
    if not rows:
        return "[0]{}:"
    cols: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for k in row.keys():
            if k not in seen:
                seen.add(k)
                cols.append(str(k))
    out = [f"[{len(rows)}]{{{','.join(cols)}}}:"]
    for row in rows:
        out.append("  " + ",".join(_toon_cell(row.get(c)) for c in cols))
    return "\n".join(out)


def _sig_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9_]{3,}", text.lower()) if t not in _STOP_WORDS}


def detect_shard_conflicts(shard_text: str, note_title: str, note_body: str, min_overlap: float = 0.30) -> list[dict]:
    """Detect existing notes in the same shard with high topic overlap (potential decision conflict)."""
    cand_tokens = _sig_tokens(f"{note_title} {note_body}")
    if len(cand_tokens) < 2 or "## " not in shard_text:
        return []
    sections: list[tuple[str, str]] = []
    cur_head = ""
    cur_body: list[str] = []
    for ln in shard_text.splitlines():
        if ln.startswith("## "):
            if cur_head:
                sections.append((cur_head, "\n".join(cur_body)))
            cur_head = ln[3:].strip()
            cur_body = []
        elif cur_head:
            cur_body.append(ln)
    if cur_head:
        sections.append((cur_head, "\n".join(cur_body)))

    hits: list[dict] = []
    for heading, body in sections[-20:]:
        title_part = heading.split("—", 1)[-1].strip()
        if note_title and title_part.lower() == note_title.strip().lower():
            continue
        sec_tokens = _sig_tokens(f"{title_part} {body}")
        if not sec_tokens:
            continue
        inter = len(cand_tokens & sec_tokens)
        denom = min(len(cand_tokens), len(sec_tokens))
        overlap_ratio = inter / denom if denom else 0.0
        if overlap_ratio >= min_overlap and inter >= 2:
            hits.append({"existing_heading": heading, "overlap": round(overlap_ratio, 3)})
    hits.sort(key=lambda h: h["overlap"], reverse=True)
    return hits[:3]


def _decay_weight(created_ts: float, now_ts: float) -> float:
    age = max(0.0, now_ts - float(created_ts))
    return 0.5 ** (age / HALF_LIFE_SECONDS)


def record_lesson(
    conn: sqlite3.Connection,
    mem_dir: Path,
    outcome: str,
    query: str,
    paths: list[str] | None = None,
    correction: str = "",
    created_ts: float | None = None,
) -> dict:
    """Persist an experiential lesson (useful/dead_end/corrected) and refresh LESSONS.md."""
    conn.executescript(LESSONS_SCHEMA_SQL)
    norm = outcome.strip().lower()
    if norm not in VALID_OUTCOMES:
        raise ValueError(f"outcome must be one of {VALID_OUTCOMES}")
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("query/topic is required")
    clean_paths = [str(p).strip() for p in (paths or []) if str(p).strip()][:12]
    ts = float(created_ts) if created_ts is not None else time.time()
    conn.execute(
        "INSERT INTO lessons(outcome, query, paths_json, correction, created_ts) VALUES (?, ?, ?, ?, ?)",
        (norm, clean_query, json.dumps(clean_paths, ensure_ascii=False), correction.strip(), ts),
    )
    conn.commit()
    lessons_path = write_lessons_md(conn, mem_dir, now_ts=ts)
    return {
        "outcome": norm,
        "query": clean_query,
        "paths": clean_paths,
        "correction": correction.strip(),
        "lessons_path": str(lessons_path),
    }


def query_lessons(
    conn: sqlite3.Connection,
    query: str = "",
    outcome: str = "",
    limit: int = 10,
    now_ts: float | None = None,
) -> list[dict]:
    """Return active non-decayed lessons (30-day half-life, weight > 0.1)."""
    conn.executescript(LESSONS_SCHEMA_SQL)
    now = float(now_ts) if now_ts is not None else time.time()
    rows = conn.execute(
        "SELECT id, outcome, query, paths_json, correction, created_ts FROM lessons ORDER BY created_ts DESC LIMIT 200"
    ).fetchall()
    q_low = query.strip().lower()
    o_low = outcome.strip().lower()
    results: list[dict] = []
    for r in rows:
        weight = _decay_weight(r["created_ts"], now)
        if weight <= MIN_DECAY_WEIGHT:
            continue
        if o_low and r["outcome"] != o_low:
            continue
        paths = json.loads(r["paths_json"] or "[]")
        hay = f"{r['query']} {' '.join(paths)} {r['correction']}".lower()
        if q_low and q_low not in hay and not any(t in hay for t in q_low.split()):
            continue
        results.append({
            "outcome": r["outcome"],
            "query": r["query"],
            "paths": paths,
            "correction": r["correction"],
            "weight": round(weight, 3),
        })
        if len(results) >= limit:
            break
    return results


def write_lessons_md(conn: sqlite3.Connection, mem_dir: Path, now_ts: float | None = None) -> Path:
    """Render compact <= 80 line .agents/memory/LESSONS.md from active lessons."""
    active = query_lessons(conn, limit=30, now_ts=now_ts)
    groups: dict[str, list[dict]] = {"useful": [], "dead_end": [], "corrected": []}
    for item in active:
        groups.setdefault(item["outcome"], []).append(item)
    lines = ["# Memory Lessons (30-Day Decay)", ""]
    titles = (("dead_end", "## Known Dead Ends"), ("corrected", "## Corrections"), ("useful", "## Proven Paths"))
    for key, heading in titles:
        items = groups.get(key) or []
        if not items:
            continue
        lines.append(heading)
        for it in items[:8]:
            locs = ", ".join(it["paths"]) or "-"
            extra = f" -> {it['correction']}" if it["correction"] else ""
            lines.append(f"- [{it['weight']:.2f}] `{it['query']}` @ `{locs}`{extra}")
        lines.append("")
    if len(lines) <= 2:
        lines.append("- (no active lessons)")
    out_path = mem_dir / "LESSONS.md"
    out_path.write_text("\n".join(lines[:80]).rstrip() + "\n", encoding="utf-8")
    return out_path


def hydrate_dead_ends_line(conn: sqlite3.Connection, max_items: int = 2) -> str:
    """Return one compact warning line of active dead_end/corrected lessons for L2 hydration."""
    active = [
        item for item in query_lessons(conn, limit=12)
        if item["outcome"] in ("dead_end", "corrected")
    ]
    if not active:
        return ""
    parts = [f"{it['query']}({','.join(it['paths'][:1]) or '-'})" for it in active[:max_items]]
    return "Avoid: " + "; ".join(parts)
