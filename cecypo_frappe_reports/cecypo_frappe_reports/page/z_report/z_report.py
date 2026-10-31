# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from cecypo_frappe_reports.cecypo_frappe_reports.z_report import _permitted_warehouses, get_z_report


@frappe.whitelist()
def get_z_report_html(warehouse: str, date: str) -> str:
	"""The A4 page body for one branch and day. get_z_report does the permission checks."""
	report = get_z_report(warehouse, date)
	currency = frappe.db.get_value("Company", report["company"], "default_currency")
	return frappe.render_template(
		"cecypo_frappe_reports/templates/z_report_a4.html", {"report": report, "currency": currency}
	)


@frappe.whitelist()
def get_default_warehouse() -> str | None:
	"""The user's only permitted Warehouse, else the warehouse of a till they work on (first
	POS Profile by name that lists them), else None."""
	allowed = _permitted_warehouses()
	if len(allowed) == 1:
		return next(iter(allowed))
	for w in frappe.db.sql_list(
		"""SELECT pp.warehouse FROM `tabPOS Profile` pp
		JOIN `tabPOS Profile User` u ON u.parent = pp.name AND u.parenttype = 'POS Profile'
		WHERE u.user = %s AND pp.disabled = 0 AND IFNULL(pp.warehouse, '') != ''
		ORDER BY pp.name""",
		frappe.session.user,
	):
		if not allowed or w in allowed:
			return w
	return None


@frappe.whitelist()
def get_branch_options() -> list[str]:
	"""Warehouses the user may report on. Read straight from the DB: Accounts roles lack Warehouse read."""
	if not frappe.has_permission("Sales Invoice", "report"):
		frappe.throw(_("Not permitted to view sales reports."), frappe.PermissionError)
	allowed = _permitted_warehouses()
	rows = frappe.get_all(
		"Warehouse", {"is_group": 0, "disabled": 0}, pluck="name", order_by="name", ignore_permissions=True
	)
	return [w for w in rows if not allowed or w in allowed]
