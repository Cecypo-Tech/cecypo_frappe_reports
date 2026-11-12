# Party statement script — finish (2026-11-03)

Pushed: cecypo_frappe_reports upstream/main cc4c914..ca748ea; cecypo_powerpack upstream/main cad95da..e572b89.

Final review (fresh reviewer): 0 Critical. Fixed: refused-clipboard dead end (manual-copy dialog, both apps);
detached image download link (TH attaches; PowerPack reuses copy_as_image.download). Verified: real clipboard
round trip in Chrome (row text, dialog text, image).

Rulings: default script sorts invoices by date then number (ORDER constant) so both dialogs copy identical text;
PowerPack takes company from the snapshot payload; extra long-queue worker started for migrate, then stopped.

Deferred minors: site-script return types unchecked; 250+ invoice images exceed Safari canvas limit; row Copy
text now calls get_party_details per click (slower, adds party/company permission checks, network failure
silent); cosmetic (blank company line, supplier image wording, filename differs); Email catch hides composer errors.

Tests: cecypo_frappe_reports full suite 186 OK (1 skipped); node 8/8; PowerPack test_party_statement_script 3/3,
test_customer_snapshot 13/13. Not tested: Safari.
