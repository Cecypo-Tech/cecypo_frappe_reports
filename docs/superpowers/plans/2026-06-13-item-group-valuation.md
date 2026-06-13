# Item Group Valuation Enhanced — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a custom Frappe page showing inventory valuation by item group, with a two-level `▶`/`▼` accordion drill-down (group → sub-groups → items), sourcing data directly from the `bin` table.

**Architecture:** Custom Page under `cecypo_frappe_reports/page/item_group_valuation/` — same pattern as `transaction_history`. Python backend exposes two `@frappe.whitelist()` methods using `frappe.qb`. The JS page class renders an HTML table and handles accordion expand/collapse via a single delegated click handler; child rows are fetched on demand and cached per group.

**Tech Stack:** Frappe framework, `frappe.qb` / PyPika, jQuery (via Frappe globals), `format_number` global, `frappe.call()`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `cecypo_frappe_reports/page/item_group_valuation/__init__.py` | Create | Empty marker |
| `cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.json` | Create | Page metadata, roles |
| `cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.py` | Create | `get_top_level_groups()`, `get_group_children()`, `_aggregate_for_group()` |
| `cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.js` | Create | `ItemGroupValuationPage` class — setup, refresh, render, events |
| `cecypo_frappe_reports/page/item_group_valuation/test_item_group_valuation.py` | Create | Unit tests for Python methods |

All paths are relative to `cecypo_frappe_reports/cecypo_frappe_reports/`.

---

### Task 1: Page skeleton (JSON + `__init__.py`)

**Files:**
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/__init__.py`
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.json`

- [ ] **Step 1: Create the directory and `__init__.py`**

```bash
mkdir -p /home/kushal/frappe-bench/apps/cecypo_frappe_reports/cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation
touch /home/kushal/frappe-bench/apps/cecypo_frappe_reports/cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/__init__.py
```

- [ ] **Step 2: Create `item_group_valuation.json`**

```json
{
 "content": null,
 "creation": "2026-06-13 00:00:00.000000",
 "docstatus": 0,
 "doctype": "Page",
 "idx": 0,
 "modified": "2026-06-13 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Cecypo Frappe Reports",
 "name": "item-group-valuation",
 "owner": "Administrator",
 "page_name": "item-group-valuation",
 "restrict_to_domain": "",
 "roles": [
  {"role": "Stock Manager"},
  {"role": "Stock User"},
  {"role": "System Manager"}
 ],
 "standard": "Yes",
 "system_page": 0,
 "title": "Item Group Valuation"
}
```

- [ ] **Step 3: Commit**

```bash
cd /home/kushal/frappe-bench/apps/cecypo_frappe_reports
git add cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/__init__.py
git add cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.json
git commit -m "feat: add Item Group Valuation page skeleton"
```

---

### Task 2: Python backend — `get_top_level_groups()` and `_aggregate_for_group()`

**Files:**
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.py`
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/test_item_group_valuation.py`

- [ ] **Step 1: Write the failing test**

Create `cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/test_item_group_valuation.py`:

```python
# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import unittest


class TestItemGroupValuationPage(unittest.TestCase):
	def test_get_top_level_groups_returns_list(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.item_group_valuation import (
			get_top_level_groups,
		)

		rows = get_top_level_groups(root_group="__nonexistent__", company="_Test Company")
		self.assertIsInstance(rows, list)
		self.assertEqual(rows, [])

	def test_get_top_level_groups_known_root(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.item_group_valuation import (
			get_top_level_groups,
		)

		rows = get_top_level_groups(root_group="All Item Groups", company="_Test Company")
		self.assertIsInstance(rows, list)
		for row in rows:
			self.assertIn("item_group", row)
			self.assertIn("qty", row)
			self.assertIn("valuation_rate", row)
			self.assertIn("value", row)
			self.assertIn("is_group", row)
			self.assertEqual(row["is_group"], 1)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/kushal/frappe-bench
bench --site $(ls sites/ | grep -v apps | grep -v assets | grep -v currentsite.txt | head -1) run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.test_item_group_valuation 2>&1 | tail -20
```

