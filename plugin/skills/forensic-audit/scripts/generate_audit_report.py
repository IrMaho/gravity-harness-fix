#!/usr/bin/env python3
"""Generate a standalone, offline-ready dark-mode HTML Engineering Audit Report.

Takes a structured JSON findings payload (or prints a schema template with
--template-json) and emits a self-contained interactive HTML report with
severity charts, baseline checks, filterable/sortable findings table, full
evidence cards (FACT vs INFERENCE vs RECOMMENDATION), P0-P3 plan, and verdict.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")

TEMPLATE_PAYLOAD: dict[str, Any] = {
    "project": {
        "name": "Example Project",
        "commit": "HEAD",
        "stack": "Flutter / Python / TypeScript",
        "architecture": "Layered Modular Architecture",
        "size": "0 files / 0 LOC",
        "scope": "Full isolated forensic audit",
    },
    "verdict": {
        "project_health": "FAIR",
        "production_readiness": "CONDITIONALLY READY",
        "security_posture": "MODERATE RISK",
        "maintainability": "MEDIUM",
        "test_confidence": "MEDIUM",
        "rationale": "Summary rationale backed by baseline checks and findings.",
    },
    "baseline_checks": [
        {"check": "Build", "result": "PASS", "evidence": "Verified clean build output"},
        {"check": "Unit Tests", "result": "PASS", "evidence": "0 failed"},
    ],
    "limitations": [
        "Production credentials unavailable in local isolated worktree.",
    ],
    "findings": [
        {
            "id": "AUD-001",
            "severity": "HIGH",
            "category": "Security",
            "confidence": "CONFIRMED",
            "status": "OPEN",
            "title": "Example verified finding",
            "location": "src/example.py:42",
            "fact": "Directly observed behavior from inspected source/test output.",
            "inference": "Likely failure impact under malformed input.",
            "impact": "Detailed operational/security impact.",
            "reproduction": "Command or input that triggers the defect.",
            "root_cause": "Missing boundary validation before execution.",
            "recommendation": "Validate schema before dispatch and add unit test.",
            "effort": "S",
            "priority": "P1",
            "snippet": "def example(raw):\n    return raw",
        }
    ],
    "next_steps": [
        "Resolve P0/P1 findings via /harden-fix",
    ],
}


def _e(val: Any) -> str:
    return html.escape(str(val if val is not None else ""), quote=True)


def _render_findings_rows(findings: list[dict[str, Any]]) -> str:
    rows: list[str] = []
    for f in findings:
        sev = str(f.get("severity", "INFO")).upper()
        cat = str(f.get("category", "General"))
        rows.append(
            f'<tr data-sev="{_e(sev)}" data-cat="{_e(cat.lower())}">'
            f'<td><code>{_e(f.get("id", ""))}</code></td>'
            f'<td><span class="badge sev-{_e(sev.lower())}">{_e(sev)}</span></td>'
            f'<td>{_e(cat)}</td>'
            f'<td>{_e(f.get("confidence", "CONFIRMED"))}</td>'
            f'<td><a href="#card-{_e(f.get("id", ""))}">{_e(f.get("title", ""))}</a></td>'
            f'<td><code>{_e(f.get("location", ""))}</code></td>'
            f'<td>{_e(f.get("priority", "P2"))}</td>'
            f'<td>{_e(f.get("status", "OPEN"))}</td>'
            "</tr>"
        )
    return "\n".join(rows) or '<tr><td colspan="8">No findings recorded.</td></tr>'


def _render_finding_cards(findings: list[dict[str, Any]]) -> str:
    cards: list[str] = []
    for f in findings:
        fid = str(f.get("id", ""))
        sev = str(f.get("severity", "INFO")).upper()
        snippet = str(f.get("snippet", "")).strip()
        snippet_html = f'<pre><code>{_e(snippet)}</code></pre>' if snippet else ""
        cards.append(
            f'<article class="card finding-card" id="card-{_e(fid)}" data-sev="{_e(sev)}" data-cat="{_e(str(f.get("category", "")).lower())}">'
            f'<div class="card-head"><div><code>{_e(fid)}</code> <strong>{_e(f.get("title", ""))}</strong></div>'
            f'<div><span class="badge sev-{_e(sev.lower())}">{_e(sev)}</span> '
            f'<span class="pill">{_e(f.get("category", ""))}</span> '
            f'<span class="pill">{_e(f.get("priority", "P2"))}</span></div></div>'
            f'<p class="meta"><strong>Location:</strong> <code>{_e(f.get("location", ""))}</code> · '
            f'<strong>Confidence:</strong> {_e(f.get("confidence", ""))} · '
            f'<strong>Effort:</strong> {_e(f.get("effort", ""))}</p>'
            f'<div class="grid2">'
            f'<div><h4>FACT (Observed)</h4><p>{_e(f.get("fact", f.get("evidence", "")))}</p></div>'
            f'<div><h4>INFERENCE &amp; IMPACT</h4><p>{_e(f.get("inference", ""))} {_e(f.get("impact", ""))}</p></div>'
            f'</div>'
            f'<p><strong>Root Cause:</strong> {_e(f.get("root_cause", ""))}</p>'
            f'<p><strong>Reproduction:</strong> <code>{_e(f.get("reproduction", "N/A"))}</code></p>'
            f'<p><strong>Recommendation:</strong> {_e(f.get("recommendation", ""))}</p>'
            f"{snippet_html}</article>"
        )
    return "\n".join(cards)


def build_html(data: dict[str, Any]) -> str:
    project = data.get("project", {})
    verdict = data.get("verdict", {})
    findings = data.get("findings", [])
    baseline = data.get("baseline_checks", [])
    limitations = data.get("limitations", [])
    next_steps = data.get("next_steps", [])
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    counts = {s: 0 for s in SEVERITIES}
    for f in findings:
        sev = str(f.get("severity", "INFO")).upper()
        counts[sev] = counts.get(sev, 0) + 1
    max_count = max([1, *counts.values()])

    bars_html = "\n".join(
        f'<div class="bar-row"><span class="badge sev-{s.lower()}">{s}</span>'
        f'<div class="bar-track"><div class="bar-fill sev-{s.lower()}" style="width:{round(counts[s]*100/max_count)}%"></div></div>'
        f'<span class="bar-num">{counts[s]}</span></div>'
        for s in SEVERITIES
    )
    baseline_html = "\n".join(
        f'<tr><td>{_e(b.get("check", ""))}</td>'
        f'<td><span class="pill">{_e(b.get("result", ""))}</span></td>'
        f'<td>{_e(b.get("evidence", ""))}</td></tr>'
        for b in baseline
    ) or '<tr><td colspan="3">No baseline checks provided.</td></tr>'
    lim_html = "\n".join(f"<li>{_e(item)}</li>" for item in limitations) or "<li>None recorded.</li>"
    next_html = "\n".join(f"<li>{_e(item)}</li>" for item in next_steps) or "<li>None recorded.</li>"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Audit Report — {_e(project.get("name", "Project"))}</title>
<style>
:root {{ --bg:#0b1020; --panel:#131a2e; --border:#232e4d; --text:#e6ecff; --muted:#95a3c6; --crit:#ff4d6d; --high:#ff9248; --med:#f5c542; --low:#4ea8de; --info:#7c8db5; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif; background:var(--bg); color:var(--text); line-height:1.55; padding:24px; }}
.wrap {{ max-width:1180px; margin:0 auto; }}
.card {{ background:var(--panel); border:1px solid var(--border); border-radius:12px; padding:18px; margin-bottom:18px; }}
h1,h2,h3,h4 {{ margin-top:0; }}
code,pre {{ background:#090d1a; border:1px solid var(--border); border-radius:6px; padding:2px 6px; font-size:0.88em; }}
pre {{ padding:12px; overflow-x:auto; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; }}
.grid2 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:12px; }}
.kpi {{ background:#0e1528; border:1px solid var(--border); border-radius:10px; padding:12px; }}
.kpi span {{ display:block; font-size:12px; color:var(--muted); text-transform:uppercase; }}
.kpi strong {{ font-size:18px; }}
.badge {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:700; color:#09101d; }}
.sev-critical {{ background:var(--crit); }} .sev-high {{ background:var(--high); }}
.sev-medium {{ background:var(--med); }} .sev-low {{ background:var(--low); }} .sev-info {{ background:var(--info); color:#fff; }}
.pill {{ display:inline-block; background:#1c2642; border:1px solid var(--border); border-radius:999px; padding:2px 8px; font-size:12px; }}
.bar-row {{ display:flex; align-items:center; gap:10px; margin:6px 0; }}
.bar-track {{ flex:1; height:12px; background:#090d1a; border-radius:999px; overflow:hidden; }}
.bar-fill {{ height:100%; }}
.bar-num {{ width:28px; text-align:right; font-weight:700; }}
.controls {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:12px; }}
input,select {{ background:#090d1a; color:var(--text); border:1px solid var(--border); border-radius:8px; padding:8px 10px; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th,td {{ text-align:left; padding:10px 8px; border-bottom:1px solid var(--border); vertical-align:top; }}
th {{ cursor:pointer; color:var(--muted); }}
a {{ color:#7cc6fe; text-decoration:none; }}
.meta {{ color:var(--muted); font-size:13px; }}
.card-head {{ display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:8px; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h1>Forensic Audit &amp; Engineering Assessment: {_e(project.get("name", "Project"))}</h1>
    <p class="meta">Commit: <code>{_e(project.get("commit", "HEAD"))}</code> · Stack: {_e(project.get("stack", ""))} · Scope: {_e(project.get("scope", ""))} · Generated: {_e(generated_at)}</p>
    <div class="grid">
      <div class="kpi"><span>Project Health</span><strong>{_e(verdict.get("project_health", "UNKNOWN"))}</strong></div>
      <div class="kpi"><span>Production Readiness</span><strong>{_e(verdict.get("production_readiness", "UNKNOWN"))}</strong></div>
      <div class="kpi"><span>Security Posture</span><strong>{_e(verdict.get("security_posture", "UNKNOWN"))}</strong></div>
      <div class="kpi"><span>Maintainability</span><strong>{_e(verdict.get("maintainability", "UNKNOWN"))}</strong></div>
      <div class="kpi"><span>Test Confidence</span><strong>{_e(verdict.get("test_confidence", "UNKNOWN"))}</strong></div>
    </div>
    <p style="margin-top:12px;">{_e(verdict.get("rationale", ""))}</p>
  </div>
  <div class="grid2">
    <div class="card"><h2>Severity Distribution ({len(findings)} total)</h2>{bars_html}</div>
    <div class="card"><h2>Baseline Verification</h2><table><thead><tr><th>Check</th><th>Result</th><th>Evidence</th></tr></thead><tbody>{baseline_html}</tbody></table></div>
  </div>
  <div class="card">
    <h2>Findings Registry</h2>
    <div class="controls">
      <input id="q" type="search" placeholder="Filter by title, file, or ID..." oninput="filterAll()">
      <select id="sev" onchange="filterAll()"><option value="">All Severities</option>{"".join(f'<option value="{s}">{s}</option>' for s in SEVERITIES)}</select>
    </div>
    <table id="ft"><thead><tr><th onclick="sortTable(0)">ID</th><th onclick="sortTable(1)">Severity</th><th onclick="sortTable(2)">Category</th><th onclick="sortTable(3)">Confidence</th><th onclick="sortTable(4)">Title</th><th onclick="sortTable(5)">Location</th><th onclick="sortTable(6)">Priority</th><th onclick="sortTable(7)">Status</th></tr></thead>
    <tbody>{_render_findings_rows(findings)}</tbody></table>
  </div>
  <div class="card"><h2>Detailed Findings (FACT vs INFERENCE)</h2>{_render_finding_cards(findings)}</div>
  <div class="grid2">
    <div class="card"><h2>Audit Limitations</h2><ul>{lim_html}</ul></div>
    <div class="card"><h2>Recommended Next Steps</h2><ul>{next_html}</ul></div>
  </div>
</div>
<script>
function filterAll() {{
  const q = document.getElementById('q').value.toLowerCase();
  const s = document.getElementById('sev').value;
  document.querySelectorAll('#ft tbody tr').forEach(r => {{
    const okQ = !q || r.textContent.toLowerCase().includes(q);
    const okS = !s || r.dataset.sev === s;
    r.style.display = (okQ && okS) ? '' : 'none';
  }});
  document.querySelectorAll('.finding-card').forEach(c => {{
    const okQ = !q || c.textContent.toLowerCase().includes(q);
    const okS = !s || c.dataset.sev === s;
    c.style.display = (okQ && okS) ? '' : 'none';
  }});
}}
let asc = true;
function sortTable(col) {{
  const tb = document.querySelector('#ft tbody');
  const rows = Array.from(tb.querySelectorAll('tr'));
  rows.sort((a,b) => asc ? a.cells[col].textContent.localeCompare(b.cells[col].textContent) : b.cells[col].textContent.localeCompare(a.cells[col].textContent));
  asc = !asc;
  rows.forEach(r => tb.appendChild(r));
}}
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build standalone interactive PROJECT_AUDIT_REPORT.html")
    parser.add_argument("--input", help="Path to structured JSON audit payload")
    parser.add_argument("--output", default="PROJECT_AUDIT_REPORT.html", help="Output HTML file path")
    parser.add_argument("--template-json", action="store_true", help="Print sample JSON schema to stdout")
    args = parser.parse_args()

    if args.template_json:
        print(json.dumps(TEMPLATE_PAYLOAD, indent=2, ensure_ascii=False))
        return 0
    if not args.input:
        parser.error("--input is required unless --template-json is passed")

    payload = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(payload), encoding="utf-8")
    print(f"HTML audit report written: {out} ({len(payload.get('findings', []))} findings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
