# Archived stock-and-sales prototype instructions

These instructions describe `python3 server.py`, not the new multi-company app. The shared launchers now start the Django application; use the direct server command for this archived prototype. Relative paths below are from the repository root.

# Atlas — modern stock and sales

A working local replacement concept for the supplied Atlascom application, with a French interface and persistent SQLite storage. Runs in your browser, works without internet, and needs only **Python 3.10 or newer**. No application dependencies or build step.

**Expanded client requirements (19 September 2026):** the target is now a multi-company, multi-user commercial and accounting suite with VAT, financial statements and XML interfaces. See [the client scope and delivery plan](CLIENT-SCOPE.md). The runnable application described below is still the local stock-and-sales prototype; the expanded suite has not been implemented.

[Moroccan declaration research](MOROCCAN-DECLARATIONS.md) identifies DGI/SIMPL as the proposed destination, distinguishes VAT and Liasse exports, and records which official format details remain unverified.

## Start

```sh
python3 server.py --open
```

Open **http://localhost:8000**. On Windows, double-click **start-atlas.bat** (Python must be installed). On Linux/macOS, run `sh start-atlas.sh`.

The first start creates `data/atlas.sqlite3` with clearly labelled fictional demonstration data. Every edit is saved in that database; restarting does not reset it. Your original `.exe` files are untouched.

## What works

- Dashboard with revenue, stock alerts, outstanding balances, and a 7-day sales chart.
- Product creation/editing, categories, SKU search, and low-stock filters.
- Customer creation/editing and per-customer purchase/payment totals.
- Stock receipts and manual stock withdrawals with mandatory reasons and a movement journal.
- Multi-product sales, an explicitly entered tax rate, partial/full payments, and printable internal sales documents.
- Atomic stock deductions, protection against overselling and duplicate sale submissions, and cancellation/restocking of unpaid sales.
- Historical product names/prices retained on sale lines even when the catalog changes.
- CSV product import/export and downloadable consistent SQLite backups.
- Responsive screens, keyboard navigation, modal dialogs, and `/` to focus product search.

Money is stored in integer centimes and tax is rounded half-up to the nearest centime on the sale subtotal. Product quantities are whole units. Tax is zero by default and must be entered explicitly; no tax rules were recovered from the original program. Paid sales cannot be cancelled here because there is no refund workflow yet.

## Start without examples

Stop the server with Ctrl+C, then use a **new database filename**:

```sh
python3 server.py --db data/my-business.sqlite3 --empty --open
```

On Windows, substitute `py -3` for `python3`. The `--empty` flag only affects creation of a new database; it never wipes an existing database. Run the same command on subsequent starts to use the same business database.

## Import products

Use **Produits & stock → Importer** to download the template and choose a CSV file. Required columns, comma-separated:

```csv
sku,name,category,cost,price,stock,minimum
PRD-001,Mon produit,Général,50.00,80.00,10,3
```

Prices are in DH with a decimal point; quantities and alert thresholds are integers. UTF-8 and a UTF-8 BOM are supported. Import adds new products; it does not overwrite existing SKUs. An invalid row or duplicate SKU rejects the entire import without changing the database. Limit: 5,000 products and 1 MB per import. CSV exports neutralize spreadsheet formula prefixes in text fields.

## Backup and restore

Download a backup from **Paramètres → Télécharger la sauvegarde**. It includes products, customers, sales, payments, movements, and business settings. The download uses SQLite's backup API, so it is consistent even while the app is open.

To restore:

1. Stop the server (Ctrl+C).
2. Keep your current database and its adjacent files as a backup. Do not overwrite a database while the server is running.
3. Put the downloaded file at a **new path**, for example `data/restored.sqlite3`.
4. Run `python3 server.py --db data/restored.sqlite3 --open`.

## Scope of this version

This is a local, single-workstation app. The server binds only to `127.0.0.1`; it has no user accounts or remote access. It is designed for the small catalog currently available and loads the working dataset into the browser. The movement screen shows up to 1,000 recent entries; all entries stay in the database.

It is **an independent rebuild, not a successfully decompiled copy**. The supplied executable could not be unpacked by the tested decompiler. See [analysis/README.md](../analysis/README.md) for evidence, tool output, and reproducible inventory. No original data was present to migrate.

Not implemented: original FoxPro database migration, supplier purchasing, purchase orders, returns/refunds, multi-warehouse inventory, multi-user authentication, regulated invoicing, or the Atlascompta/TVA/Liasse/Transfert applications. Printed documents are explicitly labelled internal sales documents. The original software's accounting rules and integrations have not been reproduced.

## Checks

Backend tests use isolated temporary databases:

```sh
python3 -m unittest discover -s tests -v
```

Optional browser checks require Node.js and Playwright, and use a separate temporary database on port 8765:

```sh
npm install --prefix /tmp/atlas-browser playwright
/tmp/atlas-browser/node_modules/.bin/playwright install chromium
PLAYWRIGHT_MODULE=/tmp/atlas-browser/node_modules/playwright node tests/browser.cjs
```

If using an existing Chromium binary, set `ATLAS_CHROME=/path/to/chrome`. Browser screenshots are saved in `test-results/`. Browser tests exercise product/client creation, stock receipts, sales, taxes, payments, printing, cancellation, persistence, CSV import/export, backup, settings, and mobile layouts.

## Files

- `server.py`: HTTP API, database, validation, transactions, sample data.
- `web/`: self-contained browser UI; no third-party scripts, fonts, or CDNs.
- `tests/`: backend and browser workflow checks.
- `tools/inspect_legacy.py`: read-only executable inventory.
- `analysis/`: original-binary analysis and decompiler results.
- `data/`: local databases (excluded from version control).
