import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from cecypo_frappe_reports.cecypo_frappe_reports.report.day_book.day_book import execute


class TestDayBook(FrappeTestCase):
	def test_summarized_runs_and_counts_vouchers(self):
		company = frappe.db.get_value("GL Entry", {"is_cancelled": 0}, "company")
		if not company:
			self.skipTest("no GL Entries on this site")
		date = (
			frappe.db.get_value("GL Entry", {"company": company, "is_cancelled": 0}, "posting_date")
			or nowdate()
		)
		filters = frappe._dict(
			company=company, from_date=date, to_date=date, date_based_on="Posting Date", summarized=1
		)
		data = execute(filters)[1]
		rows = [r for r in data if r.get("voucher_type")]
		self.assertTrue(rows)
		vt = rows[0]["voucher_type"]
		expected = frappe.db.sql(
			"""SELECT COUNT(DISTINCT voucher_no) FROM `tabGL Entry` WHERE company=%s AND posting_date=%s
			AND voucher_type=%s AND is_cancelled=0""",
			(company, date, vt),
		)[0][0]
		self.assertEqual(rows[0]["count"], expected)
