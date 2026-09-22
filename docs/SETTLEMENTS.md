# Feature 4 — payment transfer and invoice matching

Open **Comptabilité → Règlements & lettrage**. Customer and supplier payments recorded in Atlas can now generate accounting drafts without re-entering amounts. After posting, an accountant can match each payment to its invoice, including partial settlements.

## Workflow

1. Transfer and post the invoice using the accounts chosen by the accountant.
2. Record a customer or supplier payment in the commercial module. This records an external payment; Atlas does not initiate a bank transfer.
3. In **Règlements & lettrage**, choose **Transférer le règlement**. Select a journal, open period, accounting date and bank/cash account. The customer/supplier account is taken from the posted invoice. Amounts, source date, method and references are copied automatically.
4. Review the generated draft and choose **Comptabiliser**. Customer payments debit bank/cash and credit the invoice's customer account. Supplier payments debit the invoice's payable account and credit bank/cash. No new stock movement or commercial payment is created.
5. Choose **Lettrer → Confirmer le lettrage**. The full amount of that payment is associated with its invoice. Several payments can partially or fully match an invoice. Matching never alters posted amounts or commercial balances.

The accounting date cannot precede the invoice's accounting date. The original payment date is preserved separately. Accounts/journal must be active, the period open, and the source invoice posted without a pending or posted reversal. Account codes are supplied by the accountant; selecting an account does not certify its statutory classification.

## Reading the follow-up screen

The screen is cumulative across all periods, for active sales and received purchases with positive totals. It shows:

- **Payé au commercial**: the invoice's recorded commercial payments.
- **Règlements comptabilisés**: linked posted payment entries, excluding entries with a posted reversal.
- **Montant lettré**: active matches; unmatching removes an amount from this total while preserving history.
- **Reste comptable**: invoice TTC minus linked posted payments. A draft/untransferred/reversed invoice shows no accounting remainder. Arbitrary manual entries are not included in this document-level calculation; the general ledger includes them.
- **Écart commercial / comptabilité**: commercial paid amount minus linked posted payments, exposing missing/draft/reversed transfers.

A pending reversal leaves its original posted amount in accounting until the reversal is posted. An invoice is marked **Lettrée** only when its full total is matched, there is no payment gap, and its entry has no pending/posted reversal.

**Exporter le suivi** downloads all these company invoice summaries as CSV, with spreadsheet formula prefixes escaped. Export is not filtered to a period. This feature matches invoices and payments; bank statement import and bank reconciliation remain future work.

## Corrections and history

- An incorrect draft can be abandoned and transferred again. Payment drafts cannot be edited as manual entries.
- Posted payments are immutable. Choose **Délettrer**, enter a reason, then prepare and post a reversal. The payment can then be transferred again with corrected accounts. Previous entries, reversals and voided matches remain in history.
- A matched entry cannot be reversed until its matches are undone. An invoice cannot be reversed while it has effective linked payment drafts or posted entries: abandon/reverse those first. Checks run both when preparing and posting reversals.
- Reversed payment entries cease to count as effective transfers. There can only be one effective transfer per source payment and one active match per payment entry. A payment match cannot exceed the remaining invoice amount.
- Lettrage/délettrage is allowed after period closure because it does not modify dated ledger lines. Reversals require an open period.
- Matching history cannot be deleted or rewritten; only one-way voiding with an actor, time and reason is allowed. PostgreSQL guards protect these records, payment entry shape, effective-transfer uniqueness and company relationships. Application transactions serialize writes under a company lock.

## Access and API

Administrators and accountants can transfer, post, match and unmatch. Supervisors can read/export; read-only users can read; commercial users record commercial payments but cannot access accounting endpoints. All paths below are relative to `/api/companies/<company_id>/`.

| Method/path | Input / result |
| --- | --- |
| POST `accounting-payment-transfer` | `kind`: `customer_payment`/`supplier_payment`; `source_id`, `cash_account_id`, `journal_id`, `period_id`, `date` → draft entry ID/version |
| POST `accounting-post` | Existing reviewed posting action, using entry `id`/`version` |
| POST `accounting-match` | `payment_entry_id` → match ID and amount inferred from the source |
| POST `accounting-unmatch` | Match `id`, `reason` |
| GET `accounting/state` | Includes `matches` with active/voided history and `reconciliation` invoice/payment summaries |
| GET `accounting/reconciliation-export` | Company summary CSV; accounting-read and export capabilities required |

Writes require CSRF and `request_key`. Exact retries acknowledge the original operation without repeating it; changing payload under a reused key is rejected. Concurrent transfer/matching requests return the existing effective transfer/match. Refresh state after mutations: a historical retry response does not describe later changes.

Feature 4 introduced company JSON export version **4**; [Feature 5](VAT.md) advances the current version to **5**, adding payment source links, settlement invoice links, matching history and reconciliation summaries to its accounting section. It remains a data export, not a full database backup or implemented restore format.

## Upgrade and validation

Back up PostgreSQL, then run `.venv/bin/python manage.py migrate` and restart the app. `sh start-atlas.sh` applies pending migrations at startup. Migrations **0008–0009** add nullable payment links, matching records, constraints and PostgreSQL guards; existing commercial and posted accounting records are retained.

Validation uses PostgreSQL backend tests and `tests/settlements-browser.cjs`: customer/supplier transfers, partial/full settlement, centime precision, overmatching rejection, exact retries, concurrent requests, source changes, account/date/period validation, draft/reversal dependencies, replacement transfers, immutable history, permissions, company isolation, CSV and mobile read-only access. Existing platform, purchase, accounting and legacy browser suites remain covered.

Current limits: no automatic recognition/adoption of manually posted payments, unallocated advances, splitting a payment across invoices, batch transfer, refunds/credit notes, exchange-rate handling or bank-feed reconciliation. Review existing manual bookkeeping before transferring historical payments. VAT preparation is available in [Feature 5](VAT.md). Financial statements and declaration XML remain separate features.
