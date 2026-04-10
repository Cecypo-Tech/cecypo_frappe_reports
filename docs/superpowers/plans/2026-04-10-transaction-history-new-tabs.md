# Transaction History — New Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Receivables, Payables, and Pricing tabs to the Transaction History page, including AR/AP aging with party action buttons (copy/link/print) and an item pricing view with inline price list editing.

**Architecture:** All backend code lives in `transaction_history.py` as new `@frappe.whitelist()` functions. All frontend code lives in `transaction_history.js` as new methods on `TransactionHistoryPage`. A shared `_calculate_aging_bucket` helper is extracted for testability. The Pricing tab reuses the existing item history data pipeline with two new columns added to `_get_sales_rows`.

**Tech Stack:** Frappe v15, frappe.qb (PyPika), Python 3.10+, jQuery, Bootstrap tabs

---

## File Map

| File | Change |
|------|--------|
| `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py` | Add 6 new whitelisted functions; extract `_calculate_aging_bucket`; extend `_get_sales_rows` |
| `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.js` | Add 3 tab panels to `_render()`; add controls; add ~15 new methods; extend `_bind_tabs()` and constructor |
| `cecypo_frappe_reports/cecypo_frappe_reports/tests/test_transaction_history.py` | New — unit tests for aging bucket logic |
| `cecypo_frappe_reports/cecypo_frappe_reports/tests/__init__.py` | New — empty |

---

### Task 1: Extract aging bucket helper and write tests

**Files:**
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/tests/__init__.py`
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/tests/test_transaction_history.py`
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py`

- [ ] **Step 1: Create tests/__init__.py**

```bash
touch cecypo_frappe_reports/cecypo_frappe_reports/tests/__init__.py
```

- [ ] **Step 2: Write failing tests**

Create `cecypo_frappe_reports/cecypo_frappe_reports/tests/test_transaction_history.py`:

```python
# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import unittest
from datetime import date


class TestCalculateAgingBucket(unittest.TestCase):
	"""Tests for _calculate_aging_bucket — no DB required."""

	def _bucket(self, due_str, as_of_str):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history import (
			_calculate_aging_bucket,
		)
		from frappe.utils import getdate

		return _calculate_aging_bucket(getdate(due_str), getdate(as_of_str))

	def test_not_yet_due_is_current(self):
		self.assertEqual(self._bucket("2026-02-15", "2026-01-31"), "bucket_0_30")

	def test_due_today_is_current(self):
		self.assertEqual(self._bucket("2026-01-31", "2026-01-31"), "bucket_0_30")

	def test_30_days_overdue_is_current(self):
		# 30 days past due → still in 0-30 bucket
		self.assertEqual(self._bucket("2026-01-01", "2026-01-31"), "bucket_0_30")

	def test_31_days_overdue(self):
		self.assertEqual(self._bucket("2025-12-31", "2026-01-31"), "bucket_31_60")

	def test_60_days_overdue(self):
		self.assertEqual(self._bucket("2025-12-02", "2026-01-31"), "bucket_31_60")

	def test_61_days_overdue(self):
		self.assertEqual(self._bucket("2025-12-01", "2026-01-31"), "bucket_61_90")

	def test_90_days_overdue(self):
		self.assertEqual(self._bucket("2025-11-02", "2026-01-31"), "bucket_61_90")

	def test_91_days_overdue(self):
		self.assertEqual(self._bucket("2025-11-01", "2026-01-31"), "bucket_90_plus")

	def test_no_due_date_uses_posting_date(self):
		# When due_date is None the caller should pass posting_date instead; bucket still works
		self.assertEqual(self._bucket("2025-11-01", "2026-01-31"), "bucket_90_plus")
```

- [ ] **Step 3: Run tests — verify they fail with ImportError**

```bash
cd /home/frappeuser/bench16
bench --site site16.local run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.tests.test_transaction_history 2>&1 | tail -20
```

Expected: `ImportError: cannot import name '_calculate_aging_bucket'`

- [ ] **Step 4: Add _calculate_aging_bucket to transaction_history.py**

In `transaction_history.py`, add this function before `_get_item_details` at the bottom of the file:

```python
def _calculate_aging_bucket(due_date, as_of_date):
	"""Return the aging bucket key for an invoice due on due_date as of as_of_date."""
	days = (as_of_date - due_date).days
	if days <= 30:
		return "bucket_0_30"
	elif days <= 60:
		return "bucket_31_60"
	elif days <= 90:
		return "bucket_61_90"
	return "bucket_90_plus"
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd /home/frappeuser/bench16
bench --site site16.local run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.tests.test_transaction_history 2>&1 | tail -10
```

Expected: `OK` with 8 tests passed.

- [ ] **Step 6: Commit**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports
git add cecypo_frappe_reports/tests/ cecypo_frappe_reports/page/transaction_history/transaction_history.py
git commit -m "feat: extract _calculate_aging_bucket helper with tests"
```

---

### Task 2: Extend _get_sales_rows with customer_group and selling_price_list

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py`

- [ ] **Step 1: Replace _get_sales_rows**

Find and replace the full `_get_sales_rows` function (currently starts around line 451):

```python
def _get_sales_rows(item, company, from_date, to_date, warehouse):
	sii = frappe.qb.DocType("Sales Invoice Item")
	si = frappe.qb.DocType("Sales Invoice")
	cust = frappe.qb.DocType("Customer")

	query = (
		frappe.qb.from_(sii)
		.inner_join(si).on(sii.parent == si.name)
		.left_join(cust).on(si.customer == cust.name)
		.select(
			si.posting_date.as_("date"),
			sii.parent.as_("voucher_no"),
			si.customer,
			cust.customer_group,
			si.selling_price_list,
			sii.qty,
			sii.uom,
			sii.rate,
			si.currency,
			sii.base_rate,
			si.status,
		)
		.where(si.docstatus == 1)
		.where(sii.item_code == item)
		.where(si.company == company)
		.orderby(si.posting_date, order=frappe.qb.desc)
	)
	if from_date:
		query = query.where(si.posting_date >= from_date)
	if to_date:
		query = query.where(si.posting_date <= to_date)
	if warehouse:
		query = query.where(sii.warehouse == warehouse)

	rows = query.run(as_dict=True)
	for r in rows:
		r["qty"] = flt(r["qty"], 2)
		r["rate"] = flt(r["rate"], 2)
		r["base_rate"] = flt(r["base_rate"], 2)
	return rows
```

- [ ] **Step 2: Restart bench and verify Item History still works in browser**

```bash
cd /home/frappeuser/bench16 && bench restart
```

Open `/app/transaction-history`, run Item History for any item, check that Sales rows render without errors.

- [ ] **Step 3: Commit**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports
git add cecypo_frappe_reports/page/transaction_history/transaction_history.py
git commit -m "feat: add customer_group and selling_price_list to sales rows"
```

---

### Task 3: Add Receivables and Payables backend APIs

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py`

- [ ] **Step 1: Add the four new whitelisted functions**

Add the following after the existing `get_supplier_item_transactions` function (before the `# ── Private helpers` comment):

