# Transaction History Item Picker + Stock Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Items tab's sidebar + per-item tabs with an extra-large picker dialog and an item selector, add a Stock Card (ledger) view, and gate cost and warehouse data on the server by Stock Ledger Entry read and Warehouse User Permissions.

**Architecture:** All gating happens in `transaction_history.py` via two helpers (`_can_see_cost`, `_permitted_warehouses`) applied to every Items-tab endpoint plus the two Supplier-tab endpoints; gated keys are omitted from payloads, never zeroed. Two new whitelisted endpoints (`search_items`, `get_stock_card`) back the picker table and the Stock Card. `transaction_history.js` loses the sidebar, checklist and tab strip, and gains a `frappe.ui.Dialog` picker, a chips + `<select>` navigator, a History/Stock Card toggle and a stock-card renderer; renderers hide a column whenever its key is absent from the payload.

**Tech Stack:** Frappe v15 desk page (jQuery, `frappe.ui.Dialog`, `frappe.call`), `frappe.qb`, `IntegrationTestCase`, ERPNext test helpers (`make_stock_entry`, `create_sales_invoice`).

**Spec:** `docs/superpowers/specs/2026-10-24-transaction-history-item-picker-stock-card-design.md`

## Global Constraints

- Python: tabs, double quotes, line length 110, `frappe.qb` for SQL, `flt(v, 2)` for money/qty.
- JS: tabs, inline styles in template strings, `format_number(v, null, 2)` / `format_currency(v, bc)` as the rest of the file does.
- Cost keys (`cost`, `valuation_rate`, `avg_valuation_rate`, `avg_rate`, `stock_value`, `incoming_rate`, `outgoing_rate`, `stock_value_difference`, `opening_value`, `value`) must be **absent** from any payload when `_can_see_cost()` is false. Never `0`, never `null`.
- Cost switch is exactly `frappe.has_permission("Stock Ledger Entry", "read")`.
- Warehouse scope is Frappe User Permissions on `Warehouse`, intersected with the company's enabled non-group warehouses.
- Picker result cap 100; stock card row cap 5000; warehouse-column collapse threshold 6; sell price list = `Selling Settings.selling_price_list`.
- Tests run on `dev.localhost`: `bench --site dev.localhost run-tests --module cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.test_transaction_history`. Check `ps -eo cmd | grep 'run-tests'` before trusting a red run.
- No `Co-Authored-By` trailer on commits. Work on branch `feat/th-item-picker-stock-card` off `main`.
- **Mobile (user requirement, spec § Mobile):** every UI task verifies at 390×844 as well as desktop. Below 768px: picker warehouse columns always collapse to the single `Stock` column and the Group column is hidden; picker table and stock card table scroll inside an `overflow-x:auto` wrapper with sticky-left identifying columns; no whole-page horizontal scroll; tap targets ≥ 32px. New CSS goes in the existing `@media (max-width: 767px)` block in `_inject_styles`.
- Browser logins on dev.localhost: `Administrator` / `admin`; cost-blind user `rishit.test@dev.local` / `rishit123`. Use the Playwright MCP tools (`browser_navigate`, `browser_resize` to 390×844 for mobile, `browser_snapshot`, `browser_click`, `browser_type`, `browser_console_messages`). Log out via `http://dev.localhost:8000/?cmd=web_logout` between users.

## Review Focus

1. **PO/SO lines with no warehouse for an unrestricted user.** Open-order rows whose `warehouse` is NULL must still appear when no User Permission and no warehouse filter apply. Test in Task 2.
2. **Cancelled ledger entries.** A cancelled Stock Entry leaves `is_cancelled=1` rows; the stock card must exclude them and the running balance must still match `Bin.actual_qty`. Test in Task 4.
3. **Item Price validity.** An expired `Item Price` (`valid_upto` in the past) on the default list must not be shown as the sell price. Test in Task 3.
4. **Picker with empty search and no group.** Must return no rows, not the whole catalogue. Test in Task 3.
5. **Pricing tab average for a gated user.** With `valuation_rate` absent, the "Avg Val. Rate" stat must render `—`, not `0.00`. Covered manually in Task 7 (no JS test harness).
6. **Phone viewport.** At 390px wide the picker's confirm button must be reachable and the stock card must scroll inside its own wrapper rather than widening the page. Covered manually in Tasks 5 and 6.

---

### Task 1: Cost gating helpers on existing endpoints

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py` (top of file near `_can_see_billing_stats`; `get_item_history` L24–34; `get_supplier_history` L127–200; `get_supplier_item_transactions` L202–280)
- Test: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/test_transaction_history.py`

**Interfaces:**
- Produces: `_can_see_cost() -> bool`; `COST_KEYS: frozenset[str]`; `_strip_cost(rows: list[dict]) -> list[dict]` (returns same list, keys removed in place when `_can_see_cost()` is false; no-op otherwise). `get_item_history(...)` now returns an extra key `"can_see_cost": bool`.

