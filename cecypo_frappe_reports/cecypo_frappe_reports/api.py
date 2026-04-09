import frappe


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def item_query(doctype, txt, searchfield, start, page_len, filters, as_dict=False):
	"""Enhanced item search for use in reports and pages.

	- Multi-word: split txt on whitespace; all tokens must match (AND logic)
	- Wildcard: if % is present, each token is used as-is in LIKE
	- Barcode: each token also checked against tabItem Barcode
	"""
	import json as _json

	from frappe import scrub
	from frappe.desk.reportview import get_filters_cond, get_match_cond
	from frappe.utils import nowdate

	doctype = "Item"
	conditions = []

	if isinstance(filters, str):
		filters = _json.loads(filters)

	# Party Specific Item restrictions
	if filters and isinstance(filters, dict):
		if filters.get("customer") or filters.get("supplier"):
			party = filters.get("customer") or filters.get("supplier")
			item_rules_list = frappe.get_all(
				"Party Specific Item",
				filters={
					"party": ["!=", party],
					"party_type": "Customer" if filters.get("customer") else "Supplier",
				},
				fields=["restrict_based_on", "based_on_value"],
			)

			filters_dict = {}
			for rule in item_rules_list:
				if rule["restrict_based_on"] == "Item":
					rule["restrict_based_on"] = "name"
				filters_dict[rule.restrict_based_on] = []

			for rule in item_rules_list:
				filters_dict[rule.restrict_based_on].append(rule.based_on_value)

			for f in filters_dict:
				filters[scrub(f)] = ["not in", filters_dict[f]]

			if filters.get("customer"):
				del filters["customer"]
			else:
				del filters["supplier"]
		else:
			filters.pop("customer", None)
			filters.pop("supplier", None)

	# Build SELECT columns
	meta = frappe.get_meta(doctype, cached=True)
	searchfields = meta.get_search_fields()
	extra_searchfields = [f for f in searchfields if f not in ["name", "description"]]

	columns = ""
	if extra_searchfields:
		columns += ", " + ", ".join(extra_searchfields)

	if "description" in searchfields:
		columns += (
			""", if(length(tabItem.description) > 40, """
			"""concat(substr(tabItem.description, 1, 40), "..."), description) as description"""
		)

	# Columns to search across
	search_cols = list(
		dict.fromkeys(
			[searchfield or "name", "item_code", "item_name", "item_group"]
			+ [f for f in searchfields if f not in ["name", "description"]]
		)
	)

	# Parse tokens
	txt = (txt or "").strip()
	if not txt:
		tokens = ["%"]
	elif "%" in txt:
		tokens = [txt]  # wildcard mode: use as-is
	else:
		tokens = txt.split() or [txt]  # multi-word mode

	values = {
		"today": nowdate(),
		"start": start,
		"page_len": page_len,
		"_txt": txt.replace("%", ""),
	}

	token_clauses = []
	for i, token in enumerate(tokens):
		key = f"tok{i}"
		if "%" in token:
			val = token
			if not val.startswith("%"):
				val = "%" + val
			if not val.endswith("%"):
				val = val + "%"
			values[key] = val
		else:
			values[key] = f"%{token}%"
		col_parts = [f"tabItem.{col} LIKE %({key})s" for col in search_cols]
		col_parts.append(
			f"tabItem.item_code IN (select parent from `tabItem Barcode` where barcode LIKE %({key})s)"
		)
		token_clauses.append("(" + " or ".join(col_parts) + ")")

	search_cond = " and ".join(token_clauses)

	return frappe.db.sql(
		"""select tabItem.name {columns}
		from tabItem
		where tabItem.docstatus < 2
			and tabItem.disabled=0
			and tabItem.has_variants=0
			and (tabItem.end_of_life > %(today)s or ifnull(tabItem.end_of_life, '0000-00-00')='0000-00-00')
			and ({scond})
			{fcond} {mcond}
		order by
			if(locate(%(_txt)s, name), locate(%(_txt)s, name), 99999),
			if(locate(%(_txt)s, item_name), locate(%(_txt)s, item_name), 99999),
			idx desc,
			name, item_name
		limit %(start)s, %(page_len)s""".format(
			columns=columns,
			scond=search_cond,
			fcond=get_filters_cond(doctype, filters, conditions).replace("%", "%%"),
			mcond=get_match_cond(doctype).replace("%", "%%"),
		),
		values,
		as_dict=as_dict,
	)
