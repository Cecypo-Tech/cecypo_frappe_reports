# Copyright (c) 2026, Cecypo and contributors
# For license information, please see license.txt

import os
from urllib.parse import parse_qs, urlsplit

from frappe.tests import UnitTestCase

from cecypo_frappe_reports import hooks

ASSET_PREFIX = "/assets/cecypo_frappe_reports/"
PUBLIC_DIR = os.path.join(os.path.dirname(hooks.__file__), "public")


def _as_list(value):
	return [value] if isinstance(value, str) else list(value or [])


class TestDeskIncludesAreCacheBusted(UnitTestCase):
	"""Regression: dev.cecypo.tech sits behind Cloudflare, and Frappe only versions `.bundle.` paths.
	An unversioned include kept the edge serving the 5 Aug statement_dialog.js after the GL From/To
	change shipped, so the dialog sent no from_date and statements silently used filter_duration."""

	def test_every_desk_include_carries_its_file_mtime_as_version(self):
		includes = _as_list(hooks.app_include_js) + _as_list(hooks.app_include_css)
		self.assertTrue(includes)

		for include in includes:
			with self.subTest(include=include):
				parts = urlsplit(include)
				self.assertTrue(parts.path.startswith(ASSET_PREFIX))
				full_path = os.path.join(PUBLIC_DIR, parts.path.removeprefix(ASSET_PREFIX))
				self.assertEqual(parse_qs(parts.query).get("v"), [str(int(os.path.getmtime(full_path)))])
