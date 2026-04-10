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
		this._supp_source = "pi";
		this._item_panel = {
			items: [],      // [{item_code, item_name, checked: true}]
			active_tab: null,
		};
		this._pricing_panel = {
			items: [],
			active_tab: null,
		};
		this._render();
		this._bind_tabs();
		this._render_item_checklist();
		this._render_pricing_checklist();
	}

	// ── Layout ────────────────────────────────────────────────────────────────

	_inject_styles() {
		if (document.getElementById("th-responsive-styles")) return;
		const style = document.createElement("style");
		style.id = "th-responsive-styles";
		style.textContent = `
			@media (max-width: 767px) {
				.item-body { flex-direction: column !important; }
				.item-panel-sidebar {
					width: 100% !important;
					min-width: 0 !important;
					margin-right: 0 !important;
					margin-bottom: 12px;
				}
				.item-results-grid { grid-template-columns: 1fr !important; }
			}
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
					</div>
					<div class="item-body" style="display:flex;gap:0;align-items:flex-start">
						<div class="item-panel-sidebar" style="width:224px;min-width:224px;border:1px solid var(--border-color);border-radius:6px;padding:10px;margin-right:14px;flex-shrink:0;position:relative;z-index:1">
							<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
								<span class="item-panel-label" style="font-weight:600;font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em">${__("Items")}</span>
								<button class="btn btn-xs btn-default btn-toggle-item-panel" title="${__("Toggle panel")}" style="padding:1px 6px">☰</button>
							</div>
							<div class="item-panel-body">
								<div class="ctrl-item-group" style="margin-bottom:6px"></div>
								<div class="ctrl-item-add" style="margin-bottom:8px"></div>
								<div class="item-checklist" style="max-height:45vh;overflow-y:auto;margin-bottom:8px;border-top:1px solid var(--border-color);padding-top:6px"></div>
								<div style="display:flex;gap:4px">
									<button class="btn btn-primary btn-sm btn-run-items" style="flex:1" disabled>${__("Run (0)")}</button>
									<button class="btn btn-default btn-sm btn-clear-items" title="${__("Clear all")}" style="padding:4px 8px">✕</button>
								</div>
							</div>
						</div>
						<div class="item-results" style="flex:1;min-width:0">
							<div class="item-tabs-strip"></div>
							<div class="th-content item-content"></div>
						</div>
					</div>
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

				<div class="th-panel hidden" data-panel="receivables">
					<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px">
						<div class="ctrl-recv-company" style="min-width:180px"></div>
						<div class="ctrl-recv-as-of" style="min-width:140px"></div>
						<div class="ctrl-recv-customer" style="min-width:220px"></div>
						<button class="btn btn-primary btn-sm btn-get-receivables">${__("Get")}</button>
					</div>
					<div class="th-content receivables-content"></div>
				</div>

				<div class="th-panel hidden" data-panel="payables">
					<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px">
						<div class="ctrl-pay-company" style="min-width:180px"></div>
						<div class="ctrl-pay-as-of" style="min-width:140px"></div>
						<div class="ctrl-pay-supplier" style="min-width:220px"></div>
						<button class="btn btn-primary btn-sm btn-get-payables">${__("Get")}</button>
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
						<div class="pricing-panel-sidebar" style="width:224px;min-width:224px;border:1px solid var(--border-color);border-radius:6px;padding:10px;margin-right:14px;flex-shrink:0">
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

		// Item tab
		this.controls.item_company = make(".ctrl-item-company", {
			fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company"), reqd: 1,
		});
		this.controls.item_from = make(".ctrl-item-from", { fieldtype: "Date", fieldname: "from_date", label: __("From Date") });
		this.controls.item_to = make(".ctrl-item-to", { fieldtype: "Date", fieldname: "to_date", label: __("To Date") });
		this.controls.item_warehouse = make(".ctrl-item-warehouse", {
			fieldtype: "Link", options: "Warehouse", fieldname: "warehouse", label: __("Warehouse"),
		});
		if (default_company) this.controls.item_company.set_value(default_company);

		// Item panel — group filter
		this.controls.item_group = make(".ctrl-item-group", {
			fieldtype: "Link", options: "Item Group", fieldname: "item_group", label: __("Item Group"),
		});

		// Item panel — search-and-add (get_query filters by selected group, if any)
		this.controls.item_add = make(".ctrl-item-add", {
			fieldtype: "Link", options: "Item", fieldname: "item_add", label: __("Add Item"),
		});
		this.controls.item_add.get_query = () => {
			const group = this.controls.item_group ? this.controls.item_group.get_value() : null;
			return {
				query: "cecypo_frappe_reports.cecypo_frappe_reports.api.item_query",
				filters: group ? { item_group: group } : {},
			};
		};

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

	// ── Item Checklist ────────────────────────────────────────────────────────

	_render_item_checklist() {
		const m = this.page.main;
		const $list = $(m).find(".item-checklist");
		const items = this._item_panel.items;

		if (!items.length) {
			$list.html(`<span class="text-muted" style="font-size:12px">${__("No items added yet")}</span>`);
		} else {
			$list.html(items.map((item, i) => `
				<div class="item-check-row" style="display:flex;align-items:center;padding:3px 0;border-bottom:1px solid var(--border-color)">
					<label style="display:flex;align-items:center;gap:5px;cursor:pointer;font-size:12px;flex:1;min-width:0;overflow:hidden">
						<input type="checkbox" class="item-checkbox" data-idx="${i}" ${item.checked ? "checked" : ""} style="flex-shrink:0">
						<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${item.item_name || item.item_code}">${item.item_name || item.item_code}</span>
					</label>
					<button class="btn-remove-item" data-idx="${i}"
						style="border:none;background:none;cursor:pointer;color:var(--text-muted);padding:0 4px;font-size:14px;line-height:1;flex-shrink:0">×</button>
				</div>
			`).join(""));
		}

		const checked = items.filter(it => it.checked).length;
		$(m).find(".btn-run-items").text(__("Run ({0})", [checked])).prop("disabled", checked === 0);
	}

	_add_item_to_panel(item_code, item_name) {
		if (this._item_panel.items.find(it => it.item_code === item_code)) return; // already present
		this._item_panel.items.push({ item_code, item_name: item_name || item_code, checked: true });
		this._render_item_checklist();
	}

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

	// ── Item History ─────────────────────────────────────────────────────────

	_run_item_history() {
		const m = this.page.main;
		const company = this.controls.item_company.get_value();
		if (!company) { frappe.msgprint(__("Company is required")); return; }

		const checked = this._item_panel.items.filter(it => it.checked);
		if (!checked.length) return;

		const from_date = this.controls.item_from.get_value() || null;
		const to_date = this.controls.item_to.get_value() || null;
		const warehouse = this.controls.item_warehouse.get_value() || null;

		// Generation counter: discard callbacks from superseded runs
		this._run_generation = (this._run_generation || 0) + 1;
		const gen = this._run_generation;

		// Disable Run button while in flight
		$(m).find(".btn-run-items").prop("disabled", true);
		let pending = checked.length;

		// Reset results
		this._item_panel.active_tab = checked[0].item_code;
		this._render_item_tabs(checked);

		// Fire parallel calls — one per checked item
		checked.forEach(item => {
			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.page.transaction_history.transaction_history.get_item_history",
				args: { item: item.item_code, company, from_date, to_date, warehouse },
				callback: (r) => {
					if (gen !== this._run_generation) return; // stale — discard
					if (r.message) {
						this._fill_item_tab(item.item_code, r.message);
					}
					if (--pending === 0) {
						// Re-enable button only when all responses have arrived
						const checked_count = this._item_panel.items.filter(it => it.checked).length;
						$(m).find(".btn-run-items").prop("disabled", checked_count === 0);
					}
				},
			});
		});
	}

	_render_item_tabs(items) {
		const m = this.page.main;
		const $strip = $(m).find(".item-tabs-strip");
		const $content = $(m).find(".item-content");

		$strip.html(`
			<div style="margin-bottom:8px">
				<ul class="nav nav-tabs" style="margin-bottom:0">
					${items.map((item, i) => `
						<li class="nav-item">
							<a class="nav-link item-tab-link ${i === 0 ? "active" : ""}"
								href="#" data-item="${item.item_code}"
								style="font-size:12px;padding:6px 12px">
								${item.item_code}
							</a>
						</li>
					`).join("")}
				</ul>
			</div>
			<div style="margin-bottom:10px">
				<input type="search" class="item-results-search form-control form-control-sm"
					placeholder="${__("Filter rows...")}" style="max-width:280px">
			</div>
		`);

		$content.html(items.map((item, i) => `
			<div class="item-tab-panel ${i === 0 ? "" : "hidden"}" data-item="${item.item_code}">
				<div class="text-muted" style="padding:20px">${__("Loading...")}</div>
			</div>
		`).join(""));
	}

	_fill_item_tab(item_code, data) {
		const m = this.page.main;
		const $panel = $(m).find(`.item-tab-panel[data-item="${item_code}"]`);
		$panel.empty();
		this._render_item_history(data, $panel);
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
		const col_style = "background:var(--card-bg);border:1px solid var(--border-color);border-radius:6px;padding:12px 16px";

		return `
			<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
				<div style="${col_style}">
					<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px">${__("Item Details")}</div>
					${row(__("Name"), d.item_name, true)}
					${row(__("Code"), d.item_code)}
					${row(__("Group"), d.item_group)}
					${row(__("Brand"), d.brand || "—")}
				</div>
				<div style="${col_style}">
					<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px">${__("Stock")}</div>
					${row(__("Current Stock"), `<span style="color:${stock_color};font-weight:700">${format_number(m.current_stock, null, 2)} ${d.stock_uom || ""}</span>`)}
					${row(__("Stock Value"), format_currency(m.stock_value, bc), true)}
					${row(__("Avg. Rate"), format_currency(m.avg_rate, bc))}
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

		const empty_row = `<tr><td colspan="8" style="padding:12px;text-align:center" class="text-muted">${is_purchase ? __("No purchases found") : __("No sales found")}</td></tr>`;

		const body = rows.length ? rows.map((r, i) => `
			<tr style="${i % 2 ? "background:var(--control-bg)" : ""}">
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${frappe.datetime.str_to_user(r.date)}</td>
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/${is_purchase ? (r.doctype === "Purchase Receipt" ? "purchase-receipt" : "purchase-invoice") : "sales-invoice"}/${r.voucher_no}">${r.voucher_no}</a></td>
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r[party_key] || ""}</td>
				<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.qty, null, 2)}</td>
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.uom || ""}</td>
				<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.rate, r.currency)}</td>
				<td style="padding:4px 8px;text-align:right;font-weight:600;border-bottom:1px solid var(--border-color)">${format_currency(r[rate_key], bc)}</td>
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${this._status_pill(r.status)}</td>
			</tr>`).join("") : empty_row;

		$(`
			<div style="border:1px solid var(--border-color);border-radius:6px;overflow:hidden">
				<div class="item-section-header" style="background:var(--subtle-fg);padding:8px 12px;font-weight:600;display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid ${accent};cursor:pointer;user-select:none">
					<span style="color:${accent}">${label}</span>
					<div style="display:flex;align-items:center;gap:8px">
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
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)"><a href="/app/${doctype_slug}/${r.voucher_no}">${r.voucher_no}</a></td>
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r[party_key] || ""}</td>
				<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r.ordered_qty, null, 2)}</td>
				<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_number(r[received_key], null, 2)}</td>
				<td style="padding:4px 8px;text-align:right;font-weight:600;border-bottom:1px solid var(--border-color)">${format_number(r.pending_qty, null, 2)}</td>
				<td style="padding:4px 8px;border-bottom:1px solid var(--border-color)">${r.uom || ""}</td>
				<td style="padding:4px 8px;text-align:right;border-bottom:1px solid var(--border-color)">${format_currency(r.rate, r.currency)}</td>
			</tr>`).join("") : empty_row;

		$(`
			<div style="border:1px solid var(--border-color);border-radius:6px;overflow:hidden">
				<div class="item-section-header" style="background:var(--subtle-fg);padding:8px 12px;font-weight:600;display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid ${accent};cursor:pointer;user-select:none">
					<span style="color:${accent}">${label}</span>
					<div style="display:flex;align-items:center;gap:8px">
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
					placeholder="${__("Filter rows...")}" style="max-width:280px">
			</div>
			<div style="overflow-x:auto">
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
			</table>
			</div>`;
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

		$(m).on("click", ".btn-get-customer", () => this._load_customer_history());
		$(m).on("click", ".btn-get-supplier", () => this._load_supplier_history());

		$(m).on("click", ".btn-run-items", () => this._run_item_history());

		// Item tab switching
		$(m).on("click", ".item-tab-link", (e) => {
			e.preventDefault();
			const item_code = $(e.currentTarget).data("item");
			$(m).find(".item-tab-link").removeClass("active");
			$(e.currentTarget).addClass("active");
			$(m).find(".item-tab-panel").addClass("hidden");
			$(m).find(`.item-tab-panel[data-item="${item_code}"]`).removeClass("hidden");
			this._item_panel.active_tab = item_code;
		});

		// Item results search filter
		$(m).on("input", ".item-results-search", (e) => {
			const val = $(e.currentTarget).val().toLowerCase();
			const $active = $(m).find(".item-tab-panel:not(.hidden)");
			$active.find("tbody tr").each(function () {
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
					$(this).find("td:first").text("▶");
				}
			});
			// Clear any detail row filters when search is cleared
			if (!val) {
				$table.find(".detail-content tbody tr").removeClass("hidden");
			}
		});

		// Item panel toggle (collapse/expand sidebar)
		$(m).on("click", ".btn-toggle-item-panel", () => {
			const $sidebar = $(m).find(".item-panel-sidebar");
			const collapsed = $sidebar.hasClass("item-panel-collapsed");
			if (collapsed) {
				$sidebar.removeClass("item-panel-collapsed").css({ width: "224px", "min-width": "224px", padding: "10px", overflow: "" });
				$sidebar.find(".item-panel-body").show();
				$sidebar.find(".item-panel-label").show();
			} else {
				$sidebar.addClass("item-panel-collapsed").css({ width: "36px", "min-width": "36px", padding: "4px 2px", overflow: "hidden" });
				$sidebar.find(".item-panel-body").hide();
				$sidebar.find(".item-panel-label").hide();
			}
		});

		// Item checklist — checkbox toggle
		$(m).on("change", ".item-checkbox", (e) => {
			const idx = parseInt($(e.currentTarget).data("idx"), 10);
			this._item_panel.items[idx].checked = e.currentTarget.checked;
			const checked = this._item_panel.items.filter(it => it.checked).length;
			$(m).find(".btn-run-items").text(__("Run ({0})", [checked])).prop("disabled", checked === 0);
		});

		// Item checklist — remove item
		$(m).on("click", ".btn-remove-item", (e) => {
			e.stopPropagation();
			const idx = parseInt($(e.currentTarget).data("idx"), 10);
			if (idx < 0 || idx >= this._item_panel.items.length) return;
			this._item_panel.items.splice(idx, 1);
			this._render_item_checklist();
		});

		// Item checklist — clear all
		$(m).on("click", ".btn-clear-items", () => {
			this._item_panel.items = [];
			this._render_item_checklist();
			$(m).find(".item-tabs-strip, .item-content").empty();
		});

		// Item group filter — load items in group when selected
		$(m).on("awesomplete-select", ".ctrl-item-group input", () => {
			setTimeout(() => {
				const group = this.controls.item_group ? this.controls.item_group.get_value() : null;
				if (!group) return;
				frappe.db.get_list("Item", {
					filters: { item_group: group, disabled: 0 },
					fields: ["name", "item_name"],
					limit: 500,
				}).then(items => {
					items.forEach(it => this._add_item_to_panel(it.name, it.item_name));
				});
			}, 50);
		});

		// Item search-and-add — on select
		$(m).on("awesomplete-select", ".ctrl-item-add input", (e) => {
			// Value is set asynchronously; wait one tick
			setTimeout(() => {
				const val = this.controls.item_add ? this.controls.item_add.get_value() : null;
				if (!val) return;
				// Get item_name for display
				frappe.db.get_value("Item", val, "item_name").then(r => {
					this._add_item_to_panel(val, r.message ? r.message.item_name : val);
					this.controls.item_add.set_value("");
				});
			}, 50);
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
			</table>
			</div>`;
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
