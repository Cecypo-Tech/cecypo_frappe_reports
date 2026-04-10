# Transaction History — New Tabs Design

**Date:** 2026-04-10
**Status:** Approved
**Scope:** Three new tabs added to the existing `transaction-history` Frappe page

---

## Background

The Transaction History page (`/app/transaction-history`) currently has three tabs:

- **Item History** — multi-item selector, stock metrics, purchases (PI+PR), sales (SI), open POs/SOs
- **Customer History** — per-item purchase summary for a customer, accordion drill-down to invoices
- **Supplier History** — per-item purchase summary for a supplier, accordion drill-down to PIs/PRs

Primary users are a mix of sales/purchase staff, management, and warehouse/operations. The three biggest gaps identified:

1. No visibility into what's actually paid vs outstanding (most critical)
2. No way to see price drift over time across customers or suppliers
3. No cross-party price comparison per item

---

## New Tabs Overview

| Tab | Default scope | Optional filter | Primary audience |
|-----|--------------|-----------------|-----------------|
| Receivables | Company-wide | Customer | Sales, management, accounts |
| Payables | Company-wide | Supplier | Purchasing, accounts |
| Pricing | Company-wide | Item(s), price list | Sales, purchasing, management |

Nav order after addition: `Item History | Customer History | Supplier History | Receivables | Payables | Pricing`

---

## Tab 1: Receivables

### Filters
- **Company** (required, Link)
- **As Of Date** (Date, defaults to today)
- **Customer** (optional, Link — scopes to single customer when set)
- **Get** button triggers load

### Default view (no customer filter) — Summary table

One row per customer with outstanding balance > 0:

| Customer | Customer Group | Total Invoiced | Total Paid | Outstanding | Current (0–30) | 31–60 | 61–90 | 90+ | Last Payment |
|----------|---------------|---------------|------------|-------------|----------------|-------|-------|-----|--------------|

- Rows with **90+ > 0** get a red row indicator pill
- Rows with **61–90 > 0** get an orange indicator
- Sortable on any column (reuses existing `_cust_state` sort pattern)
- Search input filters by customer name
- Aging buckets calculated from `due_date` vs As Of Date

**Accordion drill-down** — clicking a row expands it (same pattern as Customer/Supplier History) to show individual unpaid/partly-paid invoices:

| Date | Invoice No. | Grand Total | Paid | Outstanding | Due Date | Days Overdue | Status |

### Scoped view (customer filter set)

- Summary collapses to a single metrics card: Total Outstanding, oldest aging bucket with a value, Last Payment Date
- Invoice list renders directly (no accordion needed)

### Party action buttons

Each customer row (and the metrics card in scoped view) has three action buttons:

1. **📋 Copy text** — formats the customer name, company, as-of date, invoice list, and totals as plain text and copies to clipboard. Ready to paste into WhatsApp, email, etc.
2. **🔗 Copy link** — copies a URL in the form `/app/transaction-history?tab=receivables&customer=<name>` to clipboard. Opening the link auto-populates the customer filter and runs the query.
3. **🖨️ Print statement** — opens a new browser window with a clean print-friendly HTML statement (no Frappe chrome): party name, company, as-of date, invoice table, totals. Calls `window.print()` automatically.

The `TransactionHistoryPage` constructor reads `tab`, `customer`, and `supplier` query params after `_setup_controls()` completes, auto-fills the relevant filter controls, then triggers the appropriate load function.

### Data sources

- **Sales Invoice** (`docstatus=1`, `outstanding_amount > 0`) for invoice rows and totals
- **Payment Entry** + **Payment Entry Reference** to derive `total_paid` and `last_payment` date
- Aging bucket = `max(0, (as_of_date - due_date).days)` — assigned to 0–30, 31–60, 61–90, 90+ bucket

---

## Tab 2: Payables

Mirror of Receivables on the purchase side.

### Filters
- **Company** (required), **As Of Date** (defaults to today), **Supplier** (optional), **Get** button

### Summary table

| Supplier | Supplier Group | Total Invoiced | Total Paid | Outstanding | Current (0–30) | 31–60 | 61–90 | 90+ | Last Payment |

Same row indicators, sort, search, and accordion drill-down as Receivables.

**Drill-down columns:** Date | Invoice No. | Grand Total | Paid | Outstanding | Due Date | Days Overdue | Status

### Party action buttons

Same three actions as Receivables (copy text, copy link, print statement), adapted for supplier context.

- Copy link format: `/app/transaction-history?tab=payables&supplier=<name>`
- Print statement labelled "Supplier Statement" vs "Customer Statement"

### Data sources

- **Purchase Invoice** (`docstatus=1`, `outstanding_amount > 0`)
- **Payment Entry** + **Payment Entry Reference** for paid amounts and last payment date
- Same aging bucket logic

---

## Tab 3: Pricing

### Filters
- **Company** (required)
- **From Date / To Date** (optional date range)
- **Item selector** — reuses the existing item checklist + item group picker from Item History
- **Price List** (optional Select, populated from active selling price lists — filters the sales history table)
- **Run** button (same as Item History)

### Layout per item tab

Each selected item gets its own tab (same tab-strip pattern as Item History). Inside each tab:

#### Price List Reference panel (top)

A compact table showing current `Item Price` records for the item across all active **selling** price lists, plus buying price lists if any exist:

