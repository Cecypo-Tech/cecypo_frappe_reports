# Transaction History — Design Spec

**Date:** 2026-04-02
**App:** `cecypo_frappe_reports`
**Status:** Approved

---

## Overview

Three history views — Item History, Customer History, Supplier History — delivered as two artifacts:

1. **Custom Page** `/transaction-history` — tabbed, full-layout UI with 50/50 side-by-side tables and accordion drill-down
2. **Three Script Reports** — in the Reports menu, consistent with existing app reports (Day Book, Sales Report Enhanced)

---

## Artifact 1: Custom Page — `/transaction-history`

### Page structure

Single page with a persistent tab bar at the top:

```
[ Item History ]  [ Customer History ]  [ Supplier History ]
```

Each tab has its own filter bar, metrics section, and table(s). Switching tabs resets the filters and clears rendered data.

### Tab 1: Item History

**Filters**

| Field | Type | Required |
|-------|------|----------|
| Item | Link → Item | Yes |
| Company | Link → Company | Yes |
| From Date | Date | No |
| To Date | Date | No |
| Warehouse | Link → Warehouse | No |

**Metrics section** (B-style ERPNext form grid — two-column key-value)

Left column:
- Item Name
- Brand
- Stock UOM
- Current Stock (from Bin, bold green if > 0)
- Avg. Stock Rate
- Stock Value

Right column:
- Item Code
- Item Group
- Valuation Method
- Pending PO Qty (from Purchase Order Item: sum of qty − received_qty where docstatus=1)
- Pending SO Qty (from Sales Order Item: sum of qty − delivered_qty where docstatus=1)
- Reorder Level

**Tables — 50/50 side by side**

Left panel — Purchases (green header, `Purchase Receipt Item` → `Purchase Receipt`):

| Column | Source field | Notes |
|--------|-------------|-------|
| Date | `purchase_receipt.posting_date` | |
| Voucher No | `purchase_receipt.name` | Link to Purchase Receipt |
| Supplier | `purchase_receipt.supplier` | |
| Qty | `purchase_receipt_item.qty` | |
| UOM | `purchase_receipt_item.uom` | |
| Rate | `purchase_receipt_item.rate` | Transaction currency |
| Currency | `purchase_receipt.currency` | Badge pill |
| Valuation Rate | `purchase_receipt_item.valuation_rate` | Base currency, bold |

Right panel — Sales (blue header, `Sales Invoice Item` → `Sales Invoice`):

| Column | Source field | Notes |
|--------|-------------|-------|
| Date | `sales_invoice.posting_date` | |
| Voucher No | `sales_invoice.name` | Link to Sales Invoice |
| Customer | `sales_invoice.customer` | |
| Qty | `sales_invoice_item.qty` | |
| UOM | `sales_invoice_item.uom` | |
| Rate | `sales_invoice_item.rate` | Transaction currency |
| Currency | `sales_invoice.currency` | Badge pill |
| Base Rate | `sales_invoice_item.base_rate` | Base currency, bold |

Each panel header shows total qty across all rows.

### Tab 2: Customer History

**Filters**

| Field | Type | Required |
|-------|------|----------|
| Customer | Link → Customer | Yes |
| Company | Link → Company | Yes |
| From Date | Date | No |
| To Date | Date | No |

**Summary table** (one row per item, sourced from Sales Invoice Item → Sales Invoice, docstatus=1):

| Column | Source |
|--------|--------|
| Item Code | `sales_invoice_item.item_code` (link) |
| Item Name | `sales_invoice_item.item_name` |
| Total Qty | SUM(qty) |
| Invoices | COUNT(DISTINCT sales_invoice.name) |
| Avg Rate | AVG(base_rate) |
| Total Amount | SUM(base_amount) |
| Last Sale | MAX(sales_invoice.posting_date) |

Ordered by Total Amount DESC.

**Accordion drill-down**

Click ▶ on any item row → expands inline below it showing individual Sales Invoice transactions:

| Date | Voucher No | Qty | UOM | Rate | Currency | Base Rate |

Voucher No links to the Sales Invoice. Currency shown as a coloured badge pill. Collapse by clicking ▼.

### Tab 3: Supplier History

**Filters**

| Field | Type | Required |
|-------|------|----------|
| Supplier | Link → Supplier | Yes |
| Company | Link → Company | Yes |
| From Date | Date | No |
| To Date | Date | No |

**Summary table** (one row per item, sourced from Purchase Receipt Item → Purchase Receipt, docstatus=1):

| Column | Source |
|--------|--------|
| Item Code | `purchase_receipt_item.item_code` (link) |
| Item Name | `purchase_receipt_item.item_name` |
| Total Qty | SUM(qty) |
| Receipts | COUNT(DISTINCT purchase_receipt.name) |
| Avg Valuation Rate | AVG(valuation_rate) |
| Total Amount | SUM(base_amount) |
| Last Purchase | MAX(purchase_receipt.posting_date) |

Ordered by Total Amount DESC.

**Accordion drill-down**

Click ▶ on any item row → expands inline below it showing individual Purchase Receipt transactions:

| Date | Voucher No | Qty | UOM | Rate | Currency | Valuation Rate |

---

