---
name: multi-account-cli
description: >-
  Autonomous Multi-Account Antigravity CLI and Subagent Swarm Orchestrator. Discovers all configured Google accounts/profiles, spawns fully isolated subagent workers across accounts, assigns concurrent tasks to bypass single-account quota and rate limits, streams live status, and manages worker lifecycles.
---

# Multi-Account CLI Subagent Swarm Orchestrator

Orchestrate a swarm of autonomous Antigravity CLI subagents across multiple configured Google accounts (`Gravity-2`, `Gravity-3`, `Gravity-5`, `Gravity-6`, `Gravity-7`, `Host`, etc.) to multiply API quota, parallelize long-running tasks, and maintain strict process and credential isolation.

## Capabilities & Tool Contract

### 1. `call_mcp_tool("gravity-harness-fix_gravity-memory", "cli_list_accounts", {})`
Discovers all local Antigravity profiles on `C:\` and `AppData`, extracting authenticated email addresses, profile paths, and readiness.

### 2. `call_mcp_tool("gravity-harness-fix_gravity-memory", "cli_spawn_agent", { ... })`
Spawns an isolated subagent worker process under the target account/profile.
- `account`: Target profile (`Gravity-2`) or email address (`irmahodev@gmail.com`).
- `task_prompt`: Clear, actionable task instructions.
- `model`: Model to execute (e.g. `gemini-3.8-flash-high`, `claude-sonnet-4-6`, `pro`).
- `workspace`: (Optional) Path to project or dedicated git-worktree (`Workspace="share"`).
- `title`: (Optional) Human-readable session name.

### 3. `call_mcp_tool("gravity-harness-fix_gravity-memory", "cli_send_task", { ... })`
Delivers follow-up instructions or next task phases to an existing worker.
- `worker_id`: Unique worker identifier or conversation ID.
- `prompt`: Next prompt instruction.

### 4. `call_mcp_tool("gravity-harness-fix_gravity-memory", "cli_get_agent_status", { ... })`
Inspects real-time transcript progress, latest model responses, tool executions, and turn completion (`DONE`, `RUNNING`, `ERROR`).

### 5. `call_mcp_tool("gravity-harness-fix_gravity-memory", "cli_terminate_agent", { ... })`
Gracefully closes the worker and marks it terminated in the central registry.

---

## Operating Protocol

1. **Discovery & Allocation:**
   - Call `cli_list_accounts` to see available accounts and their active models.
   - For heavy parallel features, split into 2–3 disjoint tasks across separate Google accounts.

2. **Spawn & Non-Blocking Delegation:**
   - Spawn workers using `cli_spawn_agent` with dedicated branches/worktrees.
   - Workers execute autonomously in their own process boundaries without blocking the main chat.

3. **Status Check & Turn Resolution:**
   - Use `cli_get_agent_status` to inspect completions or wait for `<SYSTEM_MESSAGE>` notifications.
   - When finished, summarize output and release workers with `cli_terminate_agent`.

