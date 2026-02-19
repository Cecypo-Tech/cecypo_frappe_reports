# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.report.accounts_receivable_summary.accounts_receivable_summary import (
	AccountsReceivableSummary,
)


def execute(filters=None):
	if not filters:
		filters = frappe._dict({})

	args = {
		"account_type": "Receivable",
		"naming_by": ["Selling Settings", "cust_master_name"],
	}

	base = AccountsReceivableSummary(filters)
	columns, data = base.run(args)

	if not data:
		return columns + get_extra_columns(), data

	customers = list(
		{row.get("party") for row in data if row.get("party") and row.get("party_type") == "Customer"}
	)

	customer_details = get_customer_details(customers, filters.get("company"))

	for row in data:
		if row.get("party_type") != "Customer":
			row["payment_terms"] = ""
			row["credit_limit"] = 0.0
			row["account_manager"] = ""
			continue

		details = customer_details.get(row.get("party"), frappe._dict())
		row["payment_terms"] = details.get("payment_terms") or ""
		row["credit_limit"] = flt(details.get("credit_limit"), 2)
		row["account_manager"] = details.get("account_manager") or ""

	return columns + get_extra_columns(), data


def get_customer_details(customers, company):
	if not customers:
		return {}

	cust = frappe.qb.DocType("Customer")
	rows = (
		frappe.qb.from_(cust)
		.select(cust.name, cust.payment_terms, cust.account_manager)
		.where(cust.name.isin(customers))
		.run(as_dict=True)
	)

	details = {r.name: frappe._dict(r) for r in rows}

	# credit_limit lives in the Customer Credit Limit child table, keyed by company
	if company and customers:
		ccl = frappe.qb.DocType("Customer Credit Limit")
		limits = (
			frappe.qb.from_(ccl)
			.select(ccl.parent, ccl.credit_limit)
			.where(ccl.parent.isin(customers))
			.where(ccl.company == company)
			.run(as_dict=True)
		)
		for lim in limits:
			if lim.parent in details:
				details[lim.parent]["credit_limit"] = flt(lim.credit_limit)

	return details


def get_extra_columns():
	return [
		{
			"label": _("Payment Terms"),
			"fieldname": "payment_terms",
			"fieldtype": "Link",
			"options": "Payment Terms Template",
			"width": 160,
		},
		{
			"label": _("Credit Limit"),
			"fieldname": "credit_limit",
			"fieldtype": "Currency",
			"width": 120,
		},
		{
			"label": _("Account Manager"),
			"fieldname": "account_manager",
			"fieldtype": "Link",
			"options": "User",
			"width": 160,
		},
	]
