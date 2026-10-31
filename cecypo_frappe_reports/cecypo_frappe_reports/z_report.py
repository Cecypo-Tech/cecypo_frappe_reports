"""Z-report: the figures for one shift, or for one branch (warehouse) on one day.

One builder, rendered later as a thermal slip and an A4 page, so both show the same numbers.
The drawer ("cash_position") is counted the way klik_pos files it at shift close
(klik_pos.api.pos_entry.expected_by_mode): only money that passed through a till.
klik_pos is a soft dependency: its custom fields are checked with has_column.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_fullname, getdate, now_datetime

NO_MODE = "(no mode)"
# An invoice's branch: its till's warehouse, else the desk invoice's set_warehouse; a return
# with neither (desk "Make Return" does not copy set_warehouse) takes its original's by the same rule.
# Every query using BRANCH_SQL aliases the invoice `si` and includes BRANCH_JOINS.
BRANCH_SQL = (
	"COALESCE(NULLIF(pp.warehouse, ''), NULLIF(si.set_warehouse, ''),"
	" NULLIF(opp.warehouse, ''), NULLIF(osi.set_warehouse, ''))"
)
BRANCH_JOINS = """LEFT JOIN `tabPOS Profile` pp ON pp.name = si.pos_profile
	LEFT JOIN `tabSales Invoice` osi ON si.is_return = 1 AND osi.name = si.return_against
	LEFT JOIN `tabPOS Profile` opp ON opp.name = osi.pos_profile"""


@frappe.whitelist()
def get_z_report(warehouse: str, date: str) -> dict:
	if not frappe.has_permission("Sales Invoice", "report"):
		frappe.throw(_("Not permitted to view sales reports."), frappe.PermissionError)
	if not frappe.has_permission("Warehouse", doc=warehouse):
		frappe.throw(_("Not permitted for warehouse {0}.").format(warehouse), frappe.PermissionError)
	return build_z_report(warehouse=warehouse, date=date)


def build_z_report(
	*, opening_entry: str | None = None, warehouse: str | None = None, date: str | None = None
) -> dict:
	if opening_entry and not (warehouse or date):
		scope = _shift_scope(opening_entry)
	elif warehouse and date and not opening_entry:
		scope = _day_scope(warehouse, str(getdate(date)))
	else:
		frappe.throw(_("Pass a POS Opening Entry, or a warehouse and a date."), frappe.ValidationError)
	return _build(scope)


def _has(doctype, column):
	return frappe.db.has_column(doctype, column)


# ---- scopes ------------------------------------------------------------------------------


def _shift_scope(name):
	opening = frappe.db.get_value(
		"POS Opening Entry", name, ["name", "company", "pos_profile", "period_start_date"], as_dict=True
	)
	if not opening:
		frappe.throw(_("POS Opening Entry {0} not found.").format(name), frappe.DoesNotExistError)
	closing = frappe.db.get_value(
		"POS Closing Entry",
		{"pos_opening_entry": name, "docstatus": 1},
		["name", "period_end_date"],
		as_dict=True,
	)
	stamped = _has("Sales Invoice", "custom_pos_opening_entry")
	return {
		"scope": "shift",
		"company": opening.company,
		"warehouse": frappe.db.get_value("POS Profile", opening.pos_profile, "warehouse"),
		"report_no": closing.name if closing else name,
		"period_start": str(opening.period_start_date),
		"period_end": str(closing.period_end_date if closing else now_datetime()),
		"invoices": _invoices("si.custom_pos_opening_entry = %(shift)s", {"shift": name}) if stamped else [],
		"payment_entries": _payment_entries("pe.custom_pos_opening_entry = %(shift)s", {"shift": name})
		if _has("Payment Entry", "custom_pos_opening_entry")
		else [],
		"expenses": _shift_expenses([name]),
		"floats": _floats([name]),
		"counted": _counted([closing.name] if closing else []),
		"excluded": 0,
		"excluded_invoices": 0,
	}


def _day_scope(warehouse, date):
	company = frappe.db.get_value("Warehouse", warehouse, "company")
	if not company:
		frappe.throw(_("Warehouse {0} not found.").format(warehouse), frappe.DoesNotExistError)
	profiles = frappe.get_all("POS Profile", {"warehouse": warehouse}, pluck="name")
	shifts = profiles and frappe.get_all(
		"POS Opening Entry",
		{"docstatus": 1, "posting_date": date, "pos_profile": ("in", profiles)},
		pluck="name",
	)
	closings = profiles and frappe.get_all(
		"POS Closing Entry",
		filters=[
			["docstatus", "=", 1],
			["pos_profile", "in", profiles],
			["period_end_date", ">=", date],
			["period_end_date", "<", add_days(date, 1)],
		],
		pluck="name",
	)
	params = {"date": date, "company": company, "warehouse": warehouse}
	day = "si.posting_date = %(date)s AND si.company = %(company)s"
	invoices = _invoices(f"{day} AND {BRANCH_SQL} = %(warehouse)s", params)
	# Invoices with no branch at all (no till warehouse, no set_warehouse): counted, not lost.
	excluded_invoices = frappe.db.sql(
		f"""SELECT COUNT(*) FROM `tabSales Invoice` si
		{BRANCH_JOINS}
		WHERE si.docstatus = 1 AND {day} AND {BRANCH_SQL} IS NULL""",
		params,
	)[0][0]
	entries, excluded = [], 0
	for pe in _payment_entries("pe.posting_date = %(date)s AND pe.company = %(company)s", params):
		# Branch: the shift's till, else the invoices it is allocated to, else none (left out
		# and counted). A shift-stamped entry belongs wholly to its till's branch.
		if pe.shift:
			if not pe.shift_warehouse:
				excluded += 1
			elif pe.shift_warehouse == warehouse:
				entries.append(pe)
			continue
		branched = [r for r in pe.refs if r.warehouse]
		if not branched:
			excluded += 1
		elif any(r.warehouse == warehouse for r in branched):
			# Allocations to other branches' invoices are theirs; the unallocated remainder
			# goes to the branch of the first allocated invoice, so exactly one branch has it.
			unallocated = flt(pe.paid_amount) - sum(flt(r.allocated_amount) for r in pe.refs)
			pe.not_ours = sum(flt(r.allocated_amount) for r in pe.refs if r.warehouse != warehouse)
			if branched[0].warehouse != warehouse:
				pe.not_ours += unallocated
			entries.append(pe)
	return {
		"scope": "day",
		"company": company,
		"warehouse": warehouse,
		"report_no": f"{warehouse} {date}",
		"period_start": f"{date} 00:00:00",
		"period_end": f"{date} 23:59:59",
		"invoices": invoices,
		"payment_entries": entries,
		"expenses": _day_expenses(warehouse, date),
		"floats": _floats(shifts or []),
		"counted": _counted(closings or []),
		"excluded": excluded,
		"excluded_invoices": excluded_invoices,
	}


# ---- queries -----------------------------------------------------------------------------


def _invoices(where, params):
	shift = "si.custom_pos_opening_entry" if _has("Sales Invoice", "custom_pos_opening_entry") else "NULL"
	return frappe.db.sql(
		f"""
		SELECT si.name, si.owner, si.is_return, si.posting_date, si.posting_time, si.customer_name,
			si.grand_total, si.rounded_total, si.outstanding_amount, si.net_total,
			si.total_taxes_and_charges, si.discount_amount, si.change_amount,
			si.account_for_change_amount, NULLIF({shift}, '') AS shift
		FROM `tabSales Invoice` si
		{BRANCH_JOINS}
		WHERE si.docstatus = 1 AND {where}
		ORDER BY si.posting_date, si.posting_time, si.creation
		""",
		params,
		as_dict=True,
	)


def _payment_entries(where, params):
	"""Submitted customer receipts (Receive) and refunds (Pay), each with `refs` (its Sales
	Invoice allocations, in row order, and their branch) and, when stamped with a shift, that
	shift's till warehouse."""
	if _has("Payment Entry", "custom_pos_opening_entry"):
		shift = "NULLIF(pe.custom_pos_opening_entry, '')"
		join = """LEFT JOIN `tabPOS Opening Entry` poe ON poe.name = pe.custom_pos_opening_entry
			LEFT JOIN `tabPOS Profile` spp ON spp.name = poe.pos_profile"""
		shift_wh = "spp.warehouse"
	else:
		shift, join, shift_wh = "NULL", "", "NULL"
	entries = frappe.db.sql(
		f"""
		SELECT pe.name, pe.owner, pe.payment_type, pe.mode_of_payment, pe.paid_amount,
			{shift} AS shift, {shift_wh} AS shift_warehouse
		FROM `tabPayment Entry` pe {join}
		WHERE pe.payment_type IN ('Receive', 'Pay') AND pe.party_type = 'Customer'
			AND pe.docstatus = 1 AND {where}
		ORDER BY pe.posting_date, pe.creation
		""",
		params,
		as_dict=True,
	)
	refs = defaultdict(list)
	if entries:
		for r in frappe.db.sql(
			f"""
			SELECT per.parent, per.reference_name, ABS(per.allocated_amount) AS allocated_amount,
				{BRANCH_SQL} AS warehouse
			FROM `tabPayment Entry Reference` per
			JOIN `tabSales Invoice` si ON si.name = per.reference_name
			{BRANCH_JOINS}
			WHERE per.reference_doctype = 'Sales Invoice' AND per.parent IN %(names)s
			ORDER BY per.parent, per.idx
			""",
			{"names": tuple(e.name for e in entries)},
			as_dict=True,
		):
			refs[r.parent].append(r)
	for e in entries:
		e.refs = refs[e.name]
	return entries


