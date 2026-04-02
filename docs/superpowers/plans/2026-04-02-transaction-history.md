# Transaction History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Item History, Customer History, and Supplier History as three Script Reports plus a unified tabbed Custom Page at `/transaction-history`.

**Architecture:** Script Reports follow the existing app pattern (execute → columns + data + report_summary). The Custom Page is a Frappe Page that renders its own HTML/controls and calls whitelisted Python API functions on demand. The two artifacts share no code — each has its own Python backend.

**Tech Stack:** Frappe v15, Python 3.10+, frappe.qb (PyPika), vanilla JS (ES6 class), Frappe UI controls

**Spec:** `docs/superpowers/specs/2026-04-02-transaction-history-design.md`

**Implementation notes:**
- Use `fn.CountDistinct(col)` (not `fn.Count(col.distinct())`) — matches existing Day Book code and is confirmed to work in this frappe version.
- The `transaction_history.js` class defines `_bind_tabs()` once at the bottom of the class (the complete version with accordion logic). There is no earlier partial definition — the constructor calls it after `_render()`.
- After editing Python files outside of `bench run-tests`, run `bench restart` so the web process picks up changes.

---

## File Map

```
cecypo_frappe_reports/cecypo_frappe_reports/report/
  item_history/
    __init__.py                  # empty
    item_history.json            # Script Report metadata
    item_history.py              # execute(), get_columns(), get_data(), get_report_summary()
    item_history.js              # filters, formatter, onload
    test_item_history.py         # structural tests

  customer_history/
    __init__.py
    customer_history.json
    customer_history.py
    customer_history.js
    test_customer_history.py

  supplier_history/
    __init__.py
    supplier_history.json
    supplier_history.py
    supplier_history.js
    test_supplier_history.py

cecypo_frappe_reports/cecypo_frappe_reports/page/
  transaction_history/
    transaction_history.json     # Page metadata (page_name: transaction-history)
    transaction_history.py       # @frappe.whitelist() API functions
    transaction_history.js       # TransactionHistoryPage class, tab UI, rendering

README.md                        # updated reports list
```

---

## Task 1: Item History Script Report

**Files:**
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/report/item_history/__init__.py`
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/report/item_history/item_history.json`
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/report/item_history/item_history.py`
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/report/item_history/item_history.js`
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/report/item_history/test_item_history.py`

All paths relative to `/home/frappeuser/bench16/apps/cecypo_frappe_reports/`.

- [ ] **Step 1.1: Create the directory and empty __init__.py**

```bash
mkdir -p /home/frappeuser/bench16/apps/cecypo_frappe_reports/cecypo_frappe_reports/cecypo_frappe_reports/report/item_history
touch /home/frappeuser/bench16/apps/cecypo_frappe_reports/cecypo_frappe_reports/cecypo_frappe_reports/report/item_history/__init__.py
```

- [ ] **Step 1.2: Write the failing structural test**

Create `cecypo_frappe_reports/cecypo_frappe_reports/report/item_history/test_item_history.py`:

```python
# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
import unittest


