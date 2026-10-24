# Transaction History — Item Picker Dialog, Stock Card View, Cost Gating

## Intent

The Items tab of the Transaction History page (`cecypo_frappe_reports/page/transaction_history/`)
is hard to use with more than a handful of items:

- Each checked item becomes its own Bootstrap tab in the results strip, so twenty items means
  twenty tabs.
- Items are picked in a 224px sidebar that shows only a truncated item name. Similar items
  (e.g. `AP064`, `AP064-FF`, `AP064-UP`) cannot be told apart, and there is no stock or price
  to help decide.
- Choosing a parent Item Group adds nothing, because the group filter is an exact match on
  `item_group` and parent groups hold no items directly.
- Nothing on the tab is permission-gated. Valuation rate, stock value and the warehouse
  breakdown popover are shown to anyone who can open the page. That is a cost leak for users
  like counter staff who are deliberately kept off the Stock Ledger.

The business also wants a **Stock Card** for an item: the running +/- ledger of quantities,
with cost hidden for users who may not see it, as their previous POS provided.

## Goals

1. Pick items in a large table with search, group filter, stock and price columns, and
   checkboxes; accumulate a selection across several searches; confirm once.
2. Replace per-item result tabs with a selector that scales to 50+ items.
3. Add a Stock Card view (ledger of qty in / qty out / running balance) switchable from the
   same results area, with a direct path from a warehouse stock figure to that warehouse's card.
4. Gate cost everywhere on the Items tab by one rule: the user may see cost iff they have
   `read` on **Stock Ledger Entry**. Restrict warehouses by Frappe User Permissions on Warehouse.
5. Fix the parent Item Group bug.

## Non-goals

- Customer, Receivables, Payables tabs: untouched.
- Supplier tab: UI untouched, but `get_supplier_history` (`avg_valuation_rate`) and
  `get_supplier_item_transactions` (`valuation_rate`) drop those keys when `_can_see_cost()` is
  false, and the two renderers hide the column when the key is absent. Same helper, a few lines;
  leaving it would keep the exact leak this design exists to close.
- The Pricing tab keeps its own picker. It **does** inherit cost gating because it calls the
  same `get_item_history` endpoint (see Decisions).
- No change to the standard ERPNext Stock Ledger report.
- No "all selected items in one stock card" grid. One item at a time. Add when asked.
- No editing, exporting or printing of the stock card.

## Anti-goals

- Hiding cost only in the browser. Cost fields must never leave the server for a user who may
  not see them.
- Surprising RISHIT-type users with a permission prompt. A user without Stock Ledger Entry
  read must still get the full qty ledger; only cost columns disappear.
- Replacing the History view. Purchases / Open POs / Sales / Open SOs stay as they are and
  remain the default.

## Constraints

- Frappe v15+ desk page, jQuery + Frappe controls, no new npm dependencies.
- Existing style: inline styles in template strings, `frappe.call` to whitelisted functions in
  `transaction_history.py`, `frappe.qb` for SQL.
- Page JS is served by `frappe.desk.desk_page.getpage`, not `/assets`, so no cache-busting
  include is needed.
- Tests live in `page/transaction_history/test_transaction_history.py` and run with
  `bench --site dev.localhost run-tests --module ...`.

## Permission model (decided)

Two server-side helpers, used by every endpoint on the Items tab:

- `_can_see_cost()` → `frappe.has_permission("Stock Ledger Entry", "read")`.
  Administrator always true (Frappe already returns true for Administrator).
- `_permitted_warehouses(company)` → `frappe.get_list("Warehouse", filters={"company": company,
  "is_group": 0, "disabled": 0}, pluck="name")`. `get_list` applies User Permissions, so a user
  restricted to KIRINYAGA gets only KIRINYAGA. A user with no Warehouse restriction gets all.

Rules:

| Data | Visible when |
|------|--------------|
| valuation rate, avg rate, stock value, incoming/outgoing rate, stock value difference, purchase "Val. Rate", Stock Entry / Stock Reconciliation rate | `_can_see_cost()` |
| Sell price (Item Price, selling), sales rate on invoices/delivery notes | always |
| Qty in / out / balance, voucher, date, party | always |
| Warehouse rows and columns | only warehouses in `_permitted_warehouses()` |

