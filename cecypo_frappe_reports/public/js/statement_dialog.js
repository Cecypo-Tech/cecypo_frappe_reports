// Copyright (c) 2026, Cecypo and contributors
// For license information, please see license.txt

// One dialog serving every surface that focuses on a single party: the Accounts Receivable and
// Accounts Receivable Summary query reports, and the Transaction History page's Receivables and
// Payables tabs.
//
// Callers that can also produce a plain transaction list (Transaction History) pass a
// `transaction_list` adapter; callers that cannot (the query reports) pass nothing, and the
// Document selector simply does not render. That seam is what keeps this dialog free of any
// knowledge about which surface opened it.

(() => {
	"use strict";

	frappe.provide("cecypo_reports.statement");

	const METHOD = "cecypo_frappe_reports.cecypo_frappe_reports.statement_of_accounts.";
	// Statement templates are Process Statement Of Accounts records, so that is the natural
	// doctype to hang the per-user "which template did I last use" memory off.
	const SETTINGS_DOCTYPE = "Process Statement Of Accounts";
	const LAST_TEMPLATE_KEY = "cecypo_last_statement_template";
	const PREVIEW_DEBOUNCE_MS = 400;

	const DOC_STATEMENT = "statement";
	const DOC_TRANSACTION_LIST = "transaction_list";

	// The one PSOA report whose period is a window (from_date..to_date) rather than an as-on date.
	const GL_REPORT = "General Ledger";

	class StatementDialog {
		/**
		 * @param {object}   opts
		 * @param {string}   opts.company            required
		 * @param {string}  [opts.party]             prefilled and locked when known
		 * @param {string}  [opts.party_type]        "customer" (default) or "supplier"
		 * @param {string}  [opts.as_of_date]
		 * @param {object}  [opts.transaction_list]  {label, get_html(ctx), download(html, ctx),
		 *                                            send(html, ctx, {recipient, cc, bcc})}
		 */
		constructor(opts) {
			this.opts = opts || {};
			this.party_type = this.opts.party_type || "customer";
			this.transaction_list = this.opts.transaction_list || null;
			this.templates = [];
			// Preview renders are async and debounced, so a slow early response can land after a
			// fast later one. Every render carries a sequence number and stale ones are dropped.
			this.seq = 0;
			this.cc_shown = false;
		}

		// Process Statement Of Accounts is customer-only, so the Payables tab gets the same dialog
		// with the statement half absent rather than a different dialog.
		get supports_statement() {
			return this.party_type === "customer";
		}

		get party_doctype() {
			return this.party_type === "customer" ? "Customer" : "Supplier";
		}

		async show() {
			if (!this.opts.company) {
				frappe.msgprint(__("Company is required"));
				return;
			}

			const [templates, last_template, recipient] = await Promise.all([
				this._fetch_templates(),
				this._fetch_last_template(),
				this._fetch_recipient(),
			]);
			this.templates = templates;
			// Record who that recipient belongs to, so applying the party field's default during
			// Dialog construction is recognised as a no-op rather than refetching it.
			this._recipient_for = this.opts.party || null;

			const default_doc_type =
				this.supports_statement && this.templates.length ? DOC_STATEMENT : DOC_TRANSACTION_LIST;

			this.dialog = new frappe.ui.Dialog({
				title: __("Statement — {0}", [this.opts.party || this.opts.company]),
				size: "extra-large",
				fields: this._build_fields(default_doc_type, last_template, recipient),
				primary_action_label: __("Download"),
				primary_action: () => this._download(),
				secondary_action_label: __("Email"),
				secondary_action: () => this._email(),
			});

			this.dialog.show();
			this._sync_fields();
			this._refresh_preview();
		}

		// ── Fields ───────────────────────────────────────────────────────────

		_build_fields(default_doc_type, last_template, recipient) {
			const on_input_change = () => {
				this._sync_fields();
				this._refresh_preview();
			};

			const fields = [];

			// Only meaningful when there is a genuine choice to make.
			if (this.transaction_list && this.supports_statement) {
				fields.push({
					fieldname: "document_type",
					fieldtype: "Select",
					label: __("Document"),
					options: [
						{ label: this.transaction_list.label || __("Transaction list"), value: DOC_TRANSACTION_LIST },
						{ label: __("Statement of Accounts"), value: DOC_STATEMENT },
					],
					default: default_doc_type,
					onchange: on_input_change,
				});
			}

			fields.push({
				fieldname: "party",
				fieldtype: "Link",
				options: this.party_doctype,
				label: __(this.party_doctype),
				default: this.opts.party || "",
				reqd: 1,
				// On the query reports the party filter is a MultiSelectList that may hold zero or
				// many values, so the dialog lets the user name the one they want. When the caller
				// already knows (a Transaction History row), it is locked to avoid a silent switch.
				read_only: this.opts.party ? 1 : 0,
				onchange: () => {
					// Frappe fires onchange when it applies the field's default, before the user has
					// touched anything. Without this the recipient is fetched twice and the preview
					// is rendered twice — the second render landing after the first had painted.
					const party = this.dialog && this.dialog.get_value("party");
					if (!party || party === this._recipient_for) return;
					this._recipient_for = party;

					this._fetch_recipient().then((email) => {
						this.dialog.set_value("recipient", email || "");
						on_input_change();
					});
				},
			});

			// Template comes before the dates because the template decides which dates apply.
			if (this.supports_statement) {
				fields.push({
					fieldname: "template",
					fieldtype: "Select",
					label: __("Template"),
					options: this.templates.map((t) => ({ label: t.name, value: t.name })),
					default: last_template || (this.templates[0] && this.templates[0].name) || "",
					onchange: on_input_change,
				});
				fields.push({ fieldname: "template_hint", fieldtype: "HTML" });
			}

			// as_of_date is the end of the period in every mode, relabelled by _sync_date_fields as To
			// Date (GL), Posting Date (AR) or As of (transaction list). One field rather than three is
			// what lets switching Document keep the date the user picked.
			const period_end = this.opts.as_of_date || frappe.datetime.get_today();
			fields.push({
				fieldname: "from_date",
				fieldtype: "Date",
				label: __("From Date"),
				// First day of the previous month: the whole of last month plus this month so far.
				default: moment(period_end).subtract(1, "months").startOf("month").format("YYYY-MM-DD"),
				hidden: 1,
				onchange: on_input_change,
			});
			fields.push({
				fieldname: "as_of_date",
				fieldtype: "Date",
				label: __("As of"),
				default: period_end,
				reqd: 1,
				onchange: on_input_change,
			});

			fields.push({
				fieldname: "recipient",
				fieldtype: "Data",
				options: "Email",
				label: __("To"),
				default: recipient || "",
				onchange: () => this._sync_fields(),
			});
			fields.push({ fieldname: "cc_toggle", fieldtype: "HTML" });
			fields.push({ fieldname: "cc", fieldtype: "Data", label: __("CC"), hidden: 1 });
			fields.push({ fieldname: "bcc", fieldtype: "Data", label: __("BCC"), hidden: 1 });
			fields.push({ fieldname: "preview", fieldtype: "HTML" });

			return fields;
		}

		_sync_fields() {
			// Applying field defaults during Dialog construction can fire onchange before the
			// assignment to this.dialog has completed.
			if (!this.dialog) return;

			const d = this.dialog;
			const is_statement = this._is_statement();

			if (this.supports_statement) {
				d.set_df_property("template", "hidden", is_statement ? 0 : 1);
				d.set_df_property("template", "reqd", is_statement ? 1 : 0);
				this._render_template_hint(is_statement);
			}

			this._sync_date_fields();
			this._render_cc_toggle();

			// Statement mode needs a template, and a GL statement a valid window; without either there
			// is nothing to render.
			const blocked = (is_statement && !d.get_value("template")) || Boolean(this._date_problem());
			d.get_primary_btn().prop("disabled", blocked);

			const email_btn = d.get_secondary_btn();
			const no_recipient = !(d.get_value("recipient") || "").trim();
			email_btn.prop("disabled", blocked || no_recipient);
			email_btn.attr(
				"title",
				no_recipient ? __("No email address for this {0}", [__(this.party_doctype)]) : ""
			);
		}

		_render_template_hint(is_statement) {
			const $wrap = this.dialog.fields_dict.template_hint.$wrapper;
			if (!is_statement || this.templates.length) {
				$wrap.empty();
				return;
			}
			// Statement is unavailable but the transaction list still works, so the dialog stays
			// useful rather than becoming a dead end.
			const href = frappe.utils.get_form_link(SETTINGS_DOCTYPE, "new", true, __("create one"));
			$wrap.html(
				`<div class="text-muted" style="margin:-8px 0 12px">
					${__("No statement template for {0}.", [frappe.utils.escape_html(this.opts.company)])}
					${href}
				</div>`
			);
		}

		_render_cc_toggle() {
			const $wrap = this.dialog.fields_dict.cc_toggle.$wrapper;
			if (this.cc_shown) {
				$wrap.empty();
				return;
			}
			if ($wrap.find("a").length) return;
			$wrap.html(
				`<a href="#" class="text-muted" style="font-size:var(--text-sm)">${__("+ Add CC / BCC")}</a>`
			);
			$wrap.find("a").on("click", (e) => {
				e.preventDefault();
				this.cc_shown = true;
				this.dialog.set_df_property("cc", "hidden", 0);
				this.dialog.set_df_property("bcc", "hidden", 0);
				$wrap.empty();
			});
		}

		_sync_date_fields() {
			const is_gl = this._is_gl();
			const mode = is_gl ? "gl" : this._is_statement() ? "ar" : "list";
			// set_df_property re-renders the control, so only touch it when the mode actually changes.
			if (mode === this._date_mode) return;
			this._date_mode = mode;

			const d = this.dialog;
			d.set_df_property("from_date", "hidden", is_gl ? 0 : 1);
			d.set_df_property("from_date", "reqd", is_gl ? 1 : 0);
			d.set_df_property(
				"as_of_date",
				"label",
				{ gl: __("To Date"), ar: __("Posting Date"), list: __("As of") }[mode]
			);
		}

		_is_statement() {
			if (!this.supports_statement) return false;
			if (!this.transaction_list) return true;
			return this.dialog.get_value("document_type") === DOC_STATEMENT;
		}

		_template_report() {
			const name = this.dialog.get_value("template");
			const tpl = this.templates.find((t) => t.name === name);
			return tpl ? tpl.report : null;
		}

		_is_gl() {
			return this._is_statement() && this._template_report() === GL_REPORT;
		}

		// Why the current dates cannot produce a statement, or null. Only a GL window has a start,
		// so only it can be missing one or be out of order. A missing start must block rather than
		// be sent empty: the server would quietly fall back to the template's filter_duration.
		_date_problem() {
			if (!this._is_gl()) return null;
			const from = this.dialog.get_value("from_date");
			const to = this.dialog.get_value("as_of_date");
			if (!from) return __("Select a From Date to preview.");
			if (to && from > to) return __("From Date must be on or before To Date.");
			return null;
		}

		_context() {
			return {
				party: this.dialog.get_value("party"),
				party_type: this.party_type,
				company: this.opts.company,
				as_of_date: this.dialog.get_value("as_of_date"),
				from_date: this._is_gl() ? this.dialog.get_value("from_date") : null,
				template: this.dialog.get_value("template"),
			};
		}

		// The statement's identity as the server endpoints take it. from_date is omitted unless it
		// applies, so a non-GL call is exactly what it was before the field existed.
		_statement_args(ctx) {
			const args = {
				customer: ctx.party,
				company: ctx.company,
				template: ctx.template,
				as_of_date: ctx.as_of_date,
			};
			if (ctx.from_date) args.from_date = ctx.from_date;
			return args;
		}

		// ── Preview ──────────────────────────────────────────────────────────

		_refresh_preview() {
			if (!this.dialog) return;
			clearTimeout(this._preview_timer);
			this._preview_timer = setTimeout(() => this._render_preview(), PREVIEW_DEBOUNCE_MS);
		}

		_set_preview_message(message) {
			this.dialog.fields_dict.preview.$wrapper.html(
				`<div class="text-muted" style="padding:24px;text-align:center">${message}</div>`
			);
		}

		async _render_preview() {
			const ctx = this._context();
			const mine = ++this.seq;

			if (!ctx.party) {
				this._set_preview_message(__("Select a {0} to preview.", [__(this.party_doctype)]));
				return;
			}
			if (this._is_statement() && !ctx.template) {
				this._set_preview_message(__("Select a statement template to preview."));
				return;
			}
			const date_problem = this._date_problem();
			if (date_problem) {
				this._set_preview_message(date_problem);
				return;
			}

			this._set_preview_message(__("Loading preview…"));

			let html;
			try {
				html = this._is_statement()
					? await this._fetch_statement_html(ctx)
					: await this.transaction_list.get_html(ctx);
			} catch (e) {
				if (mine !== this.seq) return;
				this._set_preview_message(__("Preview unavailable."));
				this._sync_fields();
				return;
			}

			// A slower earlier request must not overwrite a newer render.
			if (mine !== this.seq) return;

			this.dialog.fields_dict.preview.$wrapper.html(
				`<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px">${__("Preview")}</div>
				<iframe class="cecypo-statement-preview" style="width:100%;height:420px;border:1px solid var(--border-color);border-radius:4px;background:#fff"></iframe>`
			);
			this.dialog.fields_dict.preview.$wrapper.find("iframe").attr("srcdoc", html);
		}

		// ── Actions ──────────────────────────────────────────────────────────

		async _download() {
			const ctx = this._context();
			if (!ctx.party) return;

			if (!this._is_statement()) {
				// Re-derive rather than reuse the preview. Clicking inside the preview debounce
				// window would otherwise act on HTML built from the previous field values.
				this.transaction_list.download(await this.transaction_list.get_html(ctx), ctx);
				this.dialog.hide();
				return;
			}

			// The buttons are disabled in this state, but a dialog's primary action has a keyboard path.
			if (this._date_problem()) return;

			this._remember_template(ctx.template);
			// A "download" response is a file, not JSON, so it cannot go through frappe.call.
			// open_url_post posts a form (CSRF token included) and lets the browser save the result.
			open_url_post(frappe.request.url, {
				cmd: METHOD + "download_statement",
				...this._statement_args(ctx),
			});
			this.dialog.hide();
		}

		async _email() {
			const ctx = this._context();
			const recipient = (this.dialog.get_value("recipient") || "").trim();
			if (!ctx.party || !recipient) return;

			const cc = this.dialog.get_value("cc") || "";
			const bcc = this.dialog.get_value("bcc") || "";

			if (!this._is_statement()) {
				// Same reason as _download: send what the fields currently say, not what the
				// preview happens to be showing.
				const html = await this.transaction_list.get_html(ctx);
				this.transaction_list.send(html, ctx, { recipient, cc, bcc });
				this.dialog.hide();
				return;
			}

			if (this._date_problem()) return;

			this._remember_template(ctx.template);
			this.dialog.hide();
			frappe.call({
				method: METHOD + "email_statement",
				args: {
					...this._statement_args(ctx),
					recipient,
					cc,
					bcc,
				},
				// Sending is queued rather than immediate, so the alert says queued, not sent.
				callback: () =>
					frappe.show_alert({
						message: __("Statement queued to {0}", [recipient]),
						indicator: "green",
					}),
			});
		}

		// ── Data ─────────────────────────────────────────────────────────────

		_fetch_statement_html(ctx) {
			return frappe
				.xcall(METHOD + "render_statement_html", this._statement_args(ctx))
				.then((html) => html || "");
		}

		_fetch_templates() {
			if (!this.supports_statement) return Promise.resolve([]);
			return frappe
				.xcall(METHOD + "get_statement_templates", { company: this.opts.company })
				.then((r) => r || [])
				.catch(() => []);
		}

		_fetch_recipient() {
			const party = this.dialog ? this.dialog.get_value("party") : this.opts.party;
			if (!party) return Promise.resolve("");
			return frappe
				.xcall(METHOD + "get_default_recipient", { party_type: this.party_type, party })
				.catch(() => "");
		}

		_fetch_last_template() {
			if (!this.supports_statement) return Promise.resolve(null);
			return frappe.model.user_settings
				.get(SETTINGS_DOCTYPE)
				.then((s) => (s && s[LAST_TEMPLATE_KEY] && s[LAST_TEMPLATE_KEY][this.opts.company]) || null)
				.catch(() => null);
		}

		_remember_template(template) {
			if (!template) return;
			// Keyed by company so switching companies does not drag the wrong template along.
			frappe.model.user_settings.save(SETTINGS_DOCTYPE, LAST_TEMPLATE_KEY, {
				[this.opts.company]: template,
			});
		}
	}

	cecypo_reports.statement.open = function (opts) {
		return new StatementDialog(opts).show();
	};
})();
