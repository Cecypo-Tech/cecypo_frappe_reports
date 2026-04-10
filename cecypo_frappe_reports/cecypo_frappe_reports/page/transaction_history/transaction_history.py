# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt
from pypika import functions as fn


@frappe.whitelist()
def get_item_history(item, company, from_date=None, to_date=None, warehouse=None):
	return {
		"item_details": _get_item_details(item),
		"stock_metrics": _get_stock_metrics(item, company, warehouse),
		"purchases": _get_purchase_rows(item, company, from_date, to_date, warehouse),
		"sales": _get_sales_rows(item, company, from_date, to_date, warehouse),
		"open_po": _get_open_purchase_orders(item, company, warehouse),
		"open_so": _get_open_sales_orders(item, company, warehouse),
	}


@frappe.whitelist()
def get_customer_history(customer, company, from_date=None, to_date=None):
	from pypika import Case

	sii = frappe.qb.DocType("Sales Invoice Item")
	si = frappe.qb.DocType("Sales Invoice")

	query = (
		frappe.qb.from_(sii)
		.inner_join(si).on(sii.parent == si.name)
		.select(
			sii.item_code,
			sii.item_name,
			fn.Sum(sii.qty).as_("total_qty"),
			fn.Count(si.name).distinct().as_("invoice_count"),
			fn.Avg(sii.base_rate).as_("avg_rate"),
			fn.Sum(sii.base_amount).as_("total_amount"),
			fn.Max(si.posting_date).as_("last_sale"),
			fn.Sum(Case().when(si.status == "Overdue", 1).else_(0)).as_("overdue_count"),
			fn.Sum(Case().when(si.status.isin(["Unpaid", "Overdue", "Partly Paid"]), 1).else_(0)).as_("unpaid_count"),
		)
		.where(si.docstatus == 1)
		.where(si.customer == customer)
		.where(si.company == company)
		.groupby(sii.item_code, sii.item_name)
		.orderby(fn.Sum(sii.base_amount), order=frappe.qb.desc)
	)
	if from_date:
		query = query.where(si.posting_date >= from_date)
	if to_date:
		query = query.where(si.posting_date <= to_date)

	rows = query.run(as_dict=True)
	for r in rows:
		r["total_qty"] = flt(r["total_qty"], 2)
		r["avg_rate"] = flt(r["avg_rate"], 2)
		r["total_amount"] = flt(r["total_amount"], 2)
		r["overdue_count"] = r.get("overdue_count") or 0
		r["unpaid_count"] = r.get("unpaid_count") or 0
	return rows


@frappe.whitelist()
def get_customer_item_transactions(customer, item_code, company, from_date=None, to_date=None):
	sii = frappe.qb.DocType("Sales Invoice Item")
	si = frappe.qb.DocType("Sales Invoice")

	query = (
		frappe.qb.from_(sii)
		.inner_join(si).on(sii.parent == si.name)
		.select(
			si.posting_date.as_("date"),
			sii.parent.as_("voucher_no"),
			sii.qty,
			sii.uom,
			sii.rate,
			si.currency,
			sii.base_rate,
			si.status,
		)
		.where(si.docstatus == 1)
		.where(si.customer == customer)
		.where(sii.item_code == item_code)
		.where(si.company == company)
		.orderby(si.posting_date, order=frappe.qb.desc)
	)
	if from_date:
		query = query.where(si.posting_date >= from_date)
	if to_date:
		query = query.where(si.posting_date <= to_date)

	rows = query.run(as_dict=True)
	for r in rows:
		r["qty"] = flt(r["qty"], 2)
		r["rate"] = flt(r["rate"], 2)
		r["base_rate"] = flt(r["base_rate"], 2)
	return rows