Warehouse scoping applies to **every** query on the Items tab, not just stock figures:
`_get_stock_metrics`, `_get_purchase_rows`, `_get_sales_rows`, `_get_open_purchase_orders`,
`_get_open_sales_orders`, `get_warehouse_stock`, `search_items`, `get_stock_card`. A
caller-supplied `warehouse` argument that is not in the permitted set is treated as "no rows"
(never silently widened). Otherwise a KIRINYAGA-only user would see KIRINYAGA stock but
company-wide purchases and sales.

Every number the server returns is already filtered. Gated keys are omitted from the dict,
not sent as zero, so the client can decide column visibility from presence of the key and a
`can_see_cost` flag returned alongside.

Rationale for using Stock Ledger Entry read as the switch: the standard Stock Ledger report
ignores field permission levels, so in practice "may read Stock Ledger Entry" already means
"may see cost" in this business. This design formalises that.

## UI design

### Items tab layout (after)

```
[Company] [From] [To] [Warehouse]   [ Select items… ]        View: ( History | Stock Card )
Selected: [KD2605 ×] [AP064 ×] [KY24044 ×]  (chips; click chip = view that item)
Item: [ KD2605: ASIMCO Hiace 5L/7L Front-AP064  ▾ ]  ‹ ›      [Filter rows…]
───────────────────────────────────────────────────────────────────────────────
  (History view: metrics grid + Purchases | Sales | Open PO | Open SO, unchanged)
  (Stock Card view: ledger grid, below)
```

- The sidebar, its Item Group / Add Item controls, the "Add all filtered" awesomplete footer
  hack and the per-item tab strip are removed.
- **Item selector**: a Frappe `Select` control listing selected items as
  `code: name`, plus prev/next buttons. Changing it swaps the visible panel; data for all
  selected items is still fetched in parallel on confirm, as today.
- **View switch**: two-button toggle (History default). Switching re-renders the current item
  only; Stock Card data is fetched lazily per item the first time it is viewed and cached for
  the run. Changing any top filter invalidates the cache and reruns.
- Chips: removing a chip removes the item from the run (no refetch of others). Reopening the
  picker shows current selection pre-ticked.

### Picker dialog

`frappe.ui.Dialog` with `size: "extra-large"`, title "Select Items".

Header row:

- Search (`Data`), debounced 300 ms, min 2 chars or a group chosen. Uses the existing
  `cecypo_frappe_reports.api.item_query` (multi-token AND, `%` wildcard, barcode).
- Item Group (`Link`). Filtering uses the group **and all its descendants**.
- "In stock only" is **not** included (YAGNI).

Table (rendered HTML, not DataTable; rows ≤ 100):

| ☐ | Item Code | Item Name | Group | UOM | Sell Price | ‹warehouse columns› | Cost |

- Sell Price: `Item Price.price_list_rate` for the price list in
  `Selling Settings.selling_price_list`, valid today. Blank if none. (Verified on the customer
  site: that setting is "Cash Price", which is also its most complete selling list.)
- Warehouse columns: one per warehouse in `_permitted_warehouses()` that has `actual_qty ≠ 0`
  for at least one row in the current result set, ordered by total qty desc. If that set is
  larger than **6**, collapse to a single `Stock` column (total) whose cell opens the existing
  warehouse popover (`_show_warehouse_popover`), itself filtered to permitted warehouses.
  (dev.localhost has 117 warehouses; the customer site has 3.)
- Cost: `stock_value / actual_qty` across permitted warehouses, 2 dp. Column absent entirely when
  `can_see_cost` is false.
- Clicking a warehouse qty cell (or the total `Stock` cell) **selects that item, closes the
  dialog, runs, and opens the Stock Card view for that item with the top Warehouse filter set
  to that warehouse** (or left as-is for the total cell). This is the "click 285 → KIRINYAGA
  card" path.
- Header checkbox ticks/unticks all rows currently shown.
- Selection persists across searches inside one dialog session; footer shows
  `Use selected (n)` (primary) and `Clear`.
- Result cap: 100 rows; a footer note says "Showing first 100 — refine your search" when hit.

One new whitelisted endpoint backs the table:

