# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from pypika import functions as fn

# Column for Payment Entries saved without a Mode of Payment
NO_MODE = "No Mode of Payment"


def execute(filters=None):
	if not filters:
		filters = frappe._dict({})

	include_remarks = bool(filters.get("include_remarks"))
	include_mpesa = (
		bool(filters.get("include_mpesa")) and "frappe_mpsa_payments" in frappe.get_installed_apps()
	)
	invoices = get_invoices(filters)
	if not invoices:
		return get_columns([], include_remarks, include_mpesa), [], None, None, None

	payment_map, all_modes = get_payment_map(invoices)
	mpesa_map = get_mpesa_transids([inv.name for inv in invoices]) if include_mpesa else None
	columns = get_columns(all_modes, include_remarks, include_mpesa)
	data = get_data(invoices, payment_map, all_modes, include_remarks, mpesa_map)
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
			si.base_rounded_total,
			si.outstanding_amount,
			si.is_return,
			si.return_against,
			si.update_outstanding_for_self,
			si.base_change_amount,
			si.account_for_change_amount,
			si.remarks,
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

	if filters.get("owner"):
		query = query.where(si.owner == filters.owner)

	if filters.get("with_outstandings"):
		query = query.where(si.outstanding_amount > 0)

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
			frappe.qb.from_(sii).select(sii.parent).where(sii.warehouse == filters.warehouse).distinct()
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
		direct = frappe.qb.from_(sip).select(sip.parent).where(sip.mode_of_payment == filters.mode_of_payment)

		# Non-POS payments via Payment Entry → Payment Entry Reference
		via_pe = (
			frappe.qb.from_(per)
			.inner_join(pe)
			.on(per.parent == pe.name)
			.select(per.reference_name)
			.where(per.reference_doctype == "Sales Invoice")
			.where(pe.docstatus == 1)
			.where(pe.payment_type.isin(["Receive", "Pay"]))
			.where(pe.mode_of_payment == filters.mode_of_payment)
		)

		query = query.where(si.name.isin(direct) | si.name.isin(via_pe))

	return query.run(as_dict=True)


def get_payment_map(invoices):
	if not invoices:
		return {}, []

	invoice_names = [inv.name for inv in invoices]

	# 1. POS-style direct payments (Sales Invoice Payment child table)
	sip = frappe.qb.DocType("Sales Invoice Payment")
	direct = (
		frappe.qb.from_(sip)
		.select(
			sip.parent,
			sip.mode_of_payment,
			sip.account,
			sip.type,
			fn.Sum(sip.base_amount).as_("base_amount"),
		)
		.where(sip.parent.isin(invoice_names))
		.groupby(sip.parent, sip.mode_of_payment, sip.account, sip.type)
		.run(as_dict=True)
	)

	payment_map, modes_set = get_direct_payments(direct, invoices)

	# 2. Non-POS payments via Payment Entry Reference (canonical PE → SI link)
	#    Sales Invoice Advance is unreliable: it's only populated when the invoice
	#    is saved with `allocate_advances_automatically=1` AND a matching unallocated
	#    PE exists at that moment. Payment Entry Reference is the source of truth.
	#    "Pay" entries are refunds against returns; their allocation is negative.
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
		.where(pe.payment_type.isin(["Receive", "Pay"]))
		.groupby(per.reference_name, pe.mode_of_payment)
		.run(as_dict=True)
	)

	add_payment_entries(payment_map, modes_set, via_pe)

	all_modes = sorted(modes_set)
	return payment_map, all_modes


def add_payment_entries(payment_map, modes_set, rows):
	"""Add Payment Entry allocations to the POS payments, per invoice and mode."""
	for a in rows:
		mode = a.mode_of_payment or NO_MODE
		existing = flt(payment_map.setdefault(a.parent, {}).get(mode, 0))
		payment_map[a.parent][mode] = existing + flt(a.base_amount)
		modes_set.add(mode)


def get_direct_payments(rows, invoices):
	"""Sum POS payment rows per invoice and mode, net of change handed back.

	A POS payment row holds the amount *tendered*. The change goes back out of
	`account_for_change_amount`, so take it off the row on that account — failing
	that the Cash-type row, failing that the largest row — so the mode columns sum
	to what the business kept.
	"""
	rows_by_invoice = {}
	for row in rows:
		if row.mode_of_payment:
			rows_by_invoice.setdefault(row.parent, []).append(row)

	payment_map = {}
	modes_set = set()
	for inv in invoices:
		inv_rows = rows_by_invoice.get(inv.name)
		if not inv_rows:
			continue

		change = flt(inv.get("base_change_amount"))
		change_row = None
		if change:
			change_row = (
				next((r for r in inv_rows if r.account == inv.get("account_for_change_amount")), None)
				or next((r for r in inv_rows if r.type == "Cash"), None)
				or max(inv_rows, key=lambda r: flt(r.base_amount))
			)

		inv_payments = payment_map.setdefault(inv.name, {})
		for row in inv_rows:
			amount = flt(row.base_amount) - (change if row is change_row else 0)
			inv_payments[row.mode_of_payment] = flt(inv_payments.get(row.mode_of_payment, 0)) + amount
			modes_set.add(row.mode_of_payment)

	return payment_map, modes_set


