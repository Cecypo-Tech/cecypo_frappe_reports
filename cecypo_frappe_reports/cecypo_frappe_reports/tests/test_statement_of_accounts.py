# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import functools
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_months, getdate, today

from cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts import (
	_build_bulk_statement_doc,
	_build_statement_doc,
	_company_customers,
	_resolve_recipients,
	_send_bulk_statements,
	email_bulk_statements,
	email_statement,
	get_default_recipient,
	get_statement_templates,
	preview_bulk_statements,
	render_statement_html,
)

TEST_COMPANY = "_Test Company"
TEST_CUSTOMER = "_Test Customer"
OTHER_CUSTOMER = "_Test Customer 1"
# A second company (different currency, different accounts) used only to prove GL-entry scoping
# actually excludes customers whose transactions belong elsewhere.
OTHER_COMPANY = "_Test Company 2"

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

	def _make_other_company_invoice(self, customer, rate=500):
		"""A submitted invoice against OTHER_COMPANY, whose currency and accounts differ from
		TEST_COMPANY. Exists purely to prove GL-entry scoping excludes a customer whose ledger
		activity belongs to a different company."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		return create_sales_invoice(
			customer=customer,
			company=OTHER_COMPANY,
			debit_to="Debtors - _TC2",
			income_account="Sales - _TC2",
			expense_account="Cost of Goods Sold - _TC2",
			cost_center="Main - _TC2",
			warehouse="Stores - _TC2",
			currency="EUR",
			rate=rate,
		)

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

	# ── bulk preview ─────────────────────────────────────────────────────────

	def test_bulk_doc_widens_to_every_enabled_customer_and_is_never_persisted(self):
		"""The bulk clone must reach every customer with GL activity against the company, not just
		the template's own two, and must stay in memory the exact same way the single-customer
		clone does."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		create_sales_invoice(customer=OTHER_CUSTOMER, rate=700)
		tpl = self._make_template()
		before = frappe.db.get_value("Process Statement Of Accounts", tpl.name, "modified")

		doc = _build_bulk_statement_doc(TEST_COMPANY, tpl.name, today())

		self.assertGreater(len(doc.customers), 1)
		self.assertTrue(doc.is_new())
		self.assertIsNone(doc.get("__unsaved_name"))
		# The template itself keeps its original two rows and is untouched.
		self.assertEqual(
			frappe.db.count("Process Statement Of Accounts Customer", {"parent": tpl.name}), 2
		)
		self.assertEqual(
			frappe.db.get_value("Process Statement Of Accounts", tpl.name, "modified"), before
		)

	def test_bulk_doc_applies_the_same_template_company_guard(self):
		"""Reuses _build_statement_doc, so a template belonging to another company must still throw
		even though the bulk path never receives an explicit customer from the caller. Giving
		OTHER_COMPANY a transacting customer keeps _company_customers non-empty, so it is genuinely
		the company guard that fires here, not the empty-customer-list branch."""
		tpl = self._make_template()
		self._make_other_company_invoice(OTHER_CUSTOMER)

		with self.assertRaises(frappe.ValidationError):
			_build_bulk_statement_doc(OTHER_COMPANY, tpl.name, today())

	def test_company_customers_excludes_customers_of_another_company(self):
		"""Pins the round-1 fix: _company_customers must scope through GL Entry rather than
		returning every enabled Customer on the site, since Customer itself has no company field."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		self._make_other_company_invoice(OTHER_CUSTOMER)

		names = [c.name for c in _company_customers(TEST_COMPANY)]

		self.assertIn(TEST_CUSTOMER, names)
		self.assertNotIn(OTHER_CUSTOMER, names)

	def test_preview_bulk_statements_returns_expected_keys_and_reconciles(self):
		"""The four buckets (will_send, no_email, not_permitted, no_transactions) must always add
		up to total_customers: not_permitted counts rather than silently drops, so nothing goes
		missing from the totals the user actually sees."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		tpl = self._make_template()

		result = preview_bulk_statements(TEST_COMPANY, tpl.name, today())

		for key in ("will_send", "no_email", "not_permitted", "no_transactions", "total_customers"):
			self.assertIn(key, result)

		reconciled = (
			len(result["will_send"])
			+ len(result["no_email"])
			+ result["not_permitted"]
			+ result["no_transactions"]
		)
		self.assertEqual(reconciled, result["total_customers"])

	def test_permission_error_for_one_customer_does_not_abort_the_preview(self):
		"""_resolve_recipients checks Customer read per customer (get_customer_emails calls
		frappe.has_permission(..., throw=True)); the seed check in _build_statement_doc only
		covers the first customer, so this per-customer check is what actually protects a
		restricted user. It must be caught and counted, not left to blow up the whole preview."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		create_sales_invoice(customer=OTHER_CUSTOMER, rate=700)
		frappe.db.set_value("Customer", TEST_CUSTOMER, "email_id", "primary@example.com")
		tpl = self._make_template()

		def side_effect(customer):
			if customer == OTHER_CUSTOMER:
				raise frappe.PermissionError
			return ["primary@example.com"]

		with patch(
			"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts._resolve_recipients",
			side_effect=side_effect,
		):
			result = preview_bulk_statements(TEST_COMPANY, tpl.name, today())

		self.assertEqual(result["not_permitted"], 1)
		will_send_names = [row["customer"] for row in result["will_send"]]
		no_email_names = [row["customer"] for row in result["no_email"]]
		self.assertIn(TEST_CUSTOMER, will_send_names)
		self.assertNotIn(OTHER_CUSTOMER, will_send_names)
		self.assertNotIn(OTHER_CUSTOMER, no_email_names)

	def test_customer_with_transactions_but_no_email_lands_in_no_email_not_will_send(self):
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		frappe.db.set_value("Customer", OTHER_CUSTOMER, "email_id", None)
		frappe.db.set_value("Customer", OTHER_CUSTOMER, "customer_primary_contact", None)
		create_sales_invoice(customer=OTHER_CUSTOMER, rate=500)
		tpl = self._make_template()

		result = preview_bulk_statements(TEST_COMPANY, tpl.name, today())

		no_email_names = [row["customer"] for row in result["no_email"]]
		will_send_names = [row["customer"] for row in result["will_send"]]
		self.assertIn(OTHER_CUSTOMER, no_email_names)
		self.assertNotIn(OTHER_CUSTOMER, will_send_names)

	def test_customer_with_no_transactions_appears_in_neither_list(self):
		"""A customer with zero GL activity anywhere is excluded at the _company_customers layer
		before get_statement_dict is ever consulted; a transacting customer is added so the bulk
		doc still builds. Either way, the quiet customer must never surface in the results."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		quiet = frappe.new_doc("Customer")
		quiet.customer_name = f"SOA Quiet Bulk Customer {frappe.generate_hash(length=6)}"
		quiet.insert(ignore_permissions=True)
		tpl = self._make_template()

		result = preview_bulk_statements(TEST_COMPANY, tpl.name, today())

		will_send_names = [row["customer"] for row in result["will_send"]]
		no_email_names = [row["customer"] for row in result["no_email"]]
		self.assertNotIn(quiet.name, will_send_names)
		self.assertNotIn(quiet.name, no_email_names)

	def test_bulk_doc_seeds_with_a_readable_customer_when_the_first_is_unpermitted(self):
		"""Regression: frappe.get_all does not check permissions, so _company_customers()[0] can be
		a customer this caller cannot read. The old code fed customers[0] straight into
		_build_statement_doc, whose has_permission(throw=True) then blew up the whole call on a
		customer nobody asked to see. The seed must skip past an unreadable customer instead."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		create_sales_invoice(customer=OTHER_CUSTOMER, rate=700)
		tpl = self._make_template()

		customers = _company_customers(TEST_COMPANY)
		unreadable = customers[0].name
		real_has_permission = frappe.has_permission

		def side_effect(*args, **kwargs):
			doctype = args[0] if args else kwargs.get("doctype")
			doc = args[2] if len(args) > 2 else kwargs.get("doc")
			if doctype == "Customer" and doc == unreadable:
				if kwargs.get("throw"):
					raise frappe.PermissionError
				return False
			return real_has_permission(*args, **kwargs)

		with patch("frappe.has_permission", side_effect=side_effect):
			doc = _build_bulk_statement_doc(TEST_COMPANY, tpl.name, today())

		# Building must succeed (no raw PermissionError) and still widen to every customer, not
		# just the readable seed.
		self.assertGreater(len(doc.customers), 1)

	def test_bulk_doc_throws_a_readable_message_when_no_customer_is_permitted(self):
		"""If every GL-active customer is unreadable, the seed loop finds none: this must throw a
		clear, catchable error rather than letting an unreadable customers[0] raise a bare
		PermissionError from deep inside _build_statement_doc."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		tpl = self._make_template()

		with patch("frappe.has_permission", return_value=False):
			with self.assertRaises(frappe.ValidationError):
				_build_bulk_statement_doc(TEST_COMPANY, tpl.name, today())

	def test_preview_bulk_statements_never_generates_a_pdf(self):
		"""Pins invariant 2: the preview answers who has transactions from get_statement_dict's HTML
		and must never fall through to get_report_pdf, even when the toolchain is broken."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		tpl = self._make_template()

		with patch(
			"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.get_report_pdf"
		) as mock_pdf:
			mock_pdf.side_effect = AssertionError("preview must not render a PDF")
			result = preview_bulk_statements(TEST_COMPANY, tpl.name, today())

		mock_pdf.assert_not_called()
		self.assertIn("will_send", result)

	# ── bulk send ────────────────────────────────────────────────────────────

	def test_email_bulk_statements_enqueues_rather_than_sends_inline(self):
		"""The whitelisted endpoint must return from the request without ever touching
		frappe.sendmail; rendering N statements inline would time out the request."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		frappe.db.set_value("Customer", TEST_CUSTOMER, "email_id", "primary@example.com")
		tpl = self._make_template()

		with patch("frappe.enqueue") as mock_enqueue, patch("frappe.sendmail") as mock_sendmail:
			email_bulk_statements(TEST_COMPANY, tpl.name, today())

		mock_enqueue.assert_called_once()
		mock_sendmail.assert_not_called()

	def test_email_bulk_statements_enqueue_is_deduplicated_by_job_id(self):
		"""Regression: the whole expensive pass runs before frappe.enqueue, so a proxy or gunicorn
		timeout can show the browser a failure while the job still lands; a retry must not mail
		everyone twice. frappe.enqueue's own deduplicate=True + job_id refuses to re-queue a job
		with a matching id that is already queued or running, so pin that both are actually
		passed and that the id is keyed on the inputs that define the run."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		frappe.db.set_value("Customer", TEST_CUSTOMER, "email_id", "primary@example.com")
		tpl = self._make_template()
		as_of = today()

		with patch("frappe.enqueue") as mock_enqueue:
			email_bulk_statements(TEST_COMPANY, tpl.name, as_of)

		kwargs = mock_enqueue.call_args.kwargs
		self.assertTrue(kwargs.get("deduplicate"))
		self.assertIn("job_id", kwargs)
		self.assertIn(TEST_COMPANY, kwargs["job_id"])
		self.assertIn(tpl.name, kwargs["job_id"])
		self.assertIn(str(as_of), kwargs["job_id"])

	def test_email_bulk_statements_throws_and_does_not_enqueue_when_nobody_eligible(self):
		"""Pins one of the two guards the plan's self-review calls out as mattering most: when no
		customer has both transactions and an address, the endpoint must throw rather than
		silently queue a job for zero recipients. Deliberately leaves the one transacting
		customer without any resolvable address, so preview's will_send is empty while
		total_customers is not."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		frappe.db.set_value("Customer", TEST_CUSTOMER, "email_id", None)
		frappe.db.set_value("Customer", TEST_CUSTOMER, "customer_primary_contact", None)
		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		tpl = self._make_template()

		with patch("frappe.enqueue") as mock_enqueue:
			with self.assertRaises(frappe.ValidationError):
				email_bulk_statements(TEST_COMPANY, tpl.name, today())

		mock_enqueue.assert_not_called()

	def test_email_bulk_statements_queued_count_matches_preview_will_send(self):
		"""The toast the user sees must never disagree with the preview: both are read from the
		same preview_bulk_statements call, not two independent counts that could drift apart."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		create_sales_invoice(customer=OTHER_CUSTOMER, rate=700)
		frappe.db.set_value("Customer", TEST_CUSTOMER, "email_id", "primary@example.com")
		frappe.db.set_value("Customer", OTHER_CUSTOMER, "email_id", None)
		frappe.db.set_value("Customer", OTHER_CUSTOMER, "customer_primary_contact", None)
		tpl = self._make_template()

		preview = preview_bulk_statements(TEST_COMPANY, tpl.name, today())
		with patch("frappe.enqueue"):
			result = email_bulk_statements(TEST_COMPANY, tpl.name, today())

		self.assertEqual(result["queued"], len(preview["will_send"]))

	def test_send_bulk_statements_skips_customer_with_no_recipient_without_aborting(self):
		"""One customer with no resolvable address must cost only that customer, not the run."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		create_sales_invoice(customer=OTHER_CUSTOMER, rate=700)
		tpl = self._make_template()

		def side_effect(customer):
			return [] if customer == OTHER_CUSTOMER else ["primary@example.com"]

		with (
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts._resolve_recipients",
				side_effect=side_effect,
			),
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.get_pdf",
				return_value=b"%PDF-fake",
			),
			patch("frappe.sendmail") as mock_sendmail,
		):
			_send_bulk_statements(TEST_COMPANY, tpl.name, today())

		mock_sendmail.assert_called_once()
		self.assertEqual(mock_sendmail.call_args.kwargs["reference_name"], TEST_CUSTOMER)

	def test_send_bulk_statements_logs_and_skips_a_render_failure_without_aborting_the_run(self):
		"""Pins the reason get_report_pdf is not used: get_statement_dict runs once for every
		customer, but get_pdf is called per customer inside the try, so a render failure for one
		customer costs only that customer. Patching the module's own `get_pdf` (rather than
		get_report_pdf) means this test would fail to catch a regression that "simplifies" the
		implementation back to a single get_report_pdf(doc, consolidated=False) call, since that
		call renders every customer in one uninterruptible pass before this handler ever runs."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		create_sales_invoice(customer=OTHER_CUSTOMER, rate=700)
		frappe.db.set_value("Customer", TEST_CUSTOMER, "email_id", "good@example.com")
		frappe.db.set_value("Customer", OTHER_CUSTOMER, "email_id", "bad@example.com")
		tpl = self._make_template()

		def failing_get_pdf(html, options=None):
			if OTHER_CUSTOMER in html:
				raise Exception("simulated render failure")
			return b"%PDF-fake"

		with (
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.get_pdf",
				side_effect=failing_get_pdf,
			),
			patch("frappe.sendmail") as mock_sendmail,
			patch("frappe.log_error") as mock_log_error,
		):
			_send_bulk_statements(TEST_COMPANY, tpl.name, today())

		mock_sendmail.assert_called_once()
		self.assertEqual(mock_sendmail.call_args.kwargs["reference_name"], TEST_CUSTOMER)
		mock_log_error.assert_called_once()
		self.assertIn(OTHER_CUSTOMER, mock_log_error.call_args.kwargs["message"])

	def test_send_bulk_statements_permission_error_costs_one_customer_not_the_run(self):
		"""_resolve_recipients raising frappe.PermissionError sits inside the same try as the
		render and send, so a permission gap for one customer must not abort the others. It is
		caught separately from the generic Exception handler and must NOT be logged: it is the
		expected, already-counted-in-the-preview case for a restricted user, and logging it under
		the failure title would bury genuine failures in the one channel where they must be
		found."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		create_sales_invoice(customer=OTHER_CUSTOMER, rate=700)
		tpl = self._make_template()

		def side_effect(customer):
			if customer == OTHER_CUSTOMER:
				raise frappe.PermissionError
			return ["primary@example.com"]

		with (
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts._resolve_recipients",
				side_effect=side_effect,
			),
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.get_pdf",
				return_value=b"%PDF-fake",
			),
			patch("frappe.sendmail") as mock_sendmail,
			patch("frappe.log_error") as mock_log_error,
		):
			_send_bulk_statements(TEST_COMPANY, tpl.name, today())

		mock_sendmail.assert_called_once()
		self.assertEqual(mock_sendmail.call_args.kwargs["reference_name"], TEST_CUSTOMER)
		mock_log_error.assert_not_called()

	def test_send_bulk_statements_never_saves_the_doc(self):
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		frappe.db.set_value("Customer", TEST_CUSTOMER, "email_id", "primary@example.com")
		tpl = self._make_template()
		before = frappe.db.get_value("Process Statement Of Accounts", tpl.name, "modified")

		with (
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.get_pdf",
				return_value=b"%PDF-fake",
			),
			patch("frappe.sendmail"),
		):
			_send_bulk_statements(TEST_COMPANY, tpl.name, today())

		self.assertEqual(
			frappe.db.count("Process Statement Of Accounts Customer", {"parent": tpl.name}), 2
		)
		self.assertEqual(
			frappe.db.get_value("Process Statement Of Accounts", tpl.name, "modified"), before
		)

	def test_email_bulk_statements_never_saves_the_doc(self):
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		frappe.db.set_value("Customer", TEST_CUSTOMER, "email_id", "primary@example.com")
		tpl = self._make_template()
		before = frappe.db.get_value("Process Statement Of Accounts", tpl.name, "modified")

		with patch("frappe.enqueue"):
			email_bulk_statements(TEST_COMPANY, tpl.name, today())

		self.assertEqual(
			frappe.db.count("Process Statement Of Accounts Customer", {"parent": tpl.name}), 2
		)
		self.assertEqual(
			frappe.db.get_value("Process Statement Of Accounts", tpl.name, "modified"), before
		)

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
