## Transaction History: delegate Receivables/Payables balances to ERPNext's AR/AP report engine

### Problem

`get_receivables()` / `get_payables()` in `transaction_history.py` compute "Total Outstanding" by summing `Sales Invoice.outstanding_amount` / `Purchase Invoice.outstanding_amount` directly, plus a separate, never-netted "unallocated advance" figure. Comparing this against ERPNext's own `Accounts Receivable` report (the data source the `PSOA AR Statement` print format uses) for a real customer exposed two compounding bugs, not just "future payments missing":

1. **Credit notes / returns are invisible.** A return Sales Invoice with negative `outstanding_amount` fails our `outstanding_amount > 0` filter, so it never reduces the customer's total. ERPNext's report includes it as a negative ledger line.
2. **"As of" leaks live state.** `outstanding_amount` is a live field — it already reflects any submitted payment allocation regardless of that payment's date. So when a future-dated Payment Entry is allocated to a specific invoice, our report shows that invoice's outstanding as already reduced, even when reporting "as of" an earlier date. ERPNext's report walks Payment Ledger Entries with a hard `posting_date <= report_date` cutoff and only reveals the future reduction through an opt-in `future_amount` column — the row's own `outstanding` stays at the pre-reduction value.

These two errors partially cancelled out in the observed case (49,232 shown vs. 41,563 correct), which is why it looked like a single missing feature rather than two separate defects.

Patching our own SQL to also handle returns/credit notes and date-consistent ledger walking means re-deriving ERPNext's `ReceivablePayableReport` (`erpnext/accounts/report/accounts_receivable/accounts_receivable.py`) by hand. That class already handles this correctly (it's also symmetric for payables — `accounts_payable.py` is a two-line wrapper around the same class with `account_type="Payable"`).

### Decision

`get_receivables`, `get_receivables_detail`, `get_payables`, `get_payables_detail` will call ERPNext's own report module functions —

```python
from erpnext.accounts.report.accounts_receivable.accounts_receivable import execute as ar_execute
from erpnext.accounts.report.accounts_payable.accounts_payable import execute as ap_execute
```

— to get ledger-correct per-voucher rows, then group/reshape those rows into the same JSON shapes the frontend already consumes. No JS changes are required for Receivables. Payables gains the "Show Future Payments" checkbox and per-invoice "Future Payment" column that Receivables already has, for parity (both tabs currently expose an `as_of_date`/company/party filter set that maps directly onto `report_date`/`company`/`party`).

### Filter mapping

| Our param | AR/AP report filter |
|---|---|
| `company` | `company` |
| `as_of_date` | `report_date` |
| `customer` / `supplier` | `party` (must be passed as a list: `[customer]`) — omit for "all parties" |
| (new) `show_future_payments` on Payables | `show_future_payments` |
| — | `party_type`: `"Customer"` for receivables, `"Supplier"` for payables |

`frappe.has_permission("Sales Invoice"/"Purchase Invoice", "read", throw=True)` stays as an explicit guard before calling into the report, same as today.

### Row shape returned by `execute()`

One row per voucher (or per payment-term split, or per unallocated Payment/Journal Entry). Relevant fields: `party`, `voucher_type` (`Sales Invoice`/`Purchase Invoice`/`Payment Entry`/`Journal Entry`), `voucher_no`, `posting_date`, `due_date`, `invoiced`, `paid`, `credit_note`, `outstanding`, `future_amount` (present only when `show_future_payments` is truthy), `range0`..`range5` (aging, given the default `range` filter of `"30,60,90,120"`), `customer_group`/`supplier_group`, `party_account`. No `status` field — see below.

### Rebuilding `get_receivables`/`get_payables`

Group rows by `party`:
- `total_invoiced` = `sum(invoiced)`, `total_paid` = `sum(paid)` (matches current field names/semantics).
- `outstanding` = `sum(outstanding)` — this is now the ledger-correct, netted figure (includes credit notes and, when the toggle is on, future payments), replacing the old `sum(outstanding_amount) + separate unallocated_advance` split.
- Aging buckets: `bucket_0_30 = range0 + range1`, `bucket_31_60 = range2`, `bucket_61_90 = range3`, `bucket_90_plus = range4 + range5` (range0 is "not yet due", which our existing `_calculate_aging_bucket` already folds into `bucket_0_30` — same convention, kept for continuity).
- `last_payment` = `max(posting_date)` among rows where `voucher_type in ("Payment Entry", "Journal Entry")` for that party. This now automatically respects the toggle: future-dated Payment/Journal Entries only appear in `data` at all when `show_future_payments` is on, so no separate date filter is needed on our side.
- `unallocated_advance` = `sum(-outstanding)` among `Payment Entry`/`Journal Entry` rows with `outstanding < 0` for that party (an unallocated/unapplied payment shows up as its own negative ledger row). Kept as a separate figure in the response (still surfaced in the party-info popover), even though it's now already folded into `outstanding` — this preserves the existing "Unallocated Advance / Net Payable" popover.
- The "advance-only party" seeding loop (added earlier for the advance-only bug) is no longer needed — parties whose only ledger activity is an unallocated advance already get a row and a correct (negative-only) `outstanding` from the AR/AP data directly.

### Rebuilding `get_receivables_detail`/`get_payables_detail`

Filter the same `execute()` rows (scoped to a single `party` in the filters, as today) to `voucher_type == "Sales Invoice"` (or `"Purchase Invoice"`) to build the per-invoice table: `date` (`posting_date`), `voucher_no`, `grand_total` (`invoiced`), `paid`, `outstanding_amount` (`outstanding`), `due_date`, `future_amount` (pass through when present), `days_overdue` (computed the same way as today, from `due_date`).

`status` isn't in the AR/AP row — one extra lightweight lookup (`frappe.db.get_all("Sales Invoice", filters={"name": ["in", voucher_nos]}, fields=["name", "status"])`, mirroring what today's query already implicitly relied on) fills that column in, same as the current UI expects (Overdue/Unpaid/Partly Paid/Paid/Return pill).

### Non-goals

- No changes to Item History / Customer History / Supplier History / Pricing tabs.
- No changes to the PSOA print formats themselves, or to `cecypo_frappe_reports/utils.py::get_future_payments_by_invoice` — that utility is still used independently by the `PSOA GL Statement (Future Payments)` print format and must keep working as-is.
- Not attempting to reproduce every AR/AP report filter (sales person, payment terms, etc.) — only the filters Transaction History already exposes.

### Testing

All 6 existing `test_get_receivables_*`/`test_get_payables_*` tests that assert on `outstanding`/`unallocated_advance` will need their expected values re-derived against the new ledger-correct numbers (some may still hold, some won't — e.g. the advance-only tests should still pass since AR/AP naturally produces a row for advance-only parties). New regression tests will be added for: a credit note/return invoice being netted correctly, and the future-payment toggle producing the same 44,238 → 41,563-style netting shown in this investigation. Existing per-invoice detail tests get updated for the new `status` lookup path.

### Risk

`ReceivablePayableReport` is more expensive per call than our lean SQL (it processes Payment Ledger Entries, not just invoice tables). For the party-scoped calls (`get_receivables_detail`, `get_payables_detail`, and `get_receivables`/`get_payables` when a `customer`/`supplier` filter is given) this is a single party's ledger — cheap. The unscoped "all customers/suppliers" list view calls it with no `party` filter, which is heavier (whole company's ledger) — worth confirming performance on a real dataset size during implementation, but this is the same cost the standard `Accounts Receivable`/`Accounts Payable` reports already pay today, so it's not introducing a new class of slowness to the system.
