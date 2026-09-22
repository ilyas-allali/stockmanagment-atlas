# Feature 3 — reviewed accounting and invoice transfer

The PostgreSQL app now includes **Comptabilité**: accounts, journals, accounting periods, manual drafts, sales/purchase invoice transfer, posting, linked reversals, journal, general ledger, trial balance and CSV reports. Accounts and journals start empty; no statutory chart, tax treatment or financial-statement mapping is invented.

## First use

1. Open **Comptabilité → Paramétrage**. Add the company's accountant-approved accounts and journals. Codes can contain letters, numbers, periods and hyphens. Add an accounting period with its start/end dates; periods cannot overlap within a company.
2. Open **Transfert des factures**. Active sales and received purchases with positive totals appear here. Select a document and choose a journal, open period, accounting date, counterparty account, net amount account and, if needed, tax account.
3. **Créer le brouillon de transfert** copies the source amounts automatically. No invoice re-entry or stock movement occurs. Review the source link and generated lines.
4. **Comptabiliser → Confirmer la comptabilisation** checks the period, active accounts, source snapshot and debit/credit equality. Posting assigns a consecutive number in the selected journal, records the actor/time and locks the entry. Drafts never affect reports.
5. Open **Rapports**, choose a period/date range and click **Afficher le rapport**. Switch between **Balance**, **Journal général** and **Grand livre**. CSV exports use the same period/date bounds.

The accounting date is chosen explicitly and defaults to the document date when it fits an open period; otherwise the form proposes an open period's date. The original document date stays in the source snapshot. Review any date difference before posting.

## Transfer behavior

Sales debit the selected counterparty account for TTC and credit the selected net/tax accounts for their source amounts. Purchases credit the counterparty account for TTC and debit the selected net/tax accounts. The counterparty account must differ from the net and tax accounts. The net and tax accounts may be the same if that matches the accountant's treatment. This feature does not infer tax recoverability or declaration timing.

The invoice's number, party name, source date/reference and totals are snapshotted. Transfer is unique for each source document while its entry is a draft or posted. Exact request retries and simultaneous requests do not create a second entry. Repeating a transfer with another request ID opens the existing entry; it does not replace its mappings. Mapping choices are made for each transfer in this milestone; reusable posting-rule templates are still pending.

Transferred drafts are not edited as free-form journal entries. To correct mappings before posting, abandon the draft with a reason and transfer again. Historical abandoned drafts remain visible. At posting, the original source must still be eligible and its snapshot must match. Payments do not change the invoice snapshot: invoice recognition and payment settlement are separate events.

**Payments are not automatically transferred yet.** They remain commercial records. Accountants may use manual entries for settlements, opening balances, expenses and other adjustments; those entries do not have automatic payment-source links or reconciliation. Do not enter a second manual invoice posting for a document already transferred. Automatic duplicate detection applies to explicit invoice-source links, not arbitrary manual entries with similar text.

## Manual entries, corrections and periods

- Manual drafts contain 2–100 lines. Each line has exactly one positive debit or credit, in integer centimes. An unbalanced draft can be saved for preparation, but posting rejects it. Each debit/credit total is limited to 10,000,000 DH.
- Editing/posting a stale draft is rejected through its version number. Account/journal codes cannot change after use; names and active status can change. Posted lines retain their account code/name snapshot. The trial balance displays the current account name; journal/ledger rows retain the historical name.
- Posted entries and their lines cannot be changed or deleted through the API; PostgreSQL triggers also reject direct updates/deletions/additions to posted records and reject unbalanced posting. Corrections use a linked reversal draft with opposite debits/credits, in an open period on or after the original date. The original remains posted and both entries appear in their respective reports.
- Only one non-abandoned reversal is allowed per original entry. A reversal must itself be reviewed and posted. Reversing a reversal is not offered in this milestone; further adjustments use reviewed manual entries.
- A commercially unpaid invoice cannot be cancelled while its accounting draft remains active or its posted entry remains unreversed. First abandon its draft or post its reversal; commercial cancellation then follows the existing stock/payment rules. A reversal does not automatically cancel a commercial invoice or refund payments.
- Closing a period requires no remaining drafts and a reason. Closed periods reject creation/posting. Reopening requires a reason and is audited. Authorized accountants and administrators can close/reopen periods. This is a date-entry lock, **not** statutory year-end closing, automatic profit appropriation or balance carryforward.
- A period's boundaries are fixed once created in this milestone; no period editing/deletion UI is provided.

## Report semantics

