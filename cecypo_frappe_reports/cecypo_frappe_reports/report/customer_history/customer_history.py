# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from pypika import functions as fn


def execute(filters=None):
	if not filters:
		filters = frappe._dict({})

	if not filters.get("customer"):
		return get_columns(), [], None, None, []

	columns = get_columns()
	data = get_data(filters)
	report_summary = get_report_summary(data)

	return columns, data, None, None, report_summary


def get_columns():
	return [
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 130,
		},
		{
			"label": _("Item Name"),
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"label": _("Total Qty"),
			"fieldname": "total_qty",
			"fieldtype": "Float",
			"precision": 2,
			"width": 90,
		},
		{
			"label": _("Invoices"),
			"fieldname": "invoice_count",
			"fieldtype": "Int",
			"width": 70,
		},
		{
			"label": _("Avg Rate"),
			"fieldname": "avg_rate",
			"fieldtype": "Float",
			"precision": 2,
			"width": 120,
		},
		{
			"label": _("Total Amount"),
			"fieldname": "total_amount",
			"fieldtype": "Float",
			"precision": 2,
			"width": 140,
		},
		{
			"label": _("Last Sale"),
			"fieldname": "last_sale",
			"fieldtype": "Date",
			"width": 100,
		},
	]


def get_data(filters):
	sii = frappe.qb.DocType("Sales Invoice Item")
	si = frappe.qb.DocType("Sales Invoice")

	query = (
		frappe.qb.from_(sii)
		.inner_join(si)
		.on(sii.parent == si.name)
		.select(
			sii.item_code,
			sii.item_name,
			fn.Sum(sii.qty).as_("total_qty"),
			fn.Count(si.name).distinct().as_("invoice_count"),
			fn.Avg(sii.base_rate).as_("avg_rate"),
			fn.Sum(sii.base_amount).as_("total_amount"),
			fn.Max(si.posting_date).as_("last_sale"),
		)
		.where(si.docstatus == 1)
		.where(si.customer == filters.customer)
		.where(si.company == filters.company)
		.groupby(sii.item_code, sii.item_name)
		.orderby(fn.Sum(sii.base_amount), order=frappe.qb.desc)
	)

	if filters.get("from_date"):
		query = query.where(si.posting_date >= filters.from_date)
	if filters.get("to_date"):
		query = query.where(si.posting_date <= filters.to_date)

	rows = query.run(as_dict=True)
	for r in rows:
		r["total_qty"] = flt(r["total_qty"], 2)
		r["avg_rate"] = flt(r["avg_rate"], 2)
		r["total_amount"] = flt(r["total_amount"], 2)

	if rows:
		rows.append({
			"item_code": None,
			"item_name": _("Total"),
			"total_qty": flt(sum(r["total_qty"] for r in rows), 2),
			"invoice_count": sum(r["invoice_count"] for r in rows),
			"avg_rate": None,
			"total_amount": flt(sum(r["total_amount"] for r in rows), 2),
			"last_sale": None,
			"bold": 1,
		})

	return rows


def get_report_summary(data):
	rows = [r for r in data if not r.get("bold")]
	if not rows:
		return []

	return [
		{"value": len(rows), "label": _("Total Items"), "datatype": "Int", "indicator": "Blue"},
		{"value": flt(sum(r["total_qty"] for r in rows), 2), "label": _("Total Qty Sold"), "datatype": "Float", "indicator": "Blue"},
		{"value": flt(sum(r["total_amount"] for r in rows), 2), "label": _("Total Revenue"), "datatype": "Float", "indicator": "Green"},
	]
