# Sales Report Enhanced: optional Remarks column (2026-10-03)

## Mini-plan (small change)
1. Add an "Include Remarks" Check filter (default 0) in sales_report_enhanced.js.
2. Select `si.remarks`; `get_columns(..., include_remarks)` appends a "Remarks" (Small Text, 250) column last; `get_data(..., include_remarks)` fills `remarks`.
3. Tests first, in test_sales_report_enhanced.py.

## Verification
- `bench --site dev.localhost run-tests --module cecypo_frappe_reports.cecypo_frappe_reports.report.sales_report_enhanced.test_sales_report_enhanced`: RED (2 errors: the unexpected keyword), then GREEN 16/16.
- Real data on dev, with a temporary remark on POS-01623 (rolled back):
  - off: no column;
  - on: last column "Remarks", POS-01623 shows its remark, the other rows are blank.
- Browser `/desk/query-report/Sales Report Enhanced`: the checkbox shows unticked; ticking it reruns the report with Remarks as the last column; no console errors.
- ruff check clean. Formatter reflows of two untouched query chains were reverted, so the diff holds only this change.

## Review
- Blocker / Major: none.
- Minor: Small Text renders without escaping (Frappe `Text` formatter). Remarks are sanitised by Frappe on save, as the invoice form shows them the same way. Accepted.
- Nit: dev has no invoices with remarks, hence the temporary value for the check.
