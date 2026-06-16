# Item Group Valuation — Recursive Subtotals, Sortable Headers, Reusable Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every expanded level of the Item Group Valuation tree gets its own subtotal row and its own clickable sortable header row, and the total-row CSS reads clearly as a footer. The generic sort/total logic is extracted into a new shared module so it isn't hand-rolled page-local code.

**Architecture:** New shared file `cecypo_frappe_reports/public/js/sortable_table.js` (loaded app-wide via `hooks.py`, namespaced `window.cecypo_reports.sortableTable`) holds data-shape-agnostic helpers: sort icon markup, sortable `<th>` cell markup, an array sort function, and total `<td>` cell markup with CSS injected once. `item_group_valuation.js` consumes these helpers, owns its own column definitions (with `value(row)` accessors), and keeps all DOM-state storage (`.data("rows"/"sort")` on each `<tbody>`), click-delegation wiring, and collapse-on-sort behavior page-local.

**Tech Stack:** Frappe custom page (vanilla JS + jQuery), existing `format_number` helper via `_fmt_num()`.

**Spec:** `docs/superpowers/specs/2026-06-16-item-group-valuation-recursive-totals-sortable-headers-design.md`

---

### Task 1: Create the shared `sortable_table.js` module

**Files:**
- Create: `cecypo_frappe_reports/public/js/sortable_table.js`

- [ ] **Step 1: Write the module**

```javascript
// Shared sortable-table helpers for cecypo_frappe_reports custom pages.
// Generic and data-shape-agnostic: callers supply column defs with their
// own value(row) accessors, so this module never assumes field names.
//
// Column shape: { key, label, align, width, type: "text"|"number",
//                  sortable, summable, value(row) }

window.cecypo_reports = window.cecypo_reports || {};

window.cecypo_reports.sortableTable = (function () {
	let style_injected = false;

	function inject_style_once() {
		if (style_injected) return;
		style_injected = true;
		$("<style>")
			.text(
				".cecypo-sort-header { cursor: pointer; user-select: none; }\n" +
					".cecypo-sort-header .sort-indicator { color: var(--text-muted); margin-left: 4px; font-size: 11px; }\n" +
					".cecypo-total-row td { background: var(--subtle-accent, #eef6fb); font-weight: 600; border-top: 2px solid var(--border-color); padding: 8px 12px; }"
			)
			.appendTo("head");
	}

	function sort_icon(dir) {
		if (dir === "asc") return '<span class="sort-indicator">↑</span>';
		if (dir === "desc") return '<span class="sort-indicator">↓</span>';
		return '<span class="sort-indicator">↕</span>';
	}

	function thead_cells_html(columns, sort_state) {
		inject_style_once();
		return columns
			.map((col) => {
				const align = col.align || "left";
				const width_style = col.width ? `width:${col.width}px;` : "";
				const base_style = `padding:8px 12px;${width_style}text-align:${align};border-bottom:2px solid var(--border-color)`;
				if (!col.sortable) {
					return `<th style="${base_style}">${col.label}</th>`;
				}
				const active = sort_state && sort_state.key === col.key;
				const dir = active ? sort_state.dir : null;
				return `<th class="cecypo-sort-header" data-sort-key="${col.key}" style="${base_style}">${col.label}${sort_icon(dir)}</th>`;
			})
			.join("");
	}

	function column_value(col, row) {
		return typeof col.value === "function" ? col.value(row) : row[col.key];
	}

	function sort_rows(rows, column, dir) {
		const sorted = rows.slice();
		const mul = dir === "desc" ? -1 : 1;
		sorted.sort((a, b) => {
			const av = column_value(column, a);
			const bv = column_value(column, b);
			if (column.type === "number") {
				return ((av || 0) - (bv || 0)) * mul;
			}
			return String(av || "").localeCompare(String(bv || "")) * mul;
		});
		return sorted;
	}

	function total_cells_html(columns, rows, opts) {
		inject_style_once();
		opts = opts || {};
		const format = opts.format || ((v) => v);
		return columns
			.map((col) => {
				const align = col.align || "left";
				if (opts.labelKey && col.key === opts.labelKey) {
					return `<td style="text-align:${align}">${opts.label || ""}</td>`;
				}
				if (!col.summable) {
					return `<td style="text-align:${align}">—</td>`;
				}
				const total = rows.reduce((sum, row) => sum + (Number(column_value(col, row)) || 0), 0);
				return `<td style="text-align:${align}">${format(total, col)}</td>`;
			})
			.join("");
	}

	return {
		sortIcon: sort_icon,
		theadCellsHtml: thead_cells_html,
		sortRows: sort_rows,
		totalCellsHtml: total_cells_html,
	};
})();
```

