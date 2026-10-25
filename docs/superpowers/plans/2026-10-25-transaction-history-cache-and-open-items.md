# Transaction History: Result Cache and Open-Item Handling — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve repeated Transaction History lookups from a short-lived server cache with a visible "fetched at" stamp and a Refresh control, and let the Items tab add items without refetching the ones already open, with a one-click Clear all.

**Architecture:** One helper in `transaction_history.py` wraps the six read endpoints with a Redis entry keyed by endpoint, filters and a permission fingerprint (roles + user permissions), TTL 10 minutes, bypassed by `refresh=1`; the fetch time rides back on `frappe.response`. In `transaction_history.js` every tab loader takes a `refresh` flag, each result bar gets a refresh icon plus stamp, and `_run_item_history` only fetches items that are not loaded when the filters are unchanged.

**Tech Stack:** Frappe v15 (`frappe.cache`, `frappe.response`), jQuery page script, `IntegrationTestCase`.

**Spec:** No written spec; design agreed in chat on 2026-10-25 (summarised in Global Constraints). Rulings go in the ledger.

## Global Constraints

- Cache key must include a permission fingerprint: a cost-blind user must never read a cost-visible user's payload. Fingerprint = sha1 of JSON `{"roles": sorted(frappe.get_roles()), "user_permissions": frappe.permissions.get_user_permissions(frappe.session.user)}` with `sort_keys=True, default=str`.
- TTL exactly `CACHE_TTL_SEC = 600`. No event-driven invalidation.
- Cached endpoints, and only these: `get_item_history`, `get_stock_card`, `get_customer_history`, `get_supplier_history`, `get_receivables`, `get_payables`. `get_item_prices`, `get_warehouse_stock`, `search_items`, `get_balance_basis`, details and `get_party_details` stay uncached (cheap, or mutable from this page).
- Existing `frappe.has_permission(..., throw=True)` checks stay before the cache lookup.
- Fetch time is returned as `frappe.response["th_fetched_at"]` (`frappe.utils.now()` string), never inside `message`, so list-shaped payloads keep their shape.
- Items tab: "Use selected" keeps loaded items untouched when `{company, from_date, to_date, warehouse}` is unchanged; any filter change or Refresh refetches everything as today. The dialog's Clear button is removed; a "Clear all" button sits next to the ‹ › arrows.
- No new dependencies; no asset build (page JS is served by `desk_page.getpage`). Python: tabs, double quotes, line ≤ 110. Never add `Co-Authored-By`.

## Review Focus

1. A user with fewer roles opening a customer another user just viewed must get their own payload (fingerprint differs). Pinned by `test_cache_scope_differs_between_users` (Task 1).
2. Same user, same filters, within TTL: second call must not recompute. Pinned by `test_cached_endpoint_serves_cache_until_refresh` (Task 1).
3. `refresh=1` must recompute and overwrite the entry. Same test.
4. Items tab: adding item B after A is loaded must send exactly one `get_item_history` (for B) and leave A's rendered content. Browser check in Task 4.
5. Items tab: unticking A in the dialog then "Use selected" must drop A's chip, history and card. Browser check in Task 4.

---

### Task 1: Server cache helper, wrapped endpoints, tests

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py`
- Test: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/test_transaction_history.py`

**Interfaces:**
- Produces: `CACHE_TTL_SEC: int = 600`; `_cache_scope() -> str`; `_cache_key(name: str, args: dict) -> str` (returns `f"th_page:{name}:{_cache_scope()}:{sha1 of json.dumps(args, sort_keys=True, default=str)}"`); `_cached(name: str, args: dict, refresh, compute: Callable[[], Any]) -> Any`; each of the six whitelisted endpoints gains a trailing keyword `refresh=0`.

- [ ] **Step 1: Write the failing tests** (append to the test class; import `_cache_key`, `_cache_scope`, `get_item_history` at module top)

```python
	def test_cached_endpoint_serves_cache_until_refresh(self):
		args = {"item": "__nonexistent__", "company": "_Test Company", "from_date": None, "to_date": None, "warehouse": None}
		first = get_item_history(**args)
		self.assertIn("item_details", first)
		self.assertTrue(frappe.response.get("th_fetched_at"))
		frappe.cache.set_value(_cache_key("item_history", args), {"data": {"sentinel": 1}, "at": "x"}, expires_in_sec=60)
		self.assertEqual(get_item_history(**args), {"sentinel": 1})
		self.assertEqual(frappe.response["th_fetched_at"], "x")
		self.assertIn("item_details", get_item_history(**args, refresh=1))
		self.assertNotEqual(frappe.response["th_fetched_at"], "x")

	def test_cache_scope_differs_between_users(self):
		admin_scope = _cache_scope()
		email = self._as_sales_only_user()
		frappe.set_user(email)
		try:
			self.assertNotEqual(_cache_scope(), admin_scope)
		finally:
			frappe.set_user("Administrator")

	def test_cache_key_differs_by_args(self):
		a = _cache_key("x", {"item": "A", "company": "_Test Company"})
		b = _cache_key("x", {"item": "B", "company": "_Test Company"})
		self.assertNotEqual(a, b)
		self.assertEqual(a, _cache_key("x", {"company": "_Test Company", "item": "A"}))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd ~/frappe-bench && bench --site dev.localhost run-tests --module cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.test_transaction_history --test test_cached_endpoint_serves_cache_until_refresh`
