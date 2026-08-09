// Copyright (c) 2026, Cecypo and contributors
// For license information, please see license.txt

// Adds a "Send in Batches" button to the Process Statement Of Accounts form, alongside ERPNext's
// own "Send Emails" button. ERPNext's button renders every customer's PDF inside a single HTTP
// request and times out on a sizeable customer base; this calls the same batched worker the POS
// path uses, enqueuing the record's own customers in chunks and returning immediately.

frappe.ui.form.on("Process Statement Of Accounts", {
	refresh(frm) {
		if (frm.doc.__islocal) return;

		frm.add_custom_button(__("Send in Batches"), function () {
			if (frm.is_dirty()) frappe.throw(__("Please save before proceeding."));

			frappe.confirm(
				__("Queue statements for every customer on this record, in batches of {0}?", [50]),
				function () {
					frappe.call({
						method: "cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.send_psoa_in_batches",
						args: { document_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Queueing statements..."),
						callback(r) {
							if (!r || !r.message) return;
							frappe.show_alert({
								message: __("Queued {0} customers in {1} batches", [
									r.message.customers,
									r.message.batches,
								]),
								indicator: "green",
							});
						},
					});
				}
			);
		});
	},
});
