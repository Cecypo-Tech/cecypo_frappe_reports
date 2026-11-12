# Party Statement Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One site-owned Client Script formats the party statement used by Copy to Clipboard, Email and a new Copy as Image, in Transaction History (cecypo_frappe_reports) and PowerPack's Customer Info dialog.

**Architecture:** cecypo_frappe_reports ships a default script file and seeds it as a Client Script when missing. Each app has a whitelisted getter that returns the script source. The browser runs that source with `new Function`, and the script registers `cecypo.party_statement = { columns, text(snap), image(snap) }`. Both apps normalise their dialog data into one `snap` shape and call `text` or `image`.

**Tech Stack:** Frappe v15/16 (Python, desk JS), Canvas 2D API, `ClipboardItem`, Node `--test` for the script's unit tests.

**Spec:** `docs/superpowers/specs/2026-11-03-party-statement-script-design.md`

## Global Constraints

- Client Script name `Party Statement - Copy and Email`, `dt = "Customer"`, `view = "Form"`, `module` empty, `enabled = 1`. The same string constant is used in both apps.
- Seeding creates the script only when no Client Script with that name exists. It never updates or re-enables one.
- Default columns, in order: Invoice Date, Invoice No., Total, Paid, Balance. Total, Paid and Balance are right-aligned.
- The image has the company name, party name, as-of date, the table and a "Total Outstanding" line. No logo, no greeting, no advances.
- Missing or disabled script: every action shows the toast `Statement script is missing or disabled: Client Script 'Party Statement - Copy and Email'` (orange) and copies or opens nothing.
- No new JS or Python dependencies. No server-side image rendering.
- Commits: no `Co-Authored-By` trailer (user rule).
- Work on branch `feat/party-statement-script` in both repos. File paths in each task are relative to that app's repo root (`~/frappe-bench/apps/<app>`).

## Review Focus

1. **A site edits the script badly, so it throws or doesn't register.** Show a red msgprint with the error text, and don't crash the dialog. → Task 3 / Task 4 manual check.
2. **A party with no outstanding invoices.** The text keeps today's "no outstanding invoices" line, and the image shows "No outstanding invoices" in place of the table. → Task 1 test.
3. **Missing values in a row** (`posting_date`, `paid` or `grand_total` null or undefined). Show a blank date and 0.00 amounts, never "undefined" or "NaN". → Task 1 test.
4. **The script runs on the Customer form,** because a Client Script is attached to its DocType. It must only register and not touch `frm`. → Task 1 test (load with no `frappe.ui.form`).
5. **The browser refuses to write the image to the clipboard** (Firefox before 127, or the tab losing focus). Download the PNG and show an orange toast, as `copy_as_image.js` does. → Task 3 manual check.

---

### Task 1: Default script and its Node tests (cecypo_frappe_reports)

**Files:**
- Create: `cecypo_frappe_reports/client_scripts/party_statement.js`
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/tests/js/party_statement.test.mjs`
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/tests/test_party_statement_js.py` (runs Node, same shape as `cecypo_powerpack/tests/test_profit_calculator_js.py`)

**Interfaces:**
- Produces: after `new Function(source)()`, the global `cecypo.party_statement` holds:
  - `columns: Array<{label: string, value: (row, snap) => string, align?: "left"|"right"}>`
  - `text(snap) => string`
  - `image(snap) => Promise<Blob>` (PNG)
- `snap` shape (spec, "One data shape"): `party_type` ("Customer"|"Supplier"), `party`, `party_name`, `company`, `as_of_date`, `currency`, `invoices[{name, posting_date, due_date, days_overdue, grand_total, paid, outstanding_amount}]`, `outstanding_total`, `overdue_count`, `overdue_total`, `advances[{name, posting_date, paid_amount, unallocated_amount}]`, `advances_total`, `net_position`, `payment_terms`, `credit_limit`.

