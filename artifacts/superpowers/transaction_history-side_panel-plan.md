# Plan: Transaction History links open Frappe's side panel

## Goal
Clicking a voucher / item / payment link anywhere on the Transaction History page opens
Frappe v16's side panel preview (`frappe.ui.get_side_panel().open(doctype, name)`) instead of a new tab.

## Findings
- 9 link sites in transaction_history.js, all `<a href="/app/<slug>/<name>" target="_blank">`,
  all rendered inside `this.page.main` (stock card, customer/supplier history, receivables,
  payables, payment entries, item codes, pricing).
- Frappe's own report wiring: `frappe.ui.handle_link_cell_click` (report.bundle.js, loaded in every
  desk page) + lazy `frappe.require("side_panel.bundle.js")`. It is tied to datatable columns, so
  it can't be reused directly; `frappe.ui.split_view_enabled()` can.
- Slug -> doctype: `frappe.router.routes[slug].doctype`.

## Change (one file, ~15 lines)
One delegated handler in the existing `$(m).on("click", ...)` block:
- match `a[href^="/app/"]`, plain left-click only (Ctrl/Cmd/Shift/middle-click still opens a new tab)
- skip when `frappe.ui.split_view_enabled()` is false (mobile, or user turned off "Report Split View")
- parse slug + name from the href, map slug to doctype, `preventDefault`, require bundle, open panel
- leave the per-link markup untouched (hrefs stay as the no-JS / new-tab fallback)

## Verification
- Browser (dev.localhost): Item History stock card, Customer History, Receivables, Payables,
  Payment Entries, Pricing: plain click opens side panel; Ctrl-click opens new tab.
- `bench --site test.localhost run-tests --module cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.test_transaction_history`
  (Python untouched; regression only). No JS test harness in this app.