def _shift_expenses(shifts):
	try:
		from klik_pos.api.expense import expenses_for_shifts
	except ImportError:
		return []
	return expenses_for_shifts(shifts)


def _day_expenses(warehouse, date):
	"""klik expense Journal Entries at the branch that day, drafts included, in the shape
	klik_pos.api.expense.expenses_for_shifts returns."""
	je = "Journal Entry"
	if not all(_has(je, c) for c in ("custom_warehouse", "custom_expense_type", "custom_pos_profile")):
		return []
	out = []
	for r in frappe.get_all(
		je,
		filters={
			"custom_warehouse": warehouse,
			"posting_date": date,
			"docstatus": ("<", 2),
			"custom_expense_type": ("is", "set"),
		},
		fields=[
			"name",
			"custom_expense_type",
			"user_remark",
			"total_debit",
			"owner",
			"docstatus",
			"custom_pos_profile",
		],
		order_by="creation asc",
	):
		label, remark = r.custom_expense_type, r.user_remark or ""
		out.append(
			{
				"name": r.name,
				"label": label,
				"note": remark[len(label) + 2 :] if remark.startswith(f"{label}: ") else "",
				"amount": flt(r.total_debit, 2),
				"owner": r.owner,
				"docstatus": r.docstatus,
				"pos_profile": r.custom_pos_profile,
				"account": frappe.db.get_value(
					"Journal Entry Account",
					{"parent": r.name, "credit_in_account_currency": (">", 0)},
					"account",
				),
			}
		)
	return out


