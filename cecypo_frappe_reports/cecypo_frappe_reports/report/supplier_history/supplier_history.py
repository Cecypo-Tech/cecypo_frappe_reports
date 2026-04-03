# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from pypika import functions as fn


def execute(filters=None):
	if not filters:
		filters = frappe._dict({})

	if not filters.get("supplier"):
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
			"label": _("Receipts"),
			"fieldname": "receipt_count",
			"fieldtype": "Int",
			"width": 70,
		},
		{
			"label": _("Avg Valuation Rate"),
			"fieldname": "avg_valuation_rate",
			"fieldtype": "Float",
			"precision": 2,
			"width": 140,
		},
		{
			"label": _("Total Amount"),
			"fieldname": "total_amount",
			"fieldtype": "Float",
			"precision": 2,
			"width": 140,
		},
		{
			"label": _("Last Purchase"),
			"fieldname": "last_purchase",
			"fieldtype": "Date",
			"width": 100,
		},
	]


def get_data(filters):
	pri = frappe.qb.DocType("Purchase Receipt Item")
	pr = frappe.qb.DocType("Purchase Receipt")

	query = (
		frappe.qb.from_(pri)
		.inner_join(pr)
		.on(pri.parent == pr.name)
		.select(
			pri.item_code,
			pri.item_name,
			fn.Sum(pri.qty).as_("total_qty"),
			fn.Count(pr.name).distinct().as_("receipt_count"),
			fn.Avg(pri.valuation_rate).as_("avg_valuation_rate"),
			fn.Sum(pri.base_amount).as_("total_amount"),
			fn.Max(pr.posting_date).as_("last_purchase"),
		)
		.where(pr.docstatus == 1)
		.where(pr.supplier == filters.supplier)
		.where(pr.company == filters.company)
		.groupby(pri.item_code, pri.item_name)
		.orderby(fn.Sum(pri.base_amount), order=frappe.qb.desc)
	)

	if filters.get("from_date"):
		query = query.where(pr.posting_date >= filters.from_date)
	if filters.get("to_date"):
		query = query.where(pr.posting_date <= filters.to_date)

	rows = query.run(as_dict=True)
	for r in rows:
		r["total_qty"] = flt(r["total_qty"], 2)
		r["avg_valuation_rate"] = flt(r["avg_valuation_rate"], 2)
		r["total_amount"] = flt(r["total_amount"], 2)

	if rows:
		rows.append({
			"item_code": None,
			"item_name": _("Total"),
			"total_qty": flt(sum(r["total_qty"] for r in rows), 2),
			"receipt_count": sum(r["receipt_count"] for r in rows),
			"avg_valuation_rate": None,
			"total_amount": flt(sum(r["total_amount"] for r in rows), 2),
			"last_purchase": None,
			"bold": 1,
		})

	return rows


def get_report_summary(data):
	rows = [r for r in data if not r.get("bold")]
	if not rows:
		return []

	return [
		{"value": len(rows), "label": _("Total Items"), "datatype": "Int", "indicator": "Blue"},
		{
			"value": flt(sum(r["total_qty"] for r in rows), 2),
			"label": _("Total Qty Purchased"),
			"datatype": "Float",
			"indicator": "Blue",
		},
		{
			"value": flt(sum(r["total_amount"] for r in rows), 2),
			"label": _("Total Spend"),
			"datatype": "Float",
			"indicator": "Blue",
		},
	]
