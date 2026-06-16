# Item Group Valuation — Recursive Subtotals, Sortable Headers, Reusable Module

## Goal

Extend the Item Group Valuation table so every expanded level of the tree
(not just the grand total) shows its own subtotal row, every level's column
headers repeat and are clickable to sort that level's rows, and the total
row's CSS reads clearly as a footer. Build the sort/total logic as a small
reusable module rather than page-local code, since this is the second page
in the app (after Transaction History) that needs sortable-header tables.

## Background

`item_group_valuation.js` already has a grand-total `<tfoot>` (shipped,
commit `aa95c0c`). The table is a recursive tree: each `is_group` row has a
hidden `<tr class="igv-detail-row">` containing a nested `<table>` whose
`<tbody class="igv-sub-tbody">` is lazily populated by `get_group_children`
on first expand. Both `get_top_level_groups` and `get_group_children` return
**homogeneous** rows per call — a level is either all groups (`is_group: 1`,
`item_group` field) or all items (`is_group: 0`, `item_code`/`item_name`
fields), never mixed (confirmed by reading `item_group_valuation.py`).

Transaction History (`transaction_history.js`) already implements
header-click sorting three times independently (party summary,
receivables, payables), each with its own `{rows, sort_key, sort_dir}`
instance property, a `sort_icon()` helper, and a dedicated click handler.
There is no shared grid component to adopt as-is — and its storage
mechanism (named instance properties, one per fixed table) doesn't fit
Item Group Valuation, whose tables are created recursively at unbounded
depth. So instead of copying that pattern again, the generic pieces
(header markup, sort icon, comparator, total-row math, CSS) are extracted
into a shared module now, with Item Group Valuation as its first consumer.
Transaction History is **not** touched in this change — adopting the module
there is a separate, deliberate refactor to consider later.

## Decisions

- **Per-level subtotals:** every table in the tree (top-level and every
  nested one) gets its own `<tfoot>` summing its own direct rows.
- **Repeated headers:** every nested table gets its own `<thead>`,
  identical in shape to the top-level header.
- **Sortable columns:** all 4 data columns (Item Group/Item, Qty,
  Valuation Rate, Value). The leading toggle column is never sortable.
- **Sort interaction:** click toggles ascending/descending on the same
  column; clicking a different column resets to ascending. Sorting a
  table collapses any expanded group rows **within that table only**
  (sibling/parent/child tables are unaffected).
- **Collapse-on-sort re-fetch:** sorting re-renders the table's `<tbody>`
  from scratch via the existing recursive `_render_rows()`, which rebuilds
  each group row's nested `<table>` shell. This means a previously-loaded
  child table that gets collapsed by a sort **will re-fetch** on next
  expand, rather than reusing cached data. This is a deliberate
  simplification — true in-place DOM reordering (to preserve cached
  children across a sort) would need per-row keyed reattachment, adding
  real complexity for a re-fetch that's one cheap aggregate query. Flagging
  this explicitly since it relaxes the earlier "no refetch" framing.
- **Total row style:** subtle tinted background (`var(--subtle-accent,
  #eef6fb)`), bold text, top border — replacing today's inline-only
  styling, via a shared `.cecypo-total-row` CSS class.
- **Reusability:** extract the generic, data-shape-agnostic pieces (header
  cell markup, sort icon, array comparator, total-cell math, CSS) into a
  new shared file, `cecypo_frappe_reports/public/js/sortable_table.js`,
  loaded app-wide like the existing `best_fit.js` helper. State storage
  (DOM `.data()` here), click-delegation wiring, and collapse-on-sort
  behavior stay in `item_group_valuation.js` — those are page-specific and
  would be premature to generalize before a second real consumer exists.

## Implementation

### New shared module: `cecypo_frappe_reports/public/js/sortable_table.js`

Namespaced under `window.cecypo_reports.sortableTable` (matches the
existing `window.cecypo_reports.bestFit` convention in `best_fit.js`).
Column definitions passed in by the caller have this shape:

```js
{ key, label, align, width, type: "text"|"number", sortable, summable, value(row) }
```

`value(row)` is supplied by the caller — the module never assumes a field
name, so it works whether a row is a group (`item_group`) or an item
(`item_code`).

Exports:
- `sortIcon(dir)` — returns `↑`/`↓`/`↕` indicator markup for
  `dir` of `"asc"`/`"desc"`/`null`.
- `theadCellsHtml(columns, sortState)` — returns concatenated `<th>` cells
  (not the full `<tr>`, so callers can prepend page-specific columns like
  a toggle cell). Adds `class="cecypo-sort-header" data-sort-key="<key>"`
  for sortable columns and the current sort icon.
- `sortRows(rows, column, dir)` — returns a **new** sorted array (never
  mutates input) using `column.value(row)` and `column.type` to compare.
- `totalCellsHtml(columns, rows, opts)` — returns concatenated `<td>`
  cells. For the column matching `opts.labelKey`, renders `opts.label`
  instead of a sum. For other `summable` columns, sums `column.value(row)`
  across `rows` and formats via `opts.format(total, column)`. Non-summable
  columns render `—`.
- Internal `injectStyleOnce()` — lazily appends one `<style>` block (guarded
  by a module-level flag) defining `.cecypo-sort-header` and
  `.cecypo-total-row`, called from `theadCellsHtml`/`totalCellsHtml` so any
  consumer gets consistent styling for free.

Registered in `hooks.py` by changing `app_include_js` from a single string
to a list:

```python
app_include_js = [
	"/assets/cecypo_frappe_reports/js/best_fit.js",
	"/assets/cecypo_frappe_reports/js/sortable_table.js",
]
```

### `item_group_valuation.js` changes