All reports select posted entries from one company and one chosen accounting period. Optional start/end dates must be within that period. Journal rows are ordered by accounting date, journal code, journal number and line ID. Ledger balances run independently per account. The UI can restrict the ledger to one account; a ledger CSV exports all accounts in the selected date range.

Trial balance columns: account, opening net balance, period debits, period credits and closing net balance. Net balances use **debit minus credit**; negative values are credit balances. The opening balance comprises posted activity earlier than the selected start date **inside the chosen period**. Earlier periods are not silently rolled forward. Record reviewed opening entries as appropriate before relying on a new period's balances. This feature does not generate a Bilan/CPC or certify statutory presentation.

The ledger CSV includes each exported line's running balance. Full opening/closing balances, including accounts with no movement inside the range, are available in the trial-balance CSV. Reports can be refreshed to include newly posted entries; an on-screen report and a subsequently downloaded CSV are live queries, not an immutable declaration snapshot.

## Permissions and isolation

| Role | Read entries/reports | Accounts, journals, periods, drafts, posting, reversal | Accounting CSV |
| --- | --- | --- | --- |
| Organization/company administrator | Yes | Yes | Yes |
| Accountant | Yes | Yes | Yes |
| Supervisor | Yes | No | Yes |
| Read-only | Yes | No | No |
| Commercial | No | No | No |

Every accounting endpoint checks company access and the accounting capability. Commercial `/state` does not include accounting records. The UI fetches accounting state separately for authorized roles. Company locks serialize accounting and commercial changes; PostgreSQL composite foreign keys protect account, journal, period, invoice, entry-line and reversal relationships across companies. There is no row-level-security claim: direct database privileges still require operational hardening.

Feature 3 introduced company JSON export version **3**. [Feature 4](SETTLEMENTS.md) advances it to **4**, retaining `accounts`, `journals`, `periods`, `entries` and `lines` and adding payment links, matching history and reconciliation summaries. They remain company data exports, not full operational backups or an implemented restoration format. Accounts/periods/entries make a company nonempty for the legacy SQLite importer.

## API and validation

Paths are relative to `/api/companies/<company_id>/`. Authenticated writes require CSRF tokens and a unique `request_key`; exact retries return the original response and do not repeat side effects. Reusing a request key with different content is rejected. Historical retry responses are acknowledgements of their original operation, not a replacement for refreshing current state.

| Method/path | Purpose |
| --- | --- |
| POST `accounting-account`, `accounting-journal` | Create/edit master records: code, name, active, optional id |
| POST `accounting-period` | Create nonoverlapping period: name, start, end |
| POST `accounting-period-state` | Close/reopen: id, closed, expected_closed, reason |
| POST `accounting-entry` | Manual draft: journal_id, period_id, date, memo, optional reference, lines; edits include id/version |
| POST `accounting-transfer` | kind sale/purchase, source_id, journal_id, period_id, date, counter_account_id, net_account_id, tax_account_id when applicable |
| POST `accounting-post`, `accounting-discard` | id/version; discard also requires reason |
| POST `accounting-reverse` | Original id, target journal_id/period_id/date and reason |
| GET `accounting/state` | Scoped master data, entries and lines |
| GET `accounting/reports` | period_id, optional date_from/date_to; posted ledger rows and trial balance |
| GET `accounting/export` | Same period/date parameters plus report=trial_balance/journal/ledger |

Line input uses `account_id`, optional `label`, and `debit`/`credit` in DH (at most two decimals). Responses/store use centimes. CSV text cells escape spreadsheet formula prefixes.

Tests cover balance/rounding, draft corrections, snapshots, exact retries, source duplicates, purchase receipts, cancellation dependencies, reversals, closed periods, date bounds, report reconciliation, company/role boundaries, PostgreSQL immutability/relationship constraints and concurrent transfer/posting. `tests/accounting-browser.cjs` covers the setup-to-report workflow and mobile read-only access using a disposable PostgreSQL database.

## Upgrade and remaining work

After backing up the existing PostgreSQL database, apply `manage.py migrate` and restart the app. Migrations 0006–0007 add accounting tables and PostgreSQL guards without rewriting existing commercial records. `start-atlas.sh` applies pending migrations when it starts, as before. PostgreSQL/Docker must be running before upgrading the original local database.

Payment transfer and invoice matching are now available in [Feature 4](SETTLEMENTS.md). Still pending: reusable posting templates, batch transfer, period/year-end procedures and carryforward, analytic accounting, VAT preparation, Bilan/CPC, qualified declaration XML and production rollout. Accounting datasets/reports currently load per company without pagination, following the existing commercial app's scale limits.
