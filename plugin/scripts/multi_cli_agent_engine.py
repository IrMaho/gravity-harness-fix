#!/usr/bin/env python3
"""Multi-Account Antigravity CLI Subagent Engine.

Manages isolated Antigravity CLI and agent instances across multiple Google
accounts and profiles (C:\\Gravity-2, C:\\Gravity-3, C:\\Gravity-6, etc.).
Allows spawning, messaging, monitoring, and terminating subagents on demand.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# Known root directories
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
GRAVITI_ISOLATE_DIR = Path(r"C:\Users\ASUS\Desktop\flutter_project\graviti_isolate")
if str(GRAVITI_ISOLATE_DIR) not in sys.path:
    sys.path.insert(0, str(GRAVITI_ISOLATE_DIR))

try:
    import launch_isolated
    import sync_profile
except ImportError:
    launch_isolated = None  # type: ignore
    sync_profile = None  # type: ignore

# Registry file for active CLI workers
STATE_DIR = ROOT_DIR / "logs" / ".state"
REGISTRY_FILE = STATE_DIR / "active_cli_workers.json"
STATE_DIR.mkdir(parents=True, exist_ok=True)

AGY_BIN = Path(r"C:\Gravity-5-1\home\.gemini\bin\agy.exe")


def _extract_account_info(b64_string: str) -> Optional[List[str]]:
    """Extract email addresses from base64 protobuf payload."""
    try:
        raw1 = base64.b64decode(b64_string)
    except Exception:
        return None
    chunks = re.findall(r'[A-Za-z0-9+/=]{30,}', raw1.decode('latin1', errors='ignore'))
    for c in chunks:
        for offset in range(4):
            sub = c[offset:]
            while len(sub) % 4 != 0:
                sub += '='
            try:
                dec = base64.b64decode(sub)
                emails = re.findall(rb'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', dec)
                if emails:
                    return [e.decode('latin1') for e in emails]
            except Exception:
                pass
    return None


def list_accounts() -> List[Dict[str, Any]]:
    """Scan all C:\\Gravity* profiles and return account metadata."""
    accounts = []
    
    # 1. Profiles on C:\
    c_root = Path("C:/")
    for child in sorted(c_root.iterdir()):
        name = child.name
        if not name.startswith("Gravity") or child.is_file():
            continue
        db_path = child / "User" / "globalStorage" / "state.vscdb"
        email = None
        if db_path.is_file():
            try:
                con = sqlite3.connect(str(db_path))
                cur = con.cursor()
                cur.execute("SELECT value FROM ItemTable WHERE key = 'antigravityUnifiedStateSync.userStatus'")
                row = cur.fetchone()
                if row and row[0]:
                    extracted = _extract_account_info(row[0])
                    if extracted:
                        email = extracted[0]
                con.close()
            except Exception:
                pass

        # Check fallback token files
        token_file = child / "home" / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
        if not email and token_file.is_file():
            try:
                data = json.loads(token_file.read_text(encoding="utf-8"))
                email = data.get("id_token_email")
            except Exception:
                pass

        if email:
            is_current = (name == "Gravity-5-1")
            accounts.append({
                "profile": name,
                "email": email,
                "path": str(child),
                "is_current": is_current,
                "ready": True
            })

    # 2. Host Profile
    host_db = Path(os.environ.get("APPDATA", "")) / "Antigravity IDE" / "User" / "globalStorage" / "state.vscdb"
    if host_db.is_file():
        try:
            con = sqlite3.connect(str(host_db))
            cur = con.cursor()
            cur.execute("SELECT value FROM ItemTable WHERE key = 'antigravityUnifiedStateSync.userStatus'")
            row = cur.fetchone()
            email = None
            if row and row[0]:
                extracted = _extract_account_info(row[0])
                if extracted:
                    email = extracted[0]
            con.close()
            if email:
                accounts.append({
                    "profile": "Host",
                    "email": email,
                    "path": str(host_db.parent.parent.parent),
                    "is_current": False,
                    "ready": True
                })
        except Exception:
            pass

    return accounts


def _find_profile_by_account(account_or_profile: str) -> Optional[Dict[str, Any]]:
    """Find matching profile by name (Gravity-2) or email address."""
    accs = list_accounts()
    target = account_or_profile.lower().strip()
    for a in accs:
        if a["profile"].lower() == target or a["email"].lower() == target:
            return a
    return None


def _load_workers_registry() -> Dict[str, Any]:
    if not REGISTRY_FILE.is_file():
        return {}
    try:
        return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_workers_registry(data: Dict[str, Any]) -> None:
    try:
        REGISTRY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"Warning saving registry: {e}")


def spawn_cli_agent(
    account: str,
    task_prompt: str,
    model: str = "gemini-3.8-flash-high",
    workspace: Optional[str] = None,
    title: Optional[str] = None
) -> Dict[str, Any]:
    """Spawn an isolated CLI subagent on the specified account/profile."""
    prof_meta = _find_profile_by_account(account)
    if not prof_meta:
        return {
            "success": False,
            "error": f"Account or profile '{account}' not found among configured accounts.",
            "available_accounts": [f"{a['profile']} ({a['email']})" for a in list_accounts()]
        }

    profile_name = prof_meta["profile"]
    profile_path = Path(prof_meta["path"])
    email = prof_meta["email"]

    # 1. Ensure fresh token sync
    if sync_profile and profile_name != "Gravity-3":
        try:
            sync_profile.sync_profile(str(profile_path), force_refresh=False)
        except Exception as e:
            print(f"Notice during profile sync: {e}")

    # 2. Worker ID & Title
    short_uuid = uuid.uuid4().hex[:8]
    worker_id = f"worker-{profile_name.lower()}-{short_uuid}"
    task_title = title or f"CLI Task on {email} [{short_uuid}]"

    # 3. Environment Preparation
    env = os.environ.copy()
    home_dir = profile_path / "home"
    if home_dir.is_dir():
        env["HOME"] = str(home_dir)
        env["USERPROFILE"] = str(home_dir)
        env["HOMEDRIVE"] = "C:"
        env["HOMEPATH"] = str(home_dir)[2:]
        env["ANTIGRAVITY_APP_DATA_DIR"] = str(home_dir / ".gemini" / "antigravity")
        env["ANTIGRAVITY_GEMINI_DIR"] = str(home_dir / ".gemini")

    # Pass isolated OAuth token
    token_file = home_dir / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
    if token_file.is_file():
        try:
            env["JETSKI_OAUTH_TOKEN"] = token_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    # 4. Workspace resolution
    work_dir = workspace
    if not work_dir or not Path(work_dir).is_dir():
        work_dir = str(ROOT_DIR)

    # 5. Launch via agentapi new-conversation
    cmd = [
        str(AGY_BIN),
        "agentapi",
        "new-conversation",
        f"--model={model}",
        f"--title={task_title}",
        task_prompt
    ]

    try:
        res = subprocess.run(
            cmd,
            env=env,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        if res.returncode != 0:
            return {
                "success": False,
                "error": f"Failed to spawn agentapi: {res.stderr or res.stdout}"
            }

        out_data = json.loads(res.stdout)
        new_conv = out_data.get("response", {}).get("newConversation", {})
        conv_id = new_conv.get("conversationId")

        if not conv_id:
            return {
                "success": False,
                "error": f"agentapi did not return conversationId: {res.stdout}"
            }

        # 6. Record in active registry
        record = {
            "worker_id": worker_id,
            "conversation_id": conv_id,
            "profile": profile_name,
            "email": email,
            "model": model,
            "title": task_title,
            "prompt": task_prompt,
            "workspace": work_dir,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "status": "RUNNING"
        }
        reg = _load_workers_registry()
        reg[worker_id] = record
        reg[conv_id] = record
        _save_workers_registry(reg)

        return {
            "success": True,
            "worker_id": worker_id,
            "conversation_id": conv_id,
            "profile": profile_name,
            "email": email,
            "model": model,
            "status": "RUNNING"
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Exception spawning CLI agent: {e}"
        }


def send_cli_task(worker_id_or_conv_id: str, prompt: str) -> Dict[str, Any]:
    """Send follow-up instruction to a running CLI subagent."""
    reg = _load_workers_registry()
    record = reg.get(worker_id_or_conv_id)
    conv_id = record.get("conversation_id", worker_id_or_conv_id) if record else worker_id_or_conv_id

    cmd = [
        str(AGY_BIN),
        "agentapi",
        "send-message",
        conv_id,
        prompt
    ]

    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=25
        )
        if res.returncode != 0:
            return {
                "success": False,
                "error": f"Failed to send message: {res.stderr or res.stdout}"
            }
        return {
            "success": True,
            "conversation_id": conv_id,
            "message_sent": prompt,
            "status": "SENT"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Exception sending task to CLI agent: {e}"
        }


def get_cli_agent_status(worker_id_or_conv_id: str, tail_lines: int = 15) -> Dict[str, Any]:
    """Get status, latest step, and responses of a CLI subagent."""
    reg = _load_workers_registry()
    record = reg.get(worker_id_or_conv_id, {})
    conv_id = record.get("conversation_id", worker_id_or_conv_id)

    app_dir = Path(r"C:\Gravity-5-1\home\.gemini\antigravity")
    transcript_path = app_dir / "brain" / conv_id / ".system_generated" / "logs" / "transcript.jsonl"

    if not transcript_path.is_file():
        # Also check profile-specific brain
        if record.get("profile"):
            alt_path = Path("C:/") / record["profile"] / "home" / ".gemini" / "antigravity" / "brain" / conv_id / ".system_generated" / "logs" / "transcript.jsonl"
            if alt_path.is_file():
                transcript_path = alt_path

    if not transcript_path.is_file():
        return {
            "worker_id": record.get("worker_id", worker_id_or_conv_id),
            "conversation_id": conv_id,
            "status": "INITIALIZING",
            "message": "Transcript file not yet available"
        }

    lines = transcript_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    total_steps = len(lines)
    latest_response = ""
    latest_status = "RUNNING"
    error_count = 0

    for l in lines:
        try:
            step = json.loads(l)
            if step.get("status") == "ERROR":
                error_count += 1
            if step.get("type") == "PLANNER_RESPONSE":
                latest_response = step.get("content", "")
                if step.get("status") == "DONE":
                    latest_status = "DONE"
        except Exception:
            pass

    recent_tail = lines[-tail_lines:] if lines else []

    return {
        "worker_id": record.get("worker_id", worker_id_or_conv_id),
        "conversation_id": conv_id,
        "profile": record.get("profile", "unknown"),
        "email": record.get("email", "unknown"),
        "status": latest_status,
        "total_steps": total_steps,
        "error_count": error_count,
        "latest_response": latest_response[:1000] if latest_response else "(awaiting response)",
        "recent_steps_count": len(recent_tail)
    }


def list_active_agents() -> List[Dict[str, Any]]:
    """List all registered CLI workers and check their current status."""
    reg = _load_workers_registry()
    unique_records = {}
    for k, v in reg.items():
        w_id = v.get("worker_id")
        if w_id:
            unique_records[w_id] = v

    results = []
    for w_id, rec in unique_records.items():
        st = get_cli_agent_status(w_id, tail_lines=5)
        results.append({
            "worker_id": w_id,
            "conversation_id": rec.get("conversation_id"),
            "profile": rec.get("profile"),
            "email": rec.get("email"),
            "status": st.get("status"),
            "total_steps": st.get("total_steps", 0),
            "title": rec.get("title")
        })
    return results


def terminate_cli_agent(worker_id_or_conv_id: str) -> Dict[str, Any]:
    """Terminate and unregister a CLI subagent."""
    reg = _load_workers_registry()
    record = reg.get(worker_id_or_conv_id)
    if not record:
        return {"success": False, "error": f"Agent {worker_id_or_conv_id} not found in registry."}

    w_id = record.get("worker_id")
    c_id = record.get("conversation_id")

    if w_id in reg:
        reg[w_id]["status"] = "TERMINATED"
    if c_id in reg:
        reg[c_id]["status"] = "TERMINATED"
    _save_workers_registry(reg)

    return {
        "success": True,
        "worker_id": w_id,
        "conversation_id": c_id,
        "status": "TERMINATED"
    }


if __name__ == "__main__":
    print("Testing Multi-Account CLI Subagent Engine:")
    accs = list_accounts()
    print(f"Discovered {len(accs)} accounts:")
    for a in accs:
        print(f"  - {a['profile']:12} -> {a['email']} (Current: {a['is_current']})")
