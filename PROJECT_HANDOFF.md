# Atlas — chat summary and project handoff

Updated: **22 September 2026**. Read this file first when continuing on another PC or in a new AI chat.

## 1. What the user wants

Build a modern, easier-to-use replacement for the client's old accounting/commercial software. The initial app selected was **Atlascom — stock and sales**. The reference suite also includes Atlascompta, TVA, Liasse and Transfert.

The user explicitly authorized implementation feature by feature and said an exact clone is unnecessary: build something better with equivalent useful functionality. Preserve existing data and keep moving without repeatedly asking permission for routine implementation work.

The overall product is a French-language, Moroccan commercial/accounting suite with:

- Multiple companies with isolated customers, suppliers, stock, invoices, accounting and tax records.
- Multiple users/workstations, roles and eventual secure remote access.
- Sales, purchasing, inventory, commercial documents and payments.
- Invoice/payment transfer into accounting without entering the same information twice.
- Journals, ledger, trial balance, financial statements, Bilan/CPC and Liasse.
- VAT preparation with manual review before exporting declarations.
- XML import/export compatible with the relevant Moroccan declaration systems.

The user does not know the declaration schema/platform details and asked us to research them. DGI/SIMPL-TVA and SIMPL-IS are proposed targets; accepted XML formats still require qualification.

The original executables were inspected statically and retained. Their complete business rules/database formats have **not** been reverse engineered. The implementation is a new application, not a patched legacy executable.

## 2. Current implementation

**Features 1–5 are implemented.** The local PostgreSQL database has been upgraded through migration **0011**. The next proposed feature is **financial statements: Bilan/CPC**, followed by Liasse mappings and qualified XML adapters.

| Feature | Implemented behavior | Detailed documentation |
| --- | --- | --- |
| 1. Foundation, companies and commercial operations | Login/logout, password changes, CSRF, login throttling, organization/company access, roles, company limits, products, customers, stock, sales, partial/full customer payments, unpaid-sale cancellation, CSV, internal print documents, audit and legacy SQLite import | [FOUNDATION.md](docs/FOUNDATION.md) |
| 2. Suppliers and purchasing | Supplier identities, purchase drafts, per-line tax, supplier references, invoice/due dates, full stock receipts, supplier payments, unpaid cancellation, CSV/internal print; receipt changes stock exactly once | [PURCHASES.md](docs/PURCHASES.md) |
| 3. Accounting | Company accounts/journals, nonoverlapping periods, manual drafts, reviewed sales/purchase transfers, balanced posting, immutable posted entries, reversal drafts, period close/reopen, journal, general ledger, trial balance and CSV | [ACCOUNTING.md](docs/ACCOUNTING.md) |
| 4. Payment transfer and matching | Customer/supplier payment accounting drafts, invoice-derived counterparty accounts, bank/cash selection, reviewed posting, partial/full invoice matching, audited unmatching, reversal/correction dependencies, duplicate prevention, reconciliation summaries and CSV | [SETTLEMENTS.md](docs/SETTLEMENTS.md) |
| 5. VAT preparation | Monthly/quarterly worksheets, invoice/payment import bases, proportional partial-payment proposals, manual lines, retained-tax review with reasons, prior credit, source-change checks, duplicate-recognition checks, immutable approvals, voiding and internal CSV/JSON snapshots | [VAT.md](docs/VAT.md) |

Feature 4 is invoice/payment matching, **not bank statement reconciliation**. Feature 5 is an internal reviewed worksheet, **not an officially filed declaration**.

### Latest VAT workflow

1. Open **TVA → Nouvelle préparation**.
2. Choose a calendar month/quarter and sales/purchase import bases.
3. Import sources. Every imported line starts unreviewed with zero retained tax.
4. Review each line and justify the retained amount, including exclusions at zero.
5. Add manual documents and a verified prior credit if needed.
6. Approve the preparation. Missing, changed or unreviewed sources block approval.
7. Download the approved internal CSV or JSON snapshot.