@frappe.whitelist()
def get_supplier_history(supplier, company, from_date=None, to_date=None, source="pi"):
	from pypika import Case

	if source == "pi":
		pii = frappe.qb.DocType("Purchase Invoice Item")
		pi = frappe.qb.DocType("Purchase Invoice")

		query = (
			frappe.qb.from_(pii)
			.inner_join(pi).on(pii.parent == pi.name)
			.select(
				pii.item_code,
				pii.item_name,
				fn.Sum(pii.qty).as_("total_qty"),
				fn.Count(pi.name).distinct().as_("receipt_count"),
				fn.Avg(pii.valuation_rate).as_("avg_valuation_rate"),
				fn.Sum(pii.base_amount).as_("total_amount"),
				fn.Max(pi.posting_date).as_("last_purchase"),
				fn.Sum(Case().when(pi.status == "Overdue", 1).else_(0)).as_("overdue_count"),
				fn.Sum(Case().when(pi.status.isin(["Unpaid", "Overdue", "Partly Paid"]), 1).else_(0)).as_("unpaid_count"),
			)
			.where(pi.docstatus == 1)
			.where(pi.update_stock == 1)
			.where(pi.supplier == supplier)
			.where(pi.company == company)
			.groupby(pii.item_code, pii.item_name)
			.orderby(fn.Sum(pii.base_amount), order=frappe.qb.desc)
		)
		if from_date:
			query = query.where(pi.posting_date >= from_date)
		if to_date:
			query = query.where(pi.posting_date <= to_date)
	else:
		pri = frappe.qb.DocType("Purchase Receipt Item")
		pr = frappe.qb.DocType("Purchase Receipt")

		query = (
			frappe.qb.from_(pri)
			.inner_join(pr).on(pri.parent == pr.name)
			.select(
				pri.item_code,
				pri.item_name,
				fn.Sum(pri.qty).as_("total_qty"),
				fn.Count(pr.name).distinct().as_("receipt_count"),
				fn.Avg(pri.valuation_rate).as_("avg_valuation_rate"),
				fn.Sum(pri.base_amount).as_("total_amount"),
				fn.Max(pr.posting_date).as_("last_purchase"),
				fn.Sum(Case().when(pr.status == "To Bill", 1).else_(0)).as_("unpaid_count"),
			)
			.where(pr.docstatus == 1)
			.where(pr.supplier == supplier)
			.where(pr.company == company)
			.groupby(pri.item_code, pri.item_name)
			.orderby(fn.Sum(pri.base_amount), order=frappe.qb.desc)
		)
		if from_date:
			query = query.where(pr.posting_date >= from_date)
		if to_date:
			query = query.where(pr.posting_date <= to_date)

	rows = query.run(as_dict=True)
	for r in rows:
		r["total_qty"] = flt(r["total_qty"], 2)
		r["avg_valuation_rate"] = flt(r["avg_valuation_rate"], 2)
		r["total_amount"] = flt(r["total_amount"], 2)
		r["overdue_count"] = r.get("overdue_count") or 0
		r["unpaid_count"] = r.get("unpaid_count") or 0
	return rows


@frappe.whitelist()
def get_supplier_item_transactions(supplier, item_code, company, from_date=None, to_date=None, source="pi"):
	if source == "pi":
		pii = frappe.qb.DocType("Purchase Invoice Item")
		pi = frappe.qb.DocType("Purchase Invoice")

		query = (
			frappe.qb.from_(pii)
			.inner_join(pi).on(pii.parent == pi.name)
			.select(
				pi.posting_date.as_("date"),
				pii.parent.as_("voucher_no"),
				pii.qty,
				pii.uom,
				pii.rate,
				pi.currency,
				pii.valuation_rate,
				pi.status,
			)
			.where(pi.docstatus == 1)
			.where(pi.update_stock == 1)
			.where(pi.supplier == supplier)
			.where(pii.item_code == item_code)
			.where(pi.company == company)
			.orderby(pi.posting_date, order=frappe.qb.desc)
		)
		if from_date:
			query = query.where(pi.posting_date >= from_date)
		if to_date:
			query = query.where(pi.posting_date <= to_date)
	else:
		pri = frappe.qb.DocType("Purchase Receipt Item")
		pr = frappe.qb.DocType("Purchase Receipt")

		query = (
			frappe.qb.from_(pri)
			.inner_join(pr).on(pri.parent == pr.name)
			.select(
				pr.posting_date.as_("date"),
				pri.parent.as_("voucher_no"),
				pri.qty,
				pri.uom,
				pri.rate,
				pr.currency,
				pri.valuation_rate,
				pr.status,
			)
			.where(pr.docstatus == 1)
			.where(pr.supplier == supplier)
			.where(pri.item_code == item_code)
			.where(pr.company == company)
			.orderby(pr.posting_date, order=frappe.qb.desc)
		)
		if from_date:
			query = query.where(pr.posting_date >= from_date)
		if to_date:
			query = query.where(pr.posting_date <= to_date)

	rows = query.run(as_dict=True)
	for r in rows:
		r["qty"] = flt(r["qty"], 2)
		r["rate"] = flt(r["rate"], 2)
		r["valuation_rate"] = flt(r["valuation_rate"], 2)
	return rows


# ── Private helpers ──────────────────────────────────────────────────────────

