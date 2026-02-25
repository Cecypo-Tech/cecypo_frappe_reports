# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from pypika import CustomFunction, functions as fn

CastDate = CustomFunction("DATE", ["value"])

VOUCHER_CATEGORIES = {
	"Sales": ["Sales Invoice", "Delivery Note"],
	"Purchase": ["Purchase Invoice", "Purchase Receipt", "Subcontracting Receipt"],
	"Payments & Journals": ["Payment Entry", "Journal Entry"],
	"Stock": ["Stock Entry", "Stock Reconciliation", "Landed Cost Voucher"],
	"Assets": ["Asset", "Asset Capitalization", "Asset Repair"],
	"Other": ["Expense Claim", "Period Closing Voucher"],
}


def execute(filters=None):
	if not filters:
		filters = frappe._dict({})

	validate_filters(filters)
	is_summarized = filters.get("summarized")
	use_creation = filters.get("date_based_on") == "Creation Date"
	date_label = _("Creation Date") if use_creation else _("Posting Date")
	columns = get_columns(is_summarized, date_label)
	data = get_summarized_data(filters) if is_summarized else get_data(filters)
	report_summary = get_report_summary(data, is_summarized)

	return columns, data, None, None, report_summary


def validate_filters(filters):
	if filters.get("from_date") and filters.get("to_date"):
		if filters.from_date > filters.to_date:
			frappe.throw(_("From Date cannot be after To Date"))


def get_columns(is_summarized=False, date_label=None):
	if not date_label:
		date_label = _("Posting Date")

	if is_summarized:
		return [
			{
				"label": date_label,
				"fieldname": "date",
				"fieldtype": "Date",
				"width": 100,
			},
			{
				"label": _("Voucher Type"),
				"fieldname": "voucher_type",
				"fieldtype": "Data",
				"width": 160,
			},
			{
				"label": _("Count"),
				"fieldname": "count",
				"fieldtype": "Int",
				"width": 80,
			},
			{
				"label": _("Debit"),
				"fieldname": "debit",
				"fieldtype": "Float",
				"precision": 2,
				"width": 130,
			},
			{
				"label": _("Credit"),
				"fieldname": "credit",
				"fieldtype": "Float",
				"precision": 2,
				"width": 130,
			},
		]

	return [
		{
			"label": date_label,
			"fieldname": "date",
			"fieldtype": "Date",
			"width": 100,
		},
		{
			"label": _("Voucher Type"),
			"fieldname": "voucher_type",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Voucher No"),
			"fieldname": "voucher_no",
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 180,
		},
		{
			"label": _("Party Type"),
			"fieldname": "party_type",
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"label": _("Party"),
			"fieldname": "party",
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 150,
		},
		{
			"label": _("Account"),
			"fieldname": "account",
			"fieldtype": "Link",
			"options": "Account",
			"width": 200,
		},
		{
			"label": _("Debit"),
			"fieldname": "debit",
			"fieldtype": "Float",
			"precision": 2,
			"width": 120,
		},
		{
			"label": _("Credit"),
			"fieldname": "credit",
			"fieldtype": "Float",
			"precision": 2,
			"width": 120,
		},
		{
			"label": _("Against"),
			"fieldname": "against",
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"label": _("Remarks"),
			"fieldname": "remarks",
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"label": _("Cost Center"),
			"fieldname": "cost_center",
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 150,
		},
	]


def _get_date_field(gle, filters):
	if filters.get("date_based_on") == "Creation Date":
		return CastDate(gle.creation)
	return gle.posting_date


def _apply_common_filters(query, gle, filters):
	date_field = _get_date_field(gle, filters)

	if filters.get("company"):
		query = query.where(gle.company == filters.company)

	if filters.get("from_date"):
		query = query.where(date_field >= filters.from_date)

	if filters.get("to_date"):
		query = query.where(date_field <= filters.to_date)

	if filters.get("voucher_category"):
		voucher_types = VOUCHER_CATEGORIES.get(filters.voucher_category, [])
		if voucher_types:
			query = query.where(gle.voucher_type.isin(voucher_types))

	if filters.get("party_type"):
		query = query.where(gle.party_type == filters.party_type)

	if filters.get("party"):
		query = query.where(gle.party == filters.party)

	if filters.get("account"):
		query = query.where(gle.account == filters.account)

	if filters.get("cost_center"):
		query = query.where(gle.cost_center == filters.cost_center)

	if filters.get("warehouse"):
		sle = frappe.qb.DocType("Stock Ledger Entry")
		warehouse_vouchers = (
			frappe.qb.from_(sle)
			.select(sle.voucher_no)
			.where(sle.warehouse == filters.warehouse)
			.where(sle.is_cancelled == 0)
			.distinct()
		)
		query = query.where(gle.voucher_no.isin(warehouse_vouchers))

	return query


def get_data(filters):
	gle = frappe.qb.DocType("GL Entry")
	date_field = _get_date_field(gle, filters)

	query = (
		frappe.qb.from_(gle)
		.select(
			date_field.as_("date"),
			gle.voucher_type,
			gle.voucher_no,
			gle.party_type,
			gle.party,
			gle.account,
			gle.debit,
			gle.credit,
			gle.against,
			gle.remarks,
			gle.cost_center,
		)
		.where(gle.is_cancelled == 0)
		.orderby(date_field)
		.orderby(gle.voucher_type)
		.orderby(gle.voucher_no)
	)

	query = _apply_common_filters(query, gle, filters)
	data = query.run(as_dict=True)

	for row in data:
		row["debit"] = flt(row["debit"], 2)
		row["credit"] = flt(row["credit"], 2)

	return data


def get_summarized_data(filters):
	gle = frappe.qb.DocType("GL Entry")
	date_field = _get_date_field(gle, filters)

	query = (
		frappe.qb.from_(gle)
		.select(
			date_field.as_("date"),
			gle.voucher_type,
			fn.Count(gle.name).as_("count"),
			fn.Sum(gle.debit).as_("debit"),
			fn.Sum(gle.credit).as_("credit"),
		)
		.where(gle.is_cancelled == 0)
		.groupby(date_field, gle.voucher_type)
		.orderby(date_field)
		.orderby(gle.voucher_type)
	)

	query = _apply_common_filters(query, gle, filters)
	data = query.run(as_dict=True)

	for row in data:
		row["debit"] = flt(row["debit"], 2)
		row["credit"] = flt(row["credit"], 2)

	return data


def get_report_summary(data, is_summarized=False):
	if not data:
		return []

	total_debit = sum(flt(d.get("debit")) for d in data)
	total_credit = sum(flt(d.get("credit")) for d in data)
	net_balance = flt(total_debit - total_credit, 2)

	if is_summarized:
		total_count = sum(d.get("count", 0) for d in data)
	else:
		total_count = len(data)

	return [
		{
			"value": total_debit,
			"label": _("Total Debit"),
			"datatype": "Float",
			"indicator": "Blue",
		},
		{
			"value": total_credit,
			"label": _("Total Credit"),
			"datatype": "Float",
			"indicator": "Blue",
		},
		{
			"value": net_balance,
			"label": _("Net Balance"),
			"datatype": "Float",
			"indicator": "Green" if net_balance == 0 else "Red",
		},
		{
			"value": total_count,
			"label": _("Transaction Count"),
			"datatype": "Int",
			"indicator": "Blue",
		},
	]
