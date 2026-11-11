import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "plugin" / "skills"


def _load_module(rel_path: str, name: str):
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


conservation = _load_module("plugin/skills/lossless-modularize/scripts/conservation_audit.py", "conservation_audit")
audit_html = _load_module("plugin/skills/forensic-audit/scripts/generate_audit_report.py", "generate_audit_report")
figma_ui = _load_module("plugin/skills/figma-to-prod/scripts/verify_figma_ui.py", "verify_figma_ui")
readme_ver = _load_module("plugin/skills/truthful-readme/scripts/verify_readme.py", "verify_readme")


class SkillCatalogIntegrityTests(unittest.TestCase):
    EXPECTED_SKILLS = {
        "agile-swarm",
        "gravity-session-doctor",
        "pro-dev",
        "repo-onboard",
        "forensic-audit",
        "harden-fix",
        "lossless-modularize",
        "figma-to-prod",
        "truthful-readme",
    }

    def test_all_skills_have_valid_frontmatter_and_links(self):
        found = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}
        self.assertTrue(self.EXPECTED_SKILLS.issubset(found), f"Missing skills: {self.EXPECTED_SKILLS - found}")
        for skill_name in sorted(self.EXPECTED_SKILLS):
            skill_md = SKILLS_DIR / skill_name / "SKILL.md"
            self.assertTrue(skill_md.exists(), f"Missing {skill_md}")
            text = skill_md.read_text(encoding="utf-8")
            self.assertLess(len(text.encode("utf-8")), 8192, f"SKILL.md too bloated: {skill_name}")
            m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
            self.assertIsNotNone(m, f"Missing YAML frontmatter in {skill_name}")
            fm = m.group(1)
            self.assertRegex(fm, rf"(?m)^name:\s*{re.escape(skill_name)}\s*$")
            self.assertRegex(fm, r"(?m)^description:\s*\S+")
            # Verify local relative markdown links inside SKILL.md exist
            for lm in re.finditer(r"\[[^\]]+\]\((\./[^)]+)\)", text):
                target = (skill_md.parent / lm.group(1)).resolve()
                self.assertTrue(target.exists(), f"Broken link {lm.group(1)} in {skill_name}/SKILL.md")

    def test_rules_under_24kb_limit(self):
        agents_md = REPO_ROOT / "plugin" / "rules" / "AGENTS.md"
        size = agents_md.stat().st_size
        self.assertLess(size, 24000, f"AGENTS.md exceeds Antigravity 24KB limit ({size} bytes)")


class ConservationAuditTests(unittest.TestCase):
    def test_lossless_split_passes_and_dropped_symbol_or_cycle_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            mono = td / "mono.py"
            mono.write_text(
                "def alpha():\n    return 1\n\n"
                "def beta():\n    return alpha() + 2\n\n"
                "class Engine:\n    pass\n",
                encoding="utf-8",
            )
            snap = td / "baseline.json"
            self.assertEqual(conservation.cmd_baseline([str(mono)], str(snap)), 0)

            out_dir = td / "split"
            out_dir.mkdir()
            (out_dir / "helpers.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
            (out_dir / "core.py").write_text(
                "from .helpers import alpha\n\n"
                "def beta():\n    return alpha() + 2\n\n"
                "class Engine:\n    pass\n",
                encoding="utf-8",
            )
            self.assertEqual(conservation.cmd_verify(str(snap), [str(out_dir)], 400, 200, 0.90), 0)

            # Remove beta -> must fail symbol conservation
            (out_dir / "core.py").write_text("class Engine:\n    pass\n", encoding="utf-8")
            self.assertEqual(conservation.cmd_verify(str(snap), [str(out_dir)], 400, 200, 0.50), 1)

            # Circular relative import -> must fail even with symbols intact
            (out_dir / "helpers.py").write_text("from .core import Engine\n\ndef alpha():\n    return 1\n", encoding="utf-8")
            (out_dir / "core.py").write_text(
                "from .helpers import alpha\n\n"
                "def beta():\n    return alpha() + 2\n\n"
                "class Engine:\n    pass\n",
                encoding="utf-8",
            )
            self.assertEqual(conservation.cmd_verify(str(snap), [str(out_dir)], 400, 200, 0.50), 1)


class AuditHtmlAndReadmeAndFigmaTests(unittest.TestCase):
    def test_generate_audit_html_escapes_and_renders(self):
        payload = json.loads(json.dumps(audit_html.TEMPLATE_PAYLOAD))
        payload["findings"][0]["title"] = "XSS <script>alert(1)</script> check"
        html_out = audit_html.build_html(payload)
        self.assertIn("Forensic Audit", html_out)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html_out)
        self.assertNotIn("<script>alert(1)</script>", html_out)

    def test_figma_ui_verifier_catches_inline_svg_manual_path_and_dup_svg(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            (td / "assets" / "icons").mkdir(parents=True)
            (td / "assets" / "icons" / "home.svg").write_text("<svg></svg>", encoding="utf-8")
            (td / "lib" / "core" / "icons").mkdir(parents=True)
            (td / "lib" / "core" / "icons" / "app_icon.dart").write_text("class AppIcon {}\n", encoding="utf-8")
            res_ok = figma_ui.scan_ui(td)
            self.assertEqual(res_ok["status"], "PASS")

            # Introduce manual Dart Path geometry + inline JSX <svg> + duplicate svg name
            (td / "assets" / "dup").mkdir(parents=True)
            (td / "assets" / "dup" / "home.svg").write_text("<svg></svg>", encoding="utf-8")
            (td / "lib" / "bad_icon.dart").write_text(
                "class Bad extends CustomPainter { void paint() { final p = Path(); p.moveTo(0, 0); } }\n",
                encoding="utf-8",
            )
            (td / "bad.tsx").write_text("export const Card = () => <div><svg><path/></svg></div>;\n", encoding="utf-8")
            res_bad = figma_ui.scan_ui(td)
            self.assertEqual(res_bad["status"], "FAIL")
            self.assertTrue(res_bad["manual_path_violations"])
            self.assertTrue(res_bad["inline_svg_violations"])
            self.assertIn("home.svg", res_bad["duplicate_svg_assets"])

    def test_readme_verifier_passes_real_repo_readme_and_catches_broken(self):
        for rel in ("README.md", "docs/README.fa.md", "docs/README.ar.md"):
            real_res = readme_ver.verify_markdown(REPO_ROOT / rel, REPO_ROOT)
            self.assertEqual(real_res["status"], "PASS", f"Repo doc {rel} failed: {real_res}")

        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            bad = td / "README.md"
            bad.write_text("# Demo\nSee [Missing](./nope.md) and [BadAnchor](#none).\nTODO: finish\n", encoding="utf-8")
            res = readme_ver.verify_markdown(bad, td)
            self.assertEqual(res["status"], "FAIL")
            self.assertEqual(len(res["broken_links"]), 2)
            self.assertEqual(len(res["placeholders"]), 1)


if __name__ == "__main__":
    unittest.main()
