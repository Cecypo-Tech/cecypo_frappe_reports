// Copyright (c) 2026, Cecypo and contributors
// For license information, please see license.txt

frappe.query_reports["Item History"] = {
	filters: [
		{
			fieldname: "item",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
			reqd: 1,
		},
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
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query() {
				let company = frappe.query_report.get_filter_value("company");
				return { filters: { company } };
			},
		},
	],
	formatter(value, row, column, data, default_formatter) {
		if (
			(column.fieldtype === "Float" || column.fieldtype === "Currency") &&
			value != null
		) {
			return format_number(value, null, 2);
		}
		return default_formatter(value, row, column, data);
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