class TestItemHistory(unittest.TestCase):
	def test_columns_structure(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.report.item_history.item_history import (
			get_columns,
		)

		columns = get_columns()
		fieldnames = [c["fieldname"] for c in columns]
		self.assertIn("date", fieldnames)
		self.assertIn("voucher_type", fieldnames)
		self.assertIn("voucher_no", fieldnames)
		self.assertIn("party", fieldnames)
		self.assertIn("qty", fieldnames)
		self.assertIn("uom", fieldnames)
		self.assertIn("rate", fieldnames)
		self.assertIn("currency", fieldnames)
		self.assertIn("valuation_or_base_rate", fieldnames)
		self.assertEqual(len(columns), 9)

	def test_execute_returns_tuple(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.report.item_history.item_history import (
			execute,
		)

		filters = frappe._dict({"item": "__nonexistent__", "company": "_Test Company"})
		result = execute(filters)
		self.assertIsInstance(result, tuple)
		self.assertEqual(len(result), 5)
		columns, data, message, chart, summary = result
		self.assertIsInstance(columns, list)
		self.assertIsInstance(data, list)
		# No crash on nonexistent item — empty data
		self.assertEqual(len([r for r in data if not r.get("bold")]), 0)
```

- [ ] **Step 1.3: Run test to confirm it fails**

```bash
cd /home/frappeuser/bench16 && bench --site site16.local run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.report.item_history.test_item_history 2>&1 | tail -20
```

Expected: `ImportError` or `ModuleNotFoundError` — the module doesn't exist yet.

- [ ] **Step 1.4: Create the report JSON**

Create `cecypo_frappe_reports/cecypo_frappe_reports/report/item_history/item_history.json`:

```json
{
 "add_total_row": 0,
 "columns": [],
 "creation": "2026-04-02 00:00:00.000000",
 "disabled": 0,
 "docstatus": 0,
 "doctype": "Report",
 "filters": [],
 "is_standard": "Yes",
 "modified": "2026-04-02 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Cecypo Frappe Reports",
 "name": "Item History",
 "owner": "Administrator",
 "prepared_report": 0,
 "ref_doctype": "Item",
 "report_name": "Item History",
 "report_type": "Script Report",
 "roles": [
  {"role": "Stock Manager"},
  {"role": "Stock User"},
  {"role": "Purchase Manager"},
  {"role": "Purchase User"},
  {"role": "Sales Manager"},
  {"role": "Sales User"},
  {"role": "Accounts Manager"},
  {"role": "Accounts User"}
 ]
}
```

- [ ] **Step 1.5: Implement item_history.py**

Create `cecypo_frappe_reports/cecypo_frappe_reports/report/item_history/item_history.py`:

```python
# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from pypika import functions as fn


def execute(filters=None):
	if not filters:
		filters = frappe._dict({})

	if not filters.get("item"):
		return get_columns(), [], None, None, []

	columns = get_columns()
	purchases = get_purchase_rows(filters)
	sales = get_sales_rows(filters)
	data = build_data(purchases, sales)
	report_summary = get_report_summary(filters, purchases, sales)

	return columns, data, None, None, report_summary


def get_columns():
	return [
		{
			"label": _("Date"),
			"fieldname": "date",
			"fieldtype": "Date",
			"width": 100,
		},
		{
			"label": _("Voucher Type"),
			"fieldname": "voucher_type",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Voucher No"),
			"fieldname": "voucher_no",
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 160,
		},
		{
			"label": _("Party"),
			"fieldname": "party",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": _("Qty"),
			"fieldname": "qty",
			"fieldtype": "Float",
			"precision": 2,
			"width": 80,
		},
		{
			"label": _("UOM"),
			"fieldname": "uom",
			"fieldtype": "Data",
			"width": 70,
		},
		{
			"label": _("Rate"),
			"fieldname": "rate",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": _("Currency"),
			"fieldname": "currency",
			"fieldtype": "Data",
			"width": 70,
		},
		{
			"label": _("Valuation / Base Rate"),
			"fieldname": "valuation_or_base_rate",
			"fieldtype": "Float",
			"precision": 2,
			"width": 130,
		},
	]


def get_purchase_rows(filters):
	pri = frappe.qb.DocType("Purchase Receipt Item")
	pr = frappe.qb.DocType("Purchase Receipt")

	query = (
		frappe.qb.from_(pri)
		.inner_join(pr)
		.on(pri.parent == pr.name)
		.select(
			pr.posting_date.as_("date"),
			pri.parent.as_("voucher_no"),
			pr.supplier.as_("party"),
			pri.qty,
			pri.uom,
			pri.rate,
			pr.currency,
			pri.valuation_rate.as_("valuation_or_base_rate"),
		)
		.where(pr.docstatus == 1)
		.where(pri.item_code == filters.item)
		.where(pr.company == filters.company)
		.orderby(pr.posting_date, order=frappe.qb.desc)
	)

	if filters.get("from_date"):
		query = query.where(pr.posting_date >= filters.from_date)
	if filters.get("to_date"):
		query = query.where(pr.posting_date <= filters.to_date)
	if filters.get("warehouse"):
		query = query.where(pri.warehouse == filters.warehouse)

	rows = query.run(as_dict=True)
	for r in rows:
		r["voucher_type"] = "Purchase Receipt"
		r["qty"] = flt(r["qty"], 2)
		r["rate"] = flt(r["rate"], 2)
		r["valuation_or_base_rate"] = flt(r["valuation_or_base_rate"], 2)
	return rows


def get_sales_rows(filters):
	sii = frappe.qb.DocType("Sales Invoice Item")
	si = frappe.qb.DocType("Sales Invoice")

	query = (
		frappe.qb.from_(sii)
		.inner_join(si)
		.on(sii.parent == si.name)
		.select(
			si.posting_date.as_("date"),
			sii.parent.as_("voucher_no"),
			si.customer.as_("party"),
			sii.qty,
			sii.uom,
			sii.rate,
			si.currency,
			sii.base_rate.as_("valuation_or_base_rate"),
		)
		.where(si.docstatus == 1)
		.where(sii.item_code == filters.item)
		.where(si.company == filters.company)
		.orderby(si.posting_date, order=frappe.qb.desc)
	)

	if filters.get("from_date"):
		query = query.where(si.posting_date >= filters.from_date)
	if filters.get("to_date"):
		query = query.where(si.posting_date <= filters.to_date)

	rows = query.run(as_dict=True)
	for r in rows:
		r["voucher_type"] = "Sales Invoice"
		r["qty"] = flt(r["qty"], 2)
		r["rate"] = flt(r["rate"], 2)
		r["valuation_or_base_rate"] = flt(r["valuation_or_base_rate"], 2)
	return rows


def build_data(purchases, sales):
	data = []

	total_purchase_qty = flt(sum(r["qty"] for r in purchases), 2)
	data.append({
		"date": None,
		"voucher_type": None,
		"voucher_no": _("── Purchases ({0} transactions · {1} units) ──").format(
			len(purchases), total_purchase_qty
		),
		"party": None,
		"qty": None,
		"uom": None,
		"rate": None,
		"currency": None,
		"valuation_or_base_rate": None,
		"bold": 1,
		"indicator": "green",
	})
	data.extend(purchases)

	total_sales_qty = flt(sum(r["qty"] for r in sales), 2)
	data.append({
		"date": None,
		"voucher_type": None,
		"voucher_no": _("── Sales ({0} transactions · {1} units) ──").format(
			len(sales), total_sales_qty
		),
		"party": None,
		"qty": None,
		"uom": None,
		"rate": None,
		"currency": None,
		"valuation_or_base_rate": None,
		"bold": 1,
		"indicator": "blue",
	})
	data.extend(sales)

	return data


def get_report_summary(filters, purchases, sales):
	bin_data = frappe.db.get_value(
		"Bin",
		{"item_code": filters.item, "company": filters.company},
		["sum(actual_qty)", "sum(stock_value)"],
		as_dict=True,
	) or {}

	# avg valuation rate from Bin across warehouses
	bin_rows = frappe.db.get_all(
		"Bin",
		filters={"item_code": filters.item},
		fields=["actual_qty", "valuation_rate"],
	)
	total_qty = sum(flt(b.actual_qty) for b in bin_rows)
	if total_qty:
		avg_rate = sum(flt(b.actual_qty) * flt(b.valuation_rate) for b in bin_rows) / total_qty
	else:
		avg_rate = 0.0

	current_stock = flt(sum(flt(b.actual_qty) for b in bin_rows), 2)
	stock_value = flt(sum(flt(b.actual_qty) * flt(b.valuation_rate) for b in bin_rows), 2)
	total_purchased = flt(sum(r["qty"] for r in purchases), 2)
	total_sold = flt(sum(r["qty"] for r in sales), 2)

	return [
		{"value": current_stock, "label": _("Current Stock"), "datatype": "Float", "indicator": "Green" if current_stock > 0 else "Red"},
		{"value": flt(avg_rate, 2), "label": _("Avg. Stock Rate"), "datatype": "Float", "indicator": "Blue"},
		{"value": stock_value, "label": _("Stock Value"), "datatype": "Float", "indicator": "Blue"},
		{"value": total_purchased, "label": _("Total Purchased"), "datatype": "Float", "indicator": "Blue"},
		{"value": total_sold, "label": _("Total Sold"), "datatype": "Float", "indicator": "Blue"},
	]
```

- [ ] **Step 1.6: Implement item_history.js**

Create `cecypo_frappe_reports/cecypo_frappe_reports/report/item_history/item_history.js`:

```javascript
// Copyright (c) 2026, Cecypo and contributors
// For license information, please see license.txt

frappe.query_reports["Item History"] = {
	filters: [
		{
			fieldname: "item",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
			reqd: 1,
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query() {
				let company = frappe.query_report.get_filter_value("company");
				return { filters: { company } };
			},
		},
	],
	formatter(value, row, column, data, default_formatter) {
		if (
			(column.fieldtype === "Float" || column.fieldtype === "Currency") &&
			value != null
		) {
			return format_number(value, null, 2);
		}
		return default_formatter(value, row, column, data);
	},
	onload(report) {
		report.page.add_button(__("Best Fit"), () => {
			const dt = report.datatable;
			if (!dt) return;
			dt.header
				.querySelectorAll(".dt-cell .dt-cell__resize-handle")
				.forEach((h) => h.dispatchEvent(new MouseEvent("dblclick", { bubbles: true })));
		});
	},
};
```

- [ ] **Step 1.7: Run tests — expect pass**

```bash
cd /home/frappeuser/bench16 && bench --site site16.local run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.report.item_history.test_item_history 2>&1 | tail -20
```

Expected output contains: `OK` and `Ran 2 tests`.

- [ ] **Step 1.8: Migrate to register the report**

```bash
cd /home/frappeuser/bench16 && bench --site site16.local migrate 2>&1 | tail -10
```

Expected: no errors, ends with `Frappe: Migrated`.

- [ ] **Step 1.9: Commit**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports && git add cecypo_frappe_reports/cecypo_frappe_reports/report/item_history/ && git commit -m "$(cat <<'EOF'
feat: add Item History script report

Stacked purchases/sales table filtered by item + company with
valuation/base-rate column and 5-metric report summary.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Customer History Script Report

**Files:**
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/report/customer_history/` (all 5 files)

- [ ] **Step 2.1: Create directory and __init__.py**

```bash
mkdir -p /home/frappeuser/bench16/apps/cecypo_frappe_reports/cecypo_frappe_reports/cecypo_frappe_reports/report/customer_history
touch /home/frappeuser/bench16/apps/cecypo_frappe_reports/cecypo_frappe_reports/cecypo_frappe_reports/report/customer_history/__init__.py
```

- [ ] **Step 2.2: Write the failing test**

Create `cecypo_frappe_reports/cecypo_frappe_reports/report/customer_history/test_customer_history.py`:

```python
# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
import unittest


class TestCustomerHistory(unittest.TestCase):
	def test_columns_structure(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.report.customer_history.customer_history import (
			get_columns,
		)

		columns = get_columns()
		fieldnames = [c["fieldname"] for c in columns]
		self.assertIn("item_code", fieldnames)
		self.assertIn("item_name", fieldnames)
		self.assertIn("total_qty", fieldnames)
		self.assertIn("invoice_count", fieldnames)
		self.assertIn("avg_rate", fieldnames)
		self.assertIn("total_amount", fieldnames)
		self.assertIn("last_sale", fieldnames)
		self.assertEqual(len(columns), 7)

	def test_execute_returns_tuple(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.report.customer_history.customer_history import (
			execute,
		)

		filters = frappe._dict({"customer": "__nonexistent__", "company": "_Test Company"})
		result = execute(filters)
		self.assertIsInstance(result, tuple)
		self.assertEqual(len(result), 5)
		columns, data, message, chart, summary = result
		self.assertIsInstance(data, list)
		self.assertEqual(len([r for r in data if not r.get("bold")]), 0)
```

- [ ] **Step 2.3: Run test — confirm it fails**

```bash
cd /home/frappeuser/bench16 && bench --site site16.local run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.report.customer_history.test_customer_history 2>&1 | tail -10
```

Expected: `ImportError`.

- [ ] **Step 2.4: Create customer_history.json**

Create `cecypo_frappe_reports/cecypo_frappe_reports/report/customer_history/customer_history.json`:

```json
{
 "add_total_row": 0,
 "columns": [],
 "creation": "2026-04-02 00:00:00.000000",
 "disabled": 0,
 "docstatus": 0,
 "doctype": "Report",
 "filters": [],
 "is_standard": "Yes",
 "modified": "2026-04-02 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Cecypo Frappe Reports",
 "name": "Customer History",
 "owner": "Administrator",
 "prepared_report": 0,
 "ref_doctype": "Customer",
 "report_name": "Customer History",
 "report_type": "Script Report",
 "roles": [
  {"role": "Sales Manager"},
  {"role": "Sales User"},
  {"role": "Accounts Manager"},
  {"role": "Accounts User"}
 ]
}
```

- [ ] **Step 2.5: Implement customer_history.py**

Create `cecypo_frappe_reports/cecypo_frappe_reports/report/customer_history/customer_history.py`:

```python
# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from pypika import functions as fn


def execute(filters=None):
	if not filters:
		filters = frappe._dict({})

	if not filters.get("customer"):
		return get_columns(), [], None, None, []

	columns = get_columns()
	data = get_data(filters)
	report_summary = get_report_summary(data)

	return columns, data, None, None, report_summary


def get_columns():
	return [
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 130,
		},
		{
			"label": _("Item Name"),
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"label": _("Total Qty"),
			"fieldname": "total_qty",
			"fieldtype": "Float",
			"precision": 2,
			"width": 90,
		},
		{
			"label": _("Invoices"),
			"fieldname": "invoice_count",
			"fieldtype": "Int",
			"width": 70,
		},
		{
			"label": _("Avg Rate"),
			"fieldname": "avg_rate",
			"fieldtype": "Float",
			"precision": 2,
			"width": 120,
		},
		{
			"label": _("Total Amount"),
			"fieldname": "total_amount",
			"fieldtype": "Float",
			"precision": 2,
			"width": 140,
		},
		{
			"label": _("Last Sale"),
			"fieldname": "last_sale",
			"fieldtype": "Date",
			"width": 100,
		},
	]


def get_data(filters):
	sii = frappe.qb.DocType("Sales Invoice Item")
	si = frappe.qb.DocType("Sales Invoice")

	query = (
		frappe.qb.from_(sii)
		.inner_join(si)
		.on(sii.parent == si.name)
		.select(
			sii.item_code,
			sii.item_name,
			fn.Sum(sii.qty).as_("total_qty"),
			fn.CountDistinct(si.name).as_("invoice_count"),
			fn.Avg(sii.base_rate).as_("avg_rate"),
			fn.Sum(sii.base_amount).as_("total_amount"),
			fn.Max(si.posting_date).as_("last_sale"),
		)
		.where(si.docstatus == 1)
		.where(si.customer == filters.customer)
		.where(si.company == filters.company)
		.groupby(sii.item_code, sii.item_name)
		.orderby(fn.Sum(sii.base_amount), order=frappe.qb.desc)
	)

	if filters.get("from_date"):
		query = query.where(si.posting_date >= filters.from_date)
	if filters.get("to_date"):
		query = query.where(si.posting_date <= filters.to_date)

	rows = query.run(as_dict=True)
	for r in rows:
		r["total_qty"] = flt(r["total_qty"], 2)
		r["avg_rate"] = flt(r["avg_rate"], 2)
		r["total_amount"] = flt(r["total_amount"], 2)

	if rows:
		rows.append({
			"item_code": None,
			"item_name": _("Total"),
			"total_qty": flt(sum(r["total_qty"] for r in rows), 2),
			"invoice_count": sum(r["invoice_count"] for r in rows),
			"avg_rate": None,
			"total_amount": flt(sum(r["total_amount"] for r in rows), 2),
			"last_sale": None,
			"bold": 1,
		})

	return rows


def get_report_summary(data):
	rows = [r for r in data if not r.get("bold")]
	if not rows:
		return []

	return [
		{"value": len(rows), "label": _("Total Items"), "datatype": "Int", "indicator": "Blue"},
		{"value": flt(sum(r["total_qty"] for r in rows), 2), "label": _("Total Qty Sold"), "datatype": "Float", "indicator": "Blue"},
		{"value": flt(sum(r["total_amount"] for r in rows), 2), "label": _("Total Revenue"), "datatype": "Float", "indicator": "Green"},
	]
```

- [ ] **Step 2.6: Implement customer_history.js**

Create `cecypo_frappe_reports/cecypo_frappe_reports/report/customer_history/customer_history.js`:

```javascript
// Copyright (c) 2026, Cecypo and contributors
// For license information, please see license.txt

frappe.query_reports["Customer History"] = {
	filters: [
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
			reqd: 1,
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		if (
			(column.fieldtype === "Float" || column.fieldtype === "Currency") &&
			value != null
		) {
			return format_number(value, null, 2);
		}
		return default_formatter(value, row, column, data);
	},
	onload(report) {
		report.page.add_button(__("Best Fit"), () => {
			const dt = report.datatable;
			if (!dt) return;
			dt.header
				.querySelectorAll(".dt-cell .dt-cell__resize-handle")
				.forEach((h) => h.dispatchEvent(new MouseEvent("dblclick", { bubbles: true })));
		});
	},
};
```

- [ ] **Step 2.7: Run tests — expect pass**

```bash
cd /home/frappeuser/bench16 && bench --site site16.local run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.report.customer_history.test_customer_history 2>&1 | tail -10
```

Expected: `OK` and `Ran 2 tests`.

- [ ] **Step 2.8: Migrate**

```bash
cd /home/frappeuser/bench16 && bench --site site16.local migrate 2>&1 | tail -5
```

- [ ] **Step 2.9: Commit**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports && git add cecypo_frappe_reports/cecypo_frappe_reports/report/customer_history/ && git commit -m "$(cat <<'EOF'
feat: add Customer History script report

Item-wise sales summary per customer with total qty, invoice count,
avg rate, total amount, and last sale date.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Supplier History Script Report

**Files:**
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/report/supplier_history/` (all 5 files)

- [ ] **Step 3.1: Create directory and __init__.py**

```bash
mkdir -p /home/frappeuser/bench16/apps/cecypo_frappe_reports/cecypo_frappe_reports/cecypo_frappe_reports/report/supplier_history
touch /home/frappeuser/bench16/apps/cecypo_frappe_reports/cecypo_frappe_reports/cecypo_frappe_reports/report/supplier_history/__init__.py
```

- [ ] **Step 3.2: Write the failing test**

Create `cecypo_frappe_reports/cecypo_frappe_reports/report/supplier_history/test_supplier_history.py`:

```python
# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
import unittest


class TestSupplierHistory(unittest.TestCase):
	def test_columns_structure(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.report.supplier_history.supplier_history import (
			get_columns,
		)

		columns = get_columns()
		fieldnames = [c["fieldname"] for c in columns]
		self.assertIn("item_code", fieldnames)
		self.assertIn("item_name", fieldnames)
		self.assertIn("total_qty", fieldnames)
		self.assertIn("receipt_count", fieldnames)
		self.assertIn("avg_valuation_rate", fieldnames)
		self.assertIn("total_amount", fieldnames)
		self.assertIn("last_purchase", fieldnames)
		self.assertEqual(len(columns), 7)

	def test_execute_returns_tuple(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.report.supplier_history.supplier_history import (
			execute,
		)

		filters = frappe._dict({"supplier": "__nonexistent__", "company": "_Test Company"})
		result = execute(filters)
		self.assertIsInstance(result, tuple)
		self.assertEqual(len(result), 5)
		columns, data, message, chart, summary = result
		self.assertIsInstance(data, list)
		self.assertEqual(len([r for r in data if not r.get("bold")]), 0)
```

- [ ] **Step 3.3: Run test — confirm it fails**

```bash
cd /home/frappeuser/bench16 && bench --site site16.local run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.report.supplier_history.test_supplier_history 2>&1 | tail -10
```

Expected: `ImportError`.

- [ ] **Step 3.4: Create supplier_history.json**

Create `cecypo_frappe_reports/cecypo_frappe_reports/report/supplier_history/supplier_history.json`:

```json
{
 "add_total_row": 0,
 "columns": [],
 "creation": "2026-04-02 00:00:00.000000",
 "disabled": 0,
 "docstatus": 0,
 "doctype": "Report",
 "filters": [],
 "is_standard": "Yes",
 "modified": "2026-04-02 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Cecypo Frappe Reports",
 "name": "Supplier History",
 "owner": "Administrator",
 "prepared_report": 0,
 "ref_doctype": "Supplier",
 "report_name": "Supplier History",
 "report_type": "Script Report",
 "roles": [
  {"role": "Purchase Manager"},
  {"role": "Purchase User"},
  {"role": "Accounts Manager"},
  {"role": "Accounts User"}
 ]
}
```

- [ ] **Step 3.5: Implement supplier_history.py**

Create `cecypo_frappe_reports/cecypo_frappe_reports/report/supplier_history/supplier_history.py`:

```python
# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from pypika import functions as fn


def execute(filters=None):
	if not filters:
		filters = frappe._dict({})

	if not filters.get("supplier"):
		return get_columns(), [], None, None, []

	columns = get_columns()
	data = get_data(filters)
	report_summary = get_report_summary(data)

	return columns, data, None, None, report_summary


def get_columns():
	return [
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 130,
		},
		{
			"label": _("Item Name"),
			"fieldname": "item_name",
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"label": _("Total Qty"),
			"fieldname": "total_qty",
			"fieldtype": "Float",
			"precision": 2,
			"width": 90,
		},
		{
			"label": _("Receipts"),
			"fieldname": "receipt_count",
			"fieldtype": "Int",
			"width": 70,
		},
		{
			"label": _("Avg Valuation Rate"),
			"fieldname": "avg_valuation_rate",
			"fieldtype": "Float",
			"precision": 2,
			"width": 140,
		},
		{
			"label": _("Total Amount"),
			"fieldname": "total_amount",
			"fieldtype": "Float",
			"precision": 2,
			"width": 140,
		},
		{
			"label": _("Last Purchase"),
			"fieldname": "last_purchase",
			"fieldtype": "Date",
			"width": 100,
		},
	]


def get_data(filters):
	pri = frappe.qb.DocType("Purchase Receipt Item")
	pr = frappe.qb.DocType("Purchase Receipt")

	query = (
		frappe.qb.from_(pri)
		.inner_join(pr)
		.on(pri.parent == pr.name)
		.select(
			pri.item_code,
			pri.item_name,
			fn.Sum(pri.qty).as_("total_qty"),
			fn.CountDistinct(pr.name).as_("receipt_count"),
			fn.Avg(pri.valuation_rate).as_("avg_valuation_rate"),
			fn.Sum(pri.base_amount).as_("total_amount"),
			fn.Max(pr.posting_date).as_("last_purchase"),
		)
		.where(pr.docstatus == 1)
		.where(pr.supplier == filters.supplier)
		.where(pr.company == filters.company)
		.groupby(pri.item_code, pri.item_name)
		.orderby(fn.Sum(pri.base_amount), order=frappe.qb.desc)
	)

	if filters.get("from_date"):
		query = query.where(pr.posting_date >= filters.from_date)
	if filters.get("to_date"):
		query = query.where(pr.posting_date <= filters.to_date)

	rows = query.run(as_dict=True)
	for r in rows:
		r["total_qty"] = flt(r["total_qty"], 2)
		r["avg_valuation_rate"] = flt(r["avg_valuation_rate"], 2)
		r["total_amount"] = flt(r["total_amount"], 2)

	if rows:
		rows.append({
			"item_code": None,
			"item_name": _("Total"),
			"total_qty": flt(sum(r["total_qty"] for r in rows), 2),
			"receipt_count": sum(r["receipt_count"] for r in rows),
			"avg_valuation_rate": None,
			"total_amount": flt(sum(r["total_amount"] for r in rows), 2),
			"last_purchase": None,
			"bold": 1,
		})

	return rows


def get_report_summary(data):
	rows = [r for r in data if not r.get("bold")]
	if not rows:
		return []

	return [
		{"value": len(rows), "label": _("Total Items"), "datatype": "Int", "indicator": "Blue"},
		{"value": flt(sum(r["total_qty"] for r in rows), 2), "label": _("Total Qty Purchased"), "datatype": "Float", "indicator": "Blue"},
		{"value": flt(sum(r["total_amount"] for r in rows), 2), "label": _("Total Spend"), "datatype": "Float", "indicator": "Blue"},
	]
```

- [ ] **Step 3.6: Implement supplier_history.js**

Create `cecypo_frappe_reports/cecypo_frappe_reports/report/supplier_history/supplier_history.js`:

```javascript
// Copyright (c) 2026, Cecypo and contributors
// For license information, please see license.txt

frappe.query_reports["Supplier History"] = {
	filters: [
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
			reqd: 1,
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		if (
			(column.fieldtype === "Float" || column.fieldtype === "Currency") &&
			value != null
		) {
			return format_number(value, null, 2);
		}
		return default_formatter(value, row, column, data);
	},
	onload(report) {
		report.page.add_button(__("Best Fit"), () => {
			const dt = report.datatable;
			if (!dt) return;
			dt.header
				.querySelectorAll(".dt-cell .dt-cell__resize-handle")
				.forEach((h) => h.dispatchEvent(new MouseEvent("dblclick", { bubbles: true })));
		});
	},
};
```

- [ ] **Step 3.7: Run tests — expect pass**

```bash
cd /home/frappeuser/bench16 && bench --site site16.local run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.report.supplier_history.test_supplier_history 2>&1 | tail -10
```

Expected: `OK` and `Ran 2 tests`.

- [ ] **Step 3.8: Migrate**

```bash
cd /home/frappeuser/bench16 && bench --site site16.local migrate 2>&1 | tail -5
```

- [ ] **Step 3.9: Commit**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports && git add cecypo_frappe_reports/cecypo_frappe_reports/report/supplier_history/ && git commit -m "$(cat <<'EOF'
feat: add Supplier History script report

Item-wise purchase summary per supplier with total qty, receipt count,
avg valuation rate, total amount, and last purchase date.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Transaction History Page — Backend API

**Files:**
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/__init__.py`
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py`

- [ ] **Step 4.1: Create page directory**

```bash
mkdir -p /home/frappeuser/bench16/apps/cecypo_frappe_reports/cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history
touch /home/frappeuser/bench16/apps/cecypo_frappe_reports/cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/__init__.py
```

- [ ] **Step 4.2: Implement transaction_history.py**

Create `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py`:

```python
# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_item_history(item, company, from_date=None, to_date=None, warehouse=None):
	"""Returns item details, stock metrics, purchase rows, and sales rows."""
	return {
		"item_details": _get_item_details(item),
		"stock_metrics": _get_stock_metrics(item, company, warehouse),
		"purchases": _get_purchase_rows(item, company, from_date, to_date, warehouse),
		"sales": _get_sales_rows(item, company, from_date, to_date, warehouse),
	}


@frappe.whitelist()
def get_customer_history(customer, company, from_date=None, to_date=None):
	"""Returns item-wise sales summary for a customer."""
	sii = frappe.qb.DocType("Sales Invoice Item")
	si = frappe.qb.DocType("Sales Invoice")
	from pypika import functions as fn

	query = (
		frappe.qb.from_(sii)
		.inner_join(si).on(sii.parent == si.name)
		.select(
			sii.item_code,
			sii.item_name,
			fn.Sum(sii.qty).as_("total_qty"),
			fn.CountDistinct(si.name).as_("invoice_count"),
			fn.Avg(sii.base_rate).as_("avg_rate"),
			fn.Sum(sii.base_amount).as_("total_amount"),
			fn.Max(si.posting_date).as_("last_sale"),
		)
		.where(si.docstatus == 1)
		.where(si.customer == customer)
		.where(si.company == company)
		.groupby(sii.item_code, sii.item_name)
		.orderby(fn.Sum(sii.base_amount), order=frappe.qb.desc)
	)
	if from_date:
		query = query.where(si.posting_date >= from_date)
	if to_date:
		query = query.where(si.posting_date <= to_date)

	rows = query.run(as_dict=True)
	for r in rows:
		r["total_qty"] = flt(r["total_qty"], 2)
		r["avg_rate"] = flt(r["avg_rate"], 2)
		r["total_amount"] = flt(r["total_amount"], 2)
	return rows


@frappe.whitelist()
def get_customer_item_transactions(customer, item_code, company, from_date=None, to_date=None):
	"""Returns individual Sales Invoice rows for a customer+item drill-down."""
	sii = frappe.qb.DocType("Sales Invoice Item")
	si = frappe.qb.DocType("Sales Invoice")

	query = (
		frappe.qb.from_(sii)
		.inner_join(si).on(sii.parent == si.name)
		.select(
			si.posting_date.as_("date"),
			sii.parent.as_("voucher_no"),
			sii.qty,
			sii.uom,
			sii.rate,
			si.currency,
			sii.base_rate,
		)
		.where(si.docstatus == 1)
		.where(si.customer == customer)
		.where(sii.item_code == item_code)
		.where(si.company == company)
		.orderby(si.posting_date, order=frappe.qb.desc)
	)
	if from_date:
		query = query.where(si.posting_date >= from_date)
	if to_date:
		query = query.where(si.posting_date <= to_date)

	rows = query.run(as_dict=True)
	for r in rows:
		r["qty"] = flt(r["qty"], 2)
		r["rate"] = flt(r["rate"], 2)
		r["base_rate"] = flt(r["base_rate"], 2)
	return rows


@frappe.whitelist()
def get_supplier_history(supplier, company, from_date=None, to_date=None):
	"""Returns item-wise purchase summary for a supplier."""
	pri = frappe.qb.DocType("Purchase Receipt Item")
	pr = frappe.qb.DocType("Purchase Receipt")
	from pypika import functions as fn

	query = (
		frappe.qb.from_(pri)
		.inner_join(pr).on(pri.parent == pr.name)
		.select(
			pri.item_code,
			pri.item_name,
			fn.Sum(pri.qty).as_("total_qty"),
			fn.CountDistinct(pr.name).as_("receipt_count"),
			fn.Avg(pri.valuation_rate).as_("avg_valuation_rate"),
			fn.Sum(pri.base_amount).as_("total_amount"),
			fn.Max(pr.posting_date).as_("last_purchase"),
		)
		.where(pr.docstatus == 1)
		.where(pr.supplier == supplier)
		.where(pr.company == company)
		.groupby(pri.item_code, pri.item_name)
		.orderby(fn.Sum(pri.base_amount), order=frappe.qb.desc)
	)
	if from_date:
		query = query.where(pr.posting_date >= from_date)
	if to_date:
		query = query.where(pr.posting_date <= to_date)

	rows = query.run(as_dict=True)
	for r in rows:
		r["total_qty"] = flt(r["total_qty"], 2)
		r["avg_valuation_rate"] = flt(r["avg_valuation_rate"], 2)
		r["total_amount"] = flt(r["total_amount"], 2)
	return rows


@frappe.whitelist()
def get_supplier_item_transactions(supplier, item_code, company, from_date=None, to_date=None):
	"""Returns individual Purchase Receipt rows for a supplier+item drill-down."""
	pri = frappe.qb.DocType("Purchase Receipt Item")
	pr = frappe.qb.DocType("Purchase Receipt")

	query = (
		frappe.qb.from_(pri)
		.inner_join(pr).on(pri.parent == pr.name)
		.select(
			pr.posting_date.as_("date"),
			pri.parent.as_("voucher_no"),
			pri.qty,
			pri.uom,
			pri.rate,
			pr.currency,
			pri.valuation_rate,
		)
		.where(pr.docstatus == 1)
		.where(pr.supplier == supplier)
		.where(pri.item_code == item_code)
		.where(pr.company == company)
		.orderby(pr.posting_date, order=frappe.qb.desc)
	)
	if from_date:
		query = query.where(pr.posting_date >= from_date)
	if to_date:
		query = query.where(pr.posting_date <= to_date)

	rows = query.run(as_dict=True)
	for r in rows:
		r["qty"] = flt(r["qty"], 2)
		r["rate"] = flt(r["rate"], 2)
		r["valuation_rate"] = flt(r["valuation_rate"], 2)
	return rows


# ── Private helpers ──────────────────────────────────────────────────────────

def _get_item_details(item):
	return frappe.db.get_value(
		"Item",
		item,
		["item_name", "item_code", "brand", "item_group", "stock_uom", "valuation_method"],
		as_dict=True,
	) or {}


def _get_stock_metrics(item, company, warehouse=None):
	filters = {"item_code": item}
	if warehouse:
		filters["warehouse"] = warehouse

	bin_rows = frappe.db.get_all("Bin", filters=filters, fields=["actual_qty", "valuation_rate"])
	total_qty = flt(sum(flt(b.actual_qty) for b in bin_rows), 2)
	stock_value = flt(sum(flt(b.actual_qty) * flt(b.valuation_rate) for b in bin_rows), 2)
	avg_rate = flt(stock_value / total_qty, 2) if total_qty else 0.0

	# Pending PO: qty not yet received
	poi = frappe.qb.DocType("Purchase Order Item")
	po = frappe.qb.DocType("Purchase Order")
	pending_po = (
		frappe.qb.from_(poi)
		.inner_join(po).on(poi.parent == po.name)
		.select((poi.qty - poi.received_qty).as_("pending"))
		.where(po.docstatus == 1)
		.where(poi.item_code == item)
		.where(po.company == company)
		.where(poi.qty > poi.received_qty)
		.run()
	)
	pending_po_qty = flt(sum(r[0] for r in pending_po), 2)

	# Pending SO: qty not yet delivered
	soi = frappe.qb.DocType("Sales Order Item")
	so = frappe.qb.DocType("Sales Order")
	pending_so = (
		frappe.qb.from_(soi)
		.inner_join(so).on(soi.parent == so.name)
		.select((soi.qty - soi.delivered_qty).as_("pending"))
		.where(so.docstatus == 1)
		.where(soi.item_code == item)
		.where(so.company == company)
		.where(soi.qty > soi.delivered_qty)
		.run()
	)
	pending_so_qty = flt(sum(r[0] for r in pending_so), 2)

	reorder = frappe.db.get_value(
		"Item Reorder", {"parent": item}, "warehouse_reorder_level"
	) or "—"

	return {
		"current_stock": total_qty,
		"avg_rate": avg_rate,
		"stock_value": stock_value,
		"pending_po_qty": pending_po_qty,
		"pending_so_qty": pending_so_qty,
		"reorder_level": reorder,
	}


def _get_purchase_rows(item, company, from_date, to_date, warehouse):
	pri = frappe.qb.DocType("Purchase Receipt Item")
	pr = frappe.qb.DocType("Purchase Receipt")

	query = (
		frappe.qb.from_(pri)
		.inner_join(pr).on(pri.parent == pr.name)
		.select(
			pr.posting_date.as_("date"),
			pri.parent.as_("voucher_no"),
			pr.supplier,
			pri.qty,
			pri.uom,
			pri.rate,
			pr.currency,
			pri.valuation_rate,
		)
		.where(pr.docstatus == 1)
		.where(pri.item_code == item)
		.where(pr.company == company)
		.orderby(pr.posting_date, order=frappe.qb.desc)
	)
	if from_date:
		query = query.where(pr.posting_date >= from_date)
	if to_date:
		query = query.where(pr.posting_date <= to_date)
	if warehouse:
		query = query.where(pri.warehouse == warehouse)

	rows = query.run(as_dict=True)
	for r in rows:
		r["qty"] = flt(r["qty"], 2)
		r["rate"] = flt(r["rate"], 2)
		r["valuation_rate"] = flt(r["valuation_rate"], 2)
	return rows


def _get_sales_rows(item, company, from_date, to_date, warehouse):
	sii = frappe.qb.DocType("Sales Invoice Item")
	si = frappe.qb.DocType("Sales Invoice")

	query = (
		frappe.qb.from_(sii)
		.inner_join(si).on(sii.parent == si.name)
		.select(
			si.posting_date.as_("date"),
			sii.parent.as_("voucher_no"),
			si.customer,
			sii.qty,
			sii.uom,
			sii.rate,
			si.currency,
			sii.base_rate,
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

	rows = query.run(as_dict=True)
	for r in rows:
		r["qty"] = flt(r["qty"], 2)
		r["rate"] = flt(r["rate"], 2)
		r["base_rate"] = flt(r["base_rate"], 2)
	return rows
```

- [ ] **Step 4.3: Commit backend API**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports && git add cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/__init__.py cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py && git commit -m "$(cat <<'EOF'
feat: add transaction history page backend API

Six whitelisted functions: get_item_history, get_customer_history,
get_customer_item_transactions, get_supplier_history,
get_supplier_item_transactions, plus private query helpers.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Transaction History Page — Frontend

**Files:**
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.json`
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.js`

- [ ] **Step 5.1: Create transaction_history.json**

Create `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.json`:

```json
{
 "content": null,
 "creation": "2026-04-02 00:00:00.000000",
 "docstatus": 0,
 "doctype": "Page",
 "idx": 0,
 "modified": "2026-04-02 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Cecypo Frappe Reports",
 "name": "transaction-history",
 "owner": "Administrator",
 "page_name": "transaction-history",
 "restrict_to_domain": "",
 "roles": [
  {"role": "Stock Manager"},
  {"role": "Stock User"},
  {"role": "Purchase Manager"},
  {"role": "Purchase User"},
  {"role": "Sales Manager"},
  {"role": "Sales User"},
  {"role": "Accounts Manager"},
  {"role": "Accounts User"}
 ],
 "standard": "Yes",
 "system_page": 0,
 "title": "Transaction History"
}
```

- [ ] **Step 5.2: Implement transaction_history.js**

Create `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.js`:

```javascript
// Copyright (c) 2026, Cecypo and contributors
// For license information, please see license.txt

frappe.pages["transaction-history"].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Transaction History"),
		single_column: true,
	});
	new TransactionHistoryPage(page);
};

class TransactionHistoryPage {
	constructor(page) {
		this.page = page;
		this.active_tab = "item";
		this.controls = {};
		this._render();
		this._bind_tabs();
	}

	// ── Layout ────────────────────────────────────────────────────────────────

	_render() {
		$(this.page.main).html(`
			<div class="transaction-history" style="padding:16px">
				<div class="th-tab-bar" style="display:flex;border-bottom:2px solid var(--border-color);margin-bottom:16px">
					<button class="th-tab btn btn-default active" data-tab="item"
						style="border:none;border-bottom:2px solid var(--primary);margin-bottom:-2px;border-radius:0;font-weight:600;padding:8px 20px">
						${__("Item History")}
					</button>
					<button class="th-tab btn btn-default" data-tab="customer"
						style="border:none;border-bottom:2px solid transparent;margin-bottom:-2px;border-radius:0;padding:8px 20px">
						${__("Customer History")}
					</button>
					<button class="th-tab btn btn-default" data-tab="supplier"
						style="border:none;border-bottom:2px solid transparent;margin-bottom:-2px;border-radius:0;padding:8px 20px">
						${__("Supplier History")}
					</button>
				</div>

				<div class="th-panel" data-panel="item">
					<div class="th-filters item-filters" style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px">
						<div class="ctrl-item-item" style="min-width:200px"></div>
						<div class="ctrl-item-company" style="min-width:180px"></div>
						<div class="ctrl-item-from" style="min-width:120px"></div>
						<div class="ctrl-item-to" style="min-width:120px"></div>
						<div class="ctrl-item-warehouse" style="min-width:160px"></div>
						<button class="btn btn-primary btn-sm btn-get-item">${__("Get History")}</button>
					</div>
					<div class="th-content item-content"></div>
				</div>

				<div class="th-panel hidden" data-panel="customer">
					<div class="th-filters customer-filters" style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px">
						<div class="ctrl-cust-customer" style="min-width:220px"></div>
						<div class="ctrl-cust-company" style="min-width:180px"></div>
						<div class="ctrl-cust-from" style="min-width:120px"></div>
						<div class="ctrl-cust-to" style="min-width:120px"></div>
						<button class="btn btn-primary btn-sm btn-get-customer">${__("Get History")}</button>
					</div>
					<div class="th-content customer-content"></div>
				</div>

				<div class="th-panel hidden" data-panel="supplier">
					<div class="th-filters supplier-filters" style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px">
						<div class="ctrl-supp-supplier" style="min-width:220px"></div>
						<div class="ctrl-supp-company" style="min-width:180px"></div>
						<div class="ctrl-supp-from" style="min-width:120px"></div>
						<div class="ctrl-supp-to" style="min-width:120px"></div>
						<button class="btn btn-primary btn-sm btn-get-supplier">${__("Get History")}</button>
					</div>
					<div class="th-content supplier-content"></div>
				</div>
			</div>
		`);
		this._setup_controls();
	}

	_setup_controls() {
		const m = this.page.main;
		const default_company = frappe.defaults.get_user_default("Company");
		const make = (parent, df) =>
			frappe.ui.form.make_control({ parent: $(m).find(parent)[0], df, render_input: true });

		// Item tab
		this.controls.item = make(".ctrl-item-item", { fieldtype: "Link", options: "Item", fieldname: "item", label: __("Item"), reqd: 1 });
		this.controls.item_company = make(".ctrl-item-company", { fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company"), reqd: 1, default: default_company });
		this.controls.item_from = make(".ctrl-item-from", { fieldtype: "Date", fieldname: "from_date", label: __("From Date") });
		this.controls.item_to = make(".ctrl-item-to", { fieldtype: "Date", fieldname: "to_date", label: __("To Date") });
		this.controls.item_warehouse = make(".ctrl-item-warehouse", { fieldtype: "Link", options: "Warehouse", fieldname: "warehouse", label: __("Warehouse") });

		if (default_company) this.controls.item_company.set_value(default_company);

		// Customer tab
		this.controls.customer = make(".ctrl-cust-customer", { fieldtype: "Link", options: "Customer", fieldname: "customer", label: __("Customer"), reqd: 1 });
		this.controls.cust_company = make(".ctrl-cust-company", { fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company"), reqd: 1, default: default_company });
		this.controls.cust_from = make(".ctrl-cust-from", { fieldtype: "Date", fieldname: "from_date", label: __("From Date") });
		this.controls.cust_to = make(".ctrl-cust-to", { fieldtype: "Date", fieldname: "to_date", label: __("To Date") });

		if (default_company) this.controls.cust_company.set_value(default_company);

		// Supplier tab
		this.controls.supplier = make(".ctrl-supp-supplier", { fieldtype: "Link", options: "Supplier", fieldname: "supplier", label: __("Supplier"), reqd: 1 });
		this.controls.supp_company = make(".ctrl-supp-company", { fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company"), reqd: 1, default: default_company });
		this.controls.supp_from = make(".ctrl-supp-from", { fieldtype: "Date", fieldname: "from_date", label: __("From Date") });
		this.controls.supp_to = make(".ctrl-supp-to", { fieldtype: "Date", fieldname: "to_date", label: __("To Date") });

		if (default_company) this.controls.supp_company.set_value(default_company);
	}

	// ── Tab switching ────────────────────────────────────────────────────────

	_bind_tabs() {
		const m = this.page.main;
		$(m).on("click", ".th-tab", (e) => {
			let tab = $(e.currentTarget).data("tab");
			$(m).find(".th-tab").css("border-bottom-color", "transparent").css("font-weight", "normal");
			$(e.currentTarget).css("border-bottom-color", "var(--primary)").css("font-weight", "600");
			$(m).find(".th-panel").addClass("hidden");
			$(m).find(`[data-panel="${tab}"]`).removeClass("hidden");
			this.active_tab = tab;
		});

		$(m).on("click", ".btn-get-item", () => this._load_item_history());
		$(m).on("click", ".btn-get-customer", () => this._load_customer_history());
		$(m).on("click", ".btn-get-supplier", () => this._load_supplier_history());
	}

	// ── Item History ─────────────────────────────────────────────────────────

	_load_item_history() {
		let item = this.controls.item.get_value();
		let company = this.controls.item_company.get_value();
		if (!item || !company) {
			frappe.msgprint(__("Item and Company are required"));
			return;
		}
		let $content = $(this.page.main).find(".item-content");
		$content.html(`<div class="text-muted" style="padding:20px">${__("Loading...")}</div>`);

		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_item_history",
			args: {
				item,
				company,
				from_date: this.controls.item_from.get_value() || null,
				to_date: this.controls.item_to.get_value() || null,
				warehouse: this.controls.item_warehouse.get_value() || null,
			},
			callback: (r) => {
				if (r.message) $content.html(this._render_item_history(r.message));
			},
		});
	}

	_render_item_history({ item_details, stock_metrics, purchases, sales }) {
		return `
			${this._render_metrics_grid(item_details, stock_metrics)}
			<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px">
				${this._render_purchase_panel(purchases)}
				${this._render_sales_panel(sales)}
			</div>
		`;
	}

	_render_metrics_grid(d, m) {
		const row = (label, value, bold) =>
			`<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--border-color)">
				<span style="color:var(--text-muted)">${label}</span>
				<span${bold ? ' style="font-weight:700"' : ""}>${value ?? "—"}</span>
			</div>`;

		const stock_color = (m.current_stock || 0) > 0 ? "var(--green)" : "var(--red)";

		return `
			<div style="display:grid;grid-template-columns:1fr 1fr;gap:0 24px;background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:14px 18px">
				<div>
					${row(__("Item Name"), d.item_name, true)}
					${row(__("Brand"), d.brand)}
					${row(__("Stock UOM"), d.stock_uom)}
					${row(__("Current Stock"), `<span style="color:${stock_color};font-weight:700">${format_number(m.current_stock, null, 2)} ${d.stock_uom || ""}</span>`)}
					${row(__("Avg. Stock Rate"), format_number(m.avg_rate, null, 2))}
					${row(__("Stock Value"), format_number(m.stock_value, null, 2))}
				</div>
				<div>
					${row(__("Item Code"), d.item_code, true)}
					${row(__("Item Group"), d.item_group)}
					${row(__("Valuation Method"), d.valuation_method)}
					${row(__("Pending PO Qty"), format_number(m.pending_po_qty, null, 2))}
					${row(__("Pending SO Qty"), format_number(m.pending_so_qty, null, 2))}
					${row(__("Reorder Level"), m.reorder_level)}
				</div>
			</div>`;
	}

	_render_purchase_panel(rows) {
		let total_qty = rows.reduce((s, r) => s + (r.qty || 0), 0);
		return `
			<div style="border:1px solid var(--border-color);border-radius:6px;overflow:hidden">
				<div style="background:var(--green-highlight, #e8f5e9);padding:8px 12px;font-weight:700;color:var(--green, #2e7d32);display:flex;justify-content:space-between">
					<span>${__("Purchases")}</span>
					<span style="font-weight:400;font-size:12px">${__("Total Qty: {0}", [format_number(total_qty, null, 2)])}</span>
				</div>
				<div style="overflow-x:auto">
					<table style="width:100%;border-collapse:collapse;font-size:12px">
						<thead>
							<tr style="background:var(--subtle-fg)">
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Date")}</th>
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Voucher")}</th>
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Supplier")}</th>
								<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Qty")}</th>
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("UOM")}</th>
								<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Rate")}</th>
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Curr.")}</th>
								<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:700;border-bottom:1px solid var(--border-color)">${__("Val. Rate")}</th>
							</tr>
						</thead>
						<tbody>
							${rows.length ? rows.map((r, i) => `
								<tr style="${i % 2 ? "background:var(--subtle-fg)" : ""}">
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${frappe.datetime.str_to_user(r.date)}</td>
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/purchase-receipt/${r.voucher_no}">${r.voucher_no}</a></td>
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.supplier || ""}</td>
									<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.qty, null, 2)}</td>
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.uom || ""}</td>
									<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.rate, null, 2)}</td>
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><span style="background:#e3f2fd;padding:2px 5px;border-radius:3px;font-size:10px;font-weight:600">${r.currency || ""}</span></td>
									<td style="padding:4px 8px;text-align:right;font-weight:600;border-bottom:1px solid var(--border-color)">${format_number(r.valuation_rate, null, 2)}</td>
								</tr>`).join("") : `<tr><td colspan="8" style="padding:12px;text-align:center;color:var(--text-muted)">${__("No purchases found")}</td></tr>`}
						</tbody>
					</table>
				</div>
			</div>`;
	}

	_render_sales_panel(rows) {
		let total_qty = rows.reduce((s, r) => s + (r.qty || 0), 0);
		return `
			<div style="border:1px solid var(--border-color);border-radius:6px;overflow:hidden">
				<div style="background:var(--blue-highlight, #e3f2fd);padding:8px 12px;font-weight:700;color:var(--blue, #1565c0);display:flex;justify-content:space-between">
					<span>${__("Sales")}</span>
					<span style="font-weight:400;font-size:12px">${__("Total Qty: {0}", [format_number(total_qty, null, 2)])}</span>
				</div>
				<div style="overflow-x:auto">
					<table style="width:100%;border-collapse:collapse;font-size:12px">
						<thead>
							<tr style="background:var(--subtle-fg)">
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Date")}</th>
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Voucher")}</th>
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Customer")}</th>
								<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Qty")}</th>
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("UOM")}</th>
								<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Rate")}</th>
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Curr.")}</th>
								<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:700;border-bottom:1px solid var(--border-color)">${__("Base Rate")}</th>
							</tr>
						</thead>
						<tbody>
							${rows.length ? rows.map((r, i) => `
								<tr style="${i % 2 ? "background:var(--subtle-fg)" : ""}">
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${frappe.datetime.str_to_user(r.date)}</td>
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/sales-invoice/${r.voucher_no}">${r.voucher_no}</a></td>
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.customer || ""}</td>
									<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.qty, null, 2)}</td>
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.uom || ""}</td>
									<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.rate, null, 2)}</td>
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><span style="background:#fce4ec;padding:2px 5px;border-radius:3px;font-size:10px;font-weight:600">${r.currency || ""}</span></td>
									<td style="padding:4px 8px;text-align:right;font-weight:600;border-bottom:1px solid var(--border-color)">${format_number(r.base_rate, null, 2)}</td>
								</tr>`).join("") : `<tr><td colspan="8" style="padding:12px;text-align:center;color:var(--text-muted)">${__("No sales found")}</td></tr>`}
						</tbody>
					</table>
				</div>
			</div>`;
	}

	// ── Customer History ──────────────────────────────────────────────────────

	_load_customer_history() {
		let customer = this.controls.customer.get_value();
		let company = this.controls.cust_company.get_value();
		if (!customer || !company) { frappe.msgprint(__("Customer and Company are required")); return; }
		let $content = $(this.page.main).find(".customer-content");
		$content.html(`<div class="text-muted" style="padding:20px">${__("Loading...")}</div>`);

		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_customer_history",
			args: {
				customer,
				company,
				from_date: this.controls.cust_from.get_value() || null,
				to_date: this.controls.cust_to.get_value() || null,
			},
			callback: (r) => {
				if (r.message != null)
					$content.html(this._render_party_summary(r.message, "customer", customer, company));
			},
		});
	}

	// ── Supplier History ──────────────────────────────────────────────────────

	_load_supplier_history() {
		let supplier = this.controls.supplier.get_value();
		let company = this.controls.supp_company.get_value();
		if (!supplier || !company) { frappe.msgprint(__("Supplier and Company are required")); return; }
		let $content = $(this.page.main).find(".supplier-content");
		$content.html(`<div class="text-muted" style="padding:20px">${__("Loading...")}</div>`);

		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_supplier_history",
			args: {
				supplier,
				company,
				from_date: this.controls.supp_from.get_value() || null,
				to_date: this.controls.supp_to.get_value() || null,
			},
			callback: (r) => {
				if (r.message != null)
					$content.html(this._render_party_summary(r.message, "supplier", supplier, company));
			},
		});
	}

	// ── Shared: accordion summary table ──────────────────────────────────────

	_render_party_summary(rows, party_type, party, company) {
		if (!rows.length)
			return `<div class="text-muted" style="padding:20px">${__("No transactions found")}</div>`;

		const is_customer = party_type === "customer";
		const qty_col = __("Total Qty");
		const count_col = is_customer ? __("Invoices") : __("Receipts");
		const rate_col = is_customer ? __("Avg Rate") : __("Avg Val. Rate");
		const date_col = is_customer ? __("Last Sale") : __("Last Purchase");
		const count_key = is_customer ? "invoice_count" : "receipt_count";
		const rate_key = is_customer ? "avg_rate" : "avg_valuation_rate";
		const date_key = is_customer ? "last_sale" : "last_purchase";

		return `
			<table style="width:100%;border-collapse:collapse;font-size:12px">
				<thead>
					<tr style="background:var(--subtle-fg)">
						<th style="padding:5px 8px;width:28px;border-bottom:1px solid var(--border-color)"></th>
						<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Item Code")}</th>
						<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Item Name")}</th>
						<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${qty_col}</th>
						<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${count_col}</th>
						<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${rate_col}</th>
						<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:700;border-bottom:1px solid var(--border-color)">${__("Total Amount")}</th>
						<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${date_col}</th>
					</tr>
				</thead>
				<tbody>
					${rows.map((r, i) => `
						<tr class="summary-row" data-item="${r.item_code}" data-party="${party}" data-party-type="${party_type}" data-company="${company}"
							style="${i % 2 ? "background:var(--subtle-fg)" : ""};cursor:pointer"
							title="${__("Click to expand transactions")}">
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color);color:var(--text-muted)">▶</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/item/${r.item_code}">${r.item_code}</a></td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.item_name}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.total_qty, null, 2)}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r[count_key]}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r[rate_key], null, 2)}</td>
							<td style="padding:4px 8px;text-align:right;font-weight:700;border-bottom:1px solid var(--border-color)">${format_number(r.total_amount, null, 2)}</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r[date_key] ? frappe.datetime.str_to_user(r[date_key]) : "—"}</td>
						</tr>
						<tr class="detail-row hidden" data-detail-for="${r.item_code}">
							<td colspan="8" style="padding:0;border-bottom:2px solid var(--border-color)">
								<div class="detail-content" style="padding:8px 24px;background:var(--fg-color)">
									<span class="text-muted">${__("Loading...")}</span>
								</div>
							</td>
						</tr>
					`).join("")}
				</tbody>
			</table>`;
	}

	// ── Accordion bind (called after render via event delegation) ────────────

	_bind_tabs() {
		const m = this.page.main;

		// Tab switching
		$(m).on("click", ".th-tab", (e) => {
			$(m).find(".th-tab").css("border-bottom-color", "transparent").css("font-weight", "normal");
			$(e.currentTarget).css("border-bottom-color", "var(--primary)").css("font-weight", "600");
			$(m).find(".th-panel").addClass("hidden");
			$(m).find(`[data-panel="${$(e.currentTarget).data("tab")}"]`).removeClass("hidden");
		});

		$(m).on("click", ".btn-get-item", () => this._load_item_history());
		$(m).on("click", ".btn-get-customer", () => this._load_customer_history());
		$(m).on("click", ".btn-get-supplier", () => this._load_supplier_history());

		// Accordion: expand/collapse summary rows
		$(m).on("click", ".summary-row", (e) => {
			let $row = $(e.currentTarget);
			let item_code = $row.data("item");
			let party = $row.data("party");
			let party_type = $row.data("party-type");
			let company = $row.data("company");
			let $detail = $(m).find(`.detail-row[data-detail-for="${item_code}"]`);

			if (!$detail.hasClass("hidden")) {
				$detail.addClass("hidden");
				$row.find("td:first").text("▶");
				return;
			}

			$row.find("td:first").text("▼");
			$detail.removeClass("hidden");

			// Only fetch if not already loaded
			if ($detail.find(".detail-content").data("loaded")) return;

			let is_customer = party_type === "customer";
			let from_date = is_customer ? this.controls.cust_from.get_value() : this.controls.supp_from.get_value();
			let to_date = is_customer ? this.controls.cust_to.get_value() : this.controls.supp_to.get_value();

			frappe.call({
				method: is_customer
					? "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_customer_item_transactions"
					: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_supplier_item_transactions",
				args: {
					[party_type]: party,
					item_code,
					company,
					from_date: from_date || null,
					to_date: to_date || null,
				},
				callback: (r) => {
					let html = this._render_detail_rows(r.message || [], is_customer);
					$detail.find(".detail-content").html(html).data("loaded", true);
				},
			});
		});
	}

	_render_detail_rows(rows, is_customer) {
		if (!rows.length)
			return `<span class="text-muted">${__("No transactions found")}</span>`;

		const rate_label = is_customer ? __("Base Rate") : __("Val. Rate");
		const rate_key = is_customer ? "base_rate" : "valuation_rate";

		return `
			<table style="width:100%;border-collapse:collapse;font-size:11px">
				<thead>
					<tr style="background:var(--yellow-highlight, #fffde7)">
						<th style="padding:3px 8px;text-align:left;color:var(--text-muted)">${__("Date")}</th>
						<th style="padding:3px 8px;text-align:left;color:var(--text-muted)">${__("Voucher No")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted)">${__("Qty")}</th>
						<th style="padding:3px 8px;text-align:left;color:var(--text-muted)">${__("UOM")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted)">${__("Rate")}</th>
						<th style="padding:3px 8px;text-align:left;color:var(--text-muted)">${__("Currency")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted);font-weight:700">${rate_label}</th>
					</tr>
				</thead>
				<tbody>
					${rows.map((r, i) => {
						let doctype_slug = is_customer ? "sales-invoice" : "purchase-receipt";
						return `
							<tr style="${i % 2 ? "background:var(--yellow-highlight, #fffde7)" : "background:var(--fg-color)"}">
								<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)">${frappe.datetime.str_to_user(r.date)}</td>
								<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/${doctype_slug}/${r.voucher_no}">${r.voucher_no}</a></td>
								<td style="padding:3px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.qty, null, 2)}</td>
								<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)">${r.uom || ""}</td>
								<td style="padding:3px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.rate, null, 2)}</td>
								<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)"><span style="background:#e3f2fd;padding:1px 4px;border-radius:3px;font-size:10px;font-weight:600">${r.currency || ""}</span></td>
								<td style="padding:3px 8px;text-align:right;font-weight:600;border-bottom:1px solid var(--border-color)">${format_number(r[rate_key], null, 2)}</td>
							</tr>`;
					}).join("")}
				</tbody>
			</table>`;
	}
}
```

- [ ] **Step 5.3: Build assets**

```bash
cd /home/frappeuser/bench16 && bench build --app cecypo_frappe_reports 2>&1 | tail -10
```

Expected: ends with `✓ Built` or similar, no errors.

- [ ] **Step 5.4: Migrate to register the page**

```bash
cd /home/frappeuser/bench16 && bench --site site16.local migrate 2>&1 | tail -5
```

- [ ] **Step 5.5: Clear cache and verify page loads**

```bash
cd /home/frappeuser/bench16 && bench --site site16.local clear-cache
```

Then open `http://site16.local:8002/transaction-history` in the browser. Verify:
- Page title shows "Transaction History"
- Three tabs are visible: Item History, Customer History, Supplier History
- Tab switching shows/hides panels
- Filter controls render (Link fields with autocomplete)
- Clicking "Get History" with a valid item + company returns data

