# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	if not filters:
		filters = frappe._dict({})

	columns = get_columns()
	data = get_data(filters)
	report_summary = get_report_summary(data)

	return columns, data, None, None, report_summary


def get_columns():
	return [
		{
			"label": _("Date"),
			"fieldname": "posting_date",
			"fieldtype": "Date",
			"width": 100,
		},
		{
			"label": _("Voucher"),
			"fieldname": "voucher_no",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 160,
		},
		{
			"label": _("Voucher Type"),
			"fieldname": "voucher_type",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"label": _("ETR Invoice No"),
			"fieldname": "etr_invoice_number",
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"label": _("Customer"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 120,
		},
		{
			"label": _("Tax ID"),
			"fieldname": "tax_id",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Account Manager"),
			"fieldname": "account_manager",
			"fieldtype": "Link",
			"options": "User",
			"width": 130,
		},
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
			"label": _("Cost"),
			"fieldname": "cost",
			"fieldtype": "Float",
			"precision": 2,
			"width": 100,
		},
		{
			"label": _("Total Cost"),
			"fieldname": "total_cost",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": _("Rate"),
			"fieldname": "rate",
			"fieldtype": "Float",
			"precision": 2,
			"width": 100,
		},
		{
			"label": _("Gross"),
			"fieldname": "gross",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": _("Margin"),
			"fieldname": "margin",
			"fieldtype": "Float",
			"precision": 2,
			"width": 100,
		},
		{
			"label": _("Total Margin"),
			"fieldname": "total_margin",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": _("% Margin"),
			"fieldname": "pct_margin",
			"fieldtype": "Float",
			"precision": 2,
			"width": 90,
		},
		{
			"label": _("Due Date"),
			"fieldname": "due_date",
			"fieldtype": "Date",
			"width": 100,
		},
	]


def get_data(filters):
	si = frappe.qb.DocType("Sales Invoice")
	sii = frappe.qb.DocType("Sales Invoice Item")
	cust = frappe.qb.DocType("Customer")

	query = (
		frappe.qb.from_(sii)
		.inner_join(si)
		.on(sii.parent == si.name)
		.left_join(cust)
		.on(si.customer == cust.name)
		.select(
			si.posting_date,
			si.name.as_("voucher_no"),
			si.is_return,
			si.etr_invoice_number,
			si.customer,
			si.tax_id,
			cust.account_manager,
			sii.item_code,
			sii.item_name,
			sii.qty,
			sii.incoming_rate,
			sii.base_net_rate,
			si.due_date,
		)
		.where(si.docstatus == 1)
		.orderby(si.posting_date)
		.orderby(si.name)
		.orderby(sii.idx)
	)

	if filters.get("company"):
		query = query.where(si.company == filters.company)

	if filters.get("from_date"):
		query = query.where(si.posting_date >= filters.from_date)

	if filters.get("to_date"):
		query = query.where(si.posting_date <= filters.to_date)

	if filters.get("customer"):
		query = query.where(si.customer == filters.customer)

	if filters.get("customer_group"):
		groups = frappe.db.get_descendants("Customer Group", filters.customer_group) or []
		groups.append(filters.customer_group)
		query = query.where(si.customer_group.isin(groups))

	if filters.get("item_code"):
		query = query.where(sii.item_code == filters.item_code)

	if filters.get("sales_person"):
		st = frappe.qb.DocType("Sales Team")
		sp_sub = (
			frappe.qb.from_(st)
			.select(st.parent)
			.where(st.parenttype == "Sales Invoice")
			.where(st.sales_person == filters.sales_person)
			.distinct()
		)
		query = query.where(si.name.isin(sp_sub))

	if filters.get("warehouse"):
		query = query.where(sii.warehouse == filters.warehouse)

	rows = query.run(as_dict=True)

	data = []
	for r in rows:
		is_return = bool(r.is_return)
		qty = flt(r.qty, 2)
		cost = flt(r.incoming_rate, 2)
		rate = flt(r.base_net_rate, 2)
		total_cost = flt(qty * cost, 2)
		gross = flt(qty * rate, 2)
		margin = flt(rate - cost, 2)
		total_margin = flt(gross - total_cost, 2)
		pct_margin = flt((total_margin / gross * 100) if gross else 0, 2)

		data.append({
			"posting_date": r.posting_date,
			"voucher_no": r.voucher_no,
			"voucher_type": "Sales Invoice-Return" if is_return else "Sales Invoice",
			"etr_invoice_number": r.etr_invoice_number,
			"customer": r.customer,
			"tax_id": r.tax_id,
			"account_manager": r.account_manager,
			"item_code": r.item_code,
			"item_name": r.item_name,
			"qty": qty,
			"cost": cost,
			"total_cost": total_cost,
			"rate": rate,
			"gross": gross,
			"margin": margin,
			"total_margin": total_margin,
			"pct_margin": pct_margin,
			"due_date": r.due_date,
			"is_return": 1 if is_return else 0,
		})

	return data


def get_report_summary(data):
	if not data:
		return []

	total_cost = flt(sum(flt(d.get("total_cost")) for d in data), 2)
	total_gross = flt(sum(flt(d.get("gross")) for d in data), 2)
	total_margin = flt(total_gross - total_cost, 2)
	overall_pct = flt((total_margin / total_gross * 100) if total_gross else 0, 2)

	return [
		{
			"value": total_cost,
			"label": _("Total Cost"),
			"datatype": "Float",
			"indicator": "Orange",
		},
		{
			"value": total_gross,
			"label": _("Total Gross"),
			"datatype": "Float",
			"indicator": "Blue",
		},
		{
			"value": total_margin,
			"label": _("Total Margin"),
			"datatype": "Float",
			"indicator": "Green" if total_margin >= 0 else "Red",
		},
		{
			"value": overall_pct,
			"label": _("Overall % Margin"),
			"datatype": "Float",
			"indicator": "Green" if overall_pct >= 0 else "Red",
		},
	]
