# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import functools
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_months, getdate, today

from cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts import (
	_build_statement_doc,
	_resolve_recipients,
	email_statement,
	get_default_recipient,
	get_statement_templates,
	render_statement_html,
)

TEST_COMPANY = "_Test Company"
TEST_CUSTOMER = "_Test Customer"
OTHER_CUSTOMER = "_Test Customer 1"

@functools.cache
def pdf_generation_works():
	"""Whether wkhtmltopdf can actually produce a PDF here.

	Presence of the binary is not enough: wkhtmltopdf fetches the print stylesheet over HTTP from
	the site itself, so it fails with a connection error whenever the bench web server is not up,
	which is the normal case for a test runner. The probe mirrors that by referencing a site asset.
	"""
	from frappe.utils.pdf import get_pdf

	try:
		get_pdf(
			'<html><head><link rel="stylesheet" href="/assets/frappe/dist/css/print.bundle.css">'
			"</head><body>probe</body></html>"
		)
		return True
	except Exception:
		return False


class TestStatementOfAccounts(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		# IntegrationTestCase rolls back once at class level, so per-test fixtures would leak
		# between methods. Isolate each test with its own savepoint, matching the convention in
		# test_transaction_history.py.
		self._savepoint = f"test_soa_{frappe.generate_hash(length=8)}"
		frappe.db.savepoint(self._savepoint)

	def tearDown(self):
		try:
			frappe.db.rollback(save_point=self._savepoint)
		except Exception:
			# A failed document operation may already have discarded the savepoint; fall back to
			# a full rollback so later tests still start clean.
			frappe.db.rollback()
		super().tearDown()

	# ── helpers ──────────────────────────────────────────────────────────────

	def _make_template(self, report="Accounts Receivable", **overrides):
		"""A saved PSOA record to clone from. Two customers, so tests can prove the clone
		narrows to one rather than merely happening to hold one."""
		doc = frappe.new_doc("Process Statement Of Accounts")
		# PSOA is autoname: Prompt, so the name has to be supplied.
		doc.name = f"SOA Test {frappe.generate_hash(length=8)}"
		doc.company = TEST_COMPANY
		doc.report = report
		doc.orientation = "Landscape"
		doc.ageing_based_on = "Due Date"
		doc.filter_duration = 3
		doc.posting_date = today()
		doc.from_date = add_months(today(), -3)
		doc.to_date = today()
		for customer in (TEST_CUSTOMER, OTHER_CUSTOMER):
			doc.append("customers", {"customer": customer})
		doc.update(overrides)
		doc.insert(ignore_permissions=True)
		return doc

	# ── doc construction ─────────────────────────────────────────────────────

	def test_clone_narrows_to_the_single_requested_customer(self):
		tpl = self._make_template()
		self.assertEqual(len(tpl.customers), 2)

		doc = _build_statement_doc(TEST_CUSTOMER, TEST_COMPANY, tpl.name, today())

		self.assertEqual(len(doc.customers), 1)
		self.assertEqual(doc.customers[0].customer, TEST_CUSTOMER)

	def test_clone_is_never_persisted(self):
		"""Templates can carry enable_auto_email=1; a saved clone would enrol the customer into a
		scheduled email run. The clone must stay in memory and leave the template untouched."""
		tpl = self._make_template()
		before = frappe.db.get_value(
			"Process Statement Of Accounts", tpl.name, "modified"
		)

		doc = _build_statement_doc(TEST_CUSTOMER, TEST_COMPANY, tpl.name, today())

		self.assertTrue(doc.is_new())
		self.assertIsNone(doc.get("__unsaved_name"))
		self.assertEqual(
			frappe.db.count("Process Statement Of Accounts Customer", {"parent": tpl.name}), 2
		)
		self.assertEqual(
			frappe.db.get_value("Process Statement Of Accounts", tpl.name, "modified"), before
		)

	def test_ar_template_maps_as_of_date_to_posting_date(self):
		tpl = self._make_template(report="Accounts Receivable")
		as_of = "2026-03-31"

		doc = _build_statement_doc(TEST_CUSTOMER, TEST_COMPANY, tpl.name, as_of)

		self.assertEqual(getdate(doc.posting_date), getdate(as_of))

	def test_gl_template_maps_as_of_date_to_window_from_filter_duration(self):
		tpl = self._make_template(report="General Ledger", filter_duration=3)
		as_of = "2026-03-31"

		doc = _build_statement_doc(TEST_CUSTOMER, TEST_COMPANY, tpl.name, as_of)

		self.assertEqual(getdate(doc.to_date), getdate(as_of))
		self.assertEqual(getdate(doc.from_date), getdate(add_months(as_of, -3)))

	def test_as_of_date_defaults_to_today(self):
		tpl = self._make_template()

		doc = _build_statement_doc(TEST_CUSTOMER, TEST_COMPANY, tpl.name, None)

		self.assertEqual(getdate(doc.posting_date), getdate(today()))

	def test_company_mismatch_throws(self):
		tpl = self._make_template()

		with self.assertRaises(frappe.ValidationError):
			_build_statement_doc(TEST_CUSTOMER, "_Test Company 2", tpl.name, today())

	def test_unknown_template_throws(self):
		with self.assertRaises(frappe.ValidationError):
			_build_statement_doc(TEST_CUSTOMER, TEST_COMPANY, "__nonexistent__", today())

	def test_missing_customer_throws(self):
		tpl = self._make_template()

		with self.assertRaises(frappe.ValidationError):
			_build_statement_doc(None, TEST_COMPANY, tpl.name, today())

	# ── template listing ─────────────────────────────────────────────────────

	def test_get_statement_templates_is_scoped_to_company(self):
		tpl = self._make_template()

		names = [t["name"] for t in get_statement_templates(TEST_COMPANY)]
		self.assertIn(tpl.name, names)

		other = [t["name"] for t in get_statement_templates("_Test Company 2")]
		self.assertNotIn(tpl.name, other)

	def test_get_statement_templates_without_company_returns_empty(self):
		self.assertEqual(get_statement_templates(None), [])

	# ── rendering ────────────────────────────────────────────────────────────

	def test_render_isolates_the_focused_customer(self):
		"""The whole point of the feature: one customer's statement must not carry another's rows."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		create_sales_invoice(customer=OTHER_CUSTOMER, rate=700)
		tpl = self._make_template()

		html = render_statement_html(TEST_CUSTOMER, TEST_COMPANY, tpl.name, today())

		self.assertIn(TEST_CUSTOMER, html)
		self.assertNotIn(OTHER_CUSTOMER, html)

	def test_render_with_no_transactions_throws_a_readable_error(self):
		"""A real customer who simply has no rows in the period, not a missing one."""
		quiet = frappe.new_doc("Customer")
		quiet.customer_name = f"SOA Quiet Customer {frappe.generate_hash(length=6)}"
		quiet.insert(ignore_permissions=True)
		tpl = self._make_template()

		with self.assertRaises(frappe.ValidationError) as ctx:
			render_statement_html(quiet.name, TEST_COMPANY, tpl.name, today())

		self.assertIn("No transactions", str(ctx.exception))

	# ── recipients ───────────────────────────────────────────────────────────

	def test_recipient_falls_back_to_customer_email_id(self):
		frappe.db.set_value("Customer", TEST_CUSTOMER, "email_id", "primary@example.com")

		self.assertEqual(_resolve_recipients(TEST_CUSTOMER), ["primary@example.com"])

	def test_billing_contact_wins_over_customer_email_id(self):
		frappe.db.set_value("Customer", TEST_CUSTOMER, "email_id", "primary@example.com")
		contact = frappe.new_doc("Contact")
		contact.first_name = "Billing Contact for SOA Test"
		contact.is_billing_contact = 1
		contact.append("email_ids", {"email_id": "billing@example.com", "is_primary": 1})
		contact.append("links", {"link_doctype": "Customer", "link_name": TEST_CUSTOMER})
		contact.insert(ignore_permissions=True)

		self.assertEqual(_resolve_recipients(TEST_CUSTOMER), ["billing@example.com"])

	def test_no_email_on_file_returns_empty(self):
		frappe.db.set_value("Customer", TEST_CUSTOMER, "email_id", None)

		self.assertEqual(_resolve_recipients(TEST_CUSTOMER), [])

	def test_get_default_recipient_returns_empty_string_not_none(self):
		"""The dialog assigns this straight into a Data field, where None would render as "None"."""
		frappe.db.set_value("Customer", TEST_CUSTOMER, "email_id", None)

		self.assertEqual(get_default_recipient("customer", TEST_CUSTOMER), "")

	def test_get_default_recipient_requires_read_permission(self):
		user = self._make_user_without_customer_access()

		frappe.set_user(user)
		try:
			with self.assertRaises(frappe.PermissionError):
				get_default_recipient("customer", TEST_CUSTOMER)
		finally:
			frappe.set_user("Administrator")

	# ── email ────────────────────────────────────────────────────────────────

	@IntegrationTestCase.change_settings("System Settings", {"disable_system_update_notification": 1})
	def test_email_statement_attaches_a_pdf_and_never_takes_html_from_the_client(self):
		if not pdf_generation_works():
			self.skipTest("wkhtmltopdf cannot reach the site to fetch print assets")

		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		tpl = self._make_template()

		with patch("frappe.sendmail") as sendmail:
			email_statement(
				TEST_CUSTOMER, TEST_COMPANY, tpl.name, today(), recipient="ar@example.com"
			)

		sendmail.assert_called_once()
		kwargs = sendmail.call_args.kwargs
		self.assertEqual(kwargs["recipients"], ["ar@example.com"])
		self.assertEqual(len(kwargs["attachments"]), 1)
		self.assertTrue(kwargs["attachments"][0]["fname"].endswith(".pdf"))
		self.assertTrue(kwargs["attachments"][0]["fcontent"].startswith(b"%PDF"))

	def test_email_statement_without_any_recipient_throws(self):
		frappe.db.set_value("Customer", TEST_CUSTOMER, "email_id", None)
		tpl = self._make_template()

		with self.assertRaises(frappe.ValidationError) as ctx:
			email_statement(TEST_CUSTOMER, TEST_COMPANY, tpl.name, today(), recipient=None)

		self.assertIn("No email address", str(ctx.exception))

	# ── permissions ──────────────────────────────────────────────────────────

	def test_render_requires_customer_read_permission(self):
		tpl = self._make_template()
		user = self._make_user_without_customer_access()

		frappe.set_user(user)
		try:
			with self.assertRaises(frappe.PermissionError):
				render_statement_html(TEST_CUSTOMER, TEST_COMPANY, tpl.name, today())
		finally:
			frappe.set_user("Administrator")

	def test_send_statement_email_requires_party_read_permission(self):
		"""Regression: this whitelisted method previously took recipient and HTML straight from the
		client with no permission check, letting any logged-in user mail arbitrary content."""
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			send_statement_email,
		)

		user = self._make_user_without_customer_access()

		frappe.set_user(user)
		try:
			with self.assertRaises(frappe.PermissionError):
				send_statement_email(
					party_type="customer",
					party=TEST_CUSTOMER,
					company=TEST_COMPANY,
					as_of_date=today(),
					html_content="<p>arbitrary</p>",
					recipient_email="attacker@example.com",
				)
		finally:
			frappe.set_user("Administrator")

	def _make_user_without_customer_access(self):
		email = f"soa-noperm-{frappe.generate_hash(length=6)}@example.com"
		user = frappe.new_doc("User")
		user.email = email
		user.first_name = "SOA No Perm"
		# No roles at all: Frappe still grants the implicit "All" role, which carries no Customer
		# permission, which is exactly the unprivileged case these tests need.
		user.insert(ignore_permissions=True)
		return email
