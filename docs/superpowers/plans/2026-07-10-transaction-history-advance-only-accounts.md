# Transaction History — Advance-Only Accounts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make suppliers/customers whose only activity is an unallocated advance payment (no outstanding invoice) appear in the Transaction History Payables/Receivables tabs, instead of being silently dropped.

**Architecture:** `get_receivables` and `get_payables` in `transaction_history.py` each build a per-party `agg` dict seeded only from outstanding-invoice rows, then attach unallocated-advance totals onto whatever keys already exist in `agg`. The fix seeds `agg` with a zero-valued entry for any party that has an unallocated advance but no invoice, before the final result-building loop runs — so that loop's existing attachment logic (`last_payment`, `unallocated_advance`, `future_payments`) picks these rows up automatically. No frontend changes are needed.

**Tech Stack:** Frappe Framework v15+, Python 3.10+, PyPika query builder (`frappe.qb`), Frappe's `IntegrationTestCase` test harness.

## Global Constraints

- Python: tabs for indentation, double quotes, line length 110 (ruff-enforced).
- Use `frappe.qb` (PyPika) for SQL — no raw SQL strings.
- Use `frappe.utils.flt(value, 2)` for float precision on all money fields.
- Site to run tests against: `dev.localhost` (has `cecypo_frappe_reports` and `erpnext` installed, `allow_tests: true`).
- Test company/customer/supplier fixtures: `_Test Company` (abbr `_TC`), `_Test Customer`, `_Test Supplier`, accounts `Debtors - _TC`, `Creditors - _TC`, `_Test Cash - _TC`, `_Test Bank - _TC` — all standard Frappe/ERPNext test fixtures, already used elsewhere in `erpnext.accounts.doctype.payment_entry.test_payment_entry`.

---

### Task 1: Switch test base class to `IntegrationTestCase`

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/test_transaction_history.py:1-7`

**Interfaces:**
- Consumes: `frappe.tests.IntegrationTestCase` (stdlib-compatible `unittest.TestCase` subclass; wraps each test class in a DB transaction that's rolled back in `tearDownClass`, via `addClassCleanup(_rollback_db)`).
- Produces: `TestTransactionHistoryPage(IntegrationTestCase)` — all later tasks' tests are added as methods on this class and rely on its auto-rollback so Payment Entry fixtures created in tests don't persist.

This task has no independent behavior to test (it's a base-class swap) — its correctness is verified by Task 2's tests passing without manual cleanup and by the full existing suite still passing.

- [ ] **Step 1: Change the import and base class**

Read the current top of the file first:

```python
# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import unittest


class TestTransactionHistoryPage(unittest.TestCase):
```

Replace with:

```python
# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

from frappe.tests import IntegrationTestCase


