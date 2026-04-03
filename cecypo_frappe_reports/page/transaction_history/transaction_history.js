// Copyright (c) 2026, Cecypo and contributors
// For license information, please see license.txt

frappe.pages["transaction-history"].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Transaction History"),
		single_column: true,
	});
	new TransactionHistoryPage(page);
};

class TransactionHistoryPage {
	constructor(page) {
		this.page = page;
		this.active_tab = "item";
		this.controls = {};
		this._render();
		this._bind_tabs();
	}

	// ── Layout ────────────────────────────────────────────────────────────────

	_render() {
		$(this.page.main).html(`
			<div class="transaction-history" style="padding:16px">
				<div class="th-tab-bar" style="display:flex;border-bottom:2px solid var(--border-color);margin-bottom:16px">
					<button class="th-tab btn btn-default active" data-tab="item"
						style="border:none;border-bottom:2px solid var(--primary);margin-bottom:-2px;border-radius:0;font-weight:600;padding:8px 20px">
						${__("Item History")}
					</button>
					<button class="th-tab btn btn-default" data-tab="customer"
						style="border:none;border-bottom:2px solid transparent;margin-bottom:-2px;border-radius:0;padding:8px 20px">
						${__("Customer History")}
					</button>
					<button class="th-tab btn btn-default" data-tab="supplier"
						style="border:none;border-bottom:2px solid transparent;margin-bottom:-2px;border-radius:0;padding:8px 20px">
						${__("Supplier History")}
					</button>
				</div>

				<div class="th-panel" data-panel="item">
					<div class="th-filters item-filters" style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px">
						<div class="ctrl-item-item" style="min-width:200px"></div>
						<div class="ctrl-item-company" style="min-width:180px"></div>
						<div class="ctrl-item-from" style="min-width:120px"></div>
						<div class="ctrl-item-to" style="min-width:120px"></div>
						<div class="ctrl-item-warehouse" style="min-width:160px"></div>
						<button class="btn btn-primary btn-sm btn-get-item">${__("Get History")}</button>
					</div>
					<div class="th-content item-content"></div>
				</div>

				<div class="th-panel hidden" data-panel="customer">
					<div class="th-filters customer-filters" style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px">
						<div class="ctrl-cust-customer" style="min-width:220px"></div>
						<div class="ctrl-cust-company" style="min-width:180px"></div>
						<div class="ctrl-cust-from" style="min-width:120px"></div>
						<div class="ctrl-cust-to" style="min-width:120px"></div>
						<button class="btn btn-primary btn-sm btn-get-customer">${__("Get History")}</button>
					</div>
					<div class="th-content customer-content"></div>
				</div>

				<div class="th-panel hidden" data-panel="supplier">
					<div class="th-filters supplier-filters" style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px">
						<div class="ctrl-supp-supplier" style="min-width:220px"></div>
						<div class="ctrl-supp-company" style="min-width:180px"></div>
						<div class="ctrl-supp-from" style="min-width:120px"></div>
						<div class="ctrl-supp-to" style="min-width:120px"></div>
						<button class="btn btn-primary btn-sm btn-get-supplier">${__("Get History")}</button>
					</div>
					<div class="th-content supplier-content"></div>
				</div>
			</div>
		`);
		this._setup_controls();
	}

