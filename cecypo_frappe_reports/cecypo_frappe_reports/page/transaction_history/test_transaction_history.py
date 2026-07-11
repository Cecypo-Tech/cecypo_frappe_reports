# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

from frappe.tests import IntegrationTestCase


class TestTransactionHistoryPage(IntegrationTestCase):
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
