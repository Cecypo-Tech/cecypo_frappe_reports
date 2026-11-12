# Party statement: one site script for Copy, Email and Copy as Image

## Why

Two dialogs show a party's outstanding invoices and offer "Copy to Clipboard" and "Email":

- **cecypo_frappe_reports**, Transaction History page, party (i) dialog
  (`transaction_history.js`, `_party_snapshot_text` / `_copy_party_snapshot` /
  `_email_party_snapshot`). Opens for customers and suppliers.
- **cecypo_powerpack**, Customer Info dialog under Powerup on sales documents
  (`public/js/cecypo_powerpack.js`, `CecypoPowerPack.CustomerInfo.build_text` / `copy` / `email`).
  Customers only.

Both build the same text, hard-coded. Customers want different columns (some want due date,
some invoice date), and every change today needs a release of two apps. The text should
belong to the site, in one Client Script both dialogs use, the way PowerPack's
"Copy as Message" scripts already work (`cecypo_powerpack/copy_as_message.py`).

## Goals

1. One Client Script per site formats the statement for **both** dialogs.
2. All three actions use it: **Copy to Clipboard** (text), **Email** (same text into the
   composer), and a new **Copy as Image** (PNG of the table, to the clipboard, for WhatsApp).
3. Columns are a list at the top of the script. Changing a column changes the text, the email
   and the image together.
4. Default columns: **Invoice Date, Invoice No., Total, Paid, Balance**.
5. Image content: company name, party name, as-of date, the table, Total Outstanding line.
   No logo/letterhead, no greeting.
6. Script missing or disabled: each of the three buttons shows a toast
   ("Statement script is missing or disabled: Client Script '<name>'") and does nothing else.

## Non-goals

- No per-user or per-company variations beyond what the site writes into its script.
- No server-side rendering for the image; no new JS or Python dependency.
- No change to what the dialogs show on screen, or to the data endpoints' figures.
- PowerPack does not seed the script.

## Anti-goals

- An app update must never overwrite a site's edited script, or re-enable a disabled one.
- No silent fallback to the old hard-coded text when the script is missing: the toast is the
  signal that the site needs the script.

## Decided

- **Script name:** `Party Statement - Copy and Email` (constant in both apps). `dt = Customer`,
  `view = Form`, `module` empty (keeps it out of fixture exports). Found by this exact name,
  `enabled = 1`.
- **Seeding:** cecypo_frappe_reports creates it from a shipped file
  (`cecypo_frappe_reports/client_scripts/party_statement.js`) in `after_install` and
  `after_migrate`, only when no Client Script with that name exists. Deleting the script and
  migrating resets it to the shipped default. Same rule as `copy_as_message.seed_client_scripts`.
- **Who reads it:** each app has its own small whitelisted getter returning the script source
  (or None if missing/disabled), so PowerPack works without cecypo_frappe_reports installed
  (it just shows the toast unless someone created the script). Gate: read permission on
  Sales Invoice (or Purchase Invoice for suppliers) — the same gate as the dialog data.
- **How it runs:** the browser fetches the source, runs it with `new Function(source)()`, and
  the script registers `frappe.provide("cecypo.party_statement")` with:
  - `columns`: `[{ label, value(row, snap) → string, align: "left"|"right" }]`
  - `text(snap) → string`: greeting + text table built from `columns` + closing lines
  - `image(snap) → Promise<Blob>` (PNG): canvas-drawn header + table from `columns` + total
  Because the script also runs on the Customer form (dt = Customer), it must only register,
  never touch the form.
- **Drawing lives in the script** (my call). Apps only fetch, run, and call `text` / `image`.
  Trade-off: a fix to the shipped drawing code does not reach sites that already have the
  script; they get it by deleting the script and migrating.
- **One data shape** both apps pass in (`snap`), normalised from their current payloads:

  ```
  party_type   "Customer" | "Supplier"
  party, party_name, company, as_of_date, currency
  invoices:   [{ name, posting_date, due_date, days_overdue, grand_total, paid, outstanding_amount }]
  outstanding_total, overdue_count, overdue_total
  advances:   [{ name, posting_date, paid_amount, unallocated_amount }]
  advances_total, net_position, payment_terms, credit_limit
  ```

  Transaction History maps `voucher_no → name`, `date → posting_date`, `customer_name → party_name`.
  `company` / `as_of_date` come from the page controls; PowerPack uses the form's company and today.
- **Copy as Image** button sits next to Copy to Clipboard in both dialogs. Clipboard write
  uses `ClipboardItem` started inside the click (Safari), falling back to a download with an
  orange toast, as `copy_as_image.js` does.
- Email keeps today's subject; only the body comes from `text(snap)`.
- **Row-level "Copy text"** on the Receivables/Payables grids (`_copy_party_text`, ~line 2133)
  also goes through the script (user decision). The row only has raw detail rows, so on click
  it fetches `get_party_details` for that party/company/as-of and builds the same `snap`
  (my call: one data path, the row copy then matches the dialog exactly). The clipboard write
  is started inside the click with a `ClipboardItem` whose text is the pending promise, so
  Safari accepts it after the fetch. The row's "Copy internal link" button is unchanged.
- **Suppliers (user decision):** the default script branches on `snap.party_type`. Supplier
  wording: "Dear X," / "Our records show the following open bills on your account:" / table /
  "Total Outstanding" / closing "Please let us know if your records differ." Customer wording
  stays as today.
- **Default text content (my call):** same as today apart from the columns. It keeps the
  "Unallocated payments" block, the "Net position" line and the overdue-dependent closing,
  so no site's statement loses information. The image stays as listed in Goal 5 (no advances).

## Left to the builder

- Canvas layout details (fonts, padding, row striping, width fitting long names).
- Exact toast wording, button icon/label for Copy as Image.
- Caching the fetched script per page load vs. per click.
- Test shape: Python tests for seeding (idempotent, never overwrites, respects disabled) and the
  getters (missing/disabled → None, permission gate); JS checked by hand in both dialogs.