**Column defs** (module-scope constant, the 4 sortable columns — the
toggle column stays page-specific):

```js
const IGV_COLUMNS = [
	{ key: "name", label: __("Item Group / Item"), align: "left", type: "text", sortable: true,
	  value: (row) => (row.is_group ? row.item_group : row.item_code) },
	{ key: "qty", label: __("Qty"), align: "right", width: 90, type: "number", sortable: true, summable: true,
	  value: (row) => row.qty },
	{ key: "valuation_rate", label: __("Valuation Rate"), align: "right", width: 130, type: "number", sortable: true,
	  value: (row) => row.valuation_rate },
	{ key: "value", label: __("Value"), align: "right", width: 130, type: "number", sortable: true, summable: true,
	  value: (row) => row.value },
];
```

**`_thead_row_html(sort_state)`** — new method, replaces the hardcoded
`<tr>` in `_table_shell_html`. Prepends the toggle `<th>`, then calls
`cecypo_reports.sortableTable.theadCellsHtml(IGV_COLUMNS, sort_state)`.
Used for the top-level `<thead>` and every nested table's `<thead>`.

**`_render_total_row(rows, $tfoot)`** — signature unchanged from the
shipped version. Internally now calls
`sortableTable.totalCellsHtml(IGV_COLUMNS, rows, { format: (v) => this._fmt_num(v), labelKey: "name", label: __("Total") })`
and wraps the result: `` `<tr class="cecypo-total-row"><td></td>${cells}</tr>` ``.
Reused for both the grand total and every per-level subtotal — it doesn't
care about indent or nesting depth.

**Nested table markup** (inside `_render_rows`, for `is_group` rows) gains
a `<thead>` and a `<tfoot class="igv-sub-tfoot">`:

```html
<table style="width:100%;border-collapse:collapse;font-size:13px">
	<thead>${this._thead_row_html(null)}</thead>
	<tbody class="igv-sub-tbody" data-for="${esc}" data-indent="${indent + 1}"></tbody>
	<tfoot class="igv-sub-tfoot"></tfoot>
</table>
```

**State storage** — both `#igv-tbody` (in `refresh()`) and every
`.igv-sub-tbody` (in the expand click handler, after `get_group_children`
resolves) call `.data("rows", rows)` with the original unsorted array, and
`.data("sort", { key: null, dir: null })`. This is the canonical source for
re-sorting and is never itself mutated.

**Subtotal wiring on expand** — the existing expand click handler in
`_bind_events` already fetches `get_group_children` and calls
`_render_rows(rows, $sub, indent + 1)`. It now also locates that table's
`<tfoot class="igv-sub-tfoot">` and calls
`this._render_total_row(rows, $tfoot)`.

**New delegated sort handler** in `_bind_events`:

```js
$(this.page.main).on("click", ".cecypo-sort-header", (e) => {
	const $th = $(e.currentTarget);
	const key = $th.data("sortKey");
	const $table = $th.closest("table");
	const $tbody = $table.children("tbody");
	const $tfoot = $table.children("tfoot");
	const rows = $tbody.data("rows");
	if (!rows) return;
	const indent = parseInt($tbody.data("indent") || 0, 10);

	const prev = $tbody.data("sort") || { key: null, dir: null };
	const dir = prev.key === key && prev.dir === "asc" ? "desc" : "asc";

	$tbody.children(".igv-group-row").each((_, el) => {
		const $row = $(el);
		const $detail = $row.next(".igv-detail-row");
		if (!$detail.hasClass("hidden")) {
			$detail.addClass("hidden");
			$row.find("td:first").text("▶");
		}
	});

	const column = IGV_COLUMNS.find((c) => c.key === key);
	const sorted = window.cecypo_reports.sortableTable.sortRows(rows, column, dir);

	$tbody.empty();
	this._render_rows(sorted, $tbody, indent);
	$tbody.data("sort", { key, dir });
	$table.children("thead").html(this._thead_row_html({ key, dir }));
	this._render_total_row(rows, $tfoot);
});
```

Sorting only ever touches the clicked table's own `<thead>`/`<tbody>`/
`<tfoot>` — sibling and ancestor tables' sort state and expand state are
untouched, since each lives in its own DOM subtree with its own `.data()`.

## Out of Scope

- No changes to `transaction_history.js` or any other page.
- No backend/Python changes — `get_top_level_groups`/`get_group_children`
  are unchanged.
- No attempt to preserve loaded child data across a sort (see Decisions —
  re-expand after a sort re-fetches).
- No generalized "bind click delegation" helper in the shared module —
  state storage and event wiring stay page-specific until a second real
  consumer exists.

## Testing

Pure frontend change — no Python touched, no changes to
`test_item_group_valuation.py`. Verify manually after `bench build --app
cecypo_frappe_reports`:

1. Every expanded group shows its own header row and its own subtotal
   footer; the grand total at the very bottom is unaffected by expansion.
2. Each subtotal matches the sum of qty/value of that level's direct rows.
3. Clicking each of the 4 sortable headers (Item Group/Item, Qty,
   Valuation Rate, Value) at the top level reorders the top-level rows;
   clicking again reverses order; icon shows ↕ → ↑ → ↓ correctly.
4. Repeat sorting inside an expanded nested table — only that table
   reorders; its parent/sibling tables are untouched.
5. Expand a group, then sort its parent table — the expanded group
   collapses. Re-expanding it re-fetches (a brief "Loading..." is
   expected) rather than instantly showing stale cached rows.
6. Total row renders with the tinted background style, distinguishable
   from header and data rows, at every level.
7. Filter/refresh still works end-to-end (regression check against the
   already-shipped grand-total feature).