- [ ] **Step 2: Syntax check**

Run: `node --check cecypo_frappe_reports/public/js/sortable_table.js`
Expected: no syntax errors (command exits 0, no output). Note: this file
uses the `$`/`window` globals so `node --check` validates syntax only, not
execution — that's all we need here.

- [ ] **Step 3: Commit**

```bash
git add cecypo_frappe_reports/public/js/sortable_table.js
git commit -m "feat: add reusable sortable_table.js helper module"
```

---

### Task 2: Register the module in `hooks.py`

**Files:**
- Modify: `cecypo_frappe_reports/hooks.py:29`

- [ ] **Step 1: Change `app_include_js` from a string to a list**

Find:
```python
app_include_js = "/assets/cecypo_frappe_reports/js/best_fit.js"
```

Replace with:
```python
app_include_js = [
	"/assets/cecypo_frappe_reports/js/best_fit.js",
	"/assets/cecypo_frappe_reports/js/sortable_table.js",
]
```

- [ ] **Step 2: Commit**

```bash
git add cecypo_frappe_reports/hooks.py
git commit -m "feat: load sortable_table.js app-wide"
```

---

### Task 3: Wire `item_group_valuation.js`'s top-level table to the shared module

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.js`

This task makes the top-level table use the shared module for its header
and total row, with **no visible behavior change yet** (sort clicks won't
do anything until Task 5) — it's a regression-safe checkpoint.

- [ ] **Step 1: Add `IGV_COLUMNS` above the class definition**

Insert immediately after the `frappe.pages["item-group-valuation"].on_page_load = ...;` block (before `class ItemGroupValuationPage {`):

```javascript
const IGV_COLUMNS = [
	{
		key: "name",
		label: __("Item Group / Item"),
		align: "left",
		type: "text",
		sortable: true,
		value: (row) => (row.is_group ? row.item_group : row.item_code),
	},
	{
		key: "qty",
		label: __("Qty"),
		align: "right",
		width: 90,
		type: "number",
		sortable: true,
		summable: true,
		value: (row) => row.qty,
	},
	{
		key: "valuation_rate",
		label: __("Valuation Rate"),
		align: "right",
		width: 130,
		type: "number",
		sortable: true,
		value: (row) => row.valuation_rate,
	},
	{
		key: "value",
		label: __("Value"),
		align: "right",
		width: 130,
		type: "number",
		sortable: true,
		summable: true,
		value: (row) => row.value,
	},
];
```

- [ ] **Step 2: Add `_thead_row_html(sort_state)` method**

Add directly after `setup()` (before `_table_shell_html()`):

```javascript
	_thead_row_html(sort_state) {
		const ST = window.cecypo_reports.sortableTable;
		return `<tr style="background:var(--subtle-fg,#f4f5f6)">
			<th style="padding:8px 12px;width:32px;border-bottom:2px solid var(--border-color)"></th>
			${ST.theadCellsHtml(IGV_COLUMNS, sort_state)}
		</tr>`;
	}
```

- [ ] **Step 3: Replace `_table_shell_html()` to use the new header method**

Replace:
```javascript
	_table_shell_html() {
		return `<div style="padding:16px;max-width:860px">
			<table style="width:100%;border-collapse:collapse;font-size:13px" id="igv-table">
				<thead>
					<tr style="background:var(--subtle-fg,#f4f5f6)">
						<th style="padding:8px 12px;width:32px;border-bottom:2px solid var(--border-color)"></th>
						<th style="padding:8px 12px;text-align:left;border-bottom:2px solid var(--border-color)">${__("Item Group / Item")}</th>
						<th style="padding:8px 12px;width:90px;text-align:right;border-bottom:2px solid var(--border-color)">${__("Qty")}</th>
						<th style="padding:8px 12px;width:130px;text-align:right;border-bottom:2px solid var(--border-color)">${__("Valuation Rate")}</th>
						<th style="padding:8px 12px;width:130px;text-align:right;border-bottom:2px solid var(--border-color)">${__("Value")}</th>
					</tr>
				</thead>
				<tbody id="igv-tbody">
					<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-muted)">${__("Select filters and click Refresh")}</td></tr>
				</tbody>
				<tfoot id="igv-tfoot"></tfoot>
			</table>
		</div>`;
	}
```

With:
```javascript
	_table_shell_html() {
		return `<div style="padding:16px;max-width:860px">
			<table style="width:100%;border-collapse:collapse;font-size:13px" id="igv-table">
				<thead>${this._thead_row_html(null)}</thead>
				<tbody id="igv-tbody">
					<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-muted)">${__("Select filters and click Refresh")}</td></tr>
				</tbody>
				<tfoot id="igv-tfoot"></tfoot>
			</table>
		</div>`;
	}
```

- [ ] **Step 4: Replace `_render_total_row` to delegate to the shared module**

Replace:
```javascript
	_render_total_row(rows, $tfoot) {
		const qty_total = rows.reduce((sum, row) => sum + (row.qty || 0), 0);
		const value_total = rows.reduce((sum, row) => sum + (row.value || 0), 0);
		$tfoot.html(`
			<tr style="font-weight:600;border-top:2px solid var(--border-color)">
				<td style="padding:8px 12px"></td>
				<td style="padding:8px 12px">${__("Total")}</td>
				<td style="padding:8px 12px;text-align:right">${this._fmt_num(qty_total)}</td>
				<td style="padding:8px 12px;text-align:right">—</td>
				<td style="padding:8px 12px;text-align:right">${this._fmt_num(value_total)}</td>
			</tr>`);
	}
```

With:
```javascript
	_render_total_row(rows, $tfoot) {
		const ST = window.cecypo_reports.sortableTable;
		const cells = ST.totalCellsHtml(IGV_COLUMNS, rows, {
			format: (v) => this._fmt_num(v),
			labelKey: "name",
			label: __("Total"),
		});
		$tfoot.html(`<tr class="cecypo-total-row"><td></td>${cells}</tr>`);
	}
```

- [ ] **Step 5: Syntax check**

Run: `node --check cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.js`
Expected: no syntax errors.

- [ ] **Step 6: Commit**

```bash
git add cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.js
git commit -m "feat: wire Item Group Valuation top-level table to sortable_table module"
```

---

### Task 4: Per-level subtotal + repeated header for nested tables

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.js`

- [ ] **Step 1: Add `<thead>`/`<tfoot>` to the nested table markup in `_render_rows`**

Replace:
```javascript
				<tr class="igv-detail-row hidden" data-detail-for="${esc}">
					<td colspan="5" style="padding:0;border-bottom:1px solid var(--border-color)">
						<div style="background:var(--card-bg,#fff)">
							<table style="width:100%;border-collapse:collapse;font-size:13px">
								<tbody class="igv-sub-tbody" data-for="${esc}" data-indent="${indent + 1}"></tbody>
							</table>
						</div>
					</td>
				</tr>`);
