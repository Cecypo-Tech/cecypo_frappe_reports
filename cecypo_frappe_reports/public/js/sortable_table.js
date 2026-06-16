// Shared sortable-table helpers for cecypo_frappe_reports custom pages.
// Generic and data-shape-agnostic: callers supply column defs with their
// own value(row) accessors, so this module never assumes field names.
//
// Column shape: { key, label, align, width, type: "text"|"number",
//                  sortable, summable, value(row) }

window.cecypo_reports = window.cecypo_reports || {};

window.cecypo_reports.sortableTable = (function () {
	let style_injected = false;

	function inject_style_once() {
		if (style_injected) return;
		style_injected = true;
		$("<style>")
			.text(
				".cecypo-sort-header { cursor: pointer; user-select: none; }\n" +
					".cecypo-sort-header .sort-indicator { color: var(--text-muted); margin-left: 4px; font-size: 11px; }\n" +
					".cecypo-total-row td { background: var(--subtle-accent, #eef6fb); font-weight: 600; border-top: 2px solid var(--border-color); border-bottom: 2px solid var(--border-color); padding: 8px 12px; }"
			)
			.appendTo("head");
	}

	function sort_icon(dir) {
		if (dir === "asc") return '<span class="sort-indicator">↑</span>';
		if (dir === "desc") return '<span class="sort-indicator">↓</span>';
		return '<span class="sort-indicator">↕</span>';
	}

	function thead_cells_html(columns, sort_state) {
		inject_style_once();
		return columns
			.map((col) => {
				const align = col.align || "left";
				const width_style = col.width ? `width:${col.width}px;` : "";
				const base_style = `padding:8px 12px;${width_style}text-align:${align};border-bottom:2px solid var(--border-color)`;
				if (!col.sortable) {
					return `<th style="${base_style}">${col.label}</th>`;
				}
				const active = sort_state && sort_state.key === col.key;
				const dir = active ? sort_state.dir : null;
				return `<th class="cecypo-sort-header" data-sort-key="${col.key}" style="${base_style}">${col.label}${sort_icon(dir)}</th>`;
			})
			.join("");
	}

	function column_value(col, row) {
		return typeof col.value === "function" ? col.value(row) : row[col.key];
	}

	function sort_rows(rows, column, dir) {
		const sorted = rows.slice();
		const mul = dir === "desc" ? -1 : 1;
		sorted.sort((a, b) => {
			const av = column_value(column, a);
			const bv = column_value(column, b);
			if (column.type === "number") {
				return ((av || 0) - (bv || 0)) * mul;
			}
			return String(av || "").localeCompare(String(bv || "")) * mul;
		});
		return sorted;
	}

	function total_cells_html(columns, rows, opts) {
		inject_style_once();
		opts = opts || {};
		const format = opts.format || ((v) => v);
		return columns
			.map((col) => {
				const align = col.align || "left";
				if (opts.labelKey && col.key === opts.labelKey) {
					return `<td style="text-align:${align}">${opts.label || ""}</td>`;
				}
				if (!col.summable) {
					return `<td style="text-align:${align}">—</td>`;
				}
				const total = rows.reduce((sum, row) => sum + (Number(column_value(col, row)) || 0), 0);
				return `<td style="text-align:${align}">${format(total, col)}</td>`;
			})
			.join("");
	}

	return {
		sortIcon: sort_icon,
		theadCellsHtml: thead_cells_html,
		sortRows: sort_rows,
		totalCellsHtml: total_cells_html,
	};
})();
