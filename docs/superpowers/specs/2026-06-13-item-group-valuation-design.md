# Item Group Valuation Enhanced — Design Spec

**Date:** 2026-06-13
**Type:** Custom Page

## Overview

A custom Frappe page that shows inventory valuation aggregated by item group, with an interactive drill-down accordion. Clicking a group row expands to reveal its direct child groups; clicking a leaf group expands to reveal individual items. Values are sourced directly from the `bin` table (`actual_qty`, `valuation_rate`, `stock_value`).

## File Structure

```
cecypo_frappe_reports/page/item_group_valuation/
├── __init__.py
├── item_group_valuation.json
├── item_group_valuation.py
└── item_group_valuation.js
```

## Data Model

All aggregation is done via the `tabItem Group` nested set (`lft`/`rgt`) joined to `tabItem` and `tabBin`.

| Column | Source | Notes |
|--------|--------|-------|
| Item Group / Item | `tabItem Group.name` or `tabItem.item_code` | |
| Qty | `SUM(tabBin.actual_qty)` | Aggregated across all descendants |
| Valuation Rate | `SUM(stock_value) / SUM(actual_qty)` | Weighted average; `—` when qty is 0 |
| Value | `SUM(tabBin.stock_value)` | Aggregated across all descendants |

## Backend (`item_group_valuation.py`)

### `get_top_level_groups(root_group, warehouse, company)`
- Returns direct children of `root_group` (default `"All Item Groups"`)
- Each row aggregates all descendant items using the nested set `lft`/`rgt` range
- Filtered by `warehouse` and `company` when provided

### `get_group_children(item_group, warehouse, company)`
- Called on demand when user clicks `▶`
- If `item_group` has child groups (`is_group=1` children in `tabItem Group`): returns one aggregated row per child group
- If leaf group (no child groups): returns one row per item from `tabBin` joined to `tabItem`
- Returns `is_group` flag on each row so JS knows the row type

Both methods are decorated with `@frappe.whitelist()` and use `frappe.qb` (no raw SQL).

## Filters

Rendered as a toolbar on the page (not Frappe report filters):

| Filter | Type | Required | Default |
|--------|------|----------|---------|
| Company | Link → Company | Yes | User default company |
| Warehouse | Link → Warehouse | No | — |
| Root Group | Link → Item Group | No | `"All Item Groups"` |

A **Refresh** button triggers `page.refresh()`.

## Frontend (`item_group_valuation.js`)

### Page Layout

```
┌─────────────────────────────────────────────────────────┐
│  [Company ▾] [Warehouse ▾] [Root Group ▾]  [Refresh]   │
├──────────────────────────────────────────────────────────┤
│   Item Group          Qty      Val. Rate      Value      │
│ ▶ Electronics       1,200      4,500.00   5,400,000.00  │
│ ▶ Raw Materials       800      1,200.00     960,000.00  │
│   ▼ Electronics                                          │
│     ▶ Laptops         400      8,000.00   3,200,000.00  │
│       ▼ Laptops                                          │
│         Dell XPS       50     85,000.00   4,250,000.00  │
└──────────────────────────────────────────────────────────┘
```

### JS Class Methods

| Method | Purpose |
|--------|---------|
| `setup()` | Render filter toolbar and empty table shell |
| `refresh()` | Call `get_top_level_groups`, render top-level rows |
| `_render_rows(rows, $tbody, indent)` | Shared renderer for both group and item rows |
| `_bind_events()` | Single delegated click handler on table for all `▶` rows |

### Interaction Rules

- `▶` on group rows — clickable, toggles to `▼`, child rows inserted below
- Expanded children are cached (no re-fetch on collapse/re-expand)
- Leaf item rows are indented, not clickable (no arrow), link to item in new tab
- Numbers formatted with `format_number(value, null, 2)` — no currency symbol

## Roles

System Manager and Stock Manager (mirroring existing report access patterns).
