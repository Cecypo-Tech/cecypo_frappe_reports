// Copyright (c) 2026, Cecypo and contributors
// For license information, please see license.txt

frappe.query_reports["Day Book"] = {
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
			default: frappe.datetime.get_today(),
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
			fieldname: "date_based_on",
			label: __("Date Based On"),
			fieldtype: "Select",
			options: ["Posting Date", "Creation Date"].join("\n"),
			default: "Posting Date",
		},
		{
			fieldname: "voucher_category",
			label: __("Voucher Category"),
			fieldtype: "Select",
			options: [
				"",
				"Sales",
				"Purchase",
				"Payments & Journals",
				"Stock",
				"Assets",
				"Other",
			].join("\n"),
		},
		{
			fieldname: "party_type",
			label: __("Party Type"),
			fieldtype: "Link",
			options: "Party Type",
		},
		{
			fieldname: "party",
			label: __("Party"),
			fieldtype: "Dynamic Link",
			options: "party_type",
		},
		{
			fieldname: "account",
			label: __("Account"),
			fieldtype: "Link",
			options: "Account",
			get_query() {
				let company = frappe.query_report.get_filter_value("company");
				return { filters: { company: company } };
			},
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
			get_query() {
				let company = frappe.query_report.get_filter_value("company");
				return { filters: { company: company } };
			},
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query() {
				let company = frappe.query_report.get_filter_value("company");
				return { filters: { company: company } };
			},
		},
		{
			fieldname: "summarized",
			label: __("Summarized"),
			fieldtype: "Check",
			default: 0,
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
		// Compact report summary styling
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

		// Standalone "Best Fit" button
		report.page.add_button(__("Best Fit"), () => {
			const dt = report.datatable;
			if (!dt) return;

			const handles = dt.header.querySelectorAll(
				".dt-cell .dt-cell__resize-handle"
			);
			handles.forEach((handle) => {
				handle.dispatchEvent(
					new MouseEvent("dblclick", { bubbles: true })
				);
			});
		});
	},
};
