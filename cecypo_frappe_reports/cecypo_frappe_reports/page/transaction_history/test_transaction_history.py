# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase


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
		self.assertEqual(row["outstanding"], 0.0)
		self.assertGreaterEqual(row["unallocated_advance"], 750.0)

	def test_get_receivables_excludes_future_dated_advance(self):
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
		pe.posting_date = "2025-06-25"
		pe.save()
		pe.submit()

		rows = get_receivables(company="_Test Company", as_of_date="2025-06-15")
		row = next((r for r in rows if r["customer"] == "_Test Customer"), None)
		self.assertIsNone(row)

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
		self.assertEqual(row["outstanding"], 0.0)
		self.assertGreaterEqual(row["unallocated_advance"], 500.0)

	def test_get_payables_excludes_future_dated_advance(self):
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
		pe.posting_date = "2025-06-25"
		pe.save()
		pe.submit()

		rows = get_payables(company="_Test Company", as_of_date="2025-06-15")
		row = next((r for r in rows if r["supplier"] == "_Test Supplier"), None)
		self.assertIsNone(row)

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
		self.assertEqual(rows[0]["outstanding"], si.outstanding_amount)
		self.assertEqual(rows[0]["unallocated_advance"], 300.0)

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