```python
@frappe.whitelist()
def get_receivables(company, as_of_date, customer=None):
	"""AR aging summary — one row per customer with outstanding_amount > 0."""
	from collections import defaultdict
	from frappe.utils import getdate

	as_of = getdate(as_of_date)
	si = frappe.qb.DocType("Sales Invoice")
	cust_doc = frappe.qb.DocType("Customer")

	query = (
		frappe.qb.from_(si)
		.left_join(cust_doc).on(si.customer == cust_doc.name)
		.select(
			si.customer,
			cust_doc.customer_group,
			si.name,
			si.grand_total,
			si.outstanding_amount,
			si.due_date,
			si.posting_date,
		)
		.where(si.docstatus == 1)
		.where(si.outstanding_amount > 0)
		.where(si.company == company)
	)
	if customer:
		query = query.where(si.customer == customer)
	rows = query.run(as_dict=True)

	# Last payment date per customer
	pe = frappe.qb.DocType("Payment Entry")
	pay_q = (
		frappe.qb.from_(pe)
		.select(pe.party.as_("customer"), fn.Max(pe.posting_date).as_("last_payment"))
		.where(pe.docstatus == 1)
		.where(pe.payment_type == "Receive")
		.where(pe.party_type == "Customer")
		.where(pe.company == company)
		.groupby(pe.party)
	)
	if customer:
		pay_q = pay_q.where(pe.party == customer)
	last_payments = {r.customer: r.last_payment for r in pay_q.run(as_dict=True)}

	agg = defaultdict(lambda: {
		"customer": "", "customer_group": "",
		"total_invoiced": 0.0, "total_paid": 0.0, "outstanding": 0.0,
		"bucket_0_30": 0.0, "bucket_31_60": 0.0, "bucket_61_90": 0.0, "bucket_90_plus": 0.0,
	})
	for r in rows:
		a = agg[r.customer]
		a["customer"] = r.customer
		a["customer_group"] = r.customer_group or ""
		gt = flt(r.grand_total, 2)
		oa = flt(r.outstanding_amount, 2)
		a["total_invoiced"] = flt(a["total_invoiced"] + gt, 2)
		a["total_paid"] = flt(a["total_paid"] + (gt - oa), 2)
		a["outstanding"] = flt(a["outstanding"] + oa, 2)
		due = getdate(r.due_date) if r.due_date else getdate(r.posting_date)
		bucket = _calculate_aging_bucket(due, as_of)
		a[bucket] = flt(a[bucket] + oa, 2)

	result = []
	for cust_name, data in agg.items():
		data["last_payment"] = last_payments.get(cust_name)
		result.append(data)
	result.sort(key=lambda x: x["outstanding"], reverse=True)
	return result


@frappe.whitelist()
def get_receivables_detail(customer, company, as_of_date):
	"""Individual outstanding SI rows for accordion drill-down."""
	from frappe.utils import getdate

	as_of = getdate(as_of_date)
	si = frappe.qb.DocType("Sales Invoice")
	rows = (
		frappe.qb.from_(si)
		.select(
			si.posting_date.as_("date"),
			si.name.as_("voucher_no"),
			si.grand_total,
			(si.grand_total - si.outstanding_amount).as_("paid"),
			si.outstanding_amount,
			si.due_date,
			si.status,
		)
		.where(si.docstatus == 1)
		.where(si.outstanding_amount > 0)
		.where(si.customer == customer)
		.where(si.company == company)
		.orderby(si.due_date)
		.run(as_dict=True)
	)
	for r in rows:
		due = getdate(r.due_date) if r.due_date else getdate(r.date)
		r["days_overdue"] = max(0, (as_of - due).days)
		r["grand_total"] = flt(r["grand_total"], 2)
		r["paid"] = flt(r["paid"], 2)
		r["outstanding_amount"] = flt(r["outstanding_amount"], 2)
	return rows


@frappe.whitelist()
def get_payables(company, as_of_date, supplier=None):
	"""AP aging summary — one row per supplier with outstanding_amount > 0."""
	from collections import defaultdict
	from frappe.utils import getdate

	as_of = getdate(as_of_date)
	pi = frappe.qb.DocType("Purchase Invoice")
	supp_doc = frappe.qb.DocType("Supplier")

	query = (
		frappe.qb.from_(pi)
		.left_join(supp_doc).on(pi.supplier == supp_doc.name)
		.select(
			pi.supplier,
			supp_doc.supplier_group,
			pi.name,
			pi.grand_total,
			pi.outstanding_amount,
			pi.due_date,
			pi.posting_date,
		)
		.where(pi.docstatus == 1)
		.where(pi.outstanding_amount > 0)
		.where(pi.company == company)
	)
	if supplier:
		query = query.where(pi.supplier == supplier)
	rows = query.run(as_dict=True)

	pe = frappe.qb.DocType("Payment Entry")
	pay_q = (
		frappe.qb.from_(pe)
		.select(pe.party.as_("supplier"), fn.Max(pe.posting_date).as_("last_payment"))
		.where(pe.docstatus == 1)
		.where(pe.payment_type == "Pay")
		.where(pe.party_type == "Supplier")
		.where(pe.company == company)
		.groupby(pe.party)
	)
	if supplier:
		pay_q = pay_q.where(pe.party == supplier)
	last_payments = {r.supplier: r.last_payment for r in pay_q.run(as_dict=True)}

	agg = defaultdict(lambda: {
		"supplier": "", "supplier_group": "",
		"total_invoiced": 0.0, "total_paid": 0.0, "outstanding": 0.0,
		"bucket_0_30": 0.0, "bucket_31_60": 0.0, "bucket_61_90": 0.0, "bucket_90_plus": 0.0,
	})
	for r in rows:
		a = agg[r.supplier]
		a["supplier"] = r.supplier
		a["supplier_group"] = r.supplier_group or ""
		gt = flt(r.grand_total, 2)
		oa = flt(r.outstanding_amount, 2)
		a["total_invoiced"] = flt(a["total_invoiced"] + gt, 2)
		a["total_paid"] = flt(a["total_paid"] + (gt - oa), 2)
		a["outstanding"] = flt(a["outstanding"] + oa, 2)
		due = getdate(r.due_date) if r.due_date else getdate(r.posting_date)
		bucket = _calculate_aging_bucket(due, as_of)
		a[bucket] = flt(a[bucket] + oa, 2)

	result = []
	for supp_name, data in agg.items():
		data["last_payment"] = last_payments.get(supp_name)
		result.append(data)
	result.sort(key=lambda x: x["outstanding"], reverse=True)
	return result


@frappe.whitelist()
def get_payables_detail(supplier, company, as_of_date):
	"""Individual outstanding PI rows for accordion drill-down."""
	from frappe.utils import getdate

	as_of = getdate(as_of_date)
	pi = frappe.qb.DocType("Purchase Invoice")
	rows = (
		frappe.qb.from_(pi)
		.select(
			pi.posting_date.as_("date"),
			pi.name.as_("voucher_no"),
			pi.grand_total,
			(pi.grand_total - pi.outstanding_amount).as_("paid"),
			pi.outstanding_amount,
			pi.due_date,
			pi.status,
		)
		.where(pi.docstatus == 1)
		.where(pi.outstanding_amount > 0)
		.where(pi.supplier == supplier)
		.where(pi.company == company)
		.orderby(pi.due_date)
		.run(as_dict=True)
	)
	for r in rows:
		due = getdate(r.due_date) if r.due_date else getdate(r.date)
		r["days_overdue"] = max(0, (as_of - due).days)
		r["grand_total"] = flt(r["grand_total"], 2)
		r["paid"] = flt(r["paid"], 2)
		r["outstanding_amount"] = flt(r["outstanding_amount"], 2)
	return rows
```

- [ ] **Step 2: Verify syntax**

```bash
cd /home/frappeuser/bench16
python3 -c "import ast; ast.parse(open('apps/cecypo_frappe_reports/cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports
git add cecypo_frappe_reports/page/transaction_history/transaction_history.py
git commit -m "feat: add get_receivables, get_receivables_detail, get_payables, get_payables_detail APIs"
```

---

### Task 4: Add Pricing backend APIs

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py`

- [ ] **Step 1: Add get_item_prices and update_item_price after get_payables_detail**

```python
@frappe.whitelist()
def get_item_prices(item_code):
	"""Returns all Item Price records (selling + buying) for an item."""
	ip = frappe.qb.DocType("Item Price")
	rows = (
		frappe.qb.from_(ip)
		.select(
			ip.name,
			ip.price_list,
			ip.selling,
			ip.buying,
			ip.price_list_rate,
			ip.currency,
			ip.valid_from,
			ip.valid_upto,
		)
		.where(ip.item_code == item_code)
		.where((ip.selling == 1) | (ip.buying == 1))
		.orderby(ip.selling, order=frappe.qb.desc)
		.orderby(ip.price_list)
		.run(as_dict=True)
	)
	for r in rows:
		r["price_list_rate"] = flt(r["price_list_rate"], 2)
		r["type"] = "Selling" if r.get("selling") else "Buying"
	return rows


@frappe.whitelist()
def update_item_price(item_code, price_list, rate):
	"""Upsert an Item Price record. Requires Item Price write permission."""
	frappe.has_permission("Item Price", "write", throw=True)

	existing = frappe.db.get_value(
		"Item Price",
		{"item_code": item_code, "price_list": price_list},
		"name",
	)
	if existing:
		doc = frappe.get_doc("Item Price", existing)
		doc.price_list_rate = flt(rate, 2)
		doc.save()
	else:
		pl = frappe.db.get_value("Price List", price_list, ["selling", "buying"], as_dict=True) or {}
		doc = frappe.get_doc({
			"doctype": "Item Price",
			"item_code": item_code,
			"price_list": price_list,
			"price_list_rate": flt(rate, 2),
			"selling": pl.get("selling", 0),
			"buying": pl.get("buying", 0),
		})
		doc.insert()

	frappe.db.commit()
	return {"name": doc.name, "price_list_rate": doc.price_list_rate}
```

- [ ] **Step 2: Verify syntax**

```bash
cd /home/frappeuser/bench16
python3 -c "import ast; ast.parse(open('apps/cecypo_frappe_reports/cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Restart bench**

```bash
cd /home/frappeuser/bench16 && bench restart
```

- [ ] **Step 4: Commit**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports
git add cecypo_frappe_reports/page/transaction_history/transaction_history.py
git commit -m "feat: add get_item_prices and update_item_price APIs"
```

---

### Task 5: Frontend — add three new tab panels to _render() and controls

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.js`

- [ ] **Step 1: Add Receivables, Payables, Pricing nav items to _render()**

In `_render()`, find the closing `</ul>` of the nav tabs (after the `Supplier History` nav item) and add three more items:

```javascript
					<li class="nav-item">
						<a class="nav-link" href="#" data-tab="receivables">${__("Receivables")}</a>
					</li>
					<li class="nav-item">
						<a class="nav-link" href="#" data-tab="payables">${__("Payables")}</a>
					</li>
					<li class="nav-item">
						<a class="nav-link" href="#" data-tab="pricing">${__("Pricing")}</a>
					</li>
```

- [ ] **Step 2: Add the three panel divs to _render()**

Before the closing `</div>` of the `.transaction-history` wrapper (after the existing supplier panel), add:

```javascript
				<div class="th-panel hidden" data-panel="receivables">
					<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px">
						<div class="ctrl-recv-company" style="min-width:180px"></div>
						<div class="ctrl-recv-as-of" style="min-width:140px"></div>
						<div class="ctrl-recv-customer" style="min-width:220px"></div>
						<button class="btn btn-primary btn-sm btn-get-receivables">${__("Get")}</button>
					</div>
					<div class="th-content receivables-content"></div>
				</div>

				<div class="th-panel hidden" data-panel="payables">
					<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px">
						<div class="ctrl-pay-company" style="min-width:180px"></div>
						<div class="ctrl-pay-as-of" style="min-width:140px"></div>
						<div class="ctrl-pay-supplier" style="min-width:220px"></div>
						<button class="btn btn-primary btn-sm btn-get-payables">${__("Get")}</button>
					</div>
					<div class="th-content payables-content"></div>
				</div>

				<div class="th-panel hidden" data-panel="pricing">
					<div class="pricing-filter-bar" style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:12px">
						<div class="ctrl-pricing-company" style="min-width:180px"></div>
						<div class="ctrl-pricing-from" style="min-width:120px"></div>
						<div class="ctrl-pricing-to" style="min-width:120px"></div>
						<div class="ctrl-pricing-price-list" style="min-width:160px"></div>
					</div>
					<div class="pricing-body" style="display:flex;gap:0;align-items:flex-start">
						<div class="pricing-panel-sidebar" style="width:224px;min-width:224px;border:1px solid var(--border-color);border-radius:6px;padding:10px;margin-right:14px;flex-shrink:0">
							<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
								<span class="pricing-panel-label" style="font-weight:600;font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em">${__("Items")}</span>
								<button class="btn btn-xs btn-default btn-toggle-pricing-panel" title="${__("Toggle panel")}" style="padding:1px 6px">☰</button>
							</div>
							<div class="pricing-panel-body">
								<div class="ctrl-pricing-group" style="margin-bottom:6px"></div>
								<div class="ctrl-pricing-add" style="margin-bottom:8px"></div>
								<div class="pricing-checklist" style="max-height:45vh;overflow-y:auto;margin-bottom:8px;border-top:1px solid var(--border-color);padding-top:6px"></div>
								<div style="display:flex;gap:4px">
									<button class="btn btn-primary btn-sm btn-run-pricing" style="flex:1" disabled>${__("Run (0)")}</button>
									<button class="btn btn-default btn-sm btn-clear-pricing" title="${__("Clear all")}" style="padding:4px 8px">✕</button>
								</div>
							</div>
						</div>
						<div class="pricing-results" style="flex:1;min-width:0">
							<div class="pricing-tabs-strip"></div>
							<div class="th-content pricing-content"></div>
						</div>
					</div>
				</div>
```

