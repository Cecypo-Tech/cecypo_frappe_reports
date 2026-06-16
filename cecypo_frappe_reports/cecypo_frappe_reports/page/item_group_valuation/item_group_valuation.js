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

const IGV_COLUMNS = [
	{
		key: "name",
		label: __("Item Group / Item"),
		align: "left",
		type: "text",
		sortable: true,
		value: (row) => (row.is_group ? row.item_group : row.item_code),
	},
	{
		key: "qty",
		label: __("Qty"),
		align: "right",
		width: 90,
		type: "number",
		sortable: true,
		summable: true,
		value: (row) => row.qty,
	},
	{
		key: "valuation_rate",
		label: __("Avg Valuation"),
		align: "right",
		width: 135,
		type: "number",
		sortable: true,
		value: (row) => row.valuation_rate,
	},
	{
		key: "value",
		label: __("Value"),
		align: "right",
		width: 130,
		type: "number",
		sortable: true,
		summable: true,
		value: (row) => row.value,
	},
];

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

	_thead_row_html(sort_state) {
		const ST = window.cecypo_reports.sortableTable;
		return `<tr style="background:var(--subtle-fg,#f4f5f6)">
			<th style="padding:8px 12px;width:32px;border-bottom:2px solid var(--border-color)"></th>
			${ST.theadCellsHtml(IGV_COLUMNS, sort_state)}
		</tr>`;
	}

	_table_shell_html() {
		return `<div style="padding:16px;max-width:860px">
			<table style="width:100%;border-collapse:collapse;font-size:13px" id="igv-table">
				<thead>${this._thead_row_html(null)}</thead>
				<tbody id="igv-tbody">
					<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-muted)">${__("Select filters and click Refresh")}</td></tr>
				</tbody>
				<tfoot id="igv-tfoot"></tfoot>
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
		const $tfoot = $("#igv-tfoot");
		$tbody.html(`<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-muted)">${__("Loading...")}</td></tr>`);
		$tfoot.empty();

		frappe.call({
			method: "cecypo_frappe_reports.cecypo_frappe_reports.page.item_group_valuation.item_group_valuation.get_top_level_groups",
			args: { root_group, warehouse, company },
			callback: (r) => {
				const rows = r.message || [];
				if (!rows.length) {
					$tbody.html(`<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text-muted)">${__("No data found")}</td></tr>`);
					$tfoot.empty();
					return;
				}
				$tbody.empty();
				$tbody.data("rows", rows);
				$tbody.data("sort", { key: null, dir: null });
				this._render_rows(rows, $tbody, 0);
				this._render_total_row(rows, $tfoot);
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
								<thead>${this._thead_row_html(null)}</thead>
								<tbody class="igv-sub-tbody" data-for="${esc}" data-indent="${indent + 1}"></tbody>
								<tfoot class="igv-sub-tfoot"></tfoot>
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

	_render_total_row(rows, $tfoot) {
		const ST = window.cecypo_reports.sortableTable;
		const cells = ST.totalCellsHtml(IGV_COLUMNS, rows, {
			format: (v) => this._fmt_num(v),
			labelKey: "name",
			label: __("Total"),
		});
		$tfoot.html(`<tr class="cecypo-total-row"><td></td>${cells}</tr>`);
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
					const $sub_tfoot = $sub.closest("table").children("tfoot.igv-sub-tfoot");
					$sub.empty();
					if (!rows.length) {
						$sub.html(`<tr><td colspan="5" style="padding:8px ${12 + (indent + 1) * 24}px;color:var(--text-muted)">${__("No items found")}</td></tr>`);
						$sub_tfoot.empty();
					} else {
						$sub.data("rows", rows);
						$sub.data("sort", { key: null, dir: null });
						this._render_rows(rows, $sub, indent + 1);
						this._render_total_row(rows, $sub_tfoot);
					}
					$sub.data("loaded", true);
				},
			});
		});

		$(this.page.main).on("click", ".cecypo-sort-header", (e) => {
			const $th = $(e.currentTarget);
			const key = $th.data("sortKey");
			const $table = $th.closest("table");
			const $tbody = $table.children("tbody");
			const $tfoot = $table.children("tfoot");
			const rows = $tbody.data("rows");
			if (!rows) return;
			const indent = parseInt($tbody.data("indent") || 0, 10);

			const prev = $tbody.data("sort") || { key: null, dir: null };
			const dir = prev.key === key && prev.dir === "asc" ? "desc" : "asc";

			$tbody.children(".igv-group-row").each((_, el) => {
				const $row = $(el);
				const $detail = $row.next(".igv-detail-row");
				if (!$detail.hasClass("hidden")) {
					$detail.addClass("hidden");
					$row.find("td:first").text("▶");
				}
			});

			const column = IGV_COLUMNS.find((c) => c.key === key);
			const sorted = window.cecypo_reports.sortableTable.sortRows(rows, column, dir);

			$tbody.empty();
			this._render_rows(sorted, $tbody, indent);
			$tbody.data("sort", { key, dir });
			$table.children("thead").html(this._thead_row_html({ key, dir }));
			this._render_total_row(rows, $tfoot);
		});
	}
}
