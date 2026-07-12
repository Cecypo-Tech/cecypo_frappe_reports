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
