# Design: Process Statement of Accounts — Print Format Templates

**Date:** 2026-03-26
**Scope:** Two Jinja print format templates for `Process Statement Of Accounts` in ERPNext v16 — one for General Ledger, one for Accounts Receivable.

---

## Background

In ERPNext v16, the `Process Statement Of Accounts` doctype gained a `print_format` field. When set, ERPNext renders statements using that Print Format (type: Jinja) instead of the built-in HTML templates. The print format is validated to be Jinja type and matching the report type selected on the doc.

These templates live in `cecypo_frappe_reports` as Print Format records (created via fixtures or manually via the UI with Doc Type = `Process Statement Of Accounts`).

### Jinja Context Available

The template receives these variables — no `doc` or `customer` is available:

| Variable | Contents |
|---|---|
| `filters` | Dict: `company`, `party` (customer ID), `from_date`, `to_date`, `finance_book`, `account`, `cost_center`, `show_remarks` |
| `data` | List of report row dicts (GL rows or AR rows) |
| `report` | Dict: `report_name` ("General Ledger" or "Accounts Receivable"), `columns` |
| `ageing` | Ageing bucket dict if `include_ageing` enabled, else `None` |
| `letter_head` | Raw HTML from Letter Head doctype if set, else `None` |
| `terms_and_conditions` | Plain text from T&C doctype if set, else `None` |

Customer name, tax ID, address, phone, email are not in `filters` — they are fetched inline via `frappe.db.get_value` / `frappe.db.get_all` in the template (same pattern as in the reference repo).

---

## Files to Create

| File | Description |
|---|---|
| `cecypo_frappe_reports/cecypo_frappe_reports/print_format/psoa_gl/psoa_gl.html` | GL statement Jinja template |
| `cecypo_frappe_reports/cecypo_frappe_reports/print_format/psoa_gl/psoa_gl.json` | Print Format DocType record (fixture) |
| `cecypo_frappe_reports/cecypo_frappe_reports/print_format/psoa_ar/psoa_ar.html` | AR statement Jinja template |
| `cecypo_frappe_reports/cecypo_frappe_reports/print_format/psoa_ar/psoa_ar.json` | Print Format DocType record (fixture) |

Print Format JSON fields: `name`, `doc_type = "Process Statement Of Accounts"`, `print_format_type = "Jinja"`, `html` (template content), `standard = "No"`.

Fixtures entry to add to `hooks.py`:
```python
fixtures = [
    {"dt": "Print Format", "filters": [["name", "in", ["PSOA GL Statement", "PSOA AR Statement"]]]}
]
```

---

## Visual Design — Option A (Clean Corporate)

**Page:** A4 landscape, margins 10mm top/bottom, 8mm left/right.
**Font:** Arial/Helvetica, system stack.
**Accent color:** `#1a56a0` (dark corporate blue).
**Body font size:** 8pt.

### Section 1 — Header

Conditional:
- **If `letter_head`:** render `{{ letter_head }}` as-is.
- **Else:** Two-column fallback:
  - Left: company name (14pt bold) + "STATEMENT OF ACCOUNT" (9pt, letter-spacing, uppercase)
  - Right: "Period: {from_date} – {to_date}" + "Printed: {today}"
- Solid 2px `#1a56a0` rule below the header block.

### Section 2 — Customer Info Strip

Compact two-column row (no large boxes, max ~3 lines tall):
- **Left:** Customer display name (bold 10pt), Tax ID (`tax_id` from Customer), primary address (one line, from linked Address).
- **Right:** Phone + Email (from linked Contact), currency.

All fetched via `frappe.db` in template. If a value is not found, the field is simply omitted.

### Section 3 — Main Transactions Table

Styling: 8pt font, row padding 2px 4px, alternating `#f8f8f8` on even rows, `1px solid #e0e0e0` bottom border per row. Header row: white text on `#1a56a0`.

**GL columns:**

| Column | Align | Notes |
|---|---|---|
| Date | Left | `posting_date` |
| Type | Left | `voucher_type` |
| Reference | Left | `voucher_no` as link; CUIN sub-line if applicable |
| Remarks | Left | Only if `filters.show_remarks`; omit column entirely if not |
| Debit | Right | `frappe.utils.fmt_money()` |
| Credit | Right | `frappe.utils.fmt_money()` |
| Balance | Right | Bold; `frappe.utils.fmt_money()` |

**AR columns:**

| Column | Align | Notes |
|---|---|---|
| Date | Left | `posting_date` |
| Days | Center | `age` |
| Type | Left | `voucher_type` |
| Reference | Left | `voucher_no` as link; CUIN sub-line if applicable |
| Invoiced | Right | `frappe.utils.fmt_money()` |
| Paid | Right | `frappe.utils.fmt_money()` |
| Credit Note | Right | `frappe.utils.fmt_money()` |
| Outstanding | Right | Bold; `frappe.utils.fmt_money()` |

**CUIN sub-line** (both templates): For each Sales Invoice row, if `frappe.get_meta('Sales Invoice').has_field('etr_invoice_number')` and the value is set, render a small `CUIN: <a href="{{ cu_link }}">{{ etr_invoice_number }}</a>` in 7pt below the voucher reference. Uses `frappe.db.get_value('Sales Invoice', voucher_no, ['etr_invoice_number', 'cu_link'])`.

**Totals row:** `#e8e8e8` background, bold. GL: sums of Debit, Credit. AR: sums of Invoiced, Paid, Credit Note, Outstanding.

### Section 4 — Bottom Section

Two floated columns, `page-break-inside: avoid`:

- **Left (60%) — Aging Summary:** Small compact table with section heading "Aging Summary". Buckets: 0–30 | 31–60 | 61–90 | 91–120 | 120+ | Total. Only rendered if `ageing` is not `None`.
- **Right (35%) — Future Payments:** Small table: Date | Mode of Payment | Reference | Amount. Heading "Future Payments". For AR: only rendered if any row has a non-null `future_ref`. For GL: only rendered if any row has `posting_date > filters.to_date` (future-dated entries). If no qualifying rows exist, the column is omitted entirely.

**Terms & Conditions:** Below both floated sections, small 7pt text, only if `terms_and_conditions` is set.

**Page number:** CSS `counter(page)` at bottom-right of every page via `@page` / `::after`.

---

## Key Implementation Notes

1. **No `doc` variable** — do not attempt to access `doc.*`. Use `filters.party` for the customer ID.
2. **`frappe` is available** in Jinja context — `frappe.db.get_value`, `frappe.get_meta`, `frappe.utils.fmt_money` all work.
3. **Currency formatting:** Use `frappe.utils.fmt_money(value, currency=filters.get("presentation_currency") or filters.get("currency"))` — mirrors the reference repo pattern.
4. **Remarks column** in GL: omit the entire `<th>` and `<td>` when `not filters.show_remarks` — do not render an empty column.
5. **Both templates share the same CSS** — inline it in each file (no external stylesheet dependency since print formats are self-contained).
6. **Fixtures:** After creating the JSON files, run `bench --site site16.local migrate` to register. Export with `bench --site site16.local export-fixtures --app cecypo_frappe_reports`.