class TestTransactionHistoryPage(IntegrationTestCase):
```

- [ ] **Step 2: Run the existing suite to confirm nothing broke**

Run: `bench --site dev.localhost run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.test_transaction_history`
Expected: all existing tests still PASS (same count as before the base-class swap).

- [ ] **Step 3: Commit**

```bash
git add cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/test_transaction_history.py
git commit -m "test: switch Transaction History tests to IntegrationTestCase for DB rollback"
```

---

### Task 2: Fix `get_receivables` to surface advance-only customers

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py:336-349`
- Test: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/test_transaction_history.py` (append methods)

**Interfaces:**
- Consumes: `get_receivables(company, as_of_date, customer=None, show_future_payments=0)` (existing signature, unchanged) at `transaction_history.py:271`; `cust_doc = frappe.qb.DocType("Customer")` already defined at `transaction_history.py:279`; `agg` defaultdict already defined at `transaction_history.py:318-322` before this task's edit point.
- Produces: `get_receivables(...)` return value — list of dicts — now includes one entry per customer with an unallocated advance and zero outstanding invoices, with keys `customer`, `customer_group`, `total_invoiced=0.0`, `total_paid=0.0`, `outstanding=0.0`, `bucket_0_30..bucket_90_plus=0.0`, `last_payment`, `unallocated_advance`, `future_payments` — same shape as invoice-sourced rows (no new keys introduced).

- [ ] **Step 1: Write the failing tests**

Append to `test_transaction_history.py`:

```python
	def test_get_receivables_includes_advance_only_customer(self):
		from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_payment_entry
		from frappe.utils import nowdate

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_receivables,
		)

		create_payment_entry(
			payment_type="Receive",
			party_type="Customer",
			party="_Test Customer",
			paid_from="Debtors - _TC",
			paid_to="_Test Cash - _TC",
			paid_amount=750,
			save=True,
			submit=True,
		)

		rows = get_receivables(company="_Test Company", as_of_date=nowdate())
		row = next((r for r in rows if r["customer"] == "_Test Customer"), None)
		self.assertIsNotNone(row)
		self.assertEqual(row["outstanding"], 0.0)
		self.assertGreaterEqual(row["unallocated_advance"], 750.0)

	def test_get_receivables_excludes_future_dated_advance(self):
		from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_payment_entry
		from frappe.utils import add_days, nowdate

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_receivables,
		)

		pe = create_payment_entry(
			payment_type="Receive",
			party_type="Customer",
			party="_Test Customer",
			paid_from="Debtors - _TC",
			paid_to="_Test Cash - _TC",
			paid_amount=750,
			save=True,
		)
		pe.posting_date = add_days(nowdate(), 10)
		pe.save()
		pe.submit()

		rows = get_receivables(company="_Test Company", as_of_date=nowdate())
		row = next((r for r in rows if r["customer"] == "_Test Customer"), None)
		self.assertIsNone(row)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bench --site dev.localhost run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.test_transaction_history`
Expected: `test_get_receivables_includes_advance_only_customer` FAILS with `AssertionError: unexpectedly None` (row not found — the customer is missing from the result, confirming the bug). `test_get_receivables_excludes_future_dated_advance` should currently PASS (the customer is correctly absent, but only because the bug drops it — this test guards against a regression once the fix seeds advance-only rows without the date filter).

- [ ] **Step 3: Implement the fix**

In `transaction_history.py`, find this block (currently at lines 336-349):

```python
	# Unallocated advances per customer
	adv_q = (
		frappe.qb.from_(pe)
		.select(pe.party.as_("customer"), fn.Sum(pe.unallocated_amount).as_("unallocated_advance"))
		.where(pe.docstatus == 1)
		.where(pe.payment_type == "Receive")
		.where(pe.party_type == "Customer")
		.where(pe.company == company)
		.where(pe.unallocated_amount > 0)
		.groupby(pe.party)
	)
	if customer:
		adv_q = adv_q.where(pe.party == customer)
	unallocated = {r.customer: flt(r.unallocated_advance, 2) for r in adv_q.run(as_dict=True)}
```

Replace it with:

```python
	# Unallocated advances per customer
	adv_q = (
		frappe.qb.from_(pe)
		.left_join(cust_doc).on(pe.party == cust_doc.name)
		.select(
			pe.party.as_("customer"),
			cust_doc.customer_group,
			fn.Sum(pe.unallocated_amount).as_("unallocated_advance"),
		)
		.where(pe.docstatus == 1)
		.where(pe.payment_type == "Receive")
		.where(pe.party_type == "Customer")
		.where(pe.company == company)
		.where(pe.unallocated_amount > 0)
		.where(pe.posting_date <= as_of)
		.groupby(pe.party)
	)
	if customer:
		adv_q = adv_q.where(pe.party == customer)
	adv_rows = adv_q.run(as_dict=True)
	unallocated = {r.customer: flt(r.unallocated_advance, 2) for r in adv_rows}

	# Advance-only customers have no outstanding invoice, so the invoice loop above never
	# added them to `agg`. Seed a zero-valued entry here; the final loop below attaches
	# last_payment / unallocated_advance / future_payments to every key in `agg`, so these
	# rows get the same treatment as invoice-sourced rows for free.
	for r in adv_rows:
		if r.customer not in agg:
			a = agg[r.customer]
			a["customer"] = r.customer
			a["customer_group"] = r.customer_group or ""