```
search_items(company, txt="", item_group=None, limit=100)
  -> {"can_see_cost": bool, "warehouses": [...names shown...], "items": [
       {"item_code", "item_name", "item_group", "stock_uom", "sell_price",
        "stock": {"<warehouse>": qty, ...}, "total_qty", "cost"?}
     ]}
```

It reuses `item_query` for the candidate list, then one `Bin` query for the codes.

### Stock Card view

One new whitelisted endpoint:

```
get_stock_card(item, company, from_date=None, to_date=None, warehouse=None)
  -> {"can_see_cost": bool, "opening_qty", "rows": [...], "closing_qty",
      "totals": {"qty_in", "qty_out"}, "truncated": bool}
```

Source: `Stock Ledger Entry` where `is_cancelled = 0`, `docstatus < 2`, `item_code`, `company`,
`warehouse IN permitted` (and `= warehouse` if given), `posting_date` within range. Ordered by
`posting_datetime, creation`. Hard cap 5000 rows ascending (`truncated: true` beyond that; the
client shows a warning banner because footer totals and closing balance are then incomplete).
The busiest item on the customer site has 287 ledger rows in total, so the cap is a safety
net, not a paging scheme. Do not build newest-first windows.

Row shape:

| Column | Source | Gated |
|--------|--------|-------|
| Date | `posting_date` + `posting_time` | no |
| Voucher Type / No | `voucher_type`, `voucher_no` (link) | no |
| Party | `customer`/`supplier` (or `customer_name`/`supplier_name`) from the voucher parent for SI, DN, PI, PR, POS Invoice, Sales Invoice returns; blank for Stock Entry / Stock Reconciliation / others | no |
| Warehouse | `warehouse` | row-filtered by permission; column hidden if only one permitted warehouse **or** a single warehouse filter is active |
| Rate | sale/purchase transaction rate from the voucher child row via `voucher_detail_no` (`base_rate` on SI/DN/PI/PR/POS Invoice items). For Stock Entry / Stock Reconciliation / Material Receipt etc. the only rate is a cost, so Rate is **blank** for those rows unless `can_see_cost`, in which case it shows `incoming_rate` (in) / `outgoing_rate` (out) | partially |
| Qty In | `actual_qty` if > 0 | no |
| Qty Out | `-actual_qty` if < 0 | no |
| Balance | see below | no |
| Cost Rate | `valuation_rate` | yes |
| Value Change | `stock_value_difference` | yes |
| Stock Value | `stock_value` (single warehouse) / running sum of `stock_value_difference` + opening value (multi) | yes |

Balance (corrected 2026-10-24: Stock Reconciliation ledger rows store `actual_qty = 0` and
only set `qty_after_transaction`, so summing `actual_qty` silently drops every reconciliation):

- Track the latest `qty_after_transaction` (and `stock_value`) **per warehouse** in scope.
- Opening per warehouse = `qty_after_transaction` / `stock_value` of that warehouse's last ledger
  row before `from_date` (0 when none, or when no `from_date`). `opening_qty` / `opening_value`
  are the sums over the scope.
- Each row's qty in/out = that row's `qty_after_transaction` minus the warehouse's previous
  running figure (equals `actual_qty` for ordinary vouchers; gives the true adjustment for a
  Stock Reconciliation). Balance after the row = sum of per-warehouse running figures. Value
  likewise from `stock_value`.
- With a single warehouse in scope this reduces to the stored `qty_after_transaction`.
- Rate on a Stock Reconciliation row, for a cost-visible user, is `valuation_rate`.
- An **Opening** pseudo-row is shown first whenever `from_date` is set, with the opening qty
  (and opening value if cost visible).

Footer: totals for Qty In, Qty Out, closing Balance; cost totals only when visible.

Rendering: plain HTML table in the same visual style as the History panels, rows numbered,
negative qty in red, running balance bold. The existing "Filter rows…" search box applies.

### Mobile (added 2026-10-24 at the user's request)

The redesign must be usable on a phone (tested at 390×844). The page already has a
`@media (max-width: 767px)` block in `_inject_styles`; new rules go there.

- **Picker dialog:** Frappe already renders an extra-large dialog full-screen below 768px.
  Inside it, the search box and the Item Group filter stack full width. The table sits in an
  `overflow-x:auto` wrapper so it scrolls sideways without scrolling the page; the checkbox
  and Item Code columns are `position: sticky; left: 0` so the user always sees what they are
  ticking. Below 768px the per-warehouse columns are always collapsed into the single
  `Stock` column (the ≤6 rule applies only on desktop) and the Group column is hidden. The
  footer buttons stay reachable without horizontal scrolling.
