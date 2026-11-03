# Copyright (c) 2026, Cecypo.Tech and contributors
# For license information, please see license.txt

import os
import shutil
import subprocess
import unittest

TEST_FILE = os.path.join(os.path.dirname(__file__), "js", "party_statement.test.mjs")


class TestPartyStatementJS(unittest.TestCase):
	"""Runs the Node unit tests for client_scripts/party_statement.js, the default
	statement script seeded onto each site, so `bench run-tests` covers it too."""

	def test_node_suite_passes(self):
		node = shutil.which("node")
		if not node:
			self.skipTest("node is not installed")
		proc = subprocess.run([node, "--test", TEST_FILE], capture_output=True, text=True, timeout=120)
		self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