- [ ] **Step 1: Write the failing tests.** In the `.mjs` file, stub `globalThis.frappe` (`provide`, `datetime.str_to_user` → identity), `__` (format `{0}`), `format_currency` (`(v,c)=>c+" "+Number(v).toFixed(2)`). Load the file with `new Function(src)()`. Tests:
  - `registers_without_form`: after load, `cecypo.party_statement.columns.map(c=>c.label)` deep-equals `["Invoice Date","Invoice No.","Total","Paid","Balance"]`, and no `frappe.ui` access throws.
  - `customer_text`: the text for a customer snap with 2 invoices starts with `"Dear ACME Ltd,"`, contains a header row whose labels appear in column order, contains each invoice name with its posting date on the same line, contains `"Total Outstanding: KES 300.00"`, and ends with `"Kindly arrange for payment at your earliest convenience."` when `overdue_count > 0` and `"Thank you for your business."` when it is 0.
  - `right_aligned_amounts`: in the text table, the Balance cell of each row ends at the same character column.
  - `advances_block`: with one advance, the text contains `"Unallocated payments on your account:"` and `"Net position: KES ..."`.
  - `supplier_text`: with `party_type: "Supplier"`, the text contains `"Our records show the following open bills on your account:"` and ends with `"Please let us know if your records differ."`.
  - `no_invoices`: the customer text contains `"Your account has no outstanding invoices."`.
  - `missing_values`: a row with `posting_date: null, paid: undefined` gives text with no `"undefined"`, `"NaN"` or `"null"`.

- [ ] **Step 2: Run and see them fail.** Run: `node --test cecypo_frappe_reports/cecypo_frappe_reports/tests/js/party_statement.test.mjs` from the app root. Expected: FAIL (file not found).

- [ ] **Step 3: Write `party_statement.js`.** Start with a header comment in the same voice as `cecypo_powerpack/client_scripts/copy_as_message_sales_invoice.js`: "This script belongs to your site… edit COLUMNS… delete it and migrate to get the shipped version back." Then an IIFE that does `frappe.provide("cecypo")` and assigns `cecypo.party_statement`. Put `COLUMNS` at the top. `text()` builds the text table by padding each column to the widest of its label and cells (padStart for right-aligned, padEnd for the rest), with a `-` separator line under the header. `image()` draws on an offscreen `<canvas>`:
  - Header lines: company in bold, then party name, then `As of <date>`.
  - The table, with column widths measured by `ctx.measureText`.
  - A `Total Outstanding: <money>` line.
  - Canvas width fits the widest content, at 2× scale for sharpness.
  - Resolve with `canvas.toBlob(..., "image/png")`.

- [ ] **Step 4: Run the tests and see them pass.** Same command. Expected: all pass.

- [ ] **Step 5: Add the Python wrapper and run it through bench.** Copy `TestProfitCalculatorJS` with `TEST_FILE` pointing at the new `.mjs`. Run: `cd ~/frappe-bench && bench --site dev.localhost run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.tests.test_party_statement_js`. Expected: OK.

- [ ] **Step 6: Commit.** `git add` the three files, then `git commit -m "feat(party-statement): default site script for statement text and image"`.

### Task 2: Seeding and getter (cecypo_frappe_reports)

**Files:**
- Create: `cecypo_frappe_reports/party_statement.py`
- Modify: `cecypo_frappe_reports/hooks.py` (around lines 113–114: add `after_install` and `after_migrate` lists, or append if a list exists)
- Test: `cecypo_frappe_reports/cecypo_frappe_reports/tests/test_party_statement.py`

**Interfaces:**
- Consumes: `client_scripts/party_statement.js` (Task 1).
- Produces:
  - `SCRIPT_NAME = "Party Statement - Copy and Email"`
  - `seed_client_script() -> None` (wired to `after_install` and `after_migrate`)
  - `@frappe.whitelist() get_party_statement_script(party_type: str = "Customer") -> str | None`. Method path: `cecypo_frappe_reports.party_statement.get_party_statement_script`.

- [ ] **Step 1: Write the failing tests** (`FrappeTestCase`; `setUp` deletes the script, `tearDown` rolls back):
  - `test_seed_creates_enabled_customer_form_script`: after `seed_client_script()`, the doc has `dt == "Customer"`, `view == "Form"`, `enabled == 1`, `not module`, and `script` equal to the shipped file's contents.
  - `test_seed_never_overwrites`: seed, set `script = "// mine"`, seed again, and the script is still `"// mine"`.
  - `test_seed_keeps_disabled`: seed, set `enabled = 0`, seed again, and it is still 0.
  - `test_getter_returns_source_when_enabled` and `test_getter_none_when_disabled` / `test_getter_none_when_missing`.
  - `test_getter_permission`: as a user without Sales Invoice read, `get_party_statement_script("Customer")` raises `frappe.PermissionError`. Purchase Invoice read is checked for `"Supplier"`.

