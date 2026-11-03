# Copyright (c) 2026, Cecypo.Tech and contributors
# For license information, please see license.txt

"""Party statement: the site's Client Script that formats the statement copied, emailed or
drawn as an image from the party dialog on Transaction History (and PowerPack's Customer Info).

The script is deliberately not a fixture. ``sync_fixtures`` imports with ``force=True`` on
every ``bench migrate``, which would overwrite a site's edited columns and re-enable a script
the site switched off. So it is created only when missing - on install and after every
migrate, which makes deleting it the way to reset it to the shipped version - and carries no
module, so no Client Script fixture filter exports it. Same rule as PowerPack's
``copy_as_message.seed_client_scripts``.

It is attached to Customer only because a Client Script needs a DocType; desk pages fetch
its source through ``get_party_statement_script`` and run it themselves.
"""

import os

import frappe

SCRIPT_NAME = "Party Statement - Copy and Email"
SOURCE = os.path.join(os.path.dirname(__file__), "client_scripts", "party_statement.js")


def seed_client_script():
	"""Idempotent. Wired to after_install and after_migrate."""
	if frappe.db.exists("Client Script", SCRIPT_NAME):
		return
	with open(SOURCE) as f:
		script = f.read()
	frappe.get_doc(
		{
			"doctype": "Client Script",
			"name": SCRIPT_NAME,
			"dt": "Customer",
			"view": "Form",
			"enabled": 1,
			"script": script,
		}
	).insert(ignore_permissions=True, set_name=SCRIPT_NAME)


@frappe.whitelist()
def get_party_statement_script(party_type: str = "Customer") -> str | None:
	"""Source of the site's statement script, or None when it is missing or disabled.

	Gated like the party dialog's own data: read on Sales Invoice for customers,
	Purchase Invoice for suppliers.
	"""
	doctype = "Purchase Invoice" if (party_type or "").lower() == "supplier" else "Sales Invoice"
	frappe.has_permission(doctype, "read", throw=True)
	return frappe.db.get_value("Client Script", {"name": SCRIPT_NAME, "enabled": 1}, "script")