- [ ] **Step 3: Add controls setup in _setup_controls()**

At the end of `_setup_controls()`, add:

```javascript
		// Receivables tab
		const today = frappe.datetime.get_today();
		this.controls.recv_company = make(".ctrl-recv-company", {
			fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company"), reqd: 1,
		});
		this.controls.recv_as_of = make(".ctrl-recv-as-of", {
			fieldtype: "Date", fieldname: "as_of_date", label: __("As Of Date"),
		});
		this.controls.recv_customer = make(".ctrl-recv-customer", {
			fieldtype: "Link", options: "Customer", fieldname: "customer", label: __("Customer"),
		});
		if (default_company) this.controls.recv_company.set_value(default_company);
		this.controls.recv_as_of.set_value(today);

		// Payables tab
		this.controls.pay_company = make(".ctrl-pay-company", {
			fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company"), reqd: 1,
		});
		this.controls.pay_as_of = make(".ctrl-pay-as-of", {
			fieldtype: "Date", fieldname: "as_of_date", label: __("As Of Date"),
		});
		this.controls.pay_supplier = make(".ctrl-pay-supplier", {
			fieldtype: "Link", options: "Supplier", fieldname: "supplier", label: __("Supplier"),
		});
		if (default_company) this.controls.pay_company.set_value(default_company);
		this.controls.pay_as_of.set_value(today);

		// Pricing tab
		this.controls.pricing_company = make(".ctrl-pricing-company", {
			fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company"), reqd: 1,
		});
		this.controls.pricing_from = make(".ctrl-pricing-from", {
			fieldtype: "Date", fieldname: "from_date", label: __("From Date"),
		});
		this.controls.pricing_to = make(".ctrl-pricing-to", {
			fieldtype: "Date", fieldname: "to_date", label: __("To Date"),
		});
		this.controls.pricing_price_list = make(".ctrl-pricing-price-list", {
			fieldtype: "Link", options: "Price List", fieldname: "price_list", label: __("Price List"),
		});
		this.controls.pricing_group = make(".ctrl-pricing-group", {
			fieldtype: "Link", options: "Item Group", fieldname: "item_group", label: __("Item Group"),
		});
		this.controls.pricing_add = make(".ctrl-pricing-add", {
			fieldtype: "Link", options: "Item", fieldname: "item_add", label: __("Add Item"),
		});
		this.controls.pricing_add.get_query = () => {
			const group = this.controls.pricing_group ? this.controls.pricing_group.get_value() : null;
			return {
				query: "cecypo_frappe_reports.cecypo_frappe_reports.api.item_query",
				filters: group ? { item_group: group } : {},
			};
		};
		if (default_company) this.controls.pricing_company.set_value(default_company);
```

- [ ] **Step 4: Add _pricing_panel state to constructor**

In the constructor, add after `this._item_panel = { ... }`:

```javascript
		this._pricing_panel = {
			items: [],
			active_tab: null,
		};
```

And call `this._render_pricing_checklist()` after `this._render_item_checklist()`.

- [ ] **Step 5: Build and verify tabs appear**

```bash
cd /home/frappeuser/bench16 && bench build --app cecypo_frappe_reports 2>&1 | tail -5
```

Open `/app/transaction-history` — three new tabs (Receivables, Payables, Pricing) should be visible and clickable.

- [ ] **Step 6: Commit**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports
git add cecypo_frappe_reports/page/transaction_history/transaction_history.js
git commit -m "feat: add Receivables, Payables, Pricing tab shells with filter controls"
```

---

### Task 6: Frontend — Pricing checklist (mirrors Item History checklist)

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.js`

- [ ] **Step 1: Add _render_pricing_checklist method**

Add after `_add_item_to_panel()`:

```javascript
	_render_pricing_checklist() {
		const m = this.page.main;
		const $list = $(m).find(".pricing-checklist");
		const items = this._pricing_panel.items;

		if (!items.length) {
			$list.html(`<span class="text-muted" style="font-size:12px">${__("No items added yet")}</span>`);
		} else {
			$list.html(items.map((item, i) => `
				<div class="pricing-check-row" style="display:flex;align-items:center;padding:3px 0;border-bottom:1px solid var(--border-color)">
					<label style="display:flex;align-items:center;gap:5px;cursor:pointer;font-size:12px;flex:1;min-width:0;overflow:hidden">
						<input type="checkbox" class="pricing-checkbox" data-idx="${i}" ${item.checked ? "checked" : ""} style="flex-shrink:0">
						<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${item.item_name || item.item_code}">${item.item_name || item.item_code}</span>
					</label>
					<button class="btn-remove-pricing-item" data-idx="${i}"
						style="border:none;background:none;cursor:pointer;color:var(--text-muted);padding:0 4px;font-size:14px;line-height:1;flex-shrink:0">×</button>
				</div>
			`).join(""));
		}

		const checked = items.filter(it => it.checked).length;
		$(m).find(".btn-run-pricing").text(__("Run ({0})", [checked])).prop("disabled", checked === 0);
	}

	_add_item_to_pricing_panel(item_code, item_name) {
		if (this._pricing_panel.items.find(it => it.item_code === item_code)) return;
		this._pricing_panel.items.push({ item_code, item_name: item_name || item_code, checked: true });
		this._render_pricing_checklist();
	}
```

- [ ] **Step 2: Add pricing panel event bindings in _bind_tabs()**

Add inside `_bind_tabs()` after the existing item checklist bindings:

```javascript
		// Pricing panel toggle
		$(m).on("click", ".btn-toggle-pricing-panel", () => {
			const $sidebar = $(m).find(".pricing-panel-sidebar");
			const collapsed = $sidebar.hasClass("pricing-panel-collapsed");
			if (collapsed) {
				$sidebar.removeClass("pricing-panel-collapsed").css({ width: "224px", "min-width": "224px", padding: "10px", overflow: "" });
				$sidebar.find(".pricing-panel-body").show();
				$sidebar.find(".pricing-panel-label").show();
			} else {
				$sidebar.addClass("pricing-panel-collapsed").css({ width: "36px", "min-width": "36px", padding: "4px 2px", overflow: "hidden" });
				$sidebar.find(".pricing-panel-body").hide();
				$sidebar.find(".pricing-panel-label").hide();
			}
		});

		// Pricing checklist — checkbox toggle
		$(m).on("change", ".pricing-checkbox", (e) => {
			const idx = parseInt($(e.currentTarget).data("idx"), 10);
			this._pricing_panel.items[idx].checked = e.currentTarget.checked;
			const checked = this._pricing_panel.items.filter(it => it.checked).length;
			$(m).find(".btn-run-pricing").text(__("Run ({0})", [checked])).prop("disabled", checked === 0);
		});

		// Pricing checklist — remove item
		$(m).on("click", ".btn-remove-pricing-item", (e) => {
			e.stopPropagation();
			const idx = parseInt($(e.currentTarget).data("idx"), 10);
			if (idx < 0 || idx >= this._pricing_panel.items.length) return;
			this._pricing_panel.items.splice(idx, 1);
			this._render_pricing_checklist();
		});

		// Pricing checklist — clear all
		$(m).on("click", ".btn-clear-pricing", () => {
			this._pricing_panel.items = [];
			this._render_pricing_checklist();
			$(m).find(".pricing-tabs-strip, .pricing-content").empty();
		});

		// Pricing group filter
		$(m).on("awesomplete-select", ".ctrl-pricing-group input", () => {
			setTimeout(() => {
				const group = this.controls.pricing_group ? this.controls.pricing_group.get_value() : null;
				if (!group) return;
				frappe.db.get_list("Item", {
					filters: { item_group: group, disabled: 0 },
					fields: ["name", "item_name"],
					limit: 500,
				}).then(items => items.forEach(it => this._add_item_to_pricing_panel(it.name, it.item_name)));
			}, 50);
		});

		// Pricing item add
		$(m).on("awesomplete-select", ".ctrl-pricing-add input", () => {
			setTimeout(() => {
				const val = this.controls.pricing_add ? this.controls.pricing_add.get_value() : null;
				if (!val) return;
				frappe.db.get_value("Item", val, "item_name").then(r => {
					this._add_item_to_pricing_panel(val, r.message ? r.message.item_name : val);
					this.controls.pricing_add.set_value("");
				});
			}, 50);
		});

		// Pricing run
		$(m).on("click", ".btn-run-pricing", () => this._run_pricing());

		// Pricing tab switching
		$(m).on("click", ".pricing-tab-link", (e) => {
			e.preventDefault();
			const item_code = $(e.currentTarget).data("item");
			$(m).find(".pricing-tab-link").removeClass("active");
			$(e.currentTarget).addClass("active");
			$(m).find(".pricing-tab-panel").addClass("hidden");
			$(m).find(`.pricing-tab-panel[data-item="${item_code}"]`).removeClass("hidden");
			this._pricing_panel.active_tab = item_code;
		});
```

- [ ] **Step 3: Build and verify pricing sidebar renders**

```bash
cd /home/frappeuser/bench16 && bench build --app cecypo_frappe_reports 2>&1 | tail -5
```

Navigate to Pricing tab — sidebar with item checklist should render and items can be added.

- [ ] **Step 4: Commit**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports
git add cecypo_frappe_reports/page/transaction_history/transaction_history.js
git commit -m "feat: add Pricing tab item checklist sidebar and bindings"
```

---

### Task 7: Frontend — Receivables load and render

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.js`

- [ ] **Step 1: Add _load_receivables and _render_outstanding_detail methods**

Add after `_load_supplier_history()`:

