# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import unittest

import frappe


class TestItemHistory(unittest.TestCase):
	def test_columns_structure(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.report.item_history.item_history import (
			get_columns,
		)

		columns = get_columns()
		fieldnames = [c["fieldname"] for c in columns]
		self.assertIn("date", fieldnames)
		self.assertIn("voucher_type", fieldnames)
		self.assertIn("voucher_no", fieldnames)
		self.assertIn("party", fieldnames)
		self.assertIn("qty", fieldnames)
		self.assertIn("uom", fieldnames)
		self.assertIn("rate", fieldnames)
		self.assertIn("currency", fieldnames)
		self.assertIn("valuation_or_base_rate", fieldnames)
		self.assertEqual(len(columns), 9)

	def test_execute_returns_tuple(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.report.item_history.item_history import (
			execute,
		)

		filters = frappe._dict({"item": "__nonexistent__", "company": "_Test Company"})
		result = execute(filters)
		self.assertIsInstance(result, tuple)
		self.assertEqual(len(result), 5)
		columns, data, message, chart, summary = result
		self.assertIsInstance(columns, list)
		self.assertIsInstance(data, list)
		# No crash on nonexistent item — empty data
		self.assertEqual(len([r for r in data if not r.get("bold")]), 0)
		self.assertEqual(summary, [])
