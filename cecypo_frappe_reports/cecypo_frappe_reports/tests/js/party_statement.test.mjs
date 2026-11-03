// Unit tests for client_scripts/party_statement.js, the default site script that formats
// the party statement. Run: node --test <this file>
// (test_party_statement_js.py runs it under `bench run-tests`.)
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../../../client_scripts/party_statement.js", import.meta.url), "utf8");

// Only what a desk page offers globally; no frappe.ui, so a script touching the form throws.
const sandbox = {
	frappe: {
		provide(ns) {
			let o = sandbox;
			for (const part of ns.split(".")) o = o[part] = o[part] || {};
		},
		datetime: { str_to_user: (d) => d },
	},
	__: (s, args) => (args || []).reduce((acc, a, i) => acc.replace(`{${i}}`, a), s),
	format_currency: (v, c) => `${c} ${Number(v).toFixed(2)}`,
};
vm.createContext(sandbox);
vm.runInContext(source, sandbox);
const ps = sandbox.cecypo.party_statement;

const snap = (over = {}) => ({
	party_type: "Customer",
	party: "ACME",
	party_name: "ACME Ltd",
	company: "IT Supplies",
	as_of_date: "2026-11-03",
	currency: "KES",
	invoices: [
		{ name: "SINV-0001", posting_date: "2026-10-01", due_date: "2026-10-22", days_overdue: 12, grand_total: 250, paid: 50, outstanding_amount: 200 },
		{ name: "SINV-0002", posting_date: "2026-11-01", due_date: "2026-11-22", days_overdue: 0, grand_total: 1100, paid: 1000, outstanding_amount: 100 },
	],
	outstanding_total: 300,
	overdue_count: 1,
	overdue_total: 200,
	advances: [],
	advances_total: 0,
	net_position: 300,
	...over,
});

test("registers_without_form", () => {
	assert.deepEqual(Array.from(ps.columns, (c) => c.label), ["Invoice Date", "Invoice No.", "Total", "Paid", "Balance"]);
	assert.equal(typeof ps.text, "function");
	assert.equal(typeof ps.image, "function");
});

test("customer_text", () => {
	const lines = ps.text(snap()).split("\n");
	assert.equal(lines[0], "Dear ACME Ltd,");
	const header = lines.find((l) => l.includes("Invoice Date"));
	const at = ["Invoice Date", "Invoice No.", "Total", "Paid", "Balance"].map((l) => header.indexOf(l));
	assert.deepEqual([...at].sort((a, b) => a - b), at);
	assert.ok(lines.some((l) => l.includes("SINV-0001") && l.includes("2026-10-01")));
	assert.ok(lines.includes("Total Outstanding: KES 300.00"));
	assert.equal(lines.at(-1), "Kindly arrange for payment at your earliest convenience.");
	assert.equal(ps.text(snap({ overdue_count: 0 })).split("\n").at(-1), "Thank you for your business.");
});

test("right_aligned_amounts", () => {
	const lines = ps.text(snap()).split("\n");
	const rows = lines.filter((l) => l.includes("SINV-"));
	const ends = rows.map((l) => l.indexOf(l.includes("SINV-0001") ? "KES 200.00" : "KES 100.00") + "KES 200.00".length);
	assert.equal(ends[0], ends[1]);
	assert.equal(rows[0].trimEnd().length, ends[0]);
});

test("advances_block", () => {
	const text = ps.text(snap({ advances: [{ name: "PE-1", posting_date: "2026-10-05", paid_amount: 80, unallocated_amount: 80 }], advances_total: 80, net_position: 220 }));
	assert.ok(text.includes("Unallocated payments on your account:"));
	assert.ok(text.includes("Net position: KES 220.00"));
});

test("supplier_text", () => {
	const text = ps.text(snap({ party_type: "Supplier" }));
	assert.ok(text.includes("Our records show the following open bills on your account:"));
	assert.equal(text.split("\n").at(-1), "Please let us know if your records differ.");
});

test("no_invoices", () => {
	assert.ok(ps.text(snap({ invoices: [], outstanding_total: 0, overdue_count: 0 })).includes("Your account has no outstanding invoices."));
});

test("missing_values", () => {
	const text = ps.text(snap({ invoices: [{ name: "SINV-0003", posting_date: null, due_date: null, days_overdue: 0, grand_total: null, paid: undefined, outstanding_amount: 0 }] }));
	for (const bad of ["undefined", "NaN", "null"]) assert.ok(!text.includes(bad), `text contains ${bad}`);
});

test("invoices_sorted_by_date_then_number", () => {
	// Both dialogs must copy the same text; their data arrives in different orders.
	const inv = (name, posting_date) => ({ name, posting_date, grand_total: 1, paid: 0, outstanding_amount: 1 });
	const text = ps.text(snap({ invoices: [inv("INV-9", "2026-07-20"), inv("INV-5", "2026-07-20"), inv("INV-1", "2026-07-06")] }));
	const order = text.split("\n").filter((l) => l.includes("INV-")).map((l) => l.match(/INV-\d/)[0]);
	assert.deepEqual(order, ["INV-1", "INV-5", "INV-9"]);
});
