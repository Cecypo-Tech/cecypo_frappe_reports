# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate
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
	item_codes = [r["item_code"] for r in rows]
	stock_map = _get_items_stock_map(item_codes, company) if rows else {}
	last_rate_map = _get_customer_last_rate_map(customer, company, item_codes, from_date, to_date) if rows else {}
	for r in rows:
		r["total_qty"] = flt(r["total_qty"], 2)
		r["avg_rate"] = flt(r["avg_rate"], 2)
		r["total_amount"] = flt(r["total_amount"], 2)
		r["overdue_count"] = r.get("overdue_count") or 0
		r["unpaid_count"] = r.get("unpaid_count") or 0
		r["current_stock"] = stock_map.get(r["item_code"], 0.0)
		r["last_rate"] = last_rate_map.get(r["item_code"], 0.0)
	return rows


@frappe.whitelist()
def get_customer_item_transactions(customer, item_code, company, from_date=None, to_date=None):
	from frappe.utils import getdate, today

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
			si.due_date,
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

	as_of = getdate(today())
	rows = query.run(as_dict=True)
	for r in rows:
		r["qty"] = flt(r["qty"], 2)
		r["rate"] = flt(r["rate"], 2)
		r["base_rate"] = flt(r["base_rate"], 2)
		due = getdate(r.due_date) if r.due_date else getdate(r.date)
		r["days_overdue"] = max(0, (as_of - due).days) if r.status not in ("Paid", "Return", "Credit Note Issued") else 0
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
	item_codes = [r["item_code"] for r in rows]
	stock_map = _get_items_stock_map(item_codes, company) if rows else {}
	last_rate_map = _get_supplier_last_rate_map(supplier, company, item_codes, source, from_date, to_date) if rows else {}
	for r in rows:
		r["total_qty"] = flt(r["total_qty"], 2)
		r["avg_valuation_rate"] = flt(r["avg_valuation_rate"], 2)
		r["total_amount"] = flt(r["total_amount"], 2)
		r["overdue_count"] = r.get("overdue_count") or 0
		r["unpaid_count"] = r.get("unpaid_count") or 0
		r["current_stock"] = stock_map.get(r["item_code"], 0.0)
		r["last_rate"] = last_rate_map.get(r["item_code"], 0.0)
	return rows


@frappe.whitelist()
def get_supplier_item_transactions(supplier, item_code, company, from_date=None, to_date=None, source="pi"):
	from frappe.utils import getdate, today

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
				pi.due_date,
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

		as_of = getdate(today())
		rows = query.run(as_dict=True)
		for r in rows:
			r["qty"] = flt(r["qty"], 2)
			r["rate"] = flt(r["rate"], 2)
			r["valuation_rate"] = flt(r["valuation_rate"], 2)
			due = getdate(r.due_date) if r.due_date else getdate(r.date)
			r["days_overdue"] = max(0, (as_of - due).days) if r.status not in ("Paid", "Return", "Debit Note Issued") else 0
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
			r["due_date"] = None
			r["days_overdue"] = None  # PRs have no payment due date
	return rows


@frappe.whitelist()
def get_receivables(company, as_of_date, customer=None, show_future_payments=0):
	"""AR aging summary — one row per customer with a non-zero net balance.

	Sourced from ERPNext's own Accounts Receivable report engine (Payment Ledger Entry based)
	instead of a bespoke Sales Invoice/Payment Entry query, so totals always match the standard
	AR report and the PSOA AR Statement print format: credit notes/returns net into the total,
	and "outstanding" stays as-of-date consistent (a future-dated payment only nets in when
	show_future_payments is on, matching how the standard report treats it).
	"""
	frappe.has_permission("Sales Invoice", "read", throw=True)
	return _get_party_balances(
		party_type="Customer",
		company=company,
		as_of_date=as_of_date,
		party=customer,
		show_future_payments=show_future_payments,
	)


