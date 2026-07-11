# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

from collections import defaultdict

import frappe
from frappe.utils import flt
from pypika import functions as fn


def get_future_payments_by_invoice(party=None, as_of_date=None, company=None):
	"""Future payments allocated to invoices, as of a given date.

	Single source of truth for "future payments" across the GL/AR statement print formats
	and the Transaction History receivables report. A future payment is a future-dated
	(posting_date > as_of_date) Payment Entry or Journal Entry allocation against a
	Customer's Sales Invoice — same definition as accounts_receivable.py's
	get_future_payments_from_payment_entry / get_future_payments_from_journal_entry,
	aggregated per invoice instead of per payment-term row.

	Args:
	    party: a customer name, a list of customer names, or None for all customers
	        (optionally scoped by `company`).
	    as_of_date: only postings strictly after this date count as "future".
	    company: optional company filter.

	Returns:
	    list of {"customer": str, "invoice_no": str, "future_amount": float}
	"""
	if not as_of_date:
		frappe.throw(frappe._("as_of_date is required"))

	party_list = None
	if party:
		party_list = [party] if isinstance(party, str) else list(party)

	pe = frappe.qb.DocType("Payment Entry")
	per_ref = frappe.qb.DocType("Payment Entry Reference")
	pe_q = (
		frappe.qb.from_(pe)
		.inner_join(per_ref).on(per_ref.parent == pe.name)
		.select(
			pe.party.as_("customer"),
			per_ref.reference_name.as_("invoice_no"),
			per_ref.allocated_amount.as_("future_amount"),
		)
		.where(pe.docstatus < 2)
		.where(pe.posting_date > as_of_date)
		.where(pe.party_type == "Customer")
		.where(per_ref.reference_doctype == "Sales Invoice")
	)
	if company:
		pe_q = pe_q.where(pe.company == company)
	if party_list:
		pe_q = pe_q.where(pe.party.isin(party_list))

	je = frappe.qb.DocType("Journal Entry")
	jea = frappe.qb.DocType("Journal Entry Account")
	je_q = (
		frappe.qb.from_(je)
		.inner_join(jea).on(jea.parent == je.name)
		.select(
			jea.party.as_("customer"),
			jea.reference_name.as_("invoice_no"),
			(jea.credit_in_account_currency - jea.debit_in_account_currency).as_("future_amount"),
		)
		.where(je.docstatus < 2)
		.where(je.posting_date > as_of_date)
		.where(jea.party_type == "Customer")
		.where(jea.reference_type == "Sales Invoice")
		.where(jea.reference_name.isnotnull())
		.where(jea.reference_name != "")
	)
	if company:
		je_q = je_q.where(je.company == company)
	if party_list:
		je_q = je_q.where(jea.party.isin(party_list))

	merged = defaultdict(float)
	for r in pe_q.run(as_dict=True) + je_q.run(as_dict=True):
		merged[(r.customer, r.invoice_no)] += flt(r.future_amount or 0)

	return [
		{"customer": customer, "invoice_no": invoice_no, "future_amount": flt(amount, 2)}
		for (customer, invoice_no), amount in merged.items()
		if amount
	]
