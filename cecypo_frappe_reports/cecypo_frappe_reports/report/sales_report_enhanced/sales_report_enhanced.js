// Copyright (c) 2026, Cecypo and contributors
// For license information, please see license.txt

frappe.query_reports["Sales Report Enhanced"] = {
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
			fieldname: "mode_of_payment",
			label: __("Mode of Payment"),
			fieldtype: "Link",
			options: "Mode of Payment",
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		if ((column.fieldtype === "Float" || column.fieldtype === "Currency") && value != null) {
			return frappe.utils.format_number(value, null, 2);
		}
		return default_formatter(value, row, column, data);
	},
	onload(report) {
		// Add custom_sale_type filter if the field exists on Sales Invoice
		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.report.sales_report_enhanced.sales_report_enhanced.get_custom_sale_type_options",
			callback(r) {
				if (r.message) {
					report.page.add_field({
						fieldname: "custom_sale_type",
						label: __("Sale Type"),
						fieldtype: "Select",
						options: ["", ...r.message],
					});
				}
			},
		});

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

			// Simulate a dblclick on each column's resize handle,
			// which triggers the datatable's built-in perfect-width logic
			const handles = dt.header.querySelectorAll(
				".dt-cell .dt-cell__resize-handle"
			);
			handles.forEach((handle) => {
				handle.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
			});
		});
	},
};
