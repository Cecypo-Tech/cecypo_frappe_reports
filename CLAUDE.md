# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`cecypo_frappe_reports` is a Frappe Framework application (compatible with Frappe/ERPNext v15+) providing enhanced financial reports. Reports extend or replace standard ERPNext reports with additional features.

## Development Commands

All commands run from the bench root (`/home/frappeuser/bench16`):

```bash
# Install app on a site
bench --site site16.local install-app cecypo_frappe_reports

# Build frontend assets
bench build --app cecypo_frappe_reports

# Run migrations after schema changes
bench --site site16.local migrate

# Watch for asset changes during development
bench watch

# Run Frappe tests
bench --site site16.local run-tests --app cecypo_frappe_reports
```

### Code Quality (pre-commit enforced)

```bash
# Run all pre-commit checks manually
pre-commit run --all-files

# Python: lint and format with ruff
ruff check cecypo_frappe_reports/
ruff format cecypo_frappe_reports/
```

## Architecture

### Frappe App Structure

Each report lives under `cecypo_frappe_reports/cecypo_frappe_reports/report/<report_name>/` and consists of:
- `<name>.json` — Report metadata (DocType, filters, roles, report type)
- `<name>.py` — Backend: data fetching (SQL via Frappe Query Builder / PyPika), column definitions, summary stats
- `<name>.js` — Frontend: filter declarations, formatters, `onload` hook for UI tweaks

Report type is `Script Report` with role access defined in the JSON.

### Two Report Patterns

**Pattern 1 — From-scratch reports** (`sales_report_enhanced`, `day_book`):
- Build all columns, queries, and summaries from scratch using `frappe.qb`
- `execute(filters)` calls dedicated helpers: `get_columns()`, `get_data()`, `get_report_summary()`
- Dynamic columns (one per payment mode, etc.) are determined at runtime and added to both columns and `report_summary`

**Pattern 2 — ERPNext wrapper reports** (`accounts_receivable_summary_enhanced`):
- Import and invoke the upstream ERPNext report class (e.g. `AccountsReceivableSummary`) to get base columns + data
- Append extra columns via `get_extra_columns()` and enrich each row with additional fields from extra queries
- Return `columns + get_extra_columns(), data`

### Backend Patterns

- Use `frappe.qb` (PyPika-based Query Builder) for all SQL — avoid raw SQL strings
- Entry point is `execute(filters)` returning `(columns, data, message, chart, report_summary)`
- Use `frappe.utils.flt(value, 2)` for float precision everywhere
- For datetime → date casting in `frappe.qb`, use PyPika's `CustomFunction`: `CastDate = CustomFunction("DATE", ["value"])`
- Payment/advance handling: query `Sales Invoice Payment` (direct/POS) and `Sales Invoice Advance → Payment Entry` (advance allocation) separately and merge
- `@frappe.whitelist()` functions in `.py` files are callable from JS via `frappe.call()` — used for dynamic filter population (e.g., `get_custom_sale_type_options`)

### Frontend Patterns

- Filters defined declaratively in `frappe.query_reports["Report Name"].filters`
- Dynamic filters added at runtime in `onload` via `frappe.call()` → `report.page.add_field(...)`
- Column formatting via `formatter` callbacks — see Number Formatting below
- `onload` injects compact summary `<style>` and adds a "Best Fit" button (triggers dblclick on resize handles)
- Link filters scoped to the selected company use `get_query()` returning `{ filters: { company } }`

### Number Formatting

All amount columns (`Float` and `Currency` fieldtype) must be formatted as comma-separated numbers **without** a currency symbol. Always add a `formatter` to each report's JS object:

```javascript
formatter(value, row, column, data, default_formatter) {
    if ((column.fieldtype === "Float" || column.fieldtype === "Currency") && value != null) {
        return format_number(value, null, 2);
    }
    return default_formatter(value, row, column, data);
},
```

### Reusable `onload` Boilerplate

Both existing from-scratch reports share the same `onload`: compact summary CSS injection + "Best Fit" button. Copy this pattern when adding new reports.

### Code Style

- **Python**: tabs for indentation, double quotes, line length 110, target Python 3.10+ (enforced by ruff)
- **JavaScript**: tabs for indentation, ESLint recommended + Frappe globals (`frappe`, `cur_frm`, etc.)
- **Formatting**: Prettier for JS/Vue/SCSS

## Adding a New Report

1. Create directory: `cecypo_frappe_reports/cecypo_frappe_reports/report/<report_name>/`
2. Add `__init__.py` (empty)
3. Create the `.json` metadata file (copy from an existing report's JSON — use `sales_report_enhanced` for from-scratch, `accounts_receivable_summary_enhanced` for wrapper pattern)
4. Implement `execute(filters)` in the `.py` file following one of the two patterns above
5. Define filters and formatters in the `.js` file
6. Run `bench --site site16.local migrate` to register the report
