# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import unittest


class TestItemGroupValuationPage(unittest.TestCase):
	def test_get_top_level_groups_returns_list(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.item_group_valuation import (
			get_top_level_groups,
		)

		rows = get_top_level_groups(root_group="__nonexistent__", company="_Test Company")
		self.assertIsInstance(rows, list)
		self.assertEqual(rows, [])

	def test_get_top_level_groups_known_root(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.item_group_valuation import (
			get_top_level_groups,
		)

		rows = get_top_level_groups(root_group="All Item Groups", company="_Test Company")
		self.assertIsInstance(rows, list)
		for row in rows:
			self.assertIn("item_group", row)
			self.assertIn("qty", row)
			self.assertIn("valuation_rate", row)
			self.assertIn("value", row)
			self.assertIn("is_group", row)
			self.assertEqual(row["is_group"], 1)

	def test_get_group_children_nonexistent_returns_list(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.item_group_valuation import (
			get_group_children,
		)

		rows = get_group_children(item_group="__nonexistent__", company="_Test Company")
		self.assertIsInstance(rows, list)
		self.assertEqual(rows, [])

	def test_get_group_children_returns_correct_keys(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.item_group_valuation import (
			get_group_children,
		)

		rows = get_group_children(item_group="All Item Groups", company="_Test Company")
		self.assertIsInstance(rows, list)
		for row in rows:
			self.assertIn("qty", row)
			self.assertIn("valuation_rate", row)
			self.assertIn("value", row)
			self.assertIn("is_group", row)
