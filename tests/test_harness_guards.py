#!/usr/bin/env python3
"""Regression tests for gravity-harness-fix guards, telemetry, installer, and auditor."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "plugin" / "hooks"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "plugin" / "skills" / "agile-swarm" / "scripts"))

import guard_and_log  # noqa: E402
import install_harness  # noqa: E402
import audit_transcripts  # noqa: E402
import worktree_team  # noqa: E402


class GuardHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.logs_dir = Path(self.tmp.name) / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.base_payload = {
            "conversationId": "test-conv-1",
            "workspacePaths": ["C:/work/demo"],
            "stepIdx": 12,
            "modelName": "test-model",
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_polling_loop_blocked_after_rapid_repeat(self) -> None:
        payload = {
            **self.base_payload,
            "toolCall": {"name": "manage_task", "args": {"Action": "status", "TaskId": "t-1"}},
        }
        r1 = guard_and_log._handle_pre_tool(payload, self.logs_dir)
        self.assertEqual(r1["decision"], "allow")

        r2 = guard_and_log._handle_pre_tool(payload, self.logs_dir)
        self.assertEqual(r2["decision"], "deny")
        self.assertIn("polling", r2["reason"].lower())

        issues = (self.logs_dir / "session-issues.jsonl").read_text(encoding="utf-8")
        self.assertIn("polling_loop_blocked", issues)

    def test_multiline_inline_script_blocked_and_short_allowed(self) -> None:
        short_ok = {
            **self.base_payload,
            "toolCall": {"name": "run_command", "args": {"CommandLine": "python -c \"print(123)\""}},
        }
        self.assertEqual(guard_and_log._handle_pre_tool(short_ok, self.logs_dir)["decision"], "allow")

        bad_multiline = {
            **self.base_payload,
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "python -c \"\nimport sys\nimport json\nprint(1)\n\""},
            },
        }
        r_bad = guard_and_log._handle_pre_tool(bad_multiline, self.logs_dir)
        self.assertEqual(r_bad["decision"], "deny")
        self.assertIn("multiline inline script", r_bad["reason"].lower())

        bad_node = {
            **self.base_payload,
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "node -e \"\nconst x = 1;\nconst y = 2;\nconsole.log(x+y);\n\""},
            },
        }
        self.assertEqual(guard_and_log._handle_pre_tool(bad_node, self.logs_dir)["decision"], "deny")

    def test_unguarded_export_and_grep_false_positive_filter(self) -> None:
        grep_ok = {
            **self.base_payload,
            "toolCall": {"name": "run_command", "args": {"CommandLine": "rg -n db_export scripts/"}},
        }
        self.assertEqual(guard_and_log._handle_pre_tool(grep_ok, self.logs_dir)["decision"], "allow")

        unsafe_export = {
            **self.base_payload,
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "python -m app.tools.db_export --all"},
            },
        }
        self.assertEqual(guard_and_log._handle_pre_tool(unsafe_export, self.logs_dir)["decision"], "ask")

        safe_export = {
            **self.base_payload,
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "python -m app.tools.db_export --run-id batch-1"},
            },
        }
        self.assertEqual(guard_and_log._handle_pre_tool(safe_export, self.logs_dir)["decision"], "allow")

    def test_windows_posix_scripts_unittest_guard(self) -> None:
        payload = {
            **self.base_payload,
            "toolCall": {"name": "run_command", "args": {"CommandLine": "python -m unittest discover -s scripts -p test_*.py"}},
        }
        res = guard_and_log._handle_pre_tool(payload, self.logs_dir)
        if os.name == "nt":
            self.assertEqual(res["decision"], "deny")
        else:
            self.assertEqual(res["decision"], "allow")

        wsl_ok = {
            **self.base_payload,
            "toolCall": {"name": "run_command", "args": {"CommandLine": "wsl -e python3 -m unittest discover -s scripts"}},
        }
        self.assertEqual(guard_and_log._handle_pre_tool(wsl_ok, self.logs_dir)["decision"], "allow")

    def test_blind_edit_retry_blocked_until_read(self) -> None:
        edit_payload = {
            **self.base_payload,
            "toolCall": {"name": "edit_file", "args": {"Path": "C:/work/demo/app.py"}},
        }
        self.assertEqual(guard_and_log._handle_pre_tool(edit_payload, self.logs_dir)["decision"], "allow")

        # Record edit failure in PostToolUse
        guard_and_log._handle_post_tool({**edit_payload, "error": "target not found"}, self.logs_dir)

        # Immediate second edit without reading must be blocked
        r_block = guard_and_log._handle_pre_tool(edit_payload, self.logs_dir)
        self.assertEqual(r_block["decision"], "deny")

        # Reading clears block
        read_payload = {
            **self.base_payload,
            "toolCall": {"name": "read_file", "args": {"Path": "C:/work/demo/app.py", "StartLine": 1, "EndLine": 50}},
        }
        guard_and_log._handle_post_tool(read_payload, self.logs_dir)
        self.assertEqual(guard_and_log._handle_pre_tool(edit_payload, self.logs_dir)["decision"], "allow")

    def test_duplicate_identical_read_blocked_and_reset_on_edit(self) -> None:
        read_payload = {
            **self.base_payload,
            "toolCall": {"name": "read_file", "args": {"Path": "C:/work/demo/mod.py", "StartLine": 10, "EndLine": 90}},
        }
        self.assertEqual(guard_and_log._handle_pre_tool(read_payload, self.logs_dir)["decision"], "allow")
        guard_and_log._handle_post_tool(read_payload, self.logs_dir)

        r_dup = guard_and_log._handle_pre_tool(read_payload, self.logs_dir)
        self.assertEqual(r_dup["decision"], "deny")

        # Editing the file invalidates duplicate-read cache
        edit_payload = {
            **self.base_payload,
            "toolCall": {"name": "edit_file", "args": {"Path": "C:/work/demo/mod.py"}},
        }
        guard_and_log._handle_post_tool(edit_payload, self.logs_dir)
        self.assertEqual(guard_and_log._handle_pre_tool(read_payload, self.logs_dir)["decision"], "allow")

    def test_empty_rg_exit_1_not_logged_as_error(self) -> None:
        rg_post = {
            **self.base_payload,
            "toolCall": {"name": "run_command", "args": {"CommandLine": "rg -n missing_sym src/"}},
            "error": "exit status 1",
        }
        guard_and_log._handle_post_tool(rg_post, self.logs_dir)
        self.assertFalse((self.logs_dir / "session-issues.jsonl").exists())

    def test_stop_allows_reactive_wait_when_not_fully_idle(self) -> None:
        res = guard_and_log._handle_stop(
            {**self.base_payload, "terminationReason": "NO_TOOL_CALL", "fullyIdle": False},
            self.logs_dir,
        )
        self.assertEqual(res, {})

        res_err = guard_and_log._handle_stop(
            {**self.base_payload, "terminationReason": "ERROR", "error": "stream dropped"},
            self.logs_dir,
        )
        self.assertEqual(res_err, {})
        self.assertIn("session_stop_error", (self.logs_dir / "session-issues.jsonl").read_text(encoding="utf-8"))

    def test_session_start_injects_system_message(self) -> None:
        res = guard_and_log._handle_session_start(self.base_payload, self.logs_dir)
        steps = res.get("injectSteps", [])
        self.assertEqual(len(steps), 1)
        msg = steps[0]["systemMessage"]["systemMessage"]
        self.assertIn("gravity-harness-fix active", msg)

    def test_parallel_inherit_write_subagent_blocked_while_share_and_research_allowed(self) -> None:
        inherit_coder = {
            **self.base_payload,
            "toolCall": {"name": "invoke_subagent", "args": {"TypeName": "self", "Role": "Coder 1", "Workspace": "inherit"}},
        }
        self.assertEqual(guard_and_log._handle_pre_tool(inherit_coder, self.logs_dir)["decision"], "allow")

        # 2nd concurrent write-capable subagent in inherit workspace must be denied immediately
        inherit_coder_2 = {
            **self.base_payload,
            "toolCall": {"name": "invoke_subagent", "args": {"TypeName": "self", "Role": "Coder 2"}},
        }
        r_block = guard_and_log._handle_pre_tool(inherit_coder_2, self.logs_dir)
        self.assertEqual(r_block["decision"], "deny")
        self.assertIn("Workspace='share'", r_block["reason"])

        # Switching to Workspace='share' succeeds without burning extra quota from the denied call
        share_coder_2 = {
            **self.base_payload,
            "toolCall": {"name": "invoke_subagent", "args": {"TypeName": "self", "Role": "Coder 2", "Workspace": "share"}},
        }
        self.assertEqual(guard_and_log._handle_pre_tool(share_coder_2, self.logs_dir)["decision"], "allow")

        # Read-only research subagents are allowed in inherit alongside writers (3rd allowed spawn)
        researcher = {
            **self.base_payload,
            "toolCall": {"name": "invoke_subagent", "args": {"TypeName": "research", "Role": "Scanner", "Workspace": "inherit"}},
        }
        self.assertEqual(guard_and_log._handle_pre_tool(researcher, self.logs_dir)["decision"], "allow")

        # 4th concurrent subagent inside 120s triggers Plan B burst prompt ('ask')
        share_coder_4 = {
            **self.base_payload,
            "toolCall": {"name": "invoke_subagent", "args": {"TypeName": "self", "Role": "Coder 4", "Workspace": "share"}},
        }
        self.assertEqual(guard_and_log._handle_pre_tool(share_coder_4, self.logs_dir)["decision"], "ask")


class InstallerAndAuditorTests(unittest.TestCase):
    def test_install_and_uninstall_isolated_temp_profile(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td) / ".gemini"
            (fake_home / "config").mkdir(parents=True, exist_ok=True)
            cfg_path = fake_home / "config" / "config.json"
            cfg_path.write_text(json.dumps({"userSettings": {"autoExecutionPolicy": "EAGER"}}), encoding="utf-8")

            # Run installer against isolated fake profile via subprocess
            proc = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "install_harness.py"),
                    "--gemini-root",
                    str(fake_home),
                    "--only-explicit",
                    "--skip-wsl",
                    "--skip-env",
                    "--logs-dir",
                    str(Path(td) / "logs"),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            plugin_dir = fake_home / "config" / "plugins" / "gravity-harness-fix"
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            self.assertTrue((plugin_dir / "plugin.json").exists())
            self.assertTrue((plugin_dir / "hooks.json").exists())
            self.assertTrue((plugin_dir / "rules" / "AGENTS.md").exists())
            self.assertTrue((plugin_dir / "skills" / "gravity-session-doctor" / "SKILL.md").exists())
            self.assertTrue((plugin_dir / "skills" / "agile-swarm" / "SKILL.md").exists())
            self.assertTrue((plugin_dir / "skills" / "agile-swarm" / "scripts" / "worktree_team.py").exists())
            updated_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertEqual(updated_cfg["userSettings"]["autoExecutionPolicy"], "EAGER")
            self.assertTrue(updated_cfg["plugins"]["gravity-harness-fix"]["enabled"])

            # Verify clean uninstall on isolated profile
            u_proc = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "install_harness.py"),
                    "--uninstall",
                    "--gemini-root",
                    str(fake_home),
                    "--only-explicit",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(u_proc.returncode, 0, u_proc.stderr + u_proc.stdout)
            self.assertFalse(plugin_dir.exists())
            re_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertEqual(re_cfg["userSettings"]["autoExecutionPolicy"], "EAGER")
            self.assertNotIn("gravity-harness-fix", re_cfg["plugins"])

    def test_transcript_auditor_detects_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tf = Path(td) / "transcript.jsonl"
            lines = [
                {"step_index": 0, "created_at": "2026-11-11T10:00:00Z", "type": "USER_INPUT", "content": "<USER_REQUEST> fix bug </USER_REQUEST>"},
                {"step_index": 1, "created_at": "2026-11-11T10:00:05Z", "type": "PLANNER_RESPONSE", "tool_calls": [{"name": "manage_task", "args": {"Action": "status", "TaskId": "t1"}}]},
                {"step_index": 2, "created_at": "2026-11-11T10:00:06Z", "type": "GENERIC", "content": "Command exited with code 1\nUnicodeEncodeError: cp1252"},
                {"step_index": 3, "created_at": "2026-11-11T10:01:00Z", "type": "ERROR_MESSAGE", "content": "stream error"},
                {"step_index": 4, "created_at": "2026-11-11T10:02:00Z", "type": "PLANNER_RESPONSE", "tool_calls": []},
                {"step_index": 5, "created_at": "2026-11-11T10:02:15Z", "type": "USER_INPUT", "content": "چرا متوقف شدی ادامه بده"},
            ]
            tf.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
            rep = audit_transcripts.analyze_transcript("conv-demo", td, tf)
            self.assertEqual(rep["kind"], "user_chat")
            self.assertEqual(rep["manage_task_polls"], 1)
            self.assertEqual(rep["cmd_exit_nonzero"], 1)
            self.assertEqual(rep["cmd_error_types"].get("encoding_cp1252"), 1)
            self.assertEqual(rep["premature_stop_prompts"], 1)
            self.assertEqual(rep["api_error_steps"], 1)

    def test_worktree_team_create_list_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "demo-repo"
            repo.mkdir()
            for cmd in (
                ["git", "init", "-b", "main"],
                ["git", "config", "user.name", "Test User"],
                ["git", "config", "user.email", "test@example.com"],
            ):
                subprocess.run(cmd, cwd=repo, check=True, capture_output=True)
            (repo / "README.md").write_text("# demo\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

            created = worktree_team.create_worktrees(str(repo), ["slice-a", "slice-b"])
            self.assertEqual([c["status"] for c in created], ["created", "created"])
            wt_a = Path(created[0]["path"])
            wt_b = Path(created[1]["path"])
            self.assertTrue((wt_a / "README.md").exists())
            self.assertTrue((wt_b / "README.md").exists())

            listed = worktree_team.parse_worktree_porcelain(repo)
            self.assertEqual(len(listed), 3)

            # Dirty worktree must be skipped safely without --force
            (wt_a / "dirty.txt").write_text("wip\n", encoding="utf-8")
            res1 = worktree_team.cleanup_worktrees(str(repo), delete_branches=True)
            statuses1 = {Path(r["path"]).name: r["status"] for r in res1}
            self.assertEqual(statuses1["demo-repo-wt-slice-a"], "skipped_dirty")
            self.assertEqual(statuses1["demo-repo-wt-slice-b"], "removed+branch_deleted")

            # Forced cleanup removes dirty worktree and branch cleanly
            res2 = worktree_team.cleanup_worktrees(str(repo), force=True, delete_branches=True)
            self.assertEqual(len(res2), 1)
            self.assertEqual(res2[0]["status"], "removed+branch_deleted")
            self.assertFalse(wt_a.exists())


if __name__ == "__main__":
    unittest.main()
