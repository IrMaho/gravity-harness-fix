---
name: memory-sync
description: >-
  Persistent 5-layer agent memory engine (/memory-sync) backed by SQLite WAL +
  FTS5 (BM25), incremental AST/regex symbol indexing, bounded shards, 30-day
  decaying lessons, and L2 hydration briefs.
---

# Memory Sync (`/memory-sync`)

Keep cross-session context fast, searchable, and compact without dumping raw files into the prompt. See [the 5-Layer Memory & Shard Contract](./references/memory-layers.md).

## When to Run

- **Session start / resume:** Run `hydrate` to load the compact `<= 650`-char L2 brief (including active `Avoid:` dead-end warnings), then `symbol` or `search` (`--format toon` / `format="toon"` saves ~40–60% tokens).
- **After code or doc edits:** Run `index --paths ...` (or full incremental `index`) to refresh SQLite symbols and FTS5 chunks.
- **After hitting dead ends or fixes:** Record a 30-day decaying lesson (`useful`, `dead_end`, `corrected`) via `lesson record` / `memory_lesson`.
- **Milestone / handoff:** Run `checkpoint` to persist `state.json`, update `MEMORY_INDEX.md` (`<= 60` lines), check `conflicts` against prior shard decisions, and append bounded shard notes (`<= 120` lines).

## CLI Commands

Run from any workspace using Python 3 stdlib only (no pip dependencies):

```sh
python -X utf8 plugin/skills/memory-sync/scripts/memory_engine.py --workspace . init
python -X utf8 plugin/skills/memory-sync/scripts/memory_engine.py --workspace . index
python -X utf8 plugin/skills/memory-sync/scripts/memory_engine.py --workspace . --format toon symbol AuthService
python -X utf8 plugin/skills/memory-sync/scripts/memory_engine.py --workspace . --format toon search "token refresh flow"
python -X utf8 plugin/skills/memory-sync/scripts/memory_engine.py --workspace . checkpoint --task "Slice 1" --tests "12/12 pass" --shard decisions --title "Use WAL" --body "Enabled SQLite WAL mode."
python -X utf8 plugin/skills/memory-sync/scripts/memory_engine.py --workspace . lesson record --outcome dead_end --query "legacy auth" --path src/old_auth.py --correction "Use src/auth_service.py instead"
python -X utf8 plugin/skills/memory-sync/scripts/memory_engine.py --workspace . lesson list
python -X utf8 plugin/skills/memory-sync/scripts/memory_engine.py --workspace . hydrate
```

## Guardrails

- **Never commit ephemeral DB/state:** `.agents/memory/.gitignore` ignores `memory.db*` and `state.json`; `MEMORY_INDEX.md`, `LESSONS.md`, and shard markdown files are git-friendly.
- **Respect size caps:** Keep `MEMORY_INDEX.md <= 60` lines, each shard `<= 120` lines, `LESSONS.md <= 80` lines, and L2 hydration `<= 650` chars.
- **Targeted reads over brute force:** Call `lookup_symbol` / `search_memory` (`format="toon"`) first, then read only the returned line range.
