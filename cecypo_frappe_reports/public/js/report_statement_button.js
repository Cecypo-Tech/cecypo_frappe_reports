// Copyright (c) 2026, Cecypo and contributors
// For license information, please see license.txt

// Adds a "Statement of Accounts" button to the Accounts Receivable and Accounts Receivable Summary
// query reports.
//
// QueryReport.refresh_report() calls page.clear_custom_actions() and then report_settings.onload(),
// so a button has to be re-added on every report load. Wrapping the report script's own onload is
// the obvious hook, but frappe.query_reports[name] is only populated after the script is fetched and
// eval'd, which makes that a race. Patching the prototype once and running after the returned
// promise resolves sidesteps the race entirely and still lands after clear_custom_actions().

(() => {
	"use strict";

	frappe.provide("cecypo_reports.statement");

	const TARGET_REPORTS = ["Accounts Receivable", "Accounts Receivable Summary"];

	function resolve_customer(report) {
		// party is a MultiSelectList and party_type may be any receivable party type, so a customer
		// is only unambiguous when exactly one Customer is selected. Otherwise the dialog asks.
		const party_type = report.get_filter_value("party_type");
		if (party_type && party_type !== "Customer") return null;

		const party = report.get_filter_value("party");
		const selected = Array.isArray(party) ? party : party ? [party] : [];
		return selected.length === 1 ? selected[0] : null;
	}

	function add_statement_button(report) {
		if (!TARGET_REPORTS.includes(report.report_name)) return;
		if (!cecypo_reports.statement || !cecypo_reports.statement.open) return;

		report.page.add_inner_button(__("Statement of Accounts"), () => {
			const company = report.get_filter_value("company");
			if (!company) {
				frappe.msgprint(__("Select a Company first"));
				return;
			}

			cecypo_reports.statement.open({
				company,
				party: resolve_customer(report),
				party_type: "customer",
				as_of_date: report.get_filter_value("report_date"),
			});
		});
	}

	function patch() {
		const QueryReport = frappe.views && frappe.views.QueryReport;
		if (!QueryReport || typeof QueryReport.prototype.refresh_report !== "function") {
			// A future Frappe rename degrades to no button rather than a broken desk.
			return false;
		}
		if (QueryReport.prototype._cecypo_statement_patched) return true;
		QueryReport.prototype._cecypo_statement_patched = true;

		const original = QueryReport.prototype.refresh_report;
		QueryReport.prototype.refresh_report = function (...args) {
			const result = original.apply(this, args);
			return Promise.resolve(result).then((value) => {
				try {
					add_statement_button(this);
				} catch (e) {
					// Never let a button failure break the report itself.
					console.error("cecypo: statement button", e);
				}
				return value;
			});
		};
		return true;
	}

	if (!patch()) {
		// app_include_js normally loads after frappe's desk bundle, but do not depend on it.
		$(document).on("app_ready", patch);
	}
})();