```

This is a pure insertion/replacement — nothing else in `get_receivables` changes. The `future_payments` block and final `result` loop immediately below stay exactly as they are.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `bench --site dev.localhost run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.test_transaction_history`
Expected: both new tests PASS, and all pre-existing tests in the module still PASS.

- [ ] **Step 5: Commit**

```bash
git add cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/test_transaction_history.py
git commit -m "fix: surface advance-only customers in Transaction History receivables"
```

---

### Task 3: Fix `get_payables` to surface advance-only suppliers

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py:480-493`
- Test: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/test_transaction_history.py` (append methods)

**Interfaces:**
- Consumes: `get_payables(company, as_of_date, supplier=None)` (existing signature, unchanged) at `transaction_history.py:415`; `supp_doc = frappe.qb.DocType("Supplier")` already defined at `transaction_history.py:424`; `agg` defaultdict already defined at `transaction_history.py:462-466` before this task's edit point.
- Produces: `get_payables(...)` return value — list of dicts — now includes one entry per supplier with an unallocated advance and zero outstanding invoices, with keys `supplier`, `supplier_group`, `total_invoiced=0.0`, `total_paid=0.0`, `outstanding=0.0`, `bucket_0_30..bucket_90_plus=0.0`, `last_payment`, `unallocated_advance` — same shape as invoice-sourced rows.

- [ ] **Step 1: Write the failing tests**

Append to `test_transaction_history.py`:

```python
	def test_get_payables_includes_advance_only_supplier(self):
		from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_payment_entry
		from frappe.utils import nowdate

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_payables,
		)

		create_payment_entry(
			payment_type="Pay",
			party_type="Supplier",
			party="_Test Supplier",
			paid_from="_Test Bank - _TC",
			paid_to="Creditors - _TC",
			paid_amount=500,
			save=True,
			submit=True,
		)

		rows = get_payables(company="_Test Company", as_of_date=nowdate())
		row = next((r for r in rows if r["supplier"] == "_Test Supplier"), None)
		self.assertIsNotNone(row)
		self.assertEqual(row["outstanding"], 0.0)
		self.assertGreaterEqual(row["unallocated_advance"], 500.0)

	def test_get_payables_excludes_future_dated_advance(self):
		from erpnext.accounts.doctype.payment_entry.test_payment_entry import create_payment_entry
		from frappe.utils import add_days, nowdate

		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			get_payables,
		)

		pe = create_payment_entry(
			payment_type="Pay",
			party_type="Supplier",
			party="_Test Supplier",
			paid_from="_Test Bank - _TC",
			paid_to="Creditors - _TC",
			paid_amount=500,
			save=True,
		)
		pe.posting_date = add_days(nowdate(), 10)
		pe.save()
		pe.submit()

		rows = get_payables(company="_Test Company", as_of_date=nowdate())
		row = next((r for r in rows if r["supplier"] == "_Test Supplier"), None)
		self.assertIsNone(row)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bench --site dev.localhost run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.test_transaction_history`
Expected: `test_get_payables_includes_advance_only_supplier` FAILS with `AssertionError: unexpectedly None`. `test_get_payables_excludes_future_dated_advance` currently PASSES for the same reason as its receivables counterpart.

- [ ] **Step 3: Implement the fix**

In `transaction_history.py`, find this block (currently at lines 480-493):

```python
	# Unallocated advances per supplier
	adv_q = (
		frappe.qb.from_(pe)
		.select(pe.party.as_("supplier"), fn.Sum(pe.unallocated_amount).as_("unallocated_advance"))
		.where(pe.docstatus == 1)
		.where(pe.payment_type == "Pay")
		.where(pe.party_type == "Supplier")
		.where(pe.company == company)
		.where(pe.unallocated_amount > 0)
		.groupby(pe.party)
	)
	if supplier:
		adv_q = adv_q.where(pe.party == supplier)
	unallocated = {r.supplier: flt(r.unallocated_advance, 2) for r in adv_q.run(as_dict=True)}
