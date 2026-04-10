# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import unittest


class TestCalculateAgingBucket(unittest.TestCase):
	"""Tests for _calculate_aging_bucket — no DB required."""

	def _bucket(self, due_str, as_of_str):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			_calculate_aging_bucket,
		)
		from frappe.utils import getdate

		return _calculate_aging_bucket(getdate(due_str), getdate(as_of_str))

	def test_not_yet_due_is_current(self):
		self.assertEqual(self._bucket("2026-02-15", "2026-01-31"), "bucket_0_30")

	def test_due_today_is_current(self):
		self.assertEqual(self._bucket("2026-01-31", "2026-01-31"), "bucket_0_30")

	def test_30_days_overdue_is_current(self):
		# 30 days past due → still in 0-30 bucket
		self.assertEqual(self._bucket("2026-01-01", "2026-01-31"), "bucket_0_30")

	def test_31_days_overdue(self):
		self.assertEqual(self._bucket("2025-12-31", "2026-01-31"), "bucket_31_60")

	def test_60_days_overdue(self):
		self.assertEqual(self._bucket("2025-12-02", "2026-01-31"), "bucket_31_60")

	def test_61_days_overdue(self):
		self.assertEqual(self._bucket("2025-12-01", "2026-01-31"), "bucket_61_90")

	def test_90_days_overdue(self):
		self.assertEqual(self._bucket("2025-11-02", "2026-01-31"), "bucket_61_90")

	def test_91_days_overdue(self):
		self.assertEqual(self._bucket("2025-11-01", "2026-01-31"), "bucket_90_plus")
