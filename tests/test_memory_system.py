import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MEM_SCRIPTS = REPO_ROOT / "plugin" / "skills" / "memory-sync" / "scripts"
MCP_SERVER = REPO_ROOT / "plugin" / "mcp" / "memory_mcp_server.py"
GUARD_HOOK = REPO_ROOT / "plugin" / "hooks" / "guard_and_log.py"
INSTALLER = REPO_ROOT / "scripts" / "install_harness.py"

if str(MEM_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(MEM_SCRIPTS))
import memory_engine  # noqa: E402


def _run_hook(event: str, payload: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(GUARD_HOOK), "--event", event],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=10,
    )
    return json.loads(proc.stdout or "{}")


class FiveLayerMemoryIntegrationTests(unittest.TestCase):
    def test_mcp_stdio_roundtrip_hydrate_index_symbol_search_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "sample_repo"
            (ws / "lib").mkdir(parents=True)
            (ws / "lib" / "auth_service.py").write_text(
                "class AuthService:\n"
                "    def verify_jwt_token(self, token: str) -> bool:\n"
                "        return token.startswith('ok_')\n",
                encoding="utf-8",
            )
            reqs = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "memory_reindex", "arguments": {"workspace": str(ws)}}},
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "symbol_lookup", "arguments": {"workspace": str(ws), "query": "verify_jwt_token"}}},
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_checkpoint",
                        "arguments": {
                            "workspace": str(ws),
                            "active_task": "Harden JWT verifier",
                            "status": "in_progress",
                            "verified_tests": ["unit:3/3 ok"],
                            "next_steps": ["Add expiry check"],
                            "note_shard": "decisions",
                            "note_title": "Strict prefix check",
                            "note_body": "Reject malformed tokens before decode.",
                        },
                    },
                },
                {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "memory_search", "arguments": {"workspace": str(ws), "query": "malformed tokens"}}},
                {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "memory_hydrate", "arguments": {"workspace": str(ws)}}},
            ]
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", str(MCP_SERVER)],
                input="\n".join(json.dumps(r) for r in reqs) + "\n",
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
                timeout=15,
            )
            resps = {r["id"]: r for r in (json.loads(ln) for ln in proc.stdout.splitlines() if ln.strip())}
            self.assertEqual(len(resps), 7)  # notification did not emit a response
            tool_names = {t["name"] for t in resps[2]["result"]["tools"]}
            self.assertEqual(tool_names, {"memory_hydrate", "symbol_lookup", "memory_search", "memory_checkpoint", "memory_reindex"})

            sym_payload = json.loads(resps[4]["result"]["content"][0]["text"])
            self.assertFalse(resps[4]["result"]["isError"])
            self.assertEqual(sym_payload[0]["name"], "AuthService.verify_jwt_token")
            self.assertEqual(sym_payload[0]["start_line"], 2)

            chk_payload = json.loads(resps[5]["result"]["content"][0]["text"])
            self.assertEqual(chk_payload["state"]["verified_tests"], "unit:3/3 ok")

            search_payload = json.loads(resps[6]["result"]["content"][0]["text"])
            self.assertTrue(any("decisions" in hit["source"] for hit in search_payload), f"Missing hit: {search_payload}")

            brief = resps[7]["result"]["content"][0]["text"]
            self.assertIn("Harden JWT verifier", brief)
            self.assertLessEqual(len(brief), 650)

    def test_hooks_block_big_unranged_read_reindex_on_edit_and_hydrate_session_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            ws.mkdir()
            big_file = ws / "big_module.py"
            big_file.write_text("\n".join(f"def fn_{i}():\n    return {i}" for i in range(160)) + "\n", encoding="utf-8")

            # Un-ranged big file read (>260 lines, >5KB) must be blocked by L0 guard
            res_block = _run_hook(
                "PreToolUse",
                {
                    "conversationId": "mem-hook-test",
                    "stepIdx": 1,
                    "workspacePaths": [str(ws)],
                    "toolCall": {"name": "read_file", "args": {"Path": str(big_file)}},
                },
            )
            self.assertEqual(res_block.get("decision"), "deny")

            # Explicit ranged read (<=200 lines) must be allowed
            res_allow = _run_hook(
                "PreToolUse",
                {
                    "conversationId": "mem-hook-test",
                    "stepIdx": 2,
                    "workspacePaths": [str(ws)],
                    "toolCall": {"name": "read_file", "args": {"Path": str(big_file), "StartLine": 1, "EndLine": 80}},
                },
            )
            self.assertEqual(res_allow.get("decision"), "allow")

            # Initialize L2 + DB and test PostToolUse L1 incremental reindex on newly edited file
            memory_engine.checkpoint_state(ws, active_task="Hook hydration test", verified_tests="19/19 ok")
            new_file = ws / "new_helper.py"
            new_file.write_text("def freshly_added_symbol():\n    return 42\n", encoding="utf-8")
            _run_hook(
                "PostToolUse",
                {
                    "conversationId": "mem-hook-test",
                    "stepIdx": 3,
                    "workspacePaths": [str(ws)],
                    "toolCall": {"name": "write_file", "args": {"Path": str(new_file)}, "error": ""},
                },
            )
            syms = memory_engine.lookup_symbol(ws, "freshly_added_symbol")
            self.assertTrue(syms and syms[0]["name"] == "freshly_added_symbol")

            # SessionStart must inject [L2 Memory] brief
            res_start = _run_hook("SessionStart", {"conversationId": "mem-hook-test", "workspacePaths": [str(ws)]})
            msg = res_start["injectSteps"][0]["systemMessage"]["systemMessage"]
            self.assertIn("[L2 Memory]", msg)
            self.assertIn("Hook hydration test", msg)

    def test_installer_configures_absolute_mcp_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            gemini_root = td / "profile" / ".gemini"
            gemini_root.mkdir(parents=True)
            logs_dir = td / "logs"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(INSTALLER),
                    "--gemini-root",
                    str(gemini_root),
                    "--only-explicit",
                    "--skip-wsl",
                    "--skip-env",
                    "--logs-dir",
                    str(logs_dir),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
                timeout=20,
            )
            self.assertIn("Live hook smoke test: [PASS]", proc.stdout)
            mcp_cfg = json.loads((gemini_root / "config" / "plugins" / "gravity-harness-fix" / "mcp_config.json").read_text(encoding="utf-8"))
            srv = mcp_cfg["mcpServers"]["gravity-memory"]
            self.assertTrue(Path(srv["args"][-1]).is_file())
            self.assertTrue(srv["args"][-1].endswith("memory_mcp_server.py"))


if __name__ == "__main__":
    unittest.main()
