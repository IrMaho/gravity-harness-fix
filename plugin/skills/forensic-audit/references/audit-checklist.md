# 14-Domain Forensic Audit Checklist

Use only applicable domains for the target stack (skip N/A infrastructure sections honestly instead of padding):

1. **Discovery & Inventory:** Entrypoints, manifests, lockfiles, build scripts, env templates, migrations, secrets files (`.gitignore` hygiene).
2. **Baseline Execution:** Install, build, typecheck, lint, unit/integration tests, smoke run (exact numbers + commands).
3. **Architecture Drift:** Compare documented/intended layering against actual imports, global singletons, circular deps, god files (`> 400` lines).
4. **Correctness & Edge Cases:** Race conditions, unawaited async futures, silent `except: pass` / `.catch(() => {})`, null/empty boundary handling, resource leaks.
5. **Security:** Injection (SQL/Shell/XSS/Path Traversal), auth/authz enforcement on every mutating route/command, secret exposure, CORS/CSP, insecure deserialization (`pickle`/`yaml.load`), dependency CVEs.
6. **Dependencies:** Unused/abandoned/duplicated libraries, unpinned critical versions, native binary traps on Windows vs Linux.
7. **Testing & QA Quality:** Flaky/mock-heavy tests hiding broken integration, missing negative/edge tests, skipped assertions, CI gates disconnected from real builds.
8. **Runtime & Behavioral Verification:** Boot/CLI/app startup checks, error exit codes, UTF-8 / encoding behavior, config overrides.
9. **Performance:** N+1 queries, repeated synchronous disk/network calls in loops, unbounded memory buffers/exports, unindexed lookups, rebuild storms (UI).
10. **Database & Data Integrity:** Schema constraints, foreign keys, idempotency, transaction boundaries, destructive migrations without rollback.
11. **API & Contract Hygiene:** Schema drift between producer & consumer, inconsistent error payloads, missing timeouts/retries on outbound HTTP.
12. **Documentation Reality Check:** Compare `README.md` commands, paths, env vars, and feature claims against actual source code.
13. **Technical Debt:** Copy-pasted logic blocks, dead code paths, mixed responsibilities, hard-coded environment paths.
14. **Self-Review Gate Before Report Generation:**
    - Every finding has exact `location`, `fact`, `inference`, `root_cause`, `recommendation`.
    - Zero duplicate findings; zero unverified guesses promoted to `CONFIRMED`.
    - `limitations` lists every area inaccessible during the audit.

