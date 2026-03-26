# PSOA Print Format Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create two Jinja Print Format records (GL + AR) for `Process Statement Of Accounts` in ERPNext v16, deployed as fixtures in `cecypo_frappe_reports`.

**Architecture:** Each Print Format is a standalone Jinja HTML fragment (no `<html>`/`<body>` tags — ERPNext wraps it in a base printview template). The HTML is stored in the `html` field of a Print Format fixture JSON. The Print Format must have `print_format_for = "Report"` and `report = "General Ledger"` or `"Accounts Receivable"` to pass ERPNext's validation. Both templates receive `filters`, `data`, `report`, `ageing`, `letter_head`, and `terms_and_conditions` as Jinja context — no `doc` variable is available.

**Tech Stack:** Jinja2 (Frappe-flavoured), ERPNext v16, frappe.db, frappe.utils, WeasyPrint/wkhtmltopdf PDF generation.

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `cecypo_frappe_reports/cecypo_frappe_reports/print_format/psoa_gl_statement/psoa_gl_statement.json` | GL Print Format fixture (HTML embedded) |
| Create | `cecypo_frappe_reports/cecypo_frappe_reports/print_format/psoa_ar_statement/psoa_ar_statement.json` | AR Print Format fixture (HTML embedded) |
| Modify | `cecypo_frappe_reports/cecypo_frappe_reports/hooks.py` | Register fixtures |

---

## Shared CSS

Both templates use the same CSS block. It is inlined in each template's `<style>` tag. Accent colour: `#1a56a0`.

```css
@page { size: A4 landscape; }

* { box-sizing: border-box; }

.stmt-wrapper { font-family: Arial, Helvetica, sans-serif; font-size: 8pt; color: #222; }

/* Fallback header (no letter_head) */
.fallback-header { width: 100%; border-collapse: collapse; margin-bottom: 4px; }
.fallback-header td { padding: 0; vertical-align: bottom; }
.fh-company { font-size: 14pt; font-weight: 700; line-height: 1.2; }
.fh-subtitle { font-size: 9pt; letter-spacing: 1.5px; text-transform: uppercase; color: #1a56a0; }
.fh-right { text-align: right; font-size: 7.5pt; color: #555; line-height: 1.6; }

.header-rule { border: none; border-top: 2px solid #1a56a0; margin: 4px 0 6px 0; }

/* Customer strip */
.cs-table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
.cs-table td { padding: 0 0 3px 0; vertical-align: top; border-bottom: 1px solid #ddd; }
.cs-name { font-size: 10pt; font-weight: 700; display: block; }
.cs-field { font-size: 7.5pt; color: #444; display: block; line-height: 1.4; }
.cs-right { text-align: right; }

/* Section headings */
.section-heading {
  font-size: 7.5pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;
  border-left: 3px solid #1a56a0; padding-left: 5px; margin-bottom: 4px; line-height: 1.3;
}

/* Main transactions table */
.stmt-table { width: 100%; border-collapse: collapse; font-size: 8pt; margin-bottom: 10px; }
.stmt-table thead tr { background-color: #1a56a0; color: #fff; }
.stmt-table th { padding: 3px 5px; text-align: left; font-weight: 600; white-space: nowrap; font-size: 7.5pt; }
.stmt-table td { padding: 2px 5px; border-bottom: 1px solid #e0e0e0; vertical-align: top; }
.stmt-table .row-even { background-color: #f8f8f8; }
.stmt-table tfoot .totals-row { background-color: #e8e8e8; }
.stmt-table tfoot .totals-row td { padding: 3px 5px; border-top: 1px solid #ccc; }

/* Utilities */
.text-right { text-align: right; white-space: nowrap; }
.text-center { text-align: center; }
.font-bold { font-weight: 700; }

/* Column widths */
.w-date { width: 68px; white-space: nowrap; }
.w-type { width: 105px; }
.w-days { width: 40px; }
.w-amt  { width: 90px; }
.w-bal  { width: 100px; }

/* CUIN / ETR sub-line */
.cuin-line { font-size: 6.5pt; color: #666; margin-top: 1px; }
.cuin-line a { color: #1a56a0; text-decoration: none; }

/* Bottom section */
.bottom-section { margin-top: 10px; overflow: hidden; page-break-inside: avoid; }
.bottom-section::after { content: ""; display: table; clear: both; }
.aging-container   { float: left;  width: 62%; padding-right: 12px; }
.future-container  { float: right; width: 36%; }

/* Sub-tables (aging, future payments) */
.sub-table { width: 100%; border-collapse: collapse; font-size: 7.5pt; }
.sub-table th { padding: 2px 4px; border-bottom: 1px solid #1a56a0; color: #1a56a0; font-size: 7pt; font-weight: 700; }
.sub-table td { padding: 2px 4px; border-bottom: 1px solid #ececec; }
.future-table th { color: #666; border-bottom-color: #999; }
.future-table td { color: #555; }

/* Terms */
.terms-section { margin-top: 10px; page-break-inside: avoid; border-top: 1px solid #ddd; padding-top: 6px; clear: both; }
.terms-text { font-size: 7pt; color: #555; line-height: 1.4; }
```

---

## Task 1: Scaffold directories and register fixtures in hooks.py

**Files:**
- Modify: `cecypo_frappe_reports/cecypo_frappe_reports/hooks.py`

