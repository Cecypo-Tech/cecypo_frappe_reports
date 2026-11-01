import datetime

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from cecypo_frappe_reports.cecypo_frappe_reports.report.day_book.day_book import (
	execute,
	summarize,
	transaction_of,
)

D = datetime.date(2026, 11, 1)


def _v(transaction, value, money_in=0.0, money_out=0.0, date=D):
	return {
		"date": date,
		"transaction": transaction,
		"value": value,
		"money_in": money_in,
		"money_out": money_out,
	}


class TestTransactionOf(FrappeTestCase):
	def test_mapping(self):
		self.assertEqual(transaction_of("Sales Invoice", {"is_return": 0}), "Sales")
		self.assertEqual(transaction_of("Sales Invoice", {"is_return": 1}), "Sales Returns")
		self.assertEqual(transaction_of("Purchase Invoice", {"is_return": 0}), "Purchases")
		self.assertEqual(transaction_of("Purchase Invoice", {"is_return": 1}), "Purchase Returns")
		self.assertEqual(transaction_of("Delivery Note", {"is_return": 1}), "Delivery Note Returns")
		self.assertEqual(transaction_of("Payment Entry", {"payment_type": "Receive"}), "Received")
		self.assertEqual(transaction_of("Payment Entry", {"payment_type": "Pay"}), "Paid Out")
		self.assertEqual(
			transaction_of("Payment Entry", {"payment_type": "Internal Transfer"}), "Internal Transfer"
		)
		self.assertEqual(transaction_of("Journal Entry", {"voucher_type": "Cash Entry"}), "Cash Entry")
		self.assertEqual(transaction_of("Journal Entry", {}), "Journal Entry")
		self.assertEqual(transaction_of("Stock Entry", None), "Stock Entry")


class TestSummarize(FrappeTestCase):
	def test_groups_orders_and_totals(self):
		rows = summarize(
			[
				_v("Paid Out", 300.0, money_out=300.0),
				_v("Sales", 1000.0, money_in=1000.0),
				_v("Sales", 500.0),  # on credit: value, no money
				_v("Sales Returns", -200.0, money_out=200.0),
				_v("Received", 400.0, money_in=400.0),
			]
		)
		body, total = rows[:-1], rows[-1]
		self.assertEqual([r["transaction"] for r in body], ["Sales", "Sales Returns", "Received", "Paid Out"])
		sales = body[0]
		self.assertEqual((sales["count"], sales["value"], sales["money_in"]), (2, 1500.0, 1000.0))
		self.assertEqual(total["count"], 5)
		self.assertIsNone(total.get("value"))
		self.assertEqual((total["money_in"], total["money_out"]), (1400.0, 500.0))
		self.assertTrue(total["bold"])

	def test_empty(self):
		self.assertEqual(summarize([]), [])


class TestDayBookSummarized(FrappeTestCase):
	def test_sales_value_is_the_invoice_total_not_every_gl_line(self):
		si = frappe.db.sql(
			"""SELECT DISTINCT gle.company, gle.posting_date FROM `tabGL Entry` gle
			WHERE gle.voucher_type = 'Sales Invoice' AND gle.is_cancelled = 0 LIMIT 1""",
			as_dict=True,
		)
		if not si:
			self.skipTest("no Sales Invoice GL Entries on this site")
		company, date = si[0].company, si[0].posting_date
		filters = frappe._dict(company=company, from_date=date, to_date=date, summarized=1)
		columns, data, _m, _c, summary = execute(filters)
		self.assertEqual(
			[c["fieldname"] for c in columns],
			["date", "transaction", "count", "value", "money_in", "money_out"],
		)
		names = frappe.db.sql_list(
			"""SELECT DISTINCT voucher_no FROM `tabGL Entry` WHERE voucher_type = 'Sales Invoice'
			AND company = %s AND posting_date = %s AND is_cancelled = 0""",
			(company, date),
		)
		sales = [n for n in names if not frappe.db.get_value("Sales Invoice", n, "is_return")]
		row = next((r for r in data if r.get("transaction") == "Sales"), None)
		if not sales:
			self.skipTest("only returns that day")
		self.assertEqual(row["count"], len(sales))
		expected = sum(flt(frappe.db.get_value("Sales Invoice", n, "base_grand_total")) for n in sales)
		self.assertAlmostEqual(row["value"], expected, 2)
		money_in = frappe.db.sql(
			"""SELECT COALESCE(SUM(gle.debit), 0) FROM `tabGL Entry` gle
			JOIN `tabAccount` a ON a.name = gle.account
			WHERE gle.voucher_type = 'Sales Invoice' AND gle.voucher_no IN %s AND gle.is_cancelled = 0
			AND a.account_type IN ('Cash', 'Bank')""",
			(tuple(sales),),
		)[0][0]
		self.assertAlmostEqual(row["money_in"], flt(money_in), 2)
		labels = [s["label"] for s in summary]
		self.assertEqual(labels, ["Sales", "Returns", "Money In", "Money Out", "Net Cash"])
