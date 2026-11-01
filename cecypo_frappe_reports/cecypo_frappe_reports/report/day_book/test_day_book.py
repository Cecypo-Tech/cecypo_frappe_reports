import datetime

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from cecypo_frappe_reports.cecypo_frappe_reports.report.day_book.day_book import (
	execute,
	summarize,
	transaction_of,
	warehouse_of,
)

D = datetime.date(2026, 11, 1)


def _v(transaction, value, money_in=0.0, money_out=0.0, date=D, warehouse=None):
	return {
		"date": date,
		"warehouse": warehouse,
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

	def test_groups_by_warehouse_blank_last(self):
		rows = summarize(
			[
				_v("Received", 400.0, money_in=400.0),
				_v("Sales", 100.0, warehouse="Stores - DC"),
				_v("Sales", 50.0, warehouse="Annex - DC"),
				_v("Sales", 25.0, warehouse="Stores - DC"),
			]
		)[:-1]
		self.assertEqual(
			[(r["warehouse"], r["transaction"], r["count"], r["value"]) for r in rows],
			[
				("Annex - DC", "Sales", 1, 50.0),
				("Stores - DC", "Sales", 2, 125.0),
				(None, "Received", 1, 400.0),
			],
		)


class TestWarehouseOf(FrappeTestCase):
	def test_stock_warehouse_wins_then_till_then_blank(self):
		self.assertEqual(warehouse_of({"Stores - DC"}, "Annex - DC"), "Stores - DC")
		self.assertEqual(warehouse_of({"Stores - DC", "Annex - DC"}, None), "Multiple")
		self.assertEqual(warehouse_of(set(), "Annex - DC"), "Annex - DC")
		self.assertIsNone(warehouse_of(set(), None))


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
			["date", "warehouse", "transaction", "count", "value", "money_in", "money_out"],
		)
		names = frappe.db.sql_list(
			"""SELECT DISTINCT voucher_no FROM `tabGL Entry` WHERE voucher_type = 'Sales Invoice'
			AND company = %s AND posting_date = %s AND is_cancelled = 0""",
			(company, date),
		)
		sales = [n for n in names if not frappe.db.get_value("Sales Invoice", n, "is_return")]
		if not sales:
			self.skipTest("only returns that day")
		rows = [r for r in data if r.get("transaction") == "Sales"]
		self.assertEqual(sum(r["count"] for r in rows), len(sales))
		expected = sum(flt(frappe.db.get_value("Sales Invoice", n, "base_grand_total")) for n in sales)
		self.assertAlmostEqual(sum(r["value"] for r in rows), expected, 2)
		# each sale sits under the warehouse its stock left from
		sle_wh = frappe.db.get_value(
			"Stock Ledger Entry", {"voucher_no": sales[0], "is_cancelled": 0}, "warehouse"
		)
		if sle_wh:
			self.assertIn(sle_wh, {r["warehouse"] for r in rows})
		money_in = frappe.db.sql(
			"""SELECT COALESCE(SUM(gle.debit), 0) FROM `tabGL Entry` gle
			JOIN `tabAccount` a ON a.name = gle.account
			WHERE gle.voucher_type = 'Sales Invoice' AND gle.voucher_no IN %s AND gle.is_cancelled = 0
			AND a.account_type IN ('Cash', 'Bank')""",
			(tuple(sales),),
		)[0][0]
		self.assertAlmostEqual(sum(r["money_in"] for r in rows), flt(money_in), 2)
		labels = [s["label"] for s in summary]
		self.assertEqual(labels, ["Sales", "Returns", "Money In", "Money Out", "Net Cash"])


class TestDayBookTillWarehouse(FrappeTestCase):
	def test_klik_payment_lands_under_its_till_warehouse(self):
		if not frappe.db.has_column("Payment Entry", "custom_pos_opening_entry"):
			self.skipTest("klik_pos not installed")
		pe = frappe.db.sql(
			"""SELECT pe.company, pe.posting_date, pp.warehouse FROM `tabPayment Entry` pe
			JOIN `tabPOS Opening Entry` poe ON poe.name = pe.custom_pos_opening_entry
			JOIN `tabPOS Profile` pp ON pp.name = poe.pos_profile
			WHERE pe.docstatus = 1 AND pe.payment_type = 'Receive' AND IFNULL(pp.warehouse, '') != ''
			LIMIT 1""",
			as_dict=True,
		)
		if not pe:
			self.skipTest("no klik shift payments on this site")
		pe = pe[0]
		filters = frappe._dict(
			company=pe.company, from_date=pe.posting_date, to_date=pe.posting_date, summarized=1
		)
		data = execute(filters)[1]
		self.assertIn((pe.warehouse, "Received"), {(r.get("warehouse"), r["transaction"]) for r in data})
