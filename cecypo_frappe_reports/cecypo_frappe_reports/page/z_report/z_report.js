// Copyright (c) 2026, Cecypo and contributors
// For license information, please see license.txt

frappe.pages["z-report"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Z Report"),
		single_column: true,
	});
	const warehouse = page.add_field({
		fieldname: "warehouse",
		label: __("Warehouse"),
		fieldtype: "Select", // a Link would need Warehouse read, which Accounts roles lack
		change: () => refresh(),
	});
	const date = page.add_field({
		fieldname: "date",
		label: __("Date"),
		fieldtype: "Date",
		default: frappe.datetime.get_today(),
		change: () => refresh(),
	});
	const body = $('<div class="z-report-body"></div>').appendTo(page.main);

	function refresh() {
		const w = warehouse.get_value();
		const d = date.get_value();
		if (!w || !d) {
			body.html(`<p class="text-muted">${__("Pick a warehouse and a date.")}</p>`);
			return;
		}
		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.z_report.z_report.get_z_report_html",
			args: { warehouse: w, date: d },
			freeze: true,
			callback: (r) => body.html(r.message),
		});
	}

	page.set_primary_action(__("Refresh"), refresh);
	page.add_button(__("Print"), () => window.print());

	const api = "cecypo_frappe_reports.cecypo_frappe_reports.page.z_report.z_report.";
	Promise.all([frappe.xcall(api + "get_branch_options"), frappe.xcall(api + "get_default_warehouse")]).then(
		([options, w]) => {
			warehouse.df.options = ["", ...options].join("\n");
			warehouse.refresh();
			if (w) warehouse.set_value(w);
			else refresh();
		}
	);
};
