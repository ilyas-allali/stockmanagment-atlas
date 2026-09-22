# Moroccan declaration targets for Atlas

Research performed 19–20 September 2026. This is an integration specification and evidence record, not a statement that declaration exports are implemented or accepted by the DGI.

## Conclusion for this project

Use Morocco's **DGI / SIMPL services** as the proposed declaration destination. The client description points to two initial integrations: **SIMPL-TVA** for VAT preparation/export and **SIMPL-IS** for the Liasse of companies subject to corporate income tax. This selection is an inference from the client's modules and official service descriptions, not confirmation of every company's tax regime.

The Ministry of Economy and Finance's [official service directory](https://www.finances.gov.ma/fr/Pages/e-Services-et-formulaires.aspx) lists SIMPL-TVA, SIMPL-IS and SIMPL-IR. A copy of that directory was retrieved on 19 September 2026 and is retained under `references/`.

| Client requirement | Proposed destination | What is established | What still needs verification |
| --- | --- | --- | --- |
| VAT module | SIMPL-TVA | Official DGI material documents EDI transfer of the VAT deduction schedule | Current technical specification, annexes, supported declaration scope and company regime |
| Liasse / Bilan / CPC for IS companies | SIMPL-IS | Official material describes transfer of Liasse information from accounting software through EDI | Applicable model, current XSD/annex package, codes, period applicability and target acceptance |
| Income-tax declarations, if applicable | SIMPL-IR | Listed in the official service directory | Whether these companies/declarations are in scope; any corresponding export contracts |
| Transfer from commercial to accounting inside Atlas | Atlas's own posting workflow | This is an internal product requirement | Company chart, account/tax mappings and review permissions |
| Exchange with the existing accounting/Liasse program | A separate external-software adapter, if required | No format or import contract has been supplied | Software version, accepted files and duplicate/reconciliation rules |

The DGI's [2015 activity report, page 31](https://www.finances.gov.ma/Publication/dgi/2017/rapport_dgi_2015.pdf) specifically describes the VAT **deduction schedule** and its EFI/EDI handling. This is historical evidence of that mechanism; it does not establish the complete scope or format of today's VAT declaration export.

The Ministry's [25 November 2010 SIMPL-IS announcement](https://www.finances.gov.ma/fr/Pages/detail-actualite.aspx?fiche=1414) describes EDI transfer of Liasse and other corporate-tax declaration information from accounting/tax software without re-entry. The [accompanying version 1.0 specification](https://www.finances.gov.ma/Publication/dgi/2010/9370_cahierdescharges.pdf) documents model-dependent XML/XSD structures. It is retained as an **archived reference**, not a current implementation contract.

## Findings that change the design

1. **There is no single universal “Moroccan accounting XML” established by this research.** Accounting exchange, VAT deduction schedules and Liasse exports must be separate adapters.
2. **Preparing a VAT return and exporting a deduction schedule are different deliverables.** The worksheet should support source details and manual review. Do not label a deduction-schedule export as a complete submitted VAT return.
3. **Liasse requires a selected reporting model and versioned mappings.** Do not export the general ledger directly and call it a Liasse. The exact tables and codes must come from the applicable specification.
4. **A company needs its own fiscal settings.** Do not assume all companies are IS companies, share a fiscal year or use the same VAT treatment.
5. **Generation, validation, submission and acceptance are separate events.** Downloading XML must not mark a declaration as submitted or accepted.

These are engineering decisions based on the confirmed distinction between the services and the client's review workflow. They are not tax eligibility determinations.

## What could not be verified

The DGI public portal and SIMPL-TVA login endpoint returned HTTP 403 to ordinary programmatic requests during this review. The web browsing service also reported retrieval failures. No credentials were used and no access controls were bypassed.

The current official VAT annex package and current official SIMPL-IS schema package were **not obtained or authenticated**. Search results contained third-party claims and mirrored specifications with differing versions; those are not adopted as the production authority. No claim is made that a particular “2026” version, field order, encoding, archive rule or deadline is verified.

The archived 2010 PDF is useful evidence of the integration mechanism, but must not be used as proof that files generated from it would be accepted today. The latest specification must be matched to the relevant declaration/model and fiscal period, not merely selected by its filename.

## Export adapter contract

Each supported declaration adapter must record:

- Destination service and exact declaration/annex type.
- Authoritative source URL and retrieved specification/annex files with checksums.
- Schema/annex version and applicable fiscal periods/models.
- Required company identifiers, code lists, field types and validation rules.
- XML namespaces, field ordering, encoding and packaging requirements, as verified from that contract.
- Test examples, expected rejection cases and documented target acceptance.

A declaration export runs from an approved, immutable snapshot. The artifact records company, period, preparer/reviewer, adapter version, source revision, checksum and validation results. Validation covers required business data as well as schema checks where an applicable XSD is available. It must not invent an XSD or describe syntactic XML validation as DGI certification.

The initial workflow ends with a downloadable file and human-controlled portal submission. Direct automated filing and storage of the client's DGI credentials are not requirements in the supplied brief.

## Data to preserve while official contracts are being qualified

The application can proceed with its internal foundation without pretending the export format is settled. Preserve company fiscal identity and settings, accounting periods, counterparties, source invoice references and dates, line/tax amounts, payment dates and allocations, supporting records, manual adjustments, carryforwards, account mappings and approval history.

These are internal data-model candidates to accommodate the client's workflows. They are not an asserted list of mandatory XML fields. The schema qualification step determines what is required for each adapter and how it is represented.

## Definition of a completed declaration integration

1. Retrieve the applicable official specification and all relevant annexes, through normal public access or an authorized client/accountant session when necessary.
2. Identify the company regime, declaration type, model and fiscal period.
3. Implement an adapter and validate both positive and negative examples.
4. Reconcile every exported amount to the approved source worksheet/statements.
5. Demonstrate import acceptance through the authorized target procedure; record any portal warnings and outstanding filing steps.
6. Pin that adapter version, preserve the approved artifact and document later version changes.

Until those checks are complete, any generated sample must be labelled **development sample / not validated for filing**. The rest of the application need not wait for XML qualification.

## 22 September 2026 implementation update

[Feature 5](VAT.md) implements internal VAT preparation, source review and immutable CSV/JSON approval snapshots. No DGI-compatible XML adapter or submission is implemented.

The Ministry's official [CGI 2026](https://www.finances.gov.ma/Publication/dgi/2025/CGI-2026-FR.pdf) was located through indexed official-source extracts. Article 95 distinguishes collection-based treatment from the debit option; articles 107–108 distinguish monthly and quarterly declarations. Atlas consequently exposes the period and source-selection choices to the accountant rather than inferring the company's legal treatment. The proportional payment proposal is an engineering aid subject to review, not a complete implementation of those statutory rules.

Direct retrieval of that PDF timed out in the browsing service, and the DGI/SIMPL-TVA portal remained inaccessible to that tool. The current official XML/annex package was not authenticated. Third-party format/version claims were not adopted. The qualification requirements above still apply; no tax return was submitted.

## Saved evidence

- `references/mef-eservices.html`: public ministry directory, retrieved 19 September 2026.
- `references/simpl-is-edi-v1.0-2010.pdf`: historical official SIMPL-IS specification, retrieved 19 September 2026.
- `references/sources.json`: original URLs, retrieval dates, content types, sizes and SHA-256 hashes.

No declaration was prepared for a real taxpayer, filed, or sent to a third party during this research.
