# Debug: Transaction History missing from desk search (dev.localhost)

## Symptom
Search (Ctrl+K) shows "Open Transaction History" for Administrator but not for kushal@cecypo.tech.
Direct URL /app/transaction-history works.

## Root cause
- erpnext_express `_apply_express_page_permissions` created Custom Role `ouufibf8ha` for page
  `transaction-history` with only Express Admin/Sales/Stocks/Purchase.
- Its docstring assumes page Custom Roles are additive. True for `Page.is_permitted()` (direct URL),
  false for `DeskViews._build_user_pages_or_reports` (boot `page_info` -> search/sidebar): a page that
  has a Custom Role is matched ONLY on the Custom Role's roles (`parentTable.name.notin(subq)`).
- kushal@cecypo.tech has Sales/Stock/Accounts/Purchase roles but no Express role -> page dropped from boot.
- Same applies to `z-report`.

## Proposed fix (erpnext_express, express_settings.py)
In `_apply_express_page_permissions`, include the page's standard Has Role roles in the Custom Role
(`final = (current - express_roles) | wanted | standard_roles`), so both code paths see the union.
after_migrate already re-applies, so existing sites heal on next migrate; run
`reapply_permissions` + clear cache on dev now. Regression test in erpnext_express tests.

## Outcome
- Fixed in erpnext_express (merge 9562b9e, pushed to upstream/main):
  - _apply_express_page_permissions seeds standard page roles into the Custom Role
  - ensure_report_presets (after_migrate) re-applies page permissions
  - uninstall deletes a page Custom Role left with exactly the standard roles
- Tests: erpnext_express.overrides.test_lockdown on test.localhost, 159 run, OK
  (2 new regression tests were red before the fix).
- dev.localhost: reapply_permissions + clear-cache; kushal@cecypo.tech now sees
  "Open Transaction History" in Ctrl+K search (browser verified). z-report healed too.
