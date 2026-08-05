# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

"""Statement of Accounts for a single focused customer.

ERPNext's Process Statement Of Accounts produces a properly branded statement, but it is built for
emailing many customers at once and cannot be reached when a user is looking at one customer in a
report. `get_report_pdf(doc)` takes a PSOA *document* rather than a name, and never saves or reloads
it, so an in-memory clone of an existing PSOA record with its customer table narrowed to a single row
renders through the exact same branded path.

Nothing here renders HTML. Branding, layout and print-format selection stay in ERPNext and in the
site's Print Format records, so retuning the look means editing a PSOA record, not deploying code.
"""

import re

import frappe
from frappe import _
from frappe.utils import add_months, getdate, today

from erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts import (
	get_context,
	get_customer_emails,
	get_report_pdf,
	get_statement_dict,
)

PSOA = "Process Statement Of Accounts"


# ── Core ─────────────────────────────────────────────────────────────────────


def _build_statement_doc(customer, company, template, as_of_date=None):
	"""Clone `template` in memory, narrowed to `customer`, dated `as_of_date`.

	The single point where PSOA semantics are encoded, so there is exactly one place for the clone,
	the permission checks and the date mapping to be wrong. The returned doc is never saved.
	"""
	if not customer:
		frappe.throw(_("Customer is required"))
	if not company:
		frappe.throw(_("Company is required"))
	if not template:
		frappe.throw(_("Statement template is required"))

	frappe.has_permission("Customer", "read", customer, throw=True)

	if not frappe.db.exists(PSOA, template):
		frappe.throw(_("Statement template {0} does not exist").format(frappe.bold(template)))

	tpl = frappe.get_doc(PSOA, template)
	tpl.check_permission("read")

	# The dialog filters the dropdown by company, but the endpoint cannot trust its client: a
	# mismatched template would silently apply another company's letterhead and accounts.
	if tpl.company != company:
		frappe.throw(
			_("Statement template {0} belongs to {1}, not {2}").format(
				frappe.bold(template), frappe.bold(tpl.company), frappe.bold(company)
			)
		)

	doc = frappe.copy_doc(tpl)
	doc.customers = []
	doc.append(
		"customers",
		{
			"customer": customer,
			"customer_name": frappe.db.get_value("Customer", customer, "customer_name"),
		},
	)

	# PSOA stores the AR as-on date in posting_date but the GL window in from_date/to_date, so the
	# dialog's single "As of" input has to fork on the template's report type.
	as_of = getdate(as_of_date or today())
	if doc.report == "General Ledger":
		doc.to_date = as_of
		doc.from_date = add_months(as_of, -1 * (doc.filter_duration or 12))
	else:
		doc.posting_date = as_of

	return doc


def _no_transactions_error(customer, doc):
	label = frappe.db.get_value("Customer", customer, "customer_name") or customer
	period = (
		_("{0} to {1}").format(doc.from_date, doc.to_date)
		if doc.report == "General Ledger"
		else _("as at {0}").format(doc.posting_date)
	)
	return _("No transactions for {0} in the selected period ({1}).").format(frappe.bold(label), period)


def _render_html(doc):
	statement = get_statement_dict(doc)
	if not statement:
		frappe.throw(_no_transactions_error(doc.customers[0].customer, doc))
	return next(iter(statement.values()))


def _render_pdf(doc):
	# get_report_pdf returns False rather than raising when the customer has no rows; without this
	# check a download would silently hand back an empty file.
	pdf = get_report_pdf(doc)
	if not pdf:
		frappe.throw(_no_transactions_error(doc.customers[0].customer, doc))
	return pdf


def _statement_filename(doc, customer):
	"""Prefer the template's own pdf_name Jinja, so a site that has tuned its PSOA naming keeps it."""
	name = None
	if doc.pdf_name:
		try:
			name = frappe.render_template(doc.pdf_name, get_context(customer, doc), restrict_globals=True)
		except Exception:
			# A malformed pdf_name template must not block the download it only names.
			frappe.log_error(title="Statement of Accounts: bad pdf_name template")

	name = (name or frappe.db.get_value("Customer", customer, "customer_name") or customer).strip()
	# Strip characters that browsers and filesystems handle badly in a download name.
	name = re.sub(r'[\\/:*?"<>|\r\n]+', " ", name).strip() or "Statement"
	return f"{name}.pdf"


