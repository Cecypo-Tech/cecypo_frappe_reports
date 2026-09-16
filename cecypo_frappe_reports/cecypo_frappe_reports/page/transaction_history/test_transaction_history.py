# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt


class TestTransactionHistoryPage(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		# IntegrationTestCase only rolls back the DB once, in a class-level cleanup, so
		# per-test fixtures (advance Payment Entries etc.) would otherwise leak between
		# test methods within this class and pollute each other's party-scoped assertions.
		# Isolate each test with its own savepoint.
		self._test_savepoint = f"test_transaction_history_{frappe.generate_hash(length=8)}"
		frappe.db.savepoint(self._test_savepoint)

	def tearDown(self):
		try:
			frappe.db.rollback(save_point=self._test_savepoint)
		except Exception:
			# A failed document operation earlier in the test may have already discarded the
			# savepoint (e.g. MySQL implicitly releases savepoints on some errors). Fall back
			# to a full rollback so later tests still start from a clean slate.
			frappe.db.rollback()
		super().tearDown()

	def test_get_customer_history_returns_list(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_customer_history,
		)

		rows = get_customer_history(customer="__nonexistent__", company="_Test Company")
		self.assertIsInstance(rows, list)
		self.assertEqual(rows, [])

	def test_get_customer_item_transactions_returns_list(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_customer_item_transactions,
		)

		rows = get_customer_item_transactions(
			customer="__nonexistent__", item_code="__nonexistent__", company="_Test Company"
		)
		self.assertIsInstance(rows, list)
		self.assertEqual(rows, [])

	def test_get_supplier_history_returns_list_pr(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_supplier_history,
		)

		rows = get_supplier_history(supplier="__nonexistent__", company="_Test Company", source="pr")
		self.assertIsInstance(rows, list)
		self.assertEqual(rows, [])

	def test_get_supplier_history_returns_list_pi(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_supplier_history,
		)

		rows = get_supplier_history(supplier="__nonexistent__", company="_Test Company", source="pi")
		self.assertIsInstance(rows, list)
		self.assertEqual(rows, [])

	def test_get_supplier_item_transactions_pr(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_supplier_item_transactions,
		)

		rows = get_supplier_item_transactions(
			supplier="__nonexistent__", item_code="__nonexistent__", company="_Test Company", source="pr"
		)
		self.assertIsInstance(rows, list)

	def test_get_supplier_item_transactions_pi(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_supplier_item_transactions,
		)

		rows = get_supplier_item_transactions(
			supplier="__nonexistent__", item_code="__nonexistent__", company="_Test Company", source="pi"
		)
		self.assertIsInstance(rows, list)

	def test_get_item_history_source_pr(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_item_history,
		)

		result = get_item_history(item="__nonexistent__", company="_Test Company")
		self.assertIn("purchases", result)
		self.assertIn("sales", result)
		self.assertIsInstance(result["purchases"], list)

	def test_get_item_history_source_pi(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_item_history,
		)

		result = get_item_history(item="__nonexistent__", company="_Test Company")
		self.assertIn("purchases", result)
		self.assertIn("sales", result)
		self.assertIsInstance(result["purchases"], list)

	def test_summary_rows_have_status_aggregate_fields(self):
		"""Verify the query runs without error with the new aggregate fields in the SELECT."""
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_customer_history,
		)

		rows = get_customer_history(customer="__nonexistent__", company="_Test Company")
		self.assertIsInstance(rows, list)

	def test_detail_rows_have_status_field(self):
		"""Verify the query runs without error with status added to the SELECT."""
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_customer_item_transactions,
		)

		rows = get_customer_item_transactions(
			customer="__nonexistent__", item_code="__nonexistent__", company="_Test Company"
		)
		self.assertIsInstance(rows, list)

	def test_get_receivables_nets_return_invoice_against_total(self):
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_receivables,
		)

		si = create_sales_invoice(customer="_Test Customer", posting_date="2025-06-15", qty=1, rate=1000)
		create_sales_invoice(
			customer="_Test Customer",
			posting_date="2025-06-16",
			qty=-1,
			rate=1000,
			is_return=1,
			return_against=si.name,
		)

		rows = get_receivables(company="_Test Company", as_of_date="2025-06-16", customer="_Test Customer")
		row = next((r for r in rows if r["customer"] == "_Test Customer"), None)
		self.assertIsNone(row)  # fully returned invoice must not appear as outstanding

	def test_get_receivables_future_allocated_payment_stays_out_of_outstanding(self):
		"""An allocated future payment reveals itself only via future_payments (matching the
		standard Accounts Receivable report exactly) — it never reduces outstanding, since the
		invoice legally remains outstanding until that future date arrives. Only *unallocated*
		future advances (see test_get_receivables_includes_future_dated_advance) net into
		outstanding when the toggle is on."""
		from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_payment_entry
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_receivables,
		)

		si = create_sales_invoice(customer="_Test Customer", posting_date="2025-06-15", qty=1, rate=1000)

		pe = create_payment_entry(
			payment_type="Receive",
			party_type="Customer",
			party="_Test Customer",
			paid_from="Debtors - _TC",
			paid_to="_Test Cash - _TC",
			paid_amount=1000,
			save=True,
		)
		pe.posting_date = "2025-06-25"  # after as_of_date below
		pe.set_posting_time = 1
		pe.append("references", {
			"reference_doctype": "Sales Invoice",
			"reference_name": si.name,
			"allocated_amount": 1000,
		})
		pe.save()
		pe.submit()

		# Without the toggle: outstanding stays at the pre-payment amount, no future_payments.
		rows = get_receivables(company="_Test Company", as_of_date="2025-06-15", customer="_Test Customer")
		row = next(r for r in rows if r["customer"] == "_Test Customer")
		self.assertEqual(row["outstanding"], si.grand_total)
		self.assertEqual(row["future_payments"], 0.0)

		# With the toggle: outstanding is unchanged, but future_payments reveals the allocation.
		rows_future = get_receivables(
			company="_Test Company", as_of_date="2025-06-15", customer="_Test Customer", show_future_payments=1
		)
		row_future = next(r for r in rows_future if r["customer"] == "_Test Customer")
		self.assertEqual(row_future["outstanding"], si.grand_total)
		self.assertEqual(row_future["future_payments"], 1000.0)

	def test_get_receivables_includes_advance_only_customer(self):
		from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_payment_entry

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_receivables,
		)

		pe = create_payment_entry(
			payment_type="Receive",
			party_type="Customer",
			party="_Test Customer",
			paid_from="Debtors - _TC",
			paid_to="_Test Cash - _TC",
			paid_amount=750,
			save=True,
		)
		pe.posting_date = "2025-06-15"
		pe.save()
		pe.submit()

		rows = get_receivables(company="_Test Company", as_of_date="2025-06-15")
		row = next((r for r in rows if r["customer"] == "_Test Customer"), None)
		self.assertIsNotNone(row)
		self.assertEqual(row["outstanding"], -750.0)  # net credit balance, no invoices
		self.assertGreaterEqual(row["unallocated_advance"], 750.0)

	def test_get_receivables_includes_future_dated_advance(self):
		"""A future-dated unallocated advance is invisible by default (matching the standard
		Accounts Receivable report) and only surfaces — netted into outstanding — once
		show_future_payments is on.

		ERPNext only relaxes its date cutoff for an *unallocated* payment when that payment's
		own ledger entry `creation` timestamp is on/before the report date (see
		ReceivablePayableReport.prepare_ple_query) — i.e. "recorded today, dated for a future
		clearing date", exactly like a real post-dated cheque. Backdate the Payment Ledger
		Entry's creation directly so a fixed as_of_date can be used like the rest of this suite,
		without tripping the 2026 Fiscal Year's company restriction (see test docs elsewhere in
		this file / the advance-only-party investigation for that landmine).
		"""
		from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_payment_entry
		from frappe.utils import getdate

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_receivables,
		)

		pe = create_payment_entry(
			payment_type="Receive",
			party_type="Customer",
			party="_Test Customer",
			paid_from="Debtors - _TC",
			paid_to="_Test Cash - _TC",
			paid_amount=750,
			save=True,
		)
		pe.posting_date = "2025-06-25"
		pe.save()
		pe.submit()
		frappe.db.set_value(
			"Payment Ledger Entry", {"voucher_no": pe.name}, "creation", "2025-06-15", update_modified=False
		)

		rows = get_receivables(company="_Test Company", as_of_date="2025-06-15")
		row = next((r for r in rows if r["customer"] == "_Test Customer"), None)
		self.assertIsNone(row)

		rows_future = get_receivables(company="_Test Company", as_of_date="2025-06-15", show_future_payments=1)
		row_future = next((r for r in rows_future if r["customer"] == "_Test Customer"), None)
		self.assertIsNotNone(row_future)
		self.assertEqual(row_future["outstanding"], -750.0)
		self.assertGreaterEqual(row_future["unallocated_advance"], 750.0)
		self.assertEqual(getdate(row_future["last_payment"]), getdate("2025-06-25"))

	def test_get_payables_includes_advance_only_supplier(self):
		from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_payment_entry

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_payables,
		)

		pe = create_payment_entry(
			payment_type="Pay",
			party_type="Supplier",
			party="_Test Supplier",
			paid_from="_Test Bank - _TC",
			paid_to="Creditors - _TC",
			paid_amount=500,
			save=True,
		)
		pe.posting_date = "2025-06-15"
		pe.save()
		pe.submit()

		rows = get_payables(company="_Test Company", as_of_date="2025-06-15")
		row = next((r for r in rows if r["supplier"] == "_Test Supplier"), None)
		self.assertIsNotNone(row)
		self.assertEqual(row["outstanding"], -500.0)  # net credit balance, no invoices
		self.assertGreaterEqual(row["unallocated_advance"], 500.0)

	def test_get_payables_includes_future_dated_advance(self):
		"""A future-dated unallocated advance is invisible by default (matching the standard
		Accounts Payable report) and only surfaces — netted into outstanding — once
		show_future_payments is on. See test_get_receivables_includes_future_dated_advance for
		why the Payment Ledger Entry's creation is backdated directly."""
		from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_payment_entry
		from frappe.utils import getdate

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_payables,
		)

		pe = create_payment_entry(
			payment_type="Pay",
			party_type="Supplier",
			party="_Test Supplier",
			paid_from="_Test Bank - _TC",
			paid_to="Creditors - _TC",
			paid_amount=500,
			save=True,
		)
		pe.posting_date = "2025-06-25"
		pe.save()
		pe.submit()
		frappe.db.set_value(
			"Payment Ledger Entry", {"voucher_no": pe.name}, "creation", "2025-06-15", update_modified=False
		)

		rows = get_payables(company="_Test Company", as_of_date="2025-06-15")
		row = next((r for r in rows if r["supplier"] == "_Test Supplier"), None)
		self.assertIsNone(row)

		rows_future = get_payables(company="_Test Company", as_of_date="2025-06-15", show_future_payments=1)
		row_future = next((r for r in rows_future if r["supplier"] == "_Test Supplier"), None)
		self.assertIsNotNone(row_future)
		self.assertEqual(row_future["outstanding"], -500.0)
		self.assertGreaterEqual(row_future["unallocated_advance"], 500.0)
		self.assertEqual(getdate(row_future["last_payment"]), getdate("2025-06-25"))

	def test_get_receivables_invoice_and_advance_not_double_counted(self):
		from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_payment_entry
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_receivables,
		)

		si = create_sales_invoice(customer="_Test Customer", posting_date="2025-06-15")

		pe = create_payment_entry(
			payment_type="Receive",
			party_type="Customer",
			party="_Test Customer",
			paid_from="Debtors - _TC",
			paid_to="_Test Cash - _TC",
			paid_amount=300,
			save=True,
		)
		pe.posting_date = "2025-06-15"
		pe.save()
		pe.submit()

		rows = get_receivables(company="_Test Company", as_of_date="2025-06-15", customer="_Test Customer")
		self.assertEqual(len(rows), 1)
		# Net balance: the unpaid invoice minus the unallocated advance sitting on the account —
		# not si.outstanding_amount alone, which would ignore the 300 advance entirely.
		self.assertEqual(rows[0]["outstanding"], flt(si.grand_total - 300, 2))
		self.assertEqual(rows[0]["unallocated_advance"], 300.0)

	def test_get_party_details_total_outstanding_matches_get_receivables(self):
		"""The party-info dialog's "Total Outstanding" must always agree with the grid row it was
		opened from. Regression for a bug where get_party_details computed its own
		SUM(Sales Invoice.outstanding_amount) instead of delegating to the same AR report engine
		as get_receivables, so the two disagreed whenever an unallocated advance was on the
		account (the advance nets into get_receivables' outstanding but was invisible to the
		bespoke invoice-only sum)."""
		from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_payment_entry
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_party_details,
			get_receivables,
		)

		create_sales_invoice(customer="_Test Customer", posting_date="2025-06-15")

		pe = create_payment_entry(
			payment_type="Receive",
			party_type="Customer",
			party="_Test Customer",
			paid_from="Debtors - _TC",
			paid_to="_Test Cash - _TC",
			paid_amount=300,
			save=True,
		)
		pe.posting_date = "2025-06-15"
		pe.save()
		pe.submit()

		rows = get_receivables(company="_Test Company", as_of_date="2025-06-15", customer="_Test Customer")
		self.assertEqual(len(rows), 1)

		details = get_party_details(
			party_type="customer", party="_Test Customer", company="_Test Company", as_of_date="2025-06-15"
		)
		self.assertEqual(details["stats"]["total_unpaid"], rows[0]["outstanding"])

	def test_get_payables_fully_allocated_advance_produces_no_row(self):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
		from erpnext.accounts.doctype.purchase_invoice.test_purchase_invoice import make_purchase_invoice

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_payables,
		)

		pi = make_purchase_invoice(supplier="_Test Supplier", posting_date="2025-06-15", do_not_save=1)
		# Without this, ERPNext's TransactionBase.validate_posting_time() silently overwrites
		# posting_date/posting_time with "now" on every save (make_purchase_invoice, unlike
		# create_sales_invoice, doesn't set this flag itself).
		pi.set_posting_time = 1
		pi.bill_no = "TEST-BILL-0001"
		pi.bill_date = "2025-06-15"
		pi.insert()
		pi.submit()

		pe = get_payment_entry(dt="Purchase Invoice", dn=pi.name)
		pe.posting_date = "2025-06-15"
		pe.insert()
		pe.submit()

		self.assertEqual(pe.unallocated_amount, 0.0)

		rows = get_payables(company="_Test Company", as_of_date="2025-06-15", supplier="_Test Supplier")
		self.assertEqual(rows, [])

	def test_get_receivables_customer_filter_scopes_advance_only_seeding(self):
		from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_payment_entry

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_receivables,
		)

		pe1 = create_payment_entry(
			payment_type="Receive",
			party_type="Customer",
			party="_Test Customer",
			paid_from="Debtors - _TC",
			paid_to="_Test Cash - _TC",
			paid_amount=750,
			save=True,
		)
		pe1.posting_date = "2025-06-15"
		pe1.save()
		pe1.submit()

		pe2 = create_payment_entry(
			payment_type="Receive",
			party_type="Customer",
			party="_Test Customer 1",
			paid_from="Debtors - _TC",
			paid_to="_Test Cash - _TC",
			paid_amount=750,
			save=True,
		)
		pe2.posting_date = "2025-06-15"
		pe2.save()
		pe2.submit()

		rows = get_receivables(company="_Test Company", as_of_date="2025-06-15", customer="_Test Customer")
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["customer"], "_Test Customer")

	def _details(self, **kw):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_party_details,
		)

		args = {"party_type": "customer", "party": "_Test Customer", "company": "_Test Company", "as_of_date": frappe.utils.today()}
		args.update(kw)
		return get_party_details(**args)

	def test_party_details_has_the_snapshot_shape(self):
		d = self._details()
		for key in (
			"customer_name", "primary_contact", "contacts", "credit_limit", "payment_terms",
			"outstanding_total", "overdue_total", "overdue_count", "advances_total", "net_position",
			"invoices", "advances", "highlight", "stats",
		):
			self.assertIn(key, d, key)
		self.assertNotIn("unallocated_payments", d)
		self.assertNotIn("unallocated_total", d)
		if d["invoices"]:
			for key in ("voucher_no", "date", "due_date", "grand_total", "paid", "outstanding_amount", "days_overdue", "status"):
				self.assertIn(key, d["invoices"][0], key)

	def test_billing_stats_only_for_allowed_roles(self):
		# Administrator holds every role, so stats are present.
		d = self._details()
		self.assertIn("annual_billing", d["stats"])
		self.assertIn("lifetime_billing", d["stats"])
		# A plain user sees neither.
		from unittest.mock import patch

		# "Accounts User" (not "Sales User") on purpose: get_party_details unconditionally
		# calls into ERPNext's own Accounts Receivable report (_get_party_balances) for
		# stats.total_unpaid, and that report does its own frappe.has_permission checks
		# against Journal Entry/GL Entry — a role lacking those raises PermissionError
		# before this test ever reaches the billing-stats assertion it cares about.
		# "Accounts User" has full read on those doctypes by default but isn't in
		# BILLING_STATS_ROLES, so it isolates the one thing under test.
		with patch.object(frappe, "get_roles", return_value=["All", "Guest", "Accounts User"]):
			# frappe.session is a LocalProxy wrapping a dict-subclass (_dict); patch.object's
			# `target.__dict__[name]` lookup returns None through the proxy and raises
			# TypeError before the patch even applies. patch.dict works directly against its
			# dict protocol and restores cleanly on exit.
			with patch.dict(frappe.session, {"user": "sales.user@example.com"}):
				d2 = self._details()
		self.assertNotIn("annual_billing", d2["stats"])
		self.assertNotIn("lifetime_billing", d2["stats"])
		self.assertIn("total_unpaid", d2["stats"])

	def test_highlight_rule_and_overdue_from_invoices(self):
		d = self._details()
		overdue = [r for r in d["invoices"] if r["days_overdue"] > 0]
		self.assertEqual(d["overdue_count"], len(overdue))
		self.assertEqual(d["overdue_total"], round(sum(r["outstanding_amount"] for r in overdue), 2))
		expected = "red" if overdue else ("amber" if d["outstanding_total"] > 0 or d["advances_total"] > 0 else "")
		self.assertEqual(d["highlight"], expected)
		self.assertEqual(d["net_position"], round(d["outstanding_total"] - d["advances_total"], 2))

	def test_receivables_rows_carry_overdue(self):
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
		from frappe.utils import add_days, today

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_receivables,
		)

		si = create_sales_invoice(customer="_Test Customer", company="_Test Company", rate=300, qty=1, do_not_save=True)
		si.set_posting_time = 1
		si.posting_date = add_days(today(), -40)
		si.due_date = add_days(today(), -10)
		si.insert()
		si.submit()

		rows = get_receivables(company="_Test Company", as_of_date=today())
		row = next((r for r in rows if r["customer"] == "_Test Customer"), None)
		self.assertIsNotNone(row)
		self.assertIn("overdue", row)
		self.assertGreaterEqual(row["overdue"], 300)
		for r in rows:
			self.assertGreaterEqual(r["overdue"], 0)

	def test_party_details_requires_invoice_read(self):
		from unittest.mock import patch

		with patch.object(frappe, "has_permission", side_effect=frappe.PermissionError) as perm:
			with self.assertRaises(frappe.PermissionError):
				self._details()
		self.assertEqual(perm.call_args_list[0].args[:2], ("Sales Invoice", "read"))
		self.assertTrue(perm.call_args_list[0].kwargs.get("throw"))
		self.assertEqual(perm.call_count, 1)

		with patch.object(frappe, "has_permission", side_effect=frappe.PermissionError) as perm:
			with self.assertRaises(frappe.PermissionError):
				self._details(party_type="supplier", party="_Test Supplier")
		self.assertEqual(perm.call_args_list[0].args[:2], ("Purchase Invoice", "read"))

	def test_outstanding_total_is_invoices_only_and_net_position_nets_once(self):
		from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_payment_entry
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
		from frappe.utils import add_days, today

		si = create_sales_invoice(customer="_Test Customer", company="_Test Company", rate=400, qty=1, do_not_save=True)
		si.set_posting_time = 1
		si.posting_date = add_days(today(), -5)
		si.due_date = add_days(today(), 10)
		si.insert()
		si.submit()
		pe = create_payment_entry(
			payment_type="Receive", party_type="Customer", party="_Test Customer",
			paid_from="Debtors - _TC", paid_to="_Test Cash - _TC", paid_amount=900, save=True,
		)
		pe.submit()

		d = self._details()
		self.assertEqual(d["outstanding_total"], round(sum(r["outstanding_amount"] for r in d["invoices"]), 2))
		self.assertGreaterEqual(d["outstanding_total"], 400)
		self.assertGreaterEqual(d["advances_total"], 900)
		self.assertEqual(d["net_position"], round(d["outstanding_total"] - d["advances_total"], 2))
		# stats.total_unpaid stays the grid's netted figure
		self.assertLess(d["stats"]["total_unpaid"], d["outstanding_total"])

	def _as_sales_only_user(self):
		"""A user with Sales User only — no Journal Entry read."""
		email = "_th_sales_only@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc({
				"doctype": "User", "email": email, "first_name": "TH Sales",
				"send_welcome_email": 0, "roles": [{"role": "Sales User"}],
			}).insert(ignore_permissions=True)
		return email

	def _overdue_invoice(self, rate=250):
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
		from frappe.utils import add_days, today

		si = create_sales_invoice(customer="_Test Customer", company="_Test Company", rate=rate, qty=1, do_not_save=True)
		si.set_posting_time = 1
		si.posting_date = add_days(today(), -50)
		si.due_date = add_days(today(), -45)
		si.insert()
		si.submit()
		return si

	def test_sales_only_user_gets_receivables_from_invoices(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_balance_basis, get_party_details, get_receivables, get_receivables_detail,
		)

		from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_payment_entry

		si = self._overdue_invoice()

		pe = create_payment_entry(
			payment_type="Receive", party_type="Customer", party="_Test Customer",
			paid_from="Debtors - _TC", paid_to="_Test Cash - _TC", paid_amount=600, save=True,
		)
		pe.submit()

		email = self._as_sales_only_user()
		frappe.set_user(email)
		try:
			self.assertFalse(frappe.has_permission("Journal Entry", "read"))
			self.assertEqual(get_balance_basis(), "invoices")
			rows = get_receivables(company="_Test Company", as_of_date=frappe.utils.today())
			row = next((r for r in rows if r["customer"] == "_Test Customer"), None)
			self.assertIsNotNone(row)
			self.assertGreaterEqual(row["overdue"], 250)
			self.assertGreaterEqual(row["bucket_31_60"], 250)  # 45 days past due
			detail = get_receivables_detail(customer="_Test Customer", company="_Test Company", as_of_date=frappe.utils.today())
			self.assertIn(si.name, [r["voucher_no"] for r in detail])
			d = get_party_details(party_type="customer", party="_Test Customer", company="_Test Company", as_of_date=frappe.utils.today())
			self.assertEqual(d["basis"], "invoices")
			self.assertIn(si.name, [r["voucher_no"] for r in d["invoices"]])
			self.assertIn(pe.name, [a["name"] for a in d["advances"]])
			self.assertNotIn("annual_billing", d["stats"])
		finally:
			frappe.set_user("Administrator")

	def test_accounts_user_keeps_the_ledger_report(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_balance_basis, get_party_details,
		)

		self.assertTrue(frappe.has_permission("Journal Entry", "read"))  # Administrator
		self.assertEqual(get_balance_basis(), "ledger")
		d = get_party_details(party_type="customer", party="_Test Customer", company="_Test Company", as_of_date=frappe.utils.today())
		self.assertEqual(d["basis"], "ledger")

	def test_fallback_ageing_matches_erpnext_buckets(self):
		from frappe.utils import add_days, getdate, today

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import _ageing

		as_of = getdate(today())
		for days_past_due, bucket in ((-5, "range0"), (0, "range1"), (30, "range1"), (31, "range2"), (60, "range2"), (90, "range3"), (120, "range4"), (121, "range5")):
			row = {"outstanding": 10.0}
			_ageing(row, add_days(as_of, -days_past_due), as_of)
			self.assertEqual(row[bucket], 10.0, (days_past_due, bucket, row))
			self.assertEqual(sum(v for k, v in row.items() if k.startswith("range")), 10.0)

	def test_fallback_respects_user_permissions(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import get_receivables

		self._overdue_invoice()
		email = self._as_sales_only_user()
		if not frappe.db.exists("Customer", "_Test Customer 1"):
			self.skipTest("_Test Customer 1 missing")
		frappe.get_doc({
			"doctype": "User Permission", "user": email, "allow": "Customer", "for_value": "_Test Customer 1",
		}).insert(ignore_permissions=True)
		frappe.set_user(email)
		try:
			rows = get_receivables(company="_Test Company", as_of_date=frappe.utils.today())
			self.assertNotIn("_Test Customer", [r["customer"] for r in rows])
		finally:
			frappe.set_user("Administrator")

	def test_fallback_respects_company_user_permission(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_party_details, get_receivables,
		)

		self._overdue_invoice()
		email = self._as_sales_only_user()
		if not frappe.db.exists("Company", "_Test Company 1"):
			self.skipTest("_Test Company 1 missing")
		frappe.get_doc({
			"doctype": "User Permission", "user": email, "allow": "Company", "for_value": "_Test Company 1",
		}).insert(ignore_permissions=True)
		frappe.set_user(email)
		try:
			self.assertEqual(get_receivables(company="_Test Company", as_of_date=frappe.utils.today()), [])
			with self.assertRaises(frappe.PermissionError):
				get_party_details(party_type="customer", party="_Test Customer", company="_Test Company", as_of_date=frappe.utils.today())
		finally:
			frappe.set_user("Administrator")

	def test_party_details_refuses_a_customer_outside_user_permissions(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import get_party_details

		email = self._as_sales_only_user()
		if not frappe.db.exists("Customer", "_Test Customer 1"):
			self.skipTest("_Test Customer 1 missing")
		frappe.get_doc({
			"doctype": "User Permission", "user": email, "allow": "Customer", "for_value": "_Test Customer 1",
		}).insert(ignore_permissions=True)
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				get_party_details(party_type="customer", party="_Test Customer", company="_Test Company", as_of_date=frappe.utils.today())
		finally:
			frappe.set_user("Administrator")
