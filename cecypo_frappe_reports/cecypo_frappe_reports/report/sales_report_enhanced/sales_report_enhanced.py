# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from pypika import functions as fn


def execute(filters=None):
	if not filters:
		filters = frappe._dict({})

	invoices = get_invoices(filters)
	if not invoices:
		return get_columns([]), [], None, None, None

	invoice_names = [inv.name for inv in invoices]
	payment_map, all_modes = get_payment_map(invoice_names)
	columns = get_columns(all_modes)
	data = get_data(invoices, payment_map, all_modes)
	report_summary = get_report_summary(data, all_modes)

	return columns, data, None, None, report_summary


def get_invoices(filters):
	si = frappe.qb.DocType("Sales Invoice")

	query = (
		frappe.qb.from_(si)
		.select(
			si.name,
			si.posting_date,
			si.customer,
			si.customer_name,
			si.base_grand_total,
			si.outstanding_amount,
			si.is_return,
		)
		.where(si.docstatus == 1)
		.orderby(si.posting_date)
		.orderby(si.name)
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
		# Tree-aware: include the selected group AND all descendants
		groups = frappe.db.get_descendants("Customer Group", filters.customer_group) or []
		groups.append(filters.customer_group)
		query = query.where(si.customer_group.isin(groups))

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
		sii = frappe.qb.DocType("Sales Invoice Item")
		warehouse_sub = (
			frappe.qb.from_(sii)
			.select(sii.parent)
			.where(sii.warehouse == filters.warehouse)
			.distinct()
		)
		query = query.where(si.name.isin(warehouse_sub))

	if filters.get("custom_sale_type") and "custom_sale_type" in [
		f.fieldname for f in frappe.get_meta("Sales Invoice").fields
	]:
		query = query.where(si.custom_sale_type == filters.custom_sale_type)

	if filters.get("mode_of_payment"):
		sip = frappe.qb.DocType("Sales Invoice Payment")
		per = frappe.qb.DocType("Payment Entry Reference")
		pe = frappe.qb.DocType("Payment Entry")

		# POS-style direct payments (Sales Invoice Payment child table)
		direct = (
			frappe.qb.from_(sip)
			.select(sip.parent)
			.where(sip.mode_of_payment == filters.mode_of_payment)
		)

		# Non-POS payments via Payment Entry → Payment Entry Reference
		via_pe = (
			frappe.qb.from_(per)
			.inner_join(pe)
			.on(per.parent == pe.name)
			.select(per.reference_name)
			.where(per.reference_doctype == "Sales Invoice")
			.where(pe.docstatus == 1)
			.where(pe.payment_type == "Receive")
			.where(pe.mode_of_payment == filters.mode_of_payment)
		)

		query = query.where(si.name.isin(direct) | si.name.isin(via_pe))

	return query.run(as_dict=True)


def get_payment_map(invoice_names):
	if not invoice_names:
		return {}, []

	payment_map = {}
	modes_set = set()

	# 1. POS-style direct payments (Sales Invoice Payment child table)
	sip = frappe.qb.DocType("Sales Invoice Payment")
	direct = (
		frappe.qb.from_(sip)
		.select(
			sip.parent,
			sip.mode_of_payment,
			fn.Sum(sip.base_amount).as_("base_amount"),
		)
		.where(sip.parent.isin(invoice_names))
		.groupby(sip.parent, sip.mode_of_payment)
		.run(as_dict=True)
	)

	for p in direct:
		if not p.mode_of_payment:
			continue
		payment_map.setdefault(p.parent, {})[p.mode_of_payment] = flt(p.base_amount)
		modes_set.add(p.mode_of_payment)

	# 2. Non-POS payments via Payment Entry Reference (canonical PE → SI link)
	#    Sales Invoice Advance is unreliable: it's only populated when the invoice
	#    is saved with `allocate_advances_automatically=1` AND a matching unallocated
	#    PE exists at that moment. Payment Entry Reference is the source of truth.
	per = frappe.qb.DocType("Payment Entry Reference")
	pe = frappe.qb.DocType("Payment Entry")
	via_pe = (
		frappe.qb.from_(per)
		.inner_join(pe)
		.on(per.parent == pe.name)
		.select(
			per.reference_name.as_("parent"),
			pe.mode_of_payment,
			fn.Sum(per.allocated_amount * fn.Coalesce(per.exchange_rate, 1)).as_("base_amount"),
		)
		.where(per.reference_doctype == "Sales Invoice")
		.where(per.reference_name.isin(invoice_names))
		.where(pe.docstatus == 1)
		.where(pe.payment_type == "Receive")
		.groupby(per.reference_name, pe.mode_of_payment)
		.run(as_dict=True)
	)

	for a in via_pe:
		if not a.mode_of_payment:
			continue
		existing = flt(payment_map.setdefault(a.parent, {}).get(a.mode_of_payment, 0))
		payment_map[a.parent][a.mode_of_payment] = existing + flt(a.base_amount)
		modes_set.add(a.mode_of_payment)

	all_modes = sorted(modes_set)
	return payment_map, all_modes


def get_columns(all_modes):
	columns = [
		{
			"label": _("Voucher Type"),
			"fieldname": "voucher_type",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Voucher"),
			"fieldname": "voucher_no",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 160,
		},
		{
			"label": _("Posting Date"),
			"fieldname": "posting_date",
			"fieldtype": "Date",
			"width": 100,
		},
		{
			"label": _("Customer"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 120,
		},
		{
			"label": _("Customer Name"),
			"fieldname": "customer_name",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"label": _("Grand Total"),
			"fieldname": "grand_total",
			"fieldtype": "Float",
			"precision": 2,
			"width": 120,
		},
		{
			"label": _("Outstanding Amount"),
			"fieldname": "outstanding_amount",
			"fieldtype": "Float",
			"precision": 2,
			"width": 120,
		},
	]

	for mode in all_modes:
		columns.append(
			{
				"label": _(mode),
				"fieldname": frappe.scrub(mode),
				"fieldtype": "Float",
				"width": 120,
			}
		)

	return columns


def get_data(invoices, payment_map, all_modes):
	data = []
	for inv in invoices:
		is_return = bool(inv.is_return)
		row = {
			"voucher_type": "Sales Invoice-Return" if is_return else "Sales Invoice",
			"voucher_no": inv.name,
			"posting_date": inv.posting_date,
			"customer": inv.customer,
			"customer_name": inv.customer_name,
			"grand_total": flt(inv.base_grand_total, 2),
			"outstanding_amount": flt(inv.outstanding_amount, 2),
			"is_return": 1 if is_return else 0,
		}

		inv_payments = payment_map.get(inv.name, {})
		for mode in all_modes:
			row[frappe.scrub(mode)] = flt(inv_payments.get(mode, 0), 2)

		data.append(row)

	return data


def get_report_summary(data, all_modes):
	if not data:
		return []

	total_grand = sum(flt(d.get("grand_total")) for d in data)
	total_outstanding = sum(flt(d.get("outstanding_amount")) for d in data)

	summary = [
		{
			"value": total_grand,
			"label": _("Total Grand Total"),
			"datatype": "Float",
			"indicator": "Blue",
		},
		{
			"value": total_outstanding,
			"label": _("Total Outstanding"),
			"datatype": "Float",
			"indicator": "Red" if total_outstanding > 0 else "Green",
		},
	]

	for mode in all_modes:
		fieldname = frappe.scrub(mode)
		total = sum(flt(d.get(fieldname)) for d in data)
		summary.append(
			{
				"value": total,
				"label": _(mode),
				"datatype": "Float",
				"indicator": "Blue",
			}
		)

	return summary


@frappe.whitelist()
def get_custom_sale_type_options():
	meta = frappe.get_meta("Sales Invoice")
	field = meta.get_field("custom_sale_type")
	if not field:
		return None
	return [o.strip() for o in (field.options or "").split("\n") if o.strip()]
