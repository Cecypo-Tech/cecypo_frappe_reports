# Transaction History — Show Advance-Only Accounts in Payables/Receivables

## Goal

Suppliers/customers whose only activity is an unallocated advance payment
(no outstanding invoice) currently do not appear anywhere in the Payables
or Receivables tabs of the Transaction History page. Make them visible.

## Background

`get_payables` and `get_receivables` in `transaction_history.py` build their
party list in two steps:

1. Query outstanding invoices (`outstanding_amount > 0`) and group into an
   `agg` dict keyed by party — this is the only source of parties in the
   result.
2. Query unallocated advances (`Payment Entry.unallocated_amount > 0`) and
   attach the total onto `agg[party]` — but only for parties that already
   exist in `agg` from step 1.

A party with an advance but zero outstanding invoices never gets a key in
`agg`, so it's silently omitted from the report — not just under-reported.

## Decisions

- **Display:** advance-only parties appear as a normal row in the summary
  table with `outstanding = 0` and all aging buckets = 0. No netting against
  outstanding, no separate toggle — always shown.
- **No frontend changes needed.** `transaction_history.js` already renders
  `—` for zero bucket/outstanding values and already flags any row with
  `unallocated_advance > 0` via an info icon (receivables:
  `transaction_history.js:1699-1708`; payables has the equivalent block).
  Sort is by `outstanding` desc, so these rows naturally sink to the bottom.
- **Related bug fixed in the same change:** the unallocated-advance queries
  (`transaction_history.py:337-349` receivables, `480-493` payables) don't
  filter by `posting_date <= as_of`, so an advance posted after the report's
  "as of" date would incorrectly appear. Adding that filter matters more now
  that advance-only rows are visible on their own (previously the bug only
  skewed a total that was attached to a row already shown for other reasons).

## Implementation

### `get_receivables` (and symmetrically `get_payables`)

1. Add `.where(pe.posting_date <= as_of)` to the `adv_q` advance query.
2. Left-join `Customer` (`Supplier` for payables) into `adv_q` and select
   `customer_group` (`supplier_group`) so advance-only rows get a populated
   group column, matching invoice-sourced rows.
3. After the existing `agg` build loop (which processes invoice rows) and
   before the final `for cust_name, data in agg.items():` loop, add:
   for every party in the advance results not already in `agg`, initialize
   `agg[party]` (the `defaultdict` factory already zeroes every field) and
   set `customer`/`customer_group` (`supplier`/`supplier_group`) from the
   advance query row.
4. No other changes — the existing final loop already attaches
   `last_payment`, `unallocated_advance`, and (for receivables)
   `future_payments` to every key present in `agg`, so newly-added
   advance-only parties get these for free.

### Files touched

- `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py`
  — `get_receivables`, `get_payables`.
- `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/test_transaction_history.py`
  — new regression tests (see Testing).

## Out of Scope

- No change to `get_receivables_detail`/`get_payables_detail` (invoice
  drill-down) — correctly empty for advance-only parties since there are no
  invoices to list.
- No change to `get_party_details` — it already computes unallocated
  advances independently of any invoice list.
- No frontend/JS changes.
- No change to how advances are allocated/applied — this is a visibility
  fix only.

## Testing

Add regression tests to `test_transaction_history.py`:

- `test_get_payables_includes_advance_only_supplier`: create a `Payment
  Entry` (Pay, no invoice references, `unallocated_amount > 0`) against a
  test supplier with no outstanding Purchase Invoice. Call `get_payables`
  and assert the supplier is present with `outstanding == 0` and
  `unallocated_advance > 0`.
- `test_get_receivables_includes_advance_only_customer`: same shape for
  `get_receivables` / Payment Entry (Receive) / customer.
- `test_get_payables_excludes_future_dated_advance`: create an advance
  posted after `as_of_date`; assert it does NOT appear when querying with
  an earlier `as_of_date` (covers the date-boundary fix).

Before adding these, check whether `TestTransactionHistoryPage` needs to
switch from `unittest.TestCase` to `frappe.tests.utils.FrappeTestCase` so
the Payment Entry fixtures created in each test are rolled back afterward
rather than persisting in the test database.

Manual verification:

1. `bench --site <site> migrate` (no schema change, but confirm no import
   errors).
2. In the Transaction History page, Payables tab: pick a company/as-of-date
   where a supplier has an unallocated advance and no outstanding PI.
   Confirm the supplier now appears with Outstanding = 0 and the
   advance-flag info icon.
3. Repeat for a customer on the Receivables tab.
4. Confirm a supplier/customer with an advance posted *after* the selected
   as-of-date does NOT appear (or does not count that advance) when using
   an earlier as-of-date.