```javascript
	// ── Receivables ──────────────────────────────────────────────────────────

	_load_receivables() {
		const m = this.page.main;
		const company = this.controls.recv_company.get_value();
		const as_of_date = this.controls.recv_as_of.get_value();
		if (!company || !as_of_date) { frappe.msgprint(__("Company and As Of Date are required")); return; }
		const customer = this.controls.recv_customer.get_value() || null;
		const $content = $(m).find(".receivables-content");
		$content.html(`<div class="text-muted" style="padding:20px">${__("Loading...")}</div>`);
		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_receivables",
			args: { company, as_of_date, customer },
			callback: (r) => {
				if (r.message != null) this._render_receivables(r.message, company, as_of_date, customer);
			},
		});
	}

	_render_receivables(rows, company, as_of_date, customer) {
		const m = this.page.main;
		const $content = $(m).find(".receivables-content");
		const bc = this.base_currency;
		const accent = "var(--blue)";

		if (!rows.length) {
			$content.html(`<div class="text-muted" style="padding:20px">${__("No outstanding receivables found")}</div>`);
			return;
		}

		// Scoped single-customer view
		if (customer) {
			const r = rows[0];
			const oldest = r.bucket_90_plus > 0 ? "90+" : r.bucket_61_90 > 0 ? "61–90" : r.bucket_31_60 > 0 ? "31–60" : __("Current");
			$content.html(`
				<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">
					<div style="background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:12px 16px">
						<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px">${__("Total Outstanding")}</div>
						<div style="font-size:18px;font-weight:700;color:var(--red)">${format_currency(r.outstanding, bc)}</div>
					</div>
					<div style="background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:12px 16px">
						<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px">${__("Oldest Bucket")}</div>
						<div style="font-size:18px;font-weight:700">${oldest}</div>
					</div>
					<div style="background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:12px 16px">
						<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px">${__("Last Payment")}</div>
						<div style="font-size:18px;font-weight:700">${r.last_payment ? frappe.datetime.str_to_user(r.last_payment) : "—"}</div>
					</div>
				</div>
				<div style="margin-bottom:12px;display:flex;gap:8px" data-party="${customer}" data-party-type="customer" data-company="${company}" data-as-of="${as_of_date}">
					<button class="btn btn-xs btn-default btn-copy-text">📋 ${__("Copy")}</button>
					<button class="btn btn-xs btn-default btn-copy-link">🔗 ${__("Copy Link")}</button>
					<button class="btn btn-xs btn-default btn-print-stmt">🖨️ ${__("Print")}</button>
				</div>
				<div class="recv-detail-content" data-for="${customer}" style="padding:4px 0">
					<div class="text-muted" style="padding:12px">${__("Loading invoices...")}</div>
				</div>
			`);
			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_receivables_detail",
				args: { customer, company, as_of_date },
				callback: (r2) => {
					$content.find(`.recv-detail-content[data-for="${customer}"]`)
						.html(this._render_outstanding_detail(r2.message || [], true))
						.data("rows", r2.message || []);
				},
			});
			return;
		}

		// Company-wide table
		const sort_icon = (key) => this._recv_state.sort_key !== key
			? `<span style="opacity:.35;font-size:10px"> ↕</span>`
			: this._recv_state.sort_dir === "asc" ? `<span style="font-size:10px"> ↑</span>` : `<span style="font-size:10px"> ↓</span>`;
		const th = (label, key, align) => `
			<th class="recv-sort-header" data-sort-key="${key}"
				style="padding:5px 8px;text-align:${align || "left"};color:var(--text-muted);font-weight:600;border-bottom:2px solid ${accent};cursor:pointer;white-space:nowrap;user-select:none">
				${label}${sort_icon(key)}
			</th>`;

		$content.html(`
			<div style="margin-bottom:8px">
				<input type="search" class="recv-search form-control form-control-sm"
					placeholder="${__("Filter customers...")}" style="max-width:280px">
			</div>
			<div style="overflow-x:auto">
			<table style="width:100%;border-collapse:collapse;font-size:12px" class="recv-summary-table">
				<thead>
					<tr style="background:var(--subtle-fg)">
						<th style="padding:5px 8px;width:28px;border-bottom:2px solid ${accent}"></th>
						${th(__("Customer"), "customer")}
						${th(__("Group"), "customer_group")}
						${th(__("Invoiced"), "total_invoiced", "right")}
						${th(__("Paid"), "total_paid", "right")}
						${th(__("Outstanding"), "outstanding", "right")}
						${th(__("0–30"), "bucket_0_30", "right")}
						${th(__("31–60"), "bucket_31_60", "right")}
						${th(__("61–90"), "bucket_61_90", "right")}
						${th(__("90+"), "bucket_90_plus", "right")}
						${th(__("Last Payment"), "last_payment")}
						<th style="padding:5px 8px;border-bottom:2px solid ${accent}"></th>
					</tr>
				</thead>
				<tbody>
					${rows.map((r, i) => {
						const ind = r.bucket_90_plus > 0 ? "red" : r.bucket_61_90 > 0 ? "orange" : "";
						return `
						<tr class="recv-summary-row" data-party="${r.customer}" data-company="${company}" data-as-of="${as_of_date}"
							style="${i % 2 ? "background:var(--control-bg)" : ""};cursor:pointer">
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color);color:var(--text-muted)">▶</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">
								${ind ? `<span class="indicator-pill ${ind}" style="font-size:10px;margin-right:4px"> </span>` : ""}${r.customer}
							</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.customer_group || ""}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.total_invoiced, bc)}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.total_paid, bc)}</td>
							<td style="padding:4px 8px;text-align:right;font-weight:700;border-bottom:1px solid var(--border-color)">${format_currency(r.outstanding, bc)}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r.bucket_0_30 > 0 ? format_currency(r.bucket_0_30, bc) : "—"}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r.bucket_31_60 > 0 ? format_currency(r.bucket_31_60, bc) : "—"}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r.bucket_61_90 > 0 ? format_currency(r.bucket_61_90, bc) : "—"}</td>
							<td style="padding:4px 8px;text-align:right;${r.bucket_90_plus > 0 ? "color:var(--red);font-weight:700;" : ""}border-bottom:1px solid var(--border-color)">${r.bucket_90_plus > 0 ? format_currency(r.bucket_90_plus, bc) : "—"}</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.last_payment ? frappe.datetime.str_to_user(r.last_payment) : "—"}</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">
								<div style="display:flex;gap:3px" data-party="${r.customer}" data-party-type="customer" data-company="${company}" data-as-of="${as_of_date}">
									<button class="btn btn-xs btn-default btn-copy-text" title="${__("Copy text")}">📋</button>
									<button class="btn btn-xs btn-default btn-copy-link" title="${__("Copy link")}">🔗</button>
									<button class="btn btn-xs btn-default btn-print-stmt" title="${__("Print")}">🖨️</button>
								</div>
							</td>
						</tr>
						<tr class="recv-detail-row hidden" data-detail-for="${r.customer}">
							<td colspan="12" style="padding:0;border-bottom:2px solid var(--border-color)">
								<div class="recv-detail-content" data-for="${r.customer}" style="padding:8px 24px;background:var(--card-bg)">
									<span class="text-muted">${__("Loading...")}</span>
								</div>
							</td>
						</tr>`;
					}).join("")}
				</tbody>
			</table>
			</div>
		`);
	}

	_render_outstanding_detail(rows, is_customer) {
		if (!rows.length)
			return `<span class="text-muted">${__("No outstanding invoices found")}</span>`;
		const bc = this.base_currency;
		const slug = is_customer ? "sales-invoice" : "purchase-invoice";
		return `
			<div style="overflow-x:auto">
			<table style="width:100%;border-collapse:collapse;font-size:11px">
				<thead>
					<tr style="background:var(--subtle-fg)">
						<th style="padding:3px 8px;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Date")}</th>
						<th style="padding:3px 8px;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Invoice No.")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Grand Total")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Paid")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted);font-weight:700;border-bottom:1px solid var(--border-color)">${__("Outstanding")}</th>
						<th style="padding:3px 8px;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Due Date")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Days Overdue")}</th>
						<th style="padding:3px 8px;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Status")}</th>
					</tr>
				</thead>
				<tbody>
					${rows.map((r, i) => `
						<tr style="${i % 2 ? "background:var(--subtle-fg)" : ""}">
							<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)">${frappe.datetime.str_to_user(r.date)}</td>
							<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/${slug}/${r.voucher_no}">${r.voucher_no}</a></td>
							<td style="padding:3px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.grand_total, bc)}</td>
							<td style="padding:3px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.paid, bc)}</td>
							<td style="padding:3px 8px;text-align:right;font-weight:700;border-bottom:1px solid var(--border-color)">${format_currency(r.outstanding_amount, bc)}</td>
							<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)">${r.due_date ? frappe.datetime.str_to_user(r.due_date) : "—"}</td>
							<td style="padding:3px 8px;text-align:right;${r.days_overdue > 90 ? "color:var(--red);font-weight:700;" : r.days_overdue > 60 ? "color:var(--orange);" : ""}border-bottom:1px solid var(--border-color)">${r.days_overdue || 0}</td>
							<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)">${this._status_pill(r.status)}</td>
						</tr>`).join("")}
				</tbody>
			</table>
			</div>`;
	}
```

- [ ] **Step 2: Add _recv_state and _pay_state to constructor**

In the constructor, after `this._supp_state = { ... }`, add:

```javascript
		this._recv_state = { rows: [], company: null, as_of_date: null, sort_key: "outstanding", sort_dir: "desc" };
		this._pay_state = { rows: [], company: null, as_of_date: null, sort_key: "outstanding", sort_dir: "desc" };
```

- [ ] **Step 3: Add Receivables accordion and sort bindings in _bind_tabs()**

Add inside `_bind_tabs()`:

```javascript
		// Receivables load
		$(m).on("click", ".btn-get-receivables", () => this._load_receivables());

		// Receivables search
		$(m).on("input", ".recv-search", (e) => {
			const val = $(e.currentTarget).val().toLowerCase();
			$(m).find(".recv-summary-row").each(function () {
				const show = !val || $(this).text().toLowerCase().includes(val);
				$(this).toggleClass("hidden", !show);
				if (!show) $(this).next(".recv-detail-row").addClass("hidden");
			});
		});

		// Receivables accordion
		$(m).on("click", ".recv-summary-row", (e) => {
			if ($(e.target).closest("[data-party-type]").length && !$(e.target).is("tr")) return;
			const $row = $(e.currentTarget);
			const party = $row.data("party");
			const company = $row.data("company");
			const as_of_date = $row.data("as-of");
			const $detail = $row.next(".recv-detail-row");

			if (!$detail.hasClass("hidden")) {
				$detail.addClass("hidden");
				$row.find("td:first").text("▶");
				return;
			}
			$row.find("td:first").text("▼");
			$detail.removeClass("hidden");
			const $dc = $detail.find(`.recv-detail-content[data-for="${party}"]`);
			if ($dc.data("loaded")) return;

			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_receivables_detail",
				args: { customer: party, company, as_of_date },
				callback: (r) => {
					$dc.html(this._render_outstanding_detail(r.message || [], true)).data("loaded", true).data("rows", r.message || []);
				},
			});
		});

		// Receivables column sort
		$(m).on("click", ".recv-sort-header", (e) => {
			e.stopPropagation();
			const key = $(e.currentTarget).data("sort-key");
			const state = this._recv_state;
			state.sort_dir = state.sort_key === key ? (state.sort_dir === "asc" ? "desc" : "asc") : "asc";
			state.sort_key = key;
			const sorted = [...state.rows].sort((a, b) => {
				const av = a[key] ?? ""; const bv = b[key] ?? "";
				const cmp = av < bv ? -1 : av > bv ? 1 : 0;
				return state.sort_dir === "asc" ? cmp : -cmp;
			});
			this._render_receivables(sorted, state.company, state.as_of_date, null);
		});
```

