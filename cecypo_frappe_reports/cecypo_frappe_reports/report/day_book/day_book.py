# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from pypika import Case, CustomFunction
from pypika import functions as fn

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
		money = {"fieldtype": "Float", "precision": 2, "width": 130}
		return [
			{"label": date_label, "fieldname": "date", "fieldtype": "Date", "width": 100},
			{
				"label": _("Warehouse"),
				"fieldname": "warehouse",
				"fieldtype": "Data",  # not Link: "Multiple" is not a warehouse
				"width": 150,
			},
			{"label": _("Transaction"), "fieldname": "transaction", "fieldtype": "Data", "width": 170},
			{"label": _("Count"), "fieldname": "count", "fieldtype": "Int", "width": 70},
			{"label": _("Value"), "fieldname": "value", **money},
			{"label": _("Money In"), "fieldname": "money_in", **money},
			{"label": _("Money Out"), "fieldname": "money_out", **money},
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

	total_debit = 0.0
	total_credit = 0.0
	for row in data:
		row["debit"] = flt(row["debit"], 2)
		row["credit"] = flt(row["credit"], 2)
		total_debit += row["debit"]
		total_credit += row["credit"]

	if data:
		data.append(
			{
				"date": None,
				"voucher_type": _("Total"),
				"voucher_no": None,
				"party_type": None,
				"party": None,
				"account": None,
				"debit": flt(total_debit, 2),
				"credit": flt(total_credit, 2),
				"against": None,
				"remarks": None,
				"cost_center": None,
				"bold": 1,
			}
		)

	return data


# Sales first, then money received/paid, purchases, then journals and anything else (by name).
TRANSACTION_ORDER = [
	"Sales",
	"Sales Returns",
	"Received",
	"Paid Out",
	"Internal Transfer",
	"Purchases",
	"Purchase Returns",
	"Delivery Note",
	"Delivery Note Returns",
	"Purchase Receipt",
	"Purchase Receipt Returns",
]
# Per voucher type: the fields that say which transaction it is and what it is worth.
DOC_FIELDS = {
	"Sales Invoice": ["is_return", "base_grand_total"],
	"Purchase Invoice": ["is_return", "base_grand_total"],
	"Delivery Note": ["is_return", "base_grand_total"],
	"Purchase Receipt": ["is_return", "base_grand_total"],
	"Payment Entry": ["payment_type", "base_paid_amount", "base_received_amount"],
	"Journal Entry": ["voucher_type", "total_debit"],
}
RETURNABLE = {
	"Sales Invoice": ("Sales", "Sales Returns"),
	"Purchase Invoice": ("Purchases", "Purchase Returns"),
	"Delivery Note": ("Delivery Note", "Delivery Note Returns"),
	"Purchase Receipt": ("Purchase Receipt", "Purchase Receipt Returns"),
}
PAYMENT_TYPES = {"Receive": "Received", "Pay": "Paid Out", "Internal Transfer": "Internal Transfer"}


def transaction_of(voucher_type, doc):
	"""The summary row a voucher falls in."""
	doc = doc or {}
	if voucher_type in RETURNABLE:
		return RETURNABLE[voucher_type][1 if doc.get("is_return") else 0]
	if voucher_type == "Payment Entry":
		return PAYMENT_TYPES.get(doc.get("payment_type"), voucher_type)
	if voucher_type == "Journal Entry":
		return doc.get("voucher_type") or voucher_type
	return voucher_type


def _value_of(voucher_type, doc, gl_debit):
	"""The document's own total in company currency; for types without one, its GL debits."""
	if not doc:
		return flt(gl_debit)
	if voucher_type in RETURNABLE:
		return flt(doc.get("base_grand_total"))
	if voucher_type == "Payment Entry":
		field = "base_received_amount" if doc.get("payment_type") == "Receive" else "base_paid_amount"
		return flt(doc.get(field))
	if voucher_type == "Journal Entry":
		return flt(doc.get("total_debit"))
	return flt(gl_debit)


def warehouse_of(stock_warehouses, till_warehouse):
	"""Where a voucher's stock moved; failing that, the klik till it was taken on; else blank."""
	if len(stock_warehouses) > 1:
		return _("Multiple")
	if stock_warehouses:
		return next(iter(stock_warehouses))
	return till_warehouse or None


def summarize(vouchers):
	"""One row per (date, warehouse, transaction) from per-voucher rows, then a total row. The total
	has no Value: sales plus payouts adds up to nothing meaningful."""
	groups = {}
	for v in vouchers:
		g = groups.setdefault(
			(v["date"], v.get("warehouse"), v["transaction"]),
			{
				"date": v["date"],
				"warehouse": v.get("warehouse"),
				"transaction": v["transaction"],
				"count": 0,
				"value": 0.0,
				"money_in": 0.0,
				"money_out": 0.0,
			},
		)
		g["count"] += 1
		for k in ("value", "money_in", "money_out"):
			g[k] += flt(v[k])
	order = {t: i for i, t in enumerate(TRANSACTION_ORDER)}
	rows = sorted(
		groups.values(),
		key=lambda r: (
			r["date"] or "",
			r["warehouse"] is None,  # payments and journals off any till go last
			r["warehouse"] or "",
			order.get(r["transaction"], len(order)),
			r["transaction"],
		),
	)
	for r in rows:
		for k in ("value", "money_in", "money_out"):
			r[k] = flt(r[k], 2)
	if rows:
		rows.append(
			{
				"date": None,
				"transaction": _("Total"),
				"count": sum(r["count"] for r in rows),
				"value": None,
				"money_in": flt(sum(r["money_in"] for r in rows), 2),
				"money_out": flt(sum(r["money_out"] for r in rows), 2),
				"bold": 1,
			}
		)
	return rows


def get_summarized_data(filters):
	"""Vouchers in scope from the GL (so every filter still applies), each valued from its own
	document; Money In/Out is its debit/credit on Cash and Bank accounts."""
	gle = frappe.qb.DocType("GL Entry")
	acc = frappe.qb.DocType("Account")
	date_field = _get_date_field(gle, filters)
	cash = acc.account_type.isin(["Cash", "Bank"])

	query = (
		frappe.qb.from_(gle)
		.left_join(acc)
		.on(acc.name == gle.account)
		.select(
			date_field.as_("date"),
			gle.voucher_type,
			gle.voucher_no,
			fn.Sum(gle.debit).as_("gl_debit"),
			fn.Sum(Case().when(cash, gle.debit).else_(0)).as_("money_in"),
			fn.Sum(Case().when(cash, gle.credit).else_(0)).as_("money_out"),
		)
		.where(gle.is_cancelled == 0)
		.groupby(date_field, gle.voucher_type, gle.voucher_no)
	)
	vouchers = _apply_common_filters(query, gle, filters).run(as_dict=True)

	names = {}
	for v in vouchers:
		if v.voucher_type in DOC_FIELDS:
			names.setdefault(v.voucher_type, set()).add(v.voucher_no)
	docs = {}
	for doctype, voucher_nos in names.items():
		fields = ["name", *DOC_FIELDS[doctype]]
		if doctype in SHIFT_LINKED and frappe.db.has_column(doctype, "custom_pos_opening_entry"):
			fields.append("custom_pos_opening_entry")  # klik_pos: the shift it was taken on
		for d in frappe.get_all(
			doctype, filters={"name": ("in", list(voucher_nos))}, fields=fields, ignore_permissions=True
		):
			docs[(doctype, d.name)] = d

	stock = _stock_warehouses({v.voucher_no for v in vouchers})
	tills = _till_warehouses({d.get("custom_pos_opening_entry") for d in docs.values()} - {None, ""})
	for v in vouchers:
		doc = docs.get((v.voucher_type, v.voucher_no))
		v.transaction = transaction_of(v.voucher_type, doc)
		v.value = _value_of(v.voucher_type, doc, v.gl_debit)
		v.warehouse = warehouse_of(
			stock.get((v.voucher_type, v.voucher_no), set()),
			tills.get((doc or {}).get("custom_pos_opening_entry")),
		)
	return summarize(vouchers)


SHIFT_LINKED = ("Sales Invoice", "Payment Entry", "Journal Entry")


def _stock_warehouses(voucher_nos):
	"""(voucher_type, voucher_no) -> warehouses its stock moved through."""
	out = {}
	if not voucher_nos:
		return out
	sle = frappe.qb.DocType("Stock Ledger Entry")
	for r in (
		frappe.qb.from_(sle)
		.select(sle.voucher_type, sle.voucher_no, sle.warehouse)
		.distinct()
		.where(sle.voucher_no.isin(list(voucher_nos)))
		.where(sle.is_cancelled == 0)
		.run(as_dict=True)
	):
		out.setdefault((r.voucher_type, r.voucher_no), set()).add(r.warehouse)
	return out


def _till_warehouses(opening_entries):
	"""klik_pos shift (POS Opening Entry) -> its till's (POS Profile) warehouse."""
	if not opening_entries:
		return {}
	poe = frappe.qb.DocType("POS Opening Entry")
	pp = frappe.qb.DocType("POS Profile")
	rows = (
		frappe.qb.from_(poe)
		.join(pp)
		.on(pp.name == poe.pos_profile)
		.select(poe.name, pp.warehouse)
		.where(poe.name.isin(list(opening_entries)))
		.run()
	)
	return dict(rows)


def get_report_summary(data, is_summarized=False):
	# Exclude the totals row appended at the bottom
	rows = [d for d in data if not d.get("bold")]
	if not rows:
		return []

	if is_summarized:

		def value_of(transaction):
			return flt(sum(flt(d["value"]) for d in rows if d["transaction"] == transaction), 2)

		money_in = flt(sum(d["money_in"] for d in rows), 2)
		money_out = flt(sum(d["money_out"] for d in rows), 2)
		net = flt(money_in - money_out, 2)
		return [
			{"value": value_of("Sales"), "label": _("Sales"), "datatype": "Float", "indicator": "Blue"},
			{
				"value": value_of("Sales Returns"),
				"label": _("Returns"),
				"datatype": "Float",
				"indicator": "Orange",
			},
			{"value": money_in, "label": _("Money In"), "datatype": "Float", "indicator": "Green"},
			{"value": money_out, "label": _("Money Out"), "datatype": "Float", "indicator": "Red"},
			{
				"value": net,
				"label": _("Net Cash"),
				"datatype": "Float",
				"indicator": "Green" if net >= 0 else "Red",
			},
		]

	total_debit = sum(flt(d.get("debit")) for d in rows)
	total_credit = sum(flt(d.get("credit")) for d in rows)
	net_balance = flt(total_debit - total_credit, 2)
	total_count = len(rows)

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
