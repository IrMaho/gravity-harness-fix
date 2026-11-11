# Deep Rules: Raw SVG Preservation & Figma State Safety

## 1. Raw SVG Preservation Pipeline

```text
Figma MCP Vector Node -> Raw SVG output -> assets/icons/<semantic_name>.svg -> Centralized Icon Registry -> Feature UI
```

Never alter `path` geometry, `viewBox`, strokes, fills, or curves by hand, and never replace an icon from Figma with an emoji, Unicode symbol, or approximate library glyph. If an extracted icon looks wrong when rendered:
1. Verify you exported the correct Figma variant/node.
2. Verify stroke vs fill tinting, container constraints, `BoxFit` / CSS sizing, and color inheritance.
3. Re-export the exact vector from Figma MCP rather than rewriting coordinates manually.

## 2. State, Variant & Partial-View Protection Matrix

Before modifying an existing page/component when implementing a Figma frame:
- Is this frame a **collapsed vs expanded sidebar**, **hover/focus/active state**, **drawer/modal**, **empty/error/loading state**, or **selected tab**?
- Identify the **actual visual/layout delta** between existing code and the new Figma variant.
- Extract or parameterize the new variant alongside existing states instead of overwriting logic/handlers/routes required by unselected states.

## 3. UI Hygiene Verification Checklist

- [ ] Design tokens (colors, typography, spacing, radii, shadows) centralized & reused.
- [ ] All icons live in central asset/icon module (`<= 200` lines); no duplicate `.svg` basenames.
- [ ] Zero manual `Path()` icon reconstruction or feature-scattered inline `<svg>`.
- [ ] All modified UI files `<= 400` lines; existing unselected states verified intact.
- [ ] Story/preview updated if Storybook/Widgetbook is active in the workspace.

