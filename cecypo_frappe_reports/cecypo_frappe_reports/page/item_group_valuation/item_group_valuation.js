// Copyright (c) 2026, Cecypo and contributors
// For license information, please see license.txt

frappe.pages["item-group-valuation"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Item Group Valuation"),
		single_column: true,
	});
	new ItemGroupValuationPage(wrapper);
};

class ItemGroupValuationPage {
	constructor(wrapper) {
		this.page = wrapper.page;
		this._cache = {};
		this.setup();
	}

	setup() {
		this._f_company = this.page.add_field({
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		});
		this._f_warehouse = this.page.add_field({
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
		});
		this._f_root_group = this.page.add_field({
			fieldname: "root_group",
			label: __("Root Group"),
			fieldtype: "Link",
			options: "Item Group",
			default: "All Item Groups",
		});

		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");

		$(this.page.main).html(this._table_shell_html());
		this._bind_events();
	}

	_table_shell_html() {
		return `<div style="padding:16px;max-width:860px">
			<table style="width:100%;border-collapse:collapse;font-size:13px" id="igv-table">
				<thead>
					<tr style="background:var(--subtle-fg,#f4f5f6)">
						<th style="padding:8px 12px;width:32px;border-bottom:2px solid var(--border-color)"></th>
						<th style="padding:8px 12px;text-align:left;border-bottom:2px solid var(--border-color)">${__("Item Group / Item")}</th>
						<th style="padding:8px 12px;width:90px;text-align:right;border-bottom:2px solid var(--border-color)">${__("Qty")}</th>
						<th style="padding:8px 12px;width:130px;text-align:right;border-bottom:2px solid var(--border-color)">${__("Valuation Rate")}</th>
						<th style="padding:8px 12px;width:130px;text-align:right;border-bottom:2px solid var(--border-color)">${__("Value")}</th>
					</tr>
				</thead>
				<tbody id="igv-tbody">
					<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-muted)">${__("Select filters and click Refresh")}</td></tr>
				</tbody>
			</table>
		</div>`;
	}

	refresh() {
		const company = this._f_company.get_value();
		if (!company) {
			frappe.msgprint(__("Please select a Company"));
			return;
		}
		const warehouse = this._f_warehouse.get_value() || null;
		const root_group = this._f_root_group.get_value() || "All Item Groups";

		this._cache = {};
		const $tbody = $("#igv-tbody");
		$tbody.html(`<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-muted)">${__("Loading...")}</td></tr>`);

		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.item_group_valuation.get_top_level_groups",
			args: { root_group, warehouse, company },
			callback: (r) => {
				const rows = r.message || [];
				if (!rows.length) {
					$tbody.html(`<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-muted)">${__("No data found")}</td></tr>`);
					return;
				}
				$tbody.empty();
				this._render_rows(rows, $tbody, 0);
			},
		});
	}

	_fmt_num(v) {
		return v != null ? format_number(v, null, 2) : "—";
	}

	_render_rows(rows, $tbody, indent) {
		const pad = indent * 24;
		rows.forEach((row, i) => {
			const bg = i % 2 ? "background:var(--control-bg)" : "";
			if (row.is_group) {
				const name = row.item_group;
				const esc = frappe.utils.escape_html(name);
				$tbody.append(`
				<tr class="igv-group-row" data-group="${esc}" data-indent="${indent}" style="cursor:pointer;${bg}">
					<td style="padding:6px 8px 6px ${12 + pad}px;border-bottom:1px solid var(--border-color);color:var(--text-muted)">▶</td>
					<td style="padding:6px 12px 6px ${pad || 12}px;border-bottom:1px solid var(--border-color);font-weight:500">${esc}</td>
					<td style="padding:6px 12px;text-align:right;border-bottom:1px solid var(--border-color)">${this._fmt_num(row.qty)}</td>
					<td style="padding:6px 12px;text-align:right;border-bottom:1px solid var(--border-color)">${this._fmt_num(row.valuation_rate)}</td>
					<td style="padding:6px 12px;text-align:right;border-bottom:1px solid var(--border-color);font-weight:600">${this._fmt_num(row.value)}</td>
				</tr>
				<tr class="igv-detail-row hidden" data-detail-for="${esc}">
					<td colspan="5" style="padding:0;border-bottom:1px solid var(--border-color)">
						<div style="background:var(--card-bg,#fff)">
							<table style="width:100%;border-collapse:collapse;font-size:13px">
								<tbody class="igv-sub-tbody" data-for="${esc}" data-indent="${indent + 1}"></tbody>
							</table>
						</div>
					</td>
				</tr>`);
			} else {
				const code = frappe.utils.escape_html(row.item_code);
				const item_name = row.item_name && row.item_name !== row.item_code
					? `<span style="color:var(--text-muted);margin-left:6px">${frappe.utils.escape_html(row.item_name)}</span>`
					: "";
				$tbody.append(`
				<tr style="${bg}">
					<td style="padding:6px 8px 6px ${12 + pad}px;border-bottom:1px solid var(--border-color)"></td>
					<td style="padding:6px 12px 6px ${pad || 12}px;border-bottom:1px solid var(--border-color)">
						<a href="/app/item/${code}" target="_blank">${code}</a>${item_name}
					</td>
					<td style="padding:6px 12px;text-align:right;border-bottom:1px solid var(--border-color)">${this._fmt_num(row.qty)}</td>
					<td style="padding:6px 12px;text-align:right;border-bottom:1px solid var(--border-color)">${this._fmt_num(row.valuation_rate)}</td>
					<td style="padding:6px 12px;text-align:right;border-bottom:1px solid var(--border-color);font-weight:600">${this._fmt_num(row.value)}</td>
				</tr>`);
			}
		});
	}

	_bind_events() {
		const company = () => this._f_company.get_value();
		const warehouse = () => this._f_warehouse.get_value() || null;

		$(this.page.main).on("click", ".igv-group-row", (e) => {
			const $row = $(e.currentTarget);
			const group = $row.data("group");
			const indent = parseInt($row.data("indent") || 0);
			const $detail = $row.next(".igv-detail-row");

			if (!$detail.hasClass("hidden")) {
				$detail.addClass("hidden");
				$row.find("td:first").text("▶");
				return;
			}

			$row.find("td:first").text("▼");
			$detail.removeClass("hidden");

			const $sub = $detail.find(`.igv-sub-tbody[data-for="${group}"]`);
			if ($sub.data("loaded")) return;

			$sub.html(`<tr><td colspan="5" style="padding:8px ${12 + (indent + 1) * 24}px;color:var(--text-muted)">${__("Loading...")}</td></tr>`);

			frappe.call({
				method: "cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.item_group_valuation.get_group_children",
				args: { item_group: group, warehouse: warehouse(), company: company() },
				callback: (r) => {
					const rows = r.message || [];
					$sub.empty();
					if (!rows.length) {
						$sub.html(`<tr><td colspan="5" style="padding:8px ${12 + (indent + 1) * 24}px;color:var(--text-muted)">${__("No items found")}</td></tr>`);
					} else {
						this._render_rows(rows, $sub, indent + 1);
					}
					$sub.data("loaded", true);
				},
			});
		});
	}
}