Snapshots preserve source details, company identity, amounts, reviewer/time and a SHA-256 checksum. Approved records cannot be edited. Voiding preserves history and permits a fresh preparation for that period.

## 3. What is still pending

The following are not delivered merely because they appeared in the client's original scope:

- Bilan/CPC and other financial statements; validated account-to-statement mappings.
- Liasse models, schedules and imports.
- Official DGI-compatible XML, schema qualification, portal submission and acceptance evidence.
- Full annual closing, opening-balance carryforward and profit appropriation.
- Automatic legal VAT regime selection, tax eligibility, withholding, prorata and advanced tax treatments.
- Automatic prior-credit links between VAT periods; current credit entry is manual and justified.
- Bank statement import/reconciliation and recognition of previously entered manual payment entries.
- Quotations, delivery notes, credit notes, refunds, purchase orders and partial receipts.
- Services, fractional quantities, multiple warehouses/branches and inventory valuation/costing.
- Payroll and fixed assets/depreciation: scope still needs agreement.
- Offline mode/PWA installation, production hosting, HTTPS rollout and automated operational backups.
- Broad historical migration from the original proprietary applications. The existing importer handles the standalone Atlas SQLite prototype only.
- Pagination/scaling beyond the current per-company datasets; VAT worksheets are capped at 2,000 lines.

Do not describe CSV/internal JSON as DGI XML. Do not invent statutory accounts or financial-statement mappings. See [Moroccan declaration research](docs/MOROCCAN-DECLARATIONS.md): public official material supports the service targets, but the current official XML/annex packages were not authenticated. The DGI portal was inaccessible to the browsing tool. The archived 2010 SIMPL-IS specification is historical evidence, not a current export contract.

## 4. Technical architecture and important rules

- Backend: **Django 5.2.17**, Python, **psycopg 3.3.6**, PostgreSQL 16. Exact dependencies are in [requirements.txt](requirements.txt).
- Frontend: vanilla HTML/CSS/JavaScript in `web/`, French interface, amounts displayed in MAD/DH.
- Money is stored as integer **centimes**. Commercial stock quantities currently use integers.
- Each record is scoped to a company. Membership and capabilities are checked on API requests.
- Company transaction locks serialize related commercial/accounting/VAT writes.
- Mutation request keys provide idempotency; reviewed workflows reject changed payloads under reused keys and reject stale versions.
- PostgreSQL constraints/triggers protect same-company accounting links, balanced/immutable posted entries, matching history and VAT approval history.
- No claim of PostgreSQL row-level security or production deployment readiness.
- Administrators/accountants write accounting and VAT; supervisors read/export; viewers read; commercial users manage allowed commercial operations without accounting/VAT access.
- Accounting charts/journals begin empty and are configured by the accountant.
- Reports include posted accounting entries only. Earlier accounting periods do not automatically roll into a new period.
- Company JSON exports are currently **version 5**, including accounting and VAT history. JSON export restoration is not implemented; use PostgreSQL backups for moving the database.
- `server.py` is the old, unauthenticated SQLite prototype for local comparison. The main application runs through Django `manage.py`.

### Files to read before modifying a module

| Area | Main files |
| --- | --- |
| Schema and migration history | `workspace/models.py`, `workspace/migrations/0001…0011` |
| Commercial transactions, roles, audit, request handling | `workspace/services.py` |
| Purchasing | `workspace/purchases.py`, `web/purchases.js` |
| Accounting and reports | `workspace/accounting.py`, `web/accounting.js` |
| Payment accounting/matching | `workspace/settlements.py`, `web/settlements.js` |
| VAT | `workspace/vat.py`, `web/vat.js`, `web/vat.css` |
| API/auth/export routing | `workspace/views.py`, `atlas/urls.py` |
| Shared UI and company/session handling | `web/app.js`, `web/platform.js`, `web/index.html` |
| Local startup | `start-atlas.sh`, `start-atlas.bat`, `workspace/management/commands/run_atlas.py` |
| Tests | `workspace/tests.py`, `workspace/test_*.py`, `tests/*-browser.cjs`, `tests/test_store.py` |