def _floats(shifts):
	floats = defaultdict(float)
	if shifts:
		for r in frappe.get_all(
			"POS Opening Entry Detail",
			{"parent": ("in", shifts)},
			["mode_of_payment", "opening_amount"],
			order_by="parent, idx",
		):
			floats[r.mode_of_payment] += flt(r.opening_amount)
	return floats


def _counted(closings):
	counted = {}
	if closings:
		for r in frappe.get_all(
			"POS Closing Entry Detail",
			{"parent": ("in", closings), "parenttype": "POS Closing Entry"},
			["mode_of_payment", "closing_amount"],
			order_by="parent, idx",
		):
			counted[r.mode_of_payment] = counted.get(r.mode_of_payment, 0) + flt(r.closing_amount)
	return counted


def _modes_by_account(pos_profile, cache):
	"""{account: mode} from the till's payment modes, first in the till's order wins.
	Same rule as klik_pos.api.pos_entry._drawer_modes_by_account."""
	if pos_profile not in cache:
		by_account = {}
		if pos_profile and frappe.db.exists("POS Profile", pos_profile):
			profile = frappe.get_cached_doc("POS Profile", pos_profile)
			order = [p.mode_of_payment for p in profile.payments]
			account_of = {
				r.parent: r.default_account
				for r in frappe.get_all(
					"Mode of Payment Account",
					{"parent": ("in", order or [""]), "company": profile.company},
					["parent", "default_account"],
				)
				if r.default_account
			}
			for mode in order:
				if account_of.get(mode):
					by_account.setdefault(account_of[mode], mode)
		cache[pos_profile] = by_account
	return cache[pos_profile]