- [ ] **Step 4: Store state in _load_receivables callback**

Update the callback in `_load_receivables` to also store state:

```javascript
			callback: (r) => {
				if (r.message != null) {
					this._recv_state.rows = r.message;
					this._recv_state.company = company;
					this._recv_state.as_of_date = as_of_date;
					this._render_receivables(r.message, company, as_of_date, customer);
				}
			},
```

- [ ] **Step 5: Build and test Receivables tab**

```bash
cd /home/frappeuser/bench16 && bench build --app cecypo_frappe_reports 2>&1 | tail -5
```

Hard-refresh browser. In Receivables tab: set Company + As Of Date, click Get. Should show aging table. Click a row to expand invoices.

- [ ] **Step 6: Commit**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports
git add cecypo_frappe_reports/page/transaction_history/transaction_history.js
git commit -m "feat: add Receivables tab load, render, accordion drill-down"
```

---

### Task 8: Frontend — party action buttons (copy/link/print)

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.js`

- [ ] **Step 1: Add three helper methods**

Add after `_render_outstanding_detail()`:

```javascript
	_copy_party_text(party_type, party, company, as_of_date, detail_rows) {
		const is_customer = party_type === "customer";
		const header = [
			`${is_customer ? "Customer Statement" : "Supplier Statement"}`,
			`${is_customer ? "Customer" : "Supplier"}: ${party}`,
			`Company: ${company}`,
			`As Of: ${frappe.datetime.str_to_user(as_of_date)}`,
			``,
			`Invoice No.       Date          Due Date      Outstanding   Days Overdue  Status`,
			`──────────────────────────────────────────────────────────────────────────────────`,
		];
		const body = detail_rows.map(r =>
			`${(r.voucher_no || "").padEnd(18)}${frappe.datetime.str_to_user(r.date).padEnd(14)}${(r.due_date ? frappe.datetime.str_to_user(r.due_date) : "—").padEnd(14)}${format_number(r.outstanding_amount, null, 2).padStart(14)}${String(r.days_overdue || 0).padStart(14)}  ${r.status || ""}`
		);
		const total = detail_rows.reduce((s, r) => s + (r.outstanding_amount || 0), 0);
		const footer = [``, `Total Outstanding: ${format_number(total, null, 2)}`];
		const text = [...header, ...body, ...footer].join("\n");
		navigator.clipboard.writeText(text).then(() => {
			frappe.show_alert({ message: __("Copied to clipboard"), indicator: "green" });
		}).catch(() => frappe.msgprint(__("Clipboard not available")));
	}

	_copy_party_link(tab, party_type, party) {
		const url = `${window.location.origin}/app/transaction-history?tab=${tab}&${party_type}=${encodeURIComponent(party)}`;
		navigator.clipboard.writeText(url).then(() => {
			frappe.show_alert({ message: __("Link copied"), indicator: "green" });
		}).catch(() => frappe.msgprint(__("Clipboard not available")));
	}

	_print_party_statement(party_type, party, company, as_of_date, detail_rows) {
		const is_customer = party_type === "customer";
		const title = is_customer ? "Customer Statement" : "Supplier Statement";
		const bc = this.base_currency;
		const total = detail_rows.reduce((s, r) => s + (r.outstanding_amount || 0), 0);
		const html = `<!DOCTYPE html><html><head><title>${title} — ${party}</title>