@frappe.whitelist()
def get_receivables_detail(customer, company, as_of_date, show_future_payments=0):
	"""Individual outstanding SI rows for accordion drill-down."""
	frappe.has_permission("Sales Invoice", "read", throw=True)
	return _get_party_balance_detail(
		party_type="Customer",
		company=company,
		as_of_date=as_of_date,
		party=customer,
		show_future_payments=show_future_payments,
	)


@frappe.whitelist()
def get_payables(company, as_of_date, supplier=None, show_future_payments=0):
	"""AP aging summary — one row per supplier with a non-zero net balance.

	Sourced from ERPNext's own Accounts Payable report engine — see get_receivables for why.
	"""
	frappe.has_permission("Purchase Invoice", "read", throw=True)
	return _get_party_balances(
		party_type="Supplier",
		company=company,
		as_of_date=as_of_date,
		party=supplier,
		show_future_payments=show_future_payments,
	)


@frappe.whitelist()
def get_payables_detail(supplier, company, as_of_date, show_future_payments=0):
	"""Individual outstanding PI rows for accordion drill-down."""
	frappe.has_permission("Purchase Invoice", "read", throw=True)
	return _get_party_balance_detail(
		party_type="Supplier",
		company=company,
		as_of_date=as_of_date,
		party=supplier,
		show_future_payments=show_future_payments,
	)


@frappe.whitelist()
def get_item_prices(item_code):
	"""Returns all Item Price records (selling + buying) for an item."""
	ip = frappe.qb.DocType("Item Price")
	rows = (
		frappe.qb.from_(ip)
		.select(
			ip.name,
			ip.price_list,
			ip.selling,
			ip.buying,
			ip.price_list_rate,
			ip.currency,
			ip.valid_from,
			ip.valid_upto,
		)
		.where(ip.item_code == item_code)
		.where((ip.selling == 1) | (ip.buying == 1))
		.orderby(ip.selling, order=frappe.qb.desc)
		.orderby(ip.price_list)
		.run(as_dict=True)
	)
	for r in rows:
		r["price_list_rate"] = flt(r["price_list_rate"], 2)
		r["type"] = "Selling" if r.get("selling") else "Buying"
	return rows


@frappe.whitelist()
def update_item_price(item_code, price_list, rate):
	"""Upsert an Item Price record. Requires Item Price write permission."""
	frappe.has_permission("Item Price", "write", throw=True)
	if flt(rate, 2) <= 0:
		frappe.throw(_("Rate must be greater than zero"))

	existing = frappe.db.get_value(
		"Item Price",
		{"item_code": item_code, "price_list": price_list},
		"name",
	)
	if existing:
		doc = frappe.get_doc("Item Price", existing)
		doc.price_list_rate = flt(rate, 2)
		doc.save()
	else:
		pl = frappe.db.get_value("Price List", price_list, ["selling", "buying"], as_dict=True) or {}
		doc = frappe.get_doc({
			"doctype": "Item Price",
			"item_code": item_code,
			"price_list": price_list,
			"price_list_rate": flt(rate, 2),
			"selling": pl.get("selling", 0),
			"buying": pl.get("buying", 0),
		})
		doc.insert()

	frappe.db.commit()
	return {"name": doc.name, "price_list_rate": doc.price_list_rate}


@frappe.whitelist()
def get_warehouse_stock(item_code, company):
	"""Return stock qty per enabled, non-group warehouse for the given item and company."""
	Wh = frappe.qb.DocType("Warehouse")
	Bn = frappe.qb.DocType("Bin")
	rows = (
		frappe.qb.from_(Bn)
		.inner_join(Wh).on(Bn.warehouse == Wh.name)
		.select(Wh.name.as_("warehouse"), Wh.warehouse_name, Bn.actual_qty)
		.where(Bn.item_code == item_code)
		.where(Wh.company == company)
		.where(Wh.disabled == 0)
		.where(Wh.is_group == 0)
		.where(Bn.actual_qty > 0)
		.orderby(Bn.actual_qty, order=frappe.qb.desc)
		.run(as_dict=True)
	)
	return rows