	_setup_controls() {
		const m = this.page.main;
		const default_company = frappe.defaults.get_user_default("Company");
		const make = (parent, df) =>
			frappe.ui.form.make_control({ parent: $(m).find(parent)[0], df, render_input: true });

		// Item tab
		this.controls.item = make(".ctrl-item-item", { fieldtype: "Link", options: "Item", fieldname: "item", label: __("Item"), reqd: 1 });
		this.controls.item_company = make(".ctrl-item-company", { fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company"), reqd: 1, default: default_company });
		this.controls.item_from = make(".ctrl-item-from", { fieldtype: "Date", fieldname: "from_date", label: __("From Date") });
		this.controls.item_to = make(".ctrl-item-to", { fieldtype: "Date", fieldname: "to_date", label: __("To Date") });
		this.controls.item_warehouse = make(".ctrl-item-warehouse", { fieldtype: "Link", options: "Warehouse", fieldname: "warehouse", label: __("Warehouse") });

		if (default_company) this.controls.item_company.set_value(default_company);

		// Customer tab
		this.controls.customer = make(".ctrl-cust-customer", { fieldtype: "Link", options: "Customer", fieldname: "customer", label: __("Customer"), reqd: 1 });
		this.controls.cust_company = make(".ctrl-cust-company", { fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company"), reqd: 1, default: default_company });
		this.controls.cust_from = make(".ctrl-cust-from", { fieldtype: "Date", fieldname: "from_date", label: __("From Date") });
		this.controls.cust_to = make(".ctrl-cust-to", { fieldtype: "Date", fieldname: "to_date", label: __("To Date") });

		if (default_company) this.controls.cust_company.set_value(default_company);

		// Supplier tab
		this.controls.supplier = make(".ctrl-supp-supplier", { fieldtype: "Link", options: "Supplier", fieldname: "supplier", label: __("Supplier"), reqd: 1 });
		this.controls.supp_company = make(".ctrl-supp-company", { fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company"), reqd: 1, default: default_company });
		this.controls.supp_from = make(".ctrl-supp-from", { fieldtype: "Date", fieldname: "from_date", label: __("From Date") });
		this.controls.supp_to = make(".ctrl-supp-to", { fieldtype: "Date", fieldname: "to_date", label: __("To Date") });

		if (default_company) this.controls.supp_company.set_value(default_company);
	}

	// ── Item History ─────────────────────────────────────────────────────────

	_load_item_history() {
		let item = this.controls.item.get_value();
		let company = this.controls.item_company.get_value();
		if (!item || !company) {
			frappe.msgprint(__("Item and Company are required"));
			return;
		}
		let $content = $(this.page.main).find(".item-content");
		$content.html(`<div class="text-muted" style="padding:20px">${__("Loading...")}</div>`);

		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_item_history",
			args: {
				item,
				company,
				from_date: this.controls.item_from.get_value() || null,
				to_date: this.controls.item_to.get_value() || null,
				warehouse: this.controls.item_warehouse.get_value() || null,
			},
			callback: (r) => {
				if (r.message) $content.html(this._render_item_history(r.message));
			},
		});
	}

	_render_item_history({ item_details, stock_metrics, purchases, sales }) {
		return `
			${this._render_metrics_grid(item_details, stock_metrics)}
			<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px">
				${this._render_purchase_panel(purchases)}
				${this._render_sales_panel(sales)}
			</div>
		`;
	}

	_render_metrics_grid(d, m) {
		const row = (label, value, bold) =>
			`<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--border-color)">
				<span style="color:var(--text-muted)">${label}</span>
				<span${bold ? ' style="font-weight:700"' : ""}>${value ?? "—"}</span>
			</div>`;

		const stock_color = (m.current_stock || 0) > 0 ? "var(--green)" : "var(--red)";

		return `
			<div style="display:grid;grid-template-columns:1fr 1fr;gap:0 24px;background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:14px 18px">
				<div>
					${row(__("Item Name"), d.item_name, true)}
					${row(__("Brand"), d.brand)}
					${row(__("Stock UOM"), d.stock_uom)}
					${row(__("Current Stock"), `<span style="color:${stock_color};font-weight:700">${format_number(m.current_stock, null, 2)} ${d.stock_uom || ""}</span>`)}
					${row(__("Avg. Stock Rate"), format_number(m.avg_rate, null, 2))}
					${row(__("Stock Value"), format_number(m.stock_value, null, 2))}
				</div>
				<div>
					${row(__("Item Code"), d.item_code, true)}
					${row(__("Item Group"), d.item_group)}
					${row(__("Valuation Method"), d.valuation_method)}
					${row(__("Pending PO Qty"), format_number(m.pending_po_qty, null, 2))}
					${row(__("Pending SO Qty"), format_number(m.pending_so_qty, null, 2))}
					${row(__("Reorder Level"), m.reorder_level)}
				</div>
			</div>`;
	}

	_render_purchase_panel(rows) {
		let total_qty = rows.reduce((s, r) => s + (r.qty || 0), 0);
		return `
			<div style="border:1px solid var(--border-color);border-radius:6px;overflow:hidden">
				<div style="background:var(--green-highlight, #e8f5e9);padding:8px 12px;font-weight:700;color:var(--green, #2e7d32);display:flex;justify-content:space-between">
					<span>${__("Purchases")}</span>
					<span style="font-weight:400;font-size:12px">${__("Total Qty: {0}", [format_number(total_qty, null, 2)])}</span>
				</div>
				<div style="overflow-x:auto">
					<table style="width:100%;border-collapse:collapse;font-size:12px">
						<thead>
							<tr style="background:var(--subtle-fg)">
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Date")}</th>
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Voucher")}</th>
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Supplier")}</th>
								<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Qty")}</th>
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("UOM")}</th>
								<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Rate")}</th>
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Curr.")}</th>
								<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:700;border-bottom:1px solid var(--border-color)">${__("Val. Rate")}</th>
							</tr>
						</thead>
						<tbody>
							${rows.length ? rows.map((r, i) => `
								<tr style="${i % 2 ? "background:var(--subtle-fg)" : ""}">
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${frappe.datetime.str_to_user(r.date)}</td>
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/purchase-receipt/${r.voucher_no}">${r.voucher_no}</a></td>
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.supplier || ""}</td>
									<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.qty, null, 2)}</td>
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.uom || ""}</td>
									<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.rate, null, 2)}</td>
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><span style="background:#e3f2fd;padding:2px 5px;border-radius:3px;font-size:10px;font-weight:600">${r.currency || ""}</span></td>
									<td style="padding:4px 8px;text-align:right;font-weight:600;border-bottom:1px solid var(--border-color)">${format_number(r.valuation_rate, null, 2)}</td>
								</tr>`).join("") : `<tr><td colspan="8" style="padding:12px;text-align:center;color:var(--text-muted)">${__("No purchases found")}</td></tr>`}
						</tbody>
					</table>
				</div>
			</div>`;
	}

	_render_sales_panel(rows) {
		let total_qty = rows.reduce((s, r) => s + (r.qty || 0), 0);
		return `
			<div style="border:1px solid var(--border-color);border-radius:6px;overflow:hidden">
				<div style="background:var(--blue-highlight, #e3f2fd);padding:8px 12px;font-weight:700;color:var(--blue, #1565c0);display:flex;justify-content:space-between">
					<span>${__("Sales")}</span>
					<span style="font-weight:400;font-size:12px">${__("Total Qty: {0}", [format_number(total_qty, null, 2)])}</span>
				</div>
				<div style="overflow-x:auto">
					<table style="width:100%;border-collapse:collapse;font-size:12px">
						<thead>
							<tr style="background:var(--subtle-fg)">
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Date")}</th>
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Voucher")}</th>
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Customer")}</th>
								<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Qty")}</th>
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("UOM")}</th>
								<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Rate")}</th>
								<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Curr.")}</th>
								<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:700;border-bottom:1px solid var(--border-color)">${__("Base Rate")}</th>
							</tr>
						</thead>
						<tbody>
							${rows.length ? rows.map((r, i) => `
								<tr style="${i % 2 ? "background:var(--subtle-fg)" : ""}">
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${frappe.datetime.str_to_user(r.date)}</td>
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/sales-invoice/${r.voucher_no}">${r.voucher_no}</a></td>
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.customer || ""}</td>
									<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.qty, null, 2)}</td>
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.uom || ""}</td>
									<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.rate, null, 2)}</td>
									<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><span style="background:#fce4ec;padding:2px 5px;border-radius:3px;font-size:10px;font-weight:600">${r.currency || ""}</span></td>
									<td style="padding:4px 8px;text-align:right;font-weight:600;border-bottom:1px solid var(--border-color)">${format_number(r.base_rate, null, 2)}</td>
								</tr>`).join("") : `<tr><td colspan="8" style="padding:12px;text-align:center;color:var(--text-muted)">${__("No sales found")}</td></tr>`}
						</tbody>
					</table>
				</div>
			</div>`;
	}

	// ── Customer History ──────────────────────────────────────────────────────

	_load_customer_history() {
		let customer = this.controls.customer.get_value();
		let company = this.controls.cust_company.get_value();
		if (!customer || !company) { frappe.msgprint(__("Customer and Company are required")); return; }
		let $content = $(this.page.main).find(".customer-content");
		$content.html(`<div class="text-muted" style="padding:20px">${__("Loading...")}</div>`);

		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_customer_history",
			args: {
				customer,
				company,
				from_date: this.controls.cust_from.get_value() || null,
				to_date: this.controls.cust_to.get_value() || null,
			},
			callback: (r) => {
				if (r.message != null)
					$content.html(this._render_party_summary(r.message, "customer", customer, company));
			},
		});
	}

	// ── Supplier History ──────────────────────────────────────────────────────

	_load_supplier_history() {
		let supplier = this.controls.supplier.get_value();
		let company = this.controls.supp_company.get_value();
		if (!supplier || !company) { frappe.msgprint(__("Supplier and Company are required")); return; }
		let $content = $(this.page.main).find(".supplier-content");
		$content.html(`<div class="text-muted" style="padding:20px">${__("Loading...")}</div>`);

		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_supplier_history",
			args: {
				supplier,
				company,
				from_date: this.controls.supp_from.get_value() || null,
				to_date: this.controls.supp_to.get_value() || null,
			},
			callback: (r) => {
				if (r.message != null)
					$content.html(this._render_party_summary(r.message, "supplier", supplier, company));
			},
		});
	}

	// ── Shared: accordion summary table ──────────────────────────────────────

	_render_party_summary(rows, party_type, party, company) {
		if (!rows.length)
			return `<div class="text-muted" style="padding:20px">${__("No transactions found")}</div>`;

		const is_customer = party_type === "customer";
		const count_col = is_customer ? __("Invoices") : __("Receipts");
		const rate_col = is_customer ? __("Avg Rate") : __("Avg Val. Rate");
		const date_col = is_customer ? __("Last Sale") : __("Last Purchase");
		const count_key = is_customer ? "invoice_count" : "receipt_count";
		const rate_key = is_customer ? "avg_rate" : "avg_valuation_rate";
		const date_key = is_customer ? "last_sale" : "last_purchase";

		return `
			<table style="width:100%;border-collapse:collapse;font-size:12px">
				<thead>
					<tr style="background:var(--subtle-fg)">
						<th style="padding:5px 8px;width:28px;border-bottom:1px solid var(--border-color)"></th>
						<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Item Code")}</th>
						<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Item Name")}</th>
						<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${__("Total Qty")}</th>
						<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${count_col}</th>
						<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${rate_col}</th>
						<th style="padding:5px 8px;text-align:right;color:var(--text-muted);font-weight:700;border-bottom:1px solid var(--border-color)">${__("Total Amount")}</th>
						<th style="padding:5px 8px;text-align:left;color:var(--text-muted);font-weight:600;border-bottom:1px solid var(--border-color)">${date_col}</th>
					</tr>
				</thead>
				<tbody>
					${rows.map((r, i) => `
						<tr class="summary-row" data-item="${r.item_code}" data-party="${party}" data-party-type="${party_type}" data-company="${company}"
							style="${i % 2 ? "background:var(--subtle-fg)" : ""};cursor:pointer"
							title="${__("Click to expand transactions")}">
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color);color:var(--text-muted)">▶</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/item/${r.item_code}">${r.item_code}</a></td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.item_name}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.total_qty, null, 2)}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r[count_key]}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r[rate_key], null, 2)}</td>
							<td style="padding:4px 8px;text-align:right;font-weight:700;border-bottom:1px solid var(--border-color)">${format_number(r.total_amount, null, 2)}</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r[date_key] ? frappe.datetime.str_to_user(r[date_key]) : "—"}</td>
						</tr>
						<tr class="detail-row hidden" data-detail-for="${r.item_code}">
							<td colspan="8" style="padding:0;border-bottom:2px solid var(--border-color)">
								<div class="detail-content" style="padding:8px 24px;background:var(--fg-color)">
									<span class="text-muted">${__("Loading...")}</span>
								</div>
							</td>
						</tr>
					`).join("")}
				</tbody>
			</table>`;
	}

	// ── Bind tabs + accordion (single method) ────────────────────────────────

	_bind_tabs() {
		const m = this.page.main;

		// Tab switching
		$(m).on("click", ".th-tab", (e) => {
			$(m).find(".th-tab").css("border-bottom-color", "transparent").css("font-weight", "normal");
			$(e.currentTarget).css("border-bottom-color", "var(--primary)").css("font-weight", "600");
			$(m).find(".th-panel").addClass("hidden");
			$(m).find(`[data-panel="${$(e.currentTarget).data("tab")}"]`).removeClass("hidden");
		});

		$(m).on("click", ".btn-get-item", () => this._load_item_history());
		$(m).on("click", ".btn-get-customer", () => this._load_customer_history());
		$(m).on("click", ".btn-get-supplier", () => this._load_supplier_history());

		// Accordion: expand/collapse summary rows
		$(m).on("click", ".summary-row", (e) => {
			let $row = $(e.currentTarget);
			let item_code = $row.data("item");
			let party = $row.data("party");
			let party_type = $row.data("party-type");
			let company = $row.data("company");
			let $detail = $row.closest("tbody").find(`.detail-row[data-detail-for="${item_code}"]`);

			if (!$detail.hasClass("hidden")) {
				$detail.addClass("hidden");
				$row.find("td:first").text("▶");
				return;
			}

			$row.find("td:first").text("▼");
			$detail.removeClass("hidden");

			// Only fetch if not already loaded
			if ($detail.find(".detail-content").data("loaded")) return;

			let is_customer = party_type === "customer";
			let from_date = is_customer ? this.controls.cust_from.get_value() : this.controls.supp_from.get_value();
			let to_date = is_customer ? this.controls.cust_to.get_value() : this.controls.supp_to.get_value();

			frappe.call({
				method: is_customer
					? "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_customer_item_transactions"
					: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_supplier_item_transactions",
				args: {
					[party_type]: party,
					item_code,
					company,
					from_date: from_date || null,
					to_date: to_date || null,
				},
				callback: (r) => {
					let html = this._render_detail_rows(r.message || [], is_customer);
					$detail.find(".detail-content").html(html).data("loaded", true);
				},
			});
		});
	}

	_render_detail_rows(rows, is_customer) {
		if (!rows.length)
			return `<span class="text-muted">${__("No transactions found")}</span>`;

		const rate_label = is_customer ? __("Base Rate") : __("Val. Rate");
		const rate_key = is_customer ? "base_rate" : "valuation_rate";

		return `
			<table style="width:100%;border-collapse:collapse;font-size:11px">
				<thead>
					<tr style="background:var(--yellow-highlight, #fffde7)">
						<th style="padding:3px 8px;text-align:left;color:var(--text-muted)">${__("Date")}</th>
						<th style="padding:3px 8px;text-align:left;color:var(--text-muted)">${__("Voucher No")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted)">${__("Qty")}</th>
						<th style="padding:3px 8px;text-align:left;color:var(--text-muted)">${__("UOM")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted)">${__("Rate")}</th>
						<th style="padding:3px 8px;text-align:left;color:var(--text-muted)">${__("Currency")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted);font-weight:700">${rate_label}</th>
					</tr>
				</thead>
				<tbody>
					${rows.map((r, i) => {
						let doctype_slug = is_customer ? "sales-invoice" : "purchase-receipt";
						return `
							<tr style="${i % 2 ? "background:var(--yellow-highlight, #fffde7)" : "background:var(--fg-color)"}">
								<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)">${frappe.datetime.str_to_user(r.date)}</td>
								<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/${doctype_slug}/${r.voucher_no}">${r.voucher_no}</a></td>
								<td style="padding:3px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.qty, null, 2)}</td>
								<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)">${r.uom || ""}</td>
								<td style="padding:3px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.rate, null, 2)}</td>
								<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)"><span style="background:#e3f2fd;padding:1px 4px;border-radius:3px;font-size:10px;font-weight:600">${r.currency || ""}</span></td>
								<td style="padding:3px 8px;text-align:right;font-weight:600;border-bottom:1px solid var(--border-color)">${format_number(r[rate_key], null, 2)}</td>
							</tr>`;
					}).join("")}
				</tbody>
			</table>`;
	}
}
