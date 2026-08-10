# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import functools
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_months, get_datetime, getdate, today

from cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts import (
	_assert_template_usable,
	_build_statement_doc,
	_company_customers,
	_customers_with_any_email,
	_narrow_statement_doc,
	_resolve_recipients,
	_send_statement_batch,
	email_bulk_statements,
	email_statement,
	enqueue_statement_batches,
	get_default_recipient,
	get_statement_templates,
	preview_bulk_statements,
	render_statement_html,
	send_psoa_in_batches,
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

	# ── _assert_template_usable ─────────────────────────────────────────────────

	def test_assert_template_usable_passes_for_a_valid_template(self):
		"""The positive case: a template that exists, is readable, and belongs to the given
		company must return the doc rather than throwing."""
		tpl = self._make_template()

		usable = _assert_template_usable(tpl.name, TEST_COMPANY)

		self.assertEqual(usable.name, tpl.name)

	def test_assert_template_usable_throws_for_a_nonexistent_template(self):
		with self.assertRaises(frappe.ValidationError):
			_assert_template_usable("__nonexistent__", TEST_COMPANY)

	def test_assert_template_usable_throws_for_a_template_belonging_to_another_company(self):
		"""This is the check that stops one company's letterhead and accounts being used to
		render another company's statement — the one the fix wave restores to the bulk-send path."""
		tpl = self._make_template()  # belongs to TEST_COMPANY

		with self.assertRaises(frappe.ValidationError):
			_assert_template_usable(tpl.name, OTHER_COMPANY)

	def test_assert_template_usable_throws_for_an_unreadable_template(self):
		"""The third bad-template case, alongside nonexistent and wrong-company: a template the
		caller has no read permission for. Patches Document.check_permission (the same mechanism
		the seed-permission tests use for Customer, applied here to the template doc) so this pins
		that tpl.check_permission("read") is actually invoked, rather than relying on a real
		restricted user. If someone later drops that line, this is what catches it."""
		tpl = self._make_template()

		with patch(
			"frappe.model.document.Document.check_permission",
			side_effect=frappe.PermissionError,
		):
			with self.assertRaises(frappe.PermissionError):
				_assert_template_usable(tpl.name, TEST_COMPANY)

	# ── bulk preview ─────────────────────────────────────────────────────────

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
		"""with_email + without_email + not_permitted must always add up to in_scope: not_permitted
		counts rather than silently drops, so nothing goes missing from the totals the user sees."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		tpl = self._make_template()
		as_of = today()

		result = preview_bulk_statements(TEST_COMPANY, tpl.name, as_of)

		for key in (
			"in_scope",
			"with_email",
			"without_email",
			"not_permitted",
			"template",
			"as_of_date",
		):
			self.assertIn(key, result)

		reconciled = result["with_email"] + len(result["without_email"]) + result["not_permitted"]
		self.assertEqual(reconciled, result["in_scope"])
		self.assertEqual(result["template"], tpl.name)
		self.assertEqual(result["as_of_date"], str(getdate(as_of)))

	def test_preview_bulk_statements_throws_for_a_nonexistent_template(self):
		"""Finding 2: the manifest's template checks had no test of their own. A regression here
		(e.g. the company guard being dropped) must fail loudly rather than silently returning a
		manifest built from an unreadable or wrong-company template."""
		with self.assertRaises(frappe.ValidationError):
			preview_bulk_statements(TEST_COMPANY, "__nonexistent__", today())

	def test_preview_bulk_statements_throws_for_a_template_belonging_to_another_company(self):
		tpl = self._make_template()  # belongs to TEST_COMPANY

		with self.assertRaises(frappe.ValidationError):
			preview_bulk_statements(OTHER_COMPANY, tpl.name, today())

	def test_preview_bulk_statements_throws_for_an_unreadable_template(self):
		"""Must throw rather than returning a manifest built from a template the caller cannot
		read. Same Document.check_permission patch as the other two unreadable-template tests."""
		tpl = self._make_template()

		with patch(
			"frappe.model.document.Document.check_permission",
			side_effect=frappe.PermissionError,
		):
			with self.assertRaises(frappe.PermissionError):
				preview_bulk_statements(TEST_COMPANY, tpl.name, today())

	def test_unreadable_customer_is_counted_as_not_permitted_and_never_named(self):
		"""has_permission is checked per customer before the bulk email query runs, so a user with
		restricted customer visibility must not have their whole preview die on one customer they
		cannot see, and that customer must never appear by name in without_email either."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		create_sales_invoice(customer=OTHER_CUSTOMER, rate=700)
		frappe.db.set_value("Customer", TEST_CUSTOMER, "email_id", None)
		frappe.db.set_value("Customer", TEST_CUSTOMER, "customer_primary_contact", None)
		tpl = self._make_template()
		real_has_permission = frappe.has_permission

		def side_effect(*args, **kwargs):
			doctype = args[0] if args else kwargs.get("doctype")
			doc = args[2] if len(args) > 2 else kwargs.get("doc")
			if doctype == "Customer" and doc == OTHER_CUSTOMER:
				return False
			return real_has_permission(*args, **kwargs)

		with patch("frappe.has_permission", side_effect=side_effect):
			result = preview_bulk_statements(TEST_COMPANY, tpl.name, today())

		self.assertEqual(result["not_permitted"], 1)
		self.assertIsInstance(result["not_permitted"], int)
		without_email_names = [row["customer"] for row in result["without_email"]]
		self.assertIn(TEST_CUSTOMER, without_email_names)
		self.assertNotIn(OTHER_CUSTOMER, without_email_names)

	def test_customer_with_transactions_but_no_email_lands_in_without_email(self):
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		frappe.db.set_value("Customer", TEST_CUSTOMER, "email_id", "primary@example.com")
		frappe.db.set_value("Customer", OTHER_CUSTOMER, "email_id", None)
		frappe.db.set_value("Customer", OTHER_CUSTOMER, "customer_primary_contact", None)
		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		create_sales_invoice(customer=OTHER_CUSTOMER, rate=500)
		tpl = self._make_template()

		result = preview_bulk_statements(TEST_COMPANY, tpl.name, today())

		without_email_names = [row["customer"] for row in result["without_email"]]
		self.assertIn(OTHER_CUSTOMER, without_email_names)
		self.assertNotIn(TEST_CUSTOMER, without_email_names)
		self.assertEqual(result["with_email"], 1)

	def test_customer_with_no_transactions_appears_in_neither_bucket(self):
		"""A customer with zero GL activity anywhere is excluded at the _company_customers layer;
		a transacting customer is added so the bulk preview still has something in scope. Either
		way, the quiet customer must never surface in the results or be counted in in_scope."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		quiet = frappe.new_doc("Customer")
		quiet.customer_name = f"SOA Quiet Bulk Customer {frappe.generate_hash(length=6)}"
		quiet.insert(ignore_permissions=True)
		tpl = self._make_template()

		result = preview_bulk_statements(TEST_COMPANY, tpl.name, today())

		without_email_names = [row["customer"] for row in result["without_email"]]
		self.assertNotIn(quiet.name, without_email_names)
		self.assertEqual(result["in_scope"], len(_company_customers(TEST_COMPANY)))

	def test_preview_bulk_statements_runs_no_report_pass(self):
		"""The whole point of this task: the preview must not run a full report render per
		customer to learn who has transactions. get_statement_dict is patched to raise, so any
		regression that reintroduces the render pass fails this test immediately instead of only
		showing up as a slow endpoint at a few hundred customers."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		frappe.db.set_value("Customer", TEST_CUSTOMER, "email_id", "primary@example.com")
		tpl = self._make_template()

		with patch(
			"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.get_statement_dict",
			side_effect=AssertionError("preview must not run a report render"),
		):
			result = preview_bulk_statements(TEST_COMPANY, tpl.name, today())

		self.assertIn("in_scope", result)
		self.assertGreaterEqual(result["in_scope"], 1)

	def test_preview_bulk_statements_in_scope_equals_gl_active_customer_count(self):
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		create_sales_invoice(customer=OTHER_CUSTOMER, rate=700)
		tpl = self._make_template()

		result = preview_bulk_statements(TEST_COMPANY, tpl.name, today())

		self.assertEqual(result["in_scope"], len(_company_customers(TEST_COMPANY)))

	# ── _customers_with_any_email ───────────────────────────────────────────────

	def test_customers_with_any_email_checks_all_three_sources(self):
		"""_customers_with_any_email must find an address through every source
		_resolve_recipients does: the Customer's own email_id, a billing Contact's email, and the
		customer_primary_contact's Contact email. One customer per source, plus one with nothing
		on file."""
		via_own_email_id = TEST_CUSTOMER
		frappe.db.set_value("Customer", via_own_email_id, "email_id", "primary@example.com")

		via_billing_contact = OTHER_CUSTOMER
		frappe.db.set_value("Customer", via_billing_contact, "email_id", None)
		frappe.db.set_value("Customer", via_billing_contact, "customer_primary_contact", None)
		contact = frappe.new_doc("Contact")
		contact.first_name = "Billing Contact for SOA Test"
		contact.is_billing_contact = 1
		contact.append("email_ids", {"email_id": "billing@example.com", "is_primary": 1})
		contact.append("links", {"link_doctype": "Customer", "link_name": via_billing_contact})
		contact.insert(ignore_permissions=True)

		via_primary_contact = frappe.new_doc("Customer")
		via_primary_contact.customer_name = f"SOA Primary Contact Cust {frappe.generate_hash(length=6)}"
		via_primary_contact.insert(ignore_permissions=True)
		primary_contact = frappe.new_doc("Contact")
		primary_contact.first_name = "Primary Contact for SOA Test"
		primary_contact.append("email_ids", {"email_id": "primary-contact@example.com", "is_primary": 1})
		primary_contact.append("links", {"link_doctype": "Customer", "link_name": via_primary_contact.name})
		primary_contact.insert(ignore_permissions=True)
		frappe.db.set_value(
			"Customer", via_primary_contact.name, "customer_primary_contact", primary_contact.name
		)

		no_address = frappe.new_doc("Customer")
		no_address.customer_name = f"SOA No Address Cust {frappe.generate_hash(length=6)}"
		no_address.insert(ignore_permissions=True)

		names = [via_own_email_id, via_billing_contact, via_primary_contact.name, no_address.name]

		found = _customers_with_any_email(names)

		self.assertIn(via_own_email_id, found)
		self.assertIn(via_billing_contact, found)
		self.assertIn(via_primary_contact.name, found)
		self.assertNotIn(no_address.name, found)

	def test_customers_with_any_email_ignores_a_merely_linked_non_billing_contact(self):
		"""Regression pin for the divergence the site-wide pinning test caught: a Contact linked
		to the customer via Dynamic Link but neither the billing contact nor the
		customer_primary_contact must NOT count as an address here, because
		_resolve_recipients (via get_customer_emails' is_billing_contact=1 filter) would not find
		it either. An earlier version of this query joined Dynamic Link -> Contact Email for ANY
		linked contact and wrongly said "has email" for exactly this shape of real site data."""
		frappe.db.set_value("Customer", OTHER_CUSTOMER, "email_id", None)
		frappe.db.set_value("Customer", OTHER_CUSTOMER, "customer_primary_contact", None)
		contact = frappe.new_doc("Contact")
		contact.first_name = "Merely Linked Contact for SOA Test"
		contact.is_billing_contact = 0
		contact.append("email_ids", {"email_id": "not-billing@example.com", "is_primary": 1})
		contact.append("links", {"link_doctype": "Customer", "link_name": OTHER_CUSTOMER})
		contact.insert(ignore_permissions=True)

		found = _customers_with_any_email([OTHER_CUSTOMER])

		self.assertNotIn(OTHER_CUSTOMER, found)
		self.assertEqual(_resolve_recipients(OTHER_CUSTOMER), [])

	def test_customers_with_any_email_empty_input_returns_empty_set(self):
		self.assertEqual(_customers_with_any_email([]), set())

	def test_customers_with_any_email_pins_against_resolve_recipients_on_real_site_data(self):
		"""THE PINNING TEST. _customers_with_any_email is a second implementation of "does this
		customer have an address", alongside _resolve_recipients. That duplication is exactly the
		pattern that silently diverges, and it is accepted only because this test holds the two
		together: for every enabled customer actually on the site, whether the bulk query finds
		them must agree with whether the live per-customer lookup would. Iterates real site data
		rather than a handful of fixtures, since a fixture set cannot catch a divergence introduced
		by a real data shape nobody thought to construct by hand. If this fails, that is a finding
		about the query, not a reason to weaken the assertion."""
		customer_names = frappe.get_all("Customer", filters={"disabled": 0}, pluck="name")
		self.assertTrue(customer_names, "no enabled customers on this site to pin against")

		bulk_found = _customers_with_any_email(customer_names)

		mismatches = []
		for name in customer_names:
			bulk_says_has_email = name in bulk_found
			live_says_has_email = bool(_resolve_recipients(name))
			if bulk_says_has_email != live_says_has_email:
				mismatches.append((name, bulk_says_has_email, live_says_has_email))

		self.assertEqual(
			mismatches,
			[],
			f"_customers_with_any_email disagrees with _resolve_recipients for: {mismatches}",
		)

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

	def test_email_bulk_statements_delegates_to_the_chunker_with_every_company_customer(self):
		"""The endpoint no longer pre-computes who is eligible (that decision is now the batch
		worker's, per batch); it must hand every GL-active customer of the company to
		enqueue_statement_batches and let the chunker do the enqueuing, including its own
		per-batch job_id/deduplicate dedup (covered separately by
		test_enqueue_statement_batches_job_ids_are_distinct_and_deduplicated)."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		create_sales_invoice(customer=OTHER_CUSTOMER, rate=700)
		tpl = self._make_template()
		as_of = today()

		with patch(
			"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.enqueue_statement_batches",
			return_value=1,
		) as mock_chunker:
			result = email_bulk_statements(TEST_COMPANY, tpl.name, as_of)

		mock_chunker.assert_called_once()
		args, kwargs = mock_chunker.call_args
		self.assertEqual(args[0], tpl.name)
		sent_customers = sorted(row["customer"] for row in args[1])
		self.assertEqual(sent_customers, sorted(c.name for c in _company_customers(TEST_COMPANY)))
		self.assertEqual(kwargs.get("as_of_date"), as_of)
		self.assertEqual(result, {"batches": 1})

	def test_email_bulk_statements_throws_and_does_not_enqueue_when_company_has_no_customers(self):
		"""The remaining post-template guard: an address-less or transaction-less customer is no
		longer grounds to throw (the batch worker skips them correctly, per batch), but a company
		with zero GL-active customers must still throw rather than enqueue an empty run.

		Uses a template that legitimately belongs to OTHER_COMPANY, so this test is isolated from
		the template guard that now runs ahead of it — the fix wave's own reordering means a
		nonexistent/mismatched template here would be caught by _assert_template_usable first and
		this test would stop meaning what its name says."""
		tpl = self._make_template(company=OTHER_COMPANY)

		with patch(
			"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.enqueue_statement_batches"
		) as mock_chunker:
			with self.assertRaises(frappe.ValidationError):
				email_bulk_statements(OTHER_COMPANY, tpl.name, today())

		mock_chunker.assert_not_called()

	def test_email_bulk_statements_throws_and_does_not_enqueue_for_a_nonexistent_template(self):
		"""THE FINDING THIS FIX WAVE CLOSES. Before this fix, a bad template was not validated
		until the worker ran _narrow_statement_doc, outside the per-customer try — so the caller
		was already told {"batches": N} while every batch then failed silently. Uses a company
		WITH GL-active customers, so this specifically proves the template guard fires before
		enqueuing, not the (separately tested) no-customers guard."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)

		with patch("frappe.enqueue") as mock_enqueue:
			with self.assertRaises(frappe.ValidationError):
				email_bulk_statements(TEST_COMPANY, "__nonexistent__", today())

		mock_enqueue.assert_not_called()

	def test_email_bulk_statements_throws_and_does_not_enqueue_for_a_template_belonging_to_another_company(self):
		"""The company check specifically: it stops one company's letterhead and accounts being
		used to render another company's statement. Giving OTHER_COMPANY a transacting customer
		keeps _company_customers non-empty, proving it is genuinely the template-company guard
		that fires, not the empty-customer-list branch it sits ahead of."""
		tpl = self._make_template()  # belongs to TEST_COMPANY
		self._make_other_company_invoice(OTHER_CUSTOMER)

		with patch("frappe.enqueue") as mock_enqueue:
			with self.assertRaises(frappe.ValidationError):
				email_bulk_statements(OTHER_COMPANY, tpl.name, today())

		mock_enqueue.assert_not_called()

	def test_email_bulk_statements_throws_and_does_not_enqueue_for_an_unreadable_template(self):
		"""The third bad-template case at this entry point: an unreadable template must throw
		and must not enqueue, exactly like the nonexistent and wrong-company cases above. Uses a
		company WITH GL-active customers so this is genuinely the template-permission guard, not
		the no-customers guard it sits ahead of."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		tpl = self._make_template()

		with patch(
			"frappe.model.document.Document.check_permission",
			side_effect=frappe.PermissionError,
		):
			with patch("frappe.enqueue") as mock_enqueue:
				with self.assertRaises(frappe.PermissionError):
					email_bulk_statements(TEST_COMPANY, tpl.name, today())

		mock_enqueue.assert_not_called()

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

	def test_email_bulk_statements_is_post_only(self):
		"""THE FINDING ITEM 4 CLOSES. Same GET/CSRF exposure as send_psoa_in_batches, but reachable
		by anyone who can guess a company/template pair. Both klik_pos's delegating endpoint and
		the SPA service already call this via POST, so restricting to POST changes nothing for the
		real callers."""
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[email_bulk_statements], ["POST"])

	# ── contract version ─────────────────────────────────────────────────────

	def test_statement_api_version_is_declared_and_an_int(self):
		"""Consumers gate on this. It must exist, be an int, and never silently vanish.

		A consumer treats its ABSENCE as version 1 — the pre-manifest contract — so deleting or
		renaming this constant would make every consumer report the app as too old rather than
		failing loudly. That is the safe direction, but only if the constant is here.
		"""
		from cecypo_frappe_reports.cecypo_frappe_reports import statement_of_accounts as soa

		self.assertIsInstance(soa.STATEMENT_API_VERSION, int)
		self.assertGreaterEqual(soa.STATEMENT_API_VERSION, 2)

	def test_bulk_api_shape_is_pinned(self):
		"""Guard the consumer-facing contract, because the version bump is manual.

		A changed return shape is invisible to a consumer resolving attributes — that is the
		whole reason STATEMENT_API_VERSION exists — and it is also the easiest change to make
		without realising anyone downstream cares. So the shape is pinned here, and the failure
		message says what to do about it.

		THIS TEST IS MEANT TO FAIL when the contract changes. That is its entire purpose: the
		version bump is manual, and this converts "remember to bump" into "the suite stops you".
		If you are here because a deliberate shape change broke this assertion, the fix is to
		bump STATEMENT_API_VERSION and update consumers — NOT to loosen the assertion below.
		Loosening it (including reintroducing an escape hatch for an empty without_email list)
		would silently remove the only thing enforcing the bump discipline.
		"""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		# Two transacting customers, only one with an address, so with_email AND without_email are
		# both non-empty below — a fixture that leaves without_email empty would let the row-shape
		# assertion pass vacuously no matter what that row looks like.
		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		create_sales_invoice(customer=OTHER_CUSTOMER, rate=500)
		frappe.db.set_value("Customer", TEST_CUSTOMER, "email_id", "primary@example.com")
		frappe.db.set_value("Customer", OTHER_CUSTOMER, "email_id", None)
		frappe.db.set_value("Customer", OTHER_CUSTOMER, "customer_primary_contact", None)
		tpl = self._make_template()

		manifest = preview_bulk_statements(company=TEST_COMPANY, template=tpl.name)

		self.assertEqual(
			set(manifest),
			{"in_scope", "with_email", "without_email", "not_permitted", "template", "as_of_date"},
			"\n\nThe statement API contract changed. Bump STATEMENT_API_VERSION and update "
			"consumers.",
		)
		self.assertTrue(
			manifest["without_email"],
			"\n\nFixture bug: without_email is empty, so the row-shape assertion below would test "
			"nothing. The fixture must leave at least one in-scope customer without an address.",
		)
		self.assertEqual(
			set(manifest["without_email"][0]),
			{"customer", "customer_name"},
			"\n\nThe without_email row shape changed. Bump STATEMENT_API_VERSION and update "
			"consumers.",
		)

		with patch("frappe.enqueue"):
			result = email_bulk_statements(company=TEST_COMPANY, template=tpl.name)
		self.assertEqual(
			set(result),
			{"batches"},
			"\n\nemail_bulk_statements' return shape changed. Bump STATEMENT_API_VERSION and "
			"update consumers.",
		)

	# ── batch worker ─────────────────────────────────────────────────────────

	def test_narrow_statement_doc_narrows_to_exactly_the_given_customers(self):
		tpl = self._make_template()
		self.assertEqual(len(tpl.customers), 2)

		doc = _narrow_statement_doc(tpl.name, [{"customer": TEST_CUSTOMER, "customer_name": "x"}])

		self.assertTrue(doc.is_new())
		self.assertEqual(len(doc.customers), 1)
		self.assertEqual(doc.customers[0].customer, TEST_CUSTOMER)
		# The template itself must stay untouched.
		self.assertEqual(
			frappe.db.count("Process Statement Of Accounts Customer", {"parent": tpl.name}), 2
		)

	def test_narrow_statement_doc_leaves_template_dates_untouched_when_as_of_date_is_none(self):
		"""This is what lets the desk path send a saved PSOA record for the period it was
		configured with, rather than silently re-dating it to today."""
		tpl = self._make_template(report="Accounts Receivable")

		doc = _narrow_statement_doc(
			tpl.name, [{"customer": TEST_CUSTOMER, "customer_name": "x"}], as_of_date=None
		)

		self.assertEqual(getdate(doc.posting_date), getdate(tpl.posting_date))
		self.assertEqual(getdate(doc.from_date), getdate(tpl.from_date))
		self.assertEqual(getdate(doc.to_date), getdate(tpl.to_date))

	def test_narrow_statement_doc_maps_as_of_date_like_build_statement_doc_when_given(self):
		as_of = "2026-03-31"

		ar_tpl = self._make_template(report="Accounts Receivable")
		ar_doc = _narrow_statement_doc(
			ar_tpl.name, [{"customer": TEST_CUSTOMER, "customer_name": "x"}], as_of_date=as_of
		)
		self.assertEqual(getdate(ar_doc.posting_date), getdate(as_of))

		gl_tpl = self._make_template(report="General Ledger", filter_duration=3)
		gl_doc = _narrow_statement_doc(
			gl_tpl.name, [{"customer": TEST_CUSTOMER, "customer_name": "x"}], as_of_date=as_of
		)
		self.assertEqual(getdate(gl_doc.to_date), getdate(as_of))
		self.assertEqual(getdate(gl_doc.from_date), getdate(add_months(as_of, -3)))

	def test_enqueue_statement_batches_splits_customers_into_disjoint_batches_covering_all(self):
		"""The assertion that matters: a chunker that drops or duplicates a customer either
		silently skips someone or mails them twice."""
		tpl = self._make_template()
		rows = [{"customer": f"BATCH-CUST-{i}"} for i in range(120)]

		with patch("frappe.enqueue") as mock_enqueue:
			batch_count = enqueue_statement_batches(tpl.name, rows, batch_size=50)

		self.assertEqual(batch_count, 3)
		self.assertEqual(mock_enqueue.call_count, 3)

		batches = [call.kwargs["customer_rows"] for call in mock_enqueue.call_args_list]
		self.assertEqual([len(b) for b in batches], [50, 50, 20])

		seen = [row["customer"] for batch in batches for row in batch]
		# No duplicates and nothing dropped: every input customer appears exactly once.
		self.assertEqual(len(seen), len(set(seen)))
		self.assertEqual(sorted(seen), sorted(row["customer"] for row in rows))

	def test_enqueue_statement_batches_job_ids_are_distinct_and_deduplicated(self):
		tpl = self._make_template()
		rows = [{"customer": f"BATCH-CUST-{i}"} for i in range(120)]

		with patch("frappe.enqueue") as mock_enqueue:
			enqueue_statement_batches(tpl.name, rows, batch_size=50)

		job_ids = [call.kwargs["job_id"] for call in mock_enqueue.call_args_list]
		self.assertEqual(len(job_ids), len(set(job_ids)))
		self.assertTrue(all(call.kwargs["deduplicate"] for call in mock_enqueue.call_args_list))

	def test_enqueue_statement_batches_job_id_varies_across_runs_of_the_same_desk_record(self):
		"""THE FINDING ITEM 3 CLOSES. The desk path always passes as_of_date=None (it sends for the
		record's own configured period), so before this fix the job id was CONSTANT across runs of
		the same record. With deduplicate=True, Frappe returns None on a match without raising,
		while enqueue_statement_batches still returns the batch count — so a user who sends a
		record, spots a mistake, fixes it, and clicks again would have every batch id collide with
		one still queued (or just completed): nothing enqueues, and the toast still claims success.
		A coarse per-minute run bucket must make a later call (a different "run") produce different
		job ids even though template/customers/as_of_date are byte-for-byte identical."""
		tpl = self._make_template()
		rows = [{"customer": TEST_CUSTOMER}]

		with (
			patch("frappe.enqueue") as mock_enqueue,
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.now_datetime",
				return_value=get_datetime("2026-01-01 00:00:00"),
			),
		):
			enqueue_statement_batches(tpl.name, rows, as_of_date=None, caller="psoa")
		first_run_job_id = mock_enqueue.call_args.kwargs["job_id"]

		with (
			patch("frappe.enqueue") as mock_enqueue,
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.now_datetime",
				return_value=get_datetime("2026-01-01 00:05:00"),
			),
		):
			enqueue_statement_batches(tpl.name, rows, as_of_date=None, caller="psoa")
		second_run_job_id = mock_enqueue.call_args.kwargs["job_id"]

		self.assertNotEqual(first_run_job_id, second_run_job_id)

	def test_enqueue_statement_batches_job_id_is_namespaced_by_caller(self):
		"""The desk (psoa) and POS callers must not collide even if they were ever called with the
		same template/date/batch-index, since a shared namespace would let one caller's dedupe
		swallow the other's send."""
		tpl = self._make_template()
		rows = [{"customer": TEST_CUSTOMER}]

		with patch("frappe.enqueue") as mock_enqueue:
			enqueue_statement_batches(tpl.name, rows, as_of_date=None, caller="psoa")
			psoa_job_id = mock_enqueue.call_args.kwargs["job_id"]

			enqueue_statement_batches(tpl.name, rows, as_of_date=None, caller="pos")
			pos_job_id = mock_enqueue.call_args.kwargs["job_id"]

		self.assertNotEqual(psoa_job_id, pos_job_id)

	def test_send_statement_batch_skips_customer_with_no_recipient_without_aborting(self):
		"""Ported from the deleted _send_bulk_statements' equivalent test: one customer with no
		resolvable address (an empty list, not a PermissionError) must cost only that customer,
		not the batch. Distinct from the PermissionError case covered by
		test_send_statement_batch_permission_error_is_skipped_without_being_logged."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		create_sales_invoice(customer=OTHER_CUSTOMER, rate=700)
		tpl = self._make_template()
		rows = [
			{"customer": TEST_CUSTOMER, "customer_name": "x"},
			{"customer": OTHER_CUSTOMER, "customer_name": "y"},
		]

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
			_send_statement_batch(tpl.name, rows)

		mock_sendmail.assert_called_once()
		self.assertEqual(mock_sendmail.call_args.kwargs["reference_name"], TEST_CUSTOMER)

	def test_send_statement_batch_uses_get_recipients_and_cc_when_use_record_recipients_is_true(self):
		"""The desk path (use_record_recipients=True) must route through ERPNext's own
		get_recipients_and_cc so primary_mandatory/cc_to are honoured, not through the live
		_resolve_recipients lookup — regardless of whether the row itself carries an email."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		tpl = self._make_template()
		rows = [
			{
				"customer": TEST_CUSTOMER,
				"customer_name": "x",
				"billing_email": "billing@example.com",
			}
		]

		with (
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.get_recipients_and_cc",
				return_value=(["billing@example.com"], []),
			) as mock_get_recipients_and_cc,
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts._resolve_recipients"
			) as mock_resolve_recipients,
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.get_pdf",
				return_value=b"%PDF-fake",
			),
			patch("frappe.sendmail") as mock_sendmail,
		):
			_send_statement_batch(tpl.name, rows, use_record_recipients=True)

		mock_get_recipients_and_cc.assert_called_once()
		self.assertEqual(mock_get_recipients_and_cc.call_args.args[0], TEST_CUSTOMER)
		mock_resolve_recipients.assert_not_called()
		mock_sendmail.assert_called_once()
		self.assertEqual(mock_sendmail.call_args.kwargs["recipients"], ["billing@example.com"])

	def test_send_statement_batch_uses_resolve_recipients_when_use_record_recipients_is_false(self):
		"""The POS path (use_record_recipients=False, the default) has no saved record to honour
		and must resolve live rather than going through the PSOA-record-only get_recipients_and_cc,
		even though its rows carry neither email field."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		tpl = self._make_template()
		rows = [{"customer": TEST_CUSTOMER, "customer_name": "x"}]

		with (
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts._resolve_recipients",
				return_value=["live@example.com"],
			) as mock_resolve_recipients,
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.get_recipients_and_cc"
			) as mock_get_recipients_and_cc,
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.get_pdf",
				return_value=b"%PDF-fake",
			),
			patch("frappe.sendmail") as mock_sendmail,
		):
			_send_statement_batch(tpl.name, rows)

		mock_resolve_recipients.assert_called_once_with(TEST_CUSTOMER)
		mock_get_recipients_and_cc.assert_not_called()
		mock_sendmail.assert_called_once()
		self.assertEqual(mock_sendmail.call_args.kwargs["recipients"], ["live@example.com"])

	def test_send_statement_batch_desk_row_with_both_emails_empty_does_not_fall_through_to_live_resolution(self):
		"""THE FINDING ITEM 1 CLOSES. ERPNext's fetch_customers legitimately writes rows with BOTH
		billing_email and primary_email empty (a customer with no billing contact, and
		primary_mandatory off) — and its own "Send Emails" button skips those rows. Before this
		fix, _batch_recipients branched on the row's own data, so an empty desk row fell through
		to _resolve_recipients and could mail a customer ERPNext's own button deliberately
		excludes. use_record_recipients=True must still route through get_recipients_and_cc even
		when the row carries neither field, and must not send when that returns no recipients."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		tpl = self._make_template()
		rows = [{"customer": TEST_CUSTOMER, "customer_name": "x", "billing_email": "", "primary_email": ""}]

		with (
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.get_recipients_and_cc",
				return_value=([], []),
			) as mock_get_recipients_and_cc,
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts._resolve_recipients",
				return_value=["should-never-be-used@example.com"],
			) as mock_resolve_recipients,
			patch("frappe.sendmail") as mock_sendmail,
		):
			_send_statement_batch(tpl.name, rows, use_record_recipients=True)

		mock_get_recipients_and_cc.assert_called_once()
		mock_resolve_recipients.assert_not_called()
		mock_sendmail.assert_not_called()

	def test_send_statement_batch_pos_row_with_both_emails_empty_resolves_live(self):
		"""The same empty-fields row, sent down the POS path (use_record_recipients=False), has no
		record to honour and must resolve live — this is the other half of the item 1 fix: the
		caller's declared intent decides the source, never the row's own (possibly coincidentally
		empty) data."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		tpl = self._make_template()
		rows = [{"customer": TEST_CUSTOMER, "customer_name": "x", "billing_email": "", "primary_email": ""}]

		with (
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts._resolve_recipients",
				return_value=["live@example.com"],
			) as mock_resolve_recipients,
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.get_recipients_and_cc"
			) as mock_get_recipients_and_cc,
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.get_pdf",
				return_value=b"%PDF-fake",
			),
			patch("frappe.sendmail") as mock_sendmail,
		):
			_send_statement_batch(tpl.name, rows)

		mock_resolve_recipients.assert_called_once_with(TEST_CUSTOMER)
		mock_get_recipients_and_cc.assert_not_called()
		mock_sendmail.assert_called_once()
		self.assertEqual(mock_sendmail.call_args.kwargs["recipients"], ["live@example.com"])

	def test_send_statement_batch_logs_and_skips_a_render_failure_without_aborting_the_batch(self):
		"""Pins the reason get_report_pdf is not used: a render failure on one customer in the
		batch must cost only that customer."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		create_sales_invoice(customer=OTHER_CUSTOMER, rate=700)
		tpl = self._make_template()
		rows = [
			{"customer": TEST_CUSTOMER, "customer_name": "x"},
			{"customer": OTHER_CUSTOMER, "customer_name": "y"},
		]

		def side_effect(customer):
			return ["good@example.com"] if customer == TEST_CUSTOMER else ["bad@example.com"]

		def failing_get_pdf(html, options=None):
			if OTHER_CUSTOMER in html:
				raise Exception("simulated render failure")
			return b"%PDF-fake"

		with (
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts._resolve_recipients",
				side_effect=side_effect,
			),
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.get_pdf",
				side_effect=failing_get_pdf,
			),
			patch("frappe.sendmail") as mock_sendmail,
			patch("frappe.log_error") as mock_log_error,
		):
			_send_statement_batch(tpl.name, rows)

		mock_sendmail.assert_called_once()
		self.assertEqual(mock_sendmail.call_args.kwargs["reference_name"], TEST_CUSTOMER)
		mock_log_error.assert_called_once()
		self.assertIn(OTHER_CUSTOMER, mock_log_error.call_args.kwargs["message"])

	def test_send_statement_batch_permission_error_is_skipped_without_being_logged(self):
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		create_sales_invoice(customer=OTHER_CUSTOMER, rate=700)
		tpl = self._make_template()
		rows = [
			{"customer": TEST_CUSTOMER, "customer_name": "x"},
			{"customer": OTHER_CUSTOMER, "customer_name": "y"},
		]

		def side_effect(customer):
			if customer == OTHER_CUSTOMER:
				raise frappe.PermissionError
			return ["good@example.com"]

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
			_send_statement_batch(tpl.name, rows)

		mock_sendmail.assert_called_once()
		self.assertEqual(mock_sendmail.call_args.kwargs["reference_name"], TEST_CUSTOMER)
		mock_log_error.assert_not_called()

	def test_send_statement_batch_never_saves_the_doc(self):
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		tpl = self._make_template()
		before = frappe.db.get_value("Process Statement Of Accounts", tpl.name, "modified")
		rows = [{"customer": TEST_CUSTOMER, "customer_name": "x"}]

		with (
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts._resolve_recipients",
				return_value=["good@example.com"],
			),
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.get_pdf",
				return_value=b"%PDF-fake",
			),
			patch("frappe.sendmail"),
		):
			_send_statement_batch(tpl.name, rows)

		self.assertEqual(
			frappe.db.count("Process Statement Of Accounts Customer", {"parent": tpl.name}), 2
		)
		self.assertEqual(
			frappe.db.get_value("Process Statement Of Accounts", tpl.name, "modified"), before
		)

	def test_send_statement_batch_uses_the_records_configured_sender(self):
		"""ERPNext's own send_emails resolves doc.sender to an Email Account's email_id and passes
		it to frappe.sendmail; without this, every batched statement would go from the site
		default instead of the accounts mailbox the record was configured with, and customer
		replies would land in the wrong inbox on every desk send."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		tpl = self._make_template(sender="_Test Email Account 1")
		rows = [{"customer": TEST_CUSTOMER, "customer_name": "x"}]

		with (
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts._resolve_recipients",
				return_value=["good@example.com"],
			),
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.get_pdf",
				return_value=b"%PDF-fake",
			),
			patch("frappe.sendmail") as mock_sendmail,
		):
			_send_statement_batch(tpl.name, rows)

		mock_sendmail.assert_called_once()
		self.assertEqual(mock_sendmail.call_args.kwargs["sender"], "test@example.com")

	def test_send_statement_batch_falls_back_to_session_user_when_no_sender_configured(self):
		"""Mirrors ERPNext's own fallback exactly: a record with no configured sender must send as
		the acting user, not silently pass no sender at all."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		tpl = self._make_template()
		self.assertFalse(tpl.sender)
		rows = [{"customer": TEST_CUSTOMER, "customer_name": "x"}]

		with (
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts._resolve_recipients",
				return_value=["good@example.com"],
			),
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.get_pdf",
				return_value=b"%PDF-fake",
			),
			patch("frappe.sendmail") as mock_sendmail,
		):
			_send_statement_batch(tpl.name, rows)

		mock_sendmail.assert_called_once()
		self.assertEqual(mock_sendmail.call_args.kwargs["sender"], frappe.session.user)

	def test_send_statement_batch_exposes_recipients_in_the_header(self):
		"""Mirrors ERPNext's own send_emails, which passes expose_recipients="header" so CC'd
		people are visible in the mail header. Without this, a CC on the desk path is hidden
		where the standard "Send Emails" button would show it."""
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		create_sales_invoice(customer=TEST_CUSTOMER, rate=500)
		tpl = self._make_template()
		rows = [{"customer": TEST_CUSTOMER, "customer_name": "x"}]

		with (
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts._resolve_recipients",
				return_value=["good@example.com"],
			),
			patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.get_pdf",
				return_value=b"%PDF-fake",
			),
			patch("frappe.sendmail") as mock_sendmail,
		):
			_send_statement_batch(tpl.name, rows)

		mock_sendmail.assert_called_once()
		self.assertEqual(mock_sendmail.call_args.kwargs["expose_recipients"], "header")

	# ── desk button endpoint ─────────────────────────────────────────────────

	def test_send_psoa_in_batches_uses_the_records_own_customer_rows(self):
		"""The endpoint must read doc.customers - the rows ERPNext's own fetch_customers
		populated on the saved record, carrying customer_name/billing_email/primary_email - and
		must not substitute the company-wide customer list built by the POS path's
		_company_customers.

		All four fields are pinned, not just customer/billing_email: customer_name is what the
		email templates render, and primary_email is the only place primary_mandatory's source
		value is populated, so dropping either in a future refactor would silently degrade the
		desk send without any test noticing."""
		tpl = self._make_template()
		frappe.db.set_value(
			"Process Statement Of Accounts Customer",
			{"parent": tpl.name, "customer": TEST_CUSTOMER},
			{
				"customer_name": "Test Customer Display Name",
				"billing_email": "billing@example.com",
				"primary_email": "primary@example.com",
			},
		)

		with patch("frappe.enqueue") as mock_enqueue:
			result = send_psoa_in_batches(tpl.name)

		mock_enqueue.assert_called_once()
		sent_rows = mock_enqueue.call_args.kwargs["customer_rows"]
		sent_customers = sorted(row["customer"] for row in sent_rows)
		self.assertEqual(sent_customers, sorted([TEST_CUSTOMER, OTHER_CUSTOMER]))

		by_customer = {row["customer"]: row for row in sent_rows}
		self.assertEqual(by_customer[TEST_CUSTOMER]["customer_name"], "Test Customer Display Name")
		self.assertEqual(by_customer[TEST_CUSTOMER]["billing_email"], "billing@example.com")
		self.assertEqual(by_customer[TEST_CUSTOMER]["primary_email"], "primary@example.com")
		self.assertEqual(result, {"batches": 1, "customers": 2})

	def test_send_psoa_in_batches_passes_as_of_date_none(self):
		"""The single easiest thing to get wrong here: passing a date would silently re-date the
		user's configured record to today instead of keeping its own posting/from/to dates."""
		tpl = self._make_template(report="Accounts Receivable")

		with patch("frappe.enqueue") as mock_enqueue:
			send_psoa_in_batches(tpl.name)

		mock_enqueue.assert_called_once()
		self.assertIsNone(mock_enqueue.call_args.kwargs["as_of_date"])

	def test_send_psoa_in_batches_throws_when_record_has_no_customers(self):
		tpl = self._make_template()
		# Bypass document validation (which itself requires at least one customer) to reach the
		# state the endpoint's own guard exists for: a saved record with an empty customers table.
		frappe.db.delete("Process Statement Of Accounts Customer", {"parent": tpl.name})

		with patch("frappe.enqueue") as mock_enqueue:
			with self.assertRaises(frappe.ValidationError):
				send_psoa_in_batches(tpl.name)

		mock_enqueue.assert_not_called()

	def test_send_psoa_in_batches_never_sends_mail_directly(self):
		"""Nothing about the desk button path may touch frappe.sendmail; it only enqueues."""
		tpl = self._make_template()

		with patch("frappe.enqueue") as mock_enqueue, patch("frappe.sendmail") as mock_sendmail:
			send_psoa_in_batches(tpl.name)

		mock_enqueue.assert_called_once()
		mock_sendmail.assert_not_called()

	def test_send_psoa_in_batches_is_post_only(self):
		"""THE FINDING ITEM 4 CLOSES. @frappe.whitelist() with no methods accepts GET, and Frappe
		only validates CSRF for unsafe methods — so an <img src="...?document_name=X"> on any page
		a logged-in user visits would fire a customer-wide mail blast. psoa_batch.js already calls
		this via frappe.call, which POSTs, so restricting to POST changes nothing for the real
		caller."""
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[send_psoa_in_batches], ["POST"])

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
