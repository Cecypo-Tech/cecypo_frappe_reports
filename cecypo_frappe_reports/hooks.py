app_name = "cecypo_frappe_reports"
app_title = "Cecypo Frappe Reports"
app_publisher = "Cecypo.Tech"
app_description = "Custom reports pack"
app_email = "support@cecypo.tech"
app_license = "agpl-3.0"

fixtures = [
	{
		"dt": "Print Format",
		"filters": [["name", "in", ["PSOA GL Statement", "PSOA AR Statement"]]],
	}
]

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "cecypo_frappe_reports",
# 		"logo": "/assets/cecypo_frappe_reports/logo.png",
# 		"title": "Cecypo Reports",
# 		"route": "/cecypo_frappe_reports",
# 		"has_permission": "cecypo_frappe_reports.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = "/assets/cecypo_frappe_reports/css/cecypo_frappe_reports.css"
# app_include_js = "/assets/cecypo_frappe_reports/js/cecypo_frappe_reports.js"

# include js, css files in header of web template
# web_include_css = "/assets/cecypo_frappe_reports/css/cecypo_frappe_reports.css"
# web_include_js = "/assets/cecypo_frappe_reports/js/cecypo_frappe_reports.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "cecypo_frappe_reports/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "cecypo_frappe_reports/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "cecypo_frappe_reports.utils.jinja_methods",
# 	"filters": "cecypo_frappe_reports.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "cecypo_frappe_reports.install.before_install"
# after_install = "cecypo_frappe_reports.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "cecypo_frappe_reports.uninstall.before_uninstall"
# after_uninstall = "cecypo_frappe_reports.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "cecypo_frappe_reports.utils.before_app_install"
# after_app_install = "cecypo_frappe_reports.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "cecypo_frappe_reports.utils.before_app_uninstall"
# after_app_uninstall = "cecypo_frappe_reports.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "cecypo_frappe_reports.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"cecypo_frappe_reports.tasks.all"
# 	],
# 	"daily": [
# 		"cecypo_frappe_reports.tasks.daily"
# 	],
# 	"hourly": [
# 		"cecypo_frappe_reports.tasks.hourly"
# 	],
# 	"weekly": [
# 		"cecypo_frappe_reports.tasks.weekly"
# 	],
# 	"monthly": [
# 		"cecypo_frappe_reports.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "cecypo_frappe_reports.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "cecypo_frappe_reports.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "cecypo_frappe_reports.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["cecypo_frappe_reports.utils.before_request"]
# after_request = ["cecypo_frappe_reports.utils.after_request"]

# Job Events
# ----------
# before_job = ["cecypo_frappe_reports.utils.before_job"]
# after_job = ["cecypo_frappe_reports.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"cecypo_frappe_reports.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

