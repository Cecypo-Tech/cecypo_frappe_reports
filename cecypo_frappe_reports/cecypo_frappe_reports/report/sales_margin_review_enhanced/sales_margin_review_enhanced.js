// Copyright (c) 2026, Cecypo and contributors
// For license information, please see license.txt

frappe.query_reports["Sales Margin Review Enhanced"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "customer_group",
			label: __("Customer Group"),
			fieldtype: "Link",
			options: "Customer Group",
		},
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "sales_person",
			label: __("Sales Person"),
			fieldtype: "Link",
			options: "Sales Person",
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		let formatted;
		if ((column.fieldtype === "Float" || column.fieldtype === "Currency") && value != null) {
			formatted = format_number(value, null, 2);
		} else {
			formatted = default_formatter(value, row, column, data);
		}
		if (data && data.is_return) {
			return `<span style="color: var(--text-danger, #d73a49);">${formatted}</span>`;
		}
		if (column.fieldname === "pct_margin" && data && !data.is_return) {
			const pct = parseFloat(value) || 0;
			const color = pct < 0 ? "var(--text-danger, #d73a49)" : pct < 10 ? "var(--text-warning, #e8a838)" : "inherit";
			if (color !== "inherit") {
				return `<span style="color: ${color};">${formatted}</span>`;
			}
		}
		return formatted;
	},
	onload(report) {
		let style = document.createElement("style");
		style.textContent = `
			.report-summary .summary-value {
				font-size: 16px !important;
				line-height: 1.2 !important;
			}
			.report-summary .summary-label {
				font-size: 11px !important;
			}
			.report-summary .summary-item {
				min-width: 100px !important;
				padding: 4px 8px !important;
				margin: 2px 4px !important;
			}
			.report-summary {
				gap: 4px !important;
				padding: 4px 0 !important;
				flex-wrap: wrap !important;
			}
		`;
		document.head.appendChild(style);

		report.page.add_button(__("Best Fit"), () => {
			cecypo_reports.bestFit(report);
		});
	},
};
