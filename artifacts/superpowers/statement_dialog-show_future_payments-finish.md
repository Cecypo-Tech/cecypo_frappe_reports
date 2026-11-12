# Finish — statement dialog "Show Future Payments"

Branch `fix/statement-show-future-payments` (2 commits on top of main 8e1ca04): 3b0558f, 169f3d0. Not merged or pushed yet.

## Summary
The single-customer statement clones a PSOA template and kept its saved `show_future_payments`, so a
template saved with it ticked always printed the Future Payment column. Now:
- `statement_of_accounts.py`: `_build_statement_doc`, `render_statement_html`, `download_statement`,
  `email_statement` take optional `show_future_payments`; given → overrides the clone; None → template value.
- `statement_dialog.js`: forwards `opts.show_future_payments` on preview, download and email.
- `transaction_history.js`: Statement button passes the value the table was loaded with.
- `report_statement_button.js`: AR / AR Summary pass their `show_future_payments` filter.

## Verification
- `bench --site dev.localhost run-tests --module cecypo_frappe_reports.cecypo_frappe_reports.tests.test_statement_of_accounts`
  → 79 OK (1 skipped, PDF probe). 3 new tests were red before the fix.
- Node check of `_statement_args` (scratchpad) → passes; fails against HEAD.
- Dev render, template "AR - Future Payments" (saved =1): None → column shown, 0 → hidden, 1 → shown.
- `node --check` on all three JS files.

## Review
- Blocker: none.
- Major: none.
- Minor: no browser click-through (desk session for Playwright was blocked). Manual check below.
- Minor: GL templates — ERPNext's General Ledger ignores show_future_payments, and the "(Future Payments)"
  GL print formats show the column unconditionally, so the checkbox has no effect on GL statements. Pre-existing.
- Nit: ruff I001 and format diffs in statement_of_accounts.py / the test file are pre-existing, untouched.

## Manual validation
1. Transaction History → Receivables, "Show Future Payments" unticked → Refresh → Statement on a customer
   → preview has no Future Payment column; Download / Email PDF likewise.
2. Tick it, Refresh, repeat → column shown.
3. Accounts Receivable report → toggle its "Show Future Payments" filter → Statement of Accounts button follows it.

## Follow-ups
- Land: merge to main and push `upstream/main` (needs the user's go-ahead; this app is not on the default-push list).
- Sites get it on their next app update.
