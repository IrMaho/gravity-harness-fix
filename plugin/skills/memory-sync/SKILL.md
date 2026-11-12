---
name: memory-sync
description: >-
  Persistent 5-layer agent memory engine (/memory-sync) backed by SQLite WAL +
  FTS5 (BM25), incremental AST/regex symbol indexing, bounded shards, and L2
  hydration briefs.
---

# Memory Sync (`/memory-sync`)

Keep cross-session context fast, searchable, and compact without dumping raw files into the prompt. See [the 5-Layer Memory & Shard Contract](./references/memory-layers.md).

## When to Run

- **Session start / resume:** Run `hydrate` to load the compact `<= 650`-char L2 brief, then `symbol` or `search` for exact files/lines instead of broad file scanning.
- **After code or doc edits:** Run `index --paths ...` (or full incremental `index`) to refresh SQLite symbols and FTS5 chunks.
- **Milestone / handoff:** Run `checkpoint` to persist `state.json`, update `MEMORY_INDEX.md` (`<= 60` lines), and append bounded shard notes (`<= 120` lines, auto-rolling older entries to `archive_<shard>.md`).

## CLI Commands

Run from any workspace using Python 3 stdlib only (no pip dependencies):

```sh
python -X utf8 plugin/skills/memory-sync/scripts/memory_engine.py --workspace . init
python -X utf8 plugin/skills/memory-sync/scripts/memory_engine.py --workspace . index
python -X utf8 plugin/skills/memory-sync/scripts/memory_engine.py --workspace . index --paths src/app.py docs/arch.md
python -X utf8 plugin/skills/memory-sync/scripts/memory_engine.py --workspace . symbol AuthService
python -X utf8 plugin/skills/memory-sync/scripts/memory_engine.py --workspace . search "token refresh flow"
python -X utf8 plugin/skills/memory-sync/scripts/memory_engine.py --workspace . checkpoint --task "Slice 1" --tests "12/12 pass" --shard decisions --title "Use WAL" --body "Enabled SQLite WAL mode."
python -X utf8 plugin/skills/memory-sync/scripts/memory_engine.py --workspace . hydrate
```

## Guardrails

- **Never commit ephemeral DB/state:** `.agents/memory/.gitignore` ignores `memory.db*` and `state.json`; only `MEMORY_INDEX.md` and shard markdown files are git-friendly.
- **Respect size caps:** Keep `MEMORY_INDEX.md <= 60` lines, each shard `<= 120` lines, and L2 hydration `<= 650` chars.
- **Targeted reads over brute force:** Call `lookup_symbol` / `search_memory` first, then read only the returned line range.
