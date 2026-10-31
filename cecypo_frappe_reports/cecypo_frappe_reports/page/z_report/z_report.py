# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe

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
	"""The user's only permitted Warehouse, else None."""
	allowed = _permitted_warehouses()
	return next(iter(allowed)) if len(allowed) == 1 else None
