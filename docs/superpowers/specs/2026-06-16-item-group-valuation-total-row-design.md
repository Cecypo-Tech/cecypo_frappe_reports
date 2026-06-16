# Item Group Valuation — Bottom Total Row

## Goal

Add a totals row at the bottom of the Item Group Valuation custom page table, summarizing Qty and Value across all top-level item groups currently shown.

## Background

`item_group_valuation.js` renders a hierarchical table. `refresh()` calls the
`get_top_level_groups` backend method, which returns one row per direct child
of the selected root Item Group. Each row's `qty`/`value` already aggregates
everything beneath it in the nested-set hierarchy (via `_aggregate_for_group`
in `item_group_valuation.py`), so the top-level rows fully partition the
selected subtree with no overlap.

Expanding a group lazily loads its children into a nested `<tbody>` via
`get_group_children`. Those child rows are *additional* DOM rows representing
data already counted in the parent's totals — so a correct grand total must
sum only the top-level rows, never all currently-visible rows.

## Decisions

- **Total row shows:** summed Qty and summed Value (user choice).
- **Valuation Rate cell:** left blank (`—`) — an average rate across
  dissimilar item groups is not meaningful.
- **Computation:** client-side, in `refresh()`, by summing the `qty` and
  `value` fields of the array returned from `get_top_level_groups`. No new
  backend method or query is needed — the top-level rows already contain
  everything required.

## Implementation

### Markup (`_table_shell_html`)

Add a `<tfoot id="igv-tfoot">` section to the table, separate from
`#igv-tbody`. Using `tfoot` keeps the totals row visually pinned below the
body and structurally untouched by the expand/collapse logic, which only
ever targets `tbody` elements (`#igv-tbody` and `.igv-sub-tbody`).

Initial state: empty (no totals row) until the first successful refresh.

### Behavior (`refresh`)

- On "Loading...": clear `#igv-tfoot` (no stale total during fetch).
- On "No data found": clear `#igv-tfoot`.
- On success: compute `qty_total = sum(rows[].qty)` and
  `value_total = sum(rows[].value)`, then render one `<tr>` into
  `#igv-tfoot`:
  - Col 1 (toggle): blank
  - Col 2 (label): `Total`
  - Col 3 (Qty): `_fmt_num(qty_total)`
  - Col 4 (Valuation Rate): `—`
  - Col 5 (Value): `_fmt_num(value_total)`, bold

Styling matches the existing header row (bold text, top border) to read as
a footer rather than a data row.

## Out of Scope

- No backend/Python changes.
- No change to per-row drill-down behavior.
- No persistence of the total across page filter changes beyond what
  `refresh()` already does (it recomputes on every refresh).

## Testing

Pure frontend change — no Python touched, so no changes to
`test_item_group_valuation.py`. Verify manually:

1. `bench build --app cecypo_frappe_reports`
2. Open the Item Group Valuation page, select a Company, click Refresh.
3. Confirm the footer row's Qty/Value sums match the sum of the visible
   top-level rows.
4. Expand a group; confirm the footer total is unchanged (no double count).
5. Change filters and refresh again; confirm the footer updates accordingly.
6. Select filters that produce no data; confirm the footer is empty/cleared.