- [ ] **Step 2: Run and see them fail.** Run: `bench --site dev.localhost run-tests --app cecypo_frappe_reports --module cecypo_frappe_reports.cecypo_frappe_reports.tests.test_party_statement`. Expected: ImportError.

- [ ] **Step 3: Implement `party_statement.py`.** Mirror `cecypo_powerpack/copy_as_message.py`: insert with `ignore_permissions=True, set_name=SCRIPT_NAME`, and give a docstring on why this isn't a fixture. The getter throws via `frappe.has_permission(..., throw=True)` on Sales Invoice, or on Purchase Invoice when `party_type.lower() == "supplier"`. It returns `frappe.db.get_value("Client Script", {"name": SCRIPT_NAME, "enabled": 1}, "script")`.

- [ ] **Step 4: Wire the hooks.** Add `after_install = ["cecypo_frappe_reports.party_statement.seed_client_script"]`, and the same for `after_migrate`.

- [ ] **Step 5: Run the tests and see them pass.** Same command. Expected: OK. Also run `test_hooks` to confirm nothing breaks: `--module cecypo_frappe_reports.cecypo_frappe_reports.tests.test_hooks`.

- [ ] **Step 6: Migrate dev and check.** Run `bench --site dev.localhost migrate` (start the workers first if they're not running; see the bench CLAUDE.md). Then the Client Script list shows `Party Statement - Copy and Email`, enabled.

- [ ] **Step 7: Commit.** `git commit -m "feat(party-statement): seed site script and expose it to desk"`.

### Task 3: Transaction History uses the script (cecypo_frappe_reports)

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/page/transaction_history/transaction_history.js`
  - `_show_party_info_dialog` (~2320–2400): buttons
  - `_party_snapshot_text`, `_copy_party_snapshot`, `_email_party_snapshot` (~2403–2438): replace
  - `_copy_party_text` (~2133) and its caller (~1600–1625): replace

**Interfaces:**
- Consumes: `get_party_statement_script` (Task 2) and `cecypo.party_statement` (Task 1).
- Produces (page-class methods):
  - `_statement() -> Promise<module>`. It fetches the source on every call, so edits apply without a reload. If the source is null, it shows the Global Constraints toast and rejects with a `silent` flag. If running the source throws, or `cecypo.party_statement` is missing afterwards, it shows a red msgprint with the error and rejects.
  - `_statement_snap(party_type, party, company, as_of_date, d) -> snap` maps the `get_party_details` payload. The mapping is: `voucher_no→name`, `date→posting_date`, `customer_name→party_name`, `party_type` capitalised, and `currency = this.base_currency`.
  - `_statement_copy_text(snap_promise)`, `_statement_copy_image(snap_promise, filename)`, `_statement_email(party_type, party, d, snap)`.

- [ ] **Step 1: Dialog buttons.** Copy to Clipboard calls `_statement_copy_text`. Add a custom action **Copy as Image** (`dialog.add_custom_action`, before Close) that calls `_statement_copy_image`. Email calls `_statement_email`, which keeps today's subject and puts `text(snap)` in the body. Delete `_party_snapshot_text`.

- [ ] **Step 2: Clipboard writes must start inside the click.** Text: `navigator.clipboard.write([new ClipboardItem({"text/plain": promise_of_text_blob})])`. Image: `new ClipboardItem({"image/png": promise_of_png})`. If the image write fails, download the PNG and show the orange toast `Could not copy the image, so it was downloaded instead`, the same as `cecypo_powerpack/public/js/copy_as_image.js`. If the text write fails, msgprint `Clipboard not available`. Rejections flagged `silent` show nothing more.

- [ ] **Step 3: Row "Copy text".** Replace the caller's cached-rows branch and the `_copy_party_text` body. On click, build a promise that calls `get_party_details` (party_type, party, company, as_of_date, plus show_future_payments from that tab's state), then `_statement_snap`, then `text()`. Hand it to `_statement_copy_text`. Leave `_copy_party_link` alone.

- [ ] **Step 4: Check by hand on dev** (`http://dev.localhost:8000/app/transaction-history`; page JS loads without a build, so hard-refresh). Check:
  - (a) Customer (i) dialog: Copy to Clipboard pastes the five-column table, matching the dialog's invoices.
  - (b) Email: the composer body has the same text.
  - (c) Copy as Image: the pasted PNG shows the company, customer, as-of date, table and total.
  - (d) Supplier dialog: the text uses the supplier wording.
  - (e) Row "Copy text" matches (a).
  - (f) Disable the script: all four show the orange toast.
  - (g) Make the script `throw new Error("x")`: you get a red msgprint with "x".
  - (h) Customer with no invoices: the image says "No outstanding invoices".
  - (i) Firefox, or dev tools with focus moved away during the click: the image downloads.
  Re-enable the script and restore it afterwards (delete it, then migrate).

- [ ] **Step 5: Commit.** `git commit -m "feat(transaction-history): statement copy/email/image from site script"`.

### Task 4: PowerPack Customer Info uses the script (cecypo_powerpack)

**Files:**
- Modify: `cecypo_powerpack/api.py` (add the getter)
- Modify: `cecypo_powerpack/public/js/cecypo_powerpack.js`, `CecypoPowerPack.CustomerInfo` (~518–710)
- Test: `cecypo_powerpack/tests/test_party_statement_script.py`

**Interfaces:**
- Produces: `@frappe.whitelist() cecypo_powerpack.api.get_party_statement_script() -> str | None`, with `PARTY_STATEMENT_SCRIPT = "Party Statement - Copy and Email"` in `api.py`. It checks Sales Invoice read with `throw=True`. PowerPack doesn't seed the script.
- `CustomerInfo.statement() -> Promise<module>`, with the same contract as Task 3's `_statement()`, toast and msgprint included. `CustomerInfo.snap(snap) -> snap` maps `customer→party`, `customer_name→party_name`, `party_type: "Customer"`, `company: <form company passed to open>`, `as_of_date: frappe.datetime.get_today()`. Invoices already use `name` and `posting_date`.

- [ ] **Step 1: Write the failing tests.**
  - `test_returns_source_when_enabled`: insert the Client Script with that name and `enabled=1`, and the getter returns its script.
  - `test_none_when_disabled_or_missing`.
  - `test_requires_sales_invoice_read`: raises `frappe.PermissionError` for a user without it.

- [ ] **Step 2: Run and see them fail.** Run: `bench --site dev.localhost run-tests --app cecypo_powerpack --module cecypo_powerpack.tests.test_party_statement_script`. Expected: AttributeError.

- [ ] **Step 3: Implement the getter.** Run the tests and see them pass.

- [ ] **Step 4: Rewire the JS.** `render()` keeps the company it was opened with: `open(customer, company)` passes it through to `render(snap, company)`, and `attach` → `render` passes `frm.doc.company`. Add **Copy as Image** with `d.add_custom_action` before Close. `copy`, `email` and the new `copy_image` go through `statement()`, with clipboard handling the same as Task 3 Step 2. Delete `build_text` and `_fallbackCopy`.

- [ ] **Step 5: Build and check by hand.** Run `cd ~/frappe-bench && bench build --app cecypo_powerpack`. On dev, open a Sales Invoice for a customer with outstanding invoices, go to Powerup → Customer Info (or the (i) icon), then re-run checks (a), (b), (c), (f) and (g) from Task 3. The pasted text must be identical to Transaction History's for the same customer and company.

- [ ] **Step 6: Commit.** `git commit -m "feat(customer-info): statement copy/email/image from site script"`.

### Task 5: Review and land

- [ ] **Step 1:** Run both apps' full suites for the touched modules. Check that no other session's tests are running (`ps -eo cmd | grep 'run-tests'`). Then run `bench --site dev.localhost run-tests --app cecypo_frappe_reports` and `bench --site dev.localhost run-tests --app cecypo_powerpack --module cecypo_powerpack.tests.test_customer_snapshot`.
- [ ] **Step 2:** `superpowers:requesting-code-review` on both branches. Save the review to `artifacts/superpowers/`.
- [ ] **Step 3:** `superpowers:finishing-a-development-branch`. Merge cecypo_powerpack into `main` and push to `upstream/main` (standing approval). cecypo_frappe_reports is **not** on the standing push list: merge locally, then ask the user before pushing to `upstream/main`. PowerPack's buttons show the toast until cecypo_frappe_reports seeds the script, so land both together.