- [ ] **Step 1: Write the failing tests**

```python
def _as_cost_blind_user(self):
	"""Sales User only — no Stock Ledger Entry read. Same user as _as_sales_only_user."""
	return self._as_sales_only_user()

def _receipt(self, qty=10, rate=100, warehouse="_Test Warehouse - _TC", item="_Test Item", posting_date=None):
	from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
	return make_stock_entry(item_code=item, qty=qty, rate=rate, to_warehouse=warehouse,
		company="_Test Company", posting_date=posting_date)

def test_item_history_hides_cost_for_user_without_sle_read(self):
	self._receipt()
	email = self._as_cost_blind_user()
	frappe.set_user(email)
	try:
		self.assertFalse(frappe.has_permission("Stock Ledger Entry", "read"))
		d = get_item_history(item="_Test Item", company="_Test Company")
		self.assertFalse(d["can_see_cost"])
		self.assertNotIn("avg_rate", d["stock_metrics"])
		self.assertNotIn("stock_value", d["stock_metrics"])
		self.assertIn("current_stock", d["stock_metrics"])
		for r in d["purchases"]:
			self.assertNotIn("valuation_rate", r)
	finally:
		frappe.set_user("Administrator")

def test_item_history_shows_cost_for_administrator(self):
	self._receipt()
	d = get_item_history(item="_Test Item", company="_Test Company")
	self.assertTrue(d["can_see_cost"])
	self.assertIn("avg_rate", d["stock_metrics"])
	self.assertIn("stock_value", d["stock_metrics"])

def test_supplier_endpoints_hide_valuation_for_cost_blind_user(self):
	email = self._as_cost_blind_user()
	frappe.set_user(email)
	try:
		for r in get_supplier_history(supplier="_Test Supplier", company="_Test Company", source="pr"):
			self.assertNotIn("avg_valuation_rate", r)
		for r in get_supplier_item_transactions(supplier="_Test Supplier", item_code="_Test Item",
				company="_Test Company", source="pr"):
			self.assertNotIn("valuation_rate", r)
	finally:
		frappe.set_user("Administrator")
```

