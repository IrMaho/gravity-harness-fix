---
name: figma-to-prod
description: >-
  Figma MCP to production UI workflow supporting Flutter and React/TypeScript
  (+ Storybook/Widgetbook). Enforces visual design-token fidelity, raw .svg
  icon preservation through a centralized icon package, state/variant
  differential safety, optional reference architecture adaptation (--ref), and
  static hygiene verification via scripts/verify_figma_ui.py.
---

# Figma MCP to Production UI Workflow

Convert Figma frames and components via Figma MCP into clean, modular, token-driven UI code without manual SVG geometry guessing, erased UI states, or 2,000-line widget/component bloat.

For deep SVG asset extraction steps and Figma state/partial-view edge cases, read [references/svg-and-state-rules.md](./references/svg-and-state-rules.md).

## Stack, Viewport & Visual Policy Detection (Zero Contradictions)

Before writing UI code, lock these 4 parameters explicitly from the host repository + user prompt:

1. **Target Stack:** Auto-detect `Flutter` (`pubspec.yaml` -> Material/ThemeData, `flutter_svg`, `flutter test` / goldens, Widgetbook if configured) OR `React / TypeScript` (`package.json` -> CSS/Tailwind tokens, clean components, Vitest/TSC, `.stories.tsx` when Storybook exists or is requested).
2. **Viewport Scope:**
   - **Both Mobile + Web frames selected:** Build one unified responsive architecture sharing tokens, state, and business logic with adaptive breakpoint layouts matching BOTH targets.
   - **Single frame selected (Web/Desktop-only OR Mobile-only):** Implement exact fidelity for the selected viewport without inventing contradictions or breaking existing breakpoints in sibling views.
3. **Reference Architecture (`--ref <path>`, Optional):**
   - If the user passes a reference repository path, inspect it **read-only** (`NEVER modify the reference repo`) and adapt its clean folder/atomic/state conventions cleanly to the host stack. If no `--ref` is provided, strictly match existing host project conventions.
4. **Visual Verification Policy:**
   - Run **non-browser engineering validation first**: static analysis, unit/widget/golden tests, Storybook build (`npm run build-storybook` / Widgetbook compile), token & SVG checks.
   - Leave interactive Browser Preview OFF by default when the user handles final visual QA — activate headless/browser screenshot checks ONLY if the user explicitly asks for browser verification.

## Core Execution Pipeline

1. **Figma Target & State Inspection:**
   - Query Figma MCP for node structure, visual screenshot/reference, spacing/radii/shadows/typography tokens, and component variants.
   - Inspect **parent, siblings, and variants** FIRST to determine whether the node is a complete screen OR a partial state (open sidebar, hover, modal, empty/loading/error state). **Never delete unshown production states or routes.**
2. **Design System & Atomic Decomposition:**
   - Audit existing tokens, fonts, typography styles, and reusable atoms/molecules/organisms BEFORE creating anything new. Reuse/extend first; zero duplicated cards, buttons, or colors.
3. **Centralized Raw `.svg` Icon & Vector Extraction:**
   - Retrieve raw SVG directly from Figma MCP -> save verbatim as a real `.svg` file -> register in the centralized icon package (`assets/icons/` + `AppIcon` / `icons/index.ts`).
   - **NEVER** redraw Figma icons via manual `Path()`/`CustomPainter`, inline `<svg>` JSX scattered inside features, or Material/Lucide look-alikes.
4. **Modular File-Size Cap & Story Creation:**
   - Keep standard screens/features `<= 400` lines and icon/token/atom files `<= 200` lines.
   - Create or update corresponding `.stories.tsx` / Storybook / Widgetbook story entries whenever Storybook/Widgetbook exists or the user requests story coverage.
5. **Mandatory Automated UI Verification Gate:**

   ```sh
   python -X utf8 scripts/verify_figma_ui.py <target_src_or_lib_dir>
   ```

   Then run full stack static checks + tests (`flutter analyze && flutter test` or `npx tsc --noEmit && npm test`). Report strictly verified layout, asset, state preservation, and any items requiring human visual review.