def _split_emails(value):
	if not value:
		return []
	return [e.strip() for e in value.replace(";", ",").split(",") if e.strip()]


def _resolve_recipients(customer):
	"""Billing contact, then the customer's own email, then its primary contact."""
	billing = get_customer_emails(customer, 0, billing_and_primary=False)
	if billing:
		return _split_emails(billing)

	primary = frappe.db.get_value("Customer", customer, "email_id")
	if primary:
		return _split_emails(primary)

	primary_contact = frappe.db.get_value("Customer", customer, "customer_primary_contact")
	if primary_contact:
		contact_email = frappe.db.get_value("Contact", primary_contact, "email_id")
		if contact_email:
			return _split_emails(contact_email)

	return []


# ── Endpoints ────────────────────────────────────────────────────────────────


@frappe.whitelist()
def get_statement_templates(company):
	"""PSOA records usable as a formatting template for `company`, newest first."""
	frappe.has_permission(PSOA, "read", throw=True)
	if not company:
		return []

	return frappe.get_all(
		PSOA,
		filters={"company": company},
		fields=["name", "report", "print_format", "letter_head", "modified"],
		order_by="modified desc",
	)


@frappe.whitelist()
def get_default_recipient(party_type, party):
	"""Address to prefill the dialog's To field with, or "" when the party has none on file."""
	doctype = "Customer" if party_type == "customer" else "Supplier"
	frappe.has_permission(doctype, "read", party, throw=True)

	if doctype == "Supplier":
		return frappe.db.get_value("Supplier", party, "email_id") or ""

	recipients = _resolve_recipients(party)
	return recipients[0] if recipients else ""


@frappe.whitelist()
def render_statement_html(customer, company, template, as_of_date=None):
	"""Statement HTML for the dialog preview.

	Deliberately separate from the PDF path: preview never invokes wkhtmltopdf, so a broken PDF
	toolchain still lets users see the statement and diagnose.
	"""
	return _render_html(_build_statement_doc(customer, company, template, as_of_date))


@frappe.whitelist()
def download_statement(customer, company, template, as_of_date=None):
	doc = _build_statement_doc(customer, company, template, as_of_date)
	pdf = _render_pdf(doc)

	frappe.local.response.filename = _statement_filename(doc, customer)
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "download"


@frappe.whitelist()
def email_statement(customer, company, template, as_of_date=None, recipient=None, cc="", bcc=""):
	"""Send the statement as a PDF attachment.

	Takes the statement's identity rather than its content: the HTML is rendered server-side from
	(customer, company, template, date) and never accepted from the client.
	"""
	doc = _build_statement_doc(customer, company, template, as_of_date)

	recipients = _split_emails(recipient) or _resolve_recipients(customer)
	if not recipients:
		frappe.throw(
			_("No email address on file for {0}").format(
				frappe.bold(frappe.db.get_value("Customer", customer, "customer_name") or customer)
			)
		)

	pdf = _render_pdf(doc)
	context = get_context(customer, doc)
	subject = _render_or(doc.subject, context, _("Statement of Accounts"))
	message = _render_or(doc.body, context, _("Please find your Statement of Accounts attached."))

	frappe.sendmail(
		recipients=recipients,
		cc=_split_emails(cc),
		bcc=_split_emails(bcc),
		subject=subject,
		message=message,
		attachments=[{"fname": _statement_filename(doc, customer), "fcontent": pdf}],
		reference_doctype="Customer",
		reference_name=customer,
		now=False,
	)
	return True


def _render_or(template_str, context, fallback):
	if not template_str:
		return fallback
	try:
		return frappe.render_template(template_str, context, restrict_globals=True)
	except Exception:
		# The template's subject/body are user-edited Jinja; a bad one must not block the send.
		frappe.log_error(title="Statement of Accounts: bad subject/body template")
		return fallback