- [ ] **Step 5.6: Commit**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports && git add cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/ && git commit -m "$(cat <<'EOF'
feat: add Transaction History custom page

Tabbed page at /transaction-history with Item History (50/50
side-by-side), Customer History (accordion drill-down), and
Supplier History (accordion drill-down).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: README Update

**Files:**
- Modify: `README.md`

- [ ] **Step 6.1: Update README.md with reports list**

Replace the content of `README.md` with:

```markdown
### Cecypo Reports

Custom reports pack for ERPNext, providing enhanced financial and inventory history reports.

### Reports

| Report | Module | Description |
|--------|--------|-------------|
| Sales Report Enhanced | Accounts | Sales invoices with payment mode breakdown |
| Accounts Receivable Summary Enhanced | Accounts | AR summary with ageing and payment details |
| Day Book | Accounts | GL entries by date — detailed or summarised by voucher type |
| Item History | Stock | Purchase and sales history for a specific item |
| Customer History | Accounts / Sales | Item-wise sales summary per customer with drill-down |
| Supplier History | Accounts / Purchase | Item-wise purchase summary per supplier with drill-down |

### Pages

| Page | URL | Description |
|------|-----|-------------|
| Transaction History | /transaction-history | Tabbed view: Item History, Customer History, Supplier History with side-by-side tables and accordion drill-down |

### Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app cecypo_frappe_reports
bench --site <site-name> migrate
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/cecypo_frappe_reports
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

agpl-3.0
```

- [ ] **Step 6.2: Commit**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports && git add README.md && git commit -m "$(cat <<'EOF'
docs: update README with full reports and pages list

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```
</content>
