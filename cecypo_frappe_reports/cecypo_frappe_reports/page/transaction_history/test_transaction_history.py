# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file

from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
	export_table,
	get_stock_card,
	search_items,
)


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
		from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_payment_entry

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_balance_basis,
			get_party_details,
			get_receivables,
			get_receivables_detail,
		)

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
			get_balance_basis,
			get_party_details,
		)

		self.assertTrue(frappe.has_permission("Journal Entry", "read"))  # Administrator
		self.assertEqual(get_balance_basis(), "ledger")
		d = get_party_details(party_type="customer", party="_Test Customer", company="_Test Company", as_of_date=frappe.utils.today())
		self.assertEqual(d["basis"], "ledger")

	def test_fallback_ageing_matches_erpnext_buckets(self):
		from frappe.utils import add_days, getdate, today

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			_ageing,
		)

		as_of = getdate(today())
		for days_past_due, bucket in ((-5, "range0"), (0, "range1"), (30, "range1"), (31, "range2"), (60, "range2"), (90, "range3"), (120, "range4"), (121, "range5")):
			row = {"outstanding": 10.0}
			_ageing(row, add_days(as_of, -days_past_due), as_of)
			self.assertEqual(row[bucket], 10.0, (days_past_due, bucket, row))
			self.assertEqual(sum(v for k, v in row.items() if k.startswith("range")), 10.0)

	def test_fallback_respects_user_permissions(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_receivables,
		)

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
			get_party_details,
			get_receivables,
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
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_party_details,
		)

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

	def _receipt(self, qty=10, rate=100, warehouse="_Test Warehouse - _TC", item="_Test Item", posting_date=None):
		from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

		return make_stock_entry(
			item_code=item, qty=qty, rate=rate, to_warehouse=warehouse,
			company="_Test Company", posting_date=posting_date,
		)

	def test_item_history_hides_cost_for_user_without_sle_read(self):
		from erpnext.stock.doctype.purchase_receipt.test_purchase_receipt import make_purchase_receipt

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_item_history,
		)

		self._receipt()
		make_purchase_receipt(
			item_code="_Test Item", qty=1, rate=50, warehouse="_Test Warehouse - _TC", supplier="_Test Supplier",
		)
		email = self._as_sales_only_user()
		frappe.set_user(email)
		try:
			self.assertFalse(frappe.has_permission("Stock Ledger Entry", "read"))
			d = get_item_history(item="_Test Item", company="_Test Company")
			self.assertFalse(d["can_see_cost"])
			self.assertNotIn("avg_rate", d["stock_metrics"])
			self.assertNotIn("stock_value", d["stock_metrics"])
			self.assertIn("current_stock", d["stock_metrics"])
			self.assertGreaterEqual(len(d["purchases"]), 1)
			for r in d["purchases"]:
				self.assertNotIn("valuation_rate", r)
		finally:
			frappe.set_user("Administrator")

	def test_item_history_shows_cost_for_administrator(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_item_history,
		)

		self._receipt()
		d = get_item_history(item="_Test Item", company="_Test Company")
		self.assertTrue(d["can_see_cost"])
		self.assertIn("avg_rate", d["stock_metrics"])
		self.assertIn("stock_value", d["stock_metrics"])

	def test_supplier_endpoints_hide_valuation_for_cost_blind_user(self):
		from erpnext.stock.doctype.purchase_receipt.test_purchase_receipt import make_purchase_receipt

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_supplier_history,
			get_supplier_item_transactions,
		)

		make_purchase_receipt(
			item_code="_Test Item", qty=1, rate=50, warehouse="_Test Warehouse - _TC", supplier="_Test Supplier",
		)
		email = self._as_sales_only_user()
		frappe.set_user(email)
		try:
			rows = get_supplier_history(supplier="_Test Supplier", company="_Test Company", source="pr")
			self.assertGreaterEqual(len(rows), 1)
			for r in rows:
				self.assertNotIn("avg_valuation_rate", r)
				self.assertNotIn("last_rate", r)
			rows = get_supplier_item_transactions(
				supplier="_Test Supplier", item_code="_Test Item", company="_Test Company", source="pr",
			)
			self.assertGreaterEqual(len(rows), 1)
			for r in rows:
				self.assertNotIn("valuation_rate", r)
		finally:
			frappe.set_user("Administrator")
		rows = get_supplier_history(supplier="_Test Supplier", company="_Test Company", source="pr")
		self.assertIn("last_rate", rows[0])

	def _as_warehouse_restricted_user(self, warehouse="_Test Warehouse - _TC"):
		email = self._as_sales_only_user()
		frappe.get_doc({
			"doctype": "User Permission", "user": email, "allow": "Warehouse", "for_value": warehouse,
		}).insert(ignore_permissions=True)
		return email

	def test_permitted_warehouses_respects_user_permission(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			_permitted_warehouses,
			_warehouse_filter,
		)

		email = self._as_warehouse_restricted_user()
		frappe.set_user(email)
		try:
			self.assertEqual(_permitted_warehouses("_Test Company"), ["_Test Warehouse - _TC"])
			self.assertEqual(_warehouse_filter("_Test Company", "_Test Warehouse 1 - _TC"), [])
			self.assertEqual(_warehouse_filter("_Test Company", None), ["_Test Warehouse - _TC"])
		finally:
			frappe.set_user("Administrator")
		self.assertIsNone(_warehouse_filter("_Test Company", None))
		self.assertEqual(
			_warehouse_filter("_Test Company", "_Test Warehouse 1 - _TC"), ["_Test Warehouse 1 - _TC"]
		)

	def test_item_history_scopes_to_permitted_warehouses(self):
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
		from erpnext.selling.doctype.sales_order.test_sales_order import make_sales_order

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_item_history,
			get_warehouse_stock,
		)

		def metrics(**kw):
			return get_item_history(item="_Test Item", company="_Test Company", **kw)["stock_metrics"]

		# The dev site carries leftover (negative) Bin rows, so assert against the pre-existing levels.
		base = metrics(warehouse="_Test Warehouse - _TC")["current_stock"]
		base_so = metrics(warehouse="_Test Warehouse - _TC")["pending_so_qty"]
		receipt = 10 + max(0, -flt(base))  # also covers the negative level so the invoice can submit
		self._receipt(qty=receipt, warehouse="_Test Warehouse - _TC")
		self._receipt(qty=5, warehouse="_Test Warehouse 1 - _TC")
		si_other = create_sales_invoice(
			item_code="_Test Item", qty=1, rate=300, update_stock=1,
			warehouse="_Test Warehouse 1 - _TC", company="_Test Company",
		)
		si_ok = create_sales_invoice(
			item_code="_Test Item", qty=1, rate=310, update_stock=1,
			warehouse="_Test Warehouse - _TC", company="_Test Company",
		)
		make_sales_order(
			item_code="_Test Item", qty=4, warehouse="_Test Warehouse 1 - _TC", company="_Test Company"
		)
		email = self._as_warehouse_restricted_user()
		frappe.set_user(email)
		try:
			d = get_item_history(item="_Test Item", company="_Test Company")
			self.assertEqual(d["stock_metrics"]["current_stock"], flt(base + receipt - 1, 2))
			self.assertIn(si_ok.name, [r["voucher_no"] for r in d["sales"]])
			self.assertNotIn(si_other.name, [r["voucher_no"] for r in d["sales"]])
			self.assertEqual(d["stock_metrics"]["pending_so_qty"], base_so)
			d2 = get_item_history(
				item="_Test Item", company="_Test Company", warehouse="_Test Warehouse 1 - _TC"
			)
			self.assertEqual(d2["stock_metrics"]["current_stock"], 0)
			self.assertEqual(d2["stock_metrics"]["pending_so_qty"], 0)
			self.assertEqual(d2["purchases"], [])
			self.assertEqual(d2["sales"], [])
			self.assertEqual(d2["open_so"], [])
			whs = [w["warehouse"] for w in get_warehouse_stock("_Test Item", "_Test Company")]
			# _Test Warehouse may hold negative leftover stock here, so assert on what must be absent.
			self.assertEqual(set(whs) - {"_Test Warehouse - _TC"}, set())
		finally:
			frappe.set_user("Administrator")
		self.assertIn(
			"_Test Warehouse 1 - _TC", [w["warehouse"] for w in get_warehouse_stock("_Test Item", "_Test Company")]
		)
		self.assertEqual(metrics(warehouse="_Test Warehouse 1 - _TC")["pending_so_qty"], 4)

	def test_open_orders_without_warehouse_still_listed_for_unrestricted_user(self):
		from erpnext.buying.doctype.purchase_order.test_purchase_order import create_purchase_order

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_item_history,
		)

		po = create_purchase_order(item_code="_Test Item", qty=3, rate=10, do_not_save=True)
		po.items[0].warehouse = None
		po.set_warehouse = None
		po.insert()
		po.submit()
		d = get_item_history(item="_Test Item", company="_Test Company")
		self.assertIn(po.name, [r["voucher_no"] for r in d["open_po"]])

	def _child_group_item(self):
		"""An Item Group under _Test Item Group and one item in it; returns item code."""
		if not frappe.db.exists("Item Group", "_TH Child Group"):
			frappe.get_doc({
				"doctype": "Item Group", "item_group_name": "_TH Child Group",
				"parent_item_group": "_Test Item Group",
			}).insert(ignore_permissions=True)
		if not frappe.db.exists("Item", "_TH Child Item"):
			frappe.get_doc({
				"doctype": "Item", "item_code": "_TH Child Item", "item_name": "TH Child Item",
				"item_group": "_TH Child Group", "stock_uom": "Nos", "is_stock_item": 1,
			}).insert(ignore_permissions=True)
		return "_TH Child Item"

	def test_search_items_includes_descendant_groups(self):
		code = self._child_group_item()
		res = search_items(company="_Test Company", item_group="_Test Item Group")
		self.assertIn(code, [i["item_code"] for i in res["items"]])

	def test_search_items_empty_without_text_or_group(self):
		self.assertEqual(search_items(company="_Test Company", txt=" ")["items"], [])

	def test_search_items_stock_price_and_cost_shape(self):
		wh = "_Test Warehouse - _TC"
		before = frappe.db.get_value("Bin", {"item_code": "_Test Item", "warehouse": wh}, "actual_qty") or 0
		self._receipt(qty=10, rate=100, warehouse=wh)
		pl = frappe.db.get_single_value("Selling Settings", "selling_price_list")
		frappe.db.delete("Item Price", {"item_code": "_Test Item", "price_list": pl})
		frappe.get_doc({
			"doctype": "Item Price", "item_code": "_Test Item", "price_list": pl,
			"price_list_rate": 250, "selling": 1,
		}).insert(ignore_permissions=True)
		frappe.get_doc({
			"doctype": "Item Price", "item_code": "_Test Item", "price_list": pl,
			"price_list_rate": 999, "selling": 1, "valid_from": "2020-01-01", "valid_upto": "2020-12-31",
		}).insert(ignore_permissions=True)
		res = search_items(company="_Test Company", txt="_Test Item")
		row = next(i for i in res["items"] if i["item_code"] == "_Test Item")
		self.assertEqual(row["sell_price"], 250)
		self.assertEqual(row["stock"][wh], flt(before + 10, 2))
		self.assertIn(wh, res["warehouses"])
		bins = frappe.get_all(
			"Bin", {"item_code": "_Test Item", "warehouse": ["in", list(row["stock"])]},
			["actual_qty", "stock_value"],
		)
		qty = sum(b.actual_qty for b in bins)
		self.assertEqual(row["total_qty"], flt(qty, 2))
		self.assertTrue(res["can_see_cost"])
		# cost is only meaningful for positive stock (the shared test DB can carry negative bins)
		self.assertEqual(row["cost"], flt(sum(b.stock_value for b in bins) / qty, 2) if qty > 0 else None)
		frappe.set_user(self._as_sales_only_user())
		try:
			res = search_items(company="_Test Company", txt="_Test Item")
			row = next(i for i in res["items"] if i["item_code"] == "_Test Item")
			self.assertFalse(res["can_see_cost"])
			self.assertNotIn("cost", row)
		finally:
			frappe.set_user("Administrator")

	def test_search_items_caps_and_flags_truncation(self):
		res = search_items(company="_Test Company", txt="_Test", limit="2")
		self.assertEqual(len(res["items"]), 2)
		self.assertTrue(res["truncated"])

	def test_stock_card_single_warehouse_balance_matches_ledger(self):
		from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
		from frappe.utils import add_days, today

		self._receipt(qty=50, rate=100, posting_date=add_days(today(), -10))
		create_sales_invoice(
			item_code="_Test Item", qty=3, rate=300, update_stock=1,
			warehouse="_Test Warehouse - _TC", company="_Test Company",
		)
		# dev data holds future-dated SLEs, so bound the card at today
		d = get_stock_card(
			item="_Test Item", company="_Test Company", warehouse="_Test Warehouse - _TC", to_date=today())
		self.assertTrue(d["single_warehouse"])
		last = d["rows"][-1]
		self.assertEqual(last["voucher_type"], "Sales Invoice")
		self.assertEqual(last["qty_out"], 3)
		self.assertEqual(last["qty_in"], 0)
		self.assertEqual(last["rate"], 300)
		self.assertEqual(last["party"], "_Test Customer")
		# not Bin.actual_qty: future-dated entries make the Bin differ from the balance as of today
		sle_qty = frappe.db.get_value(
			"Stock Ledger Entry", {"voucher_no": last["voucher_no"], "item_code": "_Test Item"},
			"qty_after_transaction")
		self.assertEqual(last["balance"], flt(sle_qty, 2))
		self.assertEqual(d["closing_qty"], flt(sle_qty, 2))
		self.assertIn("valuation_rate", last)
		self.assertIn("value", last)

	def _last_qty_by_warehouse(self, item, before=None, upto=None):
		"""Independent oracle: sum of each company warehouse's last qty_after_transaction."""
		whs = frappe.get_all(
			"Warehouse", {"company": "_Test Company", "is_group": 0, "disabled": 0}, pluck="name")
		total = 0
		for w in whs:
			cond, args = "", [item, "_Test Company", w]
			if before:
				cond, args = "and posting_date < %s", [*args, before]
			if upto:
				cond, args = "and posting_date <= %s", [*args, upto]
			row = frappe.db.sql(
				f"""select qty_after_transaction from `tabStock Ledger Entry`
				where item_code=%s and company=%s and warehouse=%s and is_cancelled=0 {cond}
				order by posting_datetime desc, creation desc limit 1""",
				args,
			)
			total += flt(row[0][0]) if row else 0
		return flt(total, 2)

	def test_stock_card_multi_warehouse_running_balance_and_opening(self):
		from frappe.utils import add_days, today

		self._receipt(qty=10, warehouse="_Test Warehouse - _TC", posting_date=add_days(today(), -20))
		self._receipt(qty=5, warehouse="_Test Warehouse 1 - _TC", posting_date=add_days(today(), -2))
		start = add_days(today(), -5)
		# dev data holds future-dated SLEs, so bound the card at today
		d = get_stock_card(item="_Test Item", company="_Test Company", from_date=start, to_date=today())
		self.assertFalse(d["single_warehouse"])
		self.assertEqual(d["opening_qty"], self._last_qty_by_warehouse("_Test Item", before=start))
		self.assertEqual(d["rows"][-1]["balance"], self._last_qty_by_warehouse("_Test Item", upto=today()))
		self.assertEqual(d["closing_qty"], d["rows"][-1]["balance"])
		# other tests in this class leave same-window receipts, so qty_in is a lower bound
		self.assertGreaterEqual(d["totals"]["qty_in"], 5)

	def test_stock_card_counts_stock_reconciliation(self):
		from erpnext.stock.doctype.stock_reconciliation.test_stock_reconciliation import (
			create_stock_reconciliation,
		)
		from frappe.utils import add_days, today

		wh = "_Test Warehouse 2 - _TC"
		self._receipt(qty=10, warehouse=wh, posting_date=add_days(today(), -3))
		before = frappe.db.sql(
			"""select qty_after_transaction from `tabStock Ledger Entry`
			where item_code='_Test Item' and warehouse=%s and is_cancelled=0
			order by posting_datetime desc, creation desc limit 1""",
			wh,
		)[0][0]
		sr = create_stock_reconciliation(
			item_code="_Test Item", warehouse=wh, qty=25, rate=100,
			company="_Test Company", posting_date=add_days(today(), -1),
		)
		start = add_days(today(), -2)
		d = get_stock_card(item="_Test Item", company="_Test Company", from_date=start, to_date=today())
		row = next(r for r in d["rows"] if r["voucher_no"] == sr.name)
		self.assertEqual(row["qty_in"], flt(25 - flt(before), 2))
		self.assertEqual(row["rate"], 100)
		self.assertEqual(d["opening_qty"], self._last_qty_by_warehouse("_Test Item", before=start))
		self.assertEqual(d["closing_qty"], self._last_qty_by_warehouse("_Test Item", upto=today()))

	def test_stock_card_excludes_cancelled_entries(self):
		se = self._receipt(qty=7)
		se.cancel()
		d = get_stock_card(item="_Test Item", company="_Test Company", warehouse="_Test Warehouse - _TC")
		self.assertNotIn(se.name, [r["voucher_no"] for r in d["rows"]])

	def test_stock_card_hides_cost_and_stock_entry_rate_for_cost_blind_user(self):
		se = self._receipt(qty=4, rate=50)
		frappe.set_user(self._as_sales_only_user())
		try:
			d = get_stock_card(item="_Test Item", company="_Test Company", warehouse="_Test Warehouse - _TC")
			self.assertFalse(d["can_see_cost"])
			self.assertNotIn("opening_value", d)
			se_row = next(r for r in d["rows"] if r["voucher_no"] == se.name)
			self.assertIsNone(se_row["rate"])
			self.assertEqual(se_row["qty_in"], 4)
			for r in d["rows"]:
				for k in ("valuation_rate", "stock_value_difference", "value"):
					self.assertNotIn(k, r)
		finally:
			frappe.set_user("Administrator")
		d = get_stock_card(item="_Test Item", company="_Test Company", warehouse="_Test Warehouse - _TC")
		se_row = next(r for r in d["rows"] if r["voucher_no"] == se.name)
		self.assertEqual(se_row["rate"], 50)

	def test_stock_card_respects_warehouse_user_permission(self):
		self._receipt(qty=10, warehouse="_Test Warehouse - _TC")
		self._receipt(qty=5, warehouse="_Test Warehouse 1 - _TC")
		frappe.set_user(self._as_warehouse_restricted_user())
		try:
			d = get_stock_card(item="_Test Item", company="_Test Company")
			self.assertEqual({r["warehouse"] for r in d["rows"]}, {"_Test Warehouse - _TC"})
			self.assertTrue(d["single_warehouse"])
			d2 = get_stock_card(
				item="_Test Item", company="_Test Company", warehouse="_Test Warehouse 1 - _TC")
			self.assertEqual(d2["rows"], [])
		finally:
			frappe.set_user("Administrator")

	# ── export_table ─────────────────────────────────────────────────────────

	def test_export_table_round_trip(self):
		rows = [["Item", "Qty", "Note"], ["F071", 12.5, "=SUM(A1)"], ["F050", -3, ""]]
		frappe.response.pop("filecontent", None)
		export_table("Purchases — F071", json.dumps(rows))

		self.assertEqual(frappe.response["type"], "binary")
		self.assertTrue(frappe.response["filename"].endswith(".xlsx"))
		self.assertIn("purchases", frappe.response["filename"])
		got = read_xlsx_file_from_attached_file(fcontent=frappe.response["filecontent"])
		self.assertEqual(got[0], ["Item", "Qty", "Note"])
		self.assertEqual(got[1][:2], ["F071", 12.5])
		self.assertEqual(got[1][2], "=SUM(A1)")  # written as text, not evaluated
		self.assertEqual(got[2][1], -3)

	def test_export_table_rejects_oversized_payload(self):
		rows = [["x"]] * 50_001
		self.assertRaises(frappe.ValidationError, export_table, "Big", json.dumps(rows))