- [ ] **Step 1.1: Create Print Format directories**

```bash
mkdir -p cecypo_frappe_reports/cecypo_frappe_reports/print_format/psoa_gl_statement
mkdir -p cecypo_frappe_reports/cecypo_frappe_reports/print_format/psoa_ar_statement
```

- [ ] **Step 1.2: Add fixtures entry to hooks.py**

Add this block near the top of `hooks.py`, after the `app_license` line:

```python
fixtures = [
	{
		"dt": "Print Format",
		"filters": [["name", "in", ["PSOA GL Statement", "PSOA AR Statement"]]],
	}
]
```

- [ ] **Step 1.3: Commit scaffold**

```bash
git add cecypo_frappe_reports/cecypo_frappe_reports/hooks.py \
        cecypo_frappe_reports/cecypo_frappe_reports/print_format/
git commit -m "feat: scaffold PSOA print format directories and fixtures entry"
```

---

## Task 2: GL Print Format

**Files:**
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/print_format/psoa_gl_statement/psoa_gl_statement.json`

The GL template renders a General Ledger statement with columns: Date | Type | Reference (+ optional CUIN sub-line) | Remarks* | Debit | Credit | Balance. The `*` means the Remarks column is only rendered when `filters.show_remarks` is truthy.

- [ ] **Step 2.1: Create the GL fixture JSON**

Create `cecypo_frappe_reports/cecypo_frappe_reports/print_format/psoa_gl_statement/psoa_gl_statement.json` with the following content. The `html` field contains the complete Jinja template:

```json
{
 "creation": "2026-03-26 00:00:00.000000",
 "css": "",
 "custom_format": 1,
 "disabled": 0,
 "doc_type": null,
 "docstatus": 0,
 "doctype": "Print Format",
 "html": "<!-- PSOA GL Statement — cecypo_frappe_reports -->\n<style>\n@page { size: A4 landscape; }\n* { box-sizing: border-box; }\n.stmt-wrapper { font-family: Arial, Helvetica, sans-serif; font-size: 8pt; color: #222; }\n.fallback-header { width: 100%; border-collapse: collapse; margin-bottom: 4px; }\n.fallback-header td { padding: 0; vertical-align: bottom; }\n.fh-company { font-size: 14pt; font-weight: 700; line-height: 1.2; }\n.fh-subtitle { font-size: 9pt; letter-spacing: 1.5px; text-transform: uppercase; color: #1a56a0; }\n.fh-right { text-align: right; font-size: 7.5pt; color: #555; line-height: 1.6; }\n.header-rule { border: none; border-top: 2px solid #1a56a0; margin: 4px 0 6px 0; }\n.cs-table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }\n.cs-table td { padding: 0 0 3px 0; vertical-align: top; border-bottom: 1px solid #ddd; }\n.cs-name { font-size: 10pt; font-weight: 700; display: block; }\n.cs-field { font-size: 7.5pt; color: #444; display: block; line-height: 1.4; }\n.cs-right { text-align: right; }\n.section-heading { font-size: 7.5pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; border-left: 3px solid #1a56a0; padding-left: 5px; margin-bottom: 4px; line-height: 1.3; }\n.stmt-table { width: 100%; border-collapse: collapse; font-size: 8pt; margin-bottom: 10px; }\n.stmt-table thead tr { background-color: #1a56a0; color: #fff; }\n.stmt-table th { padding: 3px 5px; text-align: left; font-weight: 600; white-space: nowrap; font-size: 7.5pt; }\n.stmt-table td { padding: 2px 5px; border-bottom: 1px solid #e0e0e0; vertical-align: top; }\n.stmt-table .row-even { background-color: #f8f8f8; }\n.stmt-table tfoot .totals-row { background-color: #e8e8e8; }\n.stmt-table tfoot .totals-row td { padding: 3px 5px; border-top: 1px solid #ccc; }\n.text-right { text-align: right; white-space: nowrap; }\n.font-bold { font-weight: 700; }\n.w-date { width: 68px; white-space: nowrap; }\n.w-type { width: 105px; }\n.w-amt { width: 90px; }\n.w-bal { width: 100px; }\n.cuin-line { font-size: 6.5pt; color: #666; margin-top: 1px; }\n.cuin-line a { color: #1a56a0; text-decoration: none; }\n.bottom-section { margin-top: 10px; overflow: hidden; page-break-inside: avoid; }\n.bottom-section::after { content: \"\"; display: table; clear: both; }\n.aging-container { float: left; width: 62%; padding-right: 12px; }\n.future-container { float: right; width: 36%; }\n.sub-table { width: 100%; border-collapse: collapse; font-size: 7.5pt; }\n.sub-table th { padding: 2px 4px; border-bottom: 1px solid #1a56a0; color: #1a56a0; font-size: 7pt; font-weight: 700; }\n.sub-table td { padding: 2px 4px; border-bottom: 1px solid #ececec; }\n.future-table th { color: #666; border-bottom-color: #999; }\n.future-table td { color: #555; }\n.terms-section { margin-top: 10px; page-break-inside: avoid; border-top: 1px solid #ddd; padding-top: 6px; clear: both; }\n.terms-text { font-size: 7pt; color: #555; line-height: 1.4; }\n</style>\n\n{%- set company   = filters.get(\"company\") -%}\n{%- set party     = filters.get(\"party\") -%}\n{%- set from_date = filters.get(\"from_date\") -%}\n{%- set to_date   = filters.get(\"to_date\") -%}\n{%- set currency  = filters.get(\"presentation_currency\") or filters.get(\"currency\") or frappe.db.get_value(\"Company\", company, \"default_currency\") -%}\n{%- set show_rem  = filters.get(\"show_remarks\") -%}\n\n{%- set cust = frappe.db.get_value(\"Customer\", party, [\"customer_name\", \"tax_id\"], as_dict=True) or frappe._dict() -%}\n\n{%- set addr_links = frappe.db.get_all(\"Dynamic Link\", filters={\"link_doctype\": \"Customer\", \"link_name\": party, \"parenttype\": \"Address\"}, fields=[\"parent\"], limit=1) -%}\n{%- set address_line = \"\" -%}\n{%- if addr_links -%}\n  {%- set a = frappe.db.get_value(\"Address\", addr_links[0].parent, [\"address_line1\", \"city\", \"country\"], as_dict=True) or frappe._dict() -%}\n  {%- set parts = [] -%}\n  {%- if a.address_line1 %}{%- set _ = parts.append(a.address_line1) %}{%- endif -%}\n  {%- if a.city %}{%- set _ = parts.append(a.city) %}{%- endif -%}\n  {%- if a.country %}{%- set _ = parts.append(a.country) %}{%- endif -%}\n  {%- set address_line = parts | join(\", \") -%}\n{%- endif -%}\n\n{%- set cont_links = frappe.db.get_all(\"Dynamic Link\", filters={\"link_doctype\": \"Customer\", \"link_name\": party, \"parenttype\": \"Contact\"}, fields=[\"parent\"], limit=1) -%}\n{%- set c_phone = \"\" -%}\n{%- set c_email = \"\" -%}\n{%- if cont_links -%}\n  {%- set c = frappe.db.get_value(\"Contact\", cont_links[0].parent, [\"phone\", \"email_id\"], as_dict=True) or frappe._dict() -%}\n  {%- set c_phone = c.phone or \"\" -%}\n  {%- set c_email = c.email_id or \"\" -%}\n{%- endif -%}\n\n{%- set has_etr = frappe.get_meta(\"Sales Invoice\").has_field(\"etr_invoice_number\") and frappe.get_meta(\"Sales Invoice\").has_field(\"cu_link\") -%}\n\n{%- set ns = namespace(t_debit=0, t_credit=0) -%}\n{%- for row in data -%}\n  {%- set ns.t_debit  = ns.t_debit  + (row.get(\"debit\")  or 0) -%}\n  {%- set ns.t_credit = ns.t_credit + (row.get(\"credit\") or 0) -%}\n{%- endfor -%}\n\n{%- set future_rows = [] -%}\n{%- for row in data -%}\n  {%- if row.get(\"posting_date\") and to_date and row.get(\"posting_date\") > to_date -%}\n    {%- set _ = future_rows.append(row) -%}\n  {%- endif -%}\n{%- endfor -%}\n\n<div class=\"stmt-wrapper\">\n\n{%- if letter_head -%}\n<div style=\"margin-bottom:4px;\">{{ letter_head }}</div>\n{%- else -%}\n<table class=\"fallback-header\">\n  <tr>\n    <td>\n      <div class=\"fh-company\">{{ company }}</div>\n      <div class=\"fh-subtitle\">Statement of Account</div>\n    </td>\n    <td class=\"fh-right\">\n      Period: {{ frappe.utils.formatdate(from_date) }} &ndash; {{ frappe.utils.formatdate(to_date) }}<br>\n      Printed: {{ frappe.utils.formatdate(frappe.utils.today()) }}\n    </td>\n  </tr>\n</table>\n{%- endif -%}\n<hr class=\"header-rule\">\n\n<table class=\"cs-table\">\n  <tr>\n    <td style=\"width:55%;\">\n      <span class=\"cs-name\">{{ cust.customer_name or party }}</span>\n      {%- if cust.tax_id -%}<span class=\"cs-field\">Tax ID: {{ cust.tax_id }}</span>{%- endif -%}\n      {%- if address_line -%}<span class=\"cs-field\">{{ address_line }}</span>{%- endif -%}\n    </td>\n    <td style=\"width:45%;\" class=\"cs-right\">\n      {%- if c_phone -%}<span class=\"cs-field\">Tel: {{ c_phone }}</span>{%- endif -%}\n      {%- if c_email -%}<span class=\"cs-field\">{{ c_email }}</span>{%- endif -%}\n      <span class=\"cs-field\">Currency: {{ currency }}</span>\n    </td>\n  </tr>\n</table>\n\n<table class=\"stmt-table\">\n  <thead>\n    <tr>\n      <th class=\"w-date\">Date</th>\n      <th class=\"w-type\">Type</th>\n      <th>Reference</th>\n      {%- if show_rem -%}<th>Remarks</th>{%- endif -%}\n      <th class=\"w-amt text-right\">Debit</th>\n      <th class=\"w-amt text-right\">Credit</th>\n      <th class=\"w-bal text-right\">Balance</th>\n    </tr>\n  </thead>\n  <tbody>\n    {%- for row in data -%}\n    <tr{%- if loop.index is even %} class=\"row-even\"{%- endif -%}>\n      <td>{{ frappe.utils.formatdate(row.get(\"posting_date\")) }}</td>\n      <td>{{ row.get(\"voucher_type\") or \"\" }}</td>\n      <td>\n        {{ row.get(\"voucher_no\") or \"\" }}\n        {%- if has_etr and row.get(\"voucher_type\") == \"Sales Invoice\" -%}\n          {%- set etr = frappe.db.get_value(\"Sales Invoice\", row.get(\"voucher_no\"), [\"etr_invoice_number\", \"cu_link\"], as_dict=True) -%}\n          {%- if etr and etr.etr_invoice_number -%}\n          <div class=\"cuin-line\">CUIN: <a href=\"{{ etr.cu_link }}\" target=\"_blank\">{{ etr.etr_invoice_number }}</a></div>\n          {%- endif -%}\n        {%- endif -%}\n      </td>\n      {%- if show_rem -%}<td>{{ row.get(\"remarks\") or \"\" }}</td>{%- endif -%}\n      <td class=\"text-right\">{{ frappe.utils.fmt_money(row.get(\"debit\") or 0, currency=currency) }}</td>\n      <td class=\"text-right\">{{ frappe.utils.fmt_money(row.get(\"credit\") or 0, currency=currency) }}</td>\n      <td class=\"text-right font-bold\">{{ frappe.utils.fmt_money(row.get(\"balance\") or 0, currency=currency) }}</td>\n    </tr>\n    {%- endfor -%}\n  </tbody>\n  <tfoot>\n    <tr class=\"totals-row\">\n      <td colspan=\"{{ 3 + (1 if show_rem else 0) }}\" class=\"font-bold\">Total</td>\n      <td class=\"text-right font-bold\">{{ frappe.utils.fmt_money(ns.t_debit, currency=currency) }}</td>\n      <td class=\"text-right font-bold\">{{ frappe.utils.fmt_money(ns.t_credit, currency=currency) }}</td>\n      <td></td>\n    </tr>\n  </tfoot>\n</table>\n\n<div class=\"bottom-section\">\n  {%- if ageing -%}\n  <div class=\"aging-container\">\n    <div class=\"section-heading\">Aging Summary</div>\n    <table class=\"sub-table\">\n      <thead>\n        <tr>\n          <th>0&ndash;30</th><th>31&ndash;60</th><th>61&ndash;90</th><th>91&ndash;120</th><th>120+</th><th class=\"text-right\">Total</th>\n        </tr>\n      </thead>\n      <tbody>\n        <tr>\n          {%- set ag_total = (ageing.range1 or 0)+(ageing.range2 or 0)+(ageing.range3 or 0)+(ageing.range4 or 0)+(ageing.range5 or 0) -%}\n          <td>{{ frappe.utils.fmt_money(ageing.range1 or 0, currency=currency) }}</td>\n          <td>{{ frappe.utils.fmt_money(ageing.range2 or 0, currency=currency) }}</td>\n          <td>{{ frappe.utils.fmt_money(ageing.range3 or 0, currency=currency) }}</td>\n          <td>{{ frappe.utils.fmt_money(ageing.range4 or 0, currency=currency) }}</td>\n          <td>{{ frappe.utils.fmt_money(ageing.range5 or 0, currency=currency) }}</td>\n          <td class=\"text-right font-bold\">{{ frappe.utils.fmt_money(ag_total, currency=currency) }}</td>\n        </tr>\n      </tbody>\n    </table>\n  </div>\n  {%- endif -%}\n\n  {%- if future_rows -%}\n  <div class=\"future-container\">\n    <div class=\"section-heading\">Future Payments</div>\n    <table class=\"sub-table future-table\">\n      <thead>\n        <tr><th>Date</th><th>Type</th><th>Reference</th><th class=\"text-right\">Amount</th></tr>\n      </thead>\n      <tbody>\n        {%- for row in future_rows -%}\n        <tr>\n          <td>{{ frappe.utils.formatdate(row.get(\"posting_date\")) }}</td>\n          <td>{{ row.get(\"voucher_type\") or \"\" }}</td>\n          <td>{{ row.get(\"voucher_no\") or \"\" }}</td>\n          <td class=\"text-right\">{{ frappe.utils.fmt_money(row.get(\"credit\") or 0, currency=currency) }}</td>\n        </tr>\n        {%- endfor -%}\n      </tbody>\n    </table>\n  </div>\n  {%- endif -%}\n</div>\n\n{%- if terms_and_conditions -%}\n<div class=\"terms-section\">\n  <div class=\"section-heading\">Terms &amp; Conditions</div>\n  <div class=\"terms-text\">{{ terms_and_conditions }}</div>\n</div>\n{%- endif -%}\n\n</div>",
 "idx": 0,
 "line_breaks": 0,
 "modified": "2026-03-26 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Cecypo Frappe Reports",
 "name": "PSOA GL Statement",
 "owner": "Administrator",
 "page_number": "Bottom Right",
 "print_format_for": "Report",
 "print_format_type": "Jinja",
 "report": "General Ledger",
 "standard": "No"
}
```

- [ ] **Step 2.2: Load into site and verify it is accepted**

```bash
cd /home/frappeuser/bench16
bench --site site16.local migrate
```

Expected: migration completes without error. No output about Print Format is normal.

- [ ] **Step 2.3: Verify the Print Format exists on the site**

```bash
bench --site site16.local execute frappe.db.get_value --args "['Print Format', 'PSOA GL Statement', ['print_format_for', 'report', 'print_format_type']]"
```

Expected output: `['Report', 'General Ledger', 'Jinja']`

If `bench execute` fails, use the console instead:
```bash
bench --site site16.local console
# then type:
frappe.db.get_value("Print Format", "PSOA GL Statement", ["print_format_for", "report", "print_format_type"])
```

If the record doesn't exist yet (fixture not auto-loaded on migrate), import it manually:

```bash
bench --site site16.local import-doc cecypo_frappe_reports/cecypo_frappe_reports/print_format/psoa_gl_statement/psoa_gl_statement.json
```

- [ ] **Step 2.4: Visual verification**

1. Open `site16.local:8002` in a browser
2. Go to Accounts → Process Statement Of Accounts → open any existing doc set to **General Ledger** report
3. Set `Print Format` = `PSOA GL Statement`
4. Click **Preview** — confirm the statement renders without a Jinja error
5. Check: header present, customer strip shows, table rows render, amounts formatted with currency, no empty columns for Remarks when not enabled

- [ ] **Step 2.5: Commit GL template**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports
git add cecypo_frappe_reports/cecypo_frappe_reports/print_format/psoa_gl_statement/
git commit -m "feat: add PSOA GL Statement print format (Jinja, landscape A4)"
```