```

With:
```javascript
				<tr class="igv-detail-row hidden" data-detail-for="${esc}">
					<td colspan="5" style="padding:0;border-bottom:1px solid var(--border-color)">
						<div style="background:var(--card-bg,#fff)">
							<table style="width:100%;border-collapse:collapse;font-size:13px">
								<thead>${this._thead_row_html(null)}</thead>
								<tbody class="igv-sub-tbody" data-for="${esc}" data-indent="${indent + 1}"></tbody>
								<tfoot class="igv-sub-tfoot"></tfoot>
							</table>
						</div>
					</td>
				</tr>`);
```

- [ ] **Step 2: Store the canonical unsorted rows + sort state on `#igv-tbody`**

In `refresh()`, find:
```javascript
				$tbody.empty();
				this._render_rows(rows, $tbody, 0);
				this._render_total_row(rows, $tfoot);
```

Replace with:
```javascript
				$tbody.empty();
				$tbody.data("rows", rows);
				$tbody.data("sort", { key: null, dir: null });
				this._render_rows(rows, $tbody, 0);
				this._render_total_row(rows, $tfoot);
```

- [ ] **Step 3: Store rows + render subtotal for nested tables on expand**

In `_bind_events()`, find the `get_group_children` callback:
```javascript
			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.item_group_valuation.get_group_children",
				args: { item_group: group, warehouse: warehouse(), company: company() },
				callback: (r) => {
					const rows = r.message || [];
					$sub.empty();
					if (!rows.length) {
						$sub.html(`<tr><td colspan="5" style="padding:8px ${12 + (indent + 1) * 24}px;color:var(--text-muted)">${__("No items found")}</td></tr>`);
					} else {
						this._render_rows(rows, $sub, indent + 1);
					}
					$sub.data("loaded", true);
				},
			});
```

