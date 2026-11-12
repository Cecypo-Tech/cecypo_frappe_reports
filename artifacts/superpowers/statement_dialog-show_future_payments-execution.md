# Execution — statement dialog "Show Future Payments"

Plan: artifacts/superpowers/statement_dialog-show_future_payments-plan.md (approved 2026-11-10 via /superpowers-execute-plan)
Branch: fix/statement-show-future-payments

## Step 1 — server override (TDD)
- Files: statement_of_accounts.py, tests/test_statement_of_accounts.py
- `_build_statement_doc` takes `show_future_payments=None`; when given, `doc.show_future_payments = cint(v)`; None keeps the template value.
- `render_statement_html`, `download_statement`, `email_statement` accept and forward it (last kwarg, positional callers unaffected).
- 3 tests: override both ways, omitted keeps template, all three endpoints forward.
- Red first: 2 errors (unexpected kwarg); omitted-keeps-template passed (current behaviour).
- Verify: `bench --site dev.localhost run-tests --module cecypo_frappe_reports.cecypo_frappe_reports.tests.test_statement_of_accounts` → 79 tests OK (1 skipped: PDF probe).
- ruff: I001 import order and format diffs are pre-existing in untouched lines (confirmed against HEAD); nothing new.

## Step 2 — statement_dialog.js
- `opts.show_future_payments` documented; `_statement_args` sends it (0/1) only when the caller supplied it, so preview, download and email all carry it.
- Verify: throwaway node check (scratchpad `dialog_args_check.mjs`, loads the file with frappe stubs) → passes; same check against HEAD fails with "unticked -> 0".

## Step 3 — transaction_history.js
- Statement button passes the loaded tab state's `show_future_payments` (receivables or payables state).
- Verify: `node --check` OK.

## Step 4 — report_statement_button.js
- AR / AR Summary button passes `report.get_filter_value("show_future_payments", false)`.
- Verify: `node --check` OK.
- Plan's "bump versioned include" not needed: hooks.py `_asset_version` appends the file mtime automatically.

## End-to-end (dev, real template "AR - Future Payments", saved with show_future_payments=1)
- render_statement_html(..., show_future_payments=None) → Future Payment header present (old behaviour, unchanged for klik_pos/bulk)
- show_future_payments=0 → header absent; =1 → present.
- Browser click-through not run: creating a desk session for Playwright was blocked by the permission classifier.
