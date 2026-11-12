---
name: context-guard
description: >-
  Proactive context budget guard and isolated multi-branch task orchestrator. Visualizes real-time token volume, protects main chat from exceeding 80% token capacity, enforces isolated sub-contexts per task (dedicated git-worktree & clean subagent prompt), and triggers automated L2 checkpoints before context overflow causes stream EOF drops.
---

# Context Guard — 80% Budget Watchdog & Isolated Multi-Branch Cockpit

Protects your main Antigravity conversation from **context bloat, 503 capacity overloads, and stream EOF drops** by enforcing a clean 3-Tier Context Architecture.

---

## 🏛️ The 3-Tier Context Architecture

```
                  ┌──────────────────────────────────────────────┐
                  │   Tier 1: Main Cockpit Chat (Orchestrator)   │
                  │   • Architecture, Decisions & User Dialogue │
                  │   • Target: Keep < 60-80% Token Capacity     │
                  └──────────────────────┬───────────────────────┘
                                         │
             ┌───────────────────────────┴───────────────────────────┐
             ▼                                                       ▼
┌─────────────────────────────┐                         ┌─────────────────────────────┐
│  Tier 2: Task Slice 1       │                         │  Tier 2: Task Slice 2       │
│  • Worktree: `wt-engine`    │                         │  • Worktree: `wt-ui`        │
│  • Branch: `agile/wt-engine`│                         │  • Branch: `agile/wt-ui`    │
│  • Isolated Context Window  │                         │  • Isolated Context Window  │
└─────────────────────────────┘                         └─────────────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │   Tier 3: L2 Memory & Zero-Loss Handoff      │
                  │   • State saved in `.agents/memory/`         │
                  │   • Auto-snapshot at 80% threshold           │
                  │   • Instant 3ms revival in fresh chat        │
                  └──────────────────────────────────────────────┘
```

1. **Tier 1 (Main Cockpit Context):**
   - Strictly reserved for high-level direction, ADR decisions, review, and user conversation.
   - **Never perform massive 50-file code scans or giant test logs directly in Tier 1.**
2. **Tier 2 (Isolated Task Slices):**
   - Spawn parallel workers using `/agile-swarm` with `Workspace="share"`.
   - Each worker runs in an independent git worktree on its own branch (`agile/<slice-slug>`).
   - All intermediate reads, edits, and widget/unit test runs stay inside the worker's isolated context.
3. **Tier 3 (Automated 80% Watchdog & L2 Handoff):**
   - When the conversation reaches **80% of token capacity** (~160k tokens), the guard saves an automatic L2 snapshot (`.agents/memory/state.json`).
   - If upstream streaming latency spikes or `EOF` drops occur, you can run `/compact` or start a fresh chat with zero lost progress.

---

## 🛠️ Tools & Commands

### 1. View Live Context Cockpit (HTML / JSON)

To view your exact token consumption, cache breakdown, and active worktree slices:

```sh
# Generate interactive dark-mode HTML Cockpit:
python plugin/skills/context-guard/scripts/context_cockpit.py --html

# Output JSON status:
python plugin/skills/context-guard/scripts/context_cockpit.py --json
```

Or call the MCP tool directly:
```json
{
  "name": "context_budget",
  "arguments": {
    "workspace": ".",
    "generate_html": true
  }
}
```

### 2. Spawning Tasks in Isolated Worktrees

Always spawn heavy implementation slices into isolated worktrees:
```bat
# 1. Create clean sibling worktrees
python plugin/skills/agile-swarm/scripts/worktree_team.py create <repo_path> slice-engine slice-ui

# 2. Inspect active slices
python plugin/skills/agile-swarm/scripts/worktree_team.py list <repo_path>

# 3. View slice diffs without polluting main context
python plugin/skills/agile-swarm/scripts/worktree_team.py diff <repo_path> --stat

# 4. If an isolated worker is interrupted by network drop, rescue all files instantly:
python plugin/skills/agile-swarm/scripts/worktree_team.py rescue <repo_path>

# 5. Clean up finished worktrees
python plugin/skills/agile-swarm/scripts/worktree_team.py cleanup <repo_path> --delete-branches
```

### 3. Handoff Protocol When Context Exceeds 80%

When the `[Context Guard: 80% Alert]` fires:
1. Call `memory_checkpoint` to save task, status, tests, and next steps into `.agents/memory/`.
2. Run `/compact` to compress the history, OR open a fresh chat.
3. In the new chat, call `memory_hydrate` (runs in `<3ms`) to instantly resume full project intelligence.
