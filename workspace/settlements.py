"""Reviewed payment transfers and invoice/payment matching (not bank reconciliation)."""
from django.db.models import Q, Sum
from django.utils import timezone
from server import label, require
from .models import Account, EntryLine, JournalEntry, Payment, Purchase, Sale, SettlementMatch, SupplierPayment
from .services import scoped


def effective_entries(company, **filters):
    reversed_ids = JournalEntry.objects.filter(company=company, status='posted', reversal_of__isnull=False).values('reversal_of_id')
    return JournalEntry.objects.filter(company=company, **filters).exclude(status='discarded').exclude(pk__in=reversed_ids)


def require_unreversed(company, entry):
    require(entry.status == 'posted', 'Comptabilisez d’abord la facture ou le règlement.')
    require(not JournalEntry.objects.filter(company=company, reversal_of=entry).exclude(status='discarded').exists(),
            'Cette écriture a une contrepassation en cours ou comptabilisée.')


def ensure_can_reverse(company, entry):
    require(not SettlementMatch.objects.filter(company=company, voided_at__isnull=True).filter(
        Q(invoice_entry=entry) | Q(payment_entry=entry)).exists(), 'Délettrez les règlements liés avant de préparer leur contrepassation.')
    require(not effective_entries(company, settlement_invoice=entry).exists(),
            'Abandonnez ou contre-passez les règlements transférés avant de contre-passer la facture.')


def counter_line(company, invoice):
    require(invoice.sale_id or invoice.purchase_id, 'Choisissez une facture transférée.')
    rows = list(EntryLine.objects.filter(company=company, entry=invoice, **({'debit__gt': 0} if invoice.sale_id else {'credit__gt': 0})).select_related('account'))
    require(len(rows) == 1 and rows[0].debit + rows[0].credit == invoice.source_snapshot['total'],
            'Le compte de tiers de la facture ne peut pas être déterminé.')
    return rows[0]


