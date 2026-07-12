# Fix: Party-Info Dialog "Total Outstanding" Disagrees With Main Grid

## Brainstorm

**Goal:** The ⓘ party-info dialog and the Receivables/Payables grid must always show the same
"Total Outstanding" figure for the same party, as-of-date, and Show-Future-Payments state.

**Observed bug:** For Commercial Customer on dev.localhost (as_of 2026-07-12, toggle off), the
grid shows **44,238** while the dialog shows **41,054**.

**Root cause (verified against live data via bench console):**

- Grid (`_get_party_balances`, `transaction_history.py:673`) delegates to ERPNext's
  `accounts_receivable`/`accounts_payable` report engine — single source of truth established by
  the July 11 AR/AP delegation refactor. It respects `as_of_date` and `show_future_payments`.
- Dialog (`get_party_details` → `stats.total_unpaid`, `transaction_history.py:459-499`) still uses
  the pre-refactor bespoke query: `SUM(Sales Invoice.outstanding_amount)` over ALL submitted
  invoices, with no date filtering at all.
- These diverge because:
  1. `Sales Invoice.outstanding_amount` is a live field — it's reduced the instant a Payment Entry
     is submitted and allocated, *regardless of the PE's posting date*. So the dialog's sum already
     "sees" a future-dated allocated payment that the as-of-date-aware grid correctly excludes
     (or, even with the toggle on, only annotates as `future_amount` rather than netting into
     `outstanding` — an inherent asymmetry in ERPNext's own report engine for *allocated* future
     payments).
  2. The dialog's sum only touches Sales/Purchase Invoice rows, so it silently excludes
     *unallocated* advance Payment Entries — while the grid's `outstanding` nets those in as
     negative-outstanding voucher rows.
- Confirmed via `bench --site dev.localhost console`:
  - `_get_party_balances(..., show_future_payments=0)` → outstanding = 44238
  - `_get_party_balances(..., show_future_payments=1)` → outstanding = 41563
  - `get_party_details(...)["stats"]["total_unpaid"]` → 41054 (matches raw
    `SUM(Sales Invoice.outstanding_amount)`, confirmed by direct SQL)
  - The 509 residual gap between 41563 and 41054 traces to `INV-00001`, which has a
    future-dated (2026-07-31) Payment Entry allocation of 7196 already reflected in its live
    `outstanding_amount` field, but reported only as `future_amount` (not netted into
    `outstanding`) by ERPNext's AR report even with `show_future_payments=1`.
- Separately, the click handler for `.th-party-info-btn` (both the grid-row icon and the
  drill-down-header icon) never passes `as_of_date` / `show_future_payments` to
  `get_party_details` at all — so even after delegating to the same engine, the dialog can't match
  whatever as-of-date/toggle state the user currently has selected unless we thread those through.

**Constraints:**
- Must not change the *meaning* of `_get_party_balances`'s `outstanding` (used elsewhere,
  tested, matches ERPNext's own AR/AP report — this is correct and shouldn't move).
- `annual_billing`, `lifetime_billing`, `last_transaction`, `credit_limit` in the dialog are a
  different concept (gross billing stats, not as-of-date outstanding) — out of scope, leave as-is.
- The dialog currently shows a 2-tier "Total Outstanding → minus Unallocated Advance → Net
  Payable" breakdown. Once `total_unpaid` is sourced from `_get_party_balances`, its `outstanding`
  field *already* nets unallocated advances in (see `_get_party_balances`, line ~726: PE/JE rows
  with negative outstanding are subtracted into the party total). Subtracting `unallocated_total`
  a second time would double-count. The "Total Outstanding" label is already used with the *net*
  meaning elsewhere in this UI (the customer-drilldown 3-col stat card at line 1632 — also labeled
  "Total Outstanding" — shows `r.outstanding`, the net figure). So the dialog must adopt the same
  net meaning for consistency, not invent a second "gross" concept under the same label.

**Acceptance criteria:**
1. Opening the party-info dialog from a grid row shows the exact same "Total Outstanding" figure
   as that row's "Outstanding" column, for whatever `as_of_date` / `show_future_payments` state
   the grid is currently in.
2. Opening the dialog from the customer/supplier drill-down view (after clicking into a single
   party) matches that view's "Total Outstanding" stat card the same way.
3. The "Unallocated Advance" figure continues to display (informational), but "Net Payable" is
   removed since it's now identical to "Total Outstanding" (no more double subtraction).
4. No regression to `annual_billing` / `lifetime_billing` / `last_transaction` / `credit_limit` /
   contacts / address / unallocated-payments-table sections of the dialog.
