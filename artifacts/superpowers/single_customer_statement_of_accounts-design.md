# Single-Customer Statement of Accounts — Design

Date: 2026-08-05
App: `cecypo_frappe_reports`
Status: approved

## Problem

Exporting the Accounts Receivable query report to PDF (`/app/query-report/Accounts Receivable` → menu → PDF)
produces an unbranded, awkwardly laid out document. The Process Statement of Accounts doctype
(`/app/process-statement-of-accounts`) produces a properly branded statement, but it is built for
bulk emailing to many customers and cannot be reached when the user is focused on one customer.

The same gap exists on the Transaction History page's Receivables tab, where the per-customer print
icon emits a hand-rolled unstyled HTML table (`_generate_statement_html`, `transaction_history.js:1823`).

Users want to produce the branded PSOA statement for **one focused customer**, from wherever they are
already looking at that customer's receivables. Bulk emailing stays with PSOA, which already works.

## Key insight

`get_report_pdf(doc)` in
`erpnext/accounts/doctype/process_statement_of_accounts/process_statement_of_accounts.py:171`
takes a Process Statement Of Accounts **document**, not a document name. It never saves, reloads, or
requires the doc to exist in the database. So an in-memory clone of an existing PSOA record, with its
`customers` child table replaced by a single row, renders through the exact same branded path.

This was verified by spike before the design was accepted: cloning the `AR` PSOA record on `dev.localhost`,
swapping in one customer, produced 11,887 characters of HTML through the site's custom
`PSOA AR Statement` print format, including its branded header block and blue rule. Only the final
`wkhtmltopdf` call failed, because the bench web server was not running in the console context —
an environment artifact, not a design constraint. PSOA already depends on that same call in production.

The consequence that shapes everything below: **we write no rendering, layout, or branding code.**
Branding lives in the existing Print Format records, which the users already tuned.

## Scope

Three surfaces, all reporting surfaces:

1. Accounts Receivable query report — inner button
2. Accounts Receivable Summary query report — inner button
3. Transaction History → Receivables tab — per-customer row icon

Explicitly out of scope: the Customer form, the Payables/Supplier equivalent (PSOA is customer-only),
and any change to PSOA's own bulk email flow.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Where formatting comes from | Clone an existing PSOA record as a template | Output is identical to the PSOA statements users already accept. Branding is retuned by editing the PSOA record, never by a code deploy. |
| Host app | `cecypo_frappe_reports` | All three surfaces are reporting surfaces, and half the combined dialog's content (`_generate_statement_html`, `send_statement_email`) already lives here. Hosting in `cecypo_powerpack` would mean reaching across an app boundary behind an existence guard on every render. |
| Row icon layout | One combined `Statement` button and dialog | Transaction History rows keep 3 icons instead of growing to 5. The existing print and email icons fold into the dialog's Download and Email actions. |
| Template preselection | Sticky per user, via `user_settings` | `cecypo_frappe_reports` has zero DocTypes, so there is no singleton to hold a global default. Per-user stickiness needs no DocType, no migration, and no cross-app read, and lands each user on the template they actually use. |
| Email editing | To editable, CC/BCC behind a toggle | Preserves the CC/BCC the existing transaction-list email dialog already offers, while keeping the combined dialog compact. |
| Email delivery | `frappe.sendmail(now=False)` | Matches the existing call and keeps PDF generation off the blocking path. |

## Architecture

### Components

| Unit | Responsibility | Depends on |
|---|---|---|
| `cecypo_frappe_reports/statement_of_accounts.py` *(new)* | The only module that touches PSOA. Builds the cloned doc; exposes 4 whitelisted endpoints. | ERPNext PSOA module |
| `public/js/statement_dialog.js` *(new)* | `cecypo_reports.statement.open({...})` — the combined dialog. Surface-agnostic. | the 4 endpoints |
| `public/js/report_statement_button.js` *(new)* | Injects the inner button into the two AR query reports. | `statement_dialog.js` |
| `page/transaction_history/transaction_history.js` *(edit)* | Collapses `print` + `email` row icons into one `Statement` icon. | `statement_dialog.js` |
| `page/transaction_history/transaction_history.py` *(edit)* | Permission fix on `send_statement_email`. | — |

Both new JS files are added to `app_include_js` in `hooks.py`.

### Backend interface

```python
def _build_statement_doc(customer, company, template, as_of_date) -> Document   # private
@frappe.whitelist() def get_statement_templates(company) -> list[dict]
@frappe.whitelist() def render_statement_html(customer, company, template, as_of_date) -> str
@frappe.whitelist() def download_statement(customer, company, template, as_of_date) -> None
@frappe.whitelist() def email_statement(customer, company, template, as_of_date,
                                        recipient, cc="", bcc="") -> bool
```

`_build_statement_doc` is the single point where PSOA semantics are encoded. The three public
render/download/email endpoints differ only in what they do with its result, so there is exactly one
place where the clone, the permission checks, and the date mapping can be wrong.

### Date mapping

The dialog offers one "As of" input, but PSOA stores the date differently per report type:

- `report == "Accounts Receivable"` → `posting_date = as_of_date`
- `report == "General Ledger"` → `to_date = as_of_date`, `from_date = as_of_date − filter_duration` months

`filter_duration` comes from the template record, so a template configured for a 3-month window keeps it.

### Dialog

```
+--------------------------------------------------+
| Statement — WEMO ELECTRICALS                     |
|                                                  |
| Document   ( ) Transaction list                  |   <- only when transaction_list passed
|            (•) Statement of Accounts             |
|                                                  |
| Customer   [WEMO ELECTRICALS                  ]  |   <- read-only when caller knows it
| As of      [05-08-2026]                          |
| Template   [AR                                v] |   <- only for Statement of Accounts
|                                                  |
| To         [ar@wemo.co.ke                     ]  |
|            + Add CC / BCC                        |
|                                                  |
| PREVIEW                                          |
| +----------------------------------------------+ |
| |  (rendered statement HTML in an iframe)      | |
| +----------------------------------------------+ |
|                                                  |
|                       [ Download ]  [ Email ]    |
+--------------------------------------------------+
```