## Artifact 2: Script Reports (3 reports)

All reports follow the existing app pattern: `Script Report`, `is_standard: Yes`, module `Cecypo Frappe Reports`.

### 2a. Item History

- **ref_doctype:** Item
- **File path:** `cecypo_frappe_reports/report/item_history/`

**Filters:** Item (req), Company (req), From Date, To Date, Warehouse

**Columns:**

| Fieldname | Label | Type | Width |
|-----------|-------|------|-------|
| date | Date | Date | 100 |
| voucher_type | Voucher Type | Data | 140 |
| voucher_no | Voucher No | Dynamic Link → voucher_type | 160 |
| party | Party | Data | 180 |
| qty | Qty | Float | 80 |
| uom | UOM | Data | 70 |
| rate | Rate | Float | 110 |
| currency | Currency | Data | 70 |
| valuation_or_base_rate | Valuation / Base Rate | Float | 130 |

`party` is populated with `supplier` for purchase rows and `customer` for sales rows.
`valuation_or_base_rate` is populated with `valuation_rate` for purchase rows and `base_rate` for sales rows — both represent the base-currency rate for that transaction line.

**Data:** Purchases rows first (section header row, bold, green indicator), then Sales rows (section header row, bold, blue indicator). Both sorted by date DESC within their section.

Section header rows use `bold: 1` and span all columns with a summary label:
- `── Purchases (N transactions · X units) ──`
- `── Sales (N transactions · X units) ──`

**report_summary (5 items):**
1. Current Stock (from Bin)
2. Avg. Stock Rate (from Bin)
3. Stock Value (from Bin)
4. Total Purchased Qty
5. Total Sold Qty

### 2b. Customer History

- **ref_doctype:** Customer
- **File path:** `cecypo_frappe_reports/report/customer_history/`

**Filters:** Customer (req), Company (req), From Date, To Date

**Columns:**

| Fieldname | Label | Type | Width |
|-----------|-------|------|-------|
| item_code | Item Code | Link → Item | 130 |
| item_name | Item Name | Data | 200 |
| total_qty | Total Qty | Float | 90 |
| invoice_count | Invoices | Int | 70 |
| avg_rate | Avg Rate | Float | 110 |
| total_amount | Total Amount | Float | 130 |
| last_sale | Last Sale | Date | 100 |

**Data:** One row per item, sorted by total_amount DESC. Totals row appended at the bottom (bold).

**report_summary:** Total Items, Total Qty Sold, Total Revenue (base)

### 2c. Supplier History

- **ref_doctype:** Supplier
- **File path:** `cecypo_frappe_reports/report/supplier_history/`

**Filters:** Supplier (req), Company (req), From Date, To Date

**Columns:**

| Fieldname | Label | Type | Width |
|-----------|-------|------|-------|
| item_code | Item Code | Link → Item | 130 |
| item_name | Item Name | Data | 200 |
| total_qty | Total Qty | Float | 90 |
| receipt_count | Receipts | Int | 70 |
| avg_valuation_rate | Avg Valuation Rate | Float | 130 |
| total_amount | Total Amount | Float | 130 |
| last_purchase | Last Purchase | Date | 100 |

**Data:** One row per item, sorted by total_amount DESC. Totals row appended at the bottom (bold).

**report_summary:** Total Items, Total Qty Purchased, Total Spend (base)

---

## Data Sources & Queries

| Data | DocType(s) | Filter |
|------|-----------|--------|
| Item details | Item | item_code |
| Stock metrics | Bin | item_code, warehouse (optional) |
| Pending PO | Purchase Order Item + Purchase Order | item_code, company, docstatus=1, received_qty < qty |
| Pending SO | Sales Order Item + Sales Order | item_code, company, docstatus=1, delivered_qty < qty |
| Purchase history | Purchase Receipt Item + Purchase Receipt | item_code, company, supplier, docstatus=1, date range |
| Sales history | Sales Invoice Item + Sales Invoice | item_code, company, customer, docstatus=1, date range |

All queries use `frappe.qb` (PyPika). No raw SQL strings.

---

## Roles

Script Reports: `Stock Manager`, `Stock User`, `Purchase Manager`, `Purchase User`, `Sales Manager`, `Sales User`, `Accounts Manager`, `Accounts User`

Custom Page: permission check via `frappe.has_role(...)` in JS on page load; same role list.

---

## Number Formatting

All Float/Currency columns formatted with `format_number(value, null, 2)` (comma-separated, no currency symbol) per app convention. Currency shown as a separate Data column / badge.

---

## File Layout

```
cecypo_frappe_reports/report/
  item_history/
    __init__.py
    item_history.json
    item_history.py
    item_history.js
  customer_history/
    __init__.py
    customer_history.json
    customer_history.py
    customer_history.js
  supplier_history/
    __init__.py
    supplier_history.json
    supplier_history.py
    supplier_history.js

cecypo_frappe_reports/page/
  transaction_history/
    transaction_history.json
    transaction_history.js
    transaction_history.py   (whitelisted API only)
```

---

## Out of Scope

- Export to PDF/Excel (uses Frappe's built-in print for Script Reports)
- Chart views
- Opening stock calculation
- Return transactions (Credit Notes, Purchase Return)
</content>
