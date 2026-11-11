<div align="center">

# Gravity Harness Fix (`gravity-harness-fix`)

**Stop AI coding agents from stalling, thrashing files, crashing on Windows encoding, or burning hours in slow `/teamwork` loops.**

[![Tests](https://github.com/IrMaho/gravity-harness-fix/actions/workflows/ci.yml/badge.svg)](https://github.com/IrMaho/gravity-harness-fix/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Read in your language / زبان خود را انتخاب کنید / اختر لغتك:**  
**[English](README.md)** · **[فارسی (Persian)](docs/README.fa.md)** · **[العربية (Arabic)](docs/README.ar.md)**

</div>

---

## Why This Exists (Empirical Data Across 444 Transcripts / 106,004 Steps)

We ran a forensic analyzer ([`scripts/audit_transcripts.py`](scripts/audit_transcripts.py)) across **444 Antigravity transcripts** (`16` full conversations + `428` subagents, **`106,004` total steps**) to uncover why single-agent & `/teamwork` sessions slow down:

- **2,888** wasted `manage_task(status)` polling loops instead of reactive waits
- **5,693** redundant `>2x` re-reads of identical files (`34.0%` of all `16,746` reads)
- **657** multiline shell quoting crashes (`python -c`, `node -e`, PowerShell -> WSL nesting) + **111** Windows `cp1252` crashes
- **535** blind `edit_file` target-mismatch retries (`20.5%` failure rate)
- **400+ wasted setup steps** inside built-in `/teamwork` coordinator interviews before writing code, followed by `7` workers colliding in `Workspace="inherit"`
- **49.3% (`211/428`)** subagent API/stream failure rate totaling **672.4 minutes (11.2 hours)** of backoff under unconstrained concurrency

[`gravity-harness-fix`](.) converts every one of those bottlenecks into **deterministic lifecycle hooks, always-on rules, `/agile-swarm` parallel execution, continuous live telemetry, and one-click installation** across every Antigravity `.gemini` profile.

---

## Key Features

### 1. `/agile-swarm` — Fast Single-Account Parallel Teamwork (Plan B)

Replaces slow 400-step coordinator ceremonies with lean **employer-style multi-worktree execution** from a **single Antigravity account**:

- **Zero coordinator/interview overhead:** The lead agent triages in `<2` minutes with strict **disjoint file ownership** and interface contracts.
- **Native isolation (`Workspace="share"`):** Spawns **2–3 concurrent `agile-worker` subagents** in isolated shared-git workspaces (`agile/<slice-slug>`), preventing shared-directory overwrites and API rate-limit collapse.
- **Fast targeted tests first:** Each slice runs `5–30s` tests cleanly before committing; heavy CI gates run once on integration or in a dedicated sibling worktree.
- **Includes [`agile-worktree.bat`](agile-worktree.bat) / [`worktree_team.py`](plugin/skills/agile-swarm/scripts/worktree_team.py):** Create, inspect, and safely clean up sibling `git worktree` folders when offloading heavy Docker/CI runs or working across parallel IDE tabs.

#### Live Benchmark: 10-Screen Flutter App Built With `/agile-swarm`

Built a complete **10-page Material 3 Flutter application** (`Dashboard`, `Projects`, `Project Detail`, `Tasks Board`, `Analytics`, `Team Chat`, `Notifications`, `Editable Profile`, `Wallet & Invoices`, `Settings & Security` + live Dark Mode) on a single Antigravity account:

| Metric | Legacy `/teamwork` (Historical Audit) | `/agile-swarm` Plan B Benchmark |
|---|---|---|
| **Setup overhead before first code** | `400` coordinator steps | **`< 3` minutes** (`1` base skeleton commit) |
| **Parallel coding execution** | `7` workers colliding in `inherit` | **`3` `agile-worker`s on `Workspace="share"` (`4.38m` / `4.75m` / `5.95m`)** |
| **Total wall-clock build + merge + E2E test** | `756` min | **`12.3` minutes** (`+5,804` handwritten Dart lines, `19` files) |
| **Worker step budget & polling** | `1,817` steps / `73` polls | **`51` / `53` / `64` steps** / **`0` polls** |
| **API backoff during worker sprint** | `22.7` minutes | **`0.0` minutes** |
| **Merge & final verification** | Shared-dir collisions | **`0` conflicts**, `flutter analyze`: `0 issues`, `11/11` tests pass |

*(Note: Greenfield modular apps parallelize 3-way cleanly; tasks sharing a single live database/core pipeline automatically drop to `1 Writer + 1 Parallel Reviewer/Tester` via the skill's WS1-vs-WS3 gate.)*

---

### 2. Deterministic Antigravity Lifecycle Guardrails ([`plugin/hooks/guard_and_log.py`](plugin/hooks/guard_and_log.py))

| Lifecycle Event | Deterministic Enforcement |
|---|---|
| **`SessionStart`** | Injects real runtime environment telemetry (OS, UTF-8, Docker daemon state, `uv`/`wsl`/`flutter`/`git` availability, active log path). |
| **`PreToolUse`** | • **Hard-blocks `manage_task(status)` polling loops** (`polling_loop_blocked`)<br>• **Hard-blocks parallel write subagents in `Workspace="inherit"`**, redirecting immediately to `Workspace="share"` (`parallel_inherit_subagent_blocked`)<br>• **Prompts before `4th+` subagent spawn in 2 min** to stay within Plan B single-account API limits (`subagent_flood_prompt`)<br>• **Hard-blocks multiline inline quoting bombs** (`python -c`, `node -e`, `powershell -Command`, nested WSL scripts) (`inline_quoting_blocked`)<br>• **Hard-blocks blind `edit_file` retries** after a target mismatch until the file is re-read (`blind_edit_retry_blocked`)<br>• **Hard-blocks identical duplicate reads `<90s`** unless edited (`duplicate_read_blocked`)<br>• **Hard-blocks POSIX test suites mistakenly run natively on Windows** (`wrong_os_test_blocked`)<br>• **Asks before unguarded live DB exports or premature full CI runs** (`unguarded_live_export`, `premature_ci_gate_prompt`) |
| **`PostToolUse`** | Logs command errors (`encoding_cp1252`, `shell_or_syntax_quoting`, `missing_binary_or_path`, `docker_or_service_unavailable`, ignoring benign `rg`/`git grep` exit-1 misses), flags read-thrashing (`8/16/25+` reads), and flags `300`-step session bloat. |
| **`Stop`** | Records error/token-limit/invocation stops cleanly while allowing reactive async waits (`fullyIdle=false`) to receive `<SYSTEM_MESSAGE>` wakeups smoothly. |

---

### 3. Always-On Telemetry & Doctor Skill ([`gravity-session-doctor`](plugin/skills/gravity-session-doctor/SKILL.md))

- Automatically writes structured anomalies and prevented anti-patterns to `logs/session-issues.jsonl` + a human-readable dashboard in `logs/latest-summary.md` (gitignored so local logs stay private).
- Double-click [`audit_all_conversations.bat`](audit_all_conversations.bat) or ask Antigravity *"Inspect gravity harness logs"* to inspect anomalies, re-scan transcripts, add regression tests, and update all profiles with one click.

---

## Quick Start (Share With Friends)

### Windows (One-Click Install / Update)

1. Clone or unzip this repository anywhere on your PC.
2. Double-click **`install.bat`** (auto-discovers `%USERPROFILE%\.gemini` and any isolated `C:\Gravity-*\home\.gemini` profiles, configures UTF-8 `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1`, fixes WSL2 `uv` PATH, enables the plugin, and runs a live `cmd /c` hook smoke test).
3. Open a **new Antigravity chat** (or restart the IDE).
4. Start any multi-part task with:
   ```text
   /agile-swarm Build feature X, Y, and Z with tests
   ```

### Linux / macOS / CLI Install

```sh
python3 scripts/install_harness.py
```

### Run Unit Tests

```sh
python3 -X utf8 -m unittest discover -s tests -p "test_*.py" -v
```

### Uninstall Cleanly

Double-click **`uninstall.bat`** or run:

```sh
python3 scripts/install_harness.py --uninstall
```

---

## Multilingual Overview · خلاصه فارسی · ملخص عربي

### فارسی (خلاصه سریع)

* **نصب و آپدیت با یک کلیک:** فایل [`install.bat`](install.bat) را دوبار کلیک کنید تا پلاگین روی تمام پروفایل‌های Antigravity نصب شود، انکودینگ `UTF-8` ویندوز و `PATH` مربوط به `uv` در WSL2 تنظیم شود و تست زنده پاس شود. برای راهنمای کامل فارسی ببینید: [**`docs/README.fa.md`**](docs/README.fa.md).
* **تیم‌ورک سریع مثل کارفرما روی یک اکانت (`/agile-swarm`):** بدون اتلاف `۴۰۰` استپ برای Coordinator، کار را با فایل‌مالکیت مجزا بین `۲` تا `۳` ورکر موازی روی `Workspace="share"` می‌شکند و در بنچمارک واقعی **اپ فلاتری ۱۰ صفحه‌ای (`۵,۸۰۴` خط کد + `۱۱/۱۱` تست پاس)** کل فرآیند در **`۱۲.۳` دقیقه** با **صفر کانفلیکت** و **صفر دقیقه‌ی قطع API** تمام شد.
* **مراقب همیشه‌فعال (`logs/` + `gravity-session-doctor`):** تمام باگ‌ها، لوپ‌های polling، ادیت‌های تکراری و خطاهای دستور به‌صورت خودکار لاگ و بلاک می‌شوند تا هر بار با هم بررسی‌شان کنیم.

### العربية (ملخص سريع)

* **التثبيت والتحديث بنقرة واحدة:** شغّل [`install.bat`](install.bat) لتثبيت الإضافة تلقائياً على جميع ملفات Antigravity، وضبط ترميز `UTF-8` على ويندوز ومسار `uv` في WSL2، مع فحص تشغيل مباشر. للدليل العربي الكامل راجع: [**`docs/README.ar.md`**](docs/README.ar.md).
* **عمل جماعي رشيق على حساب واحد (`/agile-swarm`):** بدون انتظار `400` خطوة للمنسّق التقليدي؛ يقسّم المهمة إلى `2–3` عمّال متوازين عبر `Workspace="share"` بملكية ملفات منفصلة. في اختبار تطبيقي حقيقي لبناء **تطبيق Flutter من 10 شاشات (`5,804` سطر برمجي + نجاح `11/11` اختبار)** اكتمل البناء والدمج خلال **`12.3` دقيقة** بـ **0 تعارضات** و**0 دقائق توقف API**.
* **رصد دائم للأخطاء (`gravity-session-doctor`):** يحظر التكرار العشوائي للقراءة والتعديل وحلقات الانتظار ويسجل الأعطال تلقائياً لتحسين الإعدادات باستمرار.

---

## Repository Structure

```text
gravity-harness-fix/
├── .github/workflows/ci.yml              # Cross-platform CI (Windows + Ubuntu)
├── docs/
│   ├── README.fa.md                      # Complete Persian documentation
│   ├── README.ar.md                      # Complete Arabic documentation
│   └── audit-all-conversations.md        # Empirical audit metrics (444 transcripts) & benchmark
├── logs/.gitkeep                         # Local live telemetry directory (jsonl/state gitignored)
├── plugin/
│   ├── plugin.json                       # Antigravity native plugin manifest
│   ├── hooks.json                        # SessionStart / PreToolUse / PostToolUse / Stop hooks
│   ├── hooks/guard_and_log.py            # Deterministic guardrails & structured telemetry engine
│   ├── hooks/run_hook.cmd                # Quote-safe Windows hook launcher
│   ├── rules/AGENTS.md                   # Compact always-on execution & Plan B swarm rules
│   └── skills/
│       ├── agile-swarm/                  # Plan B fast parallel teamwork skill + worktree CLI
│       └── gravity-session-doctor/       # Live telemetry inspector & regression workflow
├── scripts/
│   ├── install_harness.py                # Cross-profile installer, backup & live smoke tester
│   ├── audit_transcripts.py              # Multi-home forensic transcript scanner
│   └── _find_python.bat                  # Windows Store alias-safe Python 3 locator
├── tests/test_harness_guards.py          # Automated regression suite (13 tests)
├── install.bat                           # Double-click Windows installer / updater
├── uninstall.bat                         # Clean Windows uninstaller
├── audit_all_conversations.bat           # Double-click log viewer & transcript auditor
├── agile-worktree.bat                    # Sibling git worktree helper for parallel / CI tasks
└── LICENSE                               # MIT License
```
