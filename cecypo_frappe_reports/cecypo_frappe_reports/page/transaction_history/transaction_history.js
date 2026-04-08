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
		this.base_currency = frappe.defaults.get_default("currency") || "";
		this.controls = {};
		this._cust_state = { rows: [], party: null, company: null, sort_key: "total_amount", sort_dir: "desc" };
		this._supp_state = { rows: [], party: null, company: null, sort_key: "total_amount", sort_dir: "desc" };
		this._supp_source = "pi";
		this._render();
		this._bind_tabs();
	}

	// ── Layout ────────────────────────────────────────────────────────────────

	_render() {
		$(this.page.main).html(`
			<div class="transaction-history" style="padding:16px">
				<ul class="nav nav-tabs" style="margin-bottom:16px">
					<li class="nav-item">
						<a class="nav-link active" href="#" data-tab="item">${__("Item History")}</a>
					</li>
					<li class="nav-item">
						<a class="nav-link" href="#" data-tab="customer">${__("Customer History")}</a>
					</li>
					<li class="nav-item">
						<a class="nav-link" href="#" data-tab="supplier">${__("Supplier History")}</a>
					</li>
				</ul>

				<div class="th-panel" data-panel="item">
					<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px">
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
					<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px">
						<div class="ctrl-cust-customer" style="min-width:220px"></div>
						<div class="ctrl-cust-company" style="min-width:180px"></div>
						<div class="ctrl-cust-from" style="min-width:120px"></div>
						<div class="ctrl-cust-to" style="min-width:120px"></div>
						<button class="btn btn-primary btn-sm btn-get-customer">${__("Get History")}</button>
					</div>
					<div class="th-content customer-content"></div>
				</div>

				<div class="th-panel hidden" data-panel="supplier">
					<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px">
						<div class="ctrl-supp-supplier" style="min-width:220px"></div>
						<div class="ctrl-supp-company" style="min-width:180px"></div>
						<div class="ctrl-supp-from" style="min-width:120px"></div>
						<div class="ctrl-supp-to" style="min-width:120px"></div>
						<div class="ctrl-supp-source"></div>
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
		this.controls.item = make(".ctrl-item-item", {
			fieldtype: "Link", options: "Item", fieldname: "item", label: __("Item"), reqd: 1,
		});
		// Route through ERPNext item_query so the cecypo_powerpack custom search hook activates
		this.controls.item.get_query = () => ({ query: "erpnext.controllers.queries.item_query" });

		this.controls.item_company = make(".ctrl-item-company", {
			fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company"), reqd: 1,
		});
		this.controls.item_from = make(".ctrl-item-from", { fieldtype: "Date", fieldname: "from_date", label: __("From Date") });
		this.controls.item_to = make(".ctrl-item-to", { fieldtype: "Date", fieldname: "to_date", label: __("To Date") });
		this.controls.item_warehouse = make(".ctrl-item-warehouse", {
			fieldtype: "Link", options: "Warehouse", fieldname: "warehouse", label: __("Warehouse"),
		});
		if (default_company) this.controls.item_company.set_value(default_company);

		// Customer tab
		this.controls.customer = make(".ctrl-cust-customer", {
			fieldtype: "Link", options: "Customer", fieldname: "customer", label: __("Customer"), reqd: 1,
		});
		this.controls.cust_company = make(".ctrl-cust-company", {
			fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company"), reqd: 1,
		});
		this.controls.cust_from = make(".ctrl-cust-from", { fieldtype: "Date", fieldname: "from_date", label: __("From Date") });
		this.controls.cust_to = make(".ctrl-cust-to", { fieldtype: "Date", fieldname: "to_date", label: __("To Date") });
		if (default_company) this.controls.cust_company.set_value(default_company);

		// Supplier tab
		this.controls.supplier = make(".ctrl-supp-supplier", {
			fieldtype: "Link", options: "Supplier", fieldname: "supplier", label: __("Supplier"), reqd: 1,
		});
		this.controls.supp_company = make(".ctrl-supp-company", {
			fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company"), reqd: 1,
		});
		this.controls.supp_from = make(".ctrl-supp-from", { fieldtype: "Date", fieldname: "from_date", label: __("From Date") });
		this.controls.supp_to = make(".ctrl-supp-to", { fieldtype: "Date", fieldname: "to_date", label: __("To Date") });
		if (default_company) this.controls.supp_company.set_value(default_company);

		// Supplier source toggle
		$(m).find(".ctrl-supp-source").html(`
			<div style="display:flex;flex-direction:column;gap:2px">
				<label style="font-size:11px;color:var(--text-muted)">${__("Source")}</label>
				<div class="btn-group btn-group-sm">
					<button class="btn btn-default btn-supp-source active" data-source="pi">${__("Purchase Invoice")}</button>
					<button class="btn btn-default btn-supp-source" data-source="pr">${__("Purchase Receipt")}</button>
				</div>
			</div>
		`);
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
				if (r.message) {
					$content.empty();
					this._render_item_history(r.message, $content);
				}
			},
		});
	}

	_render_item_history({ item_details, stock_metrics, purchases, sales }, $container) {
		$container.append(this._render_metrics_grid(item_details, stock_metrics));
		let $grid = $(`<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px">`).appendTo($container);
		this._render_transaction_panel($grid, purchases, "purchase");
		this._render_transaction_panel($grid, sales, "sale");
	}

	_render_metrics_grid(d, m) {
		const bc = this.base_currency;
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
					${row(__("Avg. Stock Rate"), format_currency(m.avg_rate, bc))}
					${row(__("Stock Value"), format_currency(m.stock_value, bc))}
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

	_render_transaction_panel($grid, rows, type) {
		const is_purchase = type === "purchase";
		const total_qty = rows.reduce((s, r) => s + (r.qty || 0), 0);
		const accent = is_purchase ? "var(--green)" : "var(--blue)";
		const label = is_purchase ? __("Purchases") : __("Sales");
		const bc = this.base_currency;
		const party_col = is_purchase ? __("Supplier") : __("Customer");
		const party_key = is_purchase ? "supplier" : "customer";
		const rate_label = is_purchase ? __("Val. Rate") : __("Base Rate");
		const rate_key = is_purchase ? "valuation_rate" : "base_rate";
		// For purchases: use PI link unless source is PR. _item_panel may not exist yet (safe fallback to PI).
		const doctype_slug = is_purchase
			? (this._item_panel && this._item_panel.source === "pr" ? "purchase-receipt" : "purchase-invoice")
			: "sales-invoice";

		const th = (label, align) =>
			`<th style="padding:5px 8px;${align ? "text-align:right;" : ""}border-bottom:2px solid ${accent};white-space:nowrap;color:var(--text-muted);font-weight:600">${label}</th>`;

		const empty_row = `<tr><td colspan="8" style="padding:12px;text-align:center" class="text-muted">${is_purchase ? __("No purchases found") : __("No sales found")}</td></tr>`;

		const body = rows.length ? rows.map((r, i) => `
			<tr style="${i % 2 ? "background:var(--control-bg)" : ""}">
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${frappe.datetime.str_to_user(r.date)}</td>
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/${doctype_slug}/${r.voucher_no}">${r.voucher_no}</a></td>
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r[party_key] || ""}</td>
				<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.qty, null, 2)}</td>
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.uom || ""}</td>
				<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.rate, r.currency)}</td>
				<td style="padding:4px 8px;text-align:right;font-weight:600;border-bottom:1px solid var(--border-color)">${format_currency(r[rate_key], bc)}</td>
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${this._status_pill(r.status)}</td>
			</tr>`).join("") : empty_row;

		$(`
			<div style="border:1px solid var(--border-color);border-radius:6px;overflow:hidden">
				<div style="background:var(--subtle-fg);padding:8px 12px;font-weight:600;display:flex;justify-content:space-between;border-bottom:2px solid ${accent}">
					<span style="color:${accent}">${label}</span>
					<span style="font-weight:400;font-size:12px;color:var(--text-muted)">${__("Total Qty: {0}", [format_number(total_qty, null, 2)])}</span>
				</div>
				<div style="max-height:280px;overflow-y:auto">
					<table style="width:100%;border-collapse:collapse;font-size:12px">
						<thead>
							<tr style="background:var(--subtle-fg)">
								${th(__("Date"))}
								${th(__("Voucher"))}
								${th(party_col)}
								${th(__("Qty"), true)}
								${th(__("UOM"))}
								${th(__("Rate"), true)}
								${th(rate_label, true)}
								${th(__("Status"))}
							</tr>
						</thead>
						<tbody>${body}</tbody>
					</table>
				</div>
			</div>
		`).appendTo($grid);
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
				if (r.message != null) {
					this._cust_state.rows = r.message;
					this._cust_state.party = customer;
					this._cust_state.company = company;
					$content.html(this._render_party_summary(r.message, "customer", customer, company, this._cust_state));
				}
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
				source: this._supp_source,
			},
			callback: (r) => {
				if (r.message != null) {
					this._supp_state.rows = r.message;
					this._supp_state.party = supplier;
					this._supp_state.company = company;
					$content.html(this._render_party_summary(r.message, "supplier", supplier, company, this._supp_state));
				}
			},
		});
	}

	// ── Shared: accordion summary table ──────────────────────────────────────

	_render_party_summary(rows, party_type, party, company, sort_state) {
		if (!rows.length)
			return `<div class="text-muted" style="padding:20px">${__("No transactions found")}</div>`;

		const is_customer = party_type === "customer";
		const count_col = is_customer ? __("Invoices") : __("Receipts");
		const rate_col = is_customer ? __("Avg Rate") : __("Avg Val. Rate");
		const date_col = is_customer ? __("Last Sale") : __("Last Purchase");
		const count_key = is_customer ? "invoice_count" : "receipt_count";
		const rate_key = is_customer ? "avg_rate" : "avg_valuation_rate";
		const date_key = is_customer ? "last_sale" : "last_purchase";
		const bc = this.base_currency;

		const accent = is_customer ? "var(--blue)" : "var(--green)";
		const sort_icon = (key) => {
			if (!sort_state || sort_state.sort_key !== key) return `<span style="opacity:.35;font-size:10px"> ↕</span>`;
			return sort_state.sort_dir === "asc" ? `<span style="font-size:10px"> ↑</span>` : `<span style="font-size:10px"> ↓</span>`;
		};
		const th = (label, key, align) => `
			<th class="th-sort-header" data-sort-key="${key}" data-party-type="${party_type}"
				style="padding:5px 8px;text-align:${align || "left"};color:var(--text-muted);font-weight:600;border-bottom:2px solid ${accent};cursor:pointer;white-space:nowrap;user-select:none">
				${label}${sort_icon(key)}
			</th>`;
		const th_plain = (label) => `
			<th style="padding:5px 8px;color:var(--text-muted);font-weight:600;border-bottom:2px solid ${accent}">
				${label}
			</th>`;

		return `
			<div style="margin-bottom:8px">
				<input type="search" class="party-search form-control form-control-sm" data-party-type="${party_type}"
					placeholder="${__("Filter items...")}" style="max-width:280px">
			</div>
			<table style="width:100%;border-collapse:collapse;font-size:12px" data-party-type="${party_type}">
				<thead>
					<tr style="background:var(--subtle-fg)">
						<th style="padding:5px 8px;width:28px;border-bottom:2px solid ${accent}"></th>
						${th(__("Item Code"), "item_code")}
						${th(__("Item Name"), "item_name")}
						${th(count_col, count_key, "right")}
						${th(__("Total Qty"), "total_qty", "right")}
						${th(rate_col, rate_key, "right")}
						${th(__("Total Amount"), "total_amount", "right")}
						${th(date_col, date_key)}
						${th_plain(__("Status"))}
					</tr>
				</thead>
				<tbody>
					${rows.map((r, i) => `
						<tr class="summary-row" data-item="${r.item_code}" data-party="${party}" data-party-type="${party_type}" data-company="${company}"
							style="${i % 2 ? "background:var(--control-bg)" : "background:var(--bg-color)"};cursor:pointer"
							title="${__("Click to expand transactions")}">
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color);color:var(--text-muted)">▶</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/item/${r.item_code}">${r.item_code}</a></td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.item_name}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r[count_key]}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.total_qty, null, 2)}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r[rate_key], bc)}</td>
							<td style="padding:4px 8px;text-align:right;font-weight:700;border-bottom:1px solid var(--border-color)">${format_currency(r.total_amount, bc)}</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r[date_key] ? frappe.datetime.str_to_user(r[date_key]) : "—"}</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${this._summary_status_pill(r.overdue_count || 0, r.unpaid_count || 0)}</td>
						</tr>
						<tr class="detail-row hidden" data-detail-for="${r.item_code}">
							<td colspan="9" style="padding:0;border-bottom:2px solid var(--border-color)">
								<div class="detail-content" style="padding:8px 24px;background:var(--card-bg)">
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

		// Bootstrap nav-tabs switching
		$(m).on("click", ".nav-link[data-tab]", (e) => {
			e.preventDefault();
			$(m).find(".nav-link[data-tab]").removeClass("active");
			$(e.currentTarget).addClass("active");
			$(m).find(".th-panel").addClass("hidden");
			$(m).find(`[data-panel="${$(e.currentTarget).data("tab")}"]`).removeClass("hidden");
		});

		$(m).on("click", ".btn-get-item", () => this._load_item_history());
		$(m).on("click", ".btn-get-customer", () => this._load_customer_history());
		$(m).on("click", ".btn-get-supplier", () => this._load_supplier_history());

		// Column sort on accordion summary tables
		$(m).on("click", ".th-sort-header", (e) => {
			e.stopPropagation();
			const key = $(e.currentTarget).data("sort-key");
			const party_type = $(e.currentTarget).data("party-type");
			const state = party_type === "customer" ? this._cust_state : this._supp_state;

			if (state.sort_key === key) {
				state.sort_dir = state.sort_dir === "asc" ? "desc" : "asc";
			} else {
				state.sort_key = key;
				state.sort_dir = "asc";
			}

			const sorted = [...state.rows].sort((a, b) => {
				const av = a[key] ?? "";
				const bv = b[key] ?? "";
				const cmp = av < bv ? -1 : av > bv ? 1 : 0;
				return state.sort_dir === "asc" ? cmp : -cmp;
			});

			const $content = $(m).find(party_type === "customer" ? ".customer-content" : ".supplier-content");
			$content.html(this._render_party_summary(sorted, party_type, state.party, state.company, state));
		});

		// Party search filter
		$(m).on("input", ".party-search", (e) => {
			const val = $(e.currentTarget).val().toLowerCase();
			const party_type = $(e.currentTarget).data("party-type");
			const $table = $(m).find(`table[data-party-type="${party_type}"]`);
			$table.find(".summary-row").each(function () {
				const text = $(this).text().toLowerCase();
				const $detail = $(this).next(".detail-row");
				if (val === "" || text.includes(val)) {
					$(this).removeClass("hidden");
				} else {
					$(this).addClass("hidden");
					$detail.addClass("hidden");
					$(this).find("td:first").text("▶");
				}
			});
		});

		// Supplier source toggle
		$(m).on("click", ".btn-supp-source", (e) => {
			$(m).find(".btn-supp-source").removeClass("active");
			$(e.currentTarget).addClass("active");
			this._supp_source = $(e.currentTarget).data("source");
		});

		// Accordion: expand/collapse summary rows
		$(m).on("click", ".summary-row", (e) => {
			if ($(e.target).is("a")) return;
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
					source: party_type === "supplier" ? this._supp_source : undefined,
				},
				callback: (r) => {
					const detail_doctype = is_customer
						? "sales-invoice"
						: (this._supp_source === "pr" ? "purchase-receipt" : "purchase-invoice");
					let html = this._render_detail_rows(r.message || [], is_customer, detail_doctype);
					$detail.find(".detail-content").html(html).data("loaded", true);
				},
			});
		});
	}

	_render_detail_rows(rows, is_customer, detail_doctype) {
		if (!rows.length)
			return `<span class="text-muted">${__("No transactions found")}</span>`;

		const rate_label = is_customer ? __("Base Rate") : __("Val. Rate");
		const rate_key = is_customer ? "base_rate" : "valuation_rate";
		const bc = this.base_currency;
		// detail_doctype is passed by the accordion handler so PI vs PR links correctly
		const doctype_slug = detail_doctype || (is_customer ? "sales-invoice" : "purchase-receipt");

		return `
			<table style="width:100%;border-collapse:collapse;font-size:11px">
				<thead>
					<tr style="background:var(--subtle-fg)">
						<th style="padding:3px 8px;text-align:left;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Date")}</th>
						<th style="padding:3px 8px;text-align:left;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Voucher No")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Qty")}</th>
						<th style="padding:3px 8px;text-align:left;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("UOM")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Rate")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted);font-weight:700;border-bottom:1px solid var(--border-color)">${rate_label}</th>
						<th style="padding:3px 8px;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Status")}</th>
					</tr>
				</thead>
				<tbody>
					${rows.map((r, i) => `
						<tr style="${i % 2 ? "background:var(--subtle-fg)" : ""}">
							<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)">${frappe.datetime.str_to_user(r.date)}</td>
							<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/${doctype_slug}/${r.voucher_no}">${r.voucher_no}</a></td>
							<td style="padding:3px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.qty, null, 2)}</td>
							<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)">${r.uom || ""}</td>
							<td style="padding:3px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.rate, r.currency)}</td>
							<td style="padding:3px 8px;text-align:right;font-weight:600;border-bottom:1px solid var(--border-color)">${format_currency(r[rate_key], bc)}</td>
							<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)">${this._status_pill(r.status)}</td>
						</tr>`).join("")}
				</tbody>
			</table>`;
	}

	_summary_status_pill(overdue_count, unpaid_count) {
		if (overdue_count > 0)
			return `<span class="indicator-pill red" style="font-size:10px">${overdue_count} ${__("Overdue")}</span>`;
		if (unpaid_count > 0)
			return `<span class="indicator-pill yellow" style="font-size:10px">${unpaid_count} ${__("Unpaid")}</span>`;
		return `<span class="indicator-pill green" style="font-size:10px">${__("All Paid")}</span>`;
	}

	_status_pill(status) {
		const map = {
			"Paid": "green",
			"Completed": "green",
			"Partly Paid": "orange",
			"Unpaid": "yellow",
			"To Bill": "yellow",
			"Overdue": "red",
			"Return": "gray",
			"Return Issued": "gray",
			"Credit Note Issued": "gray",
			"Debit Note Issued": "gray",
		};
		const colour = map[status] || "gray";
		return `<span class="indicator-pill ${colour}" style="font-size:10px;white-space:nowrap">${__(status || "—")}</span>`;
	}
}
