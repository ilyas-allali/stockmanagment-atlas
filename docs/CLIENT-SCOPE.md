# Atlas — client scope and delivery baseline

Recorded: 19 September 2026. Declaration-target research added 20 September 2026.

Status: requirements and proposed implementation plan. This document describes the target product, not functionality already delivered. It supersedes the earlier stock-and-sales-only target; the existing prototype remains available for demonstration.

## Implementation update — feature 1

Accounts, company creation/switching, company-scoped roles and commercial data, audit history, and a prototype importer have now been implemented on Django/PostgreSQL. See [the delivered feature](FOUNDATION.md). The gap table below records the baseline before this work; accounting, declarations, operational backups and production rollout are still pending.

## Product objective

A French-language web application for commercial management, accounting, VAT preparation and financial statements across multiple companies. Authorized users work on a central system from several workstations and remote locations. A desktop-style installable experience may be added without maintaining a second accounting engine.

The supplied legacy executables are Atlascom, Atlascompta, TVA, Liasse and Transfert. Their presence and the static analysis identify the reference suite, but its business rules and database structures have not been recovered. Functional equivalence is the target; an exact visual clone is not required by the user's earlier instructions.

## Feature 2 implementation update

Supplier records, purchase drafts, full stock receipts, supplier payments, due dates, unpaid cancellations and purchase exports are now implemented with company isolation and role checks. See [Feature 2](PURCHASES.md). Services, partial receipts, accounting transfer and the broader commercial-document scope remain pending.

## Feature 3 implementation update

Company accounts/journals/periods, manual drafts, reviewed invoice transfer, posting, reversals, period locks, journal/ledger/trial balance and CSV reports are implemented. See [Feature 3](ACCOUNTING.md). Recurring mapping templates, annual closing/carryforward, VAT, statements and declaration XML remain pending. The scope table below remains the original baseline.

## Feature 4 implementation update

Customer/supplier payment transfer, reviewed posting, partial/full invoice matching, audited unmatching, linked reversal/correction rules and reconciliation CSV are implemented. See [Feature 4](SETTLEMENTS.md). This is invoice/payment matching; bank statement reconciliation, recognition of existing manual payment entries, VAT, financial statements and qualified XML remain pending.

## Feature 5 implementation update

VAT worksheets now support monthly/quarterly periods, invoice/payment candidate imports, manual entries, reviewed retained tax, prior credits, immutable approval snapshots and internal CSV/JSON exports. See [Feature 5](VAT.md). Tax eligibility remains a reviewed decision; qualified XML, portal submission, financial statements and advanced tax treatments remain pending. The table below is the original project baseline.

## Gap against the current application

| Area | Current implementation | Required target |
| --- | --- | --- |
| Companies | One company profile per manually selected SQLite file | Company creation, switcher, scoped membership, isolated records and configurable company entitlement |
| Workstations and remote access | Loopback-only HTTP server, no login | Central authenticated application over HTTPS with concurrent access |
| Customers and suppliers | Customers only | Company-specific customer and supplier records, balances and history |
| Catalog | Physical products with whole-unit quantities | Products and services, stock applicability, units and agreed quantity precision |
| Stock | Initial stock, receipts, withdrawals, sale deductions | Auditable receipts/issues, approved adjustments, returns, and an agreed warehouse/valuation policy |
| Sales | Internal sale records and printable sales documents | Draft/validated sales invoices, numbering, taxes, supporting documents and credit handling |
| Purchases | No supplier invoicing | Supplier purchase invoices, due dates, receipts, supplier payments and accounting transfer |
| Payments | Sale payments only | Customer and supplier payment allocation, partial settlement, credits/refunds and traceability |
| Accounting | None | Chart of accounts, fiscal years, journals, balanced entries, posting, reversal, period locks and reports |
| Transfer | None | Invoice-to-accounting generation with accountant review and duplicate prevention |
| VAT | One manually entered sale tax rate | Source invoice details, tax categorization, period preparation, manual adjustments and approval |
| Financial statements | None | Trial balance, general ledger, journals, mapped Bilan/CPC and agreed additional schedules |
| XML | None | Separate, versioned accounting exchange and declaration adapters with import/export validation |
| Reports | CSV catalog export; browser printing | Scoped PDF/XLSX reports and validated XML outputs |
| Backups | Manual SQLite download | Scheduled encrypted backups, retention, recovery targets and demonstrated restoration |
| Audit and roles | Stock history; no authenticated actors | Company-scoped permissions and audit of financial changes, approvals and exports |

