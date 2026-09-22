from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless

from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from .accounting import AccountingService
from .models import (Account, AuditEvent, JournalEntry, Membership, Payment,
                     Purchase, Sale, SettlementMatch, SupplierPayment, User)
from .services import CommercialService
from . import test_accounting as fixtures


class SettlementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.setup_book(cls)

    setUp = fixtures.AccountingTests.setUp
    payload = fixtures.AccountingTests.payload
    send = fixtures.AccountingTests.send
    ok = fixtures.AccountingTests.ok
    context = fixtures.AccountingTests.context
    sale = fixtures.AccountingTests.sale
    transfer = fixtures.AccountingTests.transfer
    post = fixtures.AccountingTests.post
    report = fixtures.AccountingTests.report

    def pay(self, source, amount='5'):
        customer = isinstance(source, Sale)
        p = self.payload(amount=amount, method='Virement')
        p.update({'sale_id': source.pk} if customer else {'purchase_id': source.pk, 'payment_date':'2026-02-01', 'reference':'PAY-1'})
        self.ok('payments' if customer else 'supplier-payments', p)
        return (Payment if customer else SupplierPayment).objects.latest('id')

    def payment_transfer(self, payment, **extra):
        p = self.payload(**self.context(), kind='customer_payment' if isinstance(payment, Payment) else 'supplier_payment',
                         source_id=payment.pk, cash_account_id=self.accounts['BANK'].pk)
        p.update(extra)
        return JournalEntry.objects.get(pk=self.ok('accounting-payment-transfer', p)['id'])

    def prepared(self, amount='5'):
        source = self.sale()
        invoice = self.transfer(source)
        self.post(invoice)
        payment = self.pay(source, amount)
        entry = self.payment_transfer(payment)
        return source, invoice, payment, entry

    def match(self, entry):
        return self.ok('accounting-match', self.payload(payment_entry_id=entry.pk))

    def reverse(self, entry):
        return self.send('accounting-reverse', self.payload(id=entry.pk, reason='Correction', **self.context()))

    def summary(self):
        return AccountingService(self.company, self.user).state()['reconciliation'][0]

    def test_partial_then_full_customer_payment_matching(self):
        source, invoice, payment, entry = self.prepared()
        self.assertEqual([(l.account.code,l.debit,l.credit) for l in entry.entryline_set.order_by('id')], [('BANK',500,0),('AR',0,500)])
        self.assertEqual(self.summary()['payment_gap'],500)
        self.assertEqual(self.send('accounting-match',self.payload(payment_entry_id=entry.pk)).status_code,400)
        self.post(entry)
        self.assertEqual(self.summary()['accounting_remaining'],700)
        self.assertEqual(self.summary()['matched'],0)
        m=self.match(entry)
        self.assertEqual(self.match(entry)['id'],m['id'])
        self.assertEqual(self.summary()['matched'],500)
        second=self.payment_transfer(self.pay(source,'7'));self.post(second);self.match(second)
        row=self.summary()
        self.assertEqual((row['paid'],row['posted_payments'],row['matched'],row['payment_gap'],row['accounting_remaining']),(1200,1200,1200,0,0))
        self.assertEqual(next(r for r in self.report()['trial_balance'] if r['code']=='AR')['closing'],0)
        source.refresh_from_db();self.product.refresh_from_db()
        self.assertEqual((source.paid,self.product.stock),(1200,49))

    def test_supplier_payment_uses_invoice_payable_account(self):
        result=self.ok('purchases',self.payload(supplier_id=self.supplier.pk,supplier_reference='S-1',invoice_date='2026-01-20',items=[{'product_id':self.product.pk,'quantity':2,'price':'5','tax_bps':2000}]))
        self.ok('purchase-receive',self.payload(purchase_id=result['id'],version=1))
        source=Purchase.objects.get(pk=result['id']);invoice=self.transfer(source);self.post(invoice)
        payment=self.pay(source,'12');entry=self.payment_transfer(payment)
        self.assertEqual([(l.account.code,l.debit,l.credit) for l in entry.entryline_set.order_by('id')],[('BANK',0,1200),('AP',1200,0)])
        self.post(entry);self.match(entry)
        self.assertEqual(self.summary()['accounting_remaining'],0)
        self.assertEqual(self.summary()['matched'],1200)

    def test_payment_requires_posted_invoice_and_valid_cash_date_period(self):
        source=self.sale();payment=self.pay(source)
        base=dict(kind='customer_payment',source_id=payment.pk,cash_account_id=self.accounts['BANK'].pk,**self.context())
        self.assertEqual(self.send('accounting-payment-transfer',self.payload(**base)).status_code,400)
        invoice=self.transfer(source)
        self.assertEqual(self.send('accounting-payment-transfer',self.payload(**base)).status_code,400)
        self.post(invoice)
        for change in [dict(cash_account_id=self.accounts['AR'].pk),dict(date='2026-01-01'),dict(date='2027-01-01'),dict(kind='sale')]:
            self.assertEqual(self.send('accounting-payment-transfer',self.payload(**dict(base,**change))).status_code,400)
        Account.objects.filter(pk=self.accounts['BANK'].pk).update(active=False)
        self.assertEqual(self.send('accounting-payment-transfer',self.payload(**base)).status_code,400)
        Account.objects.filter(pk=self.accounts['BANK'].pk).update(active=True)
        self.period.closed=True;self.period.save()
        self.assertEqual(self.send('accounting-payment-transfer',self.payload(**base)).status_code,400)

    def test_post_revalidates_payment_snapshot(self):
        _,_,payment,entry=self.prepared()
        Payment.objects.filter(pk=payment.pk).update(amount=499)
        self.assertEqual(self.send('accounting-post',self.payload(id=entry.pk,version=1)).status_code,400)
        self.assertEqual(JournalEntry.objects.get(pk=entry.pk).status,'draft')

    def test_deduplicate_discard_and_prevent_manual_edit(self):
        _,_,payment,entry=self.prepared()
        self.assertEqual(self.payment_transfer(payment).pk,entry.pk)
        self.assertEqual(self.send('accounting-entry',self.payload(id=entry.pk,version=1,memo='Tamper',**self.context(),lines=[{'account_id':self.accounts['BANK'].pk,'debit':'5'},{'account_id':self.accounts['AR'].pk,'credit':'5'}])).status_code,400)
        self.ok('accounting-discard',self.payload(id=entry.pk,version=1,reason='Wrong bank'))
        self.assertNotEqual(self.payment_transfer(payment).pk,entry.pk)

    def test_unmatch_reverse_then_retransfer_preserves_history(self):
        _,invoice,payment,entry=self.prepared();self.post(entry)
        m=self.match(entry)
        self.assertEqual(self.reverse(entry).status_code,400)
        self.assertEqual(self.reverse(invoice).status_code,400)
        request=self.payload(id=m['id'],reason='Wrong bank')
        result=self.ok('accounting-unmatch',request)
        self.assertEqual(self.ok('accounting-unmatch',request),result)
        self.assertEqual(AuditEvent.objects.filter(action='accounting-unmatch').count(),1)
        reverse=self.reverse(entry);self.assertEqual(reverse.status_code,200,reverse.content)
        self.assertEqual(self.send('accounting-match',self.payload(payment_entry_id=entry.pk)).status_code,400)
        self.assertEqual(self.reverse(invoice).status_code,400)
        reversal=JournalEntry.objects.get(pk=reverse.json()['id']);self.post(reversal)
        self.assertEqual(self.summary()['posted_payments'],0)
        replacement=self.payment_transfer(payment);self.assertNotEqual(replacement.pk,entry.pk)
        self.post(replacement);self.match(replacement)
        self.assertEqual(self.summary()['posted_payments'],500)
        self.assertEqual(SettlementMatch.objects.count(),2)
        self.assertEqual(SettlementMatch.objects.filter(voided_at__isnull=False).get().void_reason,'Wrong bank')

    def test_invoice_reversal_blocks_payment_transfer_until_abandoned(self):
        sale=self.sale();invoice=self.transfer(sale);self.post(invoice);payment=self.pay(sale)
        reversal=self.reverse(invoice);self.assertEqual(reversal.status_code,200)
        data=self.payload(**self.context(),kind='customer_payment',source_id=payment.pk,cash_account_id=self.accounts['BANK'].pk)
        self.assertEqual(self.send('accounting-payment-transfer',data).status_code,400)
        self.ok('accounting-discard',self.payload(id=reversal.json()['id'],version=1,reason='Keep invoice'))
        self.assertEqual(self.send('accounting-payment-transfer',data).status_code,200)

    def test_unmatch_can_be_reviewed_after_period_closes(self):
        _,_,_,entry=self.prepared();self.post(entry);m=self.match(entry)
        self.ok('accounting-period-state',self.payload(id=self.period.pk,closed=True,expected_closed=False,reason='Reviewed'))
        self.ok('accounting-unmatch',self.payload(id=m['id'],reason='Review allocation'))
        self.match(entry)  # Matching changes no dated ledger lines.
        self.assertEqual(self.summary()['matched'],500)

    def test_permissions_company_isolation_export_and_backup(self):
        source,_,payment,entry=self.prepared();self.post(entry);m=self.match(entry)
        Sale.objects.filter(pk=source.pk).update(customer_name='=danger')
        url=f'/api/companies/{self.company.pk}/accounting/'
        response=self.client.get(url+'reconciliation-export');self.assertEqual(response.status_code,200)
        self.assertIn("'=danger",response.content.decode())
        backup=self.client.get(f'/api/companies/{self.company.pk}/backup').json()
        self.assertEqual(backup['version'],5);self.assertEqual(len(backup['accounting']['matches']),1)
        self.assertEqual(self.client.get(f'/api/companies/{self.other.pk}/accounting/state').json()['matches'],[])
        for action,p in [('accounting-payment-transfer',dict(kind='customer_payment',source_id=payment.pk)),('accounting-match',dict(payment_entry_id=entry.pk)),('accounting-unmatch',dict(id=m['id'],reason='Bad'))]:
            self.assertEqual(self.send(action,self.payload(**p),self.other).status_code,400)
        self.ok('accounting-unmatch',self.payload(id=m['id'],reason='Review'))
        user=User.objects.create_user(username='settlement-reader',organization=self.org)
        member=Membership.objects.create(company=self.company,user=user,role='viewer');self.client.force_login(user)
        self.assertEqual(self.client.get(url+'state').status_code,200)
        self.assertEqual(self.client.get(url+'reconciliation-export').status_code,403)
        for role in ['viewer','commercial','supervisor']:
            member.role=role;member.save()
            for action in ['accounting-payment-transfer','accounting-match','accounting-unmatch']:
                self.assertEqual(self.send(action,{}).status_code,403)
        member.role='accountant';member.save()
        self.assertEqual(self.client.get(url+'reconciliation-export').status_code,200)
        self.assertEqual(self.send('accounting-match',self.payload(payment_entry_id=entry.pk)).status_code,400)  # Invoice source was changed.

    def test_centime_precision_and_match_cannot_exceed_invoice(self):
        source, invoice, payment, entry=self.prepared('0.01');self.post(entry);self.match(entry)
        self.assertEqual(self.summary()['matched'],1)
        # Imported/corrupted commercial data must not permit overmatching the invoice.
        for amount in [1199,1]:
            payment=Payment.objects.create(company=self.company,sale=source,amount=amount,created_at=timezone.now(),method='Virement')
            entry=self.payment_transfer(payment);self.post(entry)
            response=self.send('accounting-match',self.payload(payment_entry_id=entry.pk))
            self.assertEqual(response.status_code,200 if amount==1199 else 400)
        self.assertEqual(self.summary()['matched'],1200)

    def test_foreign_cash_and_changed_retry_payload_are_rejected(self):
        source=self.sale();invoice=self.transfer(source);self.post(invoice);payment=self.pay(source)
        foreign=Account.objects.create(company=self.other,code='FOREIGN',name='Other bank')
        data=self.payload(**self.context(),kind='customer_payment',source_id=payment.pk,cash_account_id=foreign.pk)
        self.assertEqual(self.send('accounting-payment-transfer',data).status_code,400)
        data['cash_account_id']=self.accounts['BANK'].pk
        result=self.ok('accounting-payment-transfer',data)
        self.assertEqual(self.ok('accounting-payment-transfer',data),result)
        self.assertEqual(self.send('accounting-payment-transfer',dict(data,date='2026-02-02')).status_code,400)
        self.assertEqual(AuditEvent.objects.filter(action='accounting-payment-transfer').count(),1)

    @skipUnless(connection.vendor=='postgresql','PostgreSQL guards')
    def test_database_guards_protect_duplicates_match_history_and_source_links(self):
        _,invoice,payment,entry=self.prepared()
        base=dict(company=self.company,journal=self.journal,period=self.period,date='2026-02-01',memo='Duplicate',customer_payment=payment,settlement_invoice=invoice,created_by=self.user)
        with self.assertRaises(IntegrityError),transaction.atomic():JournalEntry.objects.create(**base)
        self.post(entry)
        with self.assertRaises(IntegrityError),transaction.atomic():SettlementMatch.objects.create(company=self.other,invoice_entry=invoice,payment_entry=entry,amount=500,created_by=self.user)
        with self.assertRaises(IntegrityError),transaction.atomic():SettlementMatch.objects.create(company=self.company,invoice_entry=invoice,payment_entry=entry,amount=501,created_by=self.user)
        m=self.match(entry);match=SettlementMatch.objects.get(pk=m['id'])
        with self.assertRaises(IntegrityError),transaction.atomic():SettlementMatch.objects.filter(pk=match.pk).update(amount=499)
        with self.assertRaises(IntegrityError),transaction.atomic():match.delete()
        with self.assertRaises(IntegrityError),transaction.atomic():
            JournalEntry.objects.create(company=self.company,journal=self.journal,period=self.period,date='2026-02-01',memo='Reverse matched',reversal_of=entry,created_by=self.user)
        self.ok('accounting-unmatch',self.payload(id=match.pk,reason='Correction'))
        with self.assertRaises(IntegrityError),transaction.atomic():SettlementMatch.objects.filter(pk=match.pk).update(void_reason='Rewrite history')

    @skipUnless(connection.vendor=='postgresql','PostgreSQL guards')
    def test_posting_rejects_tampered_payment_lines(self):
        _,_,_,entry=self.prepared()
        other=Account.objects.create(company=self.company,code='CASH',name='Cash')
        entry.entryline_set.filter(account=self.accounts['AR']).update(account=other)
        self.assertEqual(self.send('accounting-post',self.payload(id=entry.pk,version=1)).status_code,400)


