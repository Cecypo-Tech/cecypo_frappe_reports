# Statement dialog — date fields follow the template's report type

Date: 2026-09-11
Surfaces: Transaction History (Receivables tab) statement button, and the Accounts Receivable /
Accounts Receivable Summary report button. Both use `public/js/statement_dialog.js`.

## Brainstorm

**Goal.** In the statement dialog, the date inputs should match the PSOA template's `report`:

| Mode                                      | Fields shown             |
|-------------------------------------------|--------------------------|
| Statement, template `report = General Ledger` | From Date, To Date   |
| Statement, template `report = Accounts Receivable` | Posting Date    |
| Transaction list (no template)            | As of (unchanged)        |

For GL, **From Date defaults to the first day of the previous month** (today 2026-09-11 gives
2026-08-01). To Date defaults to the caller's as-of date, or today if there is none.

**Today.** The dialog has one "As of" input. On the server, `_build_statement_doc` sets
`to_date = as_of` and `from_date = as_of − filter_duration months` for GL, so the user never sees
or controls the GL start date.

**Constraints**
- `klik_pos/api/statement_of_accounts.py` delegates to `render_statement_html`,
  `download_statement` and `email_statement` using `as_of_date` only, and
  `test_statement_delegation.py` checks those signatures. New parameters must be **optional**. Per
  the `STATEMENT_API_VERSION` comment, adding an optional parameter doesn't break callers, so the
  version stays at 2.
- `get_statement_templates` already returns `report`, so the dialog can tell a GL template from
  an AR one without another request.
- The bulk and PSOA-desk paths (`_narrow_statement_doc`, `preview_bulk_statements`,
  `email_bulk_statements`, `send_psoa_in_batches`) are out of scope and stay unchanged.

**Design**
- The `as_of_date` field stays. Its label changes by mode: "To Date" (GL), "Posting Date" (AR),
  "As of" (transaction list). Keeping one end-date field means switching the Document selector
  doesn't lose the date the user picked.
- New `from_date` Date field. It is shown and required only in statement mode with a GL template.
  Default: `moment(to_date_default).subtract(1, "month").startOf("month")`.
- `_context()` gains `from_date`, sent only when the template is GL. The preview, download and
  email calls all pass it.
- Client guard: when From Date is after To Date, disable Download and Email and show a hint
  instead of the preview.
- Server: `_build_statement_doc(customer, company, template, as_of_date=None, from_date=None)`.
  - GL with `from_date` set: `from_date = getdate(from_date)`, `to_date = as_of`.
  - GL without `from_date`: the current `filter_duration` fallback stays, so klik_pos is unaffected.
  - GL with `from_date > to_date`: `frappe.throw`, because the server can't trust the client.
  - AR: `from_date` is ignored.
- `render_statement_html`, `download_statement` and `email_statement` gain `from_date=None` and
  pass it through.

**Risks**
- Frappe runs `onchange` while it applies defaults during Dialog construction. The existing
  `if (!this.dialog) return` guard in `_sync_fields` already handles that.
- A stale preview after a template switch is already handled by the preview sequence number.
- Timezone: `moment()` in Frappe desk uses the browser's local date, the same as
  `frappe.datetime.get_today()`, which the dialog already uses.

**Acceptance criteria**
1. Choosing a GL template shows From Date and To Date, with From = 2026-08-01 by default. The
   preview, PDF and email cover exactly that range.
2. Choosing an AR template shows only Posting Date.
3. The transaction list shows only "As of" and behaves as before.
4. From Date after To Date blocks the actions in the dialog and throws on the server.
5. klik_pos's signature-binding test still passes, and existing callers that send only
   `as_of_date` get today's behaviour.

## Plan

Branch: `feat/statement-gl-date-range` off `main`.

1. **Tests first** (`tests/test_statement_of_accounts.py`), confirmed failing before any change:
   - `test_gl_template_honours_explicit_from_date`: `to_date = as_of`, `from_date` = the value given.
   - `test_gl_template_without_from_date_keeps_filter_duration_fallback`: rename the existing
     GL test so it states the backward-compatibility rule.
   - `test_gl_template_rejects_from_date_after_to_date`: expects `ValidationError`.
   - `test_ar_template_ignores_from_date`: `posting_date` set, template `from_date` left as it was.
   - `test_render_statement_html_forwards_from_date`: patch `_render_html` and read the built doc.
   - `test_single_statement_endpoints_accept_from_date_optionally`: bind the signatures with and
     without `from_date`.
2. **Server** (`statement_of_accounts.py`): the `_build_statement_doc` change and the endpoint
   parameters described above, plus the docstring and date-mapping comment.
3. **Dialog** (`statement_dialog.js`): add the `from_date` field, relabel and toggle in
   `_sync_fields`, add a `_template_report()` helper, send `from_date` in `_context` and in all
   three calls, and add the From-after-To guard.
4. **Design doc**: update the "Date mapping" section of
   `single_customer_statement_of_accounts-design.md`.
5. **Verify**
   - `bench --site dev.localhost run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.tests.test_statement_of_accounts`
   - `bench --site dev.localhost run-tests --app klik_pos --module klik_pos.tests.test_statement_delegation`
   - `ruff check` and `ruff format --check` on the changed Python files
   - `bench build --app cecypo_frappe_reports`
   - `/browse` on dev.localhost → Transaction History → Receivables → a Dev Co customer's
     Statement button:
     - "GL" template: From/To visible, From = 2026-08-01, preview header shows the range.
     - "AR" template: only Posting Date.
     - Transaction list: only As of.
     - From after To: buttons disabled.
     - Take screenshots of each.
   - The Accounts Receivable report button opens the same dialog and follows the same rules.
6. **Review pass** (Blocker / Major / Minor / Nit), saved as
   `statement_dialog-gl_date_range-review.md`.
7. **Land**: merge into `main`. I will **ask before pushing**, because this app isn't on the
   standing push list in CLAUDE.md.

## Open question for approval

When a caller sends no `from_date` (klik_pos POS today), should the server fallback **stay** at
`to_date − filter_duration months` (recommended: POS behaviour doesn't change), or should it
**also** switch to the first day of the previous month?