Replace with:
```javascript
			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.item_group_valuation.get_group_children",
				args: { item_group: group, warehouse: warehouse(), company: company() },
				callback: (r) => {
					const rows = r.message || [];
					const $sub_tfoot = $sub.closest("table").children("tfoot.igv-sub-tfoot");
					$sub.empty();
					if (!rows.length) {
						$sub.html(`<tr><td colspan="5" style="padding:8px ${12 + (indent + 1) * 24}px;color:var(--text-muted)">${__("No items found")}</td></tr>`);
						$sub_tfoot.empty();
					} else {
						$sub.data("rows", rows);
						$sub.data("sort", { key: null, dir: null });
						this._render_rows(rows, $sub, indent + 1);
						this._render_total_row(rows, $sub_tfoot);
					}
					$sub.data("loaded", true);
				},
			});
```

- [ ] **Step 4: Syntax check**

Run: `node --check cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.js`
Expected: no syntax errors.

- [ ] **Step 5: Commit**

```bash
git add cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.js
git commit -m "feat: add per-level subtotal and repeated header to nested Item Group Valuation tables"
```

---

### Task 5: Clickable sort headers with collapse-on-sort

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.js`

- [ ] **Step 1: Add the delegated sort click handler**

In `_bind_events()`, add this new handler. Place it as the last statement in
the method, after the existing `$(this.page.main).on("click", ".igv-group-row", ...)` handler's closing `});`:

```javascript
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

- [ ] **Step 2: Syntax check**

Run: `node --check cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.js`
Expected: no syntax errors.

- [ ] **Step 3: Commit**

```bash
git add cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.js
git commit -m "feat: make Item Group Valuation table headers clickable to sort, with collapse-on-sort"
```

---

### Task 6: Build assets and verify in browser

**Files:** none (build + manual verification only)

- [ ] **Step 1: Build frontend assets**

Run: `bench build --app cecypo_frappe_reports`
Expected: build completes with no errors.

- [ ] **Step 2: Manually verify**

1. Open the Item Group Valuation page (`/app/item-group-valuation`), select a Company, click Refresh.
2. Confirm the top-level header still looks the same (label + sort icon ↕ on each of the 4 sortable columns) and the grand total row at the bottom has a tinted background.
3. Expand a top-level group. Confirm the nested table shows its own header row (with ↕ icons) and its own subtotal footer (tinted background), and that the subtotal matches the sum of the visible nested rows.
4. Click the "Qty" header on the nested table. Confirm only that table's rows reorder (ascending), the icon changes to ↑, and the grand total at the very bottom is unchanged.
5. Click "Qty" again on the same nested table. Confirm it reverses to descending (↓).
6. With a group expanded inside that nested table (if any sub-group exists), click a header on the nested table. Confirm the expanded sub-group collapses (arrow resets to ▶).
7. Re-expand that sub-group. Confirm it re-fetches (briefly shows "Loading...") rather than instantly reappearing.
8. Click a header on the top-level table while a different top-level group is expanded. Confirm that group collapses, and confirm any other already-expanded nested table's own sort state is untouched (re-expand it and check its sort icon is still where you left it).
9. Change filters and click Refresh. Confirm headers, sorting, and totals all reset cleanly to the unsorted state.
10. Pick filters that return no data. Confirm the body shows "No data found" and the footer is empty (no stale total).

Expected: all checks in steps 2–10 pass.

- [ ] **Step 3: No commit needed**

This task only builds artifacts and verifies behavior — `bench build` output is not committed (build artifacts are git-ignored per existing project convention).

---

## Spec Coverage Check

- Per-level subtotals (every nested table gets its own `<tfoot>`) → Task 4.
- Repeated headers (every nested table gets its own `<thead>`) → Task 4, Step 1.
- All 4 columns sortable → Task 3 (`IGV_COLUMNS`), Task 5 (click handler).
- Sort toggles asc/desc, new column resets to asc → Task 5, Step 1.
- Collapse-on-sort, scoped to the clicked table's own tbody only → Task 5, Step 1.
- Re-fetch (not cache) on re-expand after a sort → inherent in Task 5's `_render_rows` rebuild; verified in Task 6, Steps 6–7.
- Total row tinted-background CSS via shared `.cecypo-total-row` class → Task 1 (`inject_style_once`), Task 3 Step 4.
- Reusable module, data-shape-agnostic, no Transaction History changes → Task 1, Task 2; no task touches `transaction_history.js`.
- `app_include_js` updated to load the new module → Task 2.
- No backend/Python changes → confirmed, no task touches `.py` files (other than `hooks.py`, which is config, not the report backend).
- Manual verification checklist from spec → Task 6, Step 2.