(Add a Purchase Receipt fixture in the supplier test if `_Test Supplier` has none on the site: `from erpnext.stock.doctype.purchase_receipt.test_purchase_receipt import make_purchase_receipt; make_purchase_receipt(item_code="_Test Item", qty=1, rate=50, warehouse="_Test Warehouse - _TC")` so the loops assert on at least one row; assert `len(rows) >= 1`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `bench --site dev.localhost run-tests --module cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.test_transaction_history --test test_item_history_hides_cost_for_user_without_sle_read --test test_item_history_shows_cost_for_administrator --test test_supplier_endpoints_hide_valuation_for_cost_blind_user`
Expected: FAIL — `KeyError: 'can_see_cost'` / `avg_rate` present.

- [ ] **Step 3: Implement helpers and apply them**

In `transaction_history.py`, after `_can_see_billing_stats`:

```python
COST_KEYS = frozenset({"cost", "valuation_rate", "avg_valuation_rate", "avg_rate", "stock_value",
	"incoming_rate", "outgoing_rate", "stock_value_difference", "opening_value", "value"})

def _can_see_cost() -> bool:
	return frappe.has_permission("Stock Ledger Entry", "read")

def _strip_cost(rows):
	if _can_see_cost():
		return rows
	for r in rows:
		for k in COST_KEYS:
			r.pop(k, None)
	return rows
```

Apply: `get_item_history` wraps `stock_metrics` (as a one-element list) and `purchases` with `_strip_cost`, adds `"can_see_cost": _can_see_cost()`. `get_supplier_history` and `get_supplier_item_transactions` return `_strip_cost(rows)`.

- [ ] **Step 4: Run tests to verify they pass**

Same command as Step 2. Expected: PASS. Then run the whole module once; expected: no new failures.

- [ ] **Step 5: Commit**

```bash
git add cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/
git commit -m "feat(transaction-history): gate cost fields on Stock Ledger Entry read"
```

---

### Task 2: Warehouse scoping across Items-tab queries

**Files:**
- Modify: `transaction_history.py` — `get_warehouse_stock` L410–428, `_get_stock_metrics` L1025–1075, `_get_purchase_rows` L1077–1149, `_get_open_purchase_orders` L1152–1187, `_get_open_sales_orders` L1190–1225, `_get_sales_rows` L1228–1267, `get_item_history` L24–34
- Test: `test_transaction_history.py`

**Interfaces:**
- Produces: `_permitted_warehouses(company: str) -> list[str]` (company's enabled non-group warehouses, intersected with the user's Warehouse User Permissions when any exist); `_warehouse_filter(company: str, warehouse: str | None) -> list[str] | None` (`None` = unrestricted and no filter → no WHERE clause; `[]` = nothing allowed; otherwise the list to put in `IN`). Both are used by Tasks 3 and 4.
- Consumes: Task 1 helpers.

- [ ] **Step 1: Write the failing tests**

```python
def _as_warehouse_restricted_user(self, warehouse="_Test Warehouse - _TC"):
	email = self._as_cost_blind_user()
	frappe.get_doc({"doctype": "User Permission", "user": email, "allow": "Warehouse",
		"for_value": warehouse}).insert(ignore_permissions=True)
	return email

def test_permitted_warehouses_respects_user_permission(self):
	email = self._as_warehouse_restricted_user()
	frappe.set_user(email)
	try:
		self.assertEqual(_permitted_warehouses("_Test Company"), ["_Test Warehouse - _TC"])
		self.assertEqual(_warehouse_filter("_Test Company", "_Test Warehouse 1 - _TC"), [])
		self.assertEqual(_warehouse_filter("_Test Company", None), ["_Test Warehouse - _TC"])
	finally:
		frappe.set_user("Administrator")
	self.assertIsNone(_warehouse_filter("_Test Company", None))
	self.assertEqual(_warehouse_filter("_Test Company", "_Test Warehouse 1 - _TC"), ["_Test Warehouse 1 - _TC"])

def test_item_history_scopes_to_permitted_warehouses(self):
	from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
	self._receipt(qty=10, warehouse="_Test Warehouse - _TC")
	self._receipt(qty=5, warehouse="_Test Warehouse 1 - _TC")
	create_sales_invoice(item_code="_Test Item", qty=1, rate=300, update_stock=1,
		warehouse="_Test Warehouse 1 - _TC", company="_Test Company")
	email = self._as_warehouse_restricted_user()
	frappe.set_user(email)
	try:
		d = get_item_history(item="_Test Item", company="_Test Company")
		self.assertEqual(d["stock_metrics"]["current_stock"], 10)
		self.assertEqual(d["sales"], [])
		d2 = get_item_history(item="_Test Item", company="_Test Company", warehouse="_Test Warehouse 1 - _TC")
		self.assertEqual(d2["stock_metrics"]["current_stock"], 0)
		self.assertEqual(d2["purchases"], [])
		whs = [w["warehouse"] for w in get_warehouse_stock("_Test Item", "_Test Company")]
		self.assertEqual(whs, ["_Test Warehouse - _TC"])
	finally:
		frappe.set_user("Administrator")

def test_open_orders_without_warehouse_still_listed_for_unrestricted_user(self):
	from erpnext.buying.doctype.purchase_order.test_purchase_order import create_purchase_order
	po = create_purchase_order(item_code="_Test Item", qty=3, rate=10, do_not_save=True)
	po.items[0].warehouse = None
	po.set_warehouse = None
	po.insert(); po.submit()
	d = get_item_history(item="_Test Item", company="_Test Company")
	self.assertIn(po.name, [r["voucher_no"] for r in d["open_po"]])
```

(If `Purchase Order Item.warehouse` is mandatory on this site and the insert fails, drop that test and the NULL case is moot — note it in the commit message.)

- [ ] **Step 2: Run tests to verify they fail**

Run the module with `--test` for the three names. Expected: FAIL — `ImportError` for `_permitted_warehouses`; `current_stock` 15 not 10.

- [ ] **Step 3: Implement**

```python
def _permitted_warehouses(company):
	whs = frappe.get_all("Warehouse", {"company": company, "is_group": 0, "disabled": 0}, pluck="name")
	allowed = frappe.permissions.get_user_permissions().get("Warehouse")
	if allowed:
		allowed = {d.get("doc") for d in allowed}
		whs = [w for w in whs if w in allowed]
	return whs

def _warehouse_filter(company, warehouse=None):
	restricted = bool(frappe.permissions.get_user_permissions().get("Warehouse"))
	if not restricted and not warehouse:
		return None
	permitted = _permitted_warehouses(company)
	if warehouse:
		return [warehouse] if warehouse in permitted else []
	return permitted
```

Then in each of `_get_purchase_rows`, `_get_sales_rows`, `_get_open_purchase_orders`, `_get_open_sales_orders`: replace the `if warehouse: ... == warehouse` clause with `whs = _warehouse_filter(company, warehouse)`; `if whs == []: return []`; `if whs is not None: query = query.where(child.warehouse.isin(whs))`. In `_get_stock_metrics`: `whs = _warehouse_filter(company, warehouse)`; `if whs is None: whs = _permitted_warehouses(company)`; then `filters = {"item_code": item, "warehouse": ["in", whs]}`; when `whs == []` skip the Bin query (totals 0). Bin always has a warehouse, so the IN clause is applied unconditionally there, which also fixes the missing company filter. In `get_warehouse_stock`: add `.where(Wh.name.isin(_permitted_warehouses(company)))` (return `[]` early when the list is empty).

- [ ] **Step 4: Run tests to verify they pass**

Run the three tests, then the full module. Expected: PASS, no new failures.

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(transaction-history): scope Items tab queries by Warehouse user permissions"
```

---

### Task 3: `search_items` endpoint (picker data, parent-group fix)

**Files:**
- Modify: `transaction_history.py` (new whitelisted function after `get_warehouse_stock`)
- Test: `test_transaction_history.py`

**Interfaces:**
- Produces:
  ```python
  @frappe.whitelist()
  def search_items(company, txt="", item_group=None, limit=100) -> dict
  # {"can_see_cost": bool, "warehouses": [str], "truncated": bool,
  #  "items": [{"item_code", "item_name", "item_group", "stock_uom", "sell_price": float|None,
  #             "stock": {warehouse: qty}, "total_qty": float, "cost": float|None}]}
  ```
  `warehouses` = permitted warehouses with a non-zero qty for at least one returned item, ordered by summed qty desc. `cost` key present only when `can_see_cost`. `items` empty when `txt.strip()` is shorter than 2 chars and no `item_group`.
- Consumes: `cecypo_frappe_reports.cecypo_frappe_reports.api.item_query` (call with `doctype="Item", txt=txt, searchfield="name", start=0, page_len=limit + 1, filters=..., as_dict=True`); Task 1 `_can_see_cost`; Task 2 `_permitted_warehouses`.

- [ ] **Step 1: Write the failing tests**

```python
def _child_group_item(self):
	"""An Item Group under _Test Item Group and one item in it; returns item code."""
	if not frappe.db.exists("Item Group", "_TH Child Group"):
		frappe.get_doc({"doctype": "Item Group", "item_group_name": "_TH Child Group",
			"parent_item_group": "_Test Item Group"}).insert(ignore_permissions=True)
	if not frappe.db.exists("Item", "_TH Child Item"):
		frappe.get_doc({"doctype": "Item", "item_code": "_TH Child Item", "item_name": "TH Child Item",
			"item_group": "_TH Child Group", "stock_uom": "Nos", "is_stock_item": 1}).insert(ignore_permissions=True)
	return "_TH Child Item"

def test_search_items_includes_descendant_groups(self):
	code = self._child_group_item()
	res = search_items(company="_Test Company", item_group="_Test Item Group")
	self.assertIn(code, [i["item_code"] for i in res["items"]])

def test_search_items_empty_without_text_or_group(self):
	self.assertEqual(search_items(company="_Test Company", txt=" ")["items"], [])

def test_search_items_stock_price_and_cost_shape(self):
	self._receipt(qty=10, rate=100, warehouse="_Test Warehouse - _TC")
	pl = frappe.db.get_single_value("Selling Settings", "selling_price_list")
	frappe.get_doc({"doctype": "Item Price", "item_code": "_Test Item", "price_list": pl,
		"price_list_rate": 250, "selling": 1}).insert(ignore_permissions=True)
	frappe.get_doc({"doctype": "Item Price", "item_code": "_Test Item", "price_list": pl,
		"price_list_rate": 999, "selling": 1, "valid_from": "2020-01-01",
		"valid_upto": "2020-12-31"}).insert(ignore_permissions=True)
	res = search_items(company="_Test Company", txt="_Test Item")
	row = next(i for i in res["items"] if i["item_code"] == "_Test Item")
	self.assertEqual(row["sell_price"], 250)
	self.assertEqual(row["stock"]["_Test Warehouse - _TC"], 10)
	self.assertIn("_Test Warehouse - _TC", res["warehouses"])
	self.assertTrue(res["can_see_cost"]); self.assertEqual(row["cost"], 100)
	frappe.set_user(self._as_cost_blind_user())
	try:
		res = search_items(company="_Test Company", txt="_Test Item")
		row = next(i for i in res["items"] if i["item_code"] == "_Test Item")
		self.assertFalse(res["can_see_cost"]); self.assertNotIn("cost", row)
	finally:
		frappe.set_user("Administrator")

def test_search_items_caps_and_flags_truncation(self):
	res = search_items(company="_Test Company", txt="%", limit=2)
	self.assertEqual(len(res["items"]), 2); self.assertTrue(res["truncated"])
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: `ImportError: cannot import name 'search_items'`.

- [ ] **Step 3: Implement `search_items`**

Approach: group filter = `{"item_group": ["in", frappe.get_descendants("Item Group", item_group) + [item_group]]}`; candidates from `item_query` (`limit + 1` rows → `truncated`); one `frappe.get_all("Item", ...)` for `item_group, stock_uom`; one `Bin` query over `item_code IN codes AND warehouse IN _permitted_warehouses(company)` selecting `item_code, warehouse, actual_qty, stock_value`; one `Item Price` query on the default selling list ordered by `valid_from desc nulls last`, keep the first row per item whose `valid_from <= today <= valid_upto` (NULL bounds pass); `cost = flt(sum(stock_value) / sum(actual_qty), 2)` when qty, else `None`; drop `cost` via `_strip_cost(items)`. Preserve `item_query`'s ordering.

- [ ] **Step 4: Run tests to verify they pass**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(transaction-history): search_items endpoint for the item picker"
```

---

### Task 4: `get_stock_card` endpoint

**Files:**
- Modify: `transaction_history.py` (new whitelisted function + private `_get_stock_card_rows`)
- Test: `test_transaction_history.py`

**Interfaces:**
- Produces:
  ```python
  @frappe.whitelist()
  def get_stock_card(item, company, from_date=None, to_date=None, warehouse=None) -> dict
  # {"can_see_cost": bool, "warehouses": [str], "single_warehouse": bool, "truncated": bool,
  #  "opening_qty": float, "opening_value"?: float, "closing_qty": float,
  #  "totals": {"qty_in": float, "qty_out": float},
  #  "rows": [{"posting_date", "posting_time", "voucher_type", "voucher_no", "party": str|None,
  #            "warehouse", "rate": float|None, "qty_in", "qty_out", "balance",
  #            "valuation_rate"?, "stock_value_difference"?, "value"?}]}
  ```
  Constants: `STOCK_CARD_LIMIT = 5000`; `PARTY_VOUCHERS = {"Sales Invoice": "customer", "Delivery Note": "customer", "POS Invoice": "customer", "Purchase Invoice": "supplier", "Purchase Receipt": "supplier"}`.
- Consumes: Task 1 `_can_see_cost`/`_strip_cost`; Task 2 `_warehouse_filter`/`_permitted_warehouses`.

Row rules (from spec): `rate` = child row `base_rate` (joined via `voucher_detail_no` to `f"{voucher_type} Item"`) for `PARTY_VOUCHERS`; for all other voucher types `rate` = `incoming_rate` (qty in) / `outgoing_rate` (qty out) **only if** `_can_see_cost()`, else `None`. `balance` = `qty_after_transaction` when `single_warehouse` (the scope list has exactly one warehouse) else `opening_qty + cumsum(actual_qty)`. `value` (gated) = `stock_value` when single, else `opening_value + cumsum(stock_value_difference)`. `opening_qty` = `SUM(actual_qty)` in scope with `posting_date < from_date` (0 when no `from_date`). Query excludes `is_cancelled = 1` and `docstatus = 2`, orders by `posting_datetime, creation`, fetches `STOCK_CARD_LIMIT + 1`.

- [ ] **Step 1: Write the failing tests**

```python
def test_stock_card_single_warehouse_balance_matches_ledger(self):
	from frappe.utils import add_days, today
	self._receipt(qty=10, rate=100, posting_date=add_days(today(), -10))
	from erpnext.accounts.doctype.sales_invoice.test_sales_invoice import create_sales_invoice
	create_sales_invoice(item_code="_Test Item", qty=3, rate=300, update_stock=1,
		warehouse="_Test Warehouse - _TC", company="_Test Company")
	d = get_stock_card(item="_Test Item", company="_Test Company", warehouse="_Test Warehouse - _TC")
	self.assertTrue(d["single_warehouse"])
	last = d["rows"][-1]
	self.assertEqual(last["voucher_type"], "Sales Invoice")
	self.assertEqual(last["qty_out"], 3); self.assertEqual(last["qty_in"], 0)
	self.assertEqual(last["rate"], 300); self.assertEqual(last["party"], "_Test Customer")
	bin_qty = frappe.db.get_value("Bin", {"item_code": "_Test Item", "warehouse": "_Test Warehouse - _TC"}, "actual_qty")
	self.assertEqual(last["balance"], flt(bin_qty, 2)); self.assertEqual(d["closing_qty"], flt(bin_qty, 2))
	self.assertIn("valuation_rate", last); self.assertIn("value", last)

def test_stock_card_multi_warehouse_running_balance_and_opening(self):
	from frappe.utils import add_days, today
	self._receipt(qty=10, warehouse="_Test Warehouse - _TC", posting_date=add_days(today(), -20))
	self._receipt(qty=5, warehouse="_Test Warehouse 1 - _TC", posting_date=add_days(today(), -2))
	d = get_stock_card(item="_Test Item", company="_Test Company", from_date=add_days(today(), -5))
	self.assertFalse(d["single_warehouse"])
	opening = frappe.db.sql("""select coalesce(sum(actual_qty),0) from `tabStock Ledger Entry`
		where item_code='_Test Item' and is_cancelled=0 and posting_date < %s""", add_days(today(), -5))[0][0]
	self.assertEqual(d["opening_qty"], flt(opening, 2))
	self.assertEqual(d["rows"][-1]["balance"], flt(opening, 2) + 5)
	self.assertEqual(d["totals"]["qty_in"], 5)

def test_stock_card_excludes_cancelled_entries(self):
	se = self._receipt(qty=7)
	se.cancel()
	d = get_stock_card(item="_Test Item", company="_Test Company", warehouse="_Test Warehouse - _TC")
	self.assertNotIn(se.name, [r["voucher_no"] for r in d["rows"]])

def test_stock_card_hides_cost_and_stock_entry_rate_for_cost_blind_user(self):
	self._receipt(qty=4, rate=50)
	frappe.set_user(self._as_cost_blind_user())
	try:
		d = get_stock_card(item="_Test Item", company="_Test Company", warehouse="_Test Warehouse - _TC")
		self.assertFalse(d["can_see_cost"]); self.assertNotIn("opening_value", d)
		se_row = next(r for r in d["rows"] if r["voucher_type"] == "Stock Entry")
		self.assertIsNone(se_row["rate"]); self.assertEqual(se_row["qty_in"], 4)
		for r in d["rows"]:
			for k in ("valuation_rate", "stock_value_difference", "value"):
				self.assertNotIn(k, r)
	finally:
		frappe.set_user("Administrator")
	d = get_stock_card(item="_Test Item", company="_Test Company", warehouse="_Test Warehouse - _TC")
	se_row = next(r for r in d["rows"] if r["voucher_type"] == "Stock Entry")
	self.assertEqual(se_row["rate"], 50)

def test_stock_card_respects_warehouse_user_permission(self):
	self._receipt(qty=10, warehouse="_Test Warehouse - _TC")
	self._receipt(qty=5, warehouse="_Test Warehouse 1 - _TC")
	frappe.set_user(self._as_warehouse_restricted_user())
	try:
		d = get_stock_card(item="_Test Item", company="_Test Company")
		self.assertEqual(set(r["warehouse"] for r in d["rows"]), {"_Test Warehouse - _TC"})
		self.assertTrue(d["single_warehouse"])
		d2 = get_stock_card(item="_Test Item", company="_Test Company", warehouse="_Test Warehouse 1 - _TC")
		self.assertEqual(d2["rows"], [])
	finally:
		frappe.set_user("Administrator")
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: `ImportError: cannot import name 'get_stock_card'`.

- [ ] **Step 3: Implement `get_stock_card`**

Scope: `whs = _warehouse_filter(company, warehouse)`; `if whs is None: whs = _permitted_warehouses(company)`; `if not whs: return` empty payload with `rows: []`. Party and rate lookups are batched per voucher type (`frappe.get_all(vt, {"name": ["in", ...]}, ["name", party_field])` and `frappe.get_all(f"{vt} Item", {"name": ["in", detail_nos]}, ["name", "base_rate"])`). Run `_strip_cost` on rows and pop `opening_value` from the payload when gated.

- [ ] **Step 4: Run tests to verify they pass**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(transaction-history): get_stock_card endpoint"
```

---

### Task 5: Items tab shell — picker dialog, chips, selector, view switch

**Files:**
- Modify: `transaction_history.js` — constructor L40–50, Items panel HTML L155–183, controls L281–296, `_render_item_checklist`/`_add_item_to_panel` L393–421, `_run_item_history`/`_render_item_tabs`/`_fill_item_tab` L455–537, handlers in `_bind_tabs` (`.btn-run-items` L877, `.item-tab-link` L888–896, `.item-results-search` L899–906, `.btn-toggle-item-panel` L960–973, `.item-checkbox`/`.btn-remove-item` L976–990, `.btn-clear-items` L993–998, `.ctrl-item-group`/`.ctrl-item-add` awesomplete blocks L1000–1055)

**Interfaces:**
- Produces (state): `this._item_panel = { items: [{item_code, item_name}], active: null, view: "history", can_see_cost: true, history: {}, card: {} }`.
- Produces (methods): `_open_item_picker()`, `_picker_search(dialog)`, `_render_picker_table($wrap, data)`, `_run_item_history()` (fetches `get_item_history` for every `items` entry into `history`, clears `card`, renders chips + nav, calls `_show_item(items[0].item_code)`), `_show_item(item_code)` (renders `history[item_code]` through the existing `_render_item_history` when `view === "history"`; when `view === "card"` calls `_load_stock_card(item_code)` from Task 6), `_render_item_nav()`.
- DOM hooks the next tasks rely on: `.btn-pick-items`, `.th-view-switch [data-view]`, `.item-chips .item-chip[data-item]`, `.item-select`, `.item-prev`, `.item-next`, `.item-results-search`, `.item-content`.
- Picker DOM: `.th-picker-search input`, `.th-picker-group`, `.th-picker-table`, row checkbox `.th-pick[data-item]`, header checkbox `.th-pick-all`, qty cell `.th-pick-wh[data-item][data-warehouse]` (warehouse attr empty on the collapsed `Stock` column), footer count `.th-pick-count`.
- Consumes: Task 3 `search_items`.

Behaviour pinned by the spec: dialog `size: "extra-large"`, title `__("Select Items")`; search debounced 300 ms, fires only when `txt.trim().length >= 2 || group`; selection is a `Map(item_code → {item_code,item_name})` kept across searches, pre-seeded from `this._item_panel.items`; primary action `__("Use selected ({0})")` sets `items` from the Map, hides the dialog, calls `_run_item_history()`; secondary `__("Clear")` empties the Map; warehouse columns = `data.warehouses` when `≤ 6`, else a single `Stock` column showing `total_qty` whose cell has `data-warehouse=""`; `Cost` column only when `data.can_see_cost`; footer note `__("Showing first {0} — refine your search", [100])` when `data.truncated`. Clicking a `.th-pick-wh` cell: `items = [that item]`, set `this.controls.item_warehouse` to `data-warehouse` when non-empty, `view = "card"`, hide dialog, `_run_item_history()`.

- [ ] **Step 1: Replace the Items panel HTML and state**

New panel markup inside `data-panel="item"`: filter bar (company, from, to, warehouse, `.btn-pick-items` primary button, `.th-view-switch` as a `btn-group` of two `btn btn-sm btn-default` buttons with `data-view="history"` (class `active`) and `data-view="card"`), then `<div class="item-chips">`, then `<div class="item-nav hidden">` containing `<select class="form-control form-control-sm item-select">`, `‹`/`›` buttons, and the existing `.item-results-search` input, then `<div class="th-content item-content">`. Delete the sidebar block, the `item_group`/`item_add` controls, the constructor's `_render_item_checklist()` call, and every handler listed in **Files** above.

- [ ] **Step 2: Implement the picker and run/show methods**

Signatures as in **Interfaces**. `_run_item_history` keeps the existing generation counter and `Loading…` placeholder pattern. `_render_item_nav` fills chips (`<span class="item-chip" data-item>code <a class="item-chip-x">×</a></span>`), the `<select>` (`code: name`), toggles `.item-nav` visibility on `items.length`, and marks the active chip. Removing a chip deletes from `items`/`history`/`card` and shows the next item (or clears `.item-content` when none remain).

- [ ] **Step 3: Bind the new handlers in `_bind_tabs`**

`.btn-pick-items` → `_open_item_picker()`; `.th-view-switch [data-view]` → set `view`, toggle `active`, `_show_item(active)`; `.item-select` change / `.item-prev` / `.item-next` / `.item-chip` click → `_show_item`; `.item-chip-x` → remove; `.item-results-search` now filters `tbody tr` under `.item-content`; the `.item-section-header` collapse handler is unchanged.

Mobile rules for this task (spec § Mobile): the picker table lives in a `<div style="overflow-x:auto">`; the checkbox and Item Code cells carry class `th-pick-sticky` (`position:sticky; left:0` with the table's background, checkbox at `left:0`, code at `left:<checkbox width>`); when `window.innerWidth < 768` at render time the warehouse columns collapse to the single `Stock` column regardless of count and the Group column is omitted; the search and group controls, the filter bar, the view switch, the chips and `.item-nav` wrap, and `.item-select` is `width:100%` below 768px (CSS in the existing `@media (max-width: 767px)` block in `_inject_styles`); `.item-chip`, `.item-prev`, `.item-next` and the view-switch buttons have `min-height:32px` below 768px.

- [ ] **Step 4: Verify in the browser (desktop)**

Open `http://dev.localhost:8000/app/transaction-history` as Administrator (Playwright MCP). Expected: no sidebar; "Select Items…" opens an extra-large dialog; typing `_Test` lists `_Test Item` rows with Sell Price, warehouse qty columns and Cost; choosing group `_Test Item Group` lists its items; ticking two items and "Use selected (2)" closes the dialog, shows two chips, the selector, and the History view for the first item; the selector and ‹ › switch items; removing a chip drops it. Console shows no errors.

- [ ] **Step 4b: Verify in the browser (mobile)**

`browser_resize` to 390×844 and reload. Expected: the picker opens full screen; search and group filter are stacked; the table shows ☐, Item Code, Item Name, UOM, Sell Price, Stock, Cost and scrolls sideways inside the dialog while the checkbox and code stay pinned; "Use selected (n)" is visible without horizontal scrolling; after confirming, chips wrap, the selector is full width, and `document.documentElement.scrollWidth <= window.innerWidth` (check with `browser_evaluate`).

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(transaction-history): item picker dialog and item navigator replace sidebar and tabs"
```

---

### Task 6: Stock Card view

**Files:**
- Modify: `transaction_history.js` — add `_load_stock_card(item_code)` and `_render_stock_card(data, $container)`; hook into `_show_item` from Task 5

**Interfaces:**
- Consumes: Task 4 `get_stock_card`; Task 5 state and `_show_item`.
- Produces: `_load_stock_card(item_code)` (uses `card[item_code]` if cached, else `frappe.call` with `item, company, from_date, to_date, warehouse` from the top controls, caches, renders); `_render_stock_card(data, $container)`.

Rendering pinned by the spec: a header line `__("Stock Card")` + item code/name; when `data.truncated` a `.alert.alert-warning` reading `__("Showing the first {0} entries; totals are incomplete. Narrow the date range.", [5000])`; table columns in order `#`, Date, Voucher (link `/app/<slug>/<voucher_no>` via `frappe.router.slug(voucher_type)`), Party, Warehouse (omit when `data.single_warehouse`), Rate, Qty In, Qty Out, Balance (bold), then Cost Rate / Value Change / Stock Value **only when** `data.can_see_cost`; an **Opening** first row (no voucher) when the request had `from_date`, showing `opening_qty` (and `opening_value` when present); `qty_out` cells in `var(--red)`; a footer row with `totals.qty_in`, `totals.qty_out`, `closing_qty`. Rows with `rate === null` render `—`. The existing `.item-results-search` filter applies because rows are `tbody tr` under `.item-content`.

Mobile rules for this task (spec § Mobile): the table lives in a `<div class="th-card-wrap" style="overflow-x:auto">`; Date and Voucher cells carry a sticky-left class (same technique as the picker's `th-pick-sticky`); column order is `#`, Date, Voucher, Party, Warehouse?, Rate, Qty In, Qty Out, Balance, then the cost columns, so Balance is the right-most non-cost column.

- [ ] **Step 1: Implement `_load_stock_card` and `_render_stock_card`**

Cache invalidation: `_run_item_history` already clears `card`, so changing any top filter and re-running (Task 5) refetches. A view-switch does not refetch.

- [ ] **Step 2: Verify in the browser**

As Administrator: pick `_Test Item`, switch to Stock Card. Expected: ledger rows with cost columns, Opening row when a From Date is set, balance equals the History view's Current Stock when no date filter. From the picker, click a warehouse qty cell: dialog closes, Warehouse filter shows that warehouse, Stock Card view is active, the Warehouse column is absent. Then log in as `rishit.test@dev.local` (Stock Operator + Sales User): same card has no Cost Rate / Value Change / Stock Value columns, Stock Entry rows show `—` under Rate, sales rows show their sale rate.

Mobile: `browser_resize` to 390×844 as Administrator with the Stock Card showing. Expected: the table scrolls sideways inside `.th-card-wrap` with Date and Voucher pinned, the page itself does not scroll horizontally (`document.documentElement.scrollWidth <= window.innerWidth`), the view switch buttons are tappable, and the Opening and footer rows stay aligned with their columns.

- [ ] **Step 3: Commit**

```bash
git commit -am "feat(transaction-history): stock card view"
```

---

### Task 7: Hide gated columns in existing renderers

**Files:**
- Modify: `transaction_history.js` — `_render_metrics_grid` L571–572, `_render_transaction_panel` L585–655 (rate column), `_render_party_summary` L765–840 (`avg_valuation_rate` column at L813/L836), `_render_detail_rows` L1500–1540 (L1537), `_render_pricing_tab` L2325–2452 (`avg_val_rate` L2329–2331, `p_rates` L2412, Val. Rate column L2437/L2448)

**Interfaces:**
- Consumes: payloads from Tasks 1–2 where cost keys may be absent; `this._item_panel.can_see_cost` set from `get_item_history().can_see_cost` in Task 5.

Rule for every renderer: a cost column (header **and** cells) is rendered only when `rows.some(r => key in r)` for row tables, or when the key is `!== undefined` for the metrics grid; `colspan` on empty rows adjusts accordingly. In `_render_pricing_tab`, `avg_val_rate` must be computed from `purchases.filter(r => r.valuation_rate != null)` and be `null` when that is empty, so the stat renders `—`.

- [ ] **Step 1: Apply the rule in the five renderers**

- [ ] **Step 2: Verify in the browser**

As Administrator: History view shows Stock Value, Avg. Rate and purchases' Val. Rate; Supplier tab shows Avg Val. Rate; Pricing tab shows Val. Rate and a numeric average. As `rishit.test@dev.local`: none of those columns appear, no `0.00` placeholders, no console errors, and the Pricing tab average reads `—`. Repeat the cost-blind History check at 390×844: the metrics grid stacks to one column and the purchases/sales panels stack, with no horizontal page scroll.

- [ ] **Step 3: Run the full test module once more**

Run: `bench --site dev.localhost run-tests --module cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.test_transaction_history`
Expected: all pass. Also `ruff check` and `ruff format --check` on the app, and `pre-commit run --files <the three files>`.

- [ ] **Step 4: Commit**

```bash
git commit -am "feat(transaction-history): hide cost columns when the payload omits them"
```

---

### Task 8: Spec/plan artifacts and branch finish

- [ ] **Step 1:** Copy the final spec and this plan into `~/frappe-bench/artifacts/superpowers/` (bench rule), `git add docs/superpowers/` in the app repo, commit `docs: transaction history item picker + stock card spec and plan`.
- [ ] **Step 2:** Invoke `superpowers:requesting-code-review`, then `superpowers:finishing-a-development-branch` (merge to `main`, push to `upstream/main` per the user's landing rules for this app only if that remote is configured; otherwise ask).
