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
from frappe.utils.pdf import get_pdf

from erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts import (
	get_context,
	get_customer_emails,
	get_recipients_and_cc,
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


def _company_customers(company):
	"""Enabled customers with any ledger activity against `company`.

	Scoped through GL Entry rather than the Customer doctype, which has no company field. A
	site-wide list would still send correctly — get_statement_dict drops anyone with no rows —
	but it would report every customer on the site in `total_customers` and `no_transactions`,
	and those counts are the only visibility the user gets. It would also run a GL/AR query per
	customer for customers of other companies.

	Deliberately broader than the statement period: this answers "could relate to this company
	at all", and get_statement_dict still applies the period filter. That keeps the
	has-transactions decision in one place rather than two that could disagree.
	"""
	parties = frappe.get_all(
		"GL Entry",
		filters={"company": company, "party_type": "Customer", "is_cancelled": 0},
		distinct=True,
		pluck="party",
	)
	if not parties:
		return []

	return frappe.get_all(
		"Customer",
		filters={"disabled": 0, "name": ["in", parties]},
		fields=["name", "customer_name"],
		order_by="customer_name asc",
	)


def _build_bulk_statement_doc(company, template, as_of_date=None):
	"""The single-customer clone, widened to every customer of the company.

	Reuses _build_statement_doc so the permission checks, the template-company guard and the
	report-type date mapping cannot drift between the single and bulk paths. Never saved.
	"""
	customers = _company_customers(company)
	if not customers:
		frappe.throw(_("No customers found for {0}").format(frappe.bold(company)))

	# frappe.get_all does not check permissions, so customers[0] is whoever sorts first, not
	# someone this user may read. Seeding _build_statement_doc with an unreadable customer makes
	# its has_permission check throw and takes the whole preview or run down with it.
	seed = next(
		(c.name for c in customers if frappe.has_permission("Customer", "read", c.name)), None
	)
	if not seed:
		frappe.throw(_("You are not permitted to view any customer for {0}.").format(frappe.bold(company)))

	# Seed with a readable customer so the shared builder runs its checks, then widen.
	doc = _build_statement_doc(seed, company, template, as_of_date)
	doc.customers = []
	for customer in customers:
		doc.append(
			"customers", {"customer": customer.name, "customer_name": customer.customer_name}
		)
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


def _send_bulk_statements(company, template, as_of_date=None, user=None):
	"""Render and send one statement per customer with transactions.

	Runs in a background job: rendering N statements inside a web request would time out, and
	the failure mode is a half-finished send with no record of where it stopped.

	One customer must never abort the run, so a render or send failure is logged and skipped.
	The POS shows only a queued toast, so this log is the only place a failure can be found.
	"""
	if user:
		frappe.set_user(user)

	doc = _build_bulk_statement_doc(company, template, as_of_date)

	# get_report_pdf is deliberately NOT used here. It renders every customer in one pass, so a
	# render failure on customer 3 aborts customers 4..N before any per-customer handler sees it
	# — the exact failure this loop exists to prevent. Splitting it keeps the one expensive part
	# (the AR/GL query, via get_statement_dict) as a single pass while making each PDF render
	# individually survivable.
	statements = get_statement_dict(doc) or {}

	for entry in doc.customers:
		statement_html = statements.get(entry.customer)
		if not statement_html:
			continue

		try:
			# Inside the try: _resolve_recipients raises PermissionError per customer, and
			# get_pdf can throw on a broken image or a wkhtmltopdf failure. Either must cost
			# one customer, not the run.
			recipients = _resolve_recipients(entry.customer)
			if not recipients:
				continue

			pdf = get_pdf(statement_html, {"orientation": doc.orientation})
			context = get_context(entry.customer, doc)
			frappe.sendmail(
				recipients=recipients,
				subject=_render_or(doc.subject, context, _("Statement of Accounts")),
				message=_render_or(
					doc.body, context, _("Please find your Statement of Accounts attached.")
				),
				attachments=[
					{"fname": _statement_filename(doc, entry.customer), "fcontent": pdf}
				],
				reference_doctype="Customer",
				reference_name=entry.customer,
				now=False,
			)
		except frappe.PermissionError:
			# Expected for a restricted user; the preview already counted them. Not an error,
			# and logging it under the failure title would bury real failures.
			continue
		except Exception:
			frappe.log_error(
				title="Bulk Statement of Accounts: send failed",
				message=f"{entry.customer}\n\n{frappe.get_traceback()}",
			)


STATEMENT_BATCH_SIZE = 50


def _narrow_statement_doc(template, customer_rows, as_of_date=None):
	"""Clone `template` in memory, narrowed to `customer_rows`. Never saved.

	`customer_rows` are dicts carrying at least `customer`, and optionally `customer_name`,
	`billing_email` and `primary_email` — the last two are what a saved PSOA record's own rows
	carry, and preserving them is what lets the desk path honour its configured recipients.

	`as_of_date=None` deliberately leaves the template's own dates alone, so a PSOA record sends
	for the period it was configured with rather than for today.
	"""
	if not frappe.db.exists(PSOA, template):
		frappe.throw(_("Statement template {0} does not exist").format(frappe.bold(template)))

	tpl = frappe.get_doc(PSOA, template)
	tpl.check_permission("read")

	doc = frappe.copy_doc(tpl)
	doc.customers = []
	for row in customer_rows:
		doc.append("customers", dict(row))

	if as_of_date:
		as_of = getdate(as_of_date)
		if doc.report == "General Ledger":
			doc.to_date = as_of
			doc.from_date = add_months(as_of, -1 * (doc.filter_duration or 12))
		else:
			doc.posting_date = as_of

	return doc


def _batch_recipients(entry, doc):
	"""Recipients for one row, using whichever source the row's own data implies.

	A saved PSOA record's rows carry billing_email/primary_email from ERPNext's fetch_customers,
	and that path also honours primary_mandatory and cc_to. Rows built in memory carry neither,
	so they resolve live. Branching on the data rather than a mode flag keeps both callers
	honest without either having to declare which it is.
	"""
	if entry.get("billing_email") or entry.get("primary_email"):
		return get_recipients_and_cc(entry.customer, doc)
	return _resolve_recipients(entry.customer), []


def _send_statement_batch(template, customer_rows, as_of_date=None, user=None):
	"""Render and send one statement per customer in this batch.

	Batched because ERPNext's own send renders every customer inside one HTTP request and times
	out on any sizeable customer base. One batch is sized so a worker finishes it comfortably.

	get_report_pdf is deliberately not used: it renders every customer in one pass, so a failure
	on one aborts the rest of the batch.
	"""
	if user:
		frappe.set_user(user)

	doc = _narrow_statement_doc(template, customer_rows, as_of_date)
	statements = get_statement_dict(doc) or {}

	for entry in doc.customers:
		statement_html = statements.get(entry.customer)
		if not statement_html:
			continue

		try:
			recipients, cc = _batch_recipients(entry, doc)
			if not recipients:
				continue

			pdf = get_pdf(statement_html, {"orientation": doc.orientation})
			context = get_context(entry.customer, doc)
			frappe.sendmail(
				recipients=recipients,
				cc=cc,
				subject=_render_or(doc.subject, context, _("Statement of Accounts")),
				message=_render_or(
					doc.body, context, _("Please find your Statement of Accounts attached.")
				),
				attachments=[{"fname": _statement_filename(doc, entry.customer), "fcontent": pdf}],
				reference_doctype="Customer",
				reference_name=entry.customer,
				now=False,
			)
		except frappe.PermissionError:
			continue
		except Exception:
			frappe.log_error(
				title="Statement of Accounts: batch send failed",
				message=f"{template} / {entry.customer}\n\n{frappe.get_traceback()}",
			)


def enqueue_statement_batches(template, customer_rows, as_of_date=None, batch_size=None):
	"""Split `customer_rows` into batches and enqueue one job each. Returns the batch count.

	Enqueued up front rather than chained, so workers run them in parallel and one failed batch
	does not stop the rest.
	"""
	batch_size = batch_size or STATEMENT_BATCH_SIZE
	rows = list(customer_rows)
	batches = [rows[i : i + batch_size] for i in range(0, len(rows), batch_size)]

	for index, batch in enumerate(batches):
		frappe.enqueue(
			"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts._send_statement_batch",
			queue="long",
			timeout=1800,
			# Per batch, so a retry of the whole run cannot re-send a batch already in flight.
			job_id=f"soa-batch::{template}::{as_of_date or 'template-dates'}::{index}",
			deduplicate=True,
			template=template,
			customer_rows=batch,
			as_of_date=as_of_date,
			user=frappe.session.user,
		)

	return len(batches)


# ── Endpoints ────────────────────────────────────────────────────────────────


@frappe.whitelist()
def send_psoa_in_batches(document_name):
	"""Send a saved Process Statement Of Accounts in batches, from the desk.

	ERPNext's own Send Emails button renders every customer's PDF inside the HTTP request, so it
	times out on a sizeable customer base. This enqueues the same work in batches instead and
	returns immediately.
	"""
	doc = frappe.get_doc(PSOA, document_name)
	doc.check_permission("read")

	rows = [
		{
			"customer": row.customer,
			"customer_name": row.customer_name,
			"billing_email": row.billing_email,
			"primary_email": row.primary_email,
		}
		for row in doc.customers
	]
	if not rows:
		frappe.throw(_("{0} has no customers to send to.").format(frappe.bold(document_name)))

	# as_of_date is None on purpose: the record's own from/to or posting date is the period the
	# user configured, and a batched send must not silently re-date it to today.
	batches = enqueue_statement_batches(doc.name, rows, as_of_date=None)
	return {"batches": batches, "customers": len(rows)}


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
def preview_bulk_statements(company, template, as_of_date=None):
	"""Who would receive a statement, without sending or rendering a single PDF.

	get_statement_dict returns HTML per customer and omits anyone with no rows, so it answers
	"who has transactions" without invoking wkhtmltopdf.
	"""
	doc = _build_bulk_statement_doc(company, template, as_of_date)
	statements = get_statement_dict(doc) or {}

	will_send = []
	no_email = []
	not_permitted = 0
	for entry in doc.customers:
		if entry.customer not in statements:
			continue

		try:
			recipients = _resolve_recipients(entry.customer)
		except frappe.PermissionError:
			# _resolve_recipients checks Customer read per customer. A user with restricted
			# customer visibility must not have their whole preview die on one customer they
			# cannot see — count them and move on. Counted rather than silently dropped so the
			# totals still reconcile, and never named, so nothing leaks.
			not_permitted += 1
			continue

		row = {"customer": entry.customer, "customer_name": entry.customer_name}
		if recipients:
			row["recipient"] = recipients[0]
			will_send.append(row)
		else:
			no_email.append(row)

	return {
		"will_send": will_send,
		"no_email": no_email,
		"not_permitted": not_permitted,
		"no_transactions": len(doc.customers) - len(statements),
		"total_customers": len(doc.customers),
	}


@frappe.whitelist()
def email_bulk_statements(company, template, as_of_date=None):
	"""Queue a statement for every customer of `company` who has transactions."""
	preview = preview_bulk_statements(company, template, as_of_date)
	queued = len(preview["will_send"])
	if not queued:
		frappe.throw(_("No customer has both transactions and an email address on file."))

	frappe.enqueue(
		"cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts._send_bulk_statements",
		queue="long",
		timeout=1800,
		# A retry after a lost or timed-out response must not mail everyone twice. The id is
		# keyed on exactly the inputs that define the run, so re-sending the same statement set
		# is a no-op while it is in flight, while a genuinely different date or template still
		# queues.
		job_id=f"bulk-soa::{company}::{template}::{as_of_date or today()}",
		deduplicate=True,
		company=company,
		template=template,
		as_of_date=as_of_date,
		user=frappe.session.user,
	)
	return {"queued": queued}


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