def _calculate_aging_bucket(due_date, as_of_date):
	"""Return the aging bucket key for an invoice due on due_date as of as_of_date."""
	days = (as_of_date - due_date).days
	if days <= 30:
		return "bucket_0_30"
	elif days <= 60:
		return "bucket_31_60"
	elif days <= 90:
		return "bucket_61_90"
	return "bucket_90_plus"


def _get_item_details(item):
	return frappe.db.get_value(
		"Item",
		item,
		["item_name", "item_code", "brand", "item_group", "stock_uom", "valuation_method"],
		as_dict=True,
	) or {}


def _get_stock_metrics(item, company, warehouse=None):
	filters = {"item_code": item}
	if warehouse:
		filters["warehouse"] = warehouse

	bin_rows = frappe.db.get_all("Bin", filters=filters, fields=["actual_qty", "valuation_rate"])
	total_qty = flt(sum(flt(b.actual_qty) for b in bin_rows), 2)
	stock_value = flt(sum(flt(b.actual_qty) * flt(b.valuation_rate) for b in bin_rows), 2)
	avg_rate = flt(stock_value / total_qty, 2) if total_qty else 0.0

	poi = frappe.qb.DocType("Purchase Order Item")
	po = frappe.qb.DocType("Purchase Order")
	pending_po = (
		frappe.qb.from_(poi)
		.inner_join(po).on(poi.parent == po.name)
		.select((poi.qty - poi.received_qty).as_("pending"))
		.where(po.docstatus == 1)
		.where(poi.item_code == item)
		.where(po.company == company)
		.where(poi.qty > poi.received_qty)
		.run()
	)
	pending_po_qty = flt(sum(r[0] for r in pending_po), 2)

	soi = frappe.qb.DocType("Sales Order Item")
	so = frappe.qb.DocType("Sales Order")
	pending_so = (
		frappe.qb.from_(soi)
		.inner_join(so).on(soi.parent == so.name)
		.select((soi.qty - soi.delivered_qty).as_("pending"))
		.where(so.docstatus == 1)
		.where(soi.item_code == item)
		.where(so.company == company)
		.where(soi.qty > soi.delivered_qty)
		.run()
	)
	pending_so_qty = flt(sum(r[0] for r in pending_so), 2)

	reorder = frappe.db.get_value(
		"Item Reorder", {"parent": item}, "warehouse_reorder_level"
	) or "—"

	return {
		"current_stock": total_qty,
		"avg_rate": avg_rate,
		"stock_value": stock_value,
		"pending_po_qty": pending_po_qty,
		"pending_so_qty": pending_so_qty,
		"reorder_level": reorder,
	}


def _get_purchase_rows(item, company, from_date, to_date, warehouse):
	# Purchase Invoice (stock-updating only)
	pii = frappe.qb.DocType("Purchase Invoice Item")
	pi = frappe.qb.DocType("Purchase Invoice")
	pi_query = (
		frappe.qb.from_(pii)
		.inner_join(pi).on(pii.parent == pi.name)
		.select(
			pi.posting_date.as_("date"),
			pii.parent.as_("voucher_no"),
			pi.supplier,
			pii.qty,
			pii.uom,
			pii.rate,
			pi.currency,
			pii.valuation_rate,
			pi.status,
		)
		.where(pi.docstatus == 1)
		.where(pi.update_stock == 1)
		.where(pii.item_code == item)
		.where(pi.company == company)
	)
	if from_date:
		pi_query = pi_query.where(pi.posting_date >= from_date)
	if to_date:
		pi_query = pi_query.where(pi.posting_date <= to_date)
	if warehouse:
		pi_query = pi_query.where(pii.warehouse == warehouse)
	pi_rows = pi_query.run(as_dict=True)
	for r in pi_rows:
		r["doctype"] = "Purchase Invoice"
		r["qty"] = flt(r["qty"], 2)
		r["rate"] = flt(r["rate"], 2)
		r["valuation_rate"] = flt(r["valuation_rate"], 2)

	# Purchase Receipt
	pri = frappe.qb.DocType("Purchase Receipt Item")
	pr = frappe.qb.DocType("Purchase Receipt")
	pr_query = (
		frappe.qb.from_(pri)
		.inner_join(pr).on(pri.parent == pr.name)
		.select(
			pr.posting_date.as_("date"),
			pri.parent.as_("voucher_no"),
			pr.supplier,
			pri.qty,
			pri.uom,
			pri.rate,
			pr.currency,
			pri.valuation_rate,
			pr.status,
		)
		.where(pr.docstatus == 1)
		.where(pri.item_code == item)
		.where(pr.company == company)
	)
	if from_date:
		pr_query = pr_query.where(pr.posting_date >= from_date)
	if to_date:
		pr_query = pr_query.where(pr.posting_date <= to_date)
	if warehouse:
		pr_query = pr_query.where(pri.warehouse == warehouse)
	pr_rows = pr_query.run(as_dict=True)
	for r in pr_rows:
		r["doctype"] = "Purchase Receipt"
		r["qty"] = flt(r["qty"], 2)
		r["rate"] = flt(r["rate"], 2)
		r["valuation_rate"] = flt(r["valuation_rate"], 2)

	rows = pi_rows + pr_rows
	rows.sort(key=lambda r: r.get("date") or "", reverse=True)
	return rows


