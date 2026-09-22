# Feature 5 — VAT preparation and review

Open **TVA** in the company navigation. Atlas now supports monthly/quarterly internal worksheets, commercial source imports, manual lines, explicit tax review, prior credits, immutable approval snapshots and CSV/JSON downloads. This is preparation for the accountant; it does not file a return or generate a qualified DGI XML file.

## Prepare a period

1. Choose **Nouvelle préparation**, the first day of a calendar month/quarter, and an import basis independently for sales and purchases: invoices or payments. Active periods cannot overlap within a company. These are source-selection choices, not a determination of the company's legal tax regime.
2. Choose **Importer / actualiser**. Invoice mode proposes active sales and received purchases dated in the period. Payment mode proposes their payments dated in the period. Draft/cancelled invoices are excluded. Import requires neither accounting posting nor payment matching; the commercial records are the source.
3. **Vérifier** each line. Enter the tax retained for this period and a justification. Every imported line starts unreviewed with zero retained tax. Purchase tax is never automatically treated as deductible. A zero retained amount is an explicit exclusion and also requires a reason.
4. Add manual lines for external documents and justified amounts absent from Atlas. Enter direction, recognition date, document reference, counterparty, net amount, source tax, retained tax and reason. The date must fall inside the worksheet period. Retained tax cannot exceed source tax; amounts have at most two decimals.
5. Under **Crédit & notes**, enter any verified prior credit and its origin. No automatic carryforward is applied. Totals show reviewed sales tax, reviewed deductible purchase tax, estimated payable tax and estimated remaining credit. Pending lines are excluded, and the screen identifies the calculation as partial.
6. Choose **Approuver la préparation** after checking the scope, treatment, amounts and credit. Approval requires all lines reviewed, no changed/deleted sources, and no missing source candidates. To exclude a current source, import it and retain zero with a reason.

An empty period can be approved only when it has no source candidates and the reviewer explicitly confirms its scope. No fiscal identifier format or completeness is certified by internal approval.

## Payment allocation

All amounts are integer centimes. For a payment, proposed tax is:

`round(invoice_tax × cumulative_paid / invoice_total) − round(invoice_tax × previously_paid / invoice_total)`

Rounding uses half-up at the centime. Payments are ordered by their source date and ID. Proposed net equals payment amount minus allocated tax. Full settlement therefore recovers the invoice's exact tax amount without accumulating rounding differences across periods. Supplier dates are entered payment dates; customer dates use the recorded timestamp in Africa/Casablanca.

This proportional allocation is a review aid. Mixed-rate invoices, advances, withholdings, cash-payment restrictions, prorata and eligibility exceptions may require different treatment. Atlas does not decide those rules. Imported source amounts are preserved; retained tax is explicitly entered by the accountant. Rate-level statutory schedules are not generated.

## Source changes and duplicate protection

Imports are repeatable without duplicate rows. Reimporting a changed source replaces its proposal and resets review/retained tax. Disappeared sources remain flagged until explicitly removed. Removing a current source does not bypass review: it will be listed as missing and must be reimported before approval.

At approval, sourced tax already retained in other active approved worksheets is checked by source event and original invoice. A source event cannot be counted twice, and the total retained for one invoice cannot exceed its source tax, including when different import bases were chosen in different periods. Zero-retained rows do not consume source tax. Manual lines do not have a provable source identity; the accountant must check them for duplicates and completeness.

Writes serialize under the existing company lock. Version checks reject stale edits. Every mutation requires `request_key`; identical retries acknowledge the original operation, while changed content under the same key is rejected. Approval and line decisions are recorded in company activity history.

## Approval, correction and export

Approval captures company identity, period, import bases, complete lines and source snapshots, totals, notes, reviewer and timestamp. The snapshot has a SHA-256 checksum over canonical JSON: sorted keys, ASCII escaping and compact separators. CSV and JSON exports use the stored approved snapshot, not recalculated current company/commercial data.

Approved worksheets cannot be edited or deleted. **Annuler l’approbation** records actor, time and reason, retaining the original snapshot. A fresh worksheet can then cover the period. Drafts can be abandoned with a reason. PostgreSQL guards enforce history immutability, approval metadata, reviewed lines and period overlap/calendar rules. Direct database access still requires operational access controls; tax eligibility is enforced by the human review workflow, not certified by the database.

Voided/discarded records remain visible. Exports are available only for active approved worksheets; company JSON backups include all history. Recheck any later manually carried credits after correcting an earlier worksheet. No filing, cancellation or amendment is sent to the DGI by these actions.

- **Exporter CSV**: period/company header, all reviewed lines (including zero-retained exclusions), justifications, totals and checksum. Spreadsheet formula prefixes in text are escaped.
- **Télécharger l’instantané**: approved internal JSON snapshot and SHA-256. This is not DGI XML.
- Company data exports are version **5**, adding `vat.worksheets` with preparation and approval history. They remain data exports, not an implemented restore format or a substitute for PostgreSQL backups.

## Permissions and API

Administrators/accountants prepare and approve. Supervisors read/export. Read-only users read. Commercial users have no VAT access. Every API request checks membership and company scope. VAT data is absent from the commercial state endpoint. The legacy importer refuses companies that already contain VAT history.

Paths are relative to `/api/companies/<company_id>/`. Writes require CSRF and `request_key`.

| Path | Input |
| --- | --- |
| POST `vat-create` | `start`, `cadence`: monthly/quarterly, `sales_basis` and `purchase_basis`: invoices/payments |
| POST `vat-import` | Worksheet `id`, `version` |
| POST `vat-line` | `id`, `version`, optional line `key`, `retained_tax` in DH, `reason`; manual rows also require direction sale/purchase, date, reference, party, net and tax |
| POST `vat-remove` | `id`, `version`, line `key`, reason |
| POST `vat-settings` | `id`, `version`, opening_credit in DH, credit_note, optional note |
| POST `vat-approve` | `id`, `version`, `confirmed: true` |
| POST `vat-void` | `id`, `version`, reason; abandons a draft or voids an approval |
| GET `vat/state` | Company worksheets, totals, source diagnostics and approval history |
| GET `vat/export` | Approved worksheet `id`, format csv/json |

## Validation and upgrade

Migrations **0010–0011** add VAT worksheets and PostgreSQL guards. Existing company, commercial and accounting records are retained. Back up PostgreSQL before upgrading; `manage.py migrate` or `sh start-atlas.sh` applies the migrations.

`workspace.test_vat` covers imports, review and credit arithmetic, partial-payment centime allocation across periods, duplicates, changed/missing/cancelled sources, calendar periods, stale requests, manual input validation, company/role access, exports, immutable approvals, historical voiding and concurrent requests. `tests/vat-browser.cjs` covers the complete review-to-export workflow plus mobile/read-only access.

Current limits: no XML qualification/submission, automatic legal regime selection, automatic tax-rate or recoverability determination, rate-level statutory schedules, automatic prior-credit links, withholding/refund/credit-note processing, attachments or bulk manual-file import. Up to 2,000 lines per worksheet; datasets currently load per company without pagination.

See [Moroccan declaration research](MOROCCAN-DECLARATIONS.md) for the official target and schema qualification still required.