Expected: ImportError or ModuleNotFoundError (file doesn't exist yet).

- [ ] **Step 3: Create `item_group_valuation.py`**

```python
# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from pypika import functions as fn


@frappe.whitelist()
def get_top_level_groups(root_group=None, warehouse=None, company=None):
	if not root_group:
		root_group = "All Item Groups"

	IG = frappe.qb.DocType("Item Group")
	children = (
		frappe.qb.from_(IG)
		.select(IG.name, IG.lft, IG.rgt)
		.where(IG.parent_item_group == root_group)
		.orderby(IG.lft)
	).run(as_dict=True)

	result = []
	for child in children:
		agg = _aggregate_for_group(child.lft, child.rgt, warehouse, company)
		qty = flt(agg.get("qty") or 0, 2)
		value = flt(agg.get("value") or 0, 2)
		result.append({
			"item_group": child.name,
			"qty": qty,
			"valuation_rate": flt(value / qty, 2) if qty else 0,
			"value": value,
			"is_group": 1,
		})
	return result


def _aggregate_for_group(lft, rgt, warehouse=None, company=None):
	IG = frappe.qb.DocType("Item Group")
	Item = frappe.qb.DocType("Item")
	Bin = frappe.qb.DocType("Bin")
	Wh = frappe.qb.DocType("Warehouse")

	q = (
		frappe.qb.from_(Bin)
		.join(Item).on(Item.name == Bin.item_code)
		.join(IG).on(IG.name == Item.item_group)
		.join(Wh).on(Wh.name == Bin.warehouse)
		.select(
			fn.Sum(Bin.actual_qty).as_("qty"),
			fn.Sum(Bin.stock_value).as_("value"),
		)
		.where(IG.lft >= lft)
		.where(IG.rgt <= rgt)
	)

	if company:
		q = q.where(Wh.company == company)
	if warehouse:
		q = q.where(Bin.warehouse == warehouse)

	result = q.run(as_dict=True)
	return result[0] if result else {}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/kushal/frappe-bench
bench --site $(ls sites/ | grep -v apps | grep -v assets | grep -v currentsite.txt | head -1) run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.test_item_group_valuation 2>&1 | tail -20
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/kushal/frappe-bench/apps/cecypo_frappe_reports
git add cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.py
git add cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/test_item_group_valuation.py
git commit -m "feat: add get_top_level_groups and _aggregate_for_group"
```

---

### Task 3: Python backend — `get_group_children()`

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.py`
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/test_item_group_valuation.py`

- [ ] **Step 1: Add failing tests**

Append to `test_item_group_valuation.py`:

```python
	def test_get_group_children_nonexistent_returns_list(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.item_group_valuation import (
			get_group_children,
		)

		rows = get_group_children(item_group="__nonexistent__", company="_Test Company")
		self.assertIsInstance(rows, list)
		self.assertEqual(rows, [])

	def test_get_group_children_returns_correct_keys(self):
		from cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.item_group_valuation import (
			get_group_children,
		)

		rows = get_group_children(item_group="All Item Groups", company="_Test Company")
		self.assertIsInstance(rows, list)
		for row in rows:
			self.assertIn("qty", row)
			self.assertIn("valuation_rate", row)
			self.assertIn("value", row)
			self.assertIn("is_group", row)
```

- [ ] **Step 2: Run tests to verify new tests fail**

```bash
cd /home/kushal/frappe-bench
bench --site $(ls sites/ | grep -v apps | grep -v assets | grep -v currentsite.txt | head -1) run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.test_item_group_valuation 2>&1 | tail -20
```

Expected: `AttributeError: module ... has no attribute 'get_group_children'`

- [ ] **Step 3: Add `get_group_children()` to `item_group_valuation.py`**

Append after `_aggregate_for_group`:

```python
@frappe.whitelist()
def get_group_children(item_group, warehouse=None, company=None):
	IG = frappe.qb.DocType("Item Group")
	child_groups = (
		frappe.qb.from_(IG)
		.select(IG.name, IG.lft, IG.rgt)
		.where(IG.parent_item_group == item_group)
		.orderby(IG.lft)
	).run(as_dict=True)

	if child_groups:
		result = []
		for child in child_groups:
			agg = _aggregate_for_group(child.lft, child.rgt, warehouse, company)
			qty = flt(agg.get("qty") or 0, 2)
			value = flt(agg.get("value") or 0, 2)
			result.append({
				"item_group": child.name,
				"qty": qty,
				"valuation_rate": flt(value / qty, 2) if qty else 0,
				"value": value,
				"is_group": 1,
			})
		return result

	# Leaf group — return individual items
	Item = frappe.qb.DocType("Item")
	Bin = frappe.qb.DocType("Bin")
	Wh = frappe.qb.DocType("Warehouse")

	q = (
		frappe.qb.from_(Bin)
		.join(Item).on(Item.name == Bin.item_code)
		.join(Wh).on(Wh.name == Bin.warehouse)
		.select(
			Item.item_code,
			Item.item_name,
			fn.Sum(Bin.actual_qty).as_("qty"),
			fn.Sum(Bin.stock_value).as_("value"),
		)
		.where(Item.item_group == item_group)
		.groupby(Item.item_code, Item.item_name)
		.orderby(Item.item_code)
	)

	if company:
		q = q.where(Wh.company == company)
	if warehouse:
		q = q.where(Bin.warehouse == warehouse)

	items = q.run(as_dict=True)
	result = []
	for item in items:
		qty = flt(item.get("qty") or 0, 2)
		value = flt(item.get("value") or 0, 2)
		result.append({
			"item_code": item["item_code"],
			"item_name": item["item_name"],
			"qty": qty,
			"valuation_rate": flt(value / qty, 2) if qty else 0,
			"value": value,
			"is_group": 0,
		})
	return result
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
cd /home/kushal/frappe-bench
bench --site $(ls sites/ | grep -v apps | grep -v assets | grep -v currentsite.txt | head -1) run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.test_item_group_valuation 2>&1 | tail -20
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/kushal/frappe-bench/apps/cecypo_frappe_reports
git add cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.py
git add cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/test_item_group_valuation.py
git commit -m "feat: add get_group_children for sub-groups and leaf items"
```

---

### Task 4: JS — page class, filter toolbar, table shell

**Files:**
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.js`

- [ ] **Step 1: Create `item_group_valuation.js` with page bootstrap and `setup()`**

```javascript
// Copyright (c) 2026, Cecypo and contributors
// For license information, please see license.txt

frappe.pages["item-group-valuation"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Item Group Valuation"),
		single_column: true,
	});
	new ItemGroupValuationPage(wrapper);
};