@skipUnless(connection.vendor=='postgresql','Requires PostgreSQL locks')
class ConcurrentSettlementTests(TransactionTestCase):
    def test_concurrent_transfer_and_matching_are_once_only(self):
        fixtures.setup_book(self)
        service=CommercialService(self.company,self.user)
        def mutate(action,**p):
            return service.mutate(action,dict(request_key=action,**p))
        sale=mutate('sales',items=[{'product_id':self.product.pk,'quantity':1}])
        context=dict(journal_id=self.journal.pk,period_id=self.period.pk,date='2026-02-01')
        invoice=mutate('accounting-transfer',kind='sale',source_id=sale['id'],counter_account_id=self.accounts['AR'].pk,net_account_id=self.accounts['REV'].pk,**context)
        mutate('accounting-post',id=invoice['id'],version=1)
        mutate('payments',sale_id=sale['id'],amount='5')
        payment=Payment.objects.get(sale_id=sale['id'])
        def run(args):
            close_old_connections()
            try:return CommercialService(self.company,self.user).mutate(*args)
            finally:close_old_connections()
        base=dict(kind='customer_payment',source_id=payment.pk,cash_account_id=self.accounts['BANK'].pk,**context)
        with ThreadPoolExecutor(max_workers=2) as pool:
            transfers=list(pool.map(run,[('accounting-payment-transfer',dict(base,request_key=f'transfer-{i}')) for i in range(2)]))
        self.assertEqual(transfers[0]['id'],transfers[1]['id'])
        entry_id=transfers[0]['id']
        service.mutate('accounting-post',dict(id=entry_id,version=1,request_key='payment-post'))
        with ThreadPoolExecutor(max_workers=2) as pool:
            matches=list(pool.map(run,[('accounting-match',dict(payment_entry_id=entry_id,request_key=f'match-{i}')) for i in range(2)]))
        self.assertEqual(matches[0]['id'],matches[1]['id']);self.assertEqual(SettlementMatch.objects.count(),1)
