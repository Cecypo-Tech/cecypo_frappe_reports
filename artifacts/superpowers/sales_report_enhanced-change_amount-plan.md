# Sales Report Enhanced — totals don't reconcile (plan)

## Bug
Outstanding + payment-mode columns != Grand Total (allparts-tests, 2026-10-01: payments
exceed by 4,140). Reconciled on prod for the same day: gap 9,339.50 = 9,340 change
handed back on 31 POS invoices − 0.50 rounding on CS-00162.

## Root causes
1. `get_payment_map` sums `Sales Invoice Payment.base_amount` — the amount *tendered*.
   `base_change_amount` (booked against `account_for_change_amount`) is never deducted.
2. Grand Total uses `base_grand_total`; outstanding is based on the rounded total.

## Steps
1. Regression tests (pure functions, no fixtures):
   - change is netted off the row on the change account / Cash type / largest row
   - Grand Total uses `base_rounded_total`, falling back to `base_grand_total`
   Run → must fail.
2. `get_invoices`: select `base_rounded_total`, `base_change_amount`, `account_for_change_amount`.
3. `get_payment_map(invoices)`: group SIP by parent/mode/account/type; new pure helper
   `get_direct_payments(rows, invoices)` nets change.
4. `get_data`: grand_total = base_rounded_total or base_grand_total.
5. Verify: tests green; ruff; reconcile every row of `execute()` on dev.localhost.

## Out of scope
INV-00038 / INV-X00001 return pair on allparts-tests — needs that site's data.