class ItemGroupValuationPage {
	constructor(wrapper) {
		this.page = wrapper.page;
		this._cache = {};
		this.setup();
	}

	setup() {
		this._f_company = this.page.add_field({
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		});
		this._f_warehouse = this.page.add_field({
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
		});
		this._f_root_group = this.page.add_field({
			fieldname: "root_group",
			label: __("Root Group"),
			fieldtype: "Link",
			options: "Item Group",
			default: "All Item Groups",
		});

		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");

		$(this.page.main).html(this._table_shell_html());
		this._bind_events();
	}

	_table_shell_html() {
		return `<div style="padding:16px">
			<table style="width:100%;border-collapse:collapse;font-size:13px" id="igv-table">
				<thead>
					<tr style="background:var(--subtle-fg,#f4f5f6)">
						<th style="padding:8px 12px;width:32px;border-bottom:2px solid var(--border-color)"></th>
						<th style="padding:8px 12px;text-align:left;border-bottom:2px solid var(--border-color)">${__("Item Group / Item")}</th>
						<th style="padding:8px 12px;text-align:right;border-bottom:2px solid var(--border-color)">${__("Qty")}</th>
						<th style="padding:8px 12px;text-align:right;border-bottom:2px solid var(--border-color)">${__("Valuation Rate")}</th>
						<th style="padding:8px 12px;text-align:right;border-bottom:2px solid var(--border-color)">${__("Value")}</th>
					</tr>
				</thead>
				<tbody id="igv-tbody">
					<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-muted)">${__("Select filters and click Refresh")}</td></tr>
				</tbody>
			</table>
		</div>`;
	}

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
		$tbody.html(`<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-muted)">${__("Loading...")}</td></tr>`);

		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.item_group_valuation.get_top_level_groups",
			args: { root_group, warehouse, company },
			callback: (r) => {
				const rows = r.message || [];
				if (!rows.length) {
					$tbody.html(`<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-muted)">${__("No data found")}</td></tr>`);
					return;
				}
				$tbody.empty();
				this._render_rows(rows, $tbody, 0);
			},
		});
	}

	_fmt_num(v) {
		return v != null ? format_number(v, null, 2) : "—";
	}

	_render_rows(rows, $tbody, indent) {
		const pad = indent * 24;
		rows.forEach((row, i) => {
			const bg = i % 2 ? "background:var(--control-bg)" : "";
			if (row.is_group) {
				const name = row.item_group;
				const esc = frappe.utils.escape_html(name);
				$tbody.append(`
				<tr class="igv-group-row" data-group="${esc}" data-indent="${indent}" style="cursor:pointer;${bg}">
					<td style="padding:6px 8px 6px ${12 + pad}px;border-bottom:1px solid var(--border-color);color:var(--text-muted)">▶</td>
					<td style="padding:6px 12px 6px ${pad}px;border-bottom:1px solid var(--border-color);font-weight:500">${esc}</td>
					<td style="padding:6px 12px;text-align:right;border-bottom:1px solid var(--border-color)">${this._fmt_num(row.qty)}</td>
					<td style="padding:6px 12px;text-align:right;border-bottom:1px solid var(--border-color)">${this._fmt_num(row.valuation_rate)}</td>
					<td style="padding:6px 12px;text-align:right;border-bottom:1px solid var(--border-color);font-weight:600">${this._fmt_num(row.value)}</td>
				</tr>
				<tr class="igv-detail-row hidden" data-detail-for="${esc}">
					<td colspan="5" style="padding:0;border-bottom:1px solid var(--border-color)">
						<div style="background:var(--card-bg,#fff)">
							<table style="width:100%;border-collapse:collapse;font-size:13px">
								<tbody class="igv-sub-tbody" data-for="${esc}" data-indent="${indent + 1}"></tbody>
							</table>
						</div>
					</td>
				</tr>`);
			} else {
				const code = frappe.utils.escape_html(row.item_code);
				const name = row.item_name && row.item_name !== row.item_code
					? `<span style="color:var(--text-muted);margin-left:6px">${frappe.utils.escape_html(row.item_name)}</span>`
					: "";
				$tbody.append(`
				<tr style="${bg}">
					<td style="padding:6px 8px 6px ${12 + pad}px;border-bottom:1px solid var(--border-color)"></td>
					<td style="padding:6px 12px 6px ${pad}px;border-bottom:1px solid var(--border-color)">
						<a href="/app/item/${code}" target="_blank">${code}</a>${name}
					</td>
					<td style="padding:6px 12px;text-align:right;border-bottom:1px solid var(--border-color)">${this._fmt_num(row.qty)}</td>
					<td style="padding:6px 12px;text-align:right;border-bottom:1px solid var(--border-color)">${this._fmt_num(row.valuation_rate)}</td>
					<td style="padding:6px 12px;text-align:right;border-bottom:1px solid var(--border-color);font-weight:600">${this._fmt_num(row.value)}</td>
				</tr>`);
			}
		});
	}

	_bind_events() {
		const company = () => this._f_company.get_value();
		const warehouse = () => this._f_warehouse.get_value() || null;

		$(this.page.main).on("click", ".igv-group-row", (e) => {
			const $row = $(e.currentTarget);
			const group = $row.data("group");
			const indent = parseInt($row.data("indent") || 0);
			const $detail = $row.next(".igv-detail-row");

			if (!$detail.hasClass("hidden")) {
				$detail.addClass("hidden");
				$row.find("td:first").text("▶");
				return;
			}

			$row.find("td:first").text("▼");
			$detail.removeClass("hidden");

			const $sub = $detail.find(`.igv-sub-tbody[data-for="${group}"]`);
			if ($sub.data("loaded")) return;

			$sub.html(`<tr><td colspan="5" style="padding:8px ${12 + (indent + 1) * 24}px;color:var(--text-muted)">${__("Loading...")}</td></tr>`);

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
		});
	}
}
```

- [ ] **Step 2: Commit**

```bash
cd /home/kushal/frappe-bench/apps/cecypo_frappe_reports
git add cecypo_frappe_reports/cecypo_frappe_reports/page/item_group_valuation/item_group_valuation.js
git commit -m "feat: add Item Group Valuation JS page with accordion drill-down"
```

---

### Task 5: Migrate and verify in browser

**Files:** No new files — just running bench commands.

- [ ] **Step 1: Run migrate to register the new page**

```bash
cd /home/kushal/frappe-bench
bench --site $(ls sites/ | grep -v apps | grep -v assets | grep -v currentsite.txt | head -1) migrate 2>&1 | tail -10
```

Expected: Migration completes without errors. Look for `item-group-valuation` or `item_group_valuation` in output.

- [ ] **Step 2: Build assets**

```bash
cd /home/kushal/frappe-bench
bench build --app cecypo_frappe_reports 2>&1 | tail -10
```

Expected: Build completes without errors.

- [ ] **Step 3: Verify the page is accessible**

Navigate to `/app/item-group-valuation` in the browser. Verify:
- Page title shows "Item Group Valuation"
- Filter toolbar shows Company, Warehouse, Root Group fields
- Refresh button is present
- Table shell renders with the correct headers

- [ ] **Step 4: Verify drill-down works**

1. Select a company, click Refresh
2. Confirm top-level item groups appear with `▶` arrows
3. Click a group row — confirm it expands to show child groups (arrow becomes `▼`)
4. Click a child group with no sub-groups — confirm it expands to show individual items
5. Click `▼` to collapse — confirm the arrow returns to `▶`
6. Re-expand — confirm no second server call (cached)
7. Click an item link — confirm it opens `/app/item/<item-code>` in a new tab

- [ ] **Step 5: Commit**

```bash
cd /home/kushal/frappe-bench/apps/cecypo_frappe_reports
git add -A
git commit -m "feat: complete Item Group Valuation custom page with drill-down"
```