GitHub repository: **https://github.com/ilyas-allali/stockmanagment-atlas**. The existing workspace was connected to a clone of this initially empty repository for publishing Features 1–5 and this handoff on branch `main`. Use `git log` to inspect the published history. Private local data, credentials and database dumps are excluded from Git.

## 5. Exact state at the interruption

The last development task was Feature 5: VAT. Then the user interrupted final verification and requested this handoff for changing PCs.

Confirmed before/during handoff:

- Docker Desktop's WSL integration is working again.
- Compose project: `atlas-foundation`; service: `db`; database/user: `atlas`.
- Named database volume: `atlas-foundation_atlas_postgres`.
- PostgreSQL listens on local port **55432**, mapped to container port 5432.
- Earlier accounting/payment migrations and VAT migrations were applied to the original database.
- A migration check compared all pre-existing rows across **25 tables** and confirmed they were preserved when applying VAT migrations.
- All migrations **0001 through 0011_vat_guards** were rechecked as applied while preparing this handoff.
- The local app was started on **http://localhost:8001**, and its root page returned HTTP 200. Process continuity is not guaranteed after changing machines or ending the tool session.
- A fresh PostgreSQL backup was created specifically for the PC move; details are below.

### Verification status — do not overstate completion

Confirmed automated checks from the VAT work:

- 63 existing Django/PostgreSQL tests passed.
- 10 new VAT tests passed, plus 1 additional VAT/legacy-import guard test passed separately.
- 17 legacy Python tests passed.
- These are **91 distinct backend/Python test cases**, run in separate suites.
- Five Django browser suites passed: platform, purchases, accounting, settlements and VAT, including desktop/mobile and role/company checks.
- The VAT UI initially had a form-ID bug; fixed by reading `form.getAttribute('id')` instead of `form.id`, which can be shadowed by a hidden field named `id`.
- The legacy browser suite exposed a stock-refresh timing issue. `web/app.js` now waits for `refresh()` before closing the saved form and returning focus to `main`.
- A final rerun of `tests/browser.cjs` after that timing fix was started, but its successful result was **not captured before interruption**. Re-run it.
- The final live smoke test using `data/demo-login.json` was also interrupted; its result was **not captured**. Verify login on the new PC rather than assuming it passed.

Screenshots from the VAT checks are under `test-results/vat-review.png`, `vat-approved.png` and `vat-mobile.png` if that directory is copied. They are optional artifacts, not required to run the app.

## 6. Move to the new PC without losing data

### What to copy

Copy the entire project folder, including hidden files and the following private local files:

- The fresh database dump listed below.
- `data/demo-login.json` for the saved login details. **Do not paste the password into a public handoff/chat.**
- `data/.django-secret` and `.env`, if present.
- Original executable/reference files and any historical SQLite data you want to retain.

The database is in a Docker named volume. **Copying the source folder alone does not copy that volume or its data.** Restore the dump on the new PC.

Alternatively, clone the published project, then copy the private files above separately into the checkout:

```sh
git clone https://github.com/ilyas-allali/stockmanagment-atlas.git
cd stockmanagment-atlas
```

The GitHub checkout includes source, migrations, tests, documentation and original reference executables. It does not include `data/demo-login.json`, `.env`, `.django-secret`, PostgreSQL dumps or your Docker database volume.

`data/` and `.env` are ignored by `.gitignore`, so even if you introduce Git, copying/pushing tracked files alone will not transfer these files. Do not rely on a virtual environment copied from another OS; recreate `.venv`. `node_modules`, Python caches, temporary test databases and `/tmp` tools are not required transfer artifacts.

### Fresh move backup

- File: **`data/move-pc-20260922T191243Z.dump`**
- Format: PostgreSQL custom-format archive, created with `pg_dump -Fc`.
- Size: **164,900 bytes**.
- SHA-256: **`7d9ec07b773372070b8858f90f080205cec10a6a1db31d7b3c368f334b331e41`**.
- This captures the database at the time this handoff was prepared. Take a new backup if you make further changes before moving.

