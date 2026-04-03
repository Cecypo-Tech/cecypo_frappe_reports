# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	if not filters:
		filters = frappe._dict({})

	if not filters.get("item"):
		return get_columns(), [], None, None, []

	columns = get_columns()
	purchases = get_purchase_rows(filters)
	sales = get_sales_rows(filters)
	data = build_data(purchases, sales)
	report_summary = get_report_summary(filters, purchases, sales)

	return columns, data, None, None, report_summary


def get_columns():
	return [
		{
			"label": _("Date"),
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
			"width": 160,
		},
		{
			"label": _("Party"),
			"fieldname": "party",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": _("Qty"),
			"fieldname": "qty",
			"fieldtype": "Float",
			"precision": 2,
			"width": 80,
		},
		{
			"label": _("UOM"),
			"fieldname": "uom",
			"fieldtype": "Data",
			"width": 70,
		},
		{
			"label": _("Rate"),
			"fieldname": "rate",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": _("Currency"),
			"fieldname": "currency",
			"fieldtype": "Data",
			"width": 70,
		},
		{
			"label": _("Valuation / Base Rate"),
			"fieldname": "valuation_or_base_rate",
			"fieldtype": "Float",
			"precision": 2,
			"width": 130,
		},
	]


def get_purchase_rows(filters):
	pri = frappe.qb.DocType("Purchase Receipt Item")
	pr = frappe.qb.DocType("Purchase Receipt")

	query = (
		frappe.qb.from_(pri)
		.inner_join(pr)
		.on(pri.parent == pr.name)
		.select(
			pr.posting_date.as_("date"),
			pri.parent.as_("voucher_no"),
			pr.supplier.as_("party"),
			pri.qty,
			pri.uom,
			pri.rate,
			pr.currency,
			pri.valuation_rate.as_("valuation_or_base_rate"),
		)
		.where(pr.docstatus == 1)
		.where(pri.item_code == filters.item)
		.where(pr.company == filters.company)
		.orderby(pr.posting_date, order=frappe.qb.desc)
	)

	if filters.get("from_date"):
		query = query.where(pr.posting_date >= filters.from_date)
	if filters.get("to_date"):
		query = query.where(pr.posting_date <= filters.to_date)
	if filters.get("warehouse"):
		query = query.where(pri.warehouse == filters.warehouse)

	rows = query.run(as_dict=True)
	for r in rows:
		r["voucher_type"] = "Purchase Receipt"
		r["qty"] = flt(r["qty"], 2)
		r["rate"] = flt(r["rate"], 2)
		r["valuation_or_base_rate"] = flt(r["valuation_or_base_rate"], 2)
	return rows


def get_sales_rows(filters):
	sii = frappe.qb.DocType("Sales Invoice Item")
	si = frappe.qb.DocType("Sales Invoice")

	query = (
		frappe.qb.from_(sii)
		.inner_join(si)
		.on(sii.parent == si.name)
		.select(
			si.posting_date.as_("date"),
			sii.parent.as_("voucher_no"),
			si.customer.as_("party"),
			sii.qty,
			sii.uom,
			sii.rate,
			si.currency,
			sii.base_rate.as_("valuation_or_base_rate"),
		)
		.where(si.docstatus == 1)
		.where(sii.item_code == filters.item)
		.where(si.company == filters.company)
		.orderby(si.posting_date, order=frappe.qb.desc)
	)

	if filters.get("from_date"):
		query = query.where(si.posting_date >= filters.from_date)
	if filters.get("to_date"):
		query = query.where(si.posting_date <= filters.to_date)
	if filters.get("warehouse"):
		query = query.where(sii.warehouse == filters.warehouse)

	rows = query.run(as_dict=True)
	for r in rows:
		r["voucher_type"] = "Sales Invoice"
		r["qty"] = flt(r["qty"], 2)
		r["rate"] = flt(r["rate"], 2)
		r["valuation_or_base_rate"] = flt(r["valuation_or_base_rate"], 2)
	return rows


def build_data(purchases, sales):
	data = []

	total_purchase_qty = flt(sum(r["qty"] for r in purchases), 2)
	data.append({
		"voucher_no": _("── Purchases ({0} transactions · {1} units) ──").format(
			len(purchases), total_purchase_qty
		),
		"bold": 1,
		"indicator": "green",
	})
	data.extend(purchases)

	total_sales_qty = flt(sum(r["qty"] for r in sales), 2)
	data.append({
		"voucher_no": _("── Sales ({0} transactions · {1} units) ──").format(
			len(sales), total_sales_qty
		),
		"bold": 1,
		"indicator": "blue",
	})
	data.extend(sales)

	return data


def get_report_summary(filters, purchases, sales):
	bin_rows = frappe.db.get_all(
		"Bin",
		filters={"item_code": filters.item},
		fields=["actual_qty", "valuation_rate"],
	)

	if not bin_rows and not purchases and not sales:
		return []

	total_qty = sum(flt(b.actual_qty) for b in bin_rows)
	if total_qty:
		avg_rate = sum(flt(b.actual_qty) * flt(b.valuation_rate) for b in bin_rows) / total_qty
	else:
		avg_rate = 0.0

	current_stock = flt(sum(flt(b.actual_qty) for b in bin_rows), 2)
	stock_value = flt(sum(flt(b.actual_qty) * flt(b.valuation_rate) for b in bin_rows), 2)
	total_purchased = flt(sum(r["qty"] for r in purchases), 2)
	total_sold = flt(sum(r["qty"] for r in sales), 2)

	return [
		{
			"value": current_stock,
			"label": _("Current Stock"),
			"datatype": "Float",
			"indicator": "Green" if current_stock > 0 else "Red",
		},
		{
			"value": flt(avg_rate, 2),
			"label": _("Avg. Stock Rate"),
			"datatype": "Float",
			"indicator": "Blue",
		},
		{
			"value": stock_value,
			"label": _("Stock Value"),
			"datatype": "Float",
			"indicator": "Blue",
		},
		{
			"value": total_purchased,
			"label": _("Total Purchased"),
			"datatype": "Float",
			"indicator": "Blue",
		},
		{
			"value": total_sold,
			"label": _("Total Sold"),
			"datatype": "Float",
			"indicator": "Blue",
		},
	]
