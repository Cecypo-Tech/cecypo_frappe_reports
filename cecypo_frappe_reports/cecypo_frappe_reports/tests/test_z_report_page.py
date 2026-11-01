"""The Z Report desk page: one branch, one day, on A4. The figures come from klik_pos.z_report."""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

try:
	from klik_pos.tests.test_z_report import _assert_in_order, _report

	_klik = True
except ImportError:
	_klik = False


@unittest.skipUnless(_klik, "klik_pos is not installed")
class TestZReportPage(FrappeTestCase):
	def test_html_shows_the_figures(self):
		from unittest import mock

		from cecypo_frappe_reports.cecypo_frappe_reports.page.z_report.z_report import get_z_report_html

		def html(report):
			with mock.patch(
				"cecypo_frappe_reports.cecypo_frappe_reports.page.z_report.z_report.get_z_report",
				return_value=report,
			):
				return get_z_report_html("Main Branch", "2026-10-31")

		out = html(_report())
		self.assertIn("Main Branch", out)
		self.assertIn("Z REPORT", out)
		self.assertIn("900.00", out)
		self.assertNotIn("Outstanding invoices", out)
		self.assertNotIn("Not counted", out)
		self.assertNotIn("Counted", out)
		self.assertIn("awaiting approval", out)
		self.assertIn("<td>Amina</td>", out)  # who took the expense
		self.assertIn("Tax total", out)
		self.assertIn("Discounts (net of returns)", out)
		self.assertNotIn("On credit", out)
		_assert_in_order(out)

		out = html(
			_report(
				excluded_invoices=2,
				outstanding=[
					{
						"name": "SINV-7",
						"customer_name": "Zed",
						"grand_total": 50.0,
						"outstanding_amount": 20.0,
					}
				],
				cash_position=[dict(_report()["cash_position"][0], counted=970.0, difference=-10.0)],
			)
		)
		self.assertIn("Outstanding invoices", out)
		self.assertIn("SINV-7", out)
		self.assertIn("Not counted", out)
		self.assertIn("Counted", out)

	def test_user_strings_are_escaped(self):
		from unittest import mock

		from cecypo_frappe_reports.cecypo_frappe_reports.page.z_report.z_report import get_z_report_html

		evil = "<script>alert(1)</script>"
		base = _report()
		report = _report(
			company=evil,
			warehouse=evil,
			users=[dict(base["users"][0], full_name=evil, modes=[{"mode": evil, "amount": 1.0}])],
			taxes=[{"description": evil, "amount": 1.0}],
			expenses=[dict(base["expenses"][0], label=evil, note=evil)],
			cash_position=[dict(base["cash_position"][0], mode=evil)],
			outstanding=[
				{"name": evil, "customer_name": evil, "grand_total": 5.0, "outstanding_amount": 2.0}
			],
		)
		with mock.patch(
			"cecypo_frappe_reports.cecypo_frappe_reports.page.z_report.z_report.get_z_report",
			return_value=report,
		):
			out = get_z_report_html("Main Branch", "2026-10-31")
		self.assertNotIn("<script>", out)
		self.assertIn("&lt;script&gt;", out)
		self.assertIn('<td>Date</td><td class="r">2026-10-31</td>', out)

	def test_other_warehouse_is_refused(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.z_report.z_report import get_z_report_html

		a, b = frappe.get_all("Warehouse", {"is_group": 0}, pluck="name", limit=2)
		email = "z-report-perm@example.com"
		frappe.set_user("Administrator")
		self.addCleanup(self._drop_user, email)
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "ZPerm", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
		user.add_roles("Accounts User")
		frappe.get_doc(
			{"doctype": "User Permission", "user": email, "allow": "Warehouse", "for_value": a}
		).insert(ignore_permissions=True)
		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			get_z_report_html(b, nowdate())

	def _user(self, email, roles, warehouses=()):
		frappe.set_user("Administrator")
		self.addCleanup(self._drop_user, email)
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "ZPerm", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
		user.add_roles(*roles)
		for w in warehouses:
			frappe.get_doc(
				{"doctype": "User Permission", "user": email, "allow": "Warehouse", "for_value": w}
			).insert(ignore_permissions=True)
		frappe.set_user(email)

	def test_default_warehouse(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.z_report.z_report import (
			get_default_warehouse,
		)

		a, b = frappe.get_all("Warehouse", {"is_group": 0}, pluck="name", limit=2)
		self._user("z-report-none@example.com", ["Accounts User"])
		self.assertIsNone(get_default_warehouse())
		self._user("z-report-one@example.com", ["Accounts User"], [a])
		self.assertEqual(get_default_warehouse(), a)
		self._user("z-report-two@example.com", ["Accounts User"], [a, b])
		self.assertIsNone(get_default_warehouse())

	def test_default_warehouse_falls_back_to_users_till(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.z_report.z_report import (
			get_default_warehouse,
		)

		profile = frappe.get_all(
			"POS Profile", {"disabled": 0, "warehouse": ("is", "set")}, ["name", "warehouse"], limit=1
		)
		if not profile:
			raise unittest.SkipTest("no POS Profile with a warehouse")
		email = "z-report-till@example.com"
		self._user(email, ["Accounts User"])
		frappe.set_user("Administrator")
		row = frappe.get_doc(
			{
				"doctype": "POS Profile User",
				"parent": profile[0].name,
				"parenttype": "POS Profile",
				"parentfield": "applicable_for_users",
				"user": email,
				"idx": 999,
			}
		)
		row.db_insert()
		self.addCleanup(frappe.db.commit)
		self.addCleanup(frappe.db.delete, "POS Profile User", {"name": row.name})
		frappe.set_user(email)
		self.assertEqual(get_default_warehouse(), profile[0].warehouse)

	def test_accounts_manager_needs_no_warehouse_read(self):
		from klik_pos.z_report import get_z_report

		w = frappe.get_all("Warehouse", {"is_group": 0}, pluck="name", limit=1)[0]
		self._user("z-report-am@example.com", ["Accounts Manager"])
		self.assertFalse(frappe.has_permission("Warehouse", doc=w))
		self.assertEqual(get_z_report(w, nowdate())["warehouse"], w)

	def test_branch_options(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.z_report.z_report import get_branch_options

		a = frappe.get_all("Warehouse", {"is_group": 0, "disabled": 0}, pluck="name", limit=1)[0]
		self._user("z-report-opt-am@example.com", ["Accounts Manager"])
		self.assertFalse(frappe.has_permission("Warehouse", "read"))
		self.assertIn(a, get_branch_options())
		self._user("z-report-opt-a@example.com", ["Accounts User"], [a])
		self.assertEqual(get_branch_options(), [a])
		self._user("z-report-opt-none@example.com", ["Desk User"])
		with self.assertRaises(frappe.PermissionError):
			get_branch_options()

	@staticmethod
	def _drop_user(email):
		frappe.set_user("Administrator")
		for p in frappe.get_all("User Permission", {"user": email}, pluck="name"):
			frappe.delete_doc("User Permission", p, force=True, ignore_permissions=True)
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		frappe.db.commit()