Expected: FAIL with ImportError on `_cache_key`.

- [ ] **Step 3: Implement the helper near the top of `transaction_history.py` (after the imports; add `import hashlib`, `import json`)**

`_cache_scope()` as in Global Constraints. `_cache_key(name, args)` as in Interfaces. `_cached(name, args, refresh, compute)`:
- `key = _cache_key(name, args)`
- if `not cint(refresh)`: `hit = frappe.cache.get_value(key, expires=True)`; on hit set `frappe.response["th_fetched_at"] = hit["at"]` and return `hit["data"]`
- else/miss: `data = compute()`, `at = now()`, `frappe.cache.set_value(key, {"data": data, "at": at}, expires_in_sec=CACHE_TTL_SEC)`, set the response stamp, return `data`.
Add `from frappe.utils import now` to the existing import line.

- [ ] **Step 4: Wrap the six endpoints**

For each, rename the existing body to a private function with the same parameters (`_item_history`, `_stock_card`, `_customer_history`, `_supplier_history`, `_receivables`, `_payables`) and make the whitelisted function a shim with the same parameters plus `refresh=0`:

```python
@frappe.whitelist()
def get_item_history(item, company, from_date=None, to_date=None, warehouse=None, refresh=0):
	args = {"item": item, "company": company, "from_date": from_date, "to_date": to_date, "warehouse": warehouse}
	return _cached("item_history", args, refresh, lambda: _item_history(**args))
```

`get_receivables`/`get_payables`: keep the `frappe.has_permission(..., throw=True)` line in the shim before `_cached`. `get_supplier_history` includes `source` in `args`. Cache names: `item_history`, `stock_card`, `customer_history`, `supplier_history`, `receivables`, `payables`.

- [ ] **Step 5: Run the whole module and ruff**

Run: `bench --site dev.localhost run-tests --module cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.test_transaction_history` and `ruff check cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/`
Expected: all tests OK (54), ruff clean for that directory.

- [ ] **Step 6: Commit**

```bash
git add cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.py cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/test_transaction_history.py
git commit -m "feat(transaction-history): cache read endpoints for 10 minutes, keyed by filters and permissions"
```

### Task 2: Refresh control and fetched-at stamp on every tab

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.js`

**Interfaces:**
- Consumes: `r.th_fetched_at` on every cached response; endpoint kwarg `refresh`.
- Produces: `_ICONS.refresh` (feather `refresh-cw`, 14px, same attributes as the other icons); `_refresh_btn(tab)` returning `<button type="button" class="th-action-btn btn-refresh-tab" data-tab="${tab}" title="${__("Reload from the database")}">${_ICONS.refresh}</button><span class="th-fetched-at text-muted" style="font-size:11px;margin-left:4px"></span>`; `_stamp($scope, at)` writing `__("fetched {0}", [frappe.datetime.comment_when(at, true)])` into the nearest `.th-fetched-at` inside `$scope` (no-op when `at` is empty); loaders `_load_customer_history(refresh = false)`, `_load_supplier_history(refresh = false)`, `_load_receivables(refresh = false)`, `_load_payables(refresh = false)`, `_run_pricing(refresh = false)`, `_run_item_history(refresh = false)`, `_fetch_item_history(item_code, gen, refresh = false)`, `_show_item(item_code, refresh = false)`, `_load_stock_card(item_code, refresh = false)`; each passes `refresh: refresh ? 1 : 0` in its `args`.

- [ ] **Step 1: Add the icon, `_refresh_btn`, `_stamp`, and the delegated handler** in `_bind_tabs` next to the export handler:

```js
$(m).on("click", ".btn-refresh-tab", (e) => {
	e.preventDefault();
	e.stopImmediatePropagation();
	const run = {
		items: () => this._run_item_history(true),
		customer: () => this._load_customer_history(true),
		supplier: () => this._load_supplier_history(true),
		receivables: () => this._load_receivables(true),
		payables: () => this._load_payables(true),
		pricing: () => this._run_pricing(true),
	}[$(e.currentTarget).attr("data-tab")];
	run && run();
});
```

- [ ] **Step 2: Place the control** — one per tab, beside the existing export icon or run button:
  - Items: inside `.item-nav` after the ‹ › buttons (`_refresh_btn("items")`).
  - Customer / Supplier summary: in `_render_party_summary` next to the export button (`_refresh_btn(party_type)`).
  - Receivables / Payables: next to their export buttons.
  - Pricing: in the pricing control bar next to `.btn-run-pricing`.

- [ ] **Step 3: Thread `refresh` through the loaders and stamp on success**
  - List payloads (customer, supplier, receivables, payables): call `this._stamp($content, r.th_fetched_at)` right after rendering.
  - Dict payloads: in `_fetch_item_history` callback set `r.message._fetched_at = r.th_fetched_at`; in `_load_stock_card` callback store `at: r.th_fetched_at` in the cache slot. `_show_item` (history branch) and `_paint_stock_card` call `this._stamp($(m).find(".item-nav"), <that value>)`.
  - `_run_item_history(refresh)`: full reset path passes `refresh` to `_fetch_item_history` and to `_show_item` (which forwards to `_load_stock_card`).
  - Pricing: `_run_pricing(refresh)` passes `refresh` to its `get_item_history` call; stamp the pricing control bar from the first response.

- [ ] **Step 4: Syntax check and commit**

Run: `node --check cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.js`
Expected: no output.

```bash
git add cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.js
git commit -m "feat(transaction-history): refresh control and fetched-at stamp on every tab"
```

### Task 3: Items tab keeps loaded items; Clear all replaces the dialog's Clear

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.js`