def _change_by_invoice(invoices, rows_of):
	"""{invoice: (mode, change)}: the change left through the invoice's Cash row first, else the
	row paying into account_for_change_amount. Same rule as klik_pos.api.payment._change_given_by_mode."""
	change = {}
	for inv in invoices:
		if flt(inv.change_amount) <= 0:
			continue
		rows = [
			r for r in rows_of[inv.name] if r.type == "Cash" or r.account == inv.account_for_change_amount
		]
		rows.sort(key=lambda r: (r.type != "Cash", r.account != inv.account_for_change_amount, r.idx))
		if rows:
			change[inv.name] = (rows[0].mode_of_payment, flt(inv.change_amount))
	return change


# ---- the report --------------------------------------------------------------------------


def _money(amounts):
	return [{"mode": mode, "amount": flt(amount, 2)} for mode, amount in amounts.items()]


def _build(scope):
	invoices, entries = scope["invoices"], scope["payment_entries"]
	names = tuple(i.name for i in invoices)
	in_scope = set(names)

	rows_of = defaultdict(list)
	items_discount, taxes = 0.0, []
	if names:
		for r in frappe.db.sql(
			"""SELECT parent, mode_of_payment, amount, type, account, idx FROM `tabSales Invoice Payment`
			WHERE parenttype = 'Sales Invoice' AND parent IN %(names)s ORDER BY parent, idx""",
			{"names": names},
			as_dict=True,
		):
			rows_of[r.parent].append(r)
		items_discount = flt(
			frappe.db.sql(
				"""SELECT SUM(discount_amount * qty) FROM `tabSales Invoice Item`
				WHERE parenttype = 'Sales Invoice' AND parent IN %(names)s""",
				{"names": names},
			)[0][0]
		)
		taxes = frappe.db.sql(
			"""SELECT MIN(description) AS description, SUM(tax_amount_after_discount_amount) AS amount
			FROM `tabSales Taxes and Charges`
			WHERE parenttype = 'Sales Invoice' AND parent IN %(names)s
			GROUP BY account_head ORDER BY MIN(idx), account_head""",
			{"names": names},
			as_dict=True,
		)
	change = _change_by_invoice(invoices, rows_of)

	# Every amount received, tagged (user, mode); the drawer separately, till money only.
	lines = []
	drawer_in, drawer_out = defaultdict(float), defaultdict(float)
	returns = {"count": 0, "modes": defaultdict(float), "total": 0.0}
	for inv in invoices:
		for r in rows_of[inv.name]:
			lines.append((inv.owner, r.mode_of_payment, flt(r.amount)))
			if inv.shift:
				if flt(r.amount) >= 0:
					drawer_in[r.mode_of_payment] += flt(r.amount)
				else:
					drawer_out[r.mode_of_payment] -= flt(r.amount)
			if inv.is_return:
				returns["modes"][r.mode_of_payment] += flt(r.amount)
		if inv.name in change:
			mode, amount = change[inv.name]
			lines.append((inv.owner, mode, -amount))
			if inv.shift:
				drawer_in[mode] -= amount
		if inv.is_return:
			returns["count"] += 1
			returns["total"] += flt(inv.rounded_total or inv.grand_total)

	credit = defaultdict(float)
	refunds = defaultdict(float)  # money paid back to customers by Payment Entry, per mode
	paid_back = 0.0  # the part of those refunds settling returns already in scope
	for pe in entries:
		mode = pe.mode_of_payment or NO_MODE
		allocated = sum(flt(r.allocated_amount) for r in pe.refs if r.reference_name in in_scope)
		if pe.payment_type == "Pay":
			# Listed under returns and off the balance, never in the drawer: klik's
			# expected_by_mode counts only Receive entries, even when stamped with the shift.
			refunds[mode] -= flt(pe.paid_amount)
			paid_back += allocated
			continue
		if allocated:
			lines.append((pe.owner, mode, allocated))
		# not_ours: day scope's share of the entry that belongs to another branch.
		rest = flt(pe.paid_amount) - allocated - flt(pe.get("not_ours"))
		if flt(rest, 2):
			credit[mode] += rest
		if pe.shift and pe.mode_of_payment:
			drawer_in[pe.mode_of_payment] += flt(pe.paid_amount)

	tenders = defaultdict(float)
	users = {}
	for user, mode, amount in lines:
		tenders[mode] += amount
		users.setdefault(user, defaultdict(float))[mode] += amount

	cache, expenses = {}, []
	for e in scope["expenses"]:
		account = e.get("account")
		# An account no till mode uses (a separate petty-cash box) gets its own row.
		mode = _modes_by_account(e.get("pos_profile"), cache).get(account) or account or _("Expenses")
		drawer_out[mode] += flt(e["amount"])
		expenses.append(
			{
				"name": e["name"],
				"label": e["label"],
				"note": e["note"],
				"amount": flt(e["amount"], 2),
				"user": e["owner"],
				"pending": e["docstatus"] == 0,
			}
		)

	cash_position = []
	for mode in dict.fromkeys([*scope["floats"], *drawer_in, *drawer_out]):
		opening, got, out = scope["floats"].get(mode, 0), drawer_in.get(mode, 0), drawer_out.get(mode, 0)
		expected = flt(opening + got - out, 2)
		counted = scope["counted"].get(mode)
		cash_position.append(
			{
				"mode": mode,
				"opening": flt(opening, 2),
				"in": flt(got, 2),
				"out": flt(out, 2),
				"expected": expected,
				"counted": None if counted is None else flt(counted, 2),
				"difference": None if counted is None else flt(counted - expected, 2),
			}
		)

	# What the returns in scope came to, less what went back in the till or by Payment Entry,
	# is still owed to the customer. Refunds of earlier returns add to the total.
	on_account = returns["total"] - sum(returns["modes"].values()) + paid_back
	for mode, amount in refunds.items():
		returns["modes"][mode] += amount
	if flt(on_account, 2):
		returns["modes"][_("On account")] += on_account
	refund_total = flt(-sum(refunds.values()), 2)

	tender_total = flt(sum(tenders.values()), 2)
	credit_total = flt(sum(credit.values()), 2)
	expense_total = flt(sum(e["amount"] for e in expenses), 2)
	sales = [i for i in invoices if not i.is_return]
	return {
		"scope": scope["scope"],
		"company": scope["company"],
		"warehouse": scope["warehouse"],
		"report_no": scope["report_no"],
		"printed_at": str(now_datetime()),
		"period_start": scope["period_start"],
		"period_end": scope["period_end"],
		"first_doc": invoices[0].name if invoices else None,
		"last_doc": invoices[-1].name if invoices else None,
		"sales_count": len(sales),
		"users": [
			{
				"user": user,
				"full_name": get_fullname(user),
				"modes": _money(modes),
				"total": flt(sum(modes.values()), 2),
			}
			for user, modes in users.items()
		],
		"tenders": _money(tenders),
		"tender_total": tender_total,
		"credit_collected": _money(credit),
		"credit_total": credit_total,
		"returns": {
			"count": returns["count"],
			"modes": _money(returns["modes"]),
			"total": flt(sum(returns["modes"].values()), 2),
		},
		"refund_total": refund_total,
		"discount_total": flt(sum(flt(i.discount_amount) for i in invoices) + items_discount, 2),
		"taxes": [{"description": t.description, "amount": flt(t.amount, 2)} for t in taxes],
		"net_total": flt(sum(flt(i.net_total) for i in invoices), 2),
		"tax_total": flt(sum(flt(i.total_taxes_and_charges) for i in invoices), 2),
		"grand_total": flt(sum(flt(i.grand_total) for i in invoices), 2),
		"expenses": expenses,
		"expense_total": expense_total,
		"cash_position": cash_position,
		"total_balance": flt(tender_total + credit_total - expense_total - refund_total, 2),
		"outstanding": [
			{
				"name": i.name,
				"customer_name": i.customer_name,
				"grand_total": flt(i.grand_total, 2),
				"outstanding_amount": flt(i.outstanding_amount, 2),
			}
			for i in sales
			if flt(i.outstanding_amount) > 0
		],
		"excluded_payment_entries": scope["excluded"],
		"excluded_invoices": scope["excluded_invoices"],
	}
