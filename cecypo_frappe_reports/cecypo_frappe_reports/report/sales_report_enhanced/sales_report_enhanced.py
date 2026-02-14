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
		query = query.where(si.customer_group == filters.customer_group)

	if filters.get("mode_of_payment"):
		sip = frappe.qb.DocType("Sales Invoice Payment")
		sia = frappe.qb.DocType("Sales Invoice Advance")
		pe = frappe.qb.DocType("Payment Entry")

		# Invoices with direct payment matching the mode
		direct = (
			frappe.qb.from_(sip)
			.select(sip.parent)
			.where(sip.mode_of_payment == filters.mode_of_payment)
		)

		# Invoices with advance payment entry matching the mode
		via_advance = (
			frappe.qb.from_(sia)
			.inner_join(pe)
			.on(sia.reference_name == pe.name)
			.select(sia.parent)
			.where(sia.reference_type == "Payment Entry")
			.where(pe.docstatus == 1)
			.where(pe.mode_of_payment == filters.mode_of_payment)
		)

		query = query.where(si.name.isin(direct) | si.name.isin(via_advance))

	return query.run(as_dict=True)


def get_payment_map(invoice_names):
	if not invoice_names:
		return {}, []

	payment_map = {}
	modes_set = set()

	# 1. Direct payments (Sales Invoice Payment child table - POS invoices)
	sip = frappe.qb.DocType("Sales Invoice Payment")
	payments = (
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

	for p in payments:
		payment_map.setdefault(p.parent, {})[p.mode_of_payment] = flt(p.base_amount)
		modes_set.add(p.mode_of_payment)

	# 2. Advances (Sales Invoice Advance → Payment Entry)
	sia = frappe.qb.DocType("Sales Invoice Advance")
	pe = frappe.qb.DocType("Payment Entry")
	advances = (
		frappe.qb.from_(sia)
		.inner_join(pe)
		.on(sia.reference_name == pe.name)
		.select(
			sia.parent,
			pe.mode_of_payment,
			fn.Sum(sia.allocated_amount).as_("allocated_amount"),
		)
		.where(sia.parent.isin(invoice_names))
		.where(sia.reference_type == "Payment Entry")
		.where(pe.docstatus == 1)
		.groupby(sia.parent, pe.mode_of_payment)
		.run(as_dict=True)
	)

	for a in advances:
		if not a.mode_of_payment:
			continue
		existing = flt(payment_map.setdefault(a.parent, {}).get(a.mode_of_payment, 0))
		payment_map[a.parent][a.mode_of_payment] = existing + flt(a.allocated_amount)
		modes_set.add(a.mode_of_payment)

	all_modes = sorted(modes_set)
	return payment_map, all_modes


def get_columns(all_modes):
	columns = [
		{
			"label": _("Voucher Type"),
			"fieldname": "voucher_type",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": _("Voucher"),
			"fieldname": "voucher_no",
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
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
			"fieldtype": "Currency",
			"width": 120,
		},
		{
			"label": _("Outstanding Amount"),
			"fieldname": "outstanding_amount",
			"fieldtype": "Currency",
			"width": 120,
		},
	]

	for mode in all_modes:
		columns.append(
			{
				"label": _(mode),
				"fieldname": frappe.scrub(mode),
				"fieldtype": "Currency",
				"width": 120,
			}
		)

	return columns


def get_data(invoices, payment_map, all_modes):
	data = []
	for inv in invoices:
		row = {
			"voucher_type": "Sales Invoice",
			"voucher_no": inv.name,
			"posting_date": inv.posting_date,
			"customer": inv.customer,
			"customer_name": inv.customer_name,
			"grand_total": flt(inv.base_grand_total),
			"outstanding_amount": flt(inv.outstanding_amount),
		}

		inv_payments = payment_map.get(inv.name, {})
		for mode in all_modes:
			row[frappe.scrub(mode)] = flt(inv_payments.get(mode, 0))

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
			"datatype": "Currency",
			"indicator": "Blue",
		},
		{
			"value": total_outstanding,
			"label": _("Total Outstanding"),
			"datatype": "Currency",
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
				"datatype": "Currency",
				"indicator": "Blue",
			}
		)

	return summary
