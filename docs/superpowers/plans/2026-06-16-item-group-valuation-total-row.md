# Item Group Valuation Total Row Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bottom totals row (Qty + Value, no rate) to the Item Group Valuation custom page table, computed client-side from the top-level group rows.

**Architecture:** Pure frontend change to `item_group_valuation.js`. Add a `<tfoot id="igv-tfoot">` to the table shell, and a new `_render_total_row()` method that sums `qty`/`value` from the array returned by `get_top_level_groups` (the same array already used to render the top-level `<tbody>` rows). Wire it into `refresh()`'s loading/empty/success branches. No Python or `.json` changes.

**Tech Stack:** Frappe custom page (vanilla JS + jQuery), existing `format_number` helper via `_fmt_num()`.

**Spec:** `docs/superpowers/specs/2026-06-16-item-group-valuation-total-row-design.md`

---

### Task 1: Add `<tfoot>` to the table shell

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.js:49-66` (`_table_shell_html`)

- [ ] **Step 1: Add the `<tfoot>` element**

In `_table_shell_html()`, insert a `<tfoot id="igv-tfoot"></tfoot>` immediately after the closing `</tbody>` tag and before `</table>`:

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

- [ ] **Step 2: Confirm the file still has valid template syntax**

Run: `node --check cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.js`

Note: this file uses `frappe`/`__`/`$` globals so `node --check` will only validate syntax, not execute — that's all we need here.
Expected: no syntax errors (command exits 0, no output).

---

### Task 2: Compute and render the total row

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.js` (new method `_render_total_row`, plus edits to `refresh()`)

- [ ] **Step 1: Add the `_render_total_row` method**

Add this new method directly after `_render_rows(...)` (i.e., between the closing `}` of `_render_rows` and the `_bind_events()` method):

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

- [ ] **Step 2: Wire it into `refresh()`**

Replace the current `refresh()` method body with the version below — it adds a `$tfoot` lookup, clears the footer while loading and when no data is found, and calls `_render_total_row` on success:

```javascript
	refresh() {
		const company = this._f_company.get_value();
		if (!company) {
			frappe.msgprint(__("Please select a Company"));
			return;
		}
		const warehouse = this._f_warehouse.get_value() || null;
		const root_group = this._f_root_group.get_value() || "All Item Groups";

		this._cache = {};
		const $tbody = $("#igv-tbody");
		const $tfoot = $("#igv-tfoot");
		$tbody.html(`<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-muted)">${__("Loading...")}</td></tr>`);
		$tfoot.empty();

		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.item_group_valuation.get_top_level_groups",
			args: { root_group, warehouse, company },
			callback: (r) => {
				const rows = r.message || [];
				if (!rows.length) {
					$tbody.html(`<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-muted)">${__("No data found")}</td></tr>`);
					$tfoot.empty();
					return;
				}
				$tbody.empty();
				this._render_rows(rows, $tbody, 0);
				this._render_total_row(rows, $tfoot);
			},
		});
	}
```

- [ ] **Step 3: Syntax check**

Run: `node --check cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.js`
Expected: no syntax errors (command exits 0, no output).

- [ ] **Step 4: Commit**

```bash
git add cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.js
git commit -m "feat: add total Qty/Value row to Item Group Valuation table"
```

---

### Task 3: Build assets and verify in browser

**Files:** none (build + manual verification only)

- [ ] **Step 1: Build frontend assets**

Run: `bench build --app cecypo_frappe_reports`
Expected: build completes with no errors.

- [ ] **Step 2: Manually verify the totals row**

1. Open the Item Group Valuation page (`/app/item-group-valuation`).
2. Select a Company, click Refresh.
3. Confirm a bold "Total" row appears below the last top-level group row, with Qty and Value populated and the Valuation Rate cell showing `—`.
4. Manually sum the Qty/Value of the visible top-level rows and confirm it matches the footer.
5. Expand one of the top-level groups (click to drill into children). Confirm the footer total is unchanged (no double-counting from the now-visible child rows).
6. Change a filter (e.g., pick a different Root Group or Warehouse) and click Refresh again. Confirm the footer updates to match the new top-level rows.
7. Pick a filter combination that returns no data (e.g., a Warehouse with no stock). Confirm the footer is empty (no stale total left over) and the body shows "No data found".

Expected: all checks in steps 3–7 pass.

- [ ] **Step 3: No commit needed**

This task only builds artifacts and verifies behavior — `bench build` output is not committed (build artifacts are git-ignored per existing project convention).

---

## Spec Coverage Check

- Total row shows summed Qty + Value → Task 2, Step 1–2.
- Valuation Rate cell blank (`—`) → Task 2, Step 1 (`_render_total_row`).
- Client-side computation from `get_top_level_groups` array, no new backend call → Task 2, Step 1–2.
- `<tfoot>` separate from `<tbody>`, untouched by expand/collapse → Task 1.
- Loading/no-data states clear the footer → Task 2, Step 2.
- No Python/test changes → confirmed, no Task touches `.py` files.
- Manual verification checklist from spec → Task 3, Step 2.