---

## Task 3: AR Print Format

**Files:**
- Create: `cecypo_frappe_reports/cecypo_frappe_reports/print_format/psoa_ar_statement/psoa_ar_statement.json`

The AR template renders an Accounts Receivable statement with columns: Date | Days | Type | Reference (+ optional CUIN sub-line) | Invoiced | Paid | Credit Note | Outstanding. Rows with `future_ref` set are treated as future payment rows and shown only in the Future Payments section at the bottom, not in the main table.

**Note on AR future payment fields:** The ERPNext AR report attaches future payment data as columns on each row — not as separate rows. The relevant fields are: `future_ref` (reference doc name), `future_amount`, `remaining_balance`. These come through when `show_future_payments` is enabled on the PSOA doc. If `future_ref` is null/empty for a row, it has no future payment data.

- [ ] **Step 3.1: Create the AR fixture JSON**

Create `cecypo_frappe_reports/cecypo_frappe_reports/print_format/psoa_ar_statement/psoa_ar_statement.json`:

```json
{
 "creation": "2026-03-26 00:00:00.000000",
 "css": "",
 "custom_format": 1,
 "disabled": 0,
 "doc_type": null,
 "docstatus": 0,
 "doctype": "Print Format",
 "html": "<!-- PSOA AR Statement — cecypo_frappe_reports -->\n<style>\n@page { size: A4 landscape; }\n* { box-sizing: border-box; }\n.stmt-wrapper { font-family: Arial, Helvetica, sans-serif; font-size: 8pt; color: #222; }\n.fallback-header { width: 100%; border-collapse: collapse; margin-bottom: 4px; }\n.fallback-header td { padding: 0; vertical-align: bottom; }\n.fh-company { font-size: 14pt; font-weight: 700; line-height: 1.2; }\n.fh-subtitle { font-size: 9pt; letter-spacing: 1.5px; text-transform: uppercase; color: #1a56a0; }\n.fh-right { text-align: right; font-size: 7.5pt; color: #555; line-height: 1.6; }\n.header-rule { border: none; border-top: 2px solid #1a56a0; margin: 4px 0 6px 0; }\n.cs-table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }\n.cs-table td { padding: 0 0 3px 0; vertical-align: top; border-bottom: 1px solid #ddd; }\n.cs-name { font-size: 10pt; font-weight: 700; display: block; }\n.cs-field { font-size: 7.5pt; color: #444; display: block; line-height: 1.4; }\n.cs-right { text-align: right; }\n.section-heading { font-size: 7.5pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; border-left: 3px solid #1a56a0; padding-left: 5px; margin-bottom: 4px; line-height: 1.3; }\n.stmt-table { width: 100%; border-collapse: collapse; font-size: 8pt; margin-bottom: 10px; }\n.stmt-table thead tr { background-color: #1a56a0; color: #fff; }\n.stmt-table th { padding: 3px 5px; text-align: left; font-weight: 600; white-space: nowrap; font-size: 7.5pt; }\n.stmt-table td { padding: 2px 5px; border-bottom: 1px solid #e0e0e0; vertical-align: top; }\n.stmt-table .row-even { background-color: #f8f8f8; }\n.stmt-table tfoot .totals-row { background-color: #e8e8e8; }\n.stmt-table tfoot .totals-row td { padding: 3px 5px; border-top: 1px solid #ccc; }\n.text-right { text-align: right; white-space: nowrap; }\n.text-center { text-align: center; }\n.font-bold { font-weight: 700; }\n.w-date { width: 68px; white-space: nowrap; }\n.w-type { width: 105px; }\n.w-days { width: 40px; }\n.w-amt  { width: 90px; }\n.w-bal  { width: 100px; }\n.cuin-line { font-size: 6.5pt; color: #666; margin-top: 1px; }\n.cuin-line a { color: #1a56a0; text-decoration: none; }\n.bottom-section { margin-top: 10px; overflow: hidden; page-break-inside: avoid; }\n.bottom-section::after { content: \"\"; display: table; clear: both; }\n.aging-container { float: left; width: 62%; padding-right: 12px; }\n.future-container { float: right; width: 36%; }\n.sub-table { width: 100%; border-collapse: collapse; font-size: 7.5pt; }\n.sub-table th { padding: 2px 4px; border-bottom: 1px solid #1a56a0; color: #1a56a0; font-size: 7pt; font-weight: 700; }\n.sub-table td { padding: 2px 4px; border-bottom: 1px solid #ececec; }\n.future-table th { color: #666; border-bottom-color: #999; }\n.future-table td { color: #555; }\n.terms-section { margin-top: 10px; page-break-inside: avoid; border-top: 1px solid #ddd; padding-top: 6px; clear: both; }\n.terms-text { font-size: 7pt; color: #555; line-height: 1.4; }\n</style>\n\n{%- set company   = filters.get(\"company\") -%}\n{%- set party     = filters.get(\"party\") -%}\n{%- set from_date = filters.get(\"from_date\") -%}\n{%- set to_date   = filters.get(\"to_date\") -%}\n{%- set currency  = filters.get(\"presentation_currency\") or filters.get(\"currency\") or frappe.db.get_value(\"Company\", company, \"default_currency\") -%}\n\n{%- set cust = frappe.db.get_value(\"Customer\", party, [\"customer_name\", \"tax_id\"], as_dict=True) or frappe._dict() -%}\n\n{%- set addr_links = frappe.db.get_all(\"Dynamic Link\", filters={\"link_doctype\": \"Customer\", \"link_name\": party, \"parenttype\": \"Address\"}, fields=[\"parent\"], limit=1) -%}\n{%- set address_line = \"\" -%}\n{%- if addr_links -%}\n  {%- set a = frappe.db.get_value(\"Address\", addr_links[0].parent, [\"address_line1\", \"city\", \"country\"], as_dict=True) or frappe._dict() -%}\n  {%- set parts = [] -%}\n  {%- if a.address_line1 %}{%- set _ = parts.append(a.address_line1) %}{%- endif -%}\n  {%- if a.city %}{%- set _ = parts.append(a.city) %}{%- endif -%}\n  {%- if a.country %}{%- set _ = parts.append(a.country) %}{%- endif -%}\n  {%- set address_line = parts | join(\", \") -%}\n{%- endif -%}\n\n{%- set cont_links = frappe.db.get_all(\"Dynamic Link\", filters={\"link_doctype\": \"Customer\", \"link_name\": party, \"parenttype\": \"Contact\"}, fields=[\"parent\"], limit=1) -%}\n{%- set c_phone = \"\" -%}\n{%- set c_email = \"\" -%}\n{%- if cont_links -%}\n  {%- set c = frappe.db.get_value(\"Contact\", cont_links[0].parent, [\"phone\", \"email_id\"], as_dict=True) or frappe._dict() -%}\n  {%- set c_phone = c.phone or \"\" -%}\n  {%- set c_email = c.email_id or \"\" -%}\n{%- endif -%}\n\n{%- set has_etr = frappe.get_meta(\"Sales Invoice\").has_field(\"etr_invoice_number\") and frappe.get_meta(\"Sales Invoice\").has_field(\"cu_link\") -%}\n\n{%- set ns = namespace(t_invoiced=0, t_paid=0, t_credit=0, t_outstanding=0) -%}\n{%- set future_rows = [] -%}\n{%- for row in data -%}\n  {%- if row.get(\"future_ref\") -%}\n    {%- set _ = future_rows.append(row) -%}\n  {%- else -%}\n    {%- set ns.t_invoiced    = ns.t_invoiced    + (row.get(\"invoiced\")   or 0) -%}\n    {%- set ns.t_paid        = ns.t_paid        + (row.get(\"paid\")        or 0) -%}\n    {%- set ns.t_credit      = ns.t_credit      + (row.get(\"credit_note\") or 0) -%}\n    {%- set ns.t_outstanding = ns.t_outstanding + (row.get(\"outstanding\") or 0) -%}\n  {%- endif -%}\n{%- endfor -%}\n\n<div class=\"stmt-wrapper\">\n\n{%- if letter_head -%}\n<div style=\"margin-bottom:4px;\">{{ letter_head }}</div>\n{%- else -%}\n<table class=\"fallback-header\">\n  <tr>\n    <td>\n      <div class=\"fh-company\">{{ company }}</div>\n      <div class=\"fh-subtitle\">Statement of Account</div>\n    </td>\n    <td class=\"fh-right\">\n      Period: {{ frappe.utils.formatdate(from_date) }} &ndash; {{ frappe.utils.formatdate(to_date) }}<br>\n      Printed: {{ frappe.utils.formatdate(frappe.utils.today()) }}\n    </td>\n  </tr>\n</table>\n{%- endif -%}\n<hr class=\"header-rule\">\n\n<table class=\"cs-table\">\n  <tr>\n    <td style=\"width:55%;\">\n      <span class=\"cs-name\">{{ cust.customer_name or party }}</span>\n      {%- if cust.tax_id -%}<span class=\"cs-field\">Tax ID: {{ cust.tax_id }}</span>{%- endif -%}\n      {%- if address_line -%}<span class=\"cs-field\">{{ address_line }}</span>{%- endif -%}\n    </td>\n    <td style=\"width:45%;\" class=\"cs-right\">\n      {%- if c_phone -%}<span class=\"cs-field\">Tel: {{ c_phone }}</span>{%- endif -%}\n      {%- if c_email -%}<span class=\"cs-field\">{{ c_email }}</span>{%- endif -%}\n      <span class=\"cs-field\">Currency: {{ currency }}</span>\n    </td>\n  </tr>\n</table>\n\n<table class=\"stmt-table\">\n  <thead>\n    <tr>\n      <th class=\"w-date\">Date</th>\n      <th class=\"w-days text-center\">Days</th>\n      <th class=\"w-type\">Type</th>\n      <th>Reference</th>\n      <th class=\"w-amt text-right\">Invoiced</th>\n      <th class=\"w-amt text-right\">Paid</th>\n      <th class=\"w-amt text-right\">Credit Note</th>\n      <th class=\"w-bal text-right\">Outstanding</th>\n    </tr>\n  </thead>\n  <tbody>\n    {%- for row in data -%}\n    {%- if not row.get(\"future_ref\") -%}\n    <tr{%- if loop.index is even %} class=\"row-even\"{%- endif -%}>\n      <td>{{ frappe.utils.formatdate(row.get(\"posting_date\")) }}</td>\n      <td class=\"text-center\">{{ row.get(\"age\") or \"\" }}</td>\n      <td>{{ row.get(\"voucher_type\") or \"\" }}</td>\n      <td>\n        {{ row.get(\"voucher_no\") or \"\" }}\n        {%- if has_etr and row.get(\"voucher_type\") == \"Sales Invoice\" -%}\n          {%- set etr = frappe.db.get_value(\"Sales Invoice\", row.get(\"voucher_no\"), [\"etr_invoice_number\", \"cu_link\"], as_dict=True) -%}\n          {%- if etr and etr.etr_invoice_number -%}\n          <div class=\"cuin-line\">CUIN: <a href=\"{{ etr.cu_link }}\" target=\"_blank\">{{ etr.etr_invoice_number }}</a></div>\n          {%- endif -%}\n        {%- endif -%}\n      </td>\n      <td class=\"text-right\">{{ frappe.utils.fmt_money(row.get(\"invoiced\") or 0, currency=currency) }}</td>\n      <td class=\"text-right\">{{ frappe.utils.fmt_money(row.get(\"paid\") or 0, currency=currency) }}</td>\n      <td class=\"text-right\">{{ frappe.utils.fmt_money(row.get(\"credit_note\") or 0, currency=currency) }}</td>\n      <td class=\"text-right font-bold\">{{ frappe.utils.fmt_money(row.get(\"outstanding\") or 0, currency=currency) }}</td>\n    </tr>\n    {%- endif -%}\n    {%- endfor -%}\n  </tbody>\n  <tfoot>\n    <tr class=\"totals-row\">\n      <td colspan=\"4\" class=\"font-bold\">Total</td>\n      <td class=\"text-right font-bold\">{{ frappe.utils.fmt_money(ns.t_invoiced, currency=currency) }}</td>\n      <td class=\"text-right font-bold\">{{ frappe.utils.fmt_money(ns.t_paid, currency=currency) }}</td>\n      <td class=\"text-right font-bold\">{{ frappe.utils.fmt_money(ns.t_credit, currency=currency) }}</td>\n      <td class=\"text-right font-bold\">{{ frappe.utils.fmt_money(ns.t_outstanding, currency=currency) }}</td>\n    </tr>\n  </tfoot>\n</table>\n\n<div class=\"bottom-section\">\n  {%- if ageing -%}\n  <div class=\"aging-container\">\n    <div class=\"section-heading\">Aging Summary</div>\n    <table class=\"sub-table\">\n      <thead>\n        <tr>\n          <th>0&ndash;30</th><th>31&ndash;60</th><th>61&ndash;90</th><th>91&ndash;120</th><th>120+</th><th class=\"text-right\">Total</th>\n        </tr>\n      </thead>\n      <tbody>\n        <tr>\n          {%- set ag_total = (ageing.range1 or 0)+(ageing.range2 or 0)+(ageing.range3 or 0)+(ageing.range4 or 0)+(ageing.range5 or 0) -%}\n          <td>{{ frappe.utils.fmt_money(ageing.range1 or 0, currency=currency) }}</td>\n          <td>{{ frappe.utils.fmt_money(ageing.range2 or 0, currency=currency) }}</td>\n          <td>{{ frappe.utils.fmt_money(ageing.range3 or 0, currency=currency) }}</td>\n          <td>{{ frappe.utils.fmt_money(ageing.range4 or 0, currency=currency) }}</td>\n          <td>{{ frappe.utils.fmt_money(ageing.range5 or 0, currency=currency) }}</td>\n          <td class=\"text-right font-bold\">{{ frappe.utils.fmt_money(ag_total, currency=currency) }}</td>\n        </tr>\n      </tbody>\n    </table>\n  </div>\n  {%- endif -%}\n\n  {%- if future_rows -%}\n  <div class=\"future-container\">\n    <div class=\"section-heading\">Future Payments</div>\n    <table class=\"sub-table future-table\">\n      <thead>\n        <tr><th>Reference</th><th class=\"text-right\">Amount</th><th class=\"text-right\">Remaining</th></tr>\n      </thead>\n      <tbody>\n        {%- for row in future_rows -%}\n        <tr>\n          <td>{{ row.get(\"future_ref\") or \"\" }}</td>\n          <td class=\"text-right\">{{ frappe.utils.fmt_money(row.get(\"future_amount\") or 0, currency=currency) }}</td>\n          <td class=\"text-right\">{{ frappe.utils.fmt_money(row.get(\"remaining_balance\") or 0, currency=currency) }}</td>\n        </tr>\n        {%- endfor -%}\n      </tbody>\n    </table>\n  </div>\n  {%- endif -%}\n</div>\n\n{%- if terms_and_conditions -%}\n<div class=\"terms-section\">\n  <div class=\"section-heading\">Terms &amp; Conditions</div>\n  <div class=\"terms-text\">{{ terms_and_conditions }}</div>\n</div>\n{%- endif -%}\n\n</div>",
 "idx": 0,
 "line_breaks": 0,
 "modified": "2026-03-26 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Cecypo Frappe Reports",
 "name": "PSOA AR Statement",
 "owner": "Administrator",
 "page_number": "Bottom Right",
 "print_format_for": "Report",
 "print_format_type": "Jinja",
 "report": "Accounts Receivable",
 "standard": "No"
}
```

