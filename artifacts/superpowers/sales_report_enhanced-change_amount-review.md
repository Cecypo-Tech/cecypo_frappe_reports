# Sales Report Enhanced — change amount / rounding fix (review)

## Verification
- `bench --site dev.localhost run-tests --module ...sales_report_enhanced.test_sales_report_enhanced` → 7/7 OK
- `ruff check` clean; new test file formatted (remaining `ruff format` diffs in
  sales_report_enhanced.py are pre-existing, untouched lines)
- execute() over all Dev Co invoices, per-row Grand − Outstanding − Σmodes:
  before 38 rows off (summary gap −224.05), after 4 rows off (summary gap −6.00)
- Prod 2026-10-01 (read-only): whole gap 9,339.50 = 9,340 change − 0.50 rounding,
  both handled by this fix

## Findings
- Blocker: none
- Major: none
- Minor (pre-existing, out of scope): Payment Entries without mode_of_payment are
  skipped; refunds of returns via "Pay" Payment Entries are not counted (only
  "Receive"); invoices with corrupt outstanding (dev POS-00009) still don't reconcile.
- Minor (open): allparts-tests INV-00038 / INV-X00001 return pair looks double
  counted; needs that site's data (FAC_Allparts connector points at prod).
- Nit: if change exceeds the chosen row's tendered amount, that mode goes negative —
  still reconciles, acceptable.