<style>
	body{font-family:Arial,sans-serif;padding:32px;font-size:13px;color:#222}
	h2{margin:0 0 4px}
	.meta{color:#666;margin-bottom:24px;font-size:12px}
	table{width:100%;border-collapse:collapse}
	th{padding:7px 8px;background:#f0f0f0;border-bottom:2px solid #333;text-align:left;white-space:nowrap}
	th.r,td.r{text-align:right}
	td{padding:5px 8px;border-bottom:1px solid #ddd}
	.total{margin-top:16px;text-align:right;font-weight:bold;font-size:14px}
	@media print{body{padding:0}}
</style></head><body>
<h2>${title}</h2>
<div class="meta">
	<strong>${is_customer ? "Customer" : "Supplier"}:</strong> ${party}<br>
	<strong>Company:</strong> ${company}<br>
	<strong>As Of:</strong> ${frappe.datetime.str_to_user(as_of_date)}
</div>
<table>
	<thead><tr>
		<th>${__("Date")}</th><th>${__("Invoice No.")}</th>
		<th class="r">${__("Grand Total")}</th><th class="r">${__("Paid")}</th>
		<th class="r">${__("Outstanding")}</th><th>${__("Due Date")}</th>
		<th class="r">${__("Days Overdue")}</th><th>${__("Status")}</th>
	</tr></thead>
	<tbody>
		${detail_rows.map(r => `<tr>
			<td>${frappe.datetime.str_to_user(r.date)}</td>
			<td>${r.voucher_no || ""}</td>
			<td class="r">${format_number(r.grand_total, null, 2)}</td>
			<td class="r">${format_number(r.paid, null, 2)}</td>
			<td class="r"><strong>${format_number(r.outstanding_amount, null, 2)}</strong></td>
			<td>${r.due_date ? frappe.datetime.str_to_user(r.due_date) : "—"}</td>
			<td class="r" style="${r.days_overdue > 90 ? "color:red;font-weight:bold" : r.days_overdue > 60 ? "color:darkorange" : ""}">${r.days_overdue || 0}</td>
			<td>${r.status || ""}</td>
		</tr>`).join("")}
	</tbody>
</table>
<div class="total">Total Outstanding: ${format_number(total, null, 2)}</div>
</body></html>`;
		const win = window.open("", "_blank");
		win.document.write(html);
		win.document.close();
		win.print();
	}
```

- [ ] **Step 2: Add action button event bindings in _bind_tabs()**

Add a shared handler that works for both receivables and payables action buttons:

```javascript
		// Party action buttons — copy text (fetches detail if not yet loaded)
		$(m).on("click", ".btn-copy-text", (e) => {
			e.stopPropagation();
			const $wrap = $(e.currentTarget).closest("[data-party-type]");
			const party = $wrap.data("party");
			const party_type = $wrap.data("party-type");
			const company = $wrap.data("company");
			const as_of_date = $wrap.data("as-of");
			const is_customer = party_type === "customer";
			const $dc = $(m).find(
				is_customer
					? `.recv-detail-content[data-for="${party}"]`
					: `.pay-detail-content[data-for="${party}"]`
			);
			const existing = $dc.data("rows");
			if (existing) {
				this._copy_party_text(party_type, party, company, as_of_date, existing);
			} else {
				const method = is_customer
					? "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_receivables_detail"
					: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_payables_detail";
				const args = is_customer
					? { customer: party, company, as_of_date }
					: { supplier: party, company, as_of_date };
				frappe.call({ method, args, callback: (r) => {
					this._copy_party_text(party_type, party, company, as_of_date, r.message || []);
				}});
			}
		});

		$(m).on("click", ".btn-copy-link", (e) => {
			e.stopPropagation();
			const $wrap = $(e.currentTarget).closest("[data-party-type]");
			const party = $wrap.data("party");
			const party_type = $wrap.data("party-type");
			const tab = party_type === "customer" ? "receivables" : "payables";
			this._copy_party_link(tab, party_type, party);
		});

		$(m).on("click", ".btn-print-stmt", (e) => {
			e.stopPropagation();
			const $wrap = $(e.currentTarget).closest("[data-party-type]");
			const party = $wrap.data("party");
			const party_type = $wrap.data("party-type");
			const company = $wrap.data("company");
			const as_of_date = $wrap.data("as-of");
			const is_customer = party_type === "customer";
			const $dc = $(m).find(
				is_customer
					? `.recv-detail-content[data-for="${party}"]`
					: `.pay-detail-content[data-for="${party}"]`
			);
			const existing = $dc.data("rows");
			if (existing) {
				this._print_party_statement(party_type, party, company, as_of_date, existing);
			} else {
				const method = is_customer
					? "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_receivables_detail"
					: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_payables_detail";
				const args = is_customer
					? { customer: party, company, as_of_date }
					: { supplier: party, company, as_of_date };
				frappe.call({ method, args, callback: (r) => {
					this._print_party_statement(party_type, party, company, as_of_date, r.message || []);
				}});
			}
		});
```

- [ ] **Step 3: Build and test all three action buttons**

```bash
cd /home/frappeuser/bench16 && bench build --app cecypo_frappe_reports 2>&1 | tail -5
```

In Receivables tab:
- Load data, click 📋 on a row → clipboard should contain formatted text
- Click 🔗 → clipboard should contain `/app/transaction-history?tab=receivables&customer=...`
- Click 🖨️ → new window opens with print dialog

- [ ] **Step 4: Commit**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports
git add cecypo_frappe_reports/page/transaction_history/transaction_history.js
git commit -m "feat: add copy text, copy link, and print statement party action buttons"
```

---

### Task 9: Frontend — Payables tab (mirror of Receivables)

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.js`

- [ ] **Step 1: Add _load_payables and _render_payables methods**

Add after `_render_outstanding_detail()`:

```javascript
	// ── Payables ─────────────────────────────────────────────────────────────

	_load_payables() {
		const m = this.page.main;
		const company = this.controls.pay_company.get_value();
		const as_of_date = this.controls.pay_as_of.get_value();
		if (!company || !as_of_date) { frappe.msgprint(__("Company and As Of Date are required")); return; }
		const supplier = this.controls.pay_supplier.get_value() || null;
		const $content = $(m).find(".payables-content");
		$content.html(`<div class="text-muted" style="padding:20px">${__("Loading...")}</div>`);
		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_payables",
			args: { company, as_of_date, supplier },
			callback: (r) => {
				if (r.message != null) {
					this._pay_state.rows = r.message;
					this._pay_state.company = company;
					this._pay_state.as_of_date = as_of_date;
					this._render_payables(r.message, company, as_of_date, supplier);
				}
			},
		});
	}

	_render_payables(rows, company, as_of_date, supplier) {
		const m = this.page.main;
		const $content = $(m).find(".payables-content");
		const bc = this.base_currency;
		const accent = "var(--green)";

		if (!rows.length) {
			$content.html(`<div class="text-muted" style="padding:20px">${__("No outstanding payables found")}</div>`);
			return;
		}

		if (supplier) {
			const r = rows[0];
			const oldest = r.bucket_90_plus > 0 ? "90+" : r.bucket_61_90 > 0 ? "61–90" : r.bucket_31_60 > 0 ? "31–60" : __("Current");
			$content.html(`
				<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">
					<div style="background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:12px 16px">
						<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px">${__("Total Outstanding")}</div>
						<div style="font-size:18px;font-weight:700;color:var(--orange)">${format_currency(r.outstanding, bc)}</div>
					</div>
					<div style="background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:12px 16px">
						<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px">${__("Oldest Bucket")}</div>
						<div style="font-size:18px;font-weight:700">${oldest}</div>
					</div>
					<div style="background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:12px 16px">
						<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px">${__("Last Payment")}</div>
						<div style="font-size:18px;font-weight:700">${r.last_payment ? frappe.datetime.str_to_user(r.last_payment) : "—"}</div>
					</div>
				</div>
				<div style="margin-bottom:12px;display:flex;gap:8px" data-party="${supplier}" data-party-type="supplier" data-company="${company}" data-as-of="${as_of_date}">
					<button class="btn btn-xs btn-default btn-copy-text">📋 ${__("Copy")}</button>
					<button class="btn btn-xs btn-default btn-copy-link">🔗 ${__("Copy Link")}</button>
					<button class="btn btn-xs btn-default btn-print-stmt">🖨️ ${__("Print")}</button>
				</div>
				<div class="pay-detail-content" data-for="${supplier}" style="padding:4px 0">
					<div class="text-muted" style="padding:12px">${__("Loading invoices...")}</div>
				</div>
			`);
			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_payables_detail",
				args: { supplier, company, as_of_date },
				callback: (r2) => {
					$content.find(`.pay-detail-content[data-for="${supplier}"]`)
						.html(this._render_outstanding_detail(r2.message || [], false))
						.data("rows", r2.message || []);
				},
			});
			return;
		}

		const sort_icon = (key) => this._pay_state.sort_key !== key
			? `<span style="opacity:.35;font-size:10px"> ↕</span>`
			: this._pay_state.sort_dir === "asc" ? `<span style="font-size:10px"> ↑</span>` : `<span style="font-size:10px"> ↓</span>`;
		const th = (label, key, align) => `
			<th class="pay-sort-header" data-sort-key="${key}"
				style="padding:5px 8px;text-align:${align || "left"};color:var(--text-muted);font-weight:600;border-bottom:2px solid ${accent};cursor:pointer;white-space:nowrap;user-select:none">
				${label}${sort_icon(key)}
			</th>`;

		$content.html(`
			<div style="margin-bottom:8px">
				<input type="search" class="pay-search form-control form-control-sm"
					placeholder="${__("Filter suppliers...")}" style="max-width:280px">
			</div>
			<div style="overflow-x:auto">
			<table style="width:100%;border-collapse:collapse;font-size:12px" class="pay-summary-table">
				<thead>
					<tr style="background:var(--subtle-fg)">
						<th style="padding:5px 8px;width:28px;border-bottom:2px solid ${accent}"></th>
						${th(__("Supplier"), "supplier")}
						${th(__("Group"), "supplier_group")}
						${th(__("Invoiced"), "total_invoiced", "right")}
						${th(__("Paid"), "total_paid", "right")}
						${th(__("Outstanding"), "outstanding", "right")}
						${th(__("0–30"), "bucket_0_30", "right")}
						${th(__("31–60"), "bucket_31_60", "right")}
						${th(__("61–90"), "bucket_61_90", "right")}
						${th(__("90+"), "bucket_90_plus", "right")}
						${th(__("Last Payment"), "last_payment")}
						<th style="padding:5px 8px;border-bottom:2px solid ${accent}"></th>
					</tr>
				</thead>
				<tbody>
					${rows.map((r, i) => {
						const ind = r.bucket_90_plus > 0 ? "red" : r.bucket_61_90 > 0 ? "orange" : "";
						return `
						<tr class="pay-summary-row" data-party="${r.supplier}" data-company="${company}" data-as-of="${as_of_date}"
							style="${i % 2 ? "background:var(--control-bg)" : ""};cursor:pointer">
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color);color:var(--text-muted)">▶</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">
								${ind ? `<span class="indicator-pill ${ind}" style="font-size:10px;margin-right:4px"> </span>` : ""}${r.supplier}
							</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.supplier_group || ""}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.total_invoiced, bc)}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.total_paid, bc)}</td>
							<td style="padding:4px 8px;text-align:right;font-weight:700;border-bottom:1px solid var(--border-color)">${format_currency(r.outstanding, bc)}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r.bucket_0_30 > 0 ? format_currency(r.bucket_0_30, bc) : "—"}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r.bucket_31_60 > 0 ? format_currency(r.bucket_31_60, bc) : "—"}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r.bucket_61_90 > 0 ? format_currency(r.bucket_61_90, bc) : "—"}</td>
							<td style="padding:4px 8px;text-align:right;${r.bucket_90_plus > 0 ? "color:var(--red);font-weight:700;" : ""}border-bottom:1px solid var(--border-color)">${r.bucket_90_plus > 0 ? format_currency(r.bucket_90_plus, bc) : "—"}</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.last_payment ? frappe.datetime.str_to_user(r.last_payment) : "—"}</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">
								<div style="display:flex;gap:3px" data-party="${r.supplier}" data-party-type="supplier" data-company="${company}" data-as-of="${as_of_date}">
									<button class="btn btn-xs btn-default btn-copy-text" title="${__("Copy text")}">📋</button>
									<button class="btn btn-xs btn-default btn-copy-link" title="${__("Copy link")}">🔗</button>
									<button class="btn btn-xs btn-default btn-print-stmt" title="${__("Print")}">🖨️</button>
								</div>
							</td>
						</tr>
						<tr class="pay-detail-row hidden" data-detail-for="${r.supplier}">
							<td colspan="12" style="padding:0;border-bottom:2px solid var(--border-color)">
								<div class="pay-detail-content" data-for="${r.supplier}" style="padding:8px 24px;background:var(--card-bg)">
									<span class="text-muted">${__("Loading...")}</span>
								</div>
							</td>
						</tr>`;
					}).join("")}
				</tbody>
			</table>
			</div>
		`);
	}
```

- [ ] **Step 2: Add Payables event bindings in _bind_tabs()**

```javascript
		$(m).on("click", ".btn-get-payables", () => this._load_payables());

		$(m).on("input", ".pay-search", (e) => {
			const val = $(e.currentTarget).val().toLowerCase();
			$(m).find(".pay-summary-row").each(function () {
				const show = !val || $(this).text().toLowerCase().includes(val);
				$(this).toggleClass("hidden", !show);
				if (!show) $(this).next(".pay-detail-row").addClass("hidden");
			});
		});

		$(m).on("click", ".pay-summary-row", (e) => {
			if ($(e.target).closest("[data-party-type]").length && !$(e.target).is("tr")) return;
			const $row = $(e.currentTarget);
			const party = $row.data("party");
			const company = $row.data("company");
			const as_of_date = $row.data("as-of");
			const $detail = $row.next(".pay-detail-row");

			if (!$detail.hasClass("hidden")) {
				$detail.addClass("hidden");
				$row.find("td:first").text("▶");
				return;
			}
			$row.find("td:first").text("▼");
			$detail.removeClass("hidden");
			const $dc = $detail.find(`.pay-detail-content[data-for="${party}"]`);
			if ($dc.data("loaded")) return;

			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_payables_detail",
				args: { supplier: party, company, as_of_date },
				callback: (r) => {
					$dc.html(this._render_outstanding_detail(r.message || [], false)).data("loaded", true).data("rows", r.message || []);
				},
			});
		});

		$(m).on("click", ".pay-sort-header", (e) => {
			e.stopPropagation();
			const key = $(e.currentTarget).data("sort-key");
			const state = this._pay_state;
			state.sort_dir = state.sort_key === key ? (state.sort_dir === "asc" ? "desc" : "asc") : "asc";
			state.sort_key = key;
			const sorted = [...state.rows].sort((a, b) => {
				const av = a[key] ?? ""; const bv = b[key] ?? "";
				const cmp = av < bv ? -1 : av > bv ? 1 : 0;
				return state.sort_dir === "asc" ? cmp : -cmp;
			});
			this._render_payables(sorted, state.company, state.as_of_date, null);
		});
```

- [ ] **Step 3: Build and test**

```bash
cd /home/frappeuser/bench16 && bench build --app cecypo_frappe_reports 2>&1 | tail -5
```

Test Payables tab same as Receivables — aging table, accordion, copy/link/print buttons.

- [ ] **Step 4: Commit**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports
git add cecypo_frappe_reports/page/transaction_history/transaction_history.js
git commit -m "feat: add Payables tab load, render, accordion, action buttons"
```

---

### Task 10: Frontend — Pricing tab

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.js`

- [ ] **Step 1: Add _run_pricing, _render_pricing_tabs, _fill_pricing_tab, _render_pricing_tab methods**

Add after `_render_payables()`:

```javascript
	// ── Pricing ───────────────────────────────────────────────────────────────

	_run_pricing() {
		const m = this.page.main;
		const company = this.controls.pricing_company.get_value();
		if (!company) { frappe.msgprint(__("Company is required")); return; }

		const checked = this._pricing_panel.items.filter(it => it.checked);
		if (!checked.length) return;

		const from_date = this.controls.pricing_from.get_value() || null;
		const to_date = this.controls.pricing_to.get_value() || null;
		const price_list_filter = this.controls.pricing_price_list.get_value() || null;

		this._pricing_run_gen = (this._pricing_run_gen || 0) + 1;
		const gen = this._pricing_run_gen;
		$(m).find(".btn-run-pricing").prop("disabled", true);
		let pending = checked.length;

		this._pricing_panel.active_tab = checked[0].item_code;
		this._render_pricing_tabs(checked);

		checked.forEach(item => {
			// Fire get_item_history (already returns purchases + sales with new columns) and get_item_prices in parallel
			let history_data = null;
			let price_data = null;
			let done = 0;
			const maybe_render = () => {
				if (++done < 2 || gen !== this._pricing_run_gen) return;
				this._fill_pricing_tab(item.item_code, history_data, price_data, price_list_filter);
				if (--pending === 0) {
					const cnt = this._pricing_panel.items.filter(it => it.checked).length;
					$(m).find(".btn-run-pricing").prop("disabled", cnt === 0);
				}
			};
			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_item_history",
				args: { item: item.item_code, company, from_date, to_date, warehouse: null },
				callback: (r) => { history_data = r.message; maybe_render(); },
			});
			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_item_prices",
				args: { item_code: item.item_code },
				callback: (r) => { price_data = r.message || []; maybe_render(); },
			});
		});
	}

	_render_pricing_tabs(items) {
		const m = this.page.main;
		const $strip = $(m).find(".pricing-tabs-strip");
		const $content = $(m).find(".pricing-content");

		$strip.html(`
			<div style="margin-bottom:8px">
				<ul class="nav nav-tabs" style="margin-bottom:0">
					${items.map((item, i) => `
						<li class="nav-item">
							<a class="nav-link pricing-tab-link ${i === 0 ? "active" : ""}"
								href="#" data-item="${item.item_code}"
								style="font-size:12px;padding:6px 12px">
								${item.item_code}
							</a>
						</li>
					`).join("")}
				</ul>
			</div>
		`);

		$content.html(items.map((item, i) => `
			<div class="pricing-tab-panel ${i === 0 ? "" : "hidden"}" data-item="${item.item_code}">
				<div class="text-muted" style="padding:20px">${__("Loading...")}</div>
			</div>
		`).join(""));
	}

	_fill_pricing_tab(item_code, history, prices, price_list_filter) {
		const m = this.page.main;
		const $panel = $(m).find(`.pricing-tab-panel[data-item="${item_code}"]`);
		$panel.empty();
		if (!history) { $panel.html(`<div class="text-muted" style="padding:20px">${__("Error loading data")}</div>`); return; }
		this._render_pricing_tab(history, prices || [], price_list_filter, $panel, item_code);
	}

	_render_pricing_tab({ purchases, sales }, prices, price_list_filter, $container, item_code) {
		const bc = this.base_currency;

		// ── Price List Reference panel ─────────────────────────────────────────
		const can_edit = frappe.has_perm ? frappe.has_perm("Item Price", "write") : false;
		const avg_val_rate = purchases.length
			? purchases.reduce((s, r) => s + (r.valuation_rate || 0), 0) / purchases.length
			: null;

		const price_panel_html = `
			<div style="background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:12px;margin-bottom:16px">
				<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:10px">${__("Price List Rates")}</div>
				${prices.length ? `
				<div style="overflow-x:auto">
				<table style="width:100%;border-collapse:collapse;font-size:12px">
					<thead>
						<tr style="background:var(--subtle-fg)">
							<th style="padding:4px 8px;color:var(--text-muted);border-bottom:2px solid var(--border-color)">${__("Price List")}</th>
							<th style="padding:4px 8px;color:var(--text-muted);border-bottom:2px solid var(--border-color)">${__("Type")}</th>
							<th style="padding:4px 8px;text-align:right;color:var(--text-muted);border-bottom:2px solid var(--border-color)">${__("Rate")}</th>
							<th style="padding:4px 8px;color:var(--text-muted);border-bottom:2px solid var(--border-color)">${__("Currency")}</th>
							<th style="padding:4px 8px;color:var(--text-muted);border-bottom:2px solid var(--border-color)">${__("Valid From")}</th>
							<th style="padding:4px 8px;color:var(--text-muted);border-bottom:2px solid var(--border-color)">${__("Valid Upto")}</th>
							${can_edit ? `<th style="padding:4px 8px;border-bottom:2px solid var(--border-color)"></th>` : ""}
						</tr>
					</thead>
					<tbody>
						${prices.map((p, i) => `
							<tr class="price-list-row" style="${i % 2 ? "background:var(--control-bg)" : ""}"
								data-pl="${p.price_list}" data-item="${item_code}" data-name="${p.name || ""}">
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${p.price_list}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">
									<span class="indicator-pill ${p.type === "Selling" ? "blue" : "green"}" style="font-size:10px">${__(p.type)}</span>
								</td>
								<td style="padding:4px 8px;text-align:right;font-weight:700;border-bottom:1px solid var(--border-color)">${format_number(p.price_list_rate, null, 2)}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${p.currency || ""}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${p.valid_from ? frappe.datetime.str_to_user(p.valid_from) : "—"}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${p.valid_upto ? frappe.datetime.str_to_user(p.valid_upto) : "—"}</td>
								${can_edit ? `
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">
									<button class="btn btn-xs btn-default btn-edit-price" data-pl="${p.price_list}" data-item="${item_code}"
										data-avg-val="${avg_val_rate !== null ? avg_val_rate.toFixed(2) : ""}"
										title="${__("Edit price")}">✏️</button>
								</td>` : ""}
							</tr>
							<tr class="price-edit-row hidden" data-edit-for-pl="${p.price_list}" data-edit-for-item="${item_code}">
								<td colspan="${can_edit ? 7 : 6}" style="padding:8px 12px;background:var(--card-bg);border-bottom:2px solid var(--border-color)">
									<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
										<span style="font-size:12px;color:var(--text-muted)">${__("Suggested")}:
											<strong class="price-suggested">${avg_val_rate !== null ? format_number(avg_val_rate * 1.3, null, 2) : __("N/A")}</strong>
										</span>
										${avg_val_rate !== null ? `
										<span style="font-size:12px;color:var(--text-muted)">${__("Markup %")}:
											<input type="number" class="form-control form-control-sm price-markup-input"
												value="30" style="width:70px;display:inline-block"
												data-avg-val="${avg_val_rate.toFixed(2)}">
										</span>` : ""}
										<button class="btn btn-xs btn-default btn-use-last-sold" data-item="${item_code}" data-pl="${p.price_list}"
											style="font-size:11px">${__("Use Last Sold Rate")}</button>
										<label style="font-size:12px;color:var(--text-muted)">${__("New Rate")}:
											<input type="number" class="form-control form-control-sm price-new-rate-input"
												value="${p.price_list_rate}" style="width:100px;display:inline-block">
										</label>
										<button class="btn btn-primary btn-xs btn-save-price" data-item="${item_code}" data-pl="${p.price_list}">${__("Save")}</button>
										<button class="btn btn-default btn-xs btn-cancel-price" data-pl="${p.price_list}" data-item="${item_code}">${__("Cancel")}</button>
									</div>
								</td>
							</tr>
						`).join("")}
					</tbody>
				</table>
				</div>` : `<span class="text-muted" style="font-size:12px">${__("No Item Price records found for this item")}</span>`}
			</div>`;
		$container.append(price_panel_html);

		// ── Summary strip ──────────────────────────────────────────────────────
		const filtered_sales = price_list_filter
			? sales.filter(r => r.selling_price_list === price_list_filter)
			: sales;

		const p_rates = purchases.map(r => r.valuation_rate || 0).filter(v => v > 0);
		const s_rates = filtered_sales.map(r => r.base_rate || 0).filter(v => v > 0);
		const stat = (arr) => arr.length
			? { min: Math.min(...arr), max: Math.max(...arr), avg: arr.reduce((a, b) => a + b, 0) / arr.length }
			: null;
		const ps = stat(p_rates), ss = stat(s_rates);
		const fmt = (v) => v != null ? format_number(v, null, 2) : "—";
		$container.append(`
			<div style="display:flex;flex-wrap:wrap;gap:16px;font-size:12px;margin-bottom:16px;padding:10px 12px;background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px">
				<span><span style="color:var(--text-muted)">${__("Buy Low / High / Avg")}:</span> <strong>${ps ? fmt(ps.min) : "—"} / ${ps ? fmt(ps.max) : "—"} / ${ps ? fmt(ps.avg) : "—"}</strong></span>
				<span><span style="color:var(--text-muted)">${__("Sell Low / High / Avg")}:</span> <strong>${ss ? fmt(ss.min) : "—"} / ${ss ? fmt(ss.max) : "—"} / ${ss ? fmt(ss.avg) : "—"}</strong></span>
			</div>
		`);

		// ── History tables ─────────────────────────────────────────────────────
		const $grid = $(`<div class="item-results-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:16px">`).appendTo($container);

		const buy_th = (lbl, align) => `<th style="padding:5px 8px;${align ? "text-align:right;" : ""}border-bottom:2px solid var(--green);white-space:nowrap;color:var(--text-muted);font-weight:600">${lbl}</th>`;
		const sell_th = (lbl, align) => `<th style="padding:5px 8px;${align ? "text-align:right;" : ""}border-bottom:2px solid var(--blue);white-space:nowrap;color:var(--text-muted);font-weight:600">${lbl}</th>`;

		$(`
			<div style="border:1px solid var(--border-color);border-radius:6px;overflow:hidden">
				<div style="background:var(--subtle-fg);padding:8px 12px;font-weight:600;border-bottom:2px solid var(--green);color:var(--green)">${__("Purchases")}</div>
				<div style="overflow:auto;max-height:340px">
				<table style="width:100%;border-collapse:collapse;font-size:12px">
					<thead><tr style="background:var(--subtle-fg)">
						${buy_th(__("Date"))}${buy_th(__("Voucher"))}${buy_th(__("Supplier"))}${buy_th(__("Qty"), true)}${buy_th(__("UOM"))}${buy_th(__("Rate"), true)}${buy_th(__("Val. Rate"), true)}${buy_th(__("Status"))}
					</tr></thead>
					<tbody>
						${purchases.length ? purchases.map((r, i) => `
							<tr style="${i % 2 ? "background:var(--control-bg)" : ""}">
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${frappe.datetime.str_to_user(r.date)}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/${r.doctype === "Purchase Receipt" ? "purchase-receipt" : "purchase-invoice"}/${r.voucher_no}">${r.voucher_no}</a></td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.supplier || ""}</td>
								<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.qty, null, 2)}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.uom || ""}</td>
								<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.rate, r.currency)}</td>
								<td style="padding:4px 8px;text-align:right;font-weight:600;border-bottom:1px solid var(--border-color)">${format_currency(r.valuation_rate, bc)}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${this._status_pill(r.status)}</td>
							</tr>`).join("") : `<tr><td colspan="8" style="padding:12px;text-align:center" class="text-muted">${__("No purchases found")}</td></tr>`}
					</tbody>
				</table>
				</div>
			</div>
		`).appendTo($grid);

		$(`
			<div style="border:1px solid var(--border-color);border-radius:6px;overflow:hidden">
				<div style="background:var(--subtle-fg);padding:8px 12px;font-weight:600;border-bottom:2px solid var(--blue);color:var(--blue)">${__("Sales")}${price_list_filter ? ` — ${price_list_filter}` : ""}</div>
				<div style="overflow:auto;max-height:340px">
				<table class="pricing-sales-table" style="width:100%;border-collapse:collapse;font-size:12px">
					<thead><tr style="background:var(--subtle-fg)">
						${sell_th(__("Date"))}${sell_th(__("Voucher"))}${sell_th(__("Customer"))}${sell_th(__("Group"))}${sell_th(__("Price List"))}${sell_th(__("Qty"), true)}${sell_th(__("UOM"))}${sell_th(__("Rate"), true)}${sell_th(__("Base Rate"), true)}${sell_th(__("Status"))}
					</tr></thead>
					<tbody>
						${filtered_sales.length ? filtered_sales.map((r, i) => `
							<tr style="${i % 2 ? "background:var(--control-bg)" : ""}">
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${frappe.datetime.str_to_user(r.date)}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/sales-invoice/${r.voucher_no}">${r.voucher_no}</a></td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.customer || ""}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.customer_group || ""}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.selling_price_list || ""}</td>
								<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.qty, null, 2)}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.uom || ""}</td>
								<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.rate, r.currency)}</td>
								<td style="padding:4px 8px;text-align:right;font-weight:600;border-bottom:1px solid var(--border-color)">${format_currency(r.base_rate, bc)}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${this._status_pill(r.status)}</td>
							</tr>`).join("") : `<tr><td colspan="10" style="padding:12px;text-align:center" class="text-muted">${__("No sales found")}</td></tr>`}
					</tbody>
				</table>
				</div>
			</div>
		`).appendTo($grid);
	}
```

- [ ] **Step 2: Add price edit bindings in _bind_tabs()**

```javascript
		// Pricing — edit price list rate
		$(m).on("click", ".btn-edit-price", (e) => {
			e.stopPropagation();
			const pl = $(e.currentTarget).data("pl");
			const item = $(e.currentTarget).data("item");
			$(m).find(`.price-edit-row[data-edit-for-pl="${pl}"][data-edit-for-item="${item}"]`).removeClass("hidden");
			$(e.currentTarget).closest("tr").find(".btn-edit-price").prop("disabled", true);
		});

		$(m).on("click", ".btn-cancel-price", (e) => {
			const pl = $(e.currentTarget).data("pl");
			const item = $(e.currentTarget).data("item");
			$(m).find(`.price-edit-row[data-edit-for-pl="${pl}"][data-edit-for-item="${item}"]`).addClass("hidden");
			$(m).find(`.price-list-row[data-pl="${pl}"][data-item="${item}"] .btn-edit-price`).prop("disabled", false);
		});

		$(m).on("input", ".price-markup-input", (e) => {
			const avg = parseFloat($(e.currentTarget).data("avg-val")) || 0;
			const markup = parseFloat($(e.currentTarget).val()) || 0;
			const suggested = avg * (1 + markup / 100);
			const $row = $(e.currentTarget).closest("tr");
			$row.find(".price-suggested").text(format_number(suggested, null, 2));
			$row.find(".price-new-rate-input").val(suggested.toFixed(2));
		});

		$(m).on("click", ".btn-use-last-sold", (e) => {
			const item = $(e.currentTarget).data("item");
			const pl = $(e.currentTarget).data("pl");
			// Find last sold rate for this price list from the sales table (class pricing-sales-table)
			const $panel = $(e.currentTarget).closest(".pricing-tab-panel");
			let last_rate = null;
			$panel.find(".pricing-sales-table tbody tr").each(function () {
				// col eq(4) = Price List, col eq(8) = Base Rate (newest first)
				const row_pl = $(this).find("td").eq(4).text().trim();
				if (!pl || row_pl === pl) {
					const rate_text = $(this).find("td").eq(8).text().replace(/,/g, "");
					last_rate = parseFloat(rate_text) || null;
					return false; // break — first match is newest row
				}
			});
			if (last_rate !== null) {
				$(e.currentTarget).closest("tr").find(".price-new-rate-input").val(last_rate.toFixed(2));
			} else {
				frappe.show_alert({ message: __("No sales found for this price list in the current date range"), indicator: "orange" });
			}
		});

		$(m).on("click", ".btn-save-price", (e) => {
			const item = $(e.currentTarget).data("item");
			const pl = $(e.currentTarget).data("pl");
			const $row = $(e.currentTarget).closest("tr");
			const rate = parseFloat($row.find(".price-new-rate-input").val());
			if (!rate || isNaN(rate)) { frappe.msgprint(__("Please enter a valid rate")); return; }

			$(e.currentTarget).prop("disabled", true).text(__("Saving..."));
			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.update_item_price",
				args: { item_code: item, price_list: pl, rate },
				callback: (r) => {
					if (r.message) {
						frappe.show_alert({ message: __("Price updated"), indicator: "green" });
						// Refresh the rate in the display row
						$(m).find(`.price-list-row[data-pl="${pl}"][data-item="${item}"] td:nth-child(3)`).text(format_number(r.message.price_list_rate, null, 2));
						// Hide edit row
						$(m).find(`.price-edit-row[data-edit-for-pl="${pl}"][data-edit-for-item="${item}"]`).addClass("hidden");
						$(m).find(`.price-list-row[data-pl="${pl}"][data-item="${item}"] .btn-edit-price`).prop("disabled", false);
					} else {
						$(e.currentTarget).prop("disabled", false).text(__("Save"));
					}
				},
			});
		});
```

- [ ] **Step 3: Build and test Pricing tab**

```bash
cd /home/frappeuser/bench16 && bench build --app cecypo_frappe_reports 2>&1 | tail -5
```

Add an item, click Run. Verify:
- Price List Reference panel shows Item Price records
- Summary strip shows buy/sell stats
- Purchases and Sales tables render with new columns (Customer Group, Price List)
- If user has Item Price write perm: ✏️ button appears, edit row expands, markup % recalculates suggested rate, Save updates the price

- [ ] **Step 4: Commit**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports
git add cecypo_frappe_reports/page/transaction_history/transaction_history.js
git commit -m "feat: add Pricing tab with price list reference panel and inline price editing"
```

---

### Task 11: URL param deep-linking

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.js`

- [ ] **Step 1: Add _read_url_params method**

Add after `_setup_controls()` (or anywhere before `_bind_tabs()`):

```javascript
	_read_url_params() {
		const params = new URLSearchParams(window.location.search);
		const tab = params.get("tab");
		if (!tab) return;

		const m = this.page.main;
		// Switch to the requested tab
		$(m).find(".nav-link[data-tab]").removeClass("active");
		$(m).find(`.nav-link[data-tab="${tab}"]`).addClass("active");
		$(m).find(".th-panel").addClass("hidden");
		$(m).find(`[data-panel="${tab}"]`).removeClass("hidden");

		const customer = params.get("customer");
		const supplier = params.get("supplier");

		// Small delay so controls finish rendering before setting values
		setTimeout(() => {
			if (tab === "receivables" && customer && this.controls.recv_customer) {
				this.controls.recv_customer.set_value(customer).then(() => this._load_receivables());
			} else if (tab === "payables" && supplier && this.controls.pay_supplier) {
				this.controls.pay_supplier.set_value(supplier).then(() => this._load_payables());
			} else if (tab === "customer" && customer && this.controls.customer) {
				this.controls.customer.set_value(customer).then(() => this._load_customer_history());
			} else if (tab === "supplier" && supplier && this.controls.supplier) {
				this.controls.supplier.set_value(supplier).then(() => this._load_supplier_history());
			}
		}, 200);
	}
```

- [ ] **Step 2: Call _read_url_params from constructor**

In the constructor, after `this._render_item_checklist()` and `this._render_pricing_checklist()`, add:

```javascript
		this._read_url_params();
```

- [ ] **Step 3: Build and test deep-linking**

```bash
cd /home/frappeuser/bench16 && bench build --app cecypo_frappe_reports 2>&1 | tail -5
```

Test: open `/app/transaction-history?tab=receivables` — should land on Receivables tab.
Test: open `/app/transaction-history?tab=receivables&customer=<existing customer name>` — should land on Receivables, auto-fill customer, and load.

- [ ] **Step 4: Commit**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports
git add cecypo_frappe_reports/page/transaction_history/transaction_history.js
git commit -m "feat: add URL param deep-linking for tab/customer/supplier pre-selection"
```

---

### Task 12: Final build, linting, and smoke test

**Files:** No changes — verification only

- [ ] **Step 1: Run Python linter**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports
ruff check cecypo_frappe_reports/
```

Fix any reported issues.

- [ ] **Step 2: Run tests**

```bash
cd /home/frappeuser/bench16
bench --site site16.local run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.tests.test_transaction_history 2>&1 | tail -10
```

Expected: 8 tests, all pass.

- [ ] **Step 3: Final build**

```bash
cd /home/frappeuser/bench16
bench build --app cecypo_frappe_reports 2>&1 | tail -5
bench restart
```

- [ ] **Step 4: Smoke test checklist**

In browser, hard-refresh `/app/transaction-history` and verify:

- [ ] All 6 tabs present and clickable: Item History, Customer History, Supplier History, Receivables, Payables, Pricing
- [ ] Receivables: set Company + today's date → Get → aging table renders, row expand shows invoices, 📋/🔗/🖨️ buttons work
- [ ] Payables: same flow for suppliers
- [ ] Pricing: add item → Run → Price List Reference panel, summary strip, Purchases + Sales tables (with Customer Group + Price List columns)
- [ ] Pricing: ✏️ edit price, change markup %, see suggested rate update, Save → toast confirms
- [ ] URL: `/app/transaction-history?tab=payables&supplier=<name>` → lands on Payables pre-filled
- [ ] Existing Item History, Customer History, Supplier History still work (regression check)

- [ ] **Step 5: Final commit**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports
git add -A
git commit -m "feat: complete Transaction History new tabs — Receivables, Payables, Pricing"
```