def _get_open_purchase_orders(item, company, warehouse=None):
	poi = frappe.qb.DocType("Purchase Order Item")
	po = frappe.qb.DocType("Purchase Order")

	query = (
		frappe.qb.from_(poi)
		.inner_join(po).on(poi.parent == po.name)
		.select(
			po.transaction_date.as_("date"),
			poi.parent.as_("voucher_no"),
			po.supplier,
			poi.qty.as_("ordered_qty"),
			poi.received_qty,
			(poi.qty - poi.received_qty).as_("pending_qty"),
			poi.rate,
			poi.uom,
			po.currency,
			po.status,
		)
		.where(po.docstatus == 1)
		.where(po.status.notin(["Closed", "Cancelled"]))
		.where(poi.item_code == item)
		.where(po.company == company)
		.where(poi.qty > poi.received_qty)
		.orderby(po.transaction_date, order=frappe.qb.desc)
	)
	if warehouse:
		query = query.where(poi.warehouse == warehouse)

	rows = query.run(as_dict=True)
	for r in rows:
		r["ordered_qty"] = flt(r["ordered_qty"], 2)
		r["received_qty"] = flt(r["received_qty"], 2)
		r["pending_qty"] = flt(r["pending_qty"], 2)
		r["rate"] = flt(r["rate"], 2)
	return rows


def _get_open_sales_orders(item, company, warehouse=None):
	soi = frappe.qb.DocType("Sales Order Item")
	so = frappe.qb.DocType("Sales Order")

	query = (
		frappe.qb.from_(soi)
		.inner_join(so).on(soi.parent == so.name)
		.select(
			so.transaction_date.as_("date"),
			soi.parent.as_("voucher_no"),
			so.customer,
			soi.qty.as_("ordered_qty"),
			soi.delivered_qty,
			(soi.qty - soi.delivered_qty).as_("pending_qty"),
			soi.rate,
			soi.uom,
			so.currency,
			so.status,
		)
		.where(so.docstatus == 1)
		.where(so.status.notin(["Closed", "Cancelled"]))
		.where(soi.item_code == item)
		.where(so.company == company)
		.where(soi.qty > soi.delivered_qty)
		.orderby(so.transaction_date, order=frappe.qb.desc)
	)
	if warehouse:
		query = query.where(soi.warehouse == warehouse)

	rows = query.run(as_dict=True)
	for r in rows:
		r["ordered_qty"] = flt(r["ordered_qty"], 2)
		r["delivered_qty"] = flt(r["delivered_qty"], 2)
		r["pending_qty"] = flt(r["pending_qty"], 2)
		r["rate"] = flt(r["rate"], 2)
	return rows


def _get_sales_rows(item, company, from_date, to_date, warehouse):
	sii = frappe.qb.DocType("Sales Invoice Item")
	si = frappe.qb.DocType("Sales Invoice")

	query = (
		frappe.qb.from_(sii)
		.inner_join(si).on(sii.parent == si.name)
		.select(
			si.posting_date.as_("date"),
			sii.parent.as_("voucher_no"),
			si.customer,
			sii.qty,
			sii.uom,
			sii.rate,
			si.currency,
			sii.base_rate,
			si.status,
		)
		.where(si.docstatus == 1)
		.where(sii.item_code == item)
		.where(si.company == company)
		.orderby(si.posting_date, order=frappe.qb.desc)
	)
	if from_date:
		query = query.where(si.posting_date >= from_date)
	if to_date:
		query = query.where(si.posting_date <= to_date)
	if warehouse:
		query = query.where(sii.warehouse == warehouse)

	rows = query.run(as_dict=True)
	for r in rows:
		r["qty"] = flt(r["qty"], 2)
		r["rate"] = flt(r["rate"], 2)
		r["base_rate"] = flt(r["base_rate"], 2)
	return rows
