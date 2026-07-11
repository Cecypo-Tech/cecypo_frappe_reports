# Transaction History AR/AP Delegation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the bespoke SQL balance computation in Transaction History's Receivables/Payables tabs with ERPNext's own `ReceivablePayableReport` engine, so totals always match the standard `Accounts Receivable`/`Accounts Payable` reports (and the PSOA AR Statement print format), including credit notes/returns and date-consistent future-payment handling.

**Architecture:** `get_receivables`/`get_payables`/`get_receivables_detail`/`get_payables_detail` in `transaction_history.py` call `erpnext.accounts.report.accounts_receivable.accounts_receivable.execute(filters)` / `erpnext.accounts.report.accounts_payable.accounts_payable.execute(filters)`, then group/reshape the returned per-voucher rows into the existing response shapes the frontend already consumes. Payables gains a `show_future_payments` param + UI checkbox for parity with Receivables.

**Tech Stack:** Frappe/ERPNext v15, Python, `frappe.qb`/pypika not needed here (delegating to erpnext's own query layer), existing JS page structure.

## Global Constraints

- Backend response shapes for `get_receivables`/`get_payables` (`customer`/`supplier`, `customer_group`/`supplier_group`, `total_invoiced`, `total_paid`, `outstanding`, `bucket_0_30`, `bucket_31_60`, `bucket_61_90`, `bucket_90_plus`, `last_payment`, `unallocated_advance`, `future_payments` (receivables only)) must not change — no JS changes needed for Receivables' existing fields.
- `get_receivables_detail`/`get_payables_detail` response shape (`date`, `voucher_no`, `grand_total`, `paid`, `outstanding_amount`, `due_date`, `status`, `days_overdue`, `future_amount`) must not change.
- Do not touch `cecypo_frappe_reports/utils.py::get_future_payments_by_invoice` — it's an independent dependency of the `PSOA GL Statement (Future Payments)` print format.
- Do not touch Item History / Customer History / Supplier History / Pricing tabs.
- Python: tabs, double quotes, ruff-clean.

---

### Task 1: `get_receivables` delegates to ERPNext's Accounts Receivable report

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py` (function `get_receivables`, currently lines 270-384)
- Test: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/test_transaction_history.py`

**Interfaces:**
- Consumes: `erpnext.accounts.report.accounts_receivable.accounts_receivable.execute(filters)` → `(columns, data, message, chart, report_summary, skip_total_row)`, where each `data` row is a dict with (at least) `party`, `voucher_type` (`"Sales Invoice"`/`"Payment Entry"`/`"Journal Entry"`), `posting_date`, `invoiced`, `paid`, `credit_note`, `outstanding`, `range0`..`range5`, `customer_group`.
- Produces: same shape as today — list of dicts, sorted by `outstanding` descending.

- [ ] **Step 1: Write failing tests capturing the two bugs found in production**

Add to `test_transaction_history.py`, replacing nothing yet (these run against the *current* implementation and must fail):

```python
def test_get_receivables_nets_return_invoice_against_total(self):
    from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

    from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
        get_receivables,
    )

    si = create_sales_invoice(customer="_Test Customer", posting_date="2025-06-15", qty=1, rate=1000)

    credit_note = create_sales_invoice(
        customer="_Test Customer",
        posting_date="2025-06-16",
        qty=1,
        rate=1000,
        is_return=1,
        return_against=si.name,
        do_not_submit=True,
    )
    credit_note.items[0].qty = -1
    credit_note.set_posting_time = 1
    credit_note.submit()

    rows = get_receivables(company="_Test Company", as_of_date="2025-06-16", customer="_Test Customer")
    row = next((r for r in rows if r["customer"] == "_Test Customer"), None)
    self.assertIsNone(row)  # fully returned invoice must not appear as outstanding

def test_get_receivables_future_payment_nets_into_outstanding_when_toggled(self):
    from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_payment_entry
    from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice

    from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
        get_receivables,
    )

    si = create_sales_invoice(customer="_Test Customer", posting_date="2025-06-15", qty=1, rate=1000)

    pe = create_payment_entry(
        payment_type="Receive",
        party_type="Customer",
        party="_Test Customer",
        paid_from="Debtors - _TC",
        paid_to="_Test Cash - _TC",
        paid_amount=1000,
        save=True,
    )
    pe.posting_date = "2025-06-25"  # after as_of_date below
    pe.set_posting_time = 1
    pe.append("references", {
        "reference_doctype": "Sales Invoice",
        "reference_name": si.name,
        "allocated_amount": 1000,
    })
    pe.save()
    pe.submit()

    # Without the toggle: outstanding stays at the pre-payment amount (as-of-date consistent).
    rows = get_receivables(company="_Test Company", as_of_date="2025-06-15", customer="_Test Customer")
    row = next(r for r in rows if r["customer"] == "_Test Customer")
    self.assertEqual(row["outstanding"], si.grand_total)

    # With the toggle: the future payment nets straight into outstanding.
    rows_future = get_receivables(
        company="_Test Company", as_of_date="2025-06-15", customer="_Test Customer", show_future_payments=1
    )
    row_future = next(r for r in rows_future if r["customer"] == "_Test Customer")
    self.assertEqual(row_future["outstanding"], 0.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bench --site dev.localhost run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.test_transaction_history`
Expected: both new tests FAIL (the return invoice still shows up; outstanding without the toggle already reflects the future payment instead of staying at `si.grand_total`).

- [ ] **Step 3: Rewrite `get_receivables`**

```python
@frappe.whitelist()
def get_receivables(company, as_of_date, customer=None, show_future_payments=0):
	"""AR aging summary — one row per customer with a non-zero net balance, sourced from
	ERPNext's own Accounts Receivable report engine so totals always match the standard
	AR report and the PSOA AR Statement print format (credit notes, returns, and
	date-consistent future-payment handling included)."""
	frappe.has_permission("Sales Invoice", "read", throw=True)
	from collections import defaultdict

	from erpnext.accounts.report.accounts_receivable.accounts_receivable import execute as ar_execute

	filters = {
		"company": company,
		"report_date": as_of_date,
		"party_type": "Customer",
		"show_future_payments": cint(show_future_payments),
	}
	if customer:
		filters["party"] = [customer]

	_columns, data, *_ = ar_execute(filters)

	agg = defaultdict(lambda: {
		"customer": "", "customer_group": "",
		"total_invoiced": 0.0, "total_paid": 0.0, "outstanding": 0.0,
		"bucket_0_30": 0.0, "bucket_31_60": 0.0, "bucket_61_90": 0.0, "bucket_90_plus": 0.0,
		"last_payment": None, "unallocated_advance": 0.0, "future_payments": 0.0,
	})
	for r in data:
		a = agg[r["party"]]
		a["customer"] = r["party"]
		a["customer_group"] = r.get("customer_group") or ""
		a["total_invoiced"] = flt(a["total_invoiced"] + flt(r.get("invoiced") or 0), 2)
		a["total_paid"] = flt(a["total_paid"] + flt(r.get("paid") or 0), 2)
		a["outstanding"] = flt(a["outstanding"] + flt(r.get("outstanding") or 0), 2)
		a["bucket_0_30"] = flt(a["bucket_0_30"] + flt(r.get("range0") or 0) + flt(r.get("range1") or 0), 2)
		a["bucket_31_60"] = flt(a["bucket_31_60"] + flt(r.get("range2") or 0), 2)
		a["bucket_61_90"] = flt(a["bucket_61_90"] + flt(r.get("range3") or 0), 2)
		a["bucket_90_plus"] = flt(a["bucket_90_plus"] + flt(r.get("range4") or 0) + flt(r.get("range5") or 0), 2)
		a["future_payments"] = flt(a["future_payments"] + flt(r.get("future_amount") or 0), 2)

		if r.get("voucher_type") in ("Payment Entry", "Journal Entry"):
			posting_date = getdate(r["posting_date"])
			if not a["last_payment"] or posting_date > getdate(a["last_payment"]):
				a["last_payment"] = posting_date
			if flt(r.get("outstanding") or 0) < 0:
				a["unallocated_advance"] = flt(a["unallocated_advance"] + -flt(r["outstanding"]), 2)

	result = [a for a in agg.values() if a["outstanding"] or a["unallocated_advance"]]
	result.sort(key=lambda x: x["outstanding"], reverse=True)
	return result
```

Add `from frappe.utils import cint, flt, getdate` to the top-level imports if `cint`/`getdate` aren't already imported (check current `transaction_history.py` imports — `flt` is already imported from `frappe.utils`; `cint` and `getdate` need adding to that same import line).

- [ ] **Step 4: Run tests to verify they pass**

Run: `bench --site dev.localhost run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.test_transaction_history`
Expected: the two new tests PASS. Some pre-existing tests will now fail — that's expected, fix them in Step 5.

- [ ] **Step 5: Update pre-existing receivables tests to match ledger-correct expectations**

Re-run the full test file and fix each failing assertion to match the new (correct) numbers — do not weaken assertions, recompute the expected values by hand from the fixture data in each test (same technique used to derive 41,563 in this conversation: sum `invoiced - paid - credit_note` per voucher). Specifically re-check: `test_get_receivables_includes_advance_only_customer`, `test_get_receivables_includes_future_dated_advance` (from the earlier fix in this conversation — its assertions about `unallocated_advance`/`last_payment` should still hold since those are still derived from the same rows, just sourced differently), `test_get_receivables_invoice_and_advance_not_double_counted`, `test_get_receivables_customer_filter_scopes_advance_only_seeding`.

- [ ] **Step 6: Commit**

```bash
git add cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/test_transaction_history.py
git commit -m "fix: delegate get_receivables balance calc to ERPNext's Accounts Receivable report engine"
```

---

### Task 2: `get_receivables_detail` delegates to the same engine

**Files:**
- Modify: `transaction_history.py` (function `get_receivables_detail`, currently lines 387-429)
- Test: `test_transaction_history.py`

**Interfaces:**
- Consumes: same `ar_execute(filters)` as Task 1, filtered to `filters["party"] = [customer]`.
- Produces: same shape as today (`date`, `voucher_no`, `grand_total`, `paid`, `outstanding_amount`, `due_date`, `status`, `days_overdue`, `future_amount`).

- [ ] **Step 1: Write failing test** — a detail-row test asserting `outstanding_amount` reflects a credit note against that specific invoice (reuse the return-invoice fixture pattern from Task 1, but assert on `get_receivables_detail` row values instead of the summary).

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Rewrite `get_receivables_detail`**

```python
@frappe.whitelist()
def get_receivables_detail(customer, company, as_of_date, show_future_payments=0):
	"""Individual outstanding SI rows for accordion drill-down, sourced from the same
	Accounts Receivable engine as get_receivables (see there for why)."""
	frappe.has_permission("Sales Invoice", "read", throw=True)
	from erpnext.accounts.report.accounts_receivable.accounts_receivable import execute as ar_execute

	as_of = getdate(as_of_date)
	filters = {
		"company": company,
		"report_date": as_of,
		"party_type": "Customer",
		"party": [customer],
		"show_future_payments": cint(show_future_payments),
	}
	_columns, data, *_ = ar_execute(filters)

	rows = [r for r in data if r.get("voucher_type") == "Sales Invoice" and flt(r.get("outstanding") or 0) > 0]
	voucher_nos = [r["voucher_no"] for r in rows]
	status_map = {
		d.name: d.status
		for d in frappe.db.get_all("Sales Invoice", filters={"name": ["in", voucher_nos]}, fields=["name", "status"])
	} if voucher_nos else {}

	out = []
	for r in rows:
		due = getdate(r["due_date"]) if r.get("due_date") else getdate(r["posting_date"])
		out.append({
			"date": r["posting_date"],
			"voucher_no": r["voucher_no"],
			"grand_total": flt(r.get("invoiced") or 0, 2),
			"paid": flt((r.get("invoiced") or 0) - (r.get("outstanding") or 0), 2),
			"outstanding_amount": flt(r.get("outstanding") or 0, 2),
			"due_date": r.get("due_date"),
			"status": status_map.get(r["voucher_no"]),
			"days_overdue": max(0, (as_of - due).days),
			"future_amount": flt(r.get("future_amount") or 0, 2),
		})
	out.sort(key=lambda r: r["due_date"] or r["date"])
	return out
```

- [ ] **Step 4: Run to verify it passes; fix any pre-existing detail tests the same way as Task 1 Step 5.**

- [ ] **Step 5: Commit.**

---

### Task 3: `get_payables`/`get_payables_detail` — same delegation, plus `show_future_payments` parity

**Files:**
- Modify: `transaction_history.py` (`get_payables` lines 432-535, `get_payables_detail` lines 538-571)
- Test: `test_transaction_history.py`

**Interfaces:**
- Consumes: `erpnext.accounts.report.accounts_payable.accounts_payable.execute(filters)` with `filters["party_type"] = "Supplier"`. Same row shape as AR, mirrored (`supplier_group` instead of `customer_group`).
- Produces: `get_payables` gains a new optional `show_future_payments=0` parameter (additive — existing callers without it keep today's behavior). `get_payables_detail` gains the same. Both otherwise keep their current response shape, with `get_payables_detail` additionally returning `future_amount` per row (new field, additive, mirrors receivables).

- [ ] **Step 1: Write failing tests** — mirror both Task 1 tests (return-invoice netting, future-payment toggle netting) using `make_purchase_invoice`/`get_payment_entry` fixtures (follow the pattern already used in `test_get_payables_fully_allocated_advance_produces_no_row`, including the `set_posting_time = 1` fix documented there).

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Rewrite `get_payables`** (same structure as `get_receivables` in Task 1, `party_type="Supplier"`, `supplier_group` field, keyed by `supplier` instead of `customer`, no `future_payments` field since Payables never had that per-invoice feature before — Task 3 Step 5 below adds the JS side of this).

- [ ] **Step 4: Rewrite `get_payables_detail`** (same structure as `get_receivables_detail` in Task 2, `Purchase Invoice` status lookup, add `show_future_payments` param and `future_amount` field to each row).

- [ ] **Step 5: Run to verify green; fix pre-existing payables tests the same way as Task 1 Step 5.**

- [ ] **Step 6: Commit.**

---

### Task 4: Payables UI — "Show Future Payments" checkbox + Future Payment column

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.js`

**Interfaces:**
- Consumes: `get_payables`/`get_payables_detail` now accept `show_future_payments` (Task 3).
- Produces: no new exported interfaces — purely UI wiring, mirrors the existing Receivables checkbox/column exactly (see `ctrl-recv-show-future`, `_recv_state.show_future_payments`, and the `show_future` conditionals in `_render_receivables` around lines 1613/1691-1719 for the pattern to copy).

- [ ] **Step 1:** Add `<div class="ctrl-pay-show-future" style="min-width:160px"></div>` to the payables filter bar markup (next to `ctrl-pay-supplier`, mirroring the receivables filter bar).
- [ ] **Step 2:** Add `this.controls.pay_show_future = make(".ctrl-pay-show-future", { fieldtype: "Check", fieldname: "show_future_payments", label: __("Show Future Payments") });` next to the other payables control setup.
- [ ] **Step 3:** In the payables "Get" handler (~line 2103), read `this.controls.pay_show_future.get_value() ? 1 : 0`, pass it as `show_future_payments` in the `get_payables` call args, and store it on `this._pay_state.show_future_payments` (mirror `_load_receivables` exactly).
- [ ] **Step 4:** In `_render_payables` (~line 2122) and its detail-row expansion callback (~line 2165), mirror the receivables `show_future` column conditionals (header `th(__("Future Payment"), ...)` and cell rendering) and pass `show_future_payments` through to the `get_payables_detail` call args.
- [ ] **Step 5:** Manual verification — no JS test suite exists for this page; verify via `/browse` per the existing pattern (open Payables tab, tick the checkbox, confirm the column appears and a supplier with a future-dated allocated payment shows a non-dash value).
- [ ] **Step 6: Commit.**

```bash
git add cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.js
git commit -m "feat: add Show Future Payments toggle to Payables tab for parity with Receivables"
```

---

### Task 5: Full verification pass

- [ ] Run `bench --site dev.localhost run-tests --app cecypo_frappe_reports` — all tests green.
- [ ] Run `ruff check cecypo_frappe_reports/` and `ruff format --check` on the touched files only (the repo has pre-existing unrelated formatting debt — confirmed via `git stash` earlier in this conversation — don't fix unrelated files).
- [ ] Live-verify via `/browse` against `dev.localhost`: Commercial Customer's Receivables row now shows Total Outstanding = 41,563.00 with "Show Future Payments" ticked (matching the number confirmed against the standard Accounts Receivable report in this conversation), and the correct pre-toggle value with it unticked.
- [ ] Commit any final fixups.