| Price List | Type | Rate | Currency | Valid From | Valid Upto | Edit |
|------------|------|------|----------|------------|------------|------|

**Edit** icon is visible only when `frappe.has_perm("Item Price", "write")` is true. Clicking it expands an inline edit row:

```
Suggested: 138.00  |  [ Use Last Sold Rate ]  |  Markup %: [30]  |  New Rate: [138.00]  |  [ Save ]  [ Cancel ]
```

- **Suggested rate** — computed as `avg_valuation_rate × (1 + markup/100)`. `avg_valuation_rate` is the average valuation rate from the purchase history already loaded for this item. If no purchase history is loaded (no transactions in the date range), the suggested rate field shows "N/A" and the markup % field is disabled until purchase data is available. Markup % field defaults to 30, is editable inline, recalculates the suggested rate on change.
- **"Use Last Sold Rate"** button — fills New Rate with the most recent invoiced rate for that price list from the sales table already loaded on this tab.
- **New Rate** — free-text editable; user can type any value regardless of the suggestion.
- **Save** — calls a whitelisted Python API (`update_item_price`) that upserts the `Item Price` record (`price_list_rate` field). Returns inline success/error feedback.
- **Cancel** — collapses the edit row with no changes.

#### Summary strip (below Price List Reference panel)

One line of key stats derived from the transaction history:

`Lowest purchase rate | Highest purchase rate | Avg purchase rate | Lowest sale rate | Highest sale rate | Avg sale rate`

#### History tables (below summary strip)

Two tables side by side (stack to single column on mobile, matching existing `item-results-grid` responsive class):

**Purchases** (all purchase transactions for the item in the date range):

| Date | Voucher | Supplier | Qty | UOM | Rate (txn) | Val. Rate (base) | Status |

**Sales** (all sales transactions for the item in the date range):

| Date | Voucher | Customer | Customer Group | Price List | Qty | UOM | Rate (txn) | Base Rate | Status |

- Both sorted newest-first
- Price drift is visible by scanning same-supplier or same-customer rows top to bottom
- `Customer Group` and `Price List` (from `selling_price_list` on Sales Invoice) enable instant spotting of wholesale/retail mismatches
- Optional `Price List` filter (set in the filter bar) narrows the sales table to one price list

### Data sources

- **Price List Reference:** `Item Price` DocType, filtered by `item_code` and `selling=1` or `buying=1`
- **Purchase history:** reuses `_get_purchase_rows` (already returns valuation rate)
- **Sales history:** extends `_get_sales_rows` to also select `si.selling_price_list` and `c.customer_group` via an inner join on `Customer` (aliased `c`) on `si.customer == c.name`
- **`update_item_price` API:** `@frappe.whitelist()` function — gets or creates `Item Price` by `(item_code, price_list)`, sets `price_list_rate`, calls `doc.save()`; requires `Item Price` write permission (enforced server-side too)

---

## Shared: URL param deep-linking

The `TransactionHistoryPage` constructor reads the following query params after controls are set up and auto-applies them:

| Param | Effect |
|-------|--------|
| `tab` | Activates the named tab (`receivables`, `payables`, `pricing`, `item`, `customer`, `supplier`) |
| `customer` | Pre-fills customer filter on Receivables or Customer History tab |
| `supplier` | Pre-fills supplier filter on Payables or Supplier History tab |

The **Copy Link** button constructs a URL using `window.location.origin + /app/transaction-history?tab=...&customer=...` and writes it to the clipboard.

---

## Backend changes

### New whitelisted APIs (`transaction_history.py`)

| Function | Purpose |
|----------|---------|
| `get_receivables(company, as_of_date, customer=None)` | Returns summary rows + aging buckets for Receivables tab |
| `get_receivables_detail(customer, company, as_of_date)` | Returns individual invoice rows for accordion drill-down |
| `get_payables(company, as_of_date, supplier=None)` | Returns summary rows + aging buckets for Payables tab |
| `get_payables_detail(supplier, company, as_of_date)` | Returns individual invoice rows for accordion drill-down |
| `get_item_prices(item_code)` | Returns all Item Price records for the item (selling + buying) |
| `update_item_price(item_code, price_list, rate)` | Upserts Item Price record; permission-gated server-side |

### Modified existing functions

- `_get_sales_rows` — add `si.selling_price_list` and `si.customer_group` to SELECT

---

## Frontend changes (`transaction_history.js`)

- Add `_load_receivables()`, `_render_receivables()`, `_render_receivables_detail()` methods
- Add `_load_payables()`, `_render_payables()`, `_render_payables_detail()` methods
- Add `_run_pricing()`, `_render_pricing_tab()`, `_render_price_list_panel()`, `_render_pricing_tables()` methods
- Add `_copy_party_text()`, `_copy_party_link()`, `_print_party_statement()` helpers
- `_render()` — add three new tab items to nav and three new `th-panel` divs
- `_bind_tabs()` — add click handlers for new buttons; add URL param parsing on init
- `_render_item_tabs` / `_fill_item_tab` — reused as-is for Pricing tab item switching

---

## Out of scope

- Charts / sparklines (deferred — tables are sufficient for now)
- Payment plan / scheduling from the Payables tab
- Bulk price list updates (single item at a time only)
- Email sending directly from the page (copy text covers this use case)
