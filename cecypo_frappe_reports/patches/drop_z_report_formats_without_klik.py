import frappe


def execute():
	"""The Z Report print formats moved to klik_pos with their jinja methods. Without klik_pos the
	formats left behind in the DB would fail on render, so delete them; with it, klik's migrate
	takes them over."""
	if "klik_pos" in frappe.get_installed_apps():
		return
	for name in ("Z Report", "Z Report ESC/POS"):
		if frappe.db.get_value("Print Format", name, "module") == "Cecypo Frappe Reports":
			frappe.delete_doc("Print Format", name, force=True, ignore_permissions=True)
