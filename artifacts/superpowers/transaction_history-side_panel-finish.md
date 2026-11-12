# Finish: Transaction History links open the side panel

- Commit on feat/th-side-panel, merged to local main (not pushed: cecypo_frappe_reports is not in the
  auto-push list; awaiting user OK for upstream/main).
- Change: one delegated click handler in _bind_tabs (transaction_history.js, +14 lines).
- Browser (dev.localhost, Customer History, Walk In / Dev Co):
  - item link /app/item/F050 -> side panel Item F050, no new tab
  - invoice link /app/sales-invoice/POS-01918 -> side panel Sales Invoice POS-01918, row stays expanded
  - Ctrl-click same link -> new tab /desk/sales-invoice/POS-01918
  - no console errors
- Tests: test_transaction_history on test.localhost: 55 run, 4 failures + 3 errors in Python
  permission/receivable tests. Diff is JS-only, so they come from the test site (new today,
  counts drift between runs), not from this change.

## Review
- Minor: a click on an item-code link inside a summary row no longer also expands the row
  (stopPropagation). Intended: the click opens the preview.
- Nit: the old page JS is cached in open browser tabs until a reload (page JS is not under /assets, so no Cloudflare cache issue).
