#!/usr/bin/env python3
"""Cross-profile installer / updater / uninstaller for gravity-harness-fix.

Installs the native Antigravity plugin into every discovered .gemini config
root on the machine (standard ~/.gemini plus any Gravity sandbox homes), writes
machine-local harness_config.json pointing telemetry logs back to this repo's
logs/ directory, enables UTF-8 Windows defaults, optionally ensures uv PATH in
WSL2, and runs a live smoke verification of the installed hooks.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_SRC = REPO_ROOT / "plugin"
PLUGIN_NAME = "gravity-harness-fix"


def discover_gemini_roots(extra_roots: list[str] | None = None) -> list[Path]:
    """Find all existing .gemini profile directories on this machine."""
    candidates: list[Path] = []
    for env_var in ("USERPROFILE", "HOME"):
        val = os.environ.get(env_var)
        if val:
            candidates.append(Path(val) / ".gemini")

    username = os.environ.get("USERNAME")
    if username:
        candidates.append(Path("C:/Users") / username / ".gemini")

    if os.name == "nt":
        for p in Path("C:/").glob("Gravity-*/home/.gemini"):
            candidates.append(p)

    for raw in extra_roots or []:
        candidates.append(Path(raw))

    unique: list[Path] = []
    seen: set[str] = set()
    for cand in candidates:
        try:
            key = str(cand.resolve()).lower()
        except OSError:
            key = str(cand).lower()
        if key not in seen and cand.exists():
            seen.add(key)
            unique.append(cand)
    return unique


def resolve_python_executable() -> str:
    """Return a real non-WindowsApps Python interpreter path."""
    exe = Path(sys.executable)
    if "windowsapps" not in str(exe).lower() and exe.exists():
        return str(exe)
    found = shutil.which("python")
    if found and "windowsapps" not in found.lower():
        return found
    return str(exe)


def _configure_installed_hooks(plugin_dest: Path, python_exe: str) -> None:
    """Configure installed hook launcher without cmd.exe nested-quote pitfalls."""
    if os.name == "nt":
        run_cmd = plugin_dest / "hooks" / "run_hook.cmd"
        run_cmd.write_text(
            f'@echo off\r\n"{python_exe}" -X utf8 "%~dp0guard_and_log.py" --event %1\r\n',
            encoding="utf-8",
        )
        return

    # POSIX (macOS/Linux): use direct python3 invocation cleanly in hooks.json
    hooks_file = plugin_dest / "hooks.json"
    data = json.loads(hooks_file.read_text(encoding="utf-8"))
    for hook_cfg in data.values():
        if not isinstance(hook_cfg, dict):
            continue
        for event_name in ("SessionStart", "Stop", "PreInvocation", "PostInvocation"):
            for handler in hook_cfg.get(event_name, []):
                if isinstance(handler, dict) and isinstance(handler.get("command"), str):
                    ev = handler["command"].split()[-1]
                    handler["command"] = f'"{python_exe}" -X utf8 hooks/guard_and_log.py --event {ev}'
        for event_name in ("PreToolUse", "PostToolUse"):
            for group in hook_cfg.get(event_name, []):
                if not isinstance(group, dict):
                    continue
                for handler in group.get("hooks", []):
                    if isinstance(handler, dict) and isinstance(handler.get("command"), str):
                        ev = handler["command"].split()[-1]
                        handler["command"] = f'"{python_exe}" -X utf8 hooks/guard_and_log.py --event {ev}'
    hooks_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _configure_installed_mcp(plugin_dest: Path, python_exe: str) -> None:
    """Rewrite installed mcp_config.json with resolved Python and absolute server path."""
    mcp_file = plugin_dest / "mcp_config.json"
    if not mcp_file.exists():
        return
    data = json.loads(mcp_file.read_text(encoding="utf-8"))
    servers = data.get("mcpServers")
    if isinstance(servers, dict):
        mem_srv = servers.get("gravity-memory")
        if isinstance(mem_srv, dict):
            mem_srv["command"] = python_exe
            mem_srv["args"] = ["-X", "utf8", str(plugin_dest / "mcp" / "memory_mcp_server.py")]
    mcp_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _update_config_json(config_dir: Path, *, enable: bool) -> None:
    cfg_path = config_dir / "config.json"
    data: dict[str, Any] = {}
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            backup_bad = config_dir / f"config.json.bak-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            shutil.copy2(cfg_path, backup_bad)
            data = {}
    plugins_map = data.setdefault("plugins", {})
    if enable:
        plugins_map[PLUGIN_NAME] = {"enabled": True}
    else:
        plugins_map.pop(PLUGIN_NAME, None)
    # Remove any misplaced entry under userSettings.plugins if present
    us_plugins = data.get("userSettings", {}).get("plugins")
    if isinstance(us_plugins, dict):
        us_plugins.pop(PLUGIN_NAME, None)
    cfg_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _ensure_windows_utf8_env() -> list[str]:
    changes: list[str] = []
    if os.name != "nt":
        return changes
    import winreg

    desired = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS) as key:
        for name, target_val in desired.items():
            try:
                cur_val, _ = winreg.QueryValueEx(key, name)
            except FileNotFoundError:
                cur_val = None
            if str(cur_val or "").lower() != target_val.lower():
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, target_val)
                changes.append(f"{name}={target_val}")
    if changes:
        try:
            ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 2000, None)
        except Exception:
            pass
    return changes


def _ensure_wsl_uv_path() -> str:
    if os.name != "nt" or not shutil.which("wsl"):
        return "skipped (wsl not present)"
    marker = "# gravity-harness-fix: uv PATH"
    script = (
        "set -e; "
        f"for f in \"$HOME/.bashrc\" \"$HOME/.profile\"; do "
        f"[ -f \"$f\" ] || touch \"$f\"; "
        f"grep -qF '{marker}' \"$f\" || printf '\\n{marker}\\nexport PATH=\"$HOME/.local/bin:$HOME/.cargo/bin:$PATH\"\\n' >> \"$f\"; "
        "done; "
        "echo wsl_path_ok"
    )
    try:
        res = subprocess.run(["wsl", "-e", "bash", "-c", script], capture_output=True, text=True, timeout=15)
        if res.returncode == 0:
            return "configured ~/.bashrc & ~/.profile"
        return f"warn exit={res.returncode}: {res.stderr.strip()[:120]}"
    except Exception as exc:
        return f"skipped ({exc})"


def _smoke_test_installed_plugin(plugin_dest: Path, python_exe: str, logs_dir: Path) -> None:
    hooks_data = json.loads((plugin_dest / "hooks.json").read_text(encoding="utf-8"))
    pre_cmd = hooks_data["gravity-harness-fix-guards"]["PreToolUse"][0]["hooks"][0]["command"]
    # Test PreToolUse blocking polling loop through the exact platform shell Antigravity uses
    payload = json.dumps(
        {
            "conversationId": "smoke-test-conv",
            "stepIdx": 10,
            "toolCall": {"name": "manage_task", "args": {"Action": "status", "TaskId": "smoke-task"}},
        }
    )
    shell_cmd = ["cmd", "/c", pre_cmd] if os.name == "nt" else ["sh", "-c", pre_cmd]
    # First call allowed, subsequent rapid poll blocked
    for idx in (1, 2):
        res = subprocess.run(
            shell_cmd,
            input=payload,
            capture_output=True,
            text=True,
            cwd=str(plugin_dest),
            timeout=10,
        )
        if res.returncode != 0:
            raise RuntimeError(f"Smoke test run {idx} exited {res.returncode}: {res.stderr} | cmd={pre_cmd}")
        parsed = json.loads(res.stdout)
        if idx == 1 and parsed.get("decision") != "allow":
            raise RuntimeError(f"Expected allow on first poll, got {parsed}")
        if idx == 2 and parsed.get("decision") != "deny":
            raise RuntimeError(f"Expected deny on rapid repeat poll, got {parsed}")

    # Clean up smoke-test entries so real telemetry stays signal-only
    state_smoke = logs_dir / ".state" / "smoke-test-conv.json"
    if state_smoke.exists():
        state_smoke.unlink()
    log_file = logs_dir / "session-issues.jsonl"
    if log_file.exists():
        kept = [
            ln
            for ln in log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            if '"conv_id": "smoke-test-conv"' not in ln
        ]
        if kept:
            log_file.write_text("\n".join(kept) + "\n", encoding="utf-8")
        else:
            log_file.unlink()
            summary = logs_dir / "latest-summary.md"
            if summary.exists():
                summary.unlink()


def _prune_stale_plugin_files(src: Path, dest: Path) -> None:
    expected = {p.relative_to(src) for p in src.rglob("*") if "__pycache__" not in p.parts}
    expected_dirs = {d for rel in expected for d in rel.parents}
    for cur in sorted(dest.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        rel = cur.relative_to(dest)
        if "__pycache__" in rel.parts or rel == Path("harness_config.json"):
            continue
        try:
            if cur.is_file() or cur.is_symlink():
                if rel not in expected:
                    cur.unlink()
            elif cur.is_dir():
                if rel not in expected and rel not in expected_dirs:
                    cur.rmdir()
        except OSError:
            pass  # Fail-safe on Windows when an active IDE/MCP handle locks a running directory


def install_all(
    extra_roots: list[str],
    *,
    skip_wsl: bool,
    only_explicit: bool = False,
    skip_env: bool = False,
    logs_dir_override: str = "",
) -> int:
    if only_explicit:
        roots = [Path(r) for r in extra_roots if Path(r).exists()]
    else:
        roots = discover_gemini_roots(extra_roots)
    if not roots:
        print("ERROR: No .gemini root directory found. Pass --gemini-root <path>.", file=sys.stderr)
        return 1

    python_exe = resolve_python_executable()
    logs_dir = Path(logs_dir_override) if logs_dir_override else (REPO_ROOT / "logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    print(f"Installing {PLUGIN_NAME} from: {REPO_ROOT}")
    print(f"Using Python executable: {python_exe}")
    print(f"Shared telemetry logs dir: {logs_dir}")
    print(f"Target .gemini profiles ({len(roots)}):")

    first_installed_dest: Path | None = None
    for root in roots:
        config_dir = root / "config"
        plugins_dir = config_dir / "plugins"
        dest = plugins_dir / PLUGIN_NAME
        backup_dir = config_dir / "backups" / PLUGIN_NAME / ts_tag

        plugins_dir.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(dest, backup_dir / PLUGIN_NAME, dirs_exist_ok=True)
            # Sync in place instead of rmtree so active Windows IDE/MCP handles never hit WinError 32

        shutil.copytree(
            PLUGIN_SRC,
            dest,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        _prune_stale_plugin_files(PLUGIN_SRC, dest)
        _configure_installed_hooks(dest, python_exe)
        _configure_installed_mcp(dest, python_exe)

        harness_cfg = {
            "sourceRepoDir": str(REPO_ROOT),
            "logsDir": str(logs_dir),
            "fallbackLogsDir": str(root / "gravity-harness-logs"),
            "installedAtUtc": ts_tag,
            "pythonExecutable": python_exe,
        }
        (dest / "harness_config.json").write_text(
            json.dumps(harness_cfg, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        _update_config_json(config_dir, enable=True)
        print(f"  [OK] {dest}")
        if first_installed_dest is None:
            first_installed_dest = dest

    env_changes = [] if skip_env else _ensure_windows_utf8_env()
    if skip_env:
        print("Windows User UTF-8 env: skipped (--skip-env)")
    else:
        print(f"Windows User UTF-8 env: {', '.join(env_changes) if env_changes else 'already set (PYTHONIOENCODING=utf-8, PYTHONUTF8=1)'}")

    wsl_status = "skipped (--skip-wsl)" if skip_wsl else _ensure_wsl_uv_path()
    print(f"WSL2 PATH setup: {wsl_status}")

    if first_installed_dest:
        _smoke_test_installed_plugin(first_installed_dest, python_exe, logs_dir)
        print("Live hook smoke test: [PASS]")

    print("\nInstallation complete! Restart/open a new Antigravity chat to load updated hooks and rules.")
    return 0


def uninstall_all(extra_roots: list[str], *, only_explicit: bool = False) -> int:
    roots = [Path(r) for r in extra_roots if Path(r).exists()] if only_explicit else discover_gemini_roots(extra_roots)
    removed = 0
    for root in roots:
        config_dir = root / "config"
        dest = config_dir / "plugins" / PLUGIN_NAME
        if dest.exists():
            # Sync in place instead of rmtree so active Windows IDE/MCP handles never hit WinError 32
            shutil.rmtree(dest, ignore_errors=True)
            removed += 1
            print(f"  [REMOVED] {dest}")
        if (config_dir / "config.json").exists():
            _update_config_json(config_dir, enable=False)
    print(f"Uninstall complete ({removed} plugin installation(s) removed).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Install or uninstall gravity-harness-fix plugin.")
    parser.add_argument("--uninstall", action="store_true", help="Remove plugin from all discovered .gemini profiles")
    parser.add_argument("--gemini-root", action="append", default=[], help="Extra .gemini root directory")
    parser.add_argument("--only-explicit", action="store_true", help="Target only --gemini-root paths (skip host discovery)")
    parser.add_argument("--skip-wsl", action="store_true", help="Skip checking/updating WSL2 ~/.bashrc PATH")
    parser.add_argument("--skip-env", action="store_true", help="Skip modifying Windows User env vars")
    parser.add_argument("--logs-dir", default="", help="Override telemetry logs directory")
    args = parser.parse_args()

    if args.uninstall:
        return uninstall_all(args.gemini_root, only_explicit=args.only_explicit)
    return install_all(
        args.gemini_root,
        skip_wsl=args.skip_wsl,
        only_explicit=args.only_explicit,
        skip_env=args.skip_env,
        logs_dir_override=args.logs_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
