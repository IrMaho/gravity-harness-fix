---
name: truthful-readme
description: >-
  Evidence-verified, strictly truthful README and project documentation builder.
  Reverse-engineers manifests, entrypoints, configs, APIs, tests, and CI from the
  repository first, scales documentation depth cleanly to repo size, builds valid
  Mermaid diagrams, adds an AI-Agent Navigation Guide, and verifies every local
  link and anchor via scripts/verify_readme.py.
---

# Truthful & Professional README Builder

Reverse-engineer real repository reality into clear, accurate, navigable documentation for both human engineers and AI coding agents — never prettier than it is truthful.

Check [references/readme-templates.md](./references/readme-templates.md) for section scaffolding, Mermaid diagram templates, and multilingual switcher conventions (`EN | فارسی | العربية`).

## Absolute Truth Rules

1. **Zero Fabrication:** NEVER invent badges, test/benchmark numbers, environment variables, default values, CLI flags, API routes, screenshots, or directories that do not exist in the workspace.
2. **Verified Source Priority:** Actual source code > configs & package manifests > CI workflows > verified test/command outputs > older docs (treat stale docs as suspect until confirmed!).
3. **Never Modify Code Functionality:** Only author/update documentation (plus safe `docs/` assets when clearly needed). Do not alter runtime code or ask questions answerable from repo files.

## Auto-Scaled Documentation Depth (Avoid Overdesign!)

- **Micro (`< 15` files / single utility):** Concise Hero, Install/Prerequisites, Tested Quick Start, Core API/CLI Reference, AI File Map, Test command, License. Skip forced 5-diagram boilerplate.
- **Standard (`15–120` files / app or service):** Add verified Repo Tree, **1–2 high-signal Mermaid diagrams** (Architecture + Request/Data Flow), Configuration/Env Table (real defaults only), Testing, Build/Deploy, Troubleshooting, Security notes, AI Navigation Guide.
- **Platform / Monorepo (`> 120` files):** Full Documentation Index (`docs/`), Module Matrix, Deployment & Extension Guides, plus optional localized README switcher (`README.md` + `docs/README.fa.md` + `docs/README.ar.md`).

## Build Sequence

1. **Inspect First (Do Not Write Yet):** Read manifests, entrypoints, configs, `.github/workflows`, tests, and any existing `README.md`.
2. **Draft Structured Sections & Verified Mermaid Diagrams:** Every node/module/path/flag in diagrams, repo trees, and commands MUST match real files/flags seen in Step 1.
3. **Include AI-Agent Navigation Block:** Crisp map showing where entrypoints, tests, configs, and key abstractions live + what checks to run before committing.
4. **Automated Truth & Link Verification (Mandatory):**

   ```sh
   python -X utf8 scripts/verify_readme.py README.md --repo-root .
   ```

   Also re-run verification on any localized docs (`docs/README.fa.md`, etc.) and verify documented Quick Start / test commands actually work. Fix all `broken_links` and `placeholders` before declaring Done.