class SettlementService:
    def __init__(self, accounting):
        self.book = accounting
        self.company, self.actor = accounting.company, accounting.actor

    def source(self, kind, pk):
        require(kind in ('customer_payment', 'supplier_payment'), 'Type de règlement invalide.')
        customer = kind == 'customer_payment'
        payment = scoped(Payment if customer else SupplierPayment, self.company, pk)
        invoice = payment.sale if customer else payment.purchase
        require(invoice.company_id == self.company.pk and invoice.status == ('active' if customer else 'received'), 'La facture du règlement est annulée ou non réceptionnée.')
        require(payment.amount > 0, 'Le règlement doit être positif.')
        entry = JournalEntry.objects.filter(company=self.company, **({'sale': invoice} if customer else {'purchase': invoice})).exclude(status='discarded').first()
        require(entry is not None, 'Transférez et comptabilisez d’abord la facture associée.')
        require_unreversed(self.company, entry)
        _, current = self.book.source('sale' if customer else 'purchase', invoice.pk)
        require(current == entry.source_snapshot, 'La facture ne correspond plus à son écriture comptable.')
        snapshot = dict(kind=kind, id=payment.pk, total=payment.amount, method=payment.method,
                        date=(timezone.localdate(payment.created_at) if customer else payment.payment_date).isoformat(),
                        reference='' if customer else payment.reference, invoice_id=invoice.pk,
                        invoice_reference=f"{'VT' if customer else 'AC'}-{invoice.number:04d}",
                        party=entry.source_snapshot['party'], invoice_entry_id=entry.pk)
        return payment, entry, snapshot

    def transfer(self, p):
        kind = p.get('kind')
        payment, invoice, snapshot = self.source(kind, p.get('source_id'))
        prior = effective_entries(self.company, **{kind: payment}).first()
        if prior:
            return {'id': prior.pk, 'version': prior.version, 'already_saved': True}
        journal, period, day = self.book.context(p)
        require(day >= invoice.date, 'La date du règlement comptable ne peut pas précéder celle de la facture.')
        counter = counter_line(self.company, invoice).account
        cash = scoped(Account, self.company, p.get('cash_account_id'))
        require(cash.pk != counter.pk, 'Le compte de banque ou caisse doit être distinct du compte de tiers.')
        amount = f'{payment.amount // 100}.{payment.amount % 100:02d}'
        customer = kind == 'customer_payment'
        lines = self.book.normalized_lines([
            {'account_id': cash.pk, 'debit': amount if customer else 0, 'credit': 0 if customer else amount, 'label': snapshot['invoice_reference']},
            {'account_id': counter.pk, 'debit': 0 if customer else amount, 'credit': amount if customer else 0, 'label': snapshot['invoice_reference']},
        ])
        entry = JournalEntry.objects.create(company=self.company, journal=journal, period=period, date=day,
            memo=f"Règlement {'client' if customer else 'fournisseur'} · {snapshot['party']}",
            reference=snapshot['reference'] or snapshot['invoice_reference'], source_snapshot=snapshot,
            settlement_invoice=invoice, created_by=self.actor, **{kind: payment})
        self.book.write_lines(entry, lines)
        return {'id': entry.pk, 'version': entry.version}

    def validate_post(self, entry):
        kind = 'customer_payment' if entry.customer_payment_id else 'supplier_payment'
        _, invoice, snapshot = self.source(kind, entry.customer_payment_id or entry.supplier_payment_id)
        require(snapshot == entry.source_snapshot and invoice.pk == entry.settlement_invoice_id,
                'Le règlement source a changé. Abandonnez ce brouillon et transférez-le à nouveau.')
        require(entry.date >= invoice.date, 'La date du règlement comptable ne peut pas précéder celle de la facture.')
        counter = counter_line(self.company, invoice)
        rows = list(EntryLine.objects.filter(company=self.company, entry=entry))
        amount = snapshot['total']
        customer = kind == 'customer_payment'
        require(len(rows) == 2 and any(l.account_id == counter.account_id and
                (l.debit, l.credit) == ((0, amount) if customer else (amount, 0)) for l in rows) and
                any(l.account_id != counter.account_id and
                (l.debit, l.credit) == ((amount, 0) if customer else (0, amount)) for l in rows),
                'Les lignes du règlement ne correspondent plus au compte de tiers et au montant source.')

    def match(self, p):
        entry = scoped(JournalEntry, self.company, p.get('payment_entry_id'))
        require(entry.settlement_invoice_id is not None, 'Choisissez un règlement transféré.')
        invoice = scoped(JournalEntry, self.company, entry.settlement_invoice_id)
        require_unreversed(self.company, entry)
        require_unreversed(self.company, invoice)
        prior = SettlementMatch.objects.filter(company=self.company, payment_entry=entry, voided_at__isnull=True).first()
        if prior:
            return {'id': prior.pk, 'already_saved': True}
        self.validate_post(entry)
        counter = counter_line(self.company, invoice)
        rows = list(EntryLine.objects.filter(company=self.company, entry=entry, account=counter.account))
        amount = entry.source_snapshot['total']
        require(len(rows) == 1 and ((counter.debit and rows[0].credit == amount and not rows[0].debit) or
                                  (counter.credit and rows[0].debit == amount and not rows[0].credit)), 'Le règlement ne solde pas le même compte de tiers.')
        matched = SettlementMatch.objects.filter(company=self.company, invoice_entry=invoice, voided_at__isnull=True).aggregate(total=Sum('amount'))['total'] or 0
        require(matched + amount <= counter.debit + counter.credit, 'Le lettrage dépasserait le montant de la facture.')
        match = SettlementMatch.objects.create(company=self.company, invoice_entry=invoice, payment_entry=entry, amount=amount, created_by=self.actor)
        return {'id': match.pk, 'invoice_entry_id': invoice.pk, 'payment_entry_id': entry.pk, 'amount': amount}

    def unmatch(self, p):
        match = scoped(SettlementMatch, self.company, p.get('id'))
        require(match.voided_at is None, 'Ce lettrage a déjà été annulé.')
        match.void_reason = label(p.get('reason'), 'Motif', limit=300)
        match.voided_at, match.voided_by = timezone.now(), self.actor
        match.save(update_fields=['void_reason', 'voided_at', 'voided_by'])
        return {'id': match.pk, 'reason': match.void_reason}

    def reconciliation(self):
        entries = list(JournalEntry.objects.filter(company=self.company).exclude(status='discarded'))
        reversals = {e.reversal_of_id: e for e in entries if e.reversal_of_id}
        effective = [e for e in entries if e.pk not in reversals or reversals[e.pk].status != 'posted']
        invoices = {('sale' if e.sale_id else 'purchase', e.sale_id or e.purchase_id): e for e in entries if e.sale_id or e.purchase_id}
        payment_entries = {('customer_payment' if e.customer_payment_id else 'supplier_payment', e.customer_payment_id or e.supplier_payment_id): e
                           for e in effective if e.customer_payment_id or e.supplier_payment_id}
        matches = {m.payment_entry_id: m for m in SettlementMatch.objects.filter(company=self.company, voided_at__isnull=True)}
        payment_groups = {}
        for kind, model, invoice_kind, fk in [('customer_payment', Payment, 'sale', 'sale_id'), ('supplier_payment', SupplierPayment, 'purchase', 'purchase_id')]:
            for p in model.objects.filter(company=self.company).order_by('id'):
                e = payment_entries.get((kind, p.pk))
                m = matches.get(e.pk) if e else None
                payment_groups.setdefault((invoice_kind, getattr(p, fk)), []).append(dict(kind=kind, id=p.pk, amount=p.amount,
                    date=timezone.localdate(p.created_at).isoformat() if kind == 'customer_payment' else p.payment_date.isoformat(),
                    method=p.method, reference=getattr(p, 'reference', ''), entry_id=e.pk if e else None,
                    status=e.status if e else 'untransferred', reversal_pending=bool(e and e.pk in reversals),
                    match_id=m.pk if m else None))
        result = []
        for kind, model, status in [('sale', Sale, 'active'), ('purchase', Purchase, 'received')]:
            for source in model.objects.filter(company=self.company, status=status, total__gt=0).order_by('id'):
                key = (kind, source.pk)
                entry, payments = invoices.get(key), payment_groups.get(key, [])
                available = bool(entry and entry.status == 'posted' and entry.pk not in reversals)
                invoice_posted = bool(entry and entry.status == 'posted' and (entry.pk not in reversals or reversals[entry.pk].status != 'posted'))
                posted = sum(p['amount'] for p in payments if p['status'] == 'posted')
                matched = sum(p['amount'] for p in payments if p['match_id'])
                result.append(dict(kind=kind, id=source.pk, number=f"{'VT' if kind == 'sale' else 'AC'}-{source.number:04d}",
                    party=source.customer_name if kind == 'sale' else source.supplier_name, total=source.total, paid=source.paid,
                    invoice_entry_id=entry.pk if entry else None, invoice_status=('reversed' if reversals[entry.pk].status == 'posted' else 'reversal_pending') if entry and entry.pk in reversals else entry.status if entry else 'untransferred',
                    available=available, posted_payments=posted, matched=matched, payment_gap=source.paid-posted,
                    accounting_remaining=source.total-posted if invoice_posted else None, payments=payments))
        return result