**Interfaces:**
- Consumes: `_run_item_history(refresh)`, `_fetch_item_history`, `p.args` (set per run), `p.history` (`undefined` = not requested, `null` = failed, object = loaded).
- Produces: `_clear_items()`; `.item-clear` button; `_run_item_history` partial path.

- [ ] **Step 1: Picker dialog** — delete `secondary_action_label` and `secondary_action`. In `primary_action`, after `this._item_panel.items = [...dialog._sel.values()]`, drop `p.history[code]` and `p.card[code]` for any code no longer in `p.items`, then `dialog.hide(); this._run_item_history();`.

- [ ] **Step 2: Partial run** — at the top of `_run_item_history(refresh = false)`, after computing `args = { company, from_date, to_date, warehouse }`:

```js
const unchanged = !refresh && p.args && JSON.stringify(args) === JSON.stringify(p.args);
if (unchanged) {
	const gen = this._run_generation;
	p.items.filter(it => !(it.item_code in p.history)).forEach(it => this._fetch_item_history(it.item_code, gen));
	this._show_item(p.items.some(i => i.item_code === p.active) ? p.active : p.items[0].item_code);
	return;
}
```
The existing full path (generation bump, `p.history = {}`, `p.card = {}`) follows unchanged.

- [ ] **Step 3: Clear all** — add after `.item-next` in the page HTML: `<button class="btn btn-sm btn-default item-clear" title="${__("Close all items")}">${__("Clear all")}</button>`; add `.item-clear` to the mobile `min-height` rule next to `.item-prev, .item-next`. Handler in `_bind_tabs`: `$(m).on("click", ".item-clear", () => this._clear_items());`.

```js
_clear_items() {
	const p = this._item_panel;
	this._run_generation = (this._run_generation || 0) + 1; // in-flight fetches become stale
	p.items = []; p.history = {}; p.card = {}; p.active = null; p.args = null;
	this._render_item_nav();
	$(this.page.main).find(".item-content").html(this._item_empty_html());
}
```

- [ ] **Step 4: Syntax check and commit**

Run: `node --check …/transaction_history.js` — Expected: no output.

```bash
git commit -am "feat(transaction-history): adding items keeps loaded ones; Clear all next to the item arrows"
```

### Task 4: Browser verification and landing

**Files:** none (verification only).

- [ ] **Step 1: Cache + stamp (as `th.admin@dev.local` / `thadmin123`, company `Dev Co`)**
  Customer tab for `TEST-CREDIT-ROUTER-CUSTOMER`: two consecutive loads return the same `th_fetched_at`; the stamp reads "fetched a few seconds ago"; Refresh produces a later stamp. Repeat once on Receivables and Items.
- [ ] **Step 2: Permission isolation** — as `rishit.test@dev.local` / `rishit123` immediately after step 1, Items tab for `F049`: no `cost` keys in the payload (`r.message.can_see_cost === false`).
- [ ] **Step 3: Open-item handling** — pick `F049`; then open the picker, tick `F050`, Use selected: exactly one `get_item_history` request (F050), F049 content untouched, both chips present; untick F049 in the picker, Use selected: F049 chip gone; Clear all: empty state, no chips; dialog shows no Clear button; warehouse cell click still triggers a full run.
- [ ] **Step 4: Mobile** — at 390px the `.item-nav` wraps and `Clear all` and the refresh icon are inside the viewport with no horizontal page scroll.
- [ ] **Step 5: Full module tests + ruff**, then `superpowers:requesting-code-review`, fix real findings, `superpowers:finishing-a-development-branch`: merge `--no-ff` into `main`, push `upstream/main` (user approved pushing this app's work on 2026-10-25).