```

Replace it with:

```python
	# Unallocated advances per supplier
	adv_q = (
		frappe.qb.from_(pe)
		.left_join(supp_doc).on(pe.party == supp_doc.name)
		.select(
			pe.party.as_("supplier"),
			supp_doc.supplier_group,
			fn.Sum(pe.unallocated_amount).as_("unallocated_advance"),
		)
		.where(pe.docstatus == 1)
		.where(pe.payment_type == "Pay")
		.where(pe.party_type == "Supplier")
		.where(pe.company == company)
		.where(pe.unallocated_amount > 0)
		.where(pe.posting_date <= as_of)
		.groupby(pe.party)
	)
	if supplier:
		adv_q = adv_q.where(pe.party == supplier)
	adv_rows = adv_q.run(as_dict=True)
	unallocated = {r.supplier: flt(r.unallocated_advance, 2) for r in adv_rows}

	# Advance-only suppliers have no outstanding invoice, so the invoice loop above never
	# added them to `agg`. Seed a zero-valued entry here; the final loop below attaches
	# last_payment / unallocated_advance to every key in `agg`, so these rows get the same
	# treatment as invoice-sourced rows for free.
	for r in adv_rows:
		if r.supplier not in agg:
			a = agg[r.supplier]
			a["supplier"] = r.supplier
			a["supplier_group"] = r.supplier_group or ""
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `bench --site dev.localhost run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.test_transaction_history`
Expected: all tests in the module PASS (6 pre-existing + 4 new = 10 total).

- [ ] **Step 5: Commit**

```bash
git add cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/test_transaction_history.py
git commit -m "fix: surface advance-only suppliers in Transaction History payables"
```

---

### Task 4: Manual UI verification

**Files:** none (verification only).

**Interfaces:**
- Consumes: the Transaction History page's Payables/Receivables tabs, and the two fixed backend methods from Tasks 2–3.
- Produces: confirmation that the fix is visible end-to-end, not just in unit tests.

- [ ] **Step 1: Build frontend assets (no JS changed, but confirm nothing is stale)**

Run: `bench build --app cecypo_frappe_reports`
Expected: build completes with no errors.

- [ ] **Step 2: Manually verify in the browser**

1. Open the Transaction History page on `dev.localhost`.
2. Go to the Payables tab. Pick `_Test Company` and today's date as "As Of Date".
3. Confirm `_Test Supplier` appears in the list with Outstanding = 0 (shown as `—` in the 0–30/etc bucket columns) and the advance-flag info icon next to its name (from the Task 3 test's leftover... note: since tests roll back via `IntegrationTestCase`, this data won't persist — create a real Payment Entry advance manually against a real supplier with no outstanding PI in the UI first, per the Payment Entry list, to verify visually).
4. Repeat for the Receivables tab with a customer that has an unallocated advance and no outstanding SI.
5. Confirm a supplier/customer with an advance posted *after* the selected As Of Date does not appear (or is unaffected) when using an earlier As Of Date — create one dated a week in the future and confirm it's excluded when As Of Date is today.

- [ ] **Step 3: Report results to the user**

No commit for this task — it's verification only. Summarize what was confirmed working (or any discrepancy found) back to the user.

## Self-Review Notes

- **Spec coverage:** All three spec items are covered — advance-only visibility (Tasks 2–3), the `posting_date <= as_of` date-boundary fix (Tasks 2–3, folded into the same edit since it's the same query block), and the `customer_group`/`supplier_group` backfill (Tasks 2–3). Manual verification steps from the spec are captured in Task 4. The spec's suggestion to consider switching to `FrappeTestCase` became Task 1 using the current (non-deprecated) `IntegrationTestCase`.
- **Placeholder scan:** no TBD/TODO; all steps show complete code and exact commands.
- **Type consistency:** `agg` keys/fields (`customer`, `customer_group`, `outstanding`, etc. / `supplier`, `supplier_group`, ...) match the pre-existing `defaultdict` factory shape exactly in both tasks; `adv_rows`/`unallocated` naming is consistent between Task 2 and Task 3's mirrored edits.
