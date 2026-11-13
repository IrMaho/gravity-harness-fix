import unittest
from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "plugin" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import multi_cli_agent_engine


class TestMultiCliAgentEngine(unittest.TestCase):
    def test_list_accounts(self):
        accounts = multi_cli_agent_engine.list_accounts()
        self.assertIsInstance(accounts, list)
        self.assertGreater(len(accounts), 0, "Must discover at least 1 account")
        
        # Verify required keys
        for a in accounts:
            self.assertIn("profile", a)
            self.assertIn("email", a)
            self.assertIn("ready", a)
            self.assertIn("path", a)

    def test_find_profile_by_account(self):
        acc = multi_cli_agent_engine._find_profile_by_account("Gravity-2")
        self.assertIsNotNone(acc)
        self.assertEqual(acc.get("profile"), "Gravity-2")
        self.assertIn("@", acc.get("email", ""))


if __name__ == "__main__":
    unittest.main()