def get_mpesa_transids(invoice_names):
	"""M-Pesa receipt numbers per invoice, as "ID1, ID2".

	A receipt reaches an invoice two ways: an `Mpesa C2B Payment Register` row whose
	Payment Entry is allocated to it, or a POS `Phone` payment row (STK push) carrying
	the receipt in `reference_no`, sometimes as a comma list.
	"""
	reg = frappe.qb.DocType("Mpesa C2B Payment Register")
	per = frappe.qb.DocType("Payment Entry Reference")
	pe = frappe.qb.DocType("Payment Entry")
	via_register = (
		frappe.qb.from_(reg)
		.inner_join(pe)
		.on(pe.name == reg.payment_entry)
		.inner_join(per)
		.on(per.parent == pe.name)
		.select(per.reference_name.as_("parent"), reg.transid)
		.where(pe.docstatus == 1)
		.where(per.reference_doctype == "Sales Invoice")
		.where(per.reference_name.isin(invoice_names))
		.run(as_dict=True)
	)

	sip = frappe.qb.DocType("Sales Invoice Payment")
	via_pos = (
		frappe.qb.from_(sip)
		.select(sip.parent, sip.reference_no.as_("transid"))
		.where(sip.parent.isin(invoice_names))
		.where(sip.type == "Phone")
		.where(fn.Coalesce(sip.reference_no, "") != "")
		.run(as_dict=True)
	)

	return merge_transids(via_register + via_pos)


def merge_transids(rows):
	ids = {}
	for row in rows:
		for transid in (row.transid or "").split(","):
			if transid.strip():
				ids.setdefault(row.parent, set()).add(transid.strip())
	return {parent: ", ".join(sorted(t)) for parent, t in ids.items()}


def get_columns(all_modes, include_remarks=False, include_mpesa=False):
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

	if include_remarks:
		columns.append(
			{
				"label": _("Remarks"),
				"fieldname": "remarks",
				"fieldtype": "Small Text",
				"width": 250,
				# Datatable right-aligns a column whose first value looks numeric, "" included
				"align": "left",
			}
		)

	if include_mpesa:
		columns.append(
			{
				"label": _("M-Pesa Trans ID"),
				"fieldname": "mpesa_transid",
				"fieldtype": "Data",
				"width": 200,
				# Datatable right-aligns a column whose first value looks numeric, "" included
				"align": "left",
			}
		)

	return columns


def get_data(invoices, payment_map, all_modes, include_remarks=False, mpesa_map=None):
	data = []
	for inv in invoices:
		is_return = bool(inv.is_return)
		row = {
			"voucher_type": "Sales Invoice-Return" if is_return else "Sales Invoice",
			"voucher_no": inv.name,
			"posting_date": inv.posting_date,
			"customer": inv.customer,
			"customer_name": inv.customer_name,
			# Outstanding is based on the rounded total; 0 when rounding is disabled
			"grand_total": flt(inv.base_rounded_total or inv.base_grand_total, 2),
			"outstanding_amount": flt(get_outstanding(inv), 2),
			"is_return": 1 if is_return else 0,
		}

		inv_payments = payment_map.get(inv.name, {})
		for mode in all_modes:
			row[frappe.scrub(mode)] = flt(inv_payments.get(mode, 0), 2)

		if include_remarks:
			row["remarks"] = inv.get("remarks") or ""

		if mpesa_map is not None:
			row["mpesa_transid"] = mpesa_map.get(inv.name, "")

		data.append(row)

	return data


def get_outstanding(inv):
	"""The invoice's outstanding, ignoring the stale figure on a POS return applied to its original.

	With `update_outstanding_for_self` off, a return's ledger entries reduce the original
	invoice's outstanding, not its own. ERPNext zeroes the return's own outstanding only for
	non-POS returns, so a POS return keeps -grand_total there and would be counted twice.
	"""
	if inv.get("is_return") and inv.get("return_against") and not inv.get("update_outstanding_for_self"):
		return 0
	return inv.outstanding_amount


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
