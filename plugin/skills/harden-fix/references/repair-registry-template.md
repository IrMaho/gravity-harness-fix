# Repair Registry & Verification Checklist

Track every defect cleanly during `/harden-fix` (in memory/Artifact or scratch tracker):

```markdown
| ID | Priority | Cat (A/B/C) | Target Location | Root Cause | Proof Test / Check | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| FIX-01 | P0 | A | ... | ... | ... | VERIFIED |
```

## Anti-Shortcut Second-Pass Audit Questions
1. Did any fix accidentally swallow errors, tighten happy-path assumptions, or weaken validation elsewhere?
2. Are all public APIs/schemas/configs backwards-compatible unless explicitly authorized under Category C?
3. Did static analyzers (`flutter analyze`, `tsc --noEmit`, `eslint`, `ruff`), security checks, and full integration tests run AFTER the final edit?
4. Do Before/After counts match actual command outputs from this session?
