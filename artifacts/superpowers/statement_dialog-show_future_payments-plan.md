# Statement dialog ignores "Show Future Payments" — plan

## Root cause
The branded Statement of Accounts is an in-memory clone of a PSOA template record
(`_build_statement_doc`). The clone keeps the template's own `show_future_payments`; ERPNext passes
it to the print format as `filters.show_future_payments` (process_statement_of_accounts.py:311),
which decides the Future Payment column. Nothing passes the page's checkbox down: the Transaction
History Statement button, `cecypo_reports.statement.open`, `_statement_args` and the three
endpoints have no such parameter. A template saved with the box ticked (RIOS `AR`) therefore always
shows the column.

Same gap on the Statement of Accounts button of the Accounts Receivable / AR Summary reports, both
of which have a `show_future_payments` filter.

## Change
1. `statement_of_accounts.py`: optional `show_future_payments=None` on `_build_statement_doc`,
   `render_statement_html`, `download_statement`, `email_statement`. `None` = keep the template's
   value (klik_pos, bulk send and PSOA batch unchanged); otherwise `doc.show_future_payments = cint(v)`.
   Optional kwarg, so no STATEMENT_API_VERSION bump.
2. `statement_dialog.js`: accept `opts.show_future_payments`; `_statement_args` adds it when defined.
3. `transaction_history.js`: Statement button passes `this._recv_state.show_future_payments ?? 0`
   (the value the receivables table was loaded with).
4. `report_statement_button.js`: pass `report.get_filter_value("show_future_payments", false)`.

## Tests (TDD)
- `test_statement_of_accounts.py`: template with `show_future_payments=1`;
  `_build_statement_doc(..., show_future_payments=0)` → 0; `None` → template value kept;
  all three endpoints forward it (same pattern as `test_single_statement_endpoints_forward_from_date`).
  Red first, then green.

## Verify
- `bench --site dev.localhost run-tests --module cecypo_frappe_reports.cecypo_frappe_reports.tests.test_statement_of_accounts`
- Browser on dev: Transaction History → Receivables, unchecked → Statement preview has no Future
  Payment column; checked → column shown.
- Versioned include in hooks.py bumped so Cloudflare serves the new JS.
- Land: merge to main, push `upstream/main`. RIOS gets it on its next app update (not deployed by me).