Existing UI patterns and workflow tests can be reused selectively. The current `server.py`, global `/api/state` response and SQLite schema are prototype infrastructure, not the multi-company production foundation.

## Target architecture

Proposed approach: a modular Django application backed by central PostgreSQL, retaining the current visual direction. Modules share one accounting model and explicit transactional services. Background jobs handle long imports, report generation and scheduled work. Documents and exports live in private storage and are retrieved through permission checks.

Django is a proposed framework choice because its documented authentication/permission facilities and transaction support fit these needs. Company-specific authorization still requires application design and tests; global framework permissions alone are insufficient. References: [Django authentication](https://docs.djangoproject.com/en/5.2/topics/auth/default/) and [database transactions](https://docs.djangoproject.com/en/5.2/topics/db/transactions/).

All online workstations use the same central records. Mutations use transactions, row locking where needed, conflict detection for edited drafts and stable retry identifiers. Clients refresh or receive notifications of committed changes; separate copies of the accounting database are not synchronized between workstations.

An installable web interface is proposed for desktop convenience. Offline transaction entry is unresolved and is not assumed: if needed, it requires a separately specified queue, conflict rules, identity handling and stock/numbering reconciliation. Installability alone does not provide those behaviors.

### Organization and company isolation

- An organization is the license/customer boundary; each organization owns companies. Users receive explicit company memberships and permissions.
- Every company-owned business record carries its company identity. Accounts, customers, suppliers, invoices, warehouses, stock movements, entries, declarations, reports and attachments belong to that company.
- The server authenticates the user and verifies company membership for every request. A browser-selected company ID never establishes permission by itself.
- Database constraints prevent relations between different companies. Uniqueness is scoped appropriately, such as a product SKU within a company and a document number within its company/series/year.
- Queries, exports, file downloads, background jobs, caches and audit records all preserve this boundary.
- PostgreSQL row-level security is proposed as an additional safeguard. The runtime connection must not use superuser or bypass privileges; ownership and connection-pool context require explicit configuration and testing. PostgreSQL documents the policy behavior and bypass cases in [Row Security Policies](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).
- Company entitlement is checked on the server. The licensed limit, whether archived companies count, and administrator override rules remain to be agreed. No arbitrary cap is imposed as a client requirement.

### Proposed role defaults

| Role | Proposed responsibilities |
| --- | --- |
| Organization administrator | Company setup, memberships, entitlements and settings; business-data access explicitly assigned |
| Commercial user | Customers/suppliers, catalog, draft documents, stock operations and commercial payments within assigned permissions |
| Accountant | Account mapping, entry review/posting, expenses, reconciliation, VAT preparation, statements and exports |
| Supervisor | Agreed validation/reversal permissions, reports and oversight in assigned companies |
| Read-only user | Authorized company screens and reports; exports granted separately |

Validation, posting, period reopening, refunds and declaration approval are separate permissions. The client must decide whether the preparer may also approve their own work.

## Commercial workflows

Customers and suppliers retain company-specific identity, contact, payment and account-mapping information. A counterparty can have both roles without sharing its records with another company.

Catalog items distinguish goods from services. Services do not generate stock movements. Unit precision, warehouses and inventory costing are explicit settings/policies to agree; the prototype's whole-unit restriction is not automatically carried forward.

Sales and purchase invoices have draft and validated states. Validation snapshots the parties, lines, tax treatment, amounts and relevant numbering information. Changes to a product or contact must not rewrite historical documents. Financial values use decimal arithmetic with an agreed rounding policy.

Documents retain their own lifecycle and references: quotations, orders, delivery notes, receipts, invoices, credit notes and returns are distinct concepts. The exact subset is open. If delivery notes/receipts drive stock movement, subsequently invoicing those documents must not move the same stock again.

Payments are separate records allocated against invoices. Track unapplied amounts, partial allocations, due amounts and reversals. A paid invoice is corrected through an approved credit/refund workflow rather than deletion.

## Invoice-to-accounting transfer

Proposed default: automatic preparation of entries after commercial validation, followed by accountant review and explicit posting. This supports the client's transfer requirement while leaving full unattended posting as an unresolved option.

1. Validate the invoice and its required commercial data.
2. Resolve configured accounts and tax mappings for the company and fiscal period.
3. Generate a draft accounting batch linked to the source invoice/version. Missing mappings produce actionable errors; they are not silently replaced with guessed accounts.
4. The accountant reviews source details, account allocations and the generated entry.
5. Posting verifies that the entry balances, the period is open, required accounts are valid and the user has authority. All related updates commit together.
6. Repeating a transfer or retrying a failed network request cannot generate a second batch for the same source event.
7. Reports derive from posted lines. A posted entry is immutable; corrections use linked reversal/adjustment entries under the agreed period rules.

Commercial validation, accounting posting, payment settlement and declaration approval are separate statuses. A commercial payment and its accounting entry must also be linked to prevent manual/imported duplicates.

### Core accounting records

Company, fiscal year, period, account, journal, posting rule, entry, entry line, source-document link, transfer batch, payment allocation, reconciliation and audit event.

Opening balances and direct expenses/manual entries use the same balancing and posting rules. Draft imports are reviewed before they affect reports. Accounts and statement mappings must be supplied or validated by the client's accountant; this scope does not invent a Moroccan chart, tax rates or statutory report formulas.

Required reports include journal, general ledger and trial balance with consistent company/period filters, opening balances, period movements and closing balances. Each amount must be traceable to posted lines and source documents.

## VAT preparation

VAT records may originate from invoices or manual preparation. Preserve their source, period, tax category, bases, amounts and supporting details. Manual entries/adjustments require a reason and must be distinguishable from imported information.

The preparer reviews sales/purchase tax details, eligibility, adjustments and carryforwards under the company's agreed regime. Recoverability, timing and payable amounts cannot be inferred merely from an invoice's tax percentage.

Proposed declaration lifecycle: draft, reviewed, approved, exported; submission and acceptance are recorded separately if the client wants that tracking. A source change invalidates affected draft reviews. An approved version is retained as an immutable snapshot; corrections create a revision. Prevent accidental inclusion of the same source item twice in the same applicable declaration/version.

Manual review is part of the requested workflow. No XML is presented as an accepted official declaration solely because it was generated successfully.

## Financial statements / Liasse

Use posted accounting balances and staged, validated external accounting imports. Prevent re-importing already transferred invoices as new entries. Store source batch identifiers and show a reconciliation preview before committing an import.

Bilan, CPC and additional schedules use explicit, versioned account-to-report mappings. Report versions retain the fiscal period, source balances, mappings, adjustments and reviewer identity. Unmapped accounts and unreconciled totals must be visible and resolved before approval. Prior-year comparisons and opening balances require agreed source data.

PDF/XLSX outputs must reconcile to the same report snapshot as any declaration export. The exact list of schedules and the applicable presentation/reporting regime remain open; a generic balance sheet is not automatically the client's complete Liasse.

## XML integration contract

Treat these as separate integrations:

| Integration | Purpose | Evidence required before compatibility is claimed |
| --- | --- | --- |
| Accounting exchange | Transfer/import entries, accounts, journals and balances with external software | Recipient application/version, field mapping, supported operations, sample files and reconciliation rules |
| VAT declaration | Produce the specified VAT submission or annex | Named platform, exact declaration/annex, schema/version, code lists and accepted examples |
| Financial statement declaration | Produce the specified Liasse/Bilan/CPC package | Platform, reporting regime, required schedules, schemas/versions and accepted examples |

The user asked us to research the Moroccan targets. Official ministry/DGI sources establish SIMPL-TVA and SIMPL-IS as the proposed initial destinations for this brief, subject to each company's tax regime. Current official schema/annex versions remain unverified because the live tax portal refused automated access. See [Moroccan declaration research](MOROCCAN-DECLARATIONS.md) for the evidence, distinctions between export types and qualification criteria. No particular current DGI schema/version or compatibility is asserted here.

For each adapter, obtain the specification/XSD where available, encoding/namespaces, naming/archive conventions, precision rules, mandatory identifiers, examples and rejection messages. Validate both schema and business rules, then test against an authorized target environment or the client's documented import procedure.

Imports use bounded parsers with external entity resolution disabled, staged validation and duplicate detection. Exports retain company, period, template/schema version, approval, checksum and validation results. Changing an approved snapshot requires regeneration as a new version.

Generic internal XML may be useful for application interchange, but must be labelled separately from platform-compatible declaration XML. Automatic submission to a government platform is not included by the client's request for file exports.

## Proposed delivery sequence and acceptance

These are implementation milestones, not price or delivery-date commitments. Phase 1 alone is not the requested finished suite.

| Milestone | Deliverable | Acceptance evidence |
| --- | --- | --- |
| 1. Shared foundation | PostgreSQL migrations, login/logout, company switcher, scoped roles, fiscal setup, audit, deployed staging and backups | Two companies and separate users; unauthorized cross-company reads/writes/downloads rejected; concurrent sessions; backup restoration demonstrated |
| 2. Commercial | Customers/suppliers, goods/services, agreed invoices/documents, stock and payments | Complete sale and purchase cycles; stock moved exactly once; service lines do not change stock; concurrent numbering and payments remain consistent |
| 3. Accounting | Accounts, opening balances, manual expenses, invoice transfer, review/posting, reversal, period controls, journal/ledger/trial balance | Repeated transfer creates one batch; unbalanced/cross-company/closed-period entries rejected; report totals reconcile to source lines |
| 4. VAT and statements | VAT worksheet/review, import staging, Bilan/CPC and agreed schedules | Accountant-approved sample periods; traceable manual adjustments; statement totals and mappings reconciled |
| 5. Exchange and declarations | Named XML adapters, PDF/XLSX outputs and export history | Applicable schema/business checks pass; target import acceptance demonstrated; exported amounts match approved reports |
| 6. Rollout | Agreed historical migration, production hosting, recovery procedures and operator guidance | Migration reconciliation, permission review, representative concurrent workload, restore drill and client end-to-end acceptance |

Obtain XML/accounting samples during milestone 1; do not wait until milestone 5 to discover the required data fields. Security, permission tests, backups and reconciliation are built through the milestones.

The first implementation slice should demonstrate two isolated companies and users completing an authorized login/company-switch/logout cycle on PostgreSQL. The first business slice should then carry a validated invoice through one reviewed accounting posting and a reconciled journal/trial-balance report.

## Decisions still needed

| Topic | Open decision | Work affected |
| --- | --- | --- |
| XML contracts | Proposed targets: SIMPL-TVA and SIMPL-IS; establish company applicability, declaration types, current official schemas/annexes and accepted/rejected samples | Official integrations and their acceptance criteria |
| Accounting policy | Chart, regimes, fiscal periods, posting mappings, review versus unattended posting | Automated accounting and statements |
| Commercial documents | Exact types, conversion flow, invoice fields, tax presentation and numbering conventions | Document model and compliant output templates |
| Scale | Initial/max companies, licensed cap, users and simultaneous sessions, expected data volume | Entitlements, hosting, load targets and operational costs |
| Inventory | Branches/warehouses, quantity precision, valuation, stock-event timing and negative-stock policy | Stock model and accounting mapping |
| Connectivity | Online-only versus offline entry; hosting/access constraints | Deployment and any synchronization design |
| Migration | Which companies/years, source databases/exports, master data versus history | Importers, reconciliation and rollout |
| Additional modules | Payroll, fixed assets/depreciation, bank imports/reconciliation depth and other schedules | Scope and pricing additions |
| Operations | Backup retention, acceptable data loss/recovery time, support and update responsibilities | Production service agreement |

Payroll and fixed assets/depreciation are unconfirmed additions. Historical migration is also unconfirmed. Their omission from the initial implementation must not be interpreted as the client rejecting them.

## Estimation boundary

A final fixed price needs agreed modules/documents, scale, migration scope, accounting acceptance examples and named XML interfaces. Commercial management, core accounting and each declaration adapter should be separately identifiable in the estimate, along with hosting, backups and ongoing support. Unknown schema compatibility must not be included as an unconditional promise.

## This revision changed

- Captured the expanded client scope and compared it against the repository.
- Proposed architecture, records, permissions, workflow controls and measurable milestones.
- Recorded unresolved policy and interface contracts without inventing them.
- Did not migrate databases, alter application behavior or implement the suite described above.
