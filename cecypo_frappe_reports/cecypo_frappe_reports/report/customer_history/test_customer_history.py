# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
import unittest


class TestCustomerHistory(unittest.TestCase):
	def test_columns_structure(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.report.customer_history.customer_history import (
			get_columns,
		)

		columns = get_columns()
		fieldnames = [c["fieldname"] for c in columns]
		self.assertIn("item_code", fieldnames)
		self.assertIn("item_name", fieldnames)
		self.assertIn("total_qty", fieldnames)
		self.assertIn("invoice_count", fieldnames)
		self.assertIn("avg_rate", fieldnames)
		self.assertIn("total_amount", fieldnames)
		self.assertIn("last_sale", fieldnames)
		self.assertEqual(len(columns), 7)

	def test_execute_returns_tuple(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.report.customer_history.customer_history import (
			execute,
		)

		filters = frappe._dict({"customer": "__nonexistent__", "company": "_Test Company"})
		result = execute(filters)
		self.assertIsInstance(result, tuple)
		self.assertEqual(len(result), 5)
		columns, data, message, chart, summary = result
		self.assertIsInstance(data, list)
		self.assertEqual(len([r for r in data if not r.get("bold")]), 0)
