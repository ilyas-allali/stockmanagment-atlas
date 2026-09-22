# Atlas — commercial and accounting suite

Moving PCs or continuing in a new chat? Read [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md) for the feature summary, database restore steps and exact continuation state.

**Features 1–5 implemented:** user accounts, isolated companies, company-specific roles, stock/sales, suppliers/purchases, and reviewed accounting on PostgreSQL. The French interface now includes invoice-to-accounting transfer, posting, payment transfer and matching, reversals, journal, ledger and trial balance.

## Start the new app

First copy `.env.example` to `.env` and set `POSTGRES_PASSWORD` plus the matching `DATABASE_URL` as described in the template. When restoring an existing installation, transfer its private `.env` instead. Database credentials are never committed.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
docker compose -p atlas-foundation up -d db
.venv/bin/python manage.py migrate
.venv/bin/python manage.py setup_atlas
.venv/bin/python manage.py runserver 127.0.0.1:8001
```

Open **http://localhost:8001**. Setup asks you to choose the administrator's credentials. After setup, `sh start-atlas.sh` (or `start-atlas.bat` on Windows) starts the app and opens the browser. On Windows use `.venv\Scripts\python` for the Python commands above.

For a fresh local demonstration, use `manage.py demo_atlas` instead of `setup_atlas`. It creates two companies and writes generated credentials to the private local file `data/demo-login.json`. There is no fixed default password. The demo command refuses an already configured database.

## Available now

- Login/logout, password changes, session invalidation, CSRF and login throttling.
- Company creation and switching; separate customers, products, stock, sales, payments and exports.
- Organization administrators manage users and company memberships.
- Company administrator, commercial, accountant, supervisor and read-only roles.
- Existing sales, stock movements, partial payments, unpaid-sale cancellation, CSV and printable internal sales documents.
- Supplier contact records, fiscal identifiers and balances.
- Purchase drafts with editable lines, supplier invoice references, invoice/due dates and per-line tax rates.
- Confirmed receipts increase stock once; received invoices become immutable.
- Partial/full supplier payments, overdue balances, unpaid purchase cancellation with stock reversal.
- Purchase CSV exports and printable internal copies; purchasing data included in company JSON exports.
- Company accounts, journals and nonoverlapping accounting periods.
- Manual accounting drafts and automatic preparation from sales/purchase invoice amounts, with selected accounts and explicit posting review.
- Immutable posted entries, linked reversals, period close/reopen controls, journal/ledger/trial-balance reports and CSV exports.
- Customer/supplier payment transfer, partial/full invoice matching, audited unmatching and a reconciliation CSV.
- VAT worksheets with invoice/payment imports, manual review, prior credits, locked approval snapshots and internal CSV/JSON exports.
- Company activity journal and JSON data export.
- An explicit, read-only import from the old prototype's SQLite database into an empty company.

Read [Feature 1: setup, permissions, migration and limitations](docs/FOUNDATION.md) for details. PostgreSQL relationship constraints prevent commercial records from linking across companies; application authorization scopes all requests. Row-level security, automated operational backups and production hosting are still pending. The local Docker credentials are for development only.

Read [Feature 2: suppliers and purchase invoices](docs/PURCHASES.md) for the workflow, permissions and current limits. To upgrade an existing local installation, stop the app, back up PostgreSQL, run `.venv/bin/python manage.py migrate`, restart with `sh start-atlas.sh`, and refresh the browser. The migrations retain existing accounts and commercial data.

Read [Feature 3: accounting and invoice transfer](docs/ACCOUNTING.md) before configuring accounts and periods. The chart and transfer mappings are supplied by the company's accountant. Year-end closing/carryforward and statutory declarations remain pending; the reports include posted entries only.

Read [Feature 4: payment transfer and invoice matching](docs/SETTLEMENTS.md) for the new **Règlements & lettrage** screen, correction workflow and payment-gap reporting.

Read [Feature 5: VAT preparation and review](docs/VAT.md) for monthly/quarterly worksheets and the reviewed export workflow. Official XML filing remains pending.

## Next features

Next: financial statements (Bilan/CPC), followed by Liasse mappings and qualified XML adapters. Services, fractional quantities, multiple warehouses and additional commercial documents are still pending.

- [Full client scope and acceptance roadmap](docs/CLIENT-SCOPE.md)
- [Moroccan declaration research](docs/MOROCCAN-DECLARATIONS.md)
- [Original executable analysis](analysis/README.md)

The original executable files and SQLite prototype data are untouched. The legacy app is still available with `python3 server.py`; see [archived prototype instructions](docs/PROTOTYPE.md). It has no authentication and is for local comparison only.

## Verification

```sh
.venv/bin/python manage.py test workspace --noinput
python3 -m unittest discover -s tests -v
```

Browser checks use Playwright and temporary PostgreSQL data:

```sh
PLAYWRIGHT_MODULE=/path/to/node_modules/playwright node tests/platform-browser.cjs
PLAYWRIGHT_MODULE=/path/to/node_modules/playwright node tests/purchases-browser.cjs
PLAYWRIGHT_MODULE=/path/to/node_modules/playwright node tests/accounting-browser.cjs
PLAYWRIGHT_MODULE=/path/to/node_modules/playwright node tests/settlements-browser.cjs
PLAYWRIGHT_MODULE=/path/to/node_modules/playwright node tests/vat-browser.cjs
```

Set `ATLAS_CHROME` if using an existing Chromium binary. The scripts generate screenshots under `test-results/`. The Django suite must run against PostgreSQL to exercise the database isolation and concurrent-sale checks.
