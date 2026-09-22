# Feature 1 — accounts and isolated companies

This is the first implementation milestone of the expanded Atlas suite. The new Django application uses PostgreSQL and the existing commercial interface. The old `server.py` application remains a separate local prototype.

## Run the new application locally

Prerequisites: Python 3.10+, a virtual environment, and PostgreSQL (or Docker for the provided local database).

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
docker compose -p atlas-foundation up -d db
.venv/bin/python manage.py migrate
.venv/bin/python manage.py setup_atlas
.venv/bin/python manage.py runserver 127.0.0.1:8001
```

On Windows use `.venv\Scripts\python` in place of `.venv/bin/python`. The interactive setup asks for the first administrator's username/password, organization and company. There is no fixed administrator password and no public registration endpoint. Docker publishes PostgreSQL only on localhost, port 55432. The compose credentials are explicitly local-development credentials; do not reuse them for deployment.

Open **http://localhost:8001**. To inspect fictional sample data instead of configuring a business, run `manage.py demo_atlas` in place of `setup_atlas` on a database with no users. It generates a random password in `data/demo-login.json` (excluded from version control, local file permissions 0600). It refuses to run in production or on an already configured database.

The `.env.example` file shows connection settings. An explicit `ATLAS_SQLITE_PATH` can be used for development without PostgreSQL, but production rejects that option; the PostgreSQL-specific isolation/concurrency tests must be run against PostgreSQL.

## Delivered behavior

- Login/logout, hashed passwords, eight-hour server-side sessions, CSRF protection and login throttling.
- Password change with current-password verification; other sessions are invalidated.
- Organization administrator creates companies and ordinary users, enables/disables those users, and assigns separate roles per company.
- A company switcher shows only authorized companies. Each browser tab pins requests to an explicit company URL; changing company in another tab does not silently retarget a draft.
- New companies start empty. Company-specific settings include identity, address, phone, fiscal identifier and ICE. Configuring identifiers does not certify tax compliance.
- Existing product, customer, sale, stock, payment, CSV and print workflows use company-scoped PostgreSQL records.
- Company-specific sale numbering and SKU uniqueness. Identical SKUs and sale numbers in different companies are allowed.
- The API checks current membership on every request, including reads, writes, downloads and audit history. Revoked membership and disabled users lose access on subsequent requests.
- Application service checks and PostgreSQL composite foreign keys prevent linking commercial records across companies. A PostgreSQL trigger rejects memberships crossing organizations.
- Audit records identify the actor, company, action, timestamp and operation result; password values are not logged.
- Company JSON exports contain business data and company audit information, without authentication/session records. This is a data export, not a server backup or implemented restoration workflow.
- Optional server-controlled company limit (`Organization.company_limit`); null means no license cap. Creating companies checks the limit under an organization row lock.

For this first milestone, the organization administrator has business access to every company in their organization. Company administrators cannot create organization-wide users or companies. Organization ownership is not editable through the user-management API. Users belong to one organization in this version.

## Role defaults

| Role | Allowed |
| --- | --- |
| Organization administrator | All companies, company creation, user/access management and all company operations |
| Company administrator | All existing commercial operations, company settings, CSV/company export and audit history |
| Commercial | Catalog/customers, stock, sales, payments and product CSV export |
| Accountant | Read, payment recording and exports; accounting permissions added in Feature 3 |
| Supervisor | Commercial operations, unpaid-sale cancellation, product CSV export and audit history |
| Read-only | Company screens; no API mutations or downloadable exports |

Viewing data necessarily permits ordinary browser printing/screenshots. Download permissions are enforced on server export endpoints. Accounting permissions and the posting review workflow are documented in [Feature 3](ACCOUNTING.md).

## Import the existing prototype

Create an empty company and note its ID from the company API or URL. Then run:

```sh
.venv/bin/python manage.py import_prototype data/atlas.sqlite3 --company 1 --actor YOUR_ADMIN_USERNAME
```

The command opens the SQLite source read-only and takes a consistent read transaction. It imports customers, products, historical sale numbers/line prices, stock movements and payments into one empty PostgreSQL company. It keeps source timestamps, interpreting naive timestamps in the configured Casablanca timezone. It refuses a populated target and rolls back on failure. The source file is not changed. Old prototype retry identifiers for stock/payment requests are not migrated; old clients must not replay pending operations against the new API.

## Concurrency and isolation

Company commercial operations and consistent reads currently serialize using a row lock on the company. This is deliberate for correctness in the first milestone: different companies can operate independently, and concurrent sales within a company cannot oversell. Finer-grained inventory locks and paginated reporting can follow after measuring workload. Business records are fetched per selected company; the current UI still loads that company's commercial dataset into memory.

Company isolation is enforced through API authorization, scoped services, and relationship constraints. PostgreSQL row-level security is **not yet enabled**. Do not describe this milestone as database-enforced protection against an arbitrary unscoped SELECT by a compromised application. Runtime database roles, RLS, operational deployment and load targets remain part of subsequent hardening.

## Verification

```sh
.venv/bin/python manage.py test workspace --noinput
python3 -m unittest discover -s tests -v
```

The Django tests create and delete their own PostgreSQL test database; the database user needs test-database creation permission in development. Checks cover authentication/CSRF, rate limiting, organization boundaries, guessed foreign record IDs, company-specific export contents, read-only users, role restrictions, revocation, password/session invalidation, licensing limits, idempotent stock/payment behavior, numbering, atomic CSV import, prototype import and competing sales.

Browser tests are documented in `tests/platform-browser.cjs`; they use their own temporary PostgreSQL database and remove it when finished.

## Operations and remaining work

Use PostgreSQL-native full backups, stored securely outside the app's public files, to preserve users, companies and all business data. For the development container, a manual backup can be created with:

```sh
docker compose -p atlas-foundation exec -T db pg_dump -U atlas -d atlas -Fc > data/atlas-platform.dump
```

Restore to a **new database**, using `pg_restore`, and verify it before switching the application connection. Automated scheduling, encryption, retention and a documented recovery drill are not delivered by the company JSON export.

The development server is localhost-only. Remote deployment still requires HTTPS, explicit hosts, strong independent secrets, a non-superuser PostgreSQL runtime role, operational backups and a production server configuration. The code provides production cookie/HTTPS settings when `ATLAS_ENV=production`; it is not a deployed production service. The HTTP server and database must not be exposed merely by changing their bind addresses.

Supplier/purchase invoicing is now delivered in [Feature 2](PURCHASES.md), including its additional permissions and export fields. Accounting posting and reports are delivered in [Feature 3](ACCOUNTING.md); payment transfer and invoice matching are delivered in [Feature 4](SETTLEMENTS.md). Services/quantity precision, annual fiscal closing, VAT and Liasse remain later features. XML compatibility is still subject to the qualification recorded in `MOROCCAN-DECLARATIONS.md`.
