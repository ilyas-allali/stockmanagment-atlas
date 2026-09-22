"""Internal VAT review worksheets. No filing adapter or automatic tax eligibility."""
import calendar
import hashlib
import json
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone
from server import integer, label, money, require
from .models import Company, Payment, Purchase, Sale, SupplierPayment, VatWorksheet
from .purchases import calendar_date
from .services import scoped


def totals(sheet):
    reviewed = [l for l in sheet.lines if l['reviewed']]
    sales = sum(l['retained_tax'] for l in reviewed if l['direction'] == 'sale')
    purchases = sum(l['retained_tax'] for l in reviewed if l['direction'] == 'purchase')
    net = sales - purchases - sheet.opening_credit
    return dict(sales_tax=sales, deductible_tax=purchases, opening_credit=sheet.opening_credit,
                payable=max(net, 0), carryforward=max(-net, 0), pending=sum(not l['reviewed'] for l in sheet.lines))


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


class VatService:
    def __init__(self, company, actor):
        self.company, self.actor = company, actor

    def handle(self, action, p):
        return {'vat-create': self.create, 'vat-import': self.import_sources, 'vat-line': self.line,
                'vat-remove': self.remove, 'vat-settings': self.settings, 'vat-approve': self.approve,
                'vat-void': self.void}[action](p)

    def draft(self, p):
        sheet = scoped(VatWorksheet, self.company, p.get('id'))
        require(sheet.status == 'draft', 'Cette préparation est verrouillée. Annulez son approbation pour préparer une nouvelle version.')
        require(integer(p.get('version'), 'Version', 1) == sheet.version, 'La préparation a changé. Actualisez la page.')
        return sheet

    def save(self, sheet):
        sheet.version += 1
        sheet.save()
        return {'id': sheet.pk, 'version': sheet.version}

    def create(self, p):
        start = calendar_date(p.get('start'), 'Début de période')
        cadence = p.get('cadence')
        require(cadence in ('monthly', 'quarterly'), 'Périodicité invalide.')
        require(start.day == 1 and (cadence == 'monthly' or start.month in (1, 4, 7, 10)), 'Choisissez le premier jour du mois ou du trimestre.')
        month = start.month if cadence == 'monthly' else start.month + 2
        end = date(start.year, month, calendar.monthrange(start.year, month)[1])
        require(not VatWorksheet.objects.filter(company=self.company, start__lte=end, end__gte=start).exclude(status__in=['voided', 'discarded']).exists(),
                'Une préparation active couvre déjà cette période.')
        sales_basis, purchase_basis = p.get('sales_basis'), p.get('purchase_basis')
        require(sales_basis in ('invoices', 'payments') and purchase_basis in ('invoices', 'payments'), 'Choisissez les bases d’import des ventes et achats.')
        sheet = VatWorksheet.objects.create(company=self.company, start=start, end=end, cadence=cadence,
            sales_basis=sales_basis, purchase_basis=purchase_basis, created_by=self.actor)
        return {'id': sheet.pk, 'version': sheet.version}

    def sources(self, sheet):
        """Candidate amounts, never a determination of deductibility/tax liability."""
        results = {}
        for direction, model, payment_model, fk, status, basis in [
            ('sale', Sale, Payment, 'sale_id', 'active', sheet.sales_basis),
            ('purchase', Purchase, SupplierPayment, 'purchase_id', 'received', sheet.purchase_basis)]:
            payments = defaultdict(list)
            for payment in payment_model.objects.filter(company=self.company).order_by('created_at' if direction == 'sale' else 'payment_date', 'id'):
                payments[getattr(payment, fk)].append(payment)
            for invoice in model.objects.filter(company=self.company, status=status).select_related('customer' if direction == 'sale' else 'supplier'):
                if not invoice.total:
                    continue
                day = timezone.localdate(invoice.created_at) if direction == 'sale' else invoice.invoice_date
                party = invoice.customer if direction == 'sale' else invoice.supplier
                common = dict(document_key=f'{direction}:{invoice.pk}', document_tax=invoice.tax,
                    invoice_date=day.isoformat(), invoice_total=invoice.total,
                    reference=f'VT-{invoice.number:04d}' if direction == 'sale' else invoice.supplier_reference,
                    party=invoice.customer_name if direction == 'sale' else invoice.supplier_name,
                    fiscal_id=getattr(party, 'fiscal_id', ''), ice=getattr(party, 'ice', ''), direction=direction)
                if basis == 'invoices':
                    events = [(f'{direction}:{invoice.pk}', day, invoice.subtotal, invoice.tax, '', '')]
                else:
                    events, cumulative = [], 0
                    def proportional(value, paid):
                        return int((Decimal(value) * paid / invoice.total).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                    for payment in payments[invoice.pk]:
                        payment_day = timezone.localdate(payment.created_at) if direction == 'sale' else payment.payment_date
                        before = cumulative
                        cumulative += payment.amount
                        require(cumulative <= invoice.total, 'Les règlements d’une facture dépassent son total. Corrigez la source avant l’import TVA.')
                        tax = proportional(invoice.tax, cumulative) - proportional(invoice.tax, before)
                        # TTC - allocated tax preserves the exact paid amount in centimes.
                        net = payment.amount - tax
                        events.append((f'{direction}-payment:{payment.pk}', payment_day, net, tax, payment.method, getattr(payment, 'reference', '')))
                for key, source_day, net, tax, method, payment_reference in events:
                    if sheet.start <= source_day <= sheet.end:
                        snapshot = dict(common, key=key, date=source_day.isoformat(), net=net, tax=tax,
                                        method=method, payment_reference=payment_reference, basis=basis)
                        results[key] = snapshot
        return results

    def import_sources(self, p):
        sheet = self.draft(p)
        sources = self.sources(sheet)
        existing = {l['key']: l for l in sheet.lines if l['source']}
        added = changed = 0
        for key, snapshot in sources.items():
            prior = existing.get(key)
            if prior and prior['source'] == snapshot:
                continue
            row = dict(key=key, direction=snapshot['direction'], date=snapshot['date'], reference=snapshot['reference'],
                party=snapshot['party'], net=snapshot['net'], tax=snapshot['tax'], retained_tax=0,
                reviewed=False, reason='', source=snapshot)
            if prior:
                sheet.lines[sheet.lines.index(prior)] = row
                changed += 1
            else:
                sheet.lines.append(row)
                added += 1
        require(len(sheet.lines) <= 2000, 'Maximum : 2 000 lignes par préparation.')
        result = self.save(sheet)
        return dict(result, added=added, changed=changed)

    def line(self, p):
        sheet = self.draft(p)
        key = p.get('key')
        prior = next((l for l in sheet.lines if l['key'] == key), None) if key else None
        require(not key or prior is not None, 'Ligne introuvable dans cette préparation.')
        if prior and prior['source']:
            require(self.sources(sheet).get(key) == prior['source'], 'La source a changé. Réimportez les sources ou retirez la ligne obsolète.')
            row = dict(prior)
        else:
            direction = p.get('direction')
            require(direction in ('sale', 'purchase'), 'Choisissez vente ou achat.')
            day = calendar_date(p.get('date'), 'Date de prise en compte')
            require(sheet.start <= day <= sheet.end, 'La date doit appartenir à la période.')
            row = dict(key=key or f'manual:{uuid.uuid4()}', direction=direction, date=day.isoformat(),
                reference=label(p.get('reference'), 'Référence', limit=80), party=label(p.get('party'), 'Tiers'),
                net=money(p.get('net'), 'Montant HT'), tax=money(p.get('tax'), 'TVA du document'), source=None)
        retained = money(p.get('retained_tax'), 'TVA retenue')
        require(retained <= row['tax'], 'La TVA retenue ne peut pas dépasser la TVA source.')
        reason = label(p.get('reason'), 'Justification du traitement', limit=300)
        row.update(retained_tax=retained, reviewed=True, reason=reason)
        if prior:
            sheet.lines[sheet.lines.index(prior)] = row
        else:
            require(len(sheet.lines) < 2000, 'Maximum : 2 000 lignes par préparation.')
            sheet.lines.append(row)
        return dict(self.save(sheet), key=row['key'])

    def remove(self, p):
        sheet = self.draft(p)
        key = p.get('key')
        require(any(l['key'] == key for l in sheet.lines), 'Ligne introuvable.')
        reason = label(p.get('reason'), 'Motif', limit=300)
        sheet.lines = [l for l in sheet.lines if l['key'] != key]
        return dict(self.save(sheet), key=key, reason=reason)

    def settings(self, p):
        sheet = self.draft(p)
        sheet.opening_credit = money(p.get('opening_credit', 0), 'Crédit antérieur')
        sheet.credit_note = label(p.get('credit_note', ''), 'Origine du crédit', bool(sheet.opening_credit), 300)
        sheet.note = label(p.get('note', ''), 'Note de préparation', False, 1000)
        return self.save(sheet)

    def diagnostics(self, sheet):
        sources = self.sources(sheet)
        stale = [l['key'] for l in sheet.lines if l['source'] and sources.get(l['key']) != l['source']]
        known = {l['key'] for l in sheet.lines if l['source']}
        missing = [k for k in sources if k not in known]
        return dict(stale=stale, missing=missing)

    def approve(self, p):
        sheet = self.draft(p)
        require(totals(sheet)['pending'] == 0, 'Vérifiez chaque ligne avant l’approbation.')
        require(p.get('confirmed') is True, 'Confirmez la vérification du périmètre, des montants et du crédit antérieur.')
        checks = self.diagnostics(sheet)
        require(not checks['stale'], 'Des sources ont changé ou disparu. Réimportez ou retirez les lignes obsolètes.')
        require(not checks['missing'], 'De nouvelles sources sont disponibles. Importez-les et vérifiez leur traitement, même si leur TVA retenue est nulle.')
        used_keys, allocated = set(), defaultdict(int)
        for other in VatWorksheet.objects.filter(company=self.company, status='approved'):
            for line in other.lines:
                if line['source'] and line['retained_tax']:
                    used_keys.add(line['key'])
                    allocated[line['source']['document_key']] += line['retained_tax']
        for line in sheet.lines:
            if not line['source'] or not line['retained_tax']:
                continue
            require(line['key'] not in used_keys, 'Une source est déjà retenue dans une autre préparation approuvée.')
            key = line['source']['document_key']
            allocated[key] += line['retained_tax']
            require(allocated[key] <= line['source']['document_tax'], 'Le cumul de TVA retenue dépasse la TVA de la facture dans les préparations approuvées.')
        sheet.company_snapshot = {k: getattr(self.company, k) for k in ('name', 'fiscal_id', 'ice', 'address')}
        sheet.approved_by, sheet.approved_at = self.actor, timezone.now()
        sheet.status = 'approved'
        sheet.approved_snapshot = dict(format='atlas-vat-review', version=1, worksheet_id=sheet.pk,
            company_id=self.company.pk, company=sheet.company_snapshot, start=sheet.start.isoformat(), end=sheet.end.isoformat(),
            cadence=sheet.cadence, sales_basis=sheet.sales_basis, purchase_basis=sheet.purchase_basis,
            lines=sheet.lines, totals=totals(sheet), credit_note=sheet.credit_note, note=sheet.note,
            approved_by=self.actor.pk, approved_at=sheet.approved_at.isoformat(), filing_status='not_submitted')
        sheet.checksum = fingerprint(sheet.approved_snapshot)
        return self.save(sheet)

    def void(self, p):
        sheet = scoped(VatWorksheet, self.company, p.get('id'))
        require(sheet.status in ('draft', 'approved'), 'Cette préparation est déjà annulée.')
        require(integer(p.get('version'), 'Version', 1) == sheet.version, 'La préparation a changé. Actualisez la page.')
        sheet.void_reason = label(p.get('reason'), 'Motif', limit=300)
        sheet.status, sheet.voided_by, sheet.voided_at = ('voided' if sheet.status == 'approved' else 'discarded'), self.actor, timezone.now()
        return self.save(sheet)

    @transaction.atomic
    def state(self):
        Company.objects.select_for_update().get(pk=self.company.pk)
        rows = []
        for sheet in VatWorksheet.objects.filter(company=self.company).order_by('-start', '-id'):
            row = {f.attname: getattr(sheet, f.attname) for f in sheet._meta.fields}
            row['totals'] = totals(sheet)
            row['diagnostics'] = self.diagnostics(sheet) if sheet.status == 'draft' else None
            rows.append(row)
        return {'worksheets': rows}
