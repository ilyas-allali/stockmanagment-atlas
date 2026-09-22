"""Reviewed double-entry bookkeeping; no statutory chart or tax policy is assumed."""
import re

from django.db import transaction
from django.utils import timezone
from server import integer, label, money, require
from .models import Account, AccountingPeriod, Company, EntryLine, Journal, JournalEntry, Purchase, Sale, SettlementMatch
from .purchases import calendar_date
from .services import scoped


def ensure_source_can_cancel(company, **source):
    entries = JournalEntry.objects.filter(company=company, **source).exclude(status='discarded')
    for entry in entries:
        require(entry.status == 'posted' and JournalEntry.objects.filter(company=company, reversal_of=entry, status='posted').exists(),
                'Cette facture est transférée en comptabilité. Abandonnez son brouillon ou comptabilisez sa contrepassation avant de l’annuler.')


class AccountingService:
    def __init__(self, company, actor):
        self.company, self.actor = company, actor

    def handle(self, action, p):
        from .settlements import SettlementService
        settlements = SettlementService(self)
        return {'accounting-payment-transfer': settlements.transfer, 'accounting-match': settlements.match,
                'accounting-unmatch': settlements.unmatch, 'accounting-account': self.account, 'accounting-journal': self.journal,
                'accounting-period': self.period, 'accounting-period-state': self.period_state,
                'accounting-entry': self.entry, 'accounting-transfer': self.transfer,
                'accounting-post': self.post, 'accounting-discard': self.discard,
                'accounting-reverse': self.reverse}[action](p)

    def master(self, model, p, size):
        code = label(p.get('code'), 'Code', limit=size).upper()
        require(re.fullmatch(r'[A-Z0-9][A-Z0-9.-]*', code), 'Code : lettres, chiffres, points et tirets uniquement.')
        name = label(p.get('name'), 'Libellé')
        active = p.get('active', True)
        require(isinstance(active, bool), 'État actif invalide.')
        obj = scoped(model, self.company, p['id']) if p.get('id') else model(company=self.company)
        if obj.pk:
            used = EntryLine.objects.filter(company=self.company, account=obj).exists() if model is Account else JournalEntry.objects.filter(company=self.company, journal=obj).exists()
            require(not used or obj.code == code, 'Le code d’un compte ou journal déjà utilisé ne peut pas être modifié.')
        obj.code, obj.name, obj.active = code, name, active
        obj.save()
        return {'id': obj.pk, 'code': obj.code}

    def account(self, p):
        return self.master(Account, p, 20)

    def journal(self, p):
        return self.master(Journal, p, 12)

    def period(self, p):
        start, end = calendar_date(p.get('start'), 'Début'), calendar_date(p.get('end'), 'Fin')
        require(start <= end, 'La fin doit suivre le début.')
        require(not AccountingPeriod.objects.filter(company=self.company, start__lte=end, end__gte=start).exists(),
                'Cette période chevauche une période existante.')
        period = AccountingPeriod.objects.create(company=self.company, name=label(p.get('name'), 'Période', limit=100), start=start, end=end)
        return {'id': period.pk}

    def period_state(self, p):
        period = scoped(AccountingPeriod, self.company, p.get('id'))
        require(isinstance(p.get('closed'), bool) and isinstance(p.get('expected_closed'), bool), 'État de période invalide.')
        require(period.closed == p['expected_closed'], 'La période a changé. Actualisez la page.')
        reason = label(p.get('reason'), 'Motif', limit=300)
        if p['closed']:
            require(not JournalEntry.objects.filter(company=self.company, period=period, status='draft').exists(),
                    'Comptabilisez ou abandonnez les brouillons de cette période avant de la fermer.')
        period.closed = p['closed']
        period.save(update_fields=['closed'])
        return {'id': period.pk, 'closed': period.closed, 'reason': reason}

    def context(self, p):
        journal = scoped(Journal, self.company, p.get('journal_id'))
        period = scoped(AccountingPeriod, self.company, p.get('period_id'))
        day = calendar_date(p.get('date'), 'Date comptable')
        require(journal.active, 'Ce journal est désactivé.')
        require(not period.closed, 'Cette période est fermée.')
        require(period.start <= day <= period.end, 'La date comptable doit appartenir à la période choisie.')
        return journal, period, day

    def check_version(self, entry, p):
        require(integer(p.get('version'), 'Version', 1) == entry.version, 'Cette écriture a changé. Actualisez la page.')

    def normalized_lines(self, items):
        require(isinstance(items, list) and 2 <= len(items) <= 100, 'Une écriture doit contenir entre 2 et 100 lignes.')
        lines = []
        for item in items:
            require(isinstance(item, dict), 'Ligne comptable invalide.')
            account = scoped(Account, self.company, item.get('account_id'))
            require(account.active, f'Compte désactivé : {account.code}.')
            debit, credit = money(item.get('debit', 0), 'Débit'), money(item.get('credit', 0), 'Crédit')
            require((debit > 0 and credit == 0) or (credit > 0 and debit == 0), 'Chaque ligne doit avoir un débit OU un crédit positif.')
            lines.append(dict(account=account, account_code=account.code, account_name=account.name,
                              label=label(item.get('label', ''), 'Libellé de ligne', False, 300), debit=debit, credit=credit))
        require(max(sum(l['debit'] for l in lines), sum(l['credit'] for l in lines)) <= 1_000_000_000,
                'Maximum par écriture et par sens : 10 000 000 DH.')
        return lines

    def write_lines(self, entry, lines):
        EntryLine.objects.filter(company=self.company, entry=entry).delete()
        EntryLine.objects.bulk_create([EntryLine(company=self.company, entry=entry, **line) for line in lines])

    def entry(self, p):
        journal, period, day = self.context(p)
        lines = self.normalized_lines(p.get('lines'))
        entry = scoped(JournalEntry, self.company, p['id']) if p.get('id') else JournalEntry(company=self.company, created_by=self.actor)
        if entry.pk:
            require(entry.status == 'draft' and not entry.sale_id and not entry.purchase_id and not entry.customer_payment_id and not entry.supplier_payment_id and not entry.reversal_of_id,
                    'Seul un brouillon manuel peut être modifié. Abandonnez puis recréez un transfert à corriger.')
            require(not entry.period.closed, 'La période d’origine est fermée.')
            self.check_version(entry, p)
            entry.version += 1
        entry.journal, entry.period, entry.date = journal, period, day
        entry.memo = label(p.get('memo'), 'Libellé', limit=300)
        entry.reference = label(p.get('reference', ''), 'Référence', False, 80)
        entry.save()
        self.write_lines(entry, lines)
        return {'id': entry.pk, 'version': entry.version}

    def source(self, kind, pk):
        require(kind in ('sale', 'purchase'), 'Source : vente ou achat attendu.')
        source = scoped(Sale if kind == 'sale' else Purchase, self.company, pk)
        require(source.status == ('active' if kind == 'sale' else 'received'), 'La facture source est annulée ou non réceptionnée.')
        require(source.total > 0, 'Une facture à total nul ne nécessite pas de transfert.')
        snapshot = {k: getattr(source, k) for k in ('number', 'subtotal', 'tax', 'total')}
        snapshot.update(kind=kind, id=source.pk, party=source.customer_name if kind == 'sale' else source.supplier_name,
                        date=(timezone.localdate(source.created_at) if kind == 'sale' else source.invoice_date).isoformat(),
                        reference=f'VT-{source.number:04d}' if kind == 'sale' else source.supplier_reference)
        return source, snapshot

    def transfer(self, p):
        kind = p.get('kind')
        source, snapshot = self.source(kind, p.get('source_id'))
        prior = JournalEntry.objects.filter(company=self.company, **{kind: source}).exclude(status='discarded').first()
        if prior:
            return {'id': prior.pk, 'already_saved': True, 'version': prior.version}
        journal, period, day = self.context(p)
        counter = scoped(Account, self.company, p.get('counter_account_id'))
        net = scoped(Account, self.company, p.get('net_account_id'))
        tax = scoped(Account, self.company, p.get('tax_account_id')) if source.tax else None
        require(counter.pk != net.pk and (tax is None or counter.pk != tax.pk), 'Le compte de tiers doit être distinct des comptes de montant HT et de taxe.')
        amounts = [(counter, source.total, kind == 'sale'), (net, source.subtotal, kind == 'purchase')]
        if tax:
            amounts.append((tax, source.tax, kind == 'purchase'))
        raw = [{'account_id': a.pk, 'debit': f'{amount // 100}.{amount % 100:02d}' if debit else 0,
                'credit': f'{amount // 100}.{amount % 100:02d}' if not debit else 0, 'label': snapshot['reference']}
               for a, amount, debit in amounts if amount]
        lines = self.normalized_lines(raw)
        entry = JournalEntry.objects.create(company=self.company, journal=journal, period=period, date=day,
                    memo=f"{'Vente' if kind == 'sale' else 'Achat'} · {snapshot['party']}", reference=snapshot['reference'],
                    source_snapshot=snapshot, created_by=self.actor, **{kind: source})
        self.write_lines(entry, lines)
        return {'id': entry.pk, 'version': entry.version}

    def post(self, p):
        entry = scoped(JournalEntry, self.company, p.get('id'))
        require(entry.status == 'draft', 'Seul un brouillon peut être comptabilisé.')
        self.check_version(entry, p)
        journal, _, _ = self.context({'journal_id': entry.journal_id, 'period_id': entry.period_id, 'date': entry.date.isoformat()})
        lines = list(EntryLine.objects.filter(company=self.company, entry=entry).select_related('account'))
        require(len(lines) >= 2 and sum(l.debit for l in lines) == sum(l.credit for l in lines) > 0,
                'L’écriture doit être équilibrée : total débit = total crédit, supérieur à zéro.')
        require(all(l.account.active for l in lines), 'Un compte de cette écriture est désactivé.')
        if entry.sale_id or entry.purchase_id:
            _, current = self.source('sale' if entry.sale_id else 'purchase', entry.sale_id or entry.purchase_id)
            require(current == entry.source_snapshot, 'La facture source a changé. Abandonnez ce brouillon et transférez-la à nouveau.')
        if entry.customer_payment_id or entry.supplier_payment_id:
            from .settlements import SettlementService
            SettlementService(self).validate_post(entry)
        if entry.reversal_of_id:
            from .settlements import ensure_can_reverse
            ensure_can_reverse(self.company, entry.reversal_of)
            require(entry.reversal_of.status == 'posted', 'L’écriture d’origine doit être comptabilisée.')
        for line in lines:
            line.account_code, line.account_name = line.account.code, line.account.name
            line.save(update_fields=['account_code', 'account_name'])
        entry.number, entry.journal_code = journal.next_number, journal.code
        journal.next_number += 1
        journal.save(update_fields=['next_number'])
        entry.status, entry.posted_at, entry.posted_by = 'posted', timezone.now(), self.actor
        entry.version += 1
        entry.save()
        return {'id': entry.pk, 'number': entry.number, 'journal_code': entry.journal_code, 'version': entry.version}

    def discard(self, p):
        entry = scoped(JournalEntry, self.company, p.get('id'))
        require(entry.status == 'draft', 'Seul un brouillon peut être abandonné.')
        self.check_version(entry, p)
        reason = label(p.get('reason'), 'Motif', limit=300)
        entry.status, entry.version = 'discarded', entry.version + 1
        entry.save(update_fields=['status', 'version'])
        return {'id': entry.pk, 'reason': reason}

    def reverse(self, p):
        original = scoped(JournalEntry, self.company, p.get('id'))
        require(original.status == 'posted' and not original.reversal_of_id, 'Choisissez une écriture comptabilisée d’origine.')
        prior = JournalEntry.objects.filter(company=self.company, reversal_of=original).exclude(status='discarded').first()
        if prior:
            return {'id': prior.pk, 'already_saved': True, 'version': prior.version}
        from .settlements import ensure_can_reverse
        ensure_can_reverse(self.company, original)
        journal, period, day = self.context(p)
        require(day >= original.date, 'La contrepassation ne peut pas précéder l’écriture d’origine.')
        reason = label(p.get('reason'), 'Motif', limit=260)
        entry = JournalEntry.objects.create(company=self.company, journal=journal, period=period, date=day,
                    memo=f'Contrepassation · {reason}', reference=f'{original.journal_code}-{original.number:06d}',
                    reversal_of=original, created_by=self.actor)
        rows = list(EntryLine.objects.filter(company=self.company, entry=original).select_related('account'))
        require(all(l.account.active for l in rows), 'Réactivez les comptes de l’écriture avant sa contrepassation.')
        self.write_lines(entry, [dict(account=l.account, account_code=l.account.code, account_name=l.account.name,
                               label=l.label, debit=l.credit, credit=l.debit) for l in rows])
        return {'id': entry.pk, 'version': entry.version}

    @transaction.atomic
    def state(self):
        Company.objects.select_for_update().get(pk=self.company.pk)
        from .settlements import SettlementService
        data = {key: list(model.objects.filter(company=self.company).order_by('id').values())
                for key, model in [('accounts', Account), ('journals', Journal), ('periods', AccountingPeriod),
                                   ('entries', JournalEntry), ('lines', EntryLine), ('matches', SettlementMatch)]}
        data['reconciliation'] = SettlementService(self).reconciliation()
        return data

    @transaction.atomic
    def reports(self, p):
        Company.objects.select_for_update().get(pk=self.company.pk)
        period = scoped(AccountingPeriod, self.company, p.get('period_id'))
        start = calendar_date(p.get('date_from') or period.start.isoformat(), 'Début du rapport')
        end = calendar_date(p.get('date_to') or period.end.isoformat(), 'Fin du rapport')
        require(period.start <= start <= end <= period.end, 'Choisissez une plage de dates comprise dans la période.')
        rows = EntryLine.objects.filter(company=self.company, entry__company=self.company, entry__status='posted',
                                       entry__period=period, entry__date__lte=end).select_related('entry', 'account').order_by('entry__date', 'entry__journal_code', 'entry__number', 'id')
        balance, ledger = {}, []
        for line in rows:
            e = line.entry
            account = balance.setdefault(line.account_id, {'account_id': line.account_id, 'code': line.account_code,
                    'name': line.account.name, 'opening': 0, 'debit': 0, 'credit': 0, 'closing': 0})
            net = line.debit - line.credit
            account['closing'] += net
            if e.date < start:
                account['opening'] += net
            else:
                account['debit'] += line.debit
                account['credit'] += line.credit
                ledger.append({'entry_id': e.pk, 'account_id': line.account_id, 'date': e.date,
                    'journal': e.journal_code, 'number': e.number, 'reference': e.reference, 'memo': e.memo,
                    'code': line.account_code, 'name': line.account_name, 'label': line.label,
                    'debit': line.debit, 'credit': line.credit, 'balance': account['closing']})
        trial = sorted(balance.values(), key=lambda x: x['code'])
        totals = {key: sum(row[key] for row in trial) for key in ('opening', 'debit', 'credit', 'closing')}
        return {'period_id': period.pk, 'period_name': period.name, 'date_from': start, 'date_to': end,
                'trial_balance': trial, 'ledger': ledger, 'totals': totals}
