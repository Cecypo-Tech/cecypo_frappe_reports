// Copyright (c) 2026, Cecypo and contributors
// For license information, please see license.txt

// A fetch that has not answered by then is treated as lost: the panel offers Retry.
const FETCH_TIMEOUT_MS = 20000;

const _ICONS = {
	copy:  `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`,
	link:  `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>`,
	// Replaces the former separate print and email icons: both routes now live inside the
	// statement dialog, which also offers the branded Statement of Accounts.
	statement: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/></svg>`,
	export: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`,
	refresh: `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>`,
	info:  `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
};

frappe.pages["transaction-history"].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Transaction History"),
		single_column: true,
	});
	new TransactionHistoryPage(page);
};

frappe.pages["transaction-history"].on_page_show = function () {
	$("body").addClass("th-compact");
};

frappe.pages["transaction-history"].on_page_hide = function () {
	$("body").removeClass("th-compact");
};

class TransactionHistoryPage {
	constructor(page) {
		this.page = page;
		this.base_currency = frappe.defaults.get_default("currency") || "";
		this.controls = {};
		this._cust_state = { rows: [], party: null, company: null, sort_key: "total_amount", sort_dir: "desc" };
		this._supp_state = { rows: [], party: null, company: null, sort_key: "total_amount", sort_dir: "desc" };
		this._recv_state = { rows: [], company: null, as_of_date: null, sort_key: "outstanding", sort_dir: "desc" };
		this._pay_state = { rows: [], company: null, as_of_date: null, sort_key: "outstanding", sort_dir: "desc" };
		this._supp_source = "pi";
		this._item_panel = {
			items: [],          // [{item_code, item_name}]
			active: null,       // item_code shown in .item-content
			view: "history",    // "history" | "card"
			can_see_cost: true, // from get_item_history
			history: {},        // item_code → get_item_history payload
			card: {},           // item_code → stock card payload (Task 6)
		};
		this._pricing_panel = {
			items: [],
			active_tab: null,
		};
		this._render();
		this._bind_tabs();
		this._render_pricing_checklist();
		this._read_url_params();
	}

	// ── Layout ────────────────────────────────────────────────────────────────

	_inject_styles() {
		if (document.getElementById("th-responsive-styles")) return;
		const style = document.createElement("style");
		style.id = "th-responsive-styles";
		style.textContent = `
			@media (max-width: 767px) {
				.item-chips, .item-nav, .th-view-switch { flex-wrap: wrap !important; }
				.item-select { width: 100% !important; max-width: none !important; }
				.item-results-search { max-width: none !important; flex: 1 1 100% !important; }
				.item-chip, .item-prev, .item-next, .item-clear, .th-view-switch .btn { min-height: 32px; }
				.th-picker-bar { flex-direction: column !important; }
				.th-picker-bar > div { min-width: 0 !important; width: 100% !important; }
				.th-picker-dialog .modal-dialog { margin: 0 !important; max-width: none !important; width: 100% !important; }
				.th-picker-dialog .modal-content { min-height: 100vh; border-radius: 0 !important; }
				.item-results-grid { grid-template-columns: 1fr !important; }
				.pricing-body { flex-direction: column !important; }
				.pricing-panel-sidebar {
					width: 100% !important;
					min-width: 0 !important;
					margin-right: 0 !important;
					margin-bottom: 12px !important;
				}
				.transaction-history { padding: 8px !important; }
				.transaction-history .nav-tabs {
					flex-wrap: nowrap !important;
					overflow-x: auto;
					-webkit-overflow-scrolling: touch;
					scrollbar-width: none;
					padding-bottom: 2px;
				}
				.transaction-history .nav-tabs::-webkit-scrollbar { display: none; }
				.th-metrics-3col { grid-template-columns: 1fr !important; }
				.th-stats-3col { grid-template-columns: 1fr 1fr !important; }
				.th-panel > div[style*="display:flex"] > div[style*="min-width"] {
					min-width: 0 !important;
					width: 100% !important;
				}
			}
			.th-action-btn {
				display: inline-flex;
				align-items: center;
				justify-content: center;
				width: 26px;
				height: 26px;
				padding: 0;
				border: none;
				background: transparent;
				border-radius: 4px;
				cursor: pointer;
				color: var(--text-muted);
				transition: background .1s, color .1s;
				flex-shrink: 0;
			}
			.th-action-btn:hover {
				background: var(--control-bg);
				color: var(--text-color);
			}
			.th-party-info-btn {
				display: inline-flex;
				align-items: center;
				cursor: pointer;
				margin-left: 4px;
				vertical-align: middle;
				color: var(--text-muted);
				transition: color .1s, opacity .1s;
			}
			.th-party-info-btn:hover { color: var(--text-color); }
			.th-party-info-btn.is-amber { color: var(--orange-500, #f97316); }
			.th-party-info-btn.is-red { color: var(--red-500); }
			.th-btn-wrap { display: flex; align-items: flex-end; padding-bottom: 1px; }
			.item-chip {
				display: inline-flex; align-items: center; gap: 6px;
				padding: 2px 4px 2px 10px; border: 1px solid var(--border-color); border-radius: 12px;
				font-size: 12px; cursor: pointer; background: var(--control-bg);
			}
			.item-chip.active { background: var(--primary); border-color: var(--primary); color: #fff; }
			.item-chip-x { color: inherit; opacity: .6; padding: 0 4px; text-decoration: none !important; }
			.item-chip-x:hover { opacity: 1; }
			.th-picker-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 12px; }
			.th-picker-table th, .th-picker-table td {
				padding: 4px 8px; border-bottom: 1px solid var(--border-color); white-space: nowrap; background: var(--fg-color);
			}
			.th-picker-table th { color: var(--text-muted); font-weight: 600; position: sticky; top: 0; z-index: 2; }
			.th-pick-sticky { position: sticky; left: 0; z-index: 1; }
			.th-picker-table th.th-pick-sticky { z-index: 3; }
			.th-pick-sticky.th-pick-box { width: 32px; min-width: 32px; max-width: 32px; }
			.th-pick-sticky.th-pick-code { left: 32px; }
			.th-card-table th, .th-card-table td.th-card-sticky { background: var(--fg-color); }
			.th-card-sticky { position: sticky; z-index: 1; }
			.th-card-table th.th-card-sticky { z-index: 3; }
			.th-card-date { left: 0; min-width: 92px; }
			.th-card-voucher { left: 92px; }
			.th-pick-wh { cursor: pointer; }
			.th-pick-wh:hover { text-decoration: underline; color: var(--primary); }
		`;
		document.head.appendChild(style);
	}

	_render() {
		this._inject_styles();
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
					<li class="nav-item">
						<a class="nav-link" href="#" data-tab="receivables">${__("Receivables")}</a>
					</li>
					<li class="nav-item">
						<a class="nav-link" href="#" data-tab="payables">${__("Payables")}</a>
					</li>
					<li class="nav-item">
						<a class="nav-link" href="#" data-tab="pricing">${__("Pricing")}</a>
					</li>
				</ul>

				<div class="th-panel" data-panel="item">
					<div class="item-filter-bar" style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:12px">
						<div class="ctrl-item-company" style="min-width:180px"></div>
						<div class="ctrl-item-from" style="min-width:120px"></div>
						<div class="ctrl-item-to" style="min-width:120px"></div>
						<div class="ctrl-item-warehouse" style="min-width:160px"></div>
						<div class="th-btn-wrap"><button class="btn btn-primary btn-sm btn-pick-items">${__("Select Items…")}</button></div>
						<div class="th-btn-wrap">
							<div class="btn-group th-view-switch" role="group">
								<button class="btn btn-sm btn-default active" data-view="history">${__("History")}</button>
								<button class="btn btn-sm btn-default" data-view="card">${__("Stock Card")}</button>
							</div>
						</div>
					</div>
					<div class="item-chips" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px"></div>
					<div class="item-nav hidden" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:10px">
						<select class="form-control form-control-sm item-select" style="width:auto;max-width:320px"></select>
						<button class="btn btn-sm btn-default item-prev" title="${__("Previous item")}">‹</button>
						<button class="btn btn-sm btn-default item-next" title="${__("Next item")}">›</button>
						<button class="btn btn-sm btn-default item-clear" title="${__("Close all items")}">${__("Clear all")}</button>
						${this._refresh_btn("items")}
						<input type="search" class="item-results-search form-control form-control-sm"
							placeholder="${__("Filter rows...")}" style="max-width:280px">
					</div>
					<div class="th-content item-content">${this._item_empty_html()}</div>
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
						<div class="th-btn-wrap"><button class="btn btn-primary btn-sm btn-get-supplier">${__("Get History")}</button></div>
					</div>
					<div class="th-content supplier-content"></div>
				</div>

				<div class="th-panel hidden" data-panel="receivables">
					<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px">
						<div class="ctrl-recv-company" style="min-width:180px"></div>
						<div class="ctrl-recv-as-of" style="min-width:140px"></div>
						<div class="ctrl-recv-customer" style="min-width:220px"></div>
						<div class="ctrl-recv-show-future" style="min-width:160px"></div>
						<div class="th-btn-wrap"><button class="btn btn-primary btn-sm btn-get-receivables">${__("Get")}</button></div>
					</div>
					<div class="th-content receivables-content"></div>
				</div>

				<div class="th-panel hidden" data-panel="payables">
					<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px">
						<div class="ctrl-pay-company" style="min-width:180px"></div>
						<div class="ctrl-pay-as-of" style="min-width:140px"></div>
						<div class="ctrl-pay-supplier" style="min-width:220px"></div>
						<div class="ctrl-pay-show-future" style="min-width:160px"></div>
						<div class="th-btn-wrap"><button class="btn btn-primary btn-sm btn-get-payables">${__("Get")}</button></div>
					</div>
					<div class="th-content payables-content"></div>
				</div>

				<div class="th-panel hidden" data-panel="pricing">
					<div class="pricing-filter-bar" style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:12px">
						<div class="ctrl-pricing-company" style="min-width:180px"></div>
						<div class="ctrl-pricing-from" style="min-width:120px"></div>
						<div class="ctrl-pricing-to" style="min-width:120px"></div>
						<div class="ctrl-pricing-price-list" style="min-width:160px"></div>
					</div>
					<div class="pricing-body" style="display:flex;gap:0;align-items:flex-start">
						<div class="pricing-panel-sidebar" style="width:224px;min-width:224px;border:1px solid var(--border-color);border-radius:6px;padding:10px;margin-right:14px;flex-shrink:0;position:relative;z-index:1">
							<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
								<span class="pricing-panel-label" style="font-weight:600;font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em">${__("Items")}</span>
								<button class="btn btn-xs btn-default btn-toggle-pricing-panel" title="${__("Toggle panel")}" style="padding:1px 6px">☰</button>
							</div>
							<div class="pricing-panel-body">
								<div class="ctrl-pricing-group" style="margin-bottom:6px"></div>
								<div class="ctrl-pricing-add" style="margin-bottom:8px"></div>
								<div class="pricing-checklist" style="max-height:45vh;overflow-y:auto;margin-bottom:8px;border-top:1px solid var(--border-color);padding-top:6px"></div>
								<div style="display:flex;gap:4px">
									<button class="btn btn-primary btn-sm btn-run-pricing" style="flex:1" disabled>${__("Run (0)")}</button>
									<button class="btn btn-default btn-sm btn-clear-pricing" title="${__("Clear all")}" style="padding:4px 8px">✕</button>
								</div>
								<div style="margin-top:6px">${this._refresh_btn("pricing")}</div>
							</div>
						</div>
						<div class="pricing-results" style="flex:1;min-width:0">
							<div class="pricing-tabs-strip"></div>
							<div class="th-content pricing-content"></div>
						</div>
					</div>
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

		// Item tab. Any filter change re-runs the selected items; debounced so a burst of
		// change events (and the picker's warehouse-cell click) yields exactly one fetch.
		const rerun = () => {
			clearTimeout(this._rerun_timer);
			this._rerun_timer = setTimeout(() => {
				if (this._item_panel.items.length) this._run_item_history();
			}, 150);
		};
		this._rerun_item_history = rerun;
		this.controls.item_company = make(".ctrl-item-company", {
			fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company"), reqd: 1, change: rerun,
		});
		this.controls.item_from = make(".ctrl-item-from", { fieldtype: "Date", fieldname: "from_date", label: __("From Date"), change: rerun });
		this.controls.item_to = make(".ctrl-item-to", { fieldtype: "Date", fieldname: "to_date", label: __("To Date"), change: rerun });
		this.controls.item_warehouse = make(".ctrl-item-warehouse", {
			fieldtype: "Link", options: "Warehouse", fieldname: "warehouse", label: __("Warehouse"), change: rerun,
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

		// Supplier source select
		this.controls.supp_source = make(".ctrl-supp-source", {
			fieldtype: "Select",
			fieldname: "supp_source",
			label: __("Source"),
			options: "Purchase Invoice\nPurchase Receipt",
		});
		this.controls.supp_source.set_value("Purchase Invoice");

		// Receivables tab
		const today = frappe.datetime.get_today();
		this.controls.recv_company = make(".ctrl-recv-company", {
			fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company"), reqd: 1,
		});
		this.controls.recv_as_of = make(".ctrl-recv-as-of", {
			fieldtype: "Date", fieldname: "as_of_date", label: __("As Of Date"),
		});
		this.controls.recv_customer = make(".ctrl-recv-customer", {
			fieldtype: "Link", options: "Customer", fieldname: "customer", label: __("Customer"),
		});
		this.controls.recv_show_future = make(".ctrl-recv-show-future", {
			fieldtype: "Check", fieldname: "show_future_payments", label: __("Show Future Payments"),
		});
		if (default_company) this.controls.recv_company.set_value(default_company);
		this.controls.recv_as_of.set_value(today);

		// Payables tab
		this.controls.pay_company = make(".ctrl-pay-company", {
			fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company"), reqd: 1,
		});
		this.controls.pay_as_of = make(".ctrl-pay-as-of", {
			fieldtype: "Date", fieldname: "as_of_date", label: __("As Of Date"),
		});
		this.controls.pay_supplier = make(".ctrl-pay-supplier", {
			fieldtype: "Link", options: "Supplier", fieldname: "supplier", label: __("Supplier"),
		});
		this.controls.pay_show_future = make(".ctrl-pay-show-future", {
			fieldtype: "Check", fieldname: "show_future_payments", label: __("Show Future Payments"),
		});
		if (default_company) this.controls.pay_company.set_value(default_company);
		this.controls.pay_as_of.set_value(today);

		// Pricing tab
		this.controls.pricing_company = make(".ctrl-pricing-company", {
			fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company"), reqd: 1,
		});
		this.controls.pricing_from = make(".ctrl-pricing-from", {
			fieldtype: "Date", fieldname: "from_date", label: __("From Date"),
		});
		this.controls.pricing_to = make(".ctrl-pricing-to", {
			fieldtype: "Date", fieldname: "to_date", label: __("To Date"),
		});
		this.controls.pricing_price_list = make(".ctrl-pricing-price-list", {
			fieldtype: "Link", options: "Price List", fieldname: "price_list", label: __("Price List"),
		});
		this.controls.pricing_group = make(".ctrl-pricing-group", {
			fieldtype: "Link", options: "Item Group", fieldname: "item_group", label: __("Item Group"),
		});
		this.controls.pricing_add = make(".ctrl-pricing-add", {
			fieldtype: "Link", options: "Item", fieldname: "item_add", label: __("Add Item"),
		});
		this.controls.pricing_add.get_query = () => {
			const group = this.controls.pricing_group ? this.controls.pricing_group.get_value() : null;
			return {
				query: "cecypo_frappe_reports.cecypo_frappe_reports.api.item_query",
				filters: group ? { item_group: group } : {},
			};
		};
		if (default_company) this.controls.pricing_company.set_value(default_company);
	}

	// ── Pricing Checklist ─────────────────────────────────────────────────────

	_render_pricing_checklist() {
		const m = this.page.main;
		const $list = $(m).find(".pricing-checklist");
		const items = this._pricing_panel.items;

		if (!items.length) {
			$list.html(`<span class="text-muted" style="font-size:12px">${__("No items added yet")}</span>`);
		} else {
			$list.html(items.map((item, i) => `
				<div class="pricing-check-row" style="display:flex;align-items:center;padding:3px 0;border-bottom:1px solid var(--border-color)">
					<label style="display:flex;align-items:center;gap:5px;cursor:pointer;font-size:12px;flex:1;min-width:0;overflow:hidden">
						<input type="checkbox" class="pricing-checkbox" data-idx="${i}" ${item.checked ? "checked" : ""} style="flex-shrink:0">
						<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${item.item_name || item.item_code}">${item.item_name || item.item_code}</span>
					</label>
					<button class="btn-remove-pricing-item" data-idx="${i}"
						style="border:none;background:none;cursor:pointer;color:var(--text-muted);padding:0 4px;font-size:14px;line-height:1;flex-shrink:0">×</button>
				</div>
			`).join(""));
		}

		const checked = items.filter(it => it.checked).length;
		$(m).find(".btn-run-pricing").text(__("Run ({0})", [checked])).prop("disabled", checked === 0);
	}

	_add_item_to_pricing_panel(item_code, item_name) {
		if (this._pricing_panel.items.find(it => it.item_code === item_code)) return;
		this._pricing_panel.items.push({ item_code, item_name: item_name || item_code, checked: true });
		this._render_pricing_checklist();
	}

	// ── Item picker ──────────────────────────────────────────────────────────

	_open_item_picker() {
		const company = this.controls.item_company.get_value();
		if (!company) { frappe.msgprint(__("Company is required")); return; }

		const dialog = new frappe.ui.Dialog({
			title: __("Select Items"),
			size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "picker" }],
			primary_action_label: __("Use selected ({0})", [0]),
			primary_action: () => {
				if (!dialog._sel.size) return;
				const p = this._item_panel;
				p.items = [...dialog._sel.values()];
				for (const code of Object.keys(p.history)) { // unticked items drop their loaded results
					if (!dialog._sel.has(code)) { delete p.history[code]; delete p.card[code]; }
				}
				dialog.hide();
				this._run_item_history();
			},
			on_hide: () => dialog.$wrapper.remove(),
		});
		// Selection survives searches; pre-seeded with what is already in the navigator.
		dialog._sel = new Map(this._item_panel.items.map(it => [it.item_code, { ...it }]));
		dialog._rows = {}; // item_code → last search row, for item_name on tick
		dialog.$wrapper.addClass("th-picker-dialog");

		const $body = $(dialog.fields_dict.picker.wrapper).addClass("th-export-scope").html(`
			<div class="th-picker-bar" style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:10px">
				<div class="th-picker-search" style="flex:2;min-width:220px">
					<input type="search" class="form-control" placeholder="${__("Search item code or name (min. 2 characters)")}">
				</div>
				<div class="th-picker-group" style="flex:1;min-width:180px"></div>
				<div style="flex:0 0 auto;align-self:center">${this._export_btn(__("Items"))}</div>
			</div>
			<div class="th-picker-results" style="overflow-x:auto;max-height:60vh;overflow-y:auto"></div>
			<div class="th-picker-note text-muted" style="font-size:12px;margin-top:6px"></div>
			<div class="th-pick-count text-muted" style="font-size:12px;margin-top:4px"></div>
		`);
		dialog._group = frappe.ui.form.make_control({
			parent: $body.find(".th-picker-group")[0],
			df: {
				fieldtype: "Link", options: "Item Group", fieldname: "item_group", label: __("Item Group"),
				change: () => this._picker_search(dialog),
			},
			render_input: true,
		});
		// The Link control sits in a frappe-control wrapper with bottom margin; drop it so both line up.
		$body.find(".th-picker-group .frappe-control").css("margin-bottom", 0);

		const debounced = frappe.utils.debounce(() => this._picker_search(dialog), 300);
		$body.on("input", ".th-picker-search input", debounced);
		$body.on("click", ".btn-export-table", (e) => this._export_table($(e.currentTarget)));

		$body.on("change", ".th-pick", (e) => {
			const code = $(e.currentTarget).attr("data-item");
			if (e.currentTarget.checked) {
				const row = dialog._rows[code] || {};
				dialog._sel.set(code, { item_code: code, item_name: row.item_name || code });
			} else {
				dialog._sel.delete(code);
			}
			this._picker_sync(dialog);
		});
		$body.on("change", ".th-pick-all", (e) => {
			const on = e.currentTarget.checked;
			$body.find(".th-pick").each((_, el) => {
				const code = $(el).attr("data-item");
				if (on) dialog._sel.set(code, { item_code: code, item_name: (dialog._rows[code] || {}).item_name || code });
				else dialog._sel.delete(code);
			});
			this._picker_sync(dialog);
		});
		// A warehouse qty cell opens that item's Stock Card for that warehouse.
		$body.on("click", ".th-pick-wh", (e) => {
			const code = $(e.currentTarget).attr("data-item");
			const wh = $(e.currentTarget).attr("data-warehouse");
			const p = this._item_panel;
			dialog._sel.set(code, { item_code: code, item_name: (dialog._rows[code] || {}).item_name || code });
			p.items = [...dialog._sel.values()];
			p.active = code;
			p.view = "card";
			dialog.hide();
			if (wh) this.controls.item_warehouse.set_value(wh);
			this._rerun_item_history(); // debounced with the warehouse change event: one run
		});

		this._picker_search(dialog);
		this._picker_sync(dialog);
		dialog.show();
	}

	_picker_search(dialog) {
		const $wrap = dialog.$wrapper.find(".th-picker-results");
		const txt = (dialog.$wrapper.find(".th-picker-search input").val() || "").trim();
		const group = dialog._group.get_value() || null;
		dialog._gen = (dialog._gen || 0) + 1;
		const gen = dialog._gen;

		if (txt.length < 2 && !group) {
			$wrap.html(`<div class="text-muted" style="padding:16px">${__("Type at least 2 characters or choose an Item Group")}</div>`);
			dialog.$wrapper.find(".th-picker-note").empty();
			return;
		}
		$wrap.html(`<div class="text-muted" style="padding:16px">${__("Loading...")}</div>`);
		const fail = () => $wrap.html(`<div class="text-muted" style="padding:16px">${__("Could not search items.")}</div>`);
		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.search_items",
			args: { company: this.controls.item_company.get_value(), txt, item_group: group },
			callback: (r) => {
				if (gen !== dialog._gen) return; // superseded search
				if (!r.message) return fail();
				this._render_picker_table($wrap, r.message);
				dialog._rows = {};
				r.message.items.forEach(it => { dialog._rows[it.item_code] = it; });
				dialog.$wrapper.find(".th-picker-note").text(
					r.message.truncated ? __("Showing first {0} — refine your search", [100]) : ""
				);
				this._picker_sync(dialog);
			},
			error: () => {
				if (gen === dialog._gen) fail();
			},
		});
	}

	_render_picker_table($wrap, data) {
		const esc = frappe.utils.escape_html;
		const bc = this.base_currency;
		const mobile = window.innerWidth < 768;
		const items = data.items || [];
		if (!items.length) {
			$wrap.html(`<div class="text-muted" style="padding:16px">${__("No items found")}</div>`);
			return;
		}
		// One column per warehouse when few enough to fit; otherwise (or on phones) a single Stock column.
		const whs = !mobile && data.warehouses.length <= 6 ? data.warehouses : null;
		const qty = (v) => (v ? format_number(v, null, 2) : "—");
		const wh_cell = (it, wh, v) =>
			`<td class="th-pick-wh" data-item="${esc(it.item_code)}" data-warehouse="${esc(wh)}" title="${__("Open Stock Card")}" style="text-align:right">${qty(v)}</td>`;

		$wrap.html(`
			<table class="th-picker-table">
				<thead><tr>
					<th class="th-pick-sticky th-pick-box"><input type="checkbox" class="th-pick-all"></th>
					<th class="th-pick-sticky th-pick-code">${__("Item Code")}</th>
					<th>${__("Item Name")}</th>
					${mobile ? "" : `<th>${__("Group")}</th>`}
					<th>${__("UOM")}</th>
					<th style="text-align:right">${__("Sell Price")}</th>
					${whs ? whs.map(wh => `<th style="text-align:right">${esc(wh)}</th>`).join("") : `<th style="text-align:right">${__("Stock")}</th>`}
					${data.can_see_cost ? `<th style="text-align:right">${__("Cost")}</th>` : ""}
				</tr></thead>
				<tbody>
					${items.map(it => `<tr>
						<td class="th-pick-sticky th-pick-box"><input type="checkbox" class="th-pick" data-item="${esc(it.item_code)}"></td>
						<td class="th-pick-sticky th-pick-code">${esc(it.item_code)}</td>
						<td>${esc(it.item_name)}</td>
						${mobile ? "" : `<td>${esc(it.item_group)}</td>`}
						<td>${esc(it.stock_uom)}</td>
						<td style="text-align:right">${it.sell_price == null ? "—" : format_currency(it.sell_price, bc)}</td>
						${whs ? whs.map(wh => wh_cell(it, wh, (it.stock || {})[wh])).join("") : wh_cell(it, "", it.total_qty)}
						${data.can_see_cost ? `<td style="text-align:right">${it.cost == null ? "—" : format_currency(it.cost, bc)}</td>` : ""}
					</tr>`).join("")}
				</tbody>
			</table>
		`);
	}

	// Reflect dialog._sel in the checkboxes, header box, footer count and primary label.
	_picker_sync(dialog) {
		const sel = dialog._sel;
		const $boxes = dialog.$wrapper.find(".th-pick");
		$boxes.each((_, el) => { el.checked = sel.has($(el).attr("data-item")); });
		dialog.$wrapper.find(".th-pick-all").prop("checked", $boxes.length > 0 && $boxes.filter(":checked").length === $boxes.length);
		dialog.$wrapper.find(".th-pick-count").text(__("{0} selected", [sel.size]));
		dialog.set_btn_label(dialog.get_primary_btn(), __("Use selected ({0})", [sel.size]));
		sel.size ? dialog.enable_primary_action() : dialog.disable_primary_action();
	}

	// ── Item navigator ───────────────────────────────────────────────────────

	_item_empty_html() {
		return `<div class="text-muted" style="padding:20px">${__("Click \"Select Items…\" to choose the items to look at.")}</div>`;
	}

	_run_item_history(refresh = false) {
		const company = this.controls.item_company.get_value();
		if (!company) { frappe.msgprint(__("Company is required")); return; }
		const p = this._item_panel;
		if (!p.items.length) return;

		const from_date = this.controls.item_from.get_value() || null;
		const to_date = this.controls.item_to.get_value() || null;
		const warehouse = this.controls.item_warehouse.get_value() || null;

		const args = { company, from_date, to_date, warehouse };
		const unchanged = !refresh && p.args && JSON.stringify(args) === JSON.stringify(p.args);
		if (unchanged) { // same filters: fetch only the items that were never requested, keep the rest
			const gen = this._run_generation;
			p.items.filter(it => !(it.item_code in p.history)).forEach(it => this._fetch_item_history(it.item_code, gen));
			this._show_item(p.items.some(i => i.item_code === p.active) ? p.active : p.items[0].item_code);
			return;
		}

		// Generation counter: discard callbacks from superseded runs
		this._run_generation = (this._run_generation || 0) + 1;
		const gen = this._run_generation;

		p.args = args;
		p.history = {};
		p.card = {};
		this._show_item(p.items.some(i => i.item_code === p.active) ? p.active : p.items[0].item_code, refresh);
		p.items.forEach(item => this._fetch_item_history(item.item_code, gen, refresh));
	}

	// One item's history. `null` in p.history marks a failed or timed-out fetch, which
	// _show_item renders as a Retry prompt instead of an endless "Loading…".
	_fetch_item_history(item_code, gen, refresh = false) {
		const p = this._item_panel;
		delete p.history[item_code];
		const show = () => { if (p.active === item_code && p.view === "history") this._show_item(item_code); };
		const failed = () => {
			if (gen !== this._run_generation || p.history[item_code]) return; // stale, or a retry already succeeded
			p.history[item_code] = null;
			show();
		};
		const timer = setTimeout(failed, FETCH_TIMEOUT_MS);
		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_item_history",
			args: { item: item_code, ...p.args, refresh: refresh ? 1 : 0 },
			always: () => clearTimeout(timer),
			callback: (r) => {
				if (gen !== this._run_generation) return; // stale — discard
				if (!r.message) return failed();
				p.can_see_cost = r.message.can_see_cost !== false;
				r.message._fetched_at = r.th_fetched_at;
				p.history[item_code] = r.message;
				show();
			},
			error: failed,
		});
	}

	_retry_html(message) {
		return `<div class="text-muted" style="padding:20px">${message} <a href="#" class="th-retry">${__("Retry")}</a></div>`;
	}

	_show_item(item_code, refresh = false) {
		const p = this._item_panel;
		const $content = $(this.page.main).find(".item-content");
		p.active = item_code;
		this._render_item_nav();
		if (p.view === "card") { this._load_stock_card(item_code, refresh); return; }

		const data = p.history[item_code];
		$content.empty();
		if (data === null) { $content.html(this._retry_html(__("Could not load item history."))); return; }
		if (!data) {
			$content.html(`<div class="text-muted" style="padding:20px">${__("Loading...")}</div>`);
			return;
		}
		this._render_item_history(data, $content);
		this._stamp($(this.page.main).find(".item-nav"), data._fetched_at);
		$(this.page.main).find(".item-results-search").trigger("input"); // keep the active row filter
	}

	// ── Stock card ───────────────────────────────────────────────────────────

	_load_stock_card(item_code, refresh = false) {
		const p = this._item_panel;
		const $content = $(this.page.main).find(".item-content");
		if (p.card[item_code]) { this._paint_stock_card(item_code); return; }
		$content.html(`<div class="text-muted" style="padding:20px">${__("Loading...")}</div>`);
		const gen = this._run_generation;
		const cache = p.card;
		const from_date = this.controls.item_from.get_value() || null;
		const stale = () => gen !== this._run_generation || cache !== p.card;
		const fail = (message) => {
			if (stale() || cache[item_code]) return;
			if (p.active === item_code && p.view === "card") $content.html(this._retry_html(message));
		};
		const timer = setTimeout(() => fail(__("Taking too long.")), FETCH_TIMEOUT_MS);
		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_stock_card",
			args: {
				item: item_code,
				company: this.controls.item_company.get_value(),
				from_date,
				to_date: this.controls.item_to.get_value() || null,
				warehouse: this.controls.item_warehouse.get_value() || null,
				refresh: refresh ? 1 : 0,
			},
			always: () => clearTimeout(timer),
			callback: (r) => {
				if (stale()) return;
				if (!r.message) return fail(__("Could not load the stock card."));
				cache[item_code] = { data: r.message, from_date, at: r.th_fetched_at };
				if (p.active === item_code && p.view === "card") this._paint_stock_card(item_code);
			},
			error: () => fail(__("Could not load the stock card.")),
		});
	}

	_paint_stock_card(item_code) {
		const p = this._item_panel;
		const $content = $(this.page.main).find(".item-content");
		const { data, from_date, at } = p.card[item_code];
		this._stamp($(this.page.main).find(".item-nav"), at);
		const it = p.items.find(i => i.item_code === item_code) || { item_code, item_name: "" };
		const esc = frappe.utils.escape_html;
		$content.empty().append(`<div style="font-weight:600;margin-bottom:8px">${__("Stock Card")}: ${esc(it.item_code)} ${esc(it.item_name)}</div>`);
		this._render_stock_card(data, $content, from_date);
		$(this.page.main).find(".item-results-search").trigger("input"); // keep the active row filter
	}

	_render_stock_card(data, $container, from_date) {
		const esc = frappe.utils.escape_html;
		const bc = this.base_currency;
		const cost = !!data.can_see_cost;
		const multi = !data.single_warehouse;
		const num = (v) => format_number(v, null, 2);
		const td = (v, extra = "") => `<td style="padding:4px 8px;border-bottom:1px solid var(--border-color);white-space:nowrap;${extra}">${v}</td>`;
		const right = "text-align:right;";
		const heads = [["#", ""], [__("Date"), "th-card-sticky th-card-date"], [__("Voucher"), "th-card-sticky th-card-voucher"], [__("Party"), ""]];
		if (multi) heads.push([__("Warehouse"), ""]);
		heads.push([__("Rate"), "r"], [__("Qty In"), "r"], [__("Qty Out"), "r"], [__("Balance"), "r"]);
		if (cost) heads.push([__("Cost Rate"), "r"], [__("Value Change"), "r"], [__("Stock Value"), "r"]);
		const ncols = heads.length;
		const stick = (cls) => `class="${cls}" style="padding:4px 8px;border-bottom:1px solid var(--border-color);white-space:nowrap;"`;

		const rows = [];
		const bg = (i) => (i % 2 ? "background:var(--control-bg);" : "");
		let i = 0;
		if (from_date) {
			const blanks = (n) => td("").repeat(n);
			rows.push(`<tr style="font-style:italic;${bg(i++)}">
				${td("")}<td ${stick("th-card-sticky th-card-date")}>${esc(frappe.datetime.str_to_user(from_date))}</td>
				<td ${stick("th-card-sticky th-card-voucher")}>${__("Opening")}</td>${td("")}${multi ? td("") : ""}${blanks(3)}
				${td(`<b>${num(data.opening_qty)}</b>`, right)}
				${cost ? td("") + td("") + td(data.opening_value != null ? format_currency(data.opening_value, bc) : "", right) : ""}
			</tr>`);
		}
		(data.rows || []).forEach((r, n) => {
			const b = bg(i++);
			rows.push(`<tr style="${b}">
				${td(n + 1)}
				<td ${stick("th-card-sticky th-card-date")}>${esc(frappe.datetime.str_to_user(r.posting_date))}</td>
				<td ${stick("th-card-sticky th-card-voucher")}><a href="/app/${esc(frappe.router.slug(r.voucher_type))}/${encodeURIComponent(r.voucher_no)}" target="_blank" rel="noopener">${esc(r.voucher_no)}</a></td>
				${td(esc(r.party || ""))}
				${multi ? td(esc(r.warehouse || "")) : ""}
				${td(r.rate == null ? "—" : format_currency(r.rate, bc), right)}
				${td(r.qty_in ? num(r.qty_in) : "", right)}
				${td(r.qty_out ? num(r.qty_out) : "", right + "color:var(--red);")}
				${td(`<b>${num(r.balance)}</b>`, right)}
				${cost ? td(r.valuation_rate == null ? "—" : format_currency(r.valuation_rate, bc), right)
					+ td(r.stock_value_difference == null ? "" : format_currency(r.stock_value_difference, bc), right)
					+ td(r.value == null ? "" : format_currency(r.value, bc), right) : ""}
			</tr>`);
		});
		if (!rows.length) {
			rows.push(`<tr><td colspan="${ncols}" class="text-muted" style="padding:20px;text-align:center">${__("No stock movements")}</td></tr>`);
		}
		const last = (data.rows || [])[(data.rows || []).length - 1];
		const closing_value = last ? last.value : data.opening_value;
		const tf = "font-weight:600;border-top:2px solid var(--border-color);";
		const foot = `<tr class="th-card-foot">
			${td("", tf)}<td ${stick("th-card-sticky th-card-date")}><b>${__("Total")}</b></td><td ${stick("th-card-sticky th-card-voucher")}></td>${td("", tf)}${multi ? td("", tf) : ""}${td("", tf)}
			${td(num(data.totals.qty_in), right + tf)}${td(num(data.totals.qty_out), right + tf + "color:var(--red);")}${td(num(data.closing_qty), right + tf)}
			${cost ? td("", tf) + td("", tf) + td(closing_value != null ? format_currency(closing_value, bc) : "", right + tf) : ""}
		</tr>`;

		const thead = heads.map(([label, cls]) =>
			`<th class="${cls === "r" ? "" : cls}" style="padding:4px 8px;border-bottom:2px solid var(--border-color);color:var(--text-muted);white-space:nowrap;${cls === "r" ? right : ""}">${label}</th>`
		).join("");
		$container.append(`
			${data.truncated ? `<div class="alert alert-warning">${__("Showing the first {0} entries; totals are incomplete. Narrow the date range.", [5000])}</div>` : ""}
			<div class="th-export-scope">
			<div style="display:flex;justify-content:flex-end;margin-bottom:4px">${this._export_btn(__("Stock Card {0}", [this._item_panel.active || ""]))}</div>
			<div class="th-card-wrap" style="overflow-x:auto">
				<table class="th-card-table" style="width:100%;font-size:12px;border-collapse:separate;border-spacing:0">
					<thead><tr>${thead}</tr></thead>
					<tbody>${rows.join("")}</tbody>
					<tfoot>${foot}</tfoot>
				</table>
			</div>
			</div>`);
	}

	// ── Export: one table, as rendered ────────────────────────────────────────

	// Reload control + "fetched … ago" stamp for one tab. Results come from a 10-minute server cache;
	// the button re-calls the tab's loader with refresh=1, which bypasses and overwrites that cache.
	_refresh_btn(tab) {
		return `<button type="button" class="th-action-btn btn-refresh-tab" data-tab="${tab}" title="${__("Reload from the database")}">${_ICONS.refresh}</button><span class="th-fetched-at text-muted" style="font-size:11px;margin-left:4px"></span>`;
	}
	_stamp($scope, at) {
		if (at) $scope.find(".th-fetched-at").first().text(__("fetched {0}", [frappe.datetime.comment_when(at)]));
	}
	_export_btn(title) {
		return `<button type="button" class="th-action-btn btn-export-table" data-title="${frappe.utils.escape_html(title)}" title="${__("Export to Excel")}">${_ICONS.export}</button>`;
	}

	/** Rows of a rendered table: visible rows only, checkbox columns dropped, number-looking
	 *  text (with or without a currency prefix) as numbers. A nested detail table is flattened
	 *  under its parent row, indented by one blank cell. */
	_table_rows($table) {
		const text = (el) => $(el).text().replace(/[↕↑↓▲▼▶]/g, "").replace(/\s+/g, " ").trim(); // drop sort/expand glyphs
		const num = (t) => {
			// "1,234.5", "40", "-3.5", "KSh 1,234.50", "$1,234", "-KSh 50.00" → number.
			// "SINV-4687", "F071", "00123", "+254…", dates, "12.5%" and "Tile 600" stay text: a
			// currency prefix only counts when the amount is grouped or has two decimals.
			const m = t.match(/^(-?)(?:([A-Za-z]{1,4})\s|([$€£¥₹])\s?)?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?$/);
			if (!m) return t;
			const [, sign, code, sym, int, dec = ""] = m;
			if ((code || sym) && !int.includes(",") && dec.length !== 3) return t;
			if (int.length > 1 && int[0] === "0") return t;
			return parseFloat(sign + int.replace(/,/g, "") + dec);
		};
		const out = [];
		$table.children("thead, tbody, tfoot").children("tr").each((_, tr) => {
			const $tr = $(tr);
			if ($tr.hasClass("hidden") || $tr.css("display") === "none") return;
			const $inner = $tr.find("table").first();
			if ($inner.length) {
				this._table_rows($inner).forEach(r => out.push(["", ...r]));
				return;
			}
			const $cells = $tr.children("th, td");
			if ($cells.length === 1 && ($cells.attr("colspan") || 1) > 1) return; // "No rows found" / "Loading…" placeholders
			const cells = $cells.toArray().filter(c => !$(c).find("input[type=checkbox]").length);
			out.push(cells.map(c => num(text(c))));
		});
		return out;
	}

	_export_table($btn) {
		const $table = $btn.closest(".th-export-scope").find("table").first();
		const rows = $table.length ? this._table_rows($table) : [];
		if (rows.length < 2) { frappe.show_alert({ message: __("Nothing to export"), indicator: "orange" }); return; }
		open_url_post(frappe.request.url, {
			cmd: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.export_table",
			title: $btn.attr("data-title") || "table",
			rows: JSON.stringify(rows),
		});
	}

	_render_item_nav() {
		const m = this.page.main;
		const esc = frappe.utils.escape_html;
		const p = this._item_panel;
		const idx = p.items.findIndex(it => it.item_code === p.active);

		$(m).find(".item-chips").html(p.items.map(it => `
			<span class="item-chip ${it.item_code === p.active ? "active" : ""}" data-item="${esc(it.item_code)}" title="${esc(it.item_name)}">
				${esc(it.item_code)} <a class="item-chip-x" href="#" title="${__("Remove")}">×</a>
			</span>`).join(""));
		$(m).find(".item-select").html(p.items.map(it =>
			`<option value="${esc(it.item_code)}" ${it.item_code === p.active ? "selected" : ""}>${esc(it.item_code)}: ${esc(it.item_name)}</option>`
		).join(""));
		$(m).find(".item-nav").toggleClass("hidden", !p.items.length);
		$(m).find(".item-prev").prop("disabled", idx <= 0);
		$(m).find(".item-next").prop("disabled", idx < 0 || idx >= p.items.length - 1);
		$(m).find(".th-view-switch [data-view]").each((_, el) => {
			$(el).toggleClass("active", $(el).attr("data-view") === p.view);
		});
	}

	_clear_items() {
		const p = this._item_panel;
		this._run_generation = (this._run_generation || 0) + 1; // in-flight fetches become stale
		p.items = []; p.history = {}; p.card = {}; p.active = null; p.args = null;
		this._render_item_nav();
		$(this.page.main).find(".item-content").html(this._item_empty_html());
	}

	_remove_item(item_code) {
		const p = this._item_panel;
		const idx = p.items.findIndex(it => it.item_code === item_code);
		if (idx < 0) return;
		p.items.splice(idx, 1);
		delete p.history[item_code];
		delete p.card[item_code];
		if (!p.items.length) {
			p.active = null;
			this._render_item_nav();
			$(this.page.main).find(".item-content").html(this._item_empty_html());
		} else if (p.active === item_code) {
			this._show_item(p.items[Math.min(idx, p.items.length - 1)].item_code);
		} else {
			this._render_item_nav();
		}
	}

	_render_item_history({ item_details, stock_metrics, purchases, sales, open_po, open_so }, $container) {
		$container.append(this._render_metrics_grid(item_details, stock_metrics));
		let $grid = $(`<div class="item-results-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px">`).appendTo($container);
		this._render_transaction_panel($grid, purchases, "purchase");
		this._render_transaction_panel($grid, sales, "sale");
		this._render_open_orders_panel($grid, open_po || [], "po");
		this._render_open_orders_panel($grid, open_so || [], "so");
	}

	_render_metrics_grid(d, m) {
		const bc = this.base_currency;
		const row = (label, value, bold) =>
			`<div style="display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--border-color);gap:8px">
				<span style="color:var(--text-muted);white-space:nowrap">${label}</span>
				<span style="text-align:right${bold ? ";font-weight:700" : ""}">${value ?? "—"}</span>
			</div>`;

		const stock_color = (m.current_stock || 0) > 0 ? "var(--green)" : "var(--red)";
		const company = this.controls.item_company ? (this.controls.item_company.get_value() || "") : "";
		const col_style = "background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:12px 16px";

		return `
			<div class="th-metrics-3col" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
				<div style="${col_style}">
					<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px">${__("Item Details")}</div>
					${row(__("Name"), d.item_name, true)}
					${row(__("Code"), d.item_code)}
					${row(__("Group"), d.item_group)}
					${row(__("Brand"), d.brand || "—")}
				</div>
				<div style="${col_style}">
					<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px">${__("Stock")}</div>
					${row(__("Current Stock"), `<span class="th-stock-hover" data-item="${d.item_code}" data-company="${company}" style="color:${stock_color};font-weight:700;cursor:help;border-bottom:1px dotted ${stock_color}">${format_number(m.current_stock, null, 2)} ${d.stock_uom || ""}</span>`)}
					${m.stock_value !== undefined ? row(__("Stock Value"), format_currency(m.stock_value, bc), true) : ""}
					${m.avg_rate !== undefined ? row(__("Avg. Rate"), format_currency(m.avg_rate, bc)) : ""}
					${row(__("UOM"), d.stock_uom || "—")}
					${row(__("Valuation"), d.valuation_method || "—")}
				</div>
				<div style="${col_style}">
					<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px">${__("Pending Orders")}</div>
					${row(__("Pending PO"), format_number(m.pending_po_qty, null, 2) + " " + (d.stock_uom || ""))}
					${row(__("Pending SO"), format_number(m.pending_so_qty, null, 2) + " " + (d.stock_uom || ""))}
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

		const th = (label, align) =>
			`<th style="padding:5px 8px;${align ? "text-align:right;" : ""}border-bottom:2px solid ${accent};white-space:nowrap;color:var(--text-muted);font-weight:600">${label}</th>`;

		const show_rate = !is_purchase || (rows.length ? rows.some(r => rate_key in r) : this._item_panel.can_see_cost !== false);
		const empty_row = `<tr><td colspan="${show_rate ? 8 : 7}" style="padding:12px;text-align:center" class="text-muted">${is_purchase ? __("No purchases found") : __("No sales found")}</td></tr>`;

		const body = rows.length ? rows.map((r, i) => `
			<tr style="${i % 2 ? "background:var(--control-bg)" : ""}">
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${frappe.datetime.str_to_user(r.date)}</td>
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/${is_purchase ? (r.doctype === "Purchase Receipt" ? "purchase-receipt" : "purchase-invoice") : "sales-invoice"}/${r.voucher_no}" target="_blank">${r.voucher_no}</a></td>
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r[party_key] || ""}</td>
				<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.qty, null, 2)}</td>
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.uom || ""}</td>
				<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.rate, r.currency)}</td>
				${show_rate ? `<td style="padding:4px 8px;text-align:right;font-weight:600;border-bottom:1px solid var(--border-color)">${format_currency(r[rate_key], bc)}</td>` : ""}
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${this._status_pill(r.status)}</td>
			</tr>`).join("") : empty_row;

		$(`
			<div class="th-export-scope" style="border:1px solid var(--border-color);border-radius:6px;overflow:hidden">
				<div class="item-section-header" style="background:var(--subtle-fg);padding:8px 12px;font-weight:600;display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid ${accent};cursor:pointer;user-select:none">
					<span style="color:${accent}">${label}</span>
					<div style="display:flex;align-items:center;gap:8px">
						${this._export_btn(label)}
						<span style="font-weight:400;font-size:12px;color:var(--text-muted)">${__("Total Qty: {0}", [format_number(total_qty, null, 2)])}</span>
						<span class="section-chevron" style="color:var(--text-muted);font-size:11px">▼</span>
					</div>
				</div>
				<div class="item-section-body" style="max-height:280px;overflow:auto">
					<table style="width:100%;border-collapse:collapse;font-size:12px">
						<thead>
							<tr style="background:var(--subtle-fg)">
								${th(__("Date"))}
								${th(__("Voucher"))}
								${th(party_col)}
								${th(__("Qty"), true)}
								${th(__("UOM"))}
								${th(__("Rate"), true)}
								${show_rate ? th(rate_label, true) : ""}
								${th(__("Status"))}
							</tr>
						</thead>
						<tbody>${body}</tbody>
					</table>
				</div>
			</div>
		`).appendTo($grid);
	}

	_render_open_orders_panel($grid, rows, type) {
		const is_po = type === "po";
		const accent = is_po ? "var(--green)" : "var(--blue)";
		const label = is_po ? __("Open Purchase Orders") : __("Open Sales Orders");
		const party_col = is_po ? __("Supplier") : __("Customer");
		const party_key = is_po ? "supplier" : "customer";
		const received_col = is_po ? __("Received") : __("Delivered");
		const received_key = is_po ? "received_qty" : "delivered_qty";
		const bc = this.base_currency;

		const th = (lbl, align) =>
			`<th style="padding:5px 8px;${align ? "text-align:right;" : ""}border-bottom:2px solid ${accent};white-space:nowrap;color:var(--text-muted);font-weight:600">${lbl}</th>`;

		const doctype_slug = is_po ? "purchase-order" : "sales-order";
		const empty_row = `<tr><td colspan="8" style="padding:12px;text-align:center" class="text-muted">${is_po ? __("No open purchase orders") : __("No open sales orders")}</td></tr>`;

		const body = rows.length ? rows.map((r, i) => `
			<tr style="${i % 2 ? "background:var(--control-bg)" : ""}">
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${frappe.datetime.str_to_user(r.date)}</td>
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/${doctype_slug}/${r.voucher_no}" target="_blank">${r.voucher_no}</a></td>
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r[party_key] || ""}</td>
				<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.ordered_qty, null, 2)}</td>
				<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r[received_key], null, 2)}</td>
				<td style="padding:4px 8px;text-align:right;font-weight:600;border-bottom:1px solid var(--border-color)">${format_number(r.pending_qty, null, 2)}</td>
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.uom || ""}</td>
				<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.rate, r.currency)}</td>
			</tr>`).join("") : empty_row;

		$(`
			<div class="th-export-scope" style="border:1px solid var(--border-color);border-radius:6px;overflow:hidden">
				<div class="item-section-header" style="background:var(--subtle-fg);padding:8px 12px;font-weight:600;display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid ${accent};cursor:pointer;user-select:none">
					<span style="color:${accent}">${label}</span>
					<div style="display:flex;align-items:center;gap:8px">
						${this._export_btn(label)}
						<span style="font-weight:400;font-size:12px;color:var(--text-muted)">${__("{0} open", [rows.length])}</span>
						<span class="section-chevron" style="color:var(--text-muted);font-size:11px">▼</span>
					</div>
				</div>
				<div class="item-section-body" style="max-height:220px;overflow:auto">
					<table style="width:100%;border-collapse:collapse;font-size:12px">
						<thead>
							<tr style="background:var(--subtle-fg)">
								${th(__("Date"))}
								${th(__("Order No."))}
								${th(party_col)}
								${th(__("Ordered"), true)}
								${th(received_col, true)}
								${th(__("Pending"), true)}
								${th(__("UOM"))}
								${th(__("Rate"), true)}
							</tr>
						</thead>
						<tbody>${body}</tbody>
					</table>
				</div>
			</div>
		`).appendTo($grid);
	}

	// ── Customer History ──────────────────────────────────────────────────────

	_load_customer_history(refresh = false) {
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
				refresh: refresh ? 1 : 0,
			},
			callback: (r) => {
				if (r.message != null) {
					this._cust_state.rows = r.message;
					this._cust_state.party = customer;
					this._cust_state.company = company;
					$content.html(this._render_party_summary(r.message, "customer", customer, company, this._cust_state));
					this._stamp($content, r.th_fetched_at);
				}
			},
		});
	}

	// ── Supplier History ──────────────────────────────────────────────────────

	_load_supplier_history(refresh = false) {
		let supplier = this.controls.supplier.get_value();
		let company = this.controls.supp_company.get_value();
		if (!supplier || !company) { frappe.msgprint(__("Supplier and Company are required")); return; }
		let $content = $(this.page.main).find(".supplier-content");
		$content.html(`<div class="text-muted" style="padding:20px">${__("Loading...")}</div>`);

		const source_val = this.controls.supp_source ? this.controls.supp_source.get_value() : "Purchase Invoice";
		this._supp_source = source_val === "Purchase Receipt" ? "pr" : "pi";

		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_supplier_history",
			args: {
				supplier,
				company,
				from_date: this.controls.supp_from.get_value() || null,
				to_date: this.controls.supp_to.get_value() || null,
				source: this._supp_source,
				refresh: refresh ? 1 : 0,
			},
			callback: (r) => {
				if (r.message != null) {
					this._supp_state.rows = r.message;
					this._supp_state.party = supplier;
					this._supp_state.company = company;
					$content.html(this._render_party_summary(r.message, "supplier", supplier, company, this._supp_state));
					this._stamp($content, r.th_fetched_at);
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
		const show_rate = rows.some(r => rate_key in r);

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
		const th_plain = (label, align) => `
			<th style="padding:5px 8px;${align ? "text-align:" + align + ";" : ""}color:var(--text-muted);font-weight:600;border-bottom:2px solid ${accent}">
				${label}
			</th>`;

		return `
			<div class="th-export-scope">
			<div style="margin-bottom:8px;display:flex;gap:8px;align-items:center">
				<input type="search" class="party-search form-control form-control-sm" data-party-type="${party_type}"
					placeholder="${__("Filter rows...")}" style="max-width:240px">
				${this._export_btn(__("{0} History {1}", [party_type === "customer" ? __("Customer") : __("Supplier"), party || ""]))}
				${this._refresh_btn(party_type)}
				<button class="btn-copy-selected-items" data-party-type="${party_type}" disabled
					title="${__("Copy selected item names and prices to clipboard")}"
					style="display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border:1px solid var(--border-color);border-radius:4px;background:transparent;cursor:not-allowed;color:var(--text-muted);opacity:.4;font-size:11px;flex-shrink:0">
					${_ICONS.copy} <span class="copy-sel-count">${__("0 selected")}</span>
				</button>
			</div>
			<div style="overflow-x:auto">
			<table style="width:100%;border-collapse:collapse;font-size:12px" data-party-type="${party_type}">
				<thead>
					<tr style="background:var(--subtle-fg)">
						<th style="padding:5px 8px;width:28px;border-bottom:2px solid ${accent}">
							<input type="checkbox" class="party-select-all" data-party-type="${party_type}" title="${__("Select / deselect all")}">
						</th>
						<th style="padding:5px 8px;width:28px;border-bottom:2px solid ${accent}"></th>
						${th(__("Item Code"), "item_code")}
						${th(__("Item Name"), "item_name")}
						${th(count_col, count_key, "right")}
						${th(__("Total Qty"), "total_qty", "right")}
						${show_rate ? th(rate_col, rate_key, "right") : ""}
						${th(__("Total Amount"), "total_amount", "right")}
						${th_plain(__("Avail. Qty"), "right")}
						${th(date_col, date_key)}
						${th_plain(__("Status"))}
					</tr>
				</thead>
				<tbody>
					${rows.map((r, i) => {
						const stock_color = (r.current_stock || 0) > 0 ? "var(--green)" : "var(--text-muted)";
						const last_rate = "last_rate" in r ? parseFloat(r.last_rate || 0) : "";
						return `
						<tr class="summary-row" data-item="${r.item_code}" data-avg-rate="${parseFloat(r[rate_key] || 0)}" data-last-rate="${last_rate}" data-party="${party}" data-party-type="${party_type}" data-company="${company}"
							style="${i % 2 ? "background:var(--control-bg)" : "background:var(--bg-color)"};cursor:pointer"
							title="${__("Click to expand transactions")}">
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)" onclick="event.stopPropagation()">
								<input type="checkbox" class="party-row-check" data-party-type="${party_type}">
							</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color);color:var(--text-muted)">▶</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/item/${r.item_code}" target="_blank">${r.item_code}</a></td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.item_name}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r[count_key]}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.total_qty, null, 2)}</td>
							${show_rate ? `<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${rate_key in r ? format_currency(r[rate_key], bc) : "—"}</td>` : ""}
							<td style="padding:4px 8px;text-align:right;font-weight:700;border-bottom:1px solid var(--border-color)">${format_currency(r.total_amount, bc)}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">
								<span class="th-stock-hover" data-item="${r.item_code}" data-company="${company}"
									style="color:${stock_color};font-weight:${(r.current_stock || 0) > 0 ? "700" : "400"};cursor:help;border-bottom:1px dotted ${stock_color}">
									${format_number(r.current_stock || 0, null, 2)}
								</span>
							</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r[date_key] ? frappe.datetime.str_to_user(r[date_key]) : "—"}</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${this._summary_status_pill(r.overdue_count || 0, r.unpaid_count || 0)}</td>
						</tr>
						<tr class="detail-row hidden" data-detail-for="${r.item_code}">
							<td colspan="${show_rate ? 11 : 10}" style="padding:0;border-bottom:2px solid var(--border-color)">
								<div class="detail-content" style="padding:8px 24px;background:var(--card-bg)">
									<span class="text-muted">${__("Loading...")}</span>
								</div>
							</td>
						</tr>`;
					}).join("")}
				</tbody>
			</table>
			</div>
			</div>`;
	}

	// ── Bind tabs + accordion (single method) ────────────────────────────────

	_bind_tabs() {
		const m = this.page.main;

		// Bound first so stopImmediatePropagation beats the section-header collapse toggle below.
		$(m).on("click", ".btn-export-table", (e) => {
			e.preventDefault();
			e.stopImmediatePropagation();
			this._export_table($(e.currentTarget));
		});

		// Bootstrap nav-tabs switching
		$(m).on("click", ".nav-link[data-tab]", (e) => {
			e.preventDefault();
			$(m).find(".nav-link[data-tab]").removeClass("active");
			$(e.currentTarget).addClass("active");
			$(m).find(".th-panel").addClass("hidden");
			$(m).find(`[data-panel="${$(e.currentTarget).data("tab")}"]`).removeClass("hidden");
		});

		$(m).on("click", ".btn-get-customer", () => this._load_customer_history());
		$(m).on("click", ".btn-get-supplier", () => this._load_supplier_history());

		// Item navigator
		$(m).on("click", ".btn-refresh-tab", (e) => {
			e.preventDefault();
			e.stopImmediatePropagation();
			const run = {
				items: () => this._run_item_history(true),
				customer: () => this._load_customer_history(true),
				supplier: () => this._load_supplier_history(true),
				receivables: () => this._load_receivables(true),
				payables: () => this._load_payables(true),
				pricing: () => this._run_pricing(true),
			}[$(e.currentTarget).attr("data-tab")];
			run && run();
		});
		$(m).on("click", ".btn-pick-items", () => this._open_item_picker());
		$(m).on("click", ".item-clear", () => this._clear_items());
		$(m).on("click", ".th-view-switch [data-view]", (e) => {
			this._item_panel.view = $(e.currentTarget).attr("data-view");
			if (this._item_panel.active) this._show_item(this._item_panel.active);
			else this._render_item_nav();
		});
		$(m).on("change", ".item-select", (e) => this._show_item($(e.currentTarget).val()));
		$(m).on("click", ".th-retry", (e) => {
			e.preventDefault();
			const p = this._item_panel;
			if (!p.active) return;
			if (p.view === "history") this._fetch_item_history(p.active, this._run_generation);
			this._show_item(p.active); // card view: _load_stock_card refetches because the cache slot is empty
		});
		$(m).on("click", ".item-prev, .item-next", (e) => {
			const p = this._item_panel;
			const idx = p.items.findIndex(it => it.item_code === p.active) + ($(e.currentTarget).hasClass("item-next") ? 1 : -1);
			if (p.items[idx]) this._show_item(p.items[idx].item_code);
		});
		$(m).on("click", ".item-chip", (e) => this._show_item($(e.currentTarget).attr("data-item")));
		$(m).on("click", ".item-chip-x", (e) => {
			e.preventDefault();
			e.stopPropagation();
			this._remove_item($(e.currentTarget).closest(".item-chip").attr("data-item"));
		});

		// Current Stock hover — warehouse breakdown popover
		$(m).on("mouseenter", ".th-stock-hover", (e) => {
			this._show_warehouse_popover($(e.currentTarget));
		});
		$(m).on("mouseleave", ".th-stock-hover", () => {
			$("#th-warehouse-popover").remove();
		});

		// Item results search filter — rows of the item shown in .item-content
		$(m).on("input", ".item-results-search", (e) => {
			const val = $(e.currentTarget).val().toLowerCase();
			$(m).find(".item-content tbody tr").each(function () {
				const text = $(this).text().toLowerCase();
				$(this).toggleClass("hidden", val !== "" && !text.includes(val));
			});
		});

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

		// Party search filter — filters summary rows and detail rows
		$(m).on("input", ".party-search", (e) => {
			const val = $(e.currentTarget).val().toLowerCase();
			const party_type = $(e.currentTarget).data("party-type");
			const $table = $(m).find(`table[data-party-type="${party_type}"]`);
			$table.find(".summary-row").each(function () {
				const text = $(this).text().toLowerCase();
				const $detail = $(this).next(".detail-row");
				if (val === "" || text.includes(val)) {
					$(this).removeClass("hidden");
					// Also filter within any loaded detail rows
					$detail.find("tbody tr").each(function () {
						const detail_text = $(this).text().toLowerCase();
						$(this).toggleClass("hidden", val !== "" && !detail_text.includes(val));
					});
				} else {
					$(this).addClass("hidden");
					$detail.addClass("hidden");
					$(this).find("td:eq(1)").text("▶");
				}
			});
			// Clear any detail row filters when search is cleared
			if (!val) {
				$table.find(".detail-content tbody tr").removeClass("hidden");
			}
		});

		// Item section collapse toggle
		$(m).on("click", ".item-section-header", (e) => {
			const $header = $(e.currentTarget);
			const $body = $header.next(".item-section-body");
			const $chevron = $header.find(".section-chevron");
			if ($body.is(":visible")) {
				$body.hide();
				$chevron.text("▶");
			} else {
				$body.show();
				$chevron.text("▼");
			}
		});

		// ── Receivables bindings ──────────────────────────────────────────────

		$(m).on("click", ".btn-get-receivables", () => this._load_receivables());

		$(m).on("input", ".recv-search", (e) => {
			const val = $(e.currentTarget).val().toLowerCase();
			$(m).find(".recv-summary-row").each(function () {
				const show = !val || $(this).text().toLowerCase().includes(val);
				$(this).toggleClass("hidden", !show);
				if (!show) $(this).next(".recv-detail-row").addClass("hidden");
			});
		});

		$(m).on("click", ".recv-summary-row", (e) => {
			if ($(e.target).closest("[data-party-type]").length && !$(e.target).is("tr")) return;
			const $row = $(e.currentTarget);
			const party = $row.data("party");
			const company = $row.data("company");
			const as_of_date = $row.data("as-of");
			const $detail = $row.next(".recv-detail-row");

			if (!$detail.hasClass("hidden")) {
				$detail.addClass("hidden");
				$row.find("td:first").text("▶");
				return;
			}
			$row.find("td:first").text("▼");
			$detail.removeClass("hidden");
			const $dc = $detail.find(`.recv-detail-content[data-for="${party}"]`);
			if ($dc.data("loaded")) return;

			const show_future = this._recv_state.show_future_payments ?? 0;
			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_receivables_detail",
				args: { customer: party, company, as_of_date, show_future_payments: show_future },
				callback: (r) => {
					$dc.html(this._render_outstanding_detail(r.message || [], true, show_future))
						.data("loaded", true).data("rows", r.message || []);
				},
			});
		});

		$(m).on("click", ".recv-sort-header", (e) => {
			e.stopPropagation();
			const key = $(e.currentTarget).data("sort-key");
			const state = this._recv_state;
			state.sort_dir = state.sort_key === key ? (state.sort_dir === "asc" ? "desc" : "asc") : "asc";
			state.sort_key = key;
			const sorted = [...state.rows].sort((a, b) => {
				const av = a[key] ?? ""; const bv = b[key] ?? "";
				const cmp = av < bv ? -1 : av > bv ? 1 : 0;
				return state.sort_dir === "asc" ? cmp : -cmp;
			});
			this._render_receivables(sorted, state.company, state.as_of_date, null);
		});

		// ── Payables bindings ─────────────────────────────────────────────────

		$(m).on("click", ".btn-get-payables", () => this._load_payables());

		$(m).on("input", ".pay-search", (e) => {
			const val = $(e.currentTarget).val().toLowerCase();
			$(m).find(".pay-summary-row").each(function () {
				const show = !val || $(this).text().toLowerCase().includes(val);
				$(this).toggleClass("hidden", !show);
				if (!show) $(this).next(".pay-detail-row").addClass("hidden");
			});
		});

		$(m).on("click", ".pay-summary-row", (e) => {
			if ($(e.target).closest("[data-party-type]").length && !$(e.target).is("tr")) return;
			const $row = $(e.currentTarget);
			const party = $row.data("party");
			const company = $row.data("company");
			const as_of_date = $row.data("as-of");
			const $detail = $row.next(".pay-detail-row");

			if (!$detail.hasClass("hidden")) {
				$detail.addClass("hidden");
				$row.find("td:first").text("▶");
				return;
			}
			$row.find("td:first").text("▼");
			$detail.removeClass("hidden");
			const $dc = $detail.find(`.pay-detail-content[data-for="${party}"]`);
			if ($dc.data("loaded")) return;

			const show_future = this._pay_state.show_future_payments ?? 0;
			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_payables_detail",
				args: { supplier: party, company, as_of_date, show_future_payments: show_future },
				callback: (r) => {
					$dc.html(this._render_outstanding_detail(r.message || [], false, show_future))
						.data("loaded", true).data("rows", r.message || []);
				},
			});
		});

		$(m).on("click", ".pay-sort-header", (e) => {
			e.stopPropagation();
			const key = $(e.currentTarget).data("sort-key");
			const state = this._pay_state;
			state.sort_dir = state.sort_key === key ? (state.sort_dir === "asc" ? "desc" : "asc") : "asc";
			state.sort_key = key;
			const sorted = [...state.rows].sort((a, b) => {
				const av = a[key] ?? ""; const bv = b[key] ?? "";
				const cmp = av < bv ? -1 : av > bv ? 1 : 0;
				return state.sort_dir === "asc" ? cmp : -cmp;
			});
			this._render_payables(sorted, state.company, state.as_of_date, null);
		});

		// ── Party action buttons ──────────────────────────────────────────────

		// Party summary row checkbox — update copy-selected button
		$(m).on("change", ".party-row-check", (e) => {
			const party_type = $(e.currentTarget).data("party-type");
			this._update_copy_selected_btn(party_type, $(m));
		});

		// Party summary select-all checkbox
		$(m).on("change", ".party-select-all", (e) => {
			const party_type = $(e.currentTarget).data("party-type");
			const checked = e.currentTarget.checked;
			$(m).find(`table[data-party-type="${party_type}"] .summary-row:not(.hidden) .party-row-check`)
				.prop("checked", checked);
			this._update_copy_selected_btn(party_type, $(m));
		});

		// Copy selected items
		$(m).on("click", ".btn-copy-selected-items:not([disabled])", (e) => {
			const party_type = $(e.currentTarget).data("party-type");
			this._copy_selected_items(party_type, $(m));
		});

		// Party info icon
		$(m).on("click", ".th-party-info-btn", (e) => {
			e.stopPropagation();
			const $btn = $(e.currentTarget);
			const party = $btn.data("party");
			const party_type = $btn.data("party-type");
			const company = $btn.data("company") || "";
			const as_of_date = $btn.data("as-of");
			const show_future_payments = $btn.data("show-future") ? 1 : 0;
			this._show_party_info_dialog(party_type, party, company, as_of_date, show_future_payments);
		});

		// One button for both documents and both delivery routes. Previously print and email were
		// separate icons; adding Statement of Accounts on top would have meant four.
		$(m).on("click", ".btn-statement", (e) => {
			e.stopPropagation();
			const $wrap = $(e.currentTarget).closest(".th-party-actions");
			this._open_statement_dialog(
				$wrap.data("party-type"),
				$wrap.data("party"),
				$wrap.data("company"),
				$wrap.data("as-of")
			);
		});

		$(m).on("click", ".btn-copy-text", (e) => {
			e.stopPropagation();
			const $wrap = $(e.currentTarget).closest(".th-party-actions");
			const party = $wrap.data("party");
			const party_type = $wrap.data("party-type");
			const company = $wrap.data("company");
			const as_of_date = $wrap.data("as-of");
			const is_customer = party_type === "customer";
			const $dc = $(m).find(
				is_customer
					? `.recv-detail-content[data-for="${party}"]`
					: `.pay-detail-content[data-for="${party}"]`
			);
			const existing = $dc.data("rows");
			if (existing) {
				this._copy_party_text(party_type, party, company, as_of_date, existing);
			} else {
				const method = is_customer
					? "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_receivables_detail"
					: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_payables_detail";
				const args = is_customer
					? { customer: party, company, as_of_date }
					: { supplier: party, company, as_of_date };
				frappe.call({ method, args, callback: (r) => {
					this._copy_party_text(party_type, party, company, as_of_date, r.message || []);
				}});
			}
		});

		$(m).on("click", ".btn-copy-link", (e) => {
			e.stopPropagation();
			const $wrap = $(e.currentTarget).closest(".th-party-actions");
			const party = $wrap.data("party");
			const party_type = $wrap.data("party-type");
			const tab = party_type === "customer" ? "receivables" : "payables";
			this._copy_party_link(tab, party_type, party);
		});

		// ── Pricing bindings ──────────────────────────────────────────────────

		$(m).on("click", ".btn-toggle-pricing-panel", () => {
			const $sidebar = $(m).find(".pricing-panel-sidebar");
			const collapsed = $sidebar.hasClass("pricing-panel-collapsed");
			if (collapsed) {
				$sidebar.removeClass("pricing-panel-collapsed").css({ width: "224px", "min-width": "224px", padding: "10px", overflow: "" });
				$sidebar.find(".pricing-panel-body").show();
				$sidebar.find(".pricing-panel-label").show();
			} else {
				$sidebar.addClass("pricing-panel-collapsed").css({ width: "36px", "min-width": "36px", padding: "4px 2px", overflow: "hidden" });
				$sidebar.find(".pricing-panel-body").hide();
				$sidebar.find(".pricing-panel-label").hide();
			}
		});

		$(m).on("change", ".pricing-checkbox", (e) => {
			const idx = parseInt($(e.currentTarget).data("idx"), 10);
			this._pricing_panel.items[idx].checked = e.currentTarget.checked;
			const checked = this._pricing_panel.items.filter(it => it.checked).length;
			$(m).find(".btn-run-pricing").text(__("Run ({0})", [checked])).prop("disabled", checked === 0);
		});

		$(m).on("click", ".btn-remove-pricing-item", (e) => {
			e.stopPropagation();
			const idx = parseInt($(e.currentTarget).data("idx"), 10);
			if (idx < 0 || idx >= this._pricing_panel.items.length) return;
			this._pricing_panel.items.splice(idx, 1);
			this._render_pricing_checklist();
		});

		$(m).on("click", ".btn-clear-pricing", () => {
			this._pricing_panel.items = [];
			this._render_pricing_checklist();
			$(m).find(".pricing-tabs-strip, .pricing-content").empty();
		});

		$(m).on("awesomplete-select", ".ctrl-pricing-group input", () => {
			setTimeout(() => {
				const group = this.controls.pricing_group ? this.controls.pricing_group.get_value() : null;
				if (!group) return;
				frappe.db.get_list("Item", {
					filters: { item_group: group, disabled: 0 },
					fields: ["name", "item_name"],
					limit: 500,
				}).then(items => items.forEach(it => this._add_item_to_pricing_panel(it.name, it.item_name)));
			}, 50);
		});

		$(m).on("awesomplete-select", ".ctrl-pricing-add input", () => {
			setTimeout(() => {
				const val = this.controls.pricing_add ? this.controls.pricing_add.get_value() : null;
				if (!val) return;
				frappe.db.get_value("Item", val, "item_name").then(r => {
					this._add_item_to_pricing_panel(val, r.message ? r.message.item_name : val);
					this.controls.pricing_add.set_value("");
				});
			}, 50);
		});

		// "Add all filtered" — Pricing panel
		$(m).on("awesomplete-open", ".ctrl-pricing-add input", (e) => {
			setTimeout(() => {
				const $ul = $(e.target).closest(".awesomplete").find("ul");
				if (!$ul.length || !$ul.is(":visible") || $ul.find(".add-all-filtered-li").length) return;
				$ul.append(`<li class="add-all-filtered-li" role="option" style="border-top:1px solid var(--border-color);padding:5px 10px;font-size:11px;color:var(--blue);background:var(--fg-color);cursor:pointer;text-align:center;font-style:italic">${__("+ Add all filtered")}</li>`);
			}, 0);
		});
		$(m).on("mousedown", ".ctrl-pricing-add .add-all-filtered-li", (e) => { e.preventDefault(); });
		$(m).on("click", ".ctrl-pricing-add .add-all-filtered-li", () => {
			const txt = (this.controls.pricing_add ? this.controls.pricing_add.get_value() : "") || "";
			const group = this.controls.pricing_group ? this.controls.pricing_group.get_value() : null;
			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.api.item_query",
				args: {
					doctype: "Item", txt, searchfield: "name",
					start: 0, page_len: 500,
					filters: JSON.stringify(group ? { item_group: group } : {}),
					as_dict: 1,
				},
			}).then(r => {
				const results = r.message || [];
				if (!results.length) { frappe.show_alert({ message: __("No items found"), indicator: "orange" }); return; }
				results.forEach(it => this._add_item_to_pricing_panel(it.name, it.item_name || it.name));
				frappe.show_alert({ message: __("{0} item(s) added", [results.length]), indicator: "green" });
				this.controls.pricing_add.set_value("");
			});
		});

		$(m).on("click", ".btn-run-pricing", () => this._run_pricing());

		$(m).on("click", ".pricing-tab-link", (e) => {
			e.preventDefault();
			const item_code = $(e.currentTarget).data("item");
			$(m).find(".pricing-tab-link").removeClass("active");
			$(e.currentTarget).addClass("active");
			$(m).find(".pricing-tab-panel").addClass("hidden");
			$(m).find(`.pricing-tab-panel[data-item="${item_code}"]`).removeClass("hidden");
			this._pricing_panel.active_tab = item_code;
		});

		// Pricing — edit price list rate
		$(m).on("click", ".btn-edit-price", (e) => {
			e.stopPropagation();
			const pl = $(e.currentTarget).data("pl");
			const item = $(e.currentTarget).data("item");
			$(m).find(`.price-edit-row[data-edit-for-pl="${pl}"][data-edit-for-item="${item}"]`).removeClass("hidden");
			$(e.currentTarget).closest("tr").find(".btn-edit-price").prop("disabled", true);
		});

		$(m).on("click", ".btn-cancel-price", (e) => {
			const pl = $(e.currentTarget).data("pl");
			const item = $(e.currentTarget).data("item");
			$(m).find(`.price-edit-row[data-edit-for-pl="${pl}"][data-edit-for-item="${item}"]`).addClass("hidden");
			$(m).find(`.price-list-row[data-pl="${pl}"][data-item="${item}"] .btn-edit-price`).prop("disabled", false);
		});

		const _apply_markup = ($row) => {
			const avg = parseFloat($row.find(".price-markup-input").data("avg-val")) || 0;
			const markup = parseFloat($row.find(".price-markup-input").val()) || 0;
			const round_to = parseFloat($row.find(".price-round-select").val()) || 0;
			const raw = avg * (1 + markup / 100);
			const rounded = round_to > 0 ? Math.round(raw / round_to) * round_to : raw;
			$row.find(".price-suggested").text(format_number(rounded, null, 2));
			$row.find(".price-new-rate-input").val(rounded.toFixed(2));
		};

		$(m).on("input", ".price-markup-input", (e) => {
			_apply_markup($(e.currentTarget).closest("tr"));
		});

		$(m).on("change", ".price-round-select", (e) => {
			_apply_markup($(e.currentTarget).closest("tr"));
		});

		$(m).on("click", ".btn-use-last-sold", (e) => {
			const item = $(e.currentTarget).data("item");
			const pl = $(e.currentTarget).data("pl");
			const $panel = $(e.currentTarget).closest(".pricing-tab-panel");
			let last_rate = null;
			$panel.find(".pricing-sales-table tbody tr").each(function () {
				// col eq(4) = Price List, col eq(8) = Base Rate (newest first)
				const row_pl = $(this).find("td").eq(4).text().trim();
				if (!pl || row_pl === pl) {
					const rate_text = $(this).find("td").eq(8).text().replace(/,/g, "");
					last_rate = parseFloat(rate_text) || null;
					return false; // break — first match is newest row
				}
			});
			if (last_rate !== null) {
				$(e.currentTarget).closest("tr").find(".price-new-rate-input").val(last_rate.toFixed(2));
			} else {
				frappe.show_alert({ message: __("No sales found for this price list in the current date range"), indicator: "orange" });
			}
		});

		$(m).on("click", ".btn-save-price", (e) => {
			const item = $(e.currentTarget).data("item");
			const pl = $(e.currentTarget).data("pl");
			const $row = $(e.currentTarget).closest("tr");
			const rate = parseFloat($row.find(".price-new-rate-input").val());
			if (!rate || isNaN(rate)) { frappe.msgprint(__("Please enter a valid rate")); return; }

			$(e.currentTarget).prop("disabled", true).text(__("Saving..."));
			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.update_item_price",
				args: { item_code: item, price_list: pl, rate },
				callback: (r) => {
					if (r.message) {
						frappe.show_alert({ message: __("Price updated"), indicator: "green" });
						$(m).find(`.price-list-row[data-pl="${pl}"][data-item="${item}"] td:nth-child(3)`).text(format_number(r.message.price_list_rate, null, 2));
						$(m).find(`.price-edit-row[data-edit-for-pl="${pl}"][data-edit-for-item="${item}"]`).addClass("hidden");
						$(m).find(`.price-list-row[data-pl="${pl}"][data-item="${item}"] .btn-edit-price`).prop("disabled", false);
					} else {
						$(e.currentTarget).prop("disabled", false).text(__("Save"));
					}
				},
			});
		});

		// ── URL param deep-linking ─────────────────────────────────────────────

		// Accordion: expand/collapse summary rows
		$(m).on("click", ".summary-row", (e) => {
			if ($(e.target).is("a") || $(e.target).is(".party-row-check")) return;
			let $row = $(e.currentTarget);
			let item_code = $row.data("item");
			let party = $row.data("party");
			let party_type = $row.data("party-type");
			let company = $row.data("company");
			let $detail = $row.closest("tbody").find(`.detail-row[data-detail-for="${item_code}"]`);

			if (!$detail.hasClass("hidden")) {
				$detail.addClass("hidden");
				$row.find("td:eq(1)").text("▶");
				return;
			}

			$row.find("td:eq(1)").text("▼");
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
		const show_rate = rows.some(r => rate_key in r);
		// detail_doctype is passed by the accordion handler so PI vs PR links correctly
		const doctype_slug = detail_doctype || (is_customer ? "sales-invoice" : "purchase-invoice");

		return `
			<div style="overflow-x:auto">
			<table style="width:100%;border-collapse:collapse;font-size:11px">
				<thead>
					<tr style="background:var(--subtle-fg)">
						<th style="padding:3px 8px;text-align:left;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Date")}</th>
						<th style="padding:3px 8px;text-align:left;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Voucher No")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Qty")}</th>
						<th style="padding:3px 8px;text-align:left;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("UOM")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Rate")}</th>
						${show_rate ? `<th style="padding:3px 8px;text-align:right;color:var(--text-muted);font-weight:700;border-bottom:1px solid var(--border-color)">${rate_label}</th>` : ""}
						<th style="padding:3px 8px;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Due Date")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Days Overdue")}</th>
						<th style="padding:3px 8px;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Status")}</th>
					</tr>
				</thead>
				<tbody>
					${rows.map((r, i) => {
						const overdue = r.days_overdue;
						const overdue_style = overdue > 90 ? "color:var(--red);font-weight:700;" : overdue > 60 ? "color:var(--orange);" : "";
						return `
						<tr style="${i % 2 ? "background:var(--subtle-fg)" : ""}">
							<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)">${frappe.datetime.str_to_user(r.date)}</td>
							<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/${doctype_slug}/${r.voucher_no}" target="_blank">${r.voucher_no}</a></td>
							<td style="padding:3px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.qty, null, 2)}</td>
							<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)">${r.uom || ""}</td>
							<td style="padding:3px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.rate, r.currency)}</td>
							${show_rate ? `<td style="padding:3px 8px;text-align:right;font-weight:600;border-bottom:1px solid var(--border-color)">${format_currency(r[rate_key], bc)}</td>` : ""}
							<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)">${r.due_date ? frappe.datetime.str_to_user(r.due_date) : "—"}</td>
							<td style="padding:3px 8px;text-align:right;${overdue_style}border-bottom:1px solid var(--border-color)">${overdue != null ? overdue : "—"}</td>
							<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)">${this._status_pill(r.status)}</td>
						</tr>`;
					}).join("")}
				</tbody>
			</table>
			</div>`;
	}

	// ── Shared: invoice-based fallback basis note ───────────────────────────────

	_basis_note_html() {
		return `<div class="text-muted" style="font-size:11px;margin-top:6px">${__("Based on invoices and payments; journal entry adjustments are not included.")}</div>`;
	}

	_get_balance_basis() {
		if (this._balance_basis) return Promise.resolve(this._balance_basis);
		return frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_balance_basis",
		}).then((r) => {
			this._balance_basis = r.message;
			return this._balance_basis;
		});
	}

	// ── Receivables ───────────────────────────────────────────────────────────

	_load_receivables(refresh = false) {
		const m = this.page.main;
		const company = this.controls.recv_company.get_value();
		const as_of_date = this.controls.recv_as_of.get_value();
		if (!company || !as_of_date) { frappe.msgprint(__("Company and As Of Date are required")); return; }
		const customer = this.controls.recv_customer.get_value() || null;
		const show_future_payments = this.controls.recv_show_future.get_value() ? 1 : 0;
		const $content = $(m).find(".receivables-content");
		$content.html(`<div class="text-muted" style="padding:20px">${__("Loading...")}</div>`);
		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_receivables",
			args: { company, as_of_date, customer, show_future_payments, refresh: refresh ? 1 : 0 },
			callback: (r) => {
				if (r.message != null) {
					this._recv_state.rows = r.message;
					this._recv_state.company = company;
					this._recv_state.as_of_date = as_of_date;
					this._recv_state.show_future_payments = show_future_payments;
					this._render_receivables(r.message, company, as_of_date, customer);
					this._stamp($content, r.th_fetched_at);
					this._get_balance_basis().then((basis) => {
						if (basis === "invoices") $(m).find(".receivables-content").prepend(this._basis_note_html());
					});
				}
			},
		});
	}

	_render_receivables(rows, company, as_of_date, customer) {
		const m = this.page.main;
		const $content = $(m).find(".receivables-content");
		const bc = this.base_currency;
		const accent = "var(--blue)";
		const show_future = !!this._recv_state.show_future_payments;

		if (!rows.length) {
			$content.html(`<div class="text-muted" style="padding:20px">${__("No outstanding receivables found")}</div>`);
			return;
		}

		if (customer) {
			const r = rows[0];
			const oldest = r.bucket_90_plus > 0 ? "90+" : r.bucket_61_90 > 0 ? "61–90" : r.bucket_31_60 > 0 ? "31–60" : __("Current");
			const hl = (r.overdue || 0) > 0 ? "is-red" : ((r.outstanding || 0) > 0 || (r.unallocated_advance || 0) > 0) ? "is-amber" : "";
			const info_title = hl === "is-red" ? __("Overdue invoices — click for details")
				: hl ? __("Outstanding or advances pending — click for details") : __("Party details");
			$content.html(`
				<div class="th-stats-3col" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">
					<div style="background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:12px 16px">
						<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px">${__("Total Outstanding")}</div>
						<div style="font-size:18px;font-weight:700;color:var(--red)">${format_currency(r.outstanding, bc)}</div>
					</div>
					<div style="background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:12px 16px">
						<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px">${__("Oldest Bucket")}</div>
						<div style="font-size:18px;font-weight:700">${oldest}</div>
					</div>
					<div style="background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:12px 16px">
						<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px">${__("Last Payment")}</div>
						<div style="font-size:18px;font-weight:700">${r.last_payment ? frappe.datetime.str_to_user(r.last_payment) : "—"}</div>
					</div>
				</div>
				<div style="margin-bottom:12px;display:flex;gap:4px;align-items:center">
					<div class="th-party-actions" style="display:flex;gap:1px;align-items:center" data-party="${customer}" data-party-type="customer" data-company="${company}" data-as-of="${as_of_date}">
						<button class="th-action-btn btn-copy-text" title="${__("Copy text")}">${_ICONS.copy}</button>
						<button class="th-action-btn btn-copy-link" title="${__("Copy internal link")}">${_ICONS.link}</button>
						<button class="th-action-btn btn-statement" title="${__("Statement")}">${_ICONS.statement}</button>
					</div>
					<span class="th-party-info-btn${hl ? " " + hl : ""}" data-party="${customer}" data-party-type="customer" data-company="${company}" data-as-of="${as_of_date}" data-show-future="${show_future ? 1 : 0}" title="${info_title}" style="margin-left:4px">${_ICONS.info}</span>
				</div>
				<div class="recv-detail-content" data-for="${customer}" style="padding:4px 0">
					<div class="text-muted" style="padding:12px">${__("Loading invoices...")}</div>
				</div>
			`);
			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_receivables_detail",
				args: { customer, company, as_of_date, show_future_payments: show_future ? 1 : 0 },
				callback: (r2) => {
					$content.find(`.recv-detail-content[data-for="${customer}"]`)
						.html(this._render_outstanding_detail(r2.message || [], true, show_future))
						.data("rows", r2.message || []);
				},
			});
			return;
		}

		const sort_icon = (key) => this._recv_state.sort_key !== key
			? `<span style="opacity:.35;font-size:10px"> ↕</span>`
			: this._recv_state.sort_dir === "asc" ? `<span style="font-size:10px"> ↑</span>` : `<span style="font-size:10px"> ↓</span>`;
		const th = (label, key, align) => `
			<th class="recv-sort-header" data-sort-key="${key}"
				style="padding:5px 8px;text-align:${align || "left"};color:var(--text-muted);font-weight:600;border-bottom:2px solid ${accent};cursor:pointer;white-space:nowrap;user-select:none">
				${label}${sort_icon(key)}
			</th>`;

		$content.addClass("th-export-scope").html(`
			<div style="margin-bottom:8px;display:flex;gap:8px;align-items:center">
				<input type="search" class="recv-search form-control form-control-sm"
					placeholder="${__("Filter customers...")}" style="max-width:280px">
				${this._export_btn(__("Receivables"))}
				${this._refresh_btn("receivables")}
			</div>
			<div style="overflow-x:auto">
			<table style="width:100%;border-collapse:collapse;font-size:12px" class="recv-summary-table">
				<thead>
					<tr style="background:var(--subtle-fg)">
						<th style="padding:5px 8px;width:28px;border-bottom:2px solid ${accent}"></th>
						${th(__("Customer"), "customer")}
						${th(__("Group"), "customer_group")}
						${th(__("Invoiced"), "total_invoiced", "right")}
						${th(__("Paid"), "total_paid", "right")}
						${th(__("Outstanding"), "outstanding", "right")}
						${th(__("0–30"), "bucket_0_30", "right")}
						${th(__("31–60"), "bucket_31_60", "right")}
						${th(__("61–90"), "bucket_61_90", "right")}
						${th(__("90+"), "bucket_90_plus", "right")}
						${th(__("Last Payment"), "last_payment")}
						${show_future ? th(__("Future Payments"), "future_payments", "right") : ""}
						<th style="padding:5px 8px;border-bottom:2px solid ${accent}"></th>
					</tr>
				</thead>
				<tbody>
					${rows.map((r, i) => {
						const ind = r.bucket_90_plus > 0 ? "red" : r.bucket_61_90 > 0 ? "orange" : "";
						const hl = (r.overdue || 0) > 0 ? "is-red" : ((r.outstanding || 0) > 0 || (r.unallocated_advance || 0) > 0) ? "is-amber" : "";
						const info_title = hl === "is-red" ? __("Overdue invoices — click for details")
							: hl ? __("Outstanding or advances pending — click for details") : __("Party details");
						return `
						<tr class="recv-summary-row" data-party="${r.customer}" data-company="${company}" data-as-of="${as_of_date}"
							style="${i % 2 ? "background:var(--control-bg)" : ""};cursor:pointer">
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color);color:var(--text-muted)">▶</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">
								${ind ? `<span class="indicator-pill ${ind}" style="font-size:10px;margin-right:4px"> </span>` : ""}${r.customer}<span class="th-party-info-btn${hl ? " " + hl : ""}" data-party="${r.customer}" data-party-type="customer" data-company="${company}" data-as-of="${as_of_date}" data-show-future="${show_future ? 1 : 0}" title="${info_title}">${_ICONS.info}</span>
							</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.customer_group || ""}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.total_invoiced, bc)}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.total_paid, bc)}</td>
							<td style="padding:4px 8px;text-align:right;font-weight:700;border-bottom:1px solid var(--border-color)">${format_currency(r.outstanding, bc)}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r.bucket_0_30 > 0 ? format_currency(r.bucket_0_30, bc) : "—"}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r.bucket_31_60 > 0 ? format_currency(r.bucket_31_60, bc) : "—"}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r.bucket_61_90 > 0 ? format_currency(r.bucket_61_90, bc) : "—"}</td>
							<td style="padding:4px 8px;text-align:right;${r.bucket_90_plus > 0 ? "color:var(--red);font-weight:700;" : ""}border-bottom:1px solid var(--border-color)">${r.bucket_90_plus > 0 ? format_currency(r.bucket_90_plus, bc) : "—"}</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.last_payment ? frappe.datetime.str_to_user(r.last_payment) : "—"}</td>
							${show_future ? `<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r.future_payments > 0 ? format_currency(r.future_payments, bc) : "—"}</td>` : ""}
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">
								<div class="th-party-actions" style="display:flex;gap:1px;align-items:center" data-party="${r.customer}" data-party-type="customer" data-company="${company}" data-as-of="${as_of_date}">
									<button class="th-action-btn btn-copy-text" title="${__("Copy text")}">${_ICONS.copy}</button>
									<button class="th-action-btn btn-copy-link" title="${__("Copy internal link")}">${_ICONS.link}</button>
									<button class="th-action-btn btn-statement" title="${__("Statement")}">${_ICONS.statement}</button>
								</div>
							</td>
						</tr>
						<tr class="recv-detail-row hidden" data-detail-for="${r.customer}">
							<td colspan="${show_future ? 13 : 12}" style="padding:0;border-bottom:2px solid var(--border-color)">
								<div class="recv-detail-content" data-for="${r.customer}" style="padding:8px 24px;background:var(--card-bg)">
									<span class="text-muted">${__("Loading...")}</span>
								</div>
							</td>
						</tr>`;
					}).join("")}
				</tbody>
			</table>
			</div>
		`);
	}

	_render_outstanding_detail(rows, is_customer, show_future) {
		if (!rows.length)
			return `<span class="text-muted">${__("No outstanding invoices found")}</span>`;
		const bc = this.base_currency;
		const slug = is_customer ? "sales-invoice" : "purchase-invoice";
		const show_future_col = !!show_future;
		return `
			<div style="overflow-x:auto">
			<table style="width:100%;border-collapse:collapse;font-size:11px">
				<thead>
					<tr style="background:var(--subtle-fg)">
						<th style="padding:3px 8px;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Date")}</th>
						<th style="padding:3px 8px;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Invoice No.")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Grand Total")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Paid")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted);font-weight:700;border-bottom:1px solid var(--border-color)">${__("Outstanding")}</th>
						<th style="padding:3px 8px;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Due Date")}</th>
						<th style="padding:3px 8px;text-align:right;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Days Overdue")}</th>
						<th style="padding:3px 8px;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Status")}</th>
						${show_future_col ? `<th style="padding:3px 8px;text-align:right;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${__("Future Payment")}</th>` : ""}
					</tr>
				</thead>
				<tbody>
					${rows.map((r, i) => `
						<tr style="${i % 2 ? "background:var(--subtle-fg)" : ""}">
							<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)">${frappe.datetime.str_to_user(r.date)}</td>
							<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/${slug}/${r.voucher_no}" target="_blank">${r.voucher_no}</a></td>
							<td style="padding:3px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.grand_total, bc)}</td>
							<td style="padding:3px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.paid, bc)}</td>
							<td style="padding:3px 8px;text-align:right;font-weight:700;border-bottom:1px solid var(--border-color)">${format_currency(r.outstanding_amount, bc)}</td>
							<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)">${r.due_date ? frappe.datetime.str_to_user(r.due_date) : "—"}</td>
							<td style="padding:3px 8px;text-align:right;${r.days_overdue > 90 ? "color:var(--red);font-weight:700;" : r.days_overdue > 60 ? "color:var(--orange);" : ""}border-bottom:1px solid var(--border-color)">${r.days_overdue || 0}</td>
							<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)">${this._status_pill(r.status)}</td>
							${show_future_col ? `<td style="padding:3px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r.future_amount > 0 ? format_currency(r.future_amount, bc) : "—"}</td>` : ""}
						</tr>`).join("")}
				</tbody>
			</table>
			</div>`;
	}

	_copy_party_text(party_type, party, company, as_of_date, detail_rows) {
		const is_customer = party_type === "customer";
		const header = [
			`Transaction List`,
			`${is_customer ? "Customer" : "Supplier"}: ${party}`,
			`Company: ${company}`,
			`As Of: ${frappe.datetime.str_to_user(as_of_date)}`,
			``,
			`Invoice No.       Due Date               Amount`,
			`──────────────────────────────────────────────────`,
		];
		const body = detail_rows.map(r => {
			const due = r.due_date ? frappe.datetime.str_to_user(r.due_date) : "—";
			const overdue = r.days_overdue > 0 ? ` (+${r.days_overdue})` : "";
			return `${(r.voucher_no || "").padEnd(18)}${(due + overdue).padEnd(22)}${format_number(r.outstanding_amount, null, 2).padStart(14)}`;
		});
		const total = detail_rows.reduce((s, r) => s + (r.outstanding_amount || 0), 0);
		const footer = [``, `Total Outstanding: ${format_number(total, null, 2)}`];
		const text = [...header, ...body, ...footer].join("\n");
		navigator.clipboard.writeText(text).then(() => {
			frappe.show_alert({ message: __("Copied to clipboard"), indicator: "green" });
		}).catch(() => frappe.msgprint(__("Clipboard not available")));
	}

	_copy_party_link(tab, party_type, party) {
		const url = `${window.location.origin}/app/transaction-history?tab=${tab}&${party_type}=${encodeURIComponent(party)}`;
		navigator.clipboard.writeText(url).then(() => {
			frappe.show_alert({ message: __("Link copied"), indicator: "green" });
		}).catch(() => frappe.msgprint(__("Clipboard not available")));
	}

	_generate_statement_html(party_type, party, company, as_of_date, detail_rows) {
		const is_customer = party_type === "customer";
		const bc = this.base_currency;
		const total = detail_rows.reduce((s, r) => s + (r.outstanding_amount || 0), 0);
		return `<!DOCTYPE html><html><head><title>Transaction List — ${party}</title>
<style>
	body{font-family:Arial,sans-serif;padding:32px;font-size:13px;color:#222}
	h2{margin:0 0 4px}
	.meta{color:#666;margin-bottom:24px;font-size:12px}
	table{width:100%;border-collapse:collapse}
	th{padding:7px 8px;background:#f0f0f0;border-bottom:2px solid #333;text-align:left;white-space:nowrap}
	th.r,td.r{text-align:right}
	td{padding:5px 8px;border-bottom:1px solid #ddd}
	.total{margin-top:16px;text-align:right;font-weight:bold;font-size:14px}
	@media print{body{padding:0}}
</style></head><body>
<h2>Transaction List</h2>
<div class="meta">
	<strong>${is_customer ? "Customer" : "Supplier"}:</strong> ${party}<br>
	<strong>Company:</strong> ${company}<br>
	<strong>As Of:</strong> ${frappe.datetime.str_to_user(as_of_date)}
</div>
<table>
	<thead><tr>
		<th>${__("Date")}</th><th>${__("Invoice No.")}</th>
		<th class="r">${__("Grand Total")}</th><th class="r">${__("Paid")}</th>
		<th class="r">${__("Outstanding")}</th><th>${__("Due Date")}</th>
		<th class="r">${__("Days Overdue")}</th><th>${__("Status")}</th>
	</tr></thead>
	<tbody>
		${detail_rows.map(r => `<tr>
			<td>${frappe.datetime.str_to_user(r.date)}</td>
			<td>${r.voucher_no || ""}</td>
			<td class="r">${format_number(r.grand_total, null, 2)}</td>
			<td class="r">${format_number(r.paid, null, 2)}</td>
			<td class="r"><strong>${format_number(r.outstanding_amount, null, 2)}</strong></td>
			<td>${r.due_date ? frappe.datetime.str_to_user(r.due_date) : "—"}</td>
			<td class="r" style="${r.days_overdue > 90 ? "color:red;font-weight:bold" : r.days_overdue > 60 ? "color:darkorange" : ""}">${r.days_overdue || 0}</td>
			<td>${r.status || ""}</td>
		</tr>`).join("")}
	</tbody>
</table>
<div class="total">Total Outstanding: ${format_number(total, null, 2)}</div>
</body></html>`;
	}

	// ── Statement dialog ──────────────────────────────────────────────────────

	/**
	 * Detail rows for a party, reusing what the expanded accordion already loaded.
	 *
	 * The cache is only valid for the as-of date it was fetched at, so changing "As of" inside the
	 * dialog must re-fetch rather than silently reuse rows from another date.
	 */
	_detail_rows(party_type, party, company, as_of_date, allow_cache) {
		const is_customer = party_type === "customer";
		const $dc = $(this.page.main).find(
			is_customer
				? `.recv-detail-content[data-for="${party}"]`
				: `.pay-detail-content[data-for="${party}"]`
		);
		const cached = allow_cache ? $dc.data("rows") : null;
		if (cached) return Promise.resolve(cached);

		const method = is_customer
			? "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_receivables_detail"
			: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_payables_detail";
		const args = is_customer
			? { customer: party, company, as_of_date }
			: { supplier: party, company, as_of_date };
		return frappe.xcall(method, args).then((rows) => rows || []);
	}

	_open_statement_dialog(party_type, party, company, as_of_date) {
		cecypo_reports.statement.open({
			party,
			party_type,
			company,
			as_of_date,
			// Supplied only from here: the query reports have no transaction list to offer, so their
			// dialog shows no Document selector at all.
			transaction_list: {
				label: __("Transaction list"),
				get_html: (ctx) =>
					this._detail_rows(
						ctx.party_type,
						ctx.party,
						ctx.company,
						ctx.as_of_date,
						ctx.as_of_date === as_of_date
					).then((rows) =>
						this._generate_statement_html(ctx.party_type, ctx.party, ctx.company, ctx.as_of_date, rows)
					),
				download: (html) => this._print_html(html),
				send: (html, ctx, { recipient, cc, bcc }) =>
					frappe
						.xcall(
							"cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.send_statement_email",
							{
								party_type: ctx.party_type,
								party: ctx.party,
								company: ctx.company,
								as_of_date: ctx.as_of_date,
								html_content: html,
								recipient_email: recipient,
								cc,
								bcc,
							}
						)
						.then(() =>
							frappe.show_alert({
								message: __("Transaction list queued to {0}", [recipient]),
								indicator: "green",
							})
						),
			},
		});
	}

	// The transaction list is plain HTML rather than a server-rendered PDF, so "download" means
	// hand it to the browser's own print-to-PDF, as it always has.
	_print_html(html) {
		if (!html) { frappe.msgprint(__("Nothing to print yet.")); return; }
		const win = window.open("", "_blank");
		if (!win) { frappe.msgprint(__("Popup was blocked. Please allow popups for this site and try again.")); return; }
		win.document.write(html);
		win.document.close();
		win.print();
	}

	// ── Copy-selected helpers ─────────────────────────────────────────────────

	_update_copy_selected_btn(party_type, $m) {
		const count = $m.find(`table[data-party-type="${party_type}"] .party-row-check:checked`).length;
		const $btn = $m.find(`.btn-copy-selected-items[data-party-type="${party_type}"]`);
		$btn.prop("disabled", count === 0)
			.css({ opacity: count > 0 ? 1 : 0.4, cursor: count > 0 ? "pointer" : "not-allowed" });
		$btn.find(".copy-sel-count").text(count > 0 ? __("{0} selected", [count]) : __("0 selected"));
	}

	_copy_selected_items(party_type, $m) {
		const lines = [];
		$m.find(`table[data-party-type="${party_type}"] .party-row-check:checked`).each((_, el) => {
			const $row = $(el).closest(".summary-row");
			const item_name = $row.find("td").eq(3).text().trim();
			const last_rate = $row.attr("data-last-rate");
			lines.push(`${item_name}: ${last_rate ? format_number(parseFloat(last_rate), null, 2) : "—"}`);
		});
		if (!lines.length) return;
		navigator.clipboard.writeText(lines.join("\n")).then(() => {
			frappe.show_alert({ message: __("{0} item(s) copied to clipboard", [lines.length]), indicator: "green" });
		}).catch(() => frappe.msgprint(__("Clipboard not available")));
	}

	// ── Party info dialog ─────────────────────────────────────────────────────

	_show_party_info_dialog(party_type, party, company, as_of_date, show_future_payments) {
		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_party_details",
			args: { party_type, party, company, as_of_date, show_future_payments: show_future_payments ? 1 : 0 },
			callback: (r) => {
				const d = r.message || {};
				const bc = this.base_currency;
				const is_customer = party_type === "customer";
				const stats = d.stats || {};
				const money = (v) => format_currency(v || 0, bc);
				const date = (v) => (v ? frappe.datetime.str_to_user(v) : "—");
				const card_style = "background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:10px 12px;min-width:0";
				const lbl = (t) => `<div style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;white-space:nowrap">${t}</div>`;
				const val = (v, color) => `<div style="font-size:14px;font-weight:700;${color ? "color:" + color + ";" : ""}">${v}</div>`;
				const card = (label, value, color) => `<div style="${card_style}">${lbl(label)}${val(value, color)}</div>`;
				const sec = (t) => `<div style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin:14px 0 6px">${t}</div>`;

				let cards = `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px">
					${card(__("Total Outstanding"), money(d.outstanding_total), d.outstanding_total > 0 ? "var(--red)" : "var(--green)")}
					${card(__("Overdue"), `${d.overdue_count || 0} · ${money(d.overdue_total)}`, d.overdue_count ? "var(--red)" : "")}
					${card(__("Unallocated Advances"), money(d.advances_total), d.advances_total > 0 ? "var(--green)" : "")}
					${is_customer ? card(__("Credit Limit"), d.credit_limit != null ? money(d.credit_limit) : "—") : card(__("Payment Terms"), d.payment_terms || "—")}
				</div>`;
				if (stats.annual_billing != null || stats.lifetime_billing != null) {
					cards += `<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:8px">
						${card(__("Annual Billing"), money(stats.annual_billing))}
						${card(__("Lifetime Billing"), money(stats.lifetime_billing))}
						${card(__("Last Transaction"), date(stats.last_transaction))}
					</div>`;
				}

				const invoices = (d.invoices || []).length
					? this._render_outstanding_detail(d.invoices, is_customer, show_future_payments)
					: `<div class="text-muted" style="font-size:12px">${__("No outstanding invoices")}</div>`;

				const adv_rows = (d.advances || []).map((p, i) => `
					<tr style="${i % 2 ? "background:var(--control-bg)" : ""}">
						<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/payment-entry/${p.name}" target="_blank">${p.name}</a></td>
						<td style="padding:3px 8px;border-bottom:1px solid var(--border-color)">${date(p.posting_date)}</td>
						<td style="padding:3px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${money(p.paid_amount)}</td>
						<td style="padding:3px 8px;text-align:right;font-weight:700;color:var(--green);border-bottom:1px solid var(--border-color)">${money(p.unallocated_amount)}</td>
					</tr>`).join("");
				const advances = adv_rows
					? `<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:11px">
						<thead><tr style="background:var(--subtle-fg)">
							<th style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${__("Payment Entry")}</th>
							<th style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${__("Date")}</th>
							<th style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${__("Paid")}</th>
							<th style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${__("Unallocated")}</th>
						</tr></thead><tbody>${adv_rows}</tbody></table></div>`
					: `<div class="text-muted" style="font-size:12px">${__("No open payments")}</div>`;

				const c = d.primary_contact;
				let contact = `<span class="text-muted">${__("No contact on file")}</span>`;
				if (c) {
					contact = `<strong>${frappe.utils.escape_html(c.name || "")}</strong>`
						+ (c.email ? ` · <a href="mailto:${c.email}" style="color:inherit">${c.email}</a>` : "")
						+ (c.phone ? ` · <a href="tel:${c.phone}" style="color:inherit">${c.phone}</a>` : "");
				}
				if (d.payment_terms && is_customer) contact += `<div class="text-muted">${__("Payment Terms")}: ${d.payment_terms}</div>`;

				const dialog = new frappe.ui.Dialog({
					title: d.customer_name || party,
					indicator: d.overdue_count ? "red" : "blue",
					size: "large",
					primary_action_label: __("Email {0}", [is_customer ? __("Customer") : __("Supplier")]),
					primary_action: () => this._email_party_snapshot(party_type, party, d, bc),
					secondary_action_label: __("Copy to Clipboard"),
					secondary_action: () => this._copy_party_snapshot(d, bc),
				});
				dialog.add_custom_action(__("Close"), () => dialog.hide());
				dialog.$body.html(`<div style="padding:4px 0">
					${cards}
					${d.basis === "invoices" ? this._basis_note_html() : ""}
					${sec(__("Outstanding invoices"))}${invoices}
					${sec(__("Open payments"))}${advances}
					${sec(__("Contact"))}<div style="font-size:12px">${contact}</div>
				</div>`);
				dialog.show();
			},
		});
	}

	_party_snapshot_text(d, bc) {
		const pad = (s, n) => { s = String(s == null ? "" : s); return s + " ".repeat(Math.max(0, n - s.length)); };
		const money = (v) => format_currency(v || 0, bc);
		const sep = "-".repeat(72);
		const lines = [`Dear ${d.customer_name || ""},`, ""];
		if ((d.invoices || []).length) {
			lines.push("Your account currently shows the following outstanding invoices:");
			lines.push(pad("Invoice", 22) + pad("Due Date", 14) + pad("Days Overdue", 14) + "Outstanding");
			lines.push(sep);
			d.invoices.forEach((r) => lines.push(pad(r.voucher_no, 22) + pad(r.due_date ? frappe.datetime.str_to_user(r.due_date) : "", 14) + pad(r.days_overdue || 0, 14) + money(r.outstanding_amount)));
			lines.push(sep);
			lines.push("Total Outstanding: " + money(d.outstanding_total));
		} else {
			lines.push("Your account has no outstanding invoices.");
		}
		if ((d.advances || []).length) {
			lines.push("", "Unallocated payments on your account:");
			d.advances.forEach((a) => lines.push(pad(a.name, 22) + pad(frappe.datetime.str_to_user(a.posting_date), 14) + money(a.unallocated_amount)));
			lines.push("Net position: " + money(d.net_position));
		}
		lines.push("", d.overdue_count ? "Kindly arrange for payment at your earliest convenience." : "Thank you for your business.");
		return lines.join("\n");
	}

	_copy_party_snapshot(d, bc) {
		navigator.clipboard.writeText(this._party_snapshot_text(d, bc)).then(() => {
			frappe.show_alert({ message: __("Copied to clipboard"), indicator: "green" });
		});
	}

	_email_party_snapshot(party_type, party, d, bc) {
		const doctype = party_type === "customer" ? "Customer" : "Supplier";
		new frappe.views.CommunicationComposer({
			doc: { doctype, name: party },
			subject: __("Account statement — {0}: {1} outstanding", [d.customer_name || party, format_currency(d.outstanding_total || 0, bc)]),
			recipients: d.primary_email || "",
			message: `<pre style="font-family:inherit;white-space:pre-wrap">${frappe.utils.escape_html(this._party_snapshot_text(d, bc))}</pre>`,
		});
	}

	// ── Payables ──────────────────────────────────────────────────────────────

	_load_payables(refresh = false) {
		const m = this.page.main;
		const company = this.controls.pay_company.get_value();
		const as_of_date = this.controls.pay_as_of.get_value();
		if (!company || !as_of_date) { frappe.msgprint(__("Company and As Of Date are required")); return; }
		const supplier = this.controls.pay_supplier.get_value() || null;
		const show_future_payments = this.controls.pay_show_future.get_value() ? 1 : 0;
		const $content = $(m).find(".payables-content");
		$content.html(`<div class="text-muted" style="padding:20px">${__("Loading...")}</div>`);
		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_payables",
			args: { company, as_of_date, supplier, show_future_payments, refresh: refresh ? 1 : 0 },
			callback: (r) => {
				if (r.message != null) {
					this._pay_state.rows = r.message;
					this._pay_state.company = company;
					this._pay_state.as_of_date = as_of_date;
					this._pay_state.show_future_payments = show_future_payments;
					this._render_payables(r.message, company, as_of_date, supplier);
					this._stamp($content, r.th_fetched_at);
					this._get_balance_basis().then((basis) => {
						if (basis === "invoices") $(m).find(".payables-content").prepend(this._basis_note_html());
					});
				}
			},
		});
	}

	_render_payables(rows, company, as_of_date, supplier) {
		const m = this.page.main;
		const $content = $(m).find(".payables-content");
		const bc = this.base_currency;
		const accent = "var(--green)";
		const show_future = !!this._pay_state.show_future_payments;

		if (!rows.length) {
			$content.html(`<div class="text-muted" style="padding:20px">${__("No outstanding payables found")}</div>`);
			return;
		}

		if (supplier) {
			const r = rows[0];
			const oldest = r.bucket_90_plus > 0 ? "90+" : r.bucket_61_90 > 0 ? "61–90" : r.bucket_31_60 > 0 ? "31–60" : __("Current");
			const hl = (r.overdue || 0) > 0 ? "is-red" : ((r.outstanding || 0) > 0 || (r.unallocated_advance || 0) > 0) ? "is-amber" : "";
			const info_title = hl === "is-red" ? __("Overdue invoices — click for details")
				: hl ? __("Outstanding or advances pending — click for details") : __("Party details");
			$content.html(`
				<div class="th-stats-3col" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px">
					<div style="background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:12px 16px">
						<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px">${__("Total Outstanding")}</div>
						<div style="font-size:18px;font-weight:700;color:var(--orange)">${format_currency(r.outstanding, bc)}</div>
					</div>
					<div style="background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:12px 16px">
						<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px">${__("Oldest Bucket")}</div>
						<div style="font-size:18px;font-weight:700">${oldest}</div>
					</div>
					<div style="background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:12px 16px">
						<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px">${__("Last Payment")}</div>
						<div style="font-size:18px;font-weight:700">${r.last_payment ? frappe.datetime.str_to_user(r.last_payment) : "—"}</div>
					</div>
				</div>
				<div style="margin-bottom:12px;display:flex;gap:4px;align-items:center">
					<div class="th-party-actions" style="display:flex;gap:1px;align-items:center" data-party="${supplier}" data-party-type="supplier" data-company="${company}" data-as-of="${as_of_date}">
						<button class="th-action-btn btn-copy-text" title="${__("Copy text")}">${_ICONS.copy}</button>
						<button class="th-action-btn btn-copy-link" title="${__("Copy internal link")}">${_ICONS.link}</button>
						<button class="th-action-btn btn-statement" title="${__("Statement")}">${_ICONS.statement}</button>
					</div>
					<span class="th-party-info-btn${hl ? " " + hl : ""}" data-party="${supplier}" data-party-type="supplier" data-company="${company}" data-as-of="${as_of_date}" data-show-future="${show_future ? 1 : 0}" title="${info_title}" style="margin-left:4px">${_ICONS.info}</span>
				</div>
				<div class="pay-detail-content" data-for="${supplier}" style="padding:4px 0">
					<div class="text-muted" style="padding:12px">${__("Loading invoices...")}</div>
				</div>
			`);
			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_payables_detail",
				args: { supplier, company, as_of_date, show_future_payments: show_future ? 1 : 0 },
				callback: (r2) => {
					$content.find(`.pay-detail-content[data-for="${supplier}"]`)
						.html(this._render_outstanding_detail(r2.message || [], false, show_future))
						.data("rows", r2.message || []);
				},
			});
			return;
		}

		const sort_icon = (key) => this._pay_state.sort_key !== key
			? `<span style="opacity:.35;font-size:10px"> ↕</span>`
			: this._pay_state.sort_dir === "asc" ? `<span style="font-size:10px"> ↑</span>` : `<span style="font-size:10px"> ↓</span>`;
		const th = (label, key, align) => `
			<th class="pay-sort-header" data-sort-key="${key}"
				style="padding:5px 8px;text-align:${align || "left"};color:var(--text-muted);font-weight:600;border-bottom:2px solid ${accent};cursor:pointer;white-space:nowrap;user-select:none">
				${label}${sort_icon(key)}
			</th>`;

		$content.addClass("th-export-scope").html(`
			<div style="margin-bottom:8px;display:flex;gap:8px;align-items:center">
				<input type="search" class="pay-search form-control form-control-sm"
					placeholder="${__("Filter suppliers...")}" style="max-width:280px">
				${this._export_btn(__("Payables"))}
				${this._refresh_btn("payables")}
			</div>
			<div style="overflow-x:auto">
			<table style="width:100%;border-collapse:collapse;font-size:12px" class="pay-summary-table">
				<thead>
					<tr style="background:var(--subtle-fg)">
						<th style="padding:5px 8px;width:28px;border-bottom:2px solid ${accent}"></th>
						${th(__("Supplier"), "supplier")}
						${th(__("Group"), "supplier_group")}
						${th(__("Invoiced"), "total_invoiced", "right")}
						${th(__("Paid"), "total_paid", "right")}
						${th(__("Outstanding"), "outstanding", "right")}
						${th(__("0–30"), "bucket_0_30", "right")}
						${th(__("31–60"), "bucket_31_60", "right")}
						${th(__("61–90"), "bucket_61_90", "right")}
						${th(__("90+"), "bucket_90_plus", "right")}
						${th(__("Last Payment"), "last_payment")}
						${show_future ? th(__("Future Payments"), "future_payments", "right") : ""}
						<th style="padding:5px 8px;border-bottom:2px solid ${accent}"></th>
					</tr>
				</thead>
				<tbody>
					${rows.map((r, i) => {
						const ind = r.bucket_90_plus > 0 ? "red" : r.bucket_61_90 > 0 ? "orange" : "";
						const hl = (r.overdue || 0) > 0 ? "is-red" : ((r.outstanding || 0) > 0 || (r.unallocated_advance || 0) > 0) ? "is-amber" : "";
						const info_title = hl === "is-red" ? __("Overdue invoices — click for details")
							: hl ? __("Outstanding or advances pending — click for details") : __("Party details");
						return `
						<tr class="pay-summary-row" data-party="${r.supplier}" data-company="${company}" data-as-of="${as_of_date}"
							style="${i % 2 ? "background:var(--control-bg)" : ""};cursor:pointer">
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color);color:var(--text-muted)">▶</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">
								${ind ? `<span class="indicator-pill ${ind}" style="font-size:10px;margin-right:4px"> </span>` : ""}${r.supplier}<span class="th-party-info-btn${hl ? " " + hl : ""}" data-party="${r.supplier}" data-party-type="supplier" data-company="${company}" data-as-of="${as_of_date}" data-show-future="${show_future ? 1 : 0}" title="${info_title}">${_ICONS.info}</span>
							</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.supplier_group || ""}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.total_invoiced, bc)}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.total_paid, bc)}</td>
							<td style="padding:4px 8px;text-align:right;font-weight:700;border-bottom:1px solid var(--border-color)">${format_currency(r.outstanding, bc)}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r.bucket_0_30 > 0 ? format_currency(r.bucket_0_30, bc) : "—"}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r.bucket_31_60 > 0 ? format_currency(r.bucket_31_60, bc) : "—"}</td>
							<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r.bucket_61_90 > 0 ? format_currency(r.bucket_61_90, bc) : "—"}</td>
							<td style="padding:4px 8px;text-align:right;${r.bucket_90_plus > 0 ? "color:var(--red);font-weight:700;" : ""}border-bottom:1px solid var(--border-color)">${r.bucket_90_plus > 0 ? format_currency(r.bucket_90_plus, bc) : "—"}</td>
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.last_payment ? frappe.datetime.str_to_user(r.last_payment) : "—"}</td>
							${show_future ? `<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${r.future_payments > 0 ? format_currency(r.future_payments, bc) : "—"}</td>` : ""}
							<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">
								<div class="th-party-actions" style="display:flex;gap:1px;align-items:center" data-party="${r.supplier}" data-party-type="supplier" data-company="${company}" data-as-of="${as_of_date}">
									<button class="th-action-btn btn-copy-text" title="${__("Copy text")}">${_ICONS.copy}</button>
									<button class="th-action-btn btn-copy-link" title="${__("Copy internal link")}">${_ICONS.link}</button>
									<button class="th-action-btn btn-statement" title="${__("Statement")}">${_ICONS.statement}</button>
								</div>
							</td>
						</tr>
						<tr class="pay-detail-row hidden" data-detail-for="${r.supplier}">
							<td colspan="12" style="padding:0;border-bottom:2px solid var(--border-color)">
								<div class="pay-detail-content" data-for="${r.supplier}" style="padding:8px 24px;background:var(--card-bg)">
									<span class="text-muted">${__("Loading...")}</span>
								</div>
							</td>
						</tr>`;
					}).join("")}
				</tbody>
			</table>
			</div>
		`);
	}

	// ── Pricing ───────────────────────────────────────────────────────────────

	_run_pricing(refresh = false) {
		const m = this.page.main;
		const company = this.controls.pricing_company.get_value();
		if (!company) { frappe.msgprint(__("Company is required")); return; }

		const checked = this._pricing_panel.items.filter(it => it.checked);
		if (!checked.length) return;

		const from_date = this.controls.pricing_from.get_value() || null;
		const to_date = this.controls.pricing_to.get_value() || null;
		const price_list_filter = this.controls.pricing_price_list.get_value() || null;

		this._pricing_run_gen = (this._pricing_run_gen || 0) + 1;
		const gen = this._pricing_run_gen;
		$(m).find(".btn-run-pricing").prop("disabled", true);
		let pending = checked.length;

		this._pricing_panel.active_tab = checked[0].item_code;
		this._render_pricing_tabs(checked);

		checked.forEach(item => {
			let history_data = null;
			let price_data = null;
			let done = 0;
			const maybe_render = () => {
				if (++done < 2 || gen !== this._pricing_run_gen) return;
				this._fill_pricing_tab(item.item_code, history_data, price_data, price_list_filter);
				if (--pending === 0) {
					const cnt = this._pricing_panel.items.filter(it => it.checked).length;
					$(m).find(".btn-run-pricing").prop("disabled", cnt === 0);
				}
			};
			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_item_history",
				args: { item: item.item_code, company, from_date, to_date, warehouse: null, refresh: refresh ? 1 : 0 },
				callback: (r) => { history_data = r.message; this._stamp($(m).find(".pricing-panel-body"), r.th_fetched_at); maybe_render(); },
			});
			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_item_prices",
				args: { item_code: item.item_code },
				callback: (r) => { price_data = r.message || []; maybe_render(); },
			});
		});
	}

	_render_pricing_tabs(items) {
		const m = this.page.main;
		const $strip = $(m).find(".pricing-tabs-strip");
		const $content = $(m).find(".pricing-content");

		$strip.html(`
			<div style="margin-bottom:8px">
				<ul class="nav nav-tabs" style="margin-bottom:0">
					${items.map((item, i) => `
						<li class="nav-item">
							<a class="nav-link pricing-tab-link ${i === 0 ? "active" : ""}"
								href="#" data-item="${item.item_code}"
								style="font-size:12px;padding:6px 12px">
								${item.item_code}
							</a>
						</li>
					`).join("")}
				</ul>
			</div>
		`);

		$content.html(items.map((item, i) => `
			<div class="pricing-tab-panel ${i === 0 ? "" : "hidden"}" data-item="${item.item_code}">
				<div class="text-muted" style="padding:20px">${__("Loading...")}</div>
			</div>
		`).join(""));
	}

	_fill_pricing_tab(item_code, history, prices, price_list_filter) {
		const m = this.page.main;
		const $panel = $(m).find(`.pricing-tab-panel[data-item="${item_code}"]`);
		$panel.empty();
		if (!history) { $panel.html(`<div class="text-muted" style="padding:20px">${__("Error loading data")}</div>`); return; }
		this._render_pricing_tab(history, prices || [], price_list_filter, $panel, item_code);
	}

	_render_pricing_tab({ purchases, sales, can_see_cost }, prices, price_list_filter, $container, item_code) {
		const bc = this.base_currency;

		const can_edit = frappe.model.can_write("Item Price");
		const costed = purchases.filter(r => r.valuation_rate != null);
		const avg_val_rate = costed.length
			? costed.reduce((s, r) => s + r.valuation_rate, 0) / costed.length
			: null;
		const show_val = purchases.length
			? purchases.some(r => "valuation_rate" in r)
			: (can_see_cost ?? this._item_panel.can_see_cost) !== false;

		const price_panel_html = `
			<div class="th-export-scope" style="background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:12px;margin-bottom:16px">
				<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px"><span style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em">${__("Price List Rates")}</span>${this._export_btn(__("Price List Rates {0}", [item_code]))}</div>
				${prices.length ? `
				<div style="overflow-x:auto">
				<table style="width:100%;border-collapse:collapse;font-size:12px">
					<thead>
						<tr style="background:var(--subtle-fg)">
							<th style="padding:4px 8px;color:var(--text-muted);border-bottom:2px solid var(--border-color)">${__("Price List")}</th>
							<th style="padding:4px 8px;color:var(--text-muted);border-bottom:2px solid var(--border-color)">${__("Type")}</th>
							<th style="padding:4px 8px;text-align:right;color:var(--text-muted);border-bottom:2px solid var(--border-color)">${__("Rate")}</th>
							<th style="padding:4px 8px;color:var(--text-muted);border-bottom:2px solid var(--border-color)">${__("Currency")}</th>
							<th style="padding:4px 8px;color:var(--text-muted);border-bottom:2px solid var(--border-color)">${__("Valid From")}</th>
							<th style="padding:4px 8px;color:var(--text-muted);border-bottom:2px solid var(--border-color)">${__("Valid Upto")}</th>
							${can_edit ? `<th style="padding:4px 8px;border-bottom:2px solid var(--border-color)"></th>` : ""}
						</tr>
					</thead>
					<tbody>
						${prices.map((p, i) => `
							<tr class="price-list-row" style="${i % 2 ? "background:var(--control-bg)" : ""}"
								data-pl="${p.price_list}" data-item="${item_code}" data-name="${p.name || ""}">
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${p.price_list}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">
									<span class="indicator-pill ${p.type === "Selling" ? "blue" : "green"}" style="font-size:10px">${__(p.type)}</span>
								</td>
								<td style="padding:4px 8px;text-align:right;font-weight:700;border-bottom:1px solid var(--border-color)">${format_number(p.price_list_rate, null, 2)}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${p.currency || ""}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${p.valid_from ? frappe.datetime.str_to_user(p.valid_from) : "—"}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${p.valid_upto ? frappe.datetime.str_to_user(p.valid_upto) : "—"}</td>
								${can_edit ? `
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">
									${p.type === "Selling" ? `<button class="btn btn-xs btn-default btn-edit-price" data-pl="${p.price_list}" data-item="${item_code}"
										data-avg-val="${avg_val_rate !== null ? avg_val_rate.toFixed(2) : ""}"
										title="${__("Edit price")}">✏️</button>` : ""}
								</td>` : ""}
							</tr>
							<tr class="price-edit-row hidden" data-edit-for-pl="${p.price_list}" data-edit-for-item="${item_code}">
								<td colspan="${can_edit ? 7 : 6}" style="padding:8px 12px;background:var(--card-bg);border-bottom:2px solid var(--border-color)">
									<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
										<span style="font-size:12px;color:var(--text-muted)">${__("Suggested")}:
											<strong class="price-suggested">${avg_val_rate !== null ? format_number(avg_val_rate * 1.3, null, 2) : __("N/A")}</strong>
										</span>
										${avg_val_rate !== null ? `
										<span style="font-size:12px;color:var(--text-muted)">${__("Markup %")}:
											<input type="number" class="form-control form-control-sm price-markup-input"
												value="30" style="width:70px;display:inline-block"
												data-avg-val="${avg_val_rate.toFixed(2)}">
										</span>
										<span style="font-size:12px;color:var(--text-muted)">${__("Round")}:
											<select class="form-control form-control-sm price-round-select" style="width:70px;display:inline-block">
												<option value="0">${__("None")}</option>
												<option value="1">1</option>
												<option value="5">5</option>
												<option value="10">10</option>
												<option value="100">100</option>
											</select>
										</span>` : ""}
										<button class="btn btn-xs btn-default btn-use-last-sold" data-item="${item_code}" data-pl="${p.price_list}"
											style="font-size:11px">${__("Use Last Sold Rate")}</button>
										<label style="font-size:12px;color:var(--text-muted)">${__("New Rate")}:
											<input type="number" class="form-control form-control-sm price-new-rate-input"
												value="${p.price_list_rate}" style="width:100px;display:inline-block">
										</label>
										<button class="btn btn-primary btn-xs btn-save-price" data-item="${item_code}" data-pl="${p.price_list}">${__("Save")}</button>
										<button class="btn btn-default btn-xs btn-cancel-price" data-pl="${p.price_list}" data-item="${item_code}">${__("Cancel")}</button>
									</div>
								</td>
							</tr>
						`).join("")}
					</tbody>
				</table>
				</div>` : `<span class="text-muted" style="font-size:12px">${__("No Item Price records found for this item")}</span>`}
			</div>`;
		$container.append(price_panel_html);

		const filtered_sales = price_list_filter
			? sales.filter(r => r.selling_price_list === price_list_filter)
			: sales;

		const p_rates = purchases.map(r => r.valuation_rate || 0).filter(v => v > 0);
		const s_rates = filtered_sales.map(r => r.base_rate || 0).filter(v => v > 0);
		const stat = (arr) => arr.length
			? { min: Math.min(...arr), max: Math.max(...arr), avg: arr.reduce((a, b) => a + b, 0) / arr.length }
			: null;
		const ps = stat(p_rates), ss = stat(s_rates);
		const fmt = (v) => v != null ? format_number(v, null, 2) : "—";
		$container.append(`
			<div style="display:flex;flex-wrap:wrap;gap:16px;font-size:12px;margin-bottom:16px;padding:10px 12px;background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px">
				<span><span style="color:var(--text-muted)">${__("Buy Low / High / Avg")}:</span> <strong>${ps ? fmt(ps.min) : "—"} / ${ps ? fmt(ps.max) : "—"} / ${ps ? fmt(ps.avg) : "—"}</strong></span>
				<span><span style="color:var(--text-muted)">${__("Sell Low / High / Avg")}:</span> <strong>${ss ? fmt(ss.min) : "—"} / ${ss ? fmt(ss.max) : "—"} / ${ss ? fmt(ss.avg) : "—"}</strong></span>
			</div>
		`);

		const $grid = $(`<div class="item-results-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:16px">`).appendTo($container);

		const buy_th = (lbl, align) => `<th style="padding:5px 8px;${align ? "text-align:right;" : ""}border-bottom:2px solid var(--green);white-space:nowrap;color:var(--text-muted);font-weight:600">${lbl}</th>`;
		const sell_th = (lbl, align) => `<th style="padding:5px 8px;${align ? "text-align:right;" : ""}border-bottom:2px solid var(--blue);white-space:nowrap;color:var(--text-muted);font-weight:600">${lbl}</th>`;

		$(`
			<div class="th-export-scope" style="border:1px solid var(--border-color);border-radius:6px;overflow:hidden">
				<div style="background:var(--subtle-fg);padding:8px 12px;font-weight:600;border-bottom:2px solid var(--green);color:var(--green);display:flex;justify-content:space-between;align-items:center">${__("Purchases")}${this._export_btn(__("Purchases {0}", [item_code]))}</div>
				<div style="overflow:auto;max-height:340px">
				<table style="width:100%;border-collapse:collapse;font-size:12px">
					<thead><tr style="background:var(--subtle-fg)">
						${buy_th(__("Date"))}${buy_th(__("Voucher"))}${buy_th(__("Supplier"))}${buy_th(__("Qty"), true)}${buy_th(__("UOM"))}${buy_th(__("Rate"), true)}${show_val ? buy_th(__("Val. Rate"), true) : ""}${buy_th(__("Status"))}
					</tr></thead>
					<tbody>
						${purchases.length ? purchases.map((r, i) => `
							<tr style="${i % 2 ? "background:var(--control-bg)" : ""}">
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${frappe.datetime.str_to_user(r.date)}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/${r.doctype === "Purchase Receipt" ? "purchase-receipt" : "purchase-invoice"}/${r.voucher_no}" target="_blank">${r.voucher_no}</a></td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.supplier || ""}</td>
								<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.qty, null, 2)}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.uom || ""}</td>
								<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.rate, r.currency)}</td>
								${show_val ? `<td style="padding:4px 8px;text-align:right;font-weight:600;border-bottom:1px solid var(--border-color)">${format_currency(r.valuation_rate, bc)}</td>` : ""}
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${this._status_pill(r.status)}</td>
							</tr>`).join("") : `<tr><td colspan="${show_val ? 8 : 7}" style="padding:12px;text-align:center" class="text-muted">${__("No purchases found")}</td></tr>`}
					</tbody>
				</table>
				</div>
			</div>
		`).appendTo($grid);

		$(`
			<div class="th-export-scope" style="border:1px solid var(--border-color);border-radius:6px;overflow:hidden">
				<div style="background:var(--subtle-fg);padding:8px 12px;font-weight:600;border-bottom:2px solid var(--blue);color:var(--blue);display:flex;justify-content:space-between;align-items:center"><span>${__("Sales")}${price_list_filter ? ` — ${price_list_filter}` : ""}</span>${this._export_btn(__("Sales {0}", [item_code]))}</div>
				<div style="overflow:auto;max-height:340px">
				<table class="pricing-sales-table" style="width:100%;border-collapse:collapse;font-size:12px">
					<thead><tr style="background:var(--subtle-fg)">
						${sell_th(__("Date"))}${sell_th(__("Voucher"))}${sell_th(__("Customer"))}${sell_th(__("Group"))}${sell_th(__("Price List"))}${sell_th(__("Qty"), true)}${sell_th(__("UOM"))}${sell_th(__("Rate"), true)}${sell_th(__("Base Rate"), true)}${sell_th(__("Status"))}
					</tr></thead>
					<tbody>
						${filtered_sales.length ? filtered_sales.map((r, i) => `
							<tr style="${i % 2 ? "background:var(--control-bg)" : ""}">
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${frappe.datetime.str_to_user(r.date)}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/sales-invoice/${r.voucher_no}" target="_blank">${r.voucher_no}</a></td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.customer || ""}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.customer_group || ""}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.selling_price_list || ""}</td>
								<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.qty, null, 2)}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.uom || ""}</td>
								<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.rate, r.currency)}</td>
								<td style="padding:4px 8px;text-align:right;font-weight:600;border-bottom:1px solid var(--border-color)">${format_currency(r.base_rate, bc)}</td>
								<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${this._status_pill(r.status)}</td>
							</tr>`).join("") : `<tr><td colspan="10" style="padding:12px;text-align:center" class="text-muted">${__("No sales found")}</td></tr>`}
					</tbody>
				</table>
				</div>
			</div>
		`).appendTo($grid);
	}

	// ── URL param deep-linking ────────────────────────────────────────────────

	_read_url_params() {
		const params = new URLSearchParams(window.location.search);
		const tab = params.get("tab");
		if (!tab) return;

		const m = this.page.main;
		$(m).find(".nav-link[data-tab]").removeClass("active");
		$(m).find(`.nav-link[data-tab="${tab}"]`).addClass("active");
		$(m).find(".th-panel").addClass("hidden");
		$(m).find(`[data-panel="${tab}"]`).removeClass("hidden");

		const customer = params.get("customer");
		const supplier = params.get("supplier");

		setTimeout(() => {
			if (tab === "receivables" && customer && this.controls.recv_customer) {
				this.controls.recv_customer.set_value(customer).then(() => this._load_receivables());
			} else if (tab === "payables" && supplier && this.controls.pay_supplier) {
				this.controls.pay_supplier.set_value(supplier).then(() => this._load_payables());
			} else if (tab === "customer" && customer && this.controls.customer) {
				this.controls.customer.set_value(customer).then(() => this._load_customer_history());
			} else if (tab === "supplier" && supplier && this.controls.supplier) {
				this.controls.supplier.set_value(supplier).then(() => this._load_supplier_history());
			}
		}, 200);
	}

	_show_warehouse_popover($el) {
		$("#th-warehouse-popover").remove();
		const item_code = $el.data("item");
		const company = $el.data("company");
		if (!item_code || !company) return;

		const $pop = $(`
			<div id="th-warehouse-popover" style="
				position:fixed;z-index:9999;
				background:var(--fg-color);border:1px solid var(--border-color);border-radius:6px;
				box-shadow:0 4px 16px rgba(0,0,0,.18);padding:10px 14px;min-width:240px;max-width:340px;
				font-size:12px;pointer-events:none
			">
				<div style="font-weight:600;margin-bottom:8px;color:var(--text-muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em">${__("Stock by Warehouse")}</div>
				<div class="th-whpop-body" style="color:var(--text-muted)">${__("Loading…")}</div>
			</div>`).appendTo("body");

		// Position below the element
		const rect = $el[0].getBoundingClientRect();
		$pop.css({ top: rect.bottom + 6, left: Math.max(8, rect.left) });

		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_warehouse_stock",
			args: { item_code, company },
		}).then(r => {
			if (!$("#th-warehouse-popover").length) return; // already closed
			const rows = r.message || [];
			if (!rows.length) {
				$pop.find(".th-whpop-body").html(`<span>${__("No stock in any warehouse")}</span>`);
				return;
			}
			const tbody = rows.map(w => `
				<tr>
					<td style="padding:3px 0;padding-right:16px;white-space:nowrap;color:var(--text-color)">${w.warehouse_name || w.warehouse}</td>
					<td style="padding:3px 0;text-align:right;font-weight:${w.actual_qty > 0 ? "700" : "400"};color:${w.actual_qty > 0 ? "var(--green)" : "var(--text-muted)"}">${format_number(w.actual_qty, null, 2)}</td>
				</tr>`).join("");
			$pop.find(".th-whpop-body").html(`
				<table style="width:100%;border-collapse:collapse">${tbody}</table>`);
		});
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