Older backups are retained for recovery, but are not the preferred move snapshot:

- `data/before-purchases-20260920T212737.dump`
- `data/before-vat-20260922T132923Z.dump`

### Recommended new-PC setup: Linux or Windows with WSL

Install Python 3.12 and Docker/Compose. On Windows, enable Docker Desktop integration for the WSL distribution. Open a terminal in the copied project directory.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
docker compose -p atlas-foundation up -d db
docker compose -p atlas-foundation exec -T db pg_isready -U atlas -d atlas
```

Wait for PostgreSQL to be ready. On a **fresh new database**, restore the dump **before running migrations, setup or demo seeding**:

```sh
docker compose -p atlas-foundation cp data/move-pc-20260922T191243Z.dump db:/tmp/atlas-move.dump
docker compose -p atlas-foundation exec -T db pg_restore --single-transaction --exit-on-error --no-owner --no-privileges -U atlas -d atlas /tmp/atlas-move.dump
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py check
sh start-atlas.sh
```

Open **http://localhost:8001** and use the saved credentials from `data/demo-login.json`. Do not run `setup_atlas` or `demo_atlas` after restoring an existing installation: the database already contains its users and companies.

The restore command intentionally has no `--clean`: if the destination already contains application tables, stop and inspect it rather than deleting data. Use a fresh destination or an explicitly planned restore process. Keep the same Compose project name so the expected volume is used.

For native Windows instead of WSL, create `.venv` with `py -m venv .venv`, use `.venv\Scripts\python.exe` for Python commands, and launch `start-atlas.bat`. The Docker `compose cp`/`pg_restore` commands above avoid binary shell-redirection problems. Transfer the private `.env` with the matching database configuration. Credentials are required and have no built-in fallback; `.env.example` contains blank values only.

## 7. Verify and resume on the new PC

First confirm login, existing companies/products/invoices, accounting history and the **TVA** navigation. Then run:

```sh
.venv/bin/python manage.py showmigrations workspace
.venv/bin/python manage.py test workspace --noinput
python3 -m unittest discover -s tests -v
```

Browser tests require Node.js, Playwright and Chromium. Install Playwright in a local tools directory and point `PLAYWRIGHT_MODULE` to its installed package; set `ATLAS_CHROME` only if using a specific Chromium executable. The previous machine used temporary paths under `/tmp/atlascom-browser` and a Chromium binary under its user's cache. Those paths are **not portable**.

Run these browser suites after configuring Playwright:

```sh
node tests/platform-browser.cjs
node tests/purchases-browser.cjs
node tests/accounting-browser.cjs
node tests/settlements-browser.cjs
node tests/vat-browser.cjs
node tests/browser.cjs
```

The Django tests use a disposable PostgreSQL test database. The Django browser fixtures create randomly named `atlas_browser_*` databases and remove them afterward; the test database role needs permission to create databases. The legacy browser test uses a temporary SQLite database.

### Suggested next development task

After closing the pending verification, implement **Feature 6: financial statements (Bilan/CPC)**. Start by reading the accounting report semantics and the Moroccan declaration research. Build explicit, reviewable company account mappings, trace each reported amount to posted ledger balances, and support internal statement review/export. Verify the applicable Moroccan statement model before presenting outputs as statutory. Do not label a ledger export as a Liasse or claim official XML acceptance without qualification.

The user prefers concrete implementation, feature by feature, with meaningful tests and progress updates. Do not restart the project, discard existing modules or rebuild the UI unnecessarily.

## 8. Message to paste into the next chat

> Read PROJECT_HANDOFF.md and the linked feature documentation in this repository. This is the existing Atlas multi-company commercial/accounting app; continue from its current code and restored PostgreSQL database. Features 1–5 are implemented, with migrations through 0011. First verify the new-PC setup and finish the interrupted legacy browser/live-login checks. Then implement Feature 6: Bilan/CPC financial statements, feature by feature. Preserve data, company isolation, reviewed posting and audit history. Official DGI XML is still unqualified; do not claim filing support. I authorize routine implementation and testing—do not restart from scratch.