5. Existing tests for `_get_party_balances`, `get_receivables`, `get_payables` etc. still pass
   unmodified (their contract doesn't change).

**Risks:**
- `get_party_details` is also called by `_show_email_dialog` (line 2047) purely for
  `primary_email` — must not break that caller, which doesn't pass `as_of_date`/`show_future`.
- Need `party_type` normalization: `get_party_details` takes `"customer"/"supplier"` (lowercase)
  while `_get_party_balances` takes `"Customer"/"Supplier"` (titlecase) — must map correctly.

---

## Plan

### Step 1: Backend — thread as-of-date/show-future into `get_party_details`, source total_outstanding from the AR/AP engine

**File:** `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py`

- [ ] Change `get_party_details(party_type, party, company=None)` signature to
      `get_party_details(party_type, party, company=None, as_of_date=None, show_future_payments=0)`.
- [ ] Default `as_of_date` to `nowdate()` when not supplied (keeps the `_show_email_dialog` caller,
      which omits it, working — it only reads `primary_email`).
- [ ] Replace the bespoke `stats["total_unpaid"]` computation: when `company` is provided, call
      `_get_party_balances(party_type="Customer" if is_customer else "Supplier", company=company,
      as_of_date=as_of_date, party=party, show_future_payments=show_future_payments)`, take the
      single matching row, and set:
      - `stats["total_unpaid"] = row["outstanding"] if row else 0.0`
      - keep `unallocated_total` as already computed (still needed for the informational line) —
        verify it now equals `row["unallocated_advance"]` and use whichever is simpler (prefer
        reusing the existing `adv_rows` query already in the function to avoid a second dependency
        on report internals for that number, since the info table below it needs the row-level PE
        list anyway).
- [ ] If `company` is not provided (only the email-dialog caller omits args, and it does pass
      company from `$wrap.data("company")`) — verify company is always available before relying on
      it; if any caller can omit it, fall back to the old bespoke sum in that case only.
- [ ] Keep `annual_billing`/`lifetime_billing`/`last_transaction`/`credit_limit` untouched.

### Step 2: Frontend — pass as_of_date/show_future_payments to `get_party_details`, drop double subtraction

**File:** `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.js`

- [ ] Add `data-as-of` and `data-show-future` attributes to both `.th-party-info-btn` render sites:
      - grid row icon (customer: line 1714, supplier: line 2230)
      - drill-down header icon (customer: line 1651, supplier: ~2167)
      Value: the `as_of_date` already in scope at render time, and
      `this._recv_state.show_future_payments` / `this._pay_state.show_future_payments`
      (0/1) respectively.
- [ ] Update the `.th-party-info-btn` click handler (line 1206) to read `data-as-of` and
      `data-show-future` and pass them into `_show_party_info_dialog(...)`.
- [ ] Update `_show_party_info_dialog(party_type, party, company, as_of_date, show_future_payments)`
      to include those in the `frappe.call` args.
- [ ] Remove the `adv_net` double-subtraction (line 1918: `stats.total_unpaid - unallocated_total`).
      Keep the "Unallocated Advance" info banner (line 1953-1959) but simplify it to a single
      informational line — no second "Net Payable" figure, since `stats.total_unpaid` is now
      already net.

### Step 3: Tests

**File:** `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/test_transaction_history.py`

- [ ] Add a regression test reproducing this exact scenario: a customer with (a) a fully-allocated
      past-dated invoice, (b) an invoice partially paid by a *future-dated* Payment Entry, and
      (c) a separate fully-unallocated future-dated advance Payment Entry. Assert
      `get_party_details(...)["stats"]["total_unpaid"]` equals
      `get_receivables(..., customer=X)[0]["outstanding"]` for matching `as_of_date` /
      `show_future_payments` — i.e., dialog and grid must never disagree.
- [ ] Run full suite: `bench --site <test-site> run-tests --app cecypo_frappe_reports` (or the
      module-scoped equivalent used in prior sessions) — confirm no regressions.

### Step 4: Manual verification on dev.localhost

- [ ] Reproduce original report: open Commercial Customer's ⓘ dialog from the grid row with
      toggle off — dialog must now show 44,238, matching the grid.
- [ ] Toggle "Show Future Payments" on, reopen the dialog — both grid and dialog must show 41,563.
- [ ] Spot-check a party with zero unallocated advances to confirm no visual regression (banner
      correctly hidden, single total shown).

---

## Verification commands

```bash
bench --site dev.localhost run-tests --app cecypo_frappe_reports
ruff check cecypo_frappe_reports/
```
