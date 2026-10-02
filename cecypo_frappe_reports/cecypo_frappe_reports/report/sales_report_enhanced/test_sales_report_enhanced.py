# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import unittest

import frappe

from cecypo_frappe_reports.cecypo_frappe_reports.report.sales_report_enhanced.sales_report_enhanced import (
	NO_MODE,
	add_payment_entries,
	get_data,
	get_direct_payments,
)


def _row(parent, mode, amount, account="Cash - X", type_="Cash"):
	return frappe._dict(parent=parent, mode_of_payment=mode, account=account, type=type_, base_amount=amount)


def _inv(name, change=0, change_account="Cash - X", **kw):
	return frappe._dict(name=name, base_change_amount=change, account_for_change_amount=change_account, **kw)


class TestDirectPayments(unittest.TestCase):
	def test_change_is_netted_off_the_tendered_amount(self):
		# CS-00073 on prod: 350 bill, 1,000 tendered, 650 change
		payment_map, modes = get_direct_payments([_row("CS-1", "Cash", 1000)], [_inv("CS-1", change=650)])
		self.assertEqual(payment_map, {"CS-1": {"Cash": 350}})
		self.assertEqual(modes, {"Cash"})

	def test_change_comes_off_the_row_on_the_change_account(self):
		rows = [
			_row("CS-1", "Mpesa", 600, account="Mpesa - X", type_="Phone"),
			_row("CS-1", "Cash", 500, account="Cash - X"),
		]
		payment_map, _ = get_direct_payments(rows, [_inv("CS-1", change=100, change_account="Cash - X")])
		self.assertEqual(payment_map["CS-1"], {"Mpesa": 600, "Cash": 400})

	def test_change_falls_back_to_cash_type_row(self):
		rows = [
			_row("CS-1", "Mpesa", 600, account="Mpesa - X", type_="Phone"),
			_row("CS-1", "Till", 500, account="Till - X", type_="Cash"),
		]
		payment_map, _ = get_direct_payments(rows, [_inv("CS-1", change=100, change_account="Other - X")])
		self.assertEqual(payment_map["CS-1"], {"Mpesa": 600, "Till": 400})

	def test_change_falls_back_to_largest_row(self):
		rows = [
			_row("CS-1", "Mpesa", 600, account="Mpesa - X", type_="Phone"),
			_row("CS-1", "Card", 500, account="Card - X", type_="Bank"),
		]
		payment_map, _ = get_direct_payments(rows, [_inv("CS-1", change=100, change_account="Other - X")])
		self.assertEqual(payment_map["CS-1"], {"Mpesa": 500, "Card": 500})

	def test_rows_without_mode_are_skipped(self):
		payment_map, modes = get_direct_payments([_row("CS-1", None, 100)], [_inv("CS-1")])
		self.assertEqual(payment_map, {})
		self.assertEqual(modes, set())


class TestPaymentEntries(unittest.TestCase):
	def test_refund_paid_out_against_a_return_is_a_negative_payment(self):
		# X-POS-00021 on dev: -430 return refunded by a "Pay" Payment Entry
		payment_map, modes = {}, set()
		add_payment_entries(
			payment_map, modes, [frappe._dict(parent="X-1", mode_of_payment="Cash", base_amount=-430)]
		)
		self.assertEqual(payment_map, {"X-1": {"Cash": -430}})

	def test_entry_without_mode_lands_in_no_mode_column(self):
		payment_map, modes = {"SI-1": {"Cash": 50}}, {"Cash"}
		add_payment_entries(
			payment_map, modes, [frappe._dict(parent="SI-1", mode_of_payment=None, base_amount=136)]
		)
		self.assertEqual(payment_map, {"SI-1": {"Cash": 50, NO_MODE: 136}})
		self.assertEqual(modes, {"Cash", NO_MODE})

	def test_entries_add_to_pos_payments_of_the_same_mode(self):
		payment_map, modes = {"SI-1": {"Cash": 50}}, {"Cash"}
		add_payment_entries(
			payment_map, modes, [frappe._dict(parent="SI-1", mode_of_payment="Cash", base_amount=25)]
		)
		self.assertEqual(payment_map, {"SI-1": {"Cash": 75}})


def _invoice(grand, rounded, outstanding, **kw):
	return frappe._dict(
		name="CS-1",
		posting_date="2026-10-01",
		customer="C",
		customer_name="C",
		base_grand_total=grand,
		base_rounded_total=rounded,
		outstanding_amount=outstanding,
		**{"is_return": 0, **kw},
	)


class TestOutstanding(unittest.TestCase):
	def test_pos_return_applied_to_the_original_has_no_outstanding_of_its_own(self):
		# klik_pos sets update_outstanding_for_self=0 on POS returns; ERPNext still stamps
		# the return's own outstanding (-350) while the ledger reduces the original instead.
		inv = _invoice(-350, -350, -350, is_return=1, return_against="INV-1", update_outstanding_for_self=0)
		self.assertEqual(get_data([inv], {}, [])[0]["outstanding_amount"], 0)

	def test_return_carrying_its_own_credit_keeps_its_outstanding(self):
		inv = _invoice(-350, -350, -350, is_return=1, return_against="INV-1", update_outstanding_for_self=1)
		self.assertEqual(get_data([inv], {}, [])[0]["outstanding_amount"], -350)


class TestGrandTotal(unittest.TestCase):
	def _invoice(self, grand, rounded, outstanding):
		return _invoice(grand, rounded, outstanding)

	def test_grand_total_is_rounded_total(self):
		# CS-00162 on prod: grand 37,016.50, rounded/outstanding 37,016
		data = get_data([self._invoice(37016.5, 37016, 37016)], {}, [])
		self.assertEqual(data[0]["grand_total"], 37016)

	def test_grand_total_falls_back_when_rounding_disabled(self):
		data = get_data([self._invoice(37016.5, 0, 37016.5)], {}, [])
		self.assertEqual(data[0]["grand_total"], 37016.5)