@frappe.whitelist()
def get_party_details(party_type, party, company=None, as_of_date=None, show_future_payments=0):
	"""Return full profile: contacts, address, account stats, and unallocated advances.

	`stats.total_unpaid` is sourced from the same AR/AP report engine as the Receivables/Payables
	grid (_get_party_balances) so this dialog's "Total Outstanding" always matches the grid row it
	was opened from, for the same as_of_date/show_future_payments — see the two figures never
	being independently derived.
	"""
	from pypika import Case
	from frappe.utils import getdate, nowdate

	is_customer = party_type.lower() == "customer"
	doctype = "Customer" if is_customer else "Supplier"

	# Core doc fields
	doc = frappe.db.get_value(
		doctype, party,
		["name", "email_id", "mobile_no", "payment_terms", "tax_id"],
		as_dict=True,
	) or {}

	# Primary address
	address = None
	addr_name = frappe.db.get_value(
		"Dynamic Link",
		{"link_doctype": doctype, "link_name": party, "parenttype": "Address"},
		"parent",
	)
	if addr_name:
		address = frappe.db.get_value(
			"Address", addr_name,
			["address_line1", "address_line2", "city", "state", "country", "pincode"],
			as_dict=True,
		)

	# Contacts (up to 5, primary first)
	contact_links = frappe.db.get_all(
		"Dynamic Link",
		filters={"link_doctype": doctype, "link_name": party, "parenttype": "Contact"},
		fields=["parent"],
		limit=5,
	)
	contacts = []
	for cl in contact_links:
		c = frappe.db.get_value(
			"Contact", cl.parent,
			["first_name", "last_name", "email_id", "phone", "mobile_no", "is_primary_contact"],
			as_dict=True,
		)
		if c:
			contacts.append(c)
	contacts.sort(key=lambda x: x.get("is_primary_contact") or 0, reverse=True)

	# Account stats
	today_dt = getdate(nowdate())
	year_start = str(today_dt.replace(month=1, day=1))
	stats = {"annual_billing": 0.0, "lifetime_billing": 0.0, "total_unpaid": 0.0, "last_transaction": None}

	if is_customer:
		si = frappe.qb.DocType("Sales Invoice")
		sq = (
			frappe.qb.from_(si)
			.select(
				fn.Sum(si.grand_total).as_("lifetime_billing"),
				fn.Sum(si.outstanding_amount).as_("total_unpaid"),
				fn.Max(si.posting_date).as_("last_transaction"),
				fn.Sum(Case().when(si.posting_date >= year_start, si.grand_total).else_(0)).as_("annual_billing"),
			)
			.where(si.docstatus == 1)
			.where(si.customer == party)
		)
		if company:
			sq = sq.where(si.company == company)
	else:
		pi = frappe.qb.DocType("Purchase Invoice")
		sq = (
			frappe.qb.from_(pi)
			.select(
				fn.Sum(pi.grand_total).as_("lifetime_billing"),
				fn.Sum(pi.outstanding_amount).as_("total_unpaid"),
				fn.Max(pi.posting_date).as_("last_transaction"),
				fn.Sum(Case().when(pi.posting_date >= year_start, pi.grand_total).else_(0)).as_("annual_billing"),
			)
			.where(pi.docstatus == 1)
			.where(pi.supplier == party)
		)
		if company:
			sq = sq.where(pi.company == company)

	rows = sq.run(as_dict=True)
	if rows and rows[0].get("lifetime_billing") is not None:
		stats = rows[0]
		stats["annual_billing"] = flt(stats.get("annual_billing") or 0, 2)
		stats["lifetime_billing"] = flt(stats.get("lifetime_billing") or 0, 2)
		stats["total_unpaid"] = flt(stats.get("total_unpaid") or 0, 2)

	if company:
		balance_rows = _get_party_balances(
			party_type=doctype,
			company=company,
			as_of_date=as_of_date or nowdate(),
			party=party,
			show_future_payments=show_future_payments,
		)
		stats["total_unpaid"] = flt(balance_rows[0]["outstanding"], 2) if balance_rows else 0.0

	# Credit limit (customer only, for the given company)
	credit_limit = None
	if is_customer and company:
		credit_limit = frappe.db.get_value(
			"Customer Credit Limit",
			{"parent": party, "company": company},
			"credit_limit",
		)
		if credit_limit is not None:
			credit_limit = flt(credit_limit, 2)

	# Unallocated payment entries
	pay_type = "Receive" if is_customer else "Pay"
	pe = frappe.qb.DocType("Payment Entry")
	adv_rows = (
		frappe.qb.from_(pe)
		.select(pe.name, pe.posting_date, pe.paid_amount, pe.unallocated_amount)
		.where(pe.docstatus == 1)
		.where(pe.payment_type == pay_type)
		.where(pe.party_type == doctype)
		.where(pe.party == party)
		.where(pe.unallocated_amount > 0)
		.orderby(pe.posting_date, order=frappe.qb.desc)
		.run(as_dict=True)
	)
	for r in adv_rows:
		r["paid_amount"] = flt(r["paid_amount"], 2)
		r["unallocated_amount"] = flt(r["unallocated_amount"], 2)

	unallocated_total = flt(sum(r["unallocated_amount"] for r in adv_rows), 2)

	primary_email = (
		next((c.get("email_id") for c in contacts if c.get("email_id")), None)
		or doc.get("email_id")
		or ""
	)

	return {
		"doc": doc,
		"address": address,
		"contacts": contacts,
		"stats": stats,
		"credit_limit": credit_limit,
		"unallocated_payments": adv_rows,
		"unallocated_total": unallocated_total,
		"primary_email": primary_email,
	}


