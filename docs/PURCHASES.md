# Feature 2 — suppliers and purchase invoices

This feature extends the multi-company Django/PostgreSQL app. Open **Fournisseurs** or **Achats** in the navigation. It is not part of the original standalone SQLite prototype.

## Daily workflow

1. **Create a supplier.** Record its name, contact details, address, fiscal identifier and optional 15-digit ICE. Each company keeps its own supplier list.
2. **Save a purchase draft.** Select the supplier, enter the supplier's invoice reference, invoice date and optional due date. Add catalog products, whole-unit quantities, purchase prices in DH excluding tax, and the tax percentage shown on each invoice line. The catalog purchase price is suggested and can be overridden. Save now and edit later.
3. **Confirm receipt.** After receiving all goods, open the draft and choose **Réceptionner les produits**, then confirm. All quantities enter stock together, with linked stock movements and an audit event. The invoice becomes immutable. Drafts have no stock effect and are excluded from amounts due.
4. **Record payment.** Choose **Régler le fournisseur** and enter a partial or full payment, method, payment date and optional reference. The payment date must be on/after the invoice date and no later than today in Casablanca. Amounts cannot exceed the unpaid balance. This records a payment made outside Atlas; it does not initiate a bank transfer.
5. **Follow up.** The purchase list shows drafts, received purchases, amounts owed and overdue invoices. A due date becomes overdue the day after that date, using Casablanca time. Search by internal number, supplier name or supplier reference. Supplier cards show the balance across received invoices.

Internal numbers use **AC-0001**, separately per company. Supplier invoice references are mandatory and case-insensitively unique for that supplier in that company, with outer whitespace trimmed. Cancelled references remain reserved to preserve history.

## Corrections

Drafts can be edited. Atlas rejects an edit or receipt confirmation if another user has changed that draft since it was opened; refresh before retrying.

Administrators and supervisors can cancel an unpaid draft with a reason. They may also cancel an unpaid received invoice when its receipt genuinely needs to be reversed and all quantities are still available in stock. That reversal removes the quantities once and remains visible in the movement journal. It does not track physical batches or establish that returned units are the same physical units originally received. Cancellation fails atomically if any line lacks stock. Paid invoices require a future credit-note/refund workflow and cannot be cancelled here.

## Money and inventory behavior

- Amounts are stored in integer centimes. For each line: quantity × unit price gives the net amount; tax is rounded half-up to the nearest centime. Invoice totals sum those rounded lines. Tax rates are manually supplied, not selected or certified by a statutory tax engine.
- Each product appears once per invoice. Quantities are positive integers, at most 1,000,000; stock receipts cannot increase a product above 1,000,000 units. Maximum invoice total: 10,000,000 DH.
- Product name/SKU, purchase price and tax totals are copied onto purchase lines; supplier name is copied onto the invoice when the draft is saved. Later changes to catalog/contact records do not rewrite the saved invoice. The complete historical supplier tax/address identity is not snapshotted by this milestone.
- Receipt changes stock quantities only. It does **not** overwrite catalog purchase/sale prices, calculate weighted-average cost, or retrospectively change sale margins. Inventory valuation remains a separate future feature.
- Commercial mutations serialize under the company's transaction lock. Draft creation/editing, receipt, cancellation and payments require request identifiers. Exact retries return the original result without a second stock/payment/audit event; reusing a key with different content is rejected.
- PostgreSQL composite foreign keys reject cross-company links for suppliers, purchases, purchase items, supplier payments and linked stock movements. Application authorization also scopes every endpoint.

## Permissions

| Role | Supplier records | Drafts / receipts | Supplier payments | Cancellation | Purchase CSV |
| --- | --- | --- | --- | --- | --- |
| Organization/company administrator | Create/edit/read | Yes | Yes | Yes | Yes |
| Commercial | Create/edit/read | Yes | Yes | No | Yes |
| Supervisor | Create/edit/read | Yes | Yes | Yes | Yes |
| Accountant | Read | No | Yes | No | Yes |
| Read-only | Read | No | No | No | No |

All access remains company-scoped. Visible records can be printed in the browser, including by read-only users. Organization/company administrators retain the company JSON export permission.

## Exports and API

- **Exporter** on Achats downloads a CSV of all purchase invoices in the selected company, including status, invoice/due dates, totals, payments and amounts due. The CSV contains all statuses regardless of the current screen filter; draft/cancelled amounts due are zero. Spreadsheet formula prefixes in text are escaped.
- **Imprimer** creates an internal purchase copy. Keep the supplier's original invoice; this output is not an official invoice issued by Atlas on the supplier's behalf.
- Feature 2 introduced company JSON export version **2**, adding `suppliers`, `purchases`, `purchase_items`, `supplier_payments` and purchase links on stock movements. Feature 3 adds an accounting section; Feature 4 advances the current format to version **4** with payment links and matching history. It still is not a complete operational backup or an implemented restore format.

All paths below are relative to `/api/companies/<company_id>/`:

| Method / path | Behavior |
| --- | --- |
| POST `suppliers` | Create or edit a company supplier |
| POST `purchases` | Create or replace a draft's fields and lines; edits include `id` and `version` |
| POST `purchase-receive` | Receive a draft using `purchase_id`, `version`, `request_key` |
| POST `purchase-cancel` | Cancel an unpaid invoice using `purchase_id`, `version`, `reason`, `request_key` |
| POST `supplier-payments` | Record payment using `purchase_id`, `amount`, `payment_date`, optional `method`/`reference`, `request_key` |
| GET `state` | Existing company state plus the four purchasing collections |
| GET `export/purchases` | Company purchase summary CSV |

Authenticated mutations require CSRF tokens. A draft payload also includes `request_key`, `supplier_id`, `supplier_reference`, `invoice_date`, optional `due_date`/`note`, and `items` containing `product_id`, `quantity`, `price` (DH, at most two decimals) and `tax_bps` (basis points: 2000 means 20%).

## Validation and boundaries

`manage.py test workspace` includes purchase tests for arithmetic, draft edits, immutable receipts, payments, date/quantity limits, duplicates, exact retries, company/role boundaries, database relationship constraints, exports, transaction rollback and simultaneous receipts/payments. `tests/purchases-browser.cjs` exercises supplier creation/editing, a mixed-tax invoice, receipt, partial/full payments, cancellation, search/filter, print/CSV and company isolation on desktop/mobile. Browser tests create and remove a separate PostgreSQL database.

This is a stock-product purchasing workflow with full receipt per invoice. Partial deliveries, purchase orders, advances/unallocated supplier payments, credit notes/refunds, services, fractional units, multiple warehouses, document attachments, landed costs, and valuation are not yet implemented. Reviewed invoice transfer is now available in [Feature 3](ACCOUNTING.md); supplier-payment transfer and invoice matching are available in [Feature 4](SETTLEMENTS.md). Purchase tax is recorded from the supplier invoice; VAT recoverability, declaration timing and XML compatibility are not determined here.
