// Party Statement - Copy and Email
// Formats the statement behind "Copy to Clipboard", "Email" and "Copy as Image" in the
// customer/supplier dialog on Transaction History, the row "Copy text" button there, and
// PowerPack's Customer Info dialog (Powerup on sales documents).
//
// This script belongs to your site. Edit it freely: Cecypo Frappe Reports created it once
// and will never overwrite it. To get the shipped version back, delete this script and
// run a migrate. Unticking Enabled switches the three buttons off (they show a message).
//
// To change the invoice table, edit COLUMNS. Each row also carries due_date and
// days_overdue, e.g. { label: "Due Date", value: (r) => date(r.due_date) }.
// The same columns are used for the copied text, the email and the image.
//
// It is attached to Customer only because a Client Script needs a DocType: on the
// Customer form it does nothing.
(() => {
	const COLUMNS = [
		{ label: "Invoice Date", value: (r) => date(r.posting_date) },
		{ label: "Invoice No.", value: (r) => r.name },
		{ label: "Total", value: (r, s) => money(r.grand_total, s), align: "right" },
		{ label: "Paid", value: (r, s) => money(r.paid, s), align: "right" },
		{ label: "Balance", value: (r, s) => money(r.outstanding_amount, s), align: "right" },
	];

	function date(d) {
		return d ? frappe.datetime.str_to_user(d) : "";
	}

	function money(v, snap) {
		return format_currency(v || 0, snap.currency);
	}

	// Oldest first, by invoice date then number. Change ORDER to sort differently.
	const ORDER = (a, b) =>
		String(a.posting_date || "").localeCompare(String(b.posting_date || "")) ||
		String(a.name || "").localeCompare(String(b.name || ""), undefined, { numeric: true });

	function cells(snap) {
		return [...(snap.invoices || [])].sort(ORDER).map((r) => COLUMNS.map((c) => String(c.value(r, snap) ?? "")));
	}

	function text_table(snap) {
		const rows = cells(snap);
		const widths = COLUMNS.map((c, i) => Math.max(c.label.length, ...rows.map((row) => row[i].length)));
		const fmt = (row) =>
			row
				.map((v, i) => (COLUMNS[i].align === "right" ? v.padStart(widths[i]) : v.padEnd(widths[i])))
				.join("  ")
				.trimEnd();
		const header = fmt(COLUMNS.map((c) => c.label));
		const rule = "-".repeat(header.length);
		return [header, rule, ...rows.map(fmt), rule];
	}

	function text(snap) {
		const supplier = snap.party_type === "Supplier";
		const pad = (s, n) => String(s ?? "").padEnd(n);
		const lines = [`Dear ${snap.party_name || snap.party},`, ""];

		if ((snap.invoices || []).length) {
			lines.push(
				supplier
					? "Our records show the following open bills on your account:"
					: "Your account currently shows the following outstanding invoices:"
			);
			lines.push(...text_table(snap));
			lines.push("Total Outstanding: " + money(snap.outstanding_total, snap));
		} else {
			lines.push(supplier ? "There are no open bills on your account." : "Your account has no outstanding invoices.");
		}

		if ((snap.advances || []).length) {
			lines.push("", "Unallocated payments on your account:");
			snap.advances.forEach((a) =>
				lines.push(pad(a.name, 22) + pad(date(a.posting_date), 14) + money(a.unallocated_amount, snap))
			);
			lines.push("Net position: " + money(snap.net_position, snap));
		}

		lines.push("");
		if (supplier) lines.push("Please let us know if your records differ.");
		else if (snap.overdue_count) lines.push("Kindly arrange for payment at your earliest convenience.");
		else lines.push("Thank you for your business.");
		return lines.join("\n");
	}

	// A PNG of the table for pasting into WhatsApp: company, party, as-of date, the
	// invoice table and the total. No greeting and no advances.
	function image(snap) {
		const SCALE = 2;
		const PAD = 24;
		const GAP = 24;
		const ROW_H = 28;
		const FONT = "13px sans-serif";
		const BOLD = "600 13px sans-serif";
		const head = [
			["700 17px sans-serif", snap.company || "", 26],
			["600 14px sans-serif", snap.party_name || snap.party || "", 22],
			[FONT, "As of " + date(snap.as_of_date), 22],
		];
		const rows = cells(snap);
		const total = "Total Outstanding: " + money(snap.outstanding_total, snap);
		const empty = "No outstanding invoices";

		const canvas = document.createElement("canvas");
		const ctx = canvas.getContext("2d");
		const measure = (font, s) => {
			ctx.font = font;
			return ctx.measureText(s).width;
		};

		const widths = COLUMNS.map((c, i) => Math.max(measure(BOLD, c.label), ...rows.map((row) => measure(FONT, row[i]))));
		const table_w = rows.length ? widths.reduce((a, b) => a + b, 0) + GAP * (COLUMNS.length + 1) : measure(FONT, empty);
		const width = Math.ceil(
			PAD * 2 + Math.max(table_w, measure(BOLD, total), ...head.map(([font, s]) => measure(font, s)))
		);
		const head_h = head.reduce((a, [, , h]) => a + h, 0);
		const table_h = rows.length ? ROW_H * (rows.length + 1) : ROW_H;
		const height = Math.ceil(PAD * 2 + head_h + 12 + table_h + 14 + ROW_H);

		// Resizing a canvas resets its context, so size it before drawing anything.
		canvas.width = width * SCALE;
		canvas.height = height * SCALE;
		ctx.scale(SCALE, SCALE);
		ctx.fillStyle = "#ffffff";
		ctx.fillRect(0, 0, width, height);
		ctx.textBaseline = "middle";
		ctx.fillStyle = "#111111";

		let y = PAD;
		for (const [font, s, h] of head) {
			ctx.font = font;
			ctx.fillText(s, PAD, y + h / 2);
			y += h;
		}
		y += 12;

		const table_x = PAD;
		const draw_row = (values, font, fill) => {
			if (fill) {
				ctx.fillStyle = fill;
				ctx.fillRect(table_x, y, table_w, ROW_H);
			}
			ctx.fillStyle = "#111111";
			ctx.font = font;
			let x = table_x + GAP;
			values.forEach((v, i) => {
				const right = COLUMNS[i].align === "right";
				ctx.textAlign = right ? "right" : "left";
				ctx.fillText(v, right ? x + widths[i] : x, y + ROW_H / 2);
				x += widths[i] + GAP;
			});
			ctx.textAlign = "left";
			y += ROW_H;
		};

		if (rows.length) {
			draw_row(COLUMNS.map((c) => c.label), BOLD, "#eef0f2");
			rows.forEach((row, i) => draw_row(row, FONT, i % 2 ? "#f8f9fa" : null));
			ctx.strokeStyle = "#d0d4d8";
			ctx.strokeRect(table_x + 0.5, y - table_h + 0.5, table_w - 1, table_h - 1);
		} else {
			ctx.font = FONT;
			ctx.fillText(empty, PAD, y + ROW_H / 2);
			y += ROW_H;
		}

		y += 14;
		ctx.font = BOLD;
		ctx.fillText(total, PAD, y + ROW_H / 2);

		return new Promise((resolve, reject) =>
			canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Could not create the image"))), "image/png")
		);
	}

	frappe.provide("cecypo");
	cecypo.party_statement = { columns: COLUMNS, text, image };
})();
