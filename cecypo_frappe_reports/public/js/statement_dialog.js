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
			this.preview_html = null;
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
			this.auto_recipient_missing = !recipient;

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
					this._fetch_recipient().then((email) => {
						this.auto_recipient_missing = !email;
						if (email) this.dialog.set_value("recipient", email);
						on_input_change();
					});
				},
			});

			fields.push({
				fieldname: "as_of_date",
				fieldtype: "Date",
				label: __("As of"),
				default: this.opts.as_of_date || frappe.datetime.get_today(),
				reqd: 1,
				onchange: on_input_change,
			});

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
			const d = this.dialog;
			const is_statement = this._is_statement();

			if (this.supports_statement) {
				d.set_df_property("template", "hidden", is_statement ? 0 : 1);
				d.set_df_property("template", "reqd", is_statement ? 1 : 0);
				this._render_template_hint(is_statement);
			}

			this._render_cc_toggle();

			// Statement mode needs a template; without one there is nothing to render.
			const blocked = is_statement && !d.get_value("template");
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

		_is_statement() {
			if (!this.supports_statement) return false;
			if (!this.transaction_list) return true;
			return this.dialog.get_value("document_type") === DOC_STATEMENT;
		}

		_context() {
			return {
				party: this.dialog.get_value("party"),
				party_type: this.party_type,
				company: this.opts.company,
				as_of_date: this.dialog.get_value("as_of_date"),
				template: this.dialog.get_value("template"),
			};
		}

		// ── Preview ──────────────────────────────────────────────────────────

		_refresh_preview() {
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

			this._set_preview_message(__("Loading preview…"));

			let html;
			try {
				html = this._is_statement()
					? await this._fetch_statement_html(ctx)
					: await this.transaction_list.get_html(ctx);
			} catch (e) {
				if (mine !== this.seq) return;
				this._set_preview_message(__("Preview unavailable."));
				this.preview_html = null;
				this._sync_fields();
				return;
			}

			// A slower earlier request must not overwrite a newer render.
			if (mine !== this.seq) return;

			this.preview_html = html;
			this.dialog.fields_dict.preview.$wrapper.html(
				`<div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px">${__("Preview")}</div>
				<iframe class="cecypo-statement-preview" style="width:100%;height:420px;border:1px solid var(--border-color);border-radius:4px;background:#fff"></iframe>`
			);
			this.dialog.fields_dict.preview.$wrapper.find("iframe").attr("srcdoc", html);
		}

		// ── Actions ──────────────────────────────────────────────────────────

		_download() {
			const ctx = this._context();
			if (!ctx.party) return;

			if (!this._is_statement()) {
				this.transaction_list.download(this.preview_html, ctx);
				return;
			}

			this._remember_template(ctx.template);
			// A "download" response is a file, not JSON, so it cannot go through frappe.call.
			// open_url_post posts a form (CSRF token included) and lets the browser save the result.
			open_url_post(frappe.request.url, {
				cmd: METHOD + "download_statement",
				customer: ctx.party,
				company: ctx.company,
				template: ctx.template,
				as_of_date: ctx.as_of_date,
			});
			this.dialog.hide();
		}

		_email() {
			const ctx = this._context();
			const recipient = (this.dialog.get_value("recipient") || "").trim();
			if (!ctx.party || !recipient) return;

			const cc = this.dialog.get_value("cc") || "";
			const bcc = this.dialog.get_value("bcc") || "";

			if (!this._is_statement()) {
				this.transaction_list.send(this.preview_html, ctx, { recipient, cc, bcc });
				this.dialog.hide();
				return;
			}

			this._remember_template(ctx.template);
			this.dialog.hide();
			frappe.call({
				method: METHOD + "email_statement",
				args: {
					customer: ctx.party,
					company: ctx.company,
					template: ctx.template,
					as_of_date: ctx.as_of_date,
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
				.xcall(METHOD + "render_statement_html", {
					customer: ctx.party,
					company: ctx.company,
					template: ctx.template,
					as_of_date: ctx.as_of_date,
				})
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
