# 5-Layer Memory Architecture (L0–L4) & Shard Contract

## Memory Layers

| Layer | Name | Artifact | Budget / SLA | Purpose |
| --- | --- | --- | --- | --- |
| **L0** | Raw Workspace | Source `.py/.dart/.ts/.js/.md` files | On-demand slices | Ground-truth code & docs; never preload whole files unnecessarily. |
| **L1** | SQLite WAL + FTS5 Index | `.agents/memory/memory.db` | Incremental `(mtime_ns, size)` skip | Fast `lookup_symbol` and `search_memory` weighted by architectural path priority (core store/service boosted, tests `0.3x`), with `TOON` output option. |
| **L2** | Hydration Brief & Lessons | `hydrate_brief()`, `state.json`, `LESSONS.md` | `<= 650` chars / `LESSONS.md <= 80` lines | Instant session-start summary + 30-day half-life decaying `Avoid:` dead-end warnings (`weight > 0.1`). |
| **L3** | Bounded Shards | `.agents/memory/<shard>.md` & `MEMORY_INDEX.md` | `MEMORY_INDEX.md <= 60` lines; shard `<= 120` lines | Curated domain memory with automatic overlap/conflict checks when adding decisions. |
| **L4** | Archive Rollover | `.agents/memory/archive_<shard>.md` | Unbounded, FTS-indexed | Cold storage for older `## ` shard sections rolled out automatically when a shard exceeds 120 lines. |

## Canonical Shards (`L3`)

1. `decisions.md` — Architectural choices, trade-offs, accepted constraints.
2. `solved_bugs.md` — Root causes, repro symptoms, verified fixes.
3. `architecture.md` — Module boundaries, data flows, state ownership.
4. `active_task.md` — Working notes, open hypotheses, handoff context.

## Storage & Git Hygiene

- `.agents/memory/.gitignore` MUST ignore `memory.db*` and `state.json` (machine-local ephemeral runtime files).
- `MEMORY_INDEX.md`, `LESSONS.md`, `<shard>.md`, and `archive_<shard>.md` are plain UTF-8 Markdown and may be committed or shared cleanly.
- Every `checkpoint_state` write updates `state.json`, checks existing notes for decision overlap (`conflicts`), rolls any shard exceeding `120` lines into `archive_<shard>.md`, rewrites `MEMORY_INDEX.md` (`<= 60` lines), and incrementally re-indexes modified `.md` files in SQLite.