@frappe.whitelist()
def send_statement_email(party_type, party, company, as_of_date, html_content, recipient_email, cc="", bcc=""):
	"""Send a transaction list statement as HTML email in the background.

	`html_content` is client-supplied, so this method is gated on read access to the party it claims
	to be about. Without the gate any logged-in user could mail arbitrary HTML to any address from
	the site's mail server.
	"""
	frappe.has_permission(
		"Customer" if party_type == "customer" else "Supplier", "read", party, throw=True
	)

	def split_emails(s):
		return [e.strip() for e in s.replace(";", ",").split(",") if e.strip()] if s else []

	frappe.sendmail(
		recipients=[recipient_email],
		cc=split_emails(cc),
		bcc=split_emails(bcc),
		subject=_("Transaction List — {0} as of {1}").format(party, as_of_date),
		message=html_content,
		now=False,
	)
	return True


# ── Private helpers ──────────────────────────────────────────────────────────

def _get_items_stock_map(item_codes, company):
	"""Return {item_code: total_actual_qty} across all non-group warehouses for the company."""
	if not item_codes:
		return {}
	Wh = frappe.qb.DocType("Warehouse")
	Bn = frappe.qb.DocType("Bin")
	rows = (
		frappe.qb.from_(Bn)
		.inner_join(Wh).on(Bn.warehouse == Wh.name)
		.select(Bn.item_code, fn.Sum(Bn.actual_qty).as_("actual_qty"))
		.where(Bn.item_code.isin(item_codes))
		.where(Wh.company == company)
		.where(Wh.disabled == 0)
		.where(Wh.is_group == 0)
		.groupby(Bn.item_code)
		.run(as_dict=True)
	)
	return {r["item_code"]: flt(r["actual_qty"], 2) for r in rows}


def _get_customer_last_rate_map(customer, company, item_codes, from_date=None, to_date=None):
	"""Return {item_code: base_rate} from the most recent SI line per item."""
	if not item_codes:
		return {}
	sii = frappe.qb.DocType("Sales Invoice Item")
	si = frappe.qb.DocType("Sales Invoice")
	q = (
		frappe.qb.from_(sii)
		.inner_join(si).on(sii.parent == si.name)
		.select(sii.item_code, sii.base_rate, si.posting_date)
		.where(si.docstatus == 1)
		.where(si.customer == customer)
		.where(si.company == company)
		.where(sii.item_code.isin(item_codes))
		.orderby(si.posting_date, order=frappe.qb.desc)
	)
	if from_date:
		q = q.where(si.posting_date >= from_date)
	if to_date:
		q = q.where(si.posting_date <= to_date)
	result = {}
	for rec in q.run(as_dict=True):
		if rec["item_code"] not in result:
			result[rec["item_code"]] = flt(rec["base_rate"], 2)
	return result


