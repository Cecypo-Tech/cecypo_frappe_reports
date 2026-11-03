# Copyright (c) 2026, Cecypo.Tech and contributors
# For license information, please see license.txt

import os

import frappe
from frappe.tests.utils import FrappeTestCase

import cecypo_frappe_reports
from cecypo_frappe_reports.party_statement import SCRIPT_NAME, get_party_statement_script, seed_client_script

SHIPPED = os.path.join(os.path.dirname(cecypo_frappe_reports.__file__), "client_scripts", "party_statement.js")


class TestPartyStatementScript(FrappeTestCase):
	"""The statement script is created once and then belongs to the site: never
	overwritten, never re-enabled. Not a fixture for that reason."""

	def setUp(self):
		frappe.db.delete("Client Script", {"name": SCRIPT_NAME})

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_seed_creates_enabled_customer_form_script(self):
		seed_client_script()
		doc = frappe.get_doc("Client Script", SCRIPT_NAME)
		self.assertEqual(doc.dt, "Customer")
		self.assertEqual(doc.view, "Form")
		self.assertEqual(doc.enabled, 1)
		self.assertFalse(doc.module)
		with open(SHIPPED) as f:
			self.assertEqual(doc.script, f.read())

	def test_seed_never_overwrites(self):
		seed_client_script()
		frappe.db.set_value("Client Script", SCRIPT_NAME, "script", "// mine")
		seed_client_script()
		self.assertEqual(frappe.db.get_value("Client Script", SCRIPT_NAME, "script"), "// mine")

	def test_seed_keeps_disabled(self):
		seed_client_script()
		frappe.db.set_value("Client Script", SCRIPT_NAME, "enabled", 0)
		seed_client_script()
		self.assertEqual(frappe.db.get_value("Client Script", SCRIPT_NAME, "enabled"), 0)

	def test_getter_returns_source_when_enabled(self):
		seed_client_script()
		self.assertIn("cecypo.party_statement", get_party_statement_script("Customer"))
		self.assertIn("cecypo.party_statement", get_party_statement_script("Supplier"))

	def test_getter_none_when_disabled(self):
		seed_client_script()
		frappe.db.set_value("Client Script", SCRIPT_NAME, "enabled", 0)
		self.assertIsNone(get_party_statement_script("Customer"))

	def test_getter_none_when_missing(self):
		self.assertIsNone(get_party_statement_script("Customer"))

	def test_getter_permission(self):
		seed_client_script()
		frappe.set_user("Guest")
		for party_type in ("Customer", "Supplier"):
			with self.assertRaises(frappe.PermissionError):
				get_party_statement_script(party_type)