- **Results header:** filter bar, view switch, chips and the item selector wrap onto their own
  rows; the selector takes the full width.
- **History view:** the existing one-column collapse for the metrics grid and the four
  panels is kept.
- **Stock Card:** the table sits in an `overflow-x:auto` wrapper; Date and Voucher columns are
  sticky-left; the running Balance column is the right-most non-cost column so it is the first
  thing visible after scrolling. No whole-page horizontal scroll at 390px.
- Tap targets (chips' ×, prev/next, view switch) are at least 32px tall on mobile.

## Changes to existing endpoints

- `get_item_history`: apply `_can_see_cost()` — drop `avg_rate`, `stock_value` from
  `stock_metrics` and `valuation_rate` from `purchases` rows when false; return
  `can_see_cost`. Limit `_get_stock_metrics` Bin sum to permitted warehouses (today it has no
  company filter at all, so this also fixes a cross-company bug). Client hides the
  corresponding cells/columns when the key is absent. The Pricing tab consumes the same
  payload and therefore stops showing valuation to gated users; its averaging code must treat a
  missing `valuation_rate` as "no data", not 0.
- `get_warehouse_stock`: filter by `_permitted_warehouses(company)`. (Currently it filters
  `actual_qty > 0`; keep that.)
- Item Group filter bug: `search_items` passes
  `item_group: ["in", frappe.get_descendants("Item Group", group) + [group]]` to `item_query`.
  `item_query` already handles list-valued filters through `get_filters_cond`; no change there.
  (The dict form of `"descendants of (inclusive)"` is not supported by that helper.)

## Removed

- Sidebar markup and the `_render_item_checklist`, `_add_item_to_panel` (Items tab only; the
  Pricing tab keeps its own copies), item group / add item controls, "Add all filtered" hooks,
  `_render_item_tabs` tab strip. `_fill_item_tab` / `_render_item_history` stay.

## Testing

Add to `test_transaction_history.py`:

- `search_items` with a parent group returns items from child groups.
- `search_items` / `get_stock_card` / `get_item_history` as a user without Stock Ledger Entry
  read: no `cost`, `valuation_rate`, `avg_rate`, `stock_value`, `stock_value_difference`
  keys anywhere in the payload; `can_see_cost` false. As a user with it: present.
- `get_stock_card` running balance across two warehouses equals Bin totals at the end of the
  range; opening row present when `from_date` is set; single-warehouse balance equals
  `qty_after_transaction`.
- `get_stock_card` **and** `get_item_history` purchases/sales with a User Permission on
  Warehouse return only that warehouse's rows; an explicit non-permitted `warehouse` arg
  returns no rows.
- `get_supplier_history` as a gated user has no `avg_valuation_rate`.
- Stock Entry row: `rate` blank for gated user, equal to `incoming_rate` for cost user.

Manual: on dev.localhost as Administrator and as a test user with Stock Ledger Entry read
removed, pick items by parent group, click a warehouse qty, confirm card opens for that
warehouse with no cost columns.

## Left to the builder

- Exact debounce, column widths, chip styling, empty states.
- Whether the Stock Card fetch happens on confirm (eager) or first view (lazy); lazy is the
  suggestion above.
- How prev/next and the Select control are wired.
- Whether `search_items` reuses `item_query` internally or duplicates its tokenised LIKE
  logic; reuse is preferred.

## Open calls made by the author (flag if wrong)

1. Cost switch = Stock Ledger Entry read (agreed with user).
2. Warehouse column collapse threshold = 6.
3. Rate on Stock Entry / Reconciliation rows is treated as cost.
4. Sell price comes from `Selling Settings.selling_price_list` only.
5. Pricing tab inherits gating via the shared endpoint; its UI is otherwise untouched.
6. Opening row shown only when `from_date` is set.
7. Warehouse User Permissions scope every query on the Items tab, including purchases, sales
   and open orders, not just stock figures.
8. Supplier tab valuation columns are gated too (server drops the keys, renderer hides the
   column). No other Supplier tab change.