def _get_supplier_last_rate_map(supplier, company, item_codes, source="pi", from_date=None, to_date=None):
	"""Return {item_code: valuation_rate} from the most recent PI/PR line per item."""
	if not item_codes:
		return {}
	if source == "pi":
		pii = frappe.qb.DocType("Purchase Invoice Item")
		pi = frappe.qb.DocType("Purchase Invoice")
		q = (
			frappe.qb.from_(pii)
			.inner_join(pi).on(pii.parent == pi.name)
			.select(pii.item_code, pii.valuation_rate, pi.posting_date)
			.where(pi.docstatus == 1)
			.where(pi.update_stock == 1)
			.where(pi.supplier == supplier)
			.where(pi.company == company)
			.where(pii.item_code.isin(item_codes))
			.orderby(pi.posting_date, order=frappe.qb.desc)
		)
		if from_date:
			q = q.where(pi.posting_date >= from_date)
		if to_date:
			q = q.where(pi.posting_date <= to_date)
	else:
		pri = frappe.qb.DocType("Purchase Receipt Item")
		pr = frappe.qb.DocType("Purchase Receipt")
		q = (
			frappe.qb.from_(pri)
			.inner_join(pr).on(pri.parent == pr.name)
			.select(pri.item_code, pri.valuation_rate, pr.posting_date)
			.where(pr.docstatus == 1)
			.where(pr.supplier == supplier)
			.where(pr.company == company)
			.where(pri.item_code.isin(item_codes))
			.orderby(pr.posting_date, order=frappe.qb.desc)
		)
		if from_date:
			q = q.where(pr.posting_date >= from_date)
		if to_date:
			q = q.where(pr.posting_date <= to_date)
	result = {}
	for rec in q.run(as_dict=True):
		if rec["item_code"] not in result:
			result[rec["item_code"]] = flt(rec["valuation_rate"], 2)
	return result


def _get_report_execute(party_type):
	"""Return ERPNext's Accounts Receivable/Payable report `execute` function for party_type."""
	if party_type == "Customer":
		from erpnext.accounts.report.accounts_receivable.accounts_receivable import execute as ar_execute

		return ar_execute
	from erpnext.accounts.report.accounts_payable.accounts_payable import execute as ap_execute

	return ap_execute


