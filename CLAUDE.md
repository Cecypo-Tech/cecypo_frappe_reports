# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`cecypo_frappe_reports` is a Frappe Framework application (compatible with Frappe/ERPNext v15+) providing enhanced financial reports. Reports extend or replace standard ERPNext reports with additional features.

## Development Commands

All commands run from the bench root (`/home/frappeuser/frappe-bench`):

```bash
# Install app on a site
bench --site <site-name> install-app cecypo_frappe_reports

# Build frontend assets
bench build --app cecypo_frappe_reports

# Run migrations after schema changes
bench --site <site-name> migrate

# Watch for asset changes during development
bench watch

# Run Frappe tests
bench --site <site-name> run-tests --app cecypo_frappe_reports
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

### Backend Patterns

- Use `frappe.qb` (PyPika-based Query Builder) for SQL — avoid raw SQL strings
- Entry point is `execute(filters)` returning `(columns, data, message, chart, report_summary)`
- Separate functions for: column generation, data fetching, post-processing/aggregation
- Payment/advance handling queries `Payment Entry` and `Payment Entry Reference` to map allocations back to invoices
- Use `frappe.utils.flt(value, 2)` for float precision

### Frontend Patterns

- Filters defined declaratively in `frappe.query_reports["Report Name"].filters`
- Dynamic columns (e.g., one column per payment mode) fetched via `frappe.call()` in `onload`
- Column formatting via `formatter` callbacks and Frappe's `format_currency`/`format_number`
- Apply compact display in `onload`: set column widths to `"Best Fit"` and hide unnecessary toolbar elements

### Number Formatting

All amount columns (`Float` and `Currency` fieldtype) must be formatted as comma-separated numbers **without** a currency symbol. Always add a `formatter` to each report's JS object:

```javascript
formatter(value, row, column, data, default_formatter) {
    if ((column.fieldtype === "Float" || column.fieldtype === "Currency") && value != null) {
        return frappe.utils.format_number(value, null, 2);
    }
    return default_formatter(value, row, column, data);
},
```

### Code Style

- **Python**: tabs for indentation, double quotes, line length 110, target Python 3.10+ (enforced by ruff)
- **JavaScript**: tabs for indentation, ESLint recommended + Frappe globals (`frappe`, `cur_frm`, etc.)
- **Formatting**: Prettier for JS/Vue/SCSS

## Adding a New Report

1. Create directory: `cecypo_frappe_reports/cecypo_frappe_reports/report/<report_name>/`
2. Add `__init__.py` (empty)
3. Create the `.json` metadata file (copy structure from `sales_report_enhanced.json`)
4. Implement `execute(filters)` in the `.py` file
5. Define filters and formatters in the `.js` file
6. Run `bench --site <site> migrate` to register the report