- [ ] **Step 3.2: Load into site**

```bash
cd /home/frappeuser/bench16
bench --site site16.local migrate
```

If the fixture isn't auto-imported, run:

```bash
bench --site site16.local import-doc cecypo_frappe_reports/cecypo_frappe_reports/print_format/psoa_ar_statement/psoa_ar_statement.json
```

- [ ] **Step 3.3: Verify the Print Format exists**

```bash
bench --site site16.local execute frappe.db.get_value --args "['Print Format', 'PSOA AR Statement', ['print_format_for', 'report', 'print_format_type']]"
```

Expected: `['Report', 'Accounts Receivable', 'Jinja']`

If `bench execute` fails, use the console:
```bash
bench --site site16.local console
frappe.db.get_value("Print Format", "PSOA AR Statement", ["print_format_for", "report", "print_format_type"])
```

- [ ] **Step 3.4: Visual verification**

1. Go to Accounts → Process Statement Of Accounts → open/create a doc set to **Accounts Receivable** report
2. Set `Print Format` = `PSOA AR Statement`
3. Click **Preview** — confirm no Jinja error
4. Check: columns Date/Days/Type/Reference/Invoiced/Paid/Credit Note/Outstanding all present; amounts formatted; aging summary appears if `Include Ageing` is enabled
5. If `Show Future Payments` is enabled and there are future-dated payment entries, confirm the Future Payments section appears in the bottom-right

