// Shared "Best Fit" helper for cecypo_frappe_reports.
// Sizes each column to the wider of (header label) and (longest cell value),
// adding breathing room for sort/filter icons. The datatable's built-in
// dblclick-resize uses a character-count heuristic that under-sizes value
// columns whose header label is longer than the formatted numbers.

window.cecypo_reports = window.cecypo_reports || {};

window.cecypo_reports.bestFit = function (report) {
	const dt = report && report.datatable;
	if (!dt || !dt.header) return;

	const measurer = document.createElement("span");
	measurer.style.cssText =
		"position:absolute;visibility:hidden;white-space:nowrap;top:-9999px;left:-9999px;";

	const sample =
		(dt.bodyScrollable && dt.bodyScrollable.querySelector(".dt-cell__content")) ||
		dt.header.querySelector(".dt-cell__content");
	if (sample) {
		const cs = getComputedStyle(sample);
		measurer.style.font = cs.font;
		measurer.style.letterSpacing = cs.letterSpacing;
	}
	document.body.appendChild(measurer);

	const measure = (text) => {
		measurer.textContent = String(text == null ? "" : text);
		return measurer.offsetWidth;
	};

	const HEADER_PAD = 40; // sort caret + filter icon + buffer
	const CELL_PAD = 24;   // cell padding + buffer
	const MIN_WIDTH = 60;
	const MAX_WIDTH = 480;

	const headerCells = dt.header.querySelectorAll(".dt-cell--header");
	headerCells.forEach((headerCell) => {
		const colIdx = parseInt(headerCell.getAttribute("data-col-index"), 10);
		if (Number.isNaN(colIdx) || colIdx < 0) return;

		const headerContent = headerCell.querySelector(".dt-cell__content");
		const headerText = headerContent ? headerContent.textContent.trim() : "";
		let width = measure(headerText) + HEADER_PAD;

		const bodyCells = dt.bodyScrollable
			? dt.bodyScrollable.querySelectorAll(
					`.dt-cell[data-col-index="${colIdx}"] .dt-cell__content`
				)
			: [];
		bodyCells.forEach((cell) => {
			const w = measure(cell.textContent.trim()) + CELL_PAD;
			if (w > width) width = w;
		});

		width = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, width));
		// The DataTable instance has no setColumnWidth; the column manager does. Same steps as the
		// datatable's own resize handle: store the width, then restyle the header and the cells.
		try {
			dt.datamanager.updateColumn(colIdx, { width });
			dt.columnmanager.setColumnHeaderWidth(colIdx);
			dt.columnmanager.setColumnWidth(colIdx);
		} catch (e) {
			console.warn(`Best Fit: column ${colIdx} skipped`, e); // hidden/internal columns
		}
	});
	dt.style.refreshStickyColumns();
	dt.style.setBodyStyle();

	document.body.removeChild(measurer);
};
