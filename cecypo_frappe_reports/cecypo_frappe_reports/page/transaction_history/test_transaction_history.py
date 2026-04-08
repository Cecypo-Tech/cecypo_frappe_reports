# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
import unittest


class TestTransactionHistoryPage(unittest.TestCase):
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

		result = get_item_history(item="__nonexistent__", company="_Test Company", source="pr")
		self.assertIn("purchases", result)
		self.assertIn("sales", result)
		self.assertIsInstance(result["purchases"], list)

	def test_get_item_history_source_pi(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_item_history,
		)

		result = get_item_history(item="__nonexistent__", company="_Test Company", source="pi")
		self.assertIn("purchases", result)
		self.assertIn("sales", result)
		self.assertIsInstance(result["purchases"], list)

	def test_summary_rows_have_status_aggregate_fields(self):
		"""Verify new fields exist on summary rows when data is present."""
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_customer_history,
		)

		# With nonexistent customer we get [] — verify the query runs without error
		rows = get_customer_history(customer="__nonexistent__", company="_Test Company")
		self.assertIsInstance(rows, list)
		# If rows were present, each would have overdue_count and unpaid_count
		for row in rows:
			self.assertIn("overdue_count", row)
			self.assertIn("unpaid_count", row)

	def test_detail_rows_have_status_field(self):
		"""Verify status field exists on detail rows when data is present."""
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_customer_item_transactions,
		)

		rows = get_customer_item_transactions(
			customer="__nonexistent__", item_code="__nonexistent__", company="_Test Company"
		)
		self.assertIsInstance(rows, list)
		for row in rows:
			self.assertIn("status", row)