def _get_party_balances(party_type, company, as_of_date, party=None, show_future_payments=0):
	"""Group ERPNext's Accounts Receivable/Payable report rows into one entry per party.

	Delegating to erpnext's own report engine (Payment Ledger Entry based) instead of a bespoke
	Sales/Purchase Invoice query means credit notes/returns net into the total automatically, and
	"outstanding" stays as-of-date consistent: a future-dated payment only nets in when
	show_future_payments is on, exactly like the standard report and the PSOA statement print
	formats.
	"""
	from collections import defaultdict

	party_field = "customer" if party_type == "Customer" else "supplier"
	group_field = "customer_group" if party_type == "Customer" else "supplier_group"

	filters = {
		"company": company,
		"report_date": as_of_date,
		"party_type": party_type,
		"show_future_payments": cint(show_future_payments),
	}
	if party:
		filters["party"] = [party]

	_columns, data, *_rest = _get_report_execute(party_type)(filters)

	agg = defaultdict(lambda: {
		party_field: "", group_field: "",
		"total_invoiced": 0.0, "total_paid": 0.0, "outstanding": 0.0,
		"bucket_0_30": 0.0, "bucket_31_60": 0.0, "bucket_61_90": 0.0, "bucket_90_plus": 0.0,
		"last_payment": None, "unallocated_advance": 0.0, "future_payments": 0.0,
	})
	for r in data or []:
		name = r.get("party")
		if not name:
			continue
		a = agg[name]
		a[party_field] = name
		a[group_field] = r.get(group_field) or ""
		a["total_invoiced"] = flt(a["total_invoiced"] + flt(r.get("invoiced") or 0), 2)
		a["total_paid"] = flt(a["total_paid"] + flt(r.get("paid") or 0), 2)
		a["outstanding"] = flt(a["outstanding"] + flt(r.get("outstanding") or 0), 2)
		a["bucket_0_30"] = flt(a["bucket_0_30"] + flt(r.get("range0") or 0) + flt(r.get("range1") or 0), 2)
		a["bucket_31_60"] = flt(a["bucket_31_60"] + flt(r.get("range2") or 0), 2)
		a["bucket_61_90"] = flt(a["bucket_61_90"] + flt(r.get("range3") or 0), 2)
		a["bucket_90_plus"] = flt(a["bucket_90_plus"] + flt(r.get("range4") or 0) + flt(r.get("range5") or 0), 2)
		a["future_payments"] = flt(a["future_payments"] + flt(r.get("future_amount") or 0), 2)

		if r.get("voucher_type") in ("Payment Entry", "Journal Entry"):
			posting_date = getdate(r["posting_date"])
			if not a["last_payment"] or posting_date > getdate(a["last_payment"]):
				a["last_payment"] = posting_date
			outstanding = flt(r.get("outstanding") or 0)
			if outstanding < 0:
				a["unallocated_advance"] = flt(a["unallocated_advance"] + -outstanding, 2)

	result = [a for a in agg.values() if a["outstanding"] or a["unallocated_advance"]]
	result.sort(key=lambda x: x["outstanding"], reverse=True)
	return result


def _get_party_balance_detail(party_type, company, as_of_date, party, show_future_payments=0):
	"""Per-invoice outstanding rows for a single party's accordion drill-down.

	Sourced from the same AR/AP report rows as _get_party_balances (see there for why),
	filtered down to invoice vouchers only.
	"""
	voucher_doctype = "Sales Invoice" if party_type == "Customer" else "Purchase Invoice"

	as_of = getdate(as_of_date)
	filters = {
		"company": company,
		"report_date": as_of,
		"party_type": party_type,
		"party": [party],
		"show_future_payments": cint(show_future_payments),
	}
	_columns, data, *_rest = _get_report_execute(party_type)(filters)

	invoice_rows = [
		r for r in (data or [])
		if r.get("voucher_type") == voucher_doctype and flt(r.get("outstanding") or 0) > 0
	]
	voucher_nos = [r["voucher_no"] for r in invoice_rows]
	statuses = {}
	if voucher_nos:
		statuses = {
			d.name: d.status
			for d in frappe.db.get_all(
				voucher_doctype, filters={"name": ["in", voucher_nos]}, fields=["name", "status"]
			)
		}

	rows = []
	for r in invoice_rows:
		due = getdate(r["due_date"]) if r.get("due_date") else getdate(r["posting_date"])
		rows.append({
			"date": r["posting_date"],
			"voucher_no": r["voucher_no"],
			"grand_total": flt(r.get("invoiced") or 0, 2),
			"paid": flt(flt(r.get("invoiced") or 0) - flt(r.get("outstanding") or 0), 2),
			"outstanding_amount": flt(r.get("outstanding") or 0, 2),
			"due_date": r.get("due_date"),
			"status": statuses.get(r["voucher_no"]),
			"days_overdue": max(0, (as_of - due).days),
			"future_amount": flt(r.get("future_amount") or 0, 2),
		})
	rows.sort(key=lambda r: r["due_date"] or r["date"])
	return rows


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
	cust = frappe.qb.DocType("Customer")

	query = (
		frappe.qb.from_(sii)
		.inner_join(si).on(sii.parent == si.name)
		.left_join(cust).on(si.customer == cust.name)  # LEFT keeps invoices whose Customer was deleted
		.select(
			si.posting_date.as_("date"),
			sii.parent.as_("voucher_no"),
			si.customer,
			cust.customer_group,
			si.selling_price_list,
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