- [ ] **Step 3.5: Commit AR template**

```bash
cd /home/frappeuser/bench16/apps/cecypo_frappe_reports
git add cecypo_frappe_reports/cecypo_frappe_reports/print_format/psoa_ar_statement/
git commit -m "feat: add PSOA AR Statement print format (Jinja, landscape A4)"
```

---

## Task 4: Export fixtures and final cleanup

- [ ] **Step 4.1: Export both Print Formats as fixtures**

This regenerates the JSON from the live site (captures any modifications made through the UI):

```bash
cd /home/frappeuser/bench16
bench --site site16.local export-fixtures --app cecypo_frappe_reports
```

- [ ] **Step 4.2: Verify exported files**

```bash
ls -la apps/cecypo_frappe_reports/cecypo_frappe_reports/print_format/psoa_gl_statement/
ls -la apps/cecypo_frappe_reports/cecypo_frappe_reports/print_format/psoa_ar_statement/
```

Expected: both `psoa_gl_statement.json` and `psoa_ar_statement.json` are present and non-empty.

- [ ] **Step 4.3: Final commit**

```bash
cd apps/cecypo_frappe_reports
git add -A
git status  # review — should only be the two JSON files updated (if export changed anything)
git commit -m "feat: export PSOA print format fixtures post-verification"
```

---

## Troubleshooting

**Jinja error on preview:** Check the error message — most likely cause is accessing a `None` value. Add `or frappe._dict()` guards after `frappe.db.get_value` calls that could return None.

**Print Format not accepted by PSOA validation:** Confirm `print_format_for = "Report"` and `report` matches exactly the value in the PSOA's `report` field ("General Ledger" or "Accounts Receivable"). Check with:
```bash
bench --site site16.local execute frappe.db.get_value --args "['Print Format', 'PSOA GL Statement', 'print_format_for']"
```

**Future payments section not showing (AR):** Enable `Show Future Payments` on the PSOA doc. The `future_ref` field only appears in data rows when this is enabled.

**Aging not showing:** Enable `Include Ageing` on the PSOA doc. The `ageing` context variable is `None` when disabled.

**Fixture not loading on migrate:** Use `import-doc` command (Step 2.3 / 3.2). Fixtures defined in `hooks.py` are only auto-imported on `install-app`, not on every `migrate`.