`transaction_list` is the seam that lets one dialog serve three surfaces. Transaction History passes
`{label, get_html}`; the two reports pass nothing, so the Document radio does not render and Statement
of Accounts is implied.

**Customer resolution.** On the reports, `party` is a MultiSelectList that may hold zero or many values,
so the customer is genuinely ambiguous. The dialog therefore carries a Customer link field: prefilled
and read-only when the caller knows the customer (a Transaction History row, or a `party` filter holding
exactly one Customer), editable otherwise. Introspecting the datatable's focused cell was rejected —
Frappe's datatable internals are not a stable interface.

### Query report injection

`QueryReport.refresh_report()` calls `page.clear_custom_actions()` and then
`report_settings.onload(this)` (`frappe/public/js/frappe/views/reports/query_report.js:398`), so any
button must be re-added on each report load.

`frappe.query_reports[name]` is populated lazily after the report script is fetched and eval'd, which
makes wrapping its `onload` a race. Instead we patch `frappe.views.QueryReport.prototype.refresh_report`
**once** and add the button after the returned promise resolves — after `clear_custom_actions()` has run.
The patch is guarded so a future Frappe rename degrades to a no-op rather than a broken desk.

### Data flow

```
dialog opens
  └─ get_statement_templates(company)
       → PSOA records where company = <company>
       → preselect user_settings last-used for that company, else newest AR-report record
       → none found? Statement option disabled, message + link to create one

on field change (debounced, sequence-numbered)
  └─ render_statement_html(...) → _build_statement_doc() → get_statement_dict() → iframe

[Download] download_statement(...) → get_report_pdf(doc) → frappe.local.response
[Email]    email_statement(...)    → get_report_pdf(doc) → sendmail(now=False), PDF attached
```

## Error handling

| Condition | Behaviour |
|---|---|
| No PSOA record for the company | Statement option disabled with an inline note and a link to create one. Transaction list still works, so the dialog never becomes useless. |
| Customer has no rows in the period | `get_statement_dict` returns `{}` and `get_report_pdf` returns `False`. All three endpoints detect this and throw *"No transactions for {customer} in the selected period."* rather than emitting a blank PDF. |
| No email on file | Email button disabled with the reason and a link to the Customer. Download unaffected. |
| Permission denied | `has_permission("Customer", "read", …)` and `template.check_permission("read")` throw **before** any rendering, so no data reaches a preview the user may not read. |
| Template company ≠ selected company | Defensive throw. The dropdown is company-filtered, but the endpoint cannot trust its client. |
| `wkhtmltopdf` failure | Surfaces as it does for PSOA today. The preview path never invokes it, so a broken PDF toolchain still allows viewing and diagnosis. |
| Stale preview responses | Renders are debounced and sequence-numbered; responses older than the latest are dropped. |

### Invariants

- **The cloned doc is never persisted.** Nothing calls `save()` or `insert()`. Templates can carry
  `enable_auto_email = 1`, so an accidentally-saved clone would enrol a customer into a scheduled
  email run. Asserted by test.
- **The client never supplies statement HTML.** The PSOA endpoints take
  `(customer, company, template, date)` and render server-side.

## Security fix

`send_statement_email` (`transaction_history.py:567`) is whitelisted, accepts `html_content` and
`recipient_email` straight from the client, and performs **no permission check** — any logged-in user
can send arbitrary HTML to any address through the site's mail server.

Fix: `frappe.has_permission("Customer"|"Supplier", "read", party, throw=True)` at the top of the method.

The `html_content` parameter is retained. Removing it would require re-deriving the transaction list
server-side, a larger change than this work needs; the permission gate means only users who can already
read that party's data can trigger a send.

## Testing

`tests/test_statement_of_accounts.py`, following `test_transaction_history.py`'s conventions —
`IntegrationTestCase` against the real DB with per-test savepoints.

**Doc construction** (no PDF, fast):
- clone carries exactly one customer row regardless of what the template held
- AR template sets `posting_date` and leaves `from_date`/`to_date` alone
- GL template sets `to_date` and derives `from_date` from `filter_duration`
- clone is `is_new()`, and the template record on disk is unchanged afterwards
- company mismatch throws; unknown template throws

**Rendering:**
- against a seeded customer with a known invoice, `render_statement_html` returns HTML containing that
  customer's name and **no other customer's name** — single-customer isolation is the point of the
  feature, so it is asserted directly rather than inferred
- a customer with no transactions raises the friendly error rather than returning a blank result

**Email:**
- `frappe.sendmail` patched: one attachment, `.pdf` filename derived from the customer, correct recipient
- recipient resolution order billing contact → primary → `Customer.email_id`, one case per rung
- a user without Customer read access triggers `PermissionError`, covering both the new endpoints and
  the `send_statement_email` fix

PDF-generating assertions skip when `wkhtmltopdf` is unreachable, so the suite stays green in
environments without it. The HTML-level assertions carry the real coverage regardless.

## Verification

```bash
bench --site dev.localhost run-tests --app cecypo_frappe_reports \
  --module cecypo_frappe_reports.cecypo_frappe_reports.tests.test_statement_of_accounts
bench build --app cecypo_frappe_reports
bench --site dev.localhost clear-cache && bench restart
```

Manual: open `/app/query-report/Accounts Receivable` filtered to Dev Co, click **Statement of Accounts**,
confirm the PDF matches what PSOA produces for the same customer.
