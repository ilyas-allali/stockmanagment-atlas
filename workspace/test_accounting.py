import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from unittest import skipUnless

from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from server import ValidationError
from .accounting import AccountingService
from .models import (Account, AccountingPeriod, AuditEvent, Company, EntryLine, Journal, JournalEntry,
                     Membership, Organization, Product, Purchase, Sale, Supplier, User)
from .services import CommercialService


def setup_book(cls):
    cls.org = Organization.objects.create(name='Accounting test')
    cls.company = Company.objects.create(organization=cls.org, name='A')
    cls.other = Company.objects.create(organization=cls.org, name='B')
    cls.user = User.objects.create_user(username='accounting-owner', organization=cls.org, is_org_admin=True)
    cls.accounts = {code: Account.objects.create(company=cls.company, code=code, name=code) for code in ['AR', 'REV', 'TAX', 'AP', 'EXP', 'BANK']}
    cls.journal = Journal.objects.create(company=cls.company, code='GEN', name='Journal général')
    cls.period = AccountingPeriod.objects.create(company=cls.company, name='Période test', start=date(2026, 1, 1), end=date(2026, 12, 31))
    cls.product = Product.objects.create(company=cls.company, sku='P', name='Product', cost=100, price=1000, category='T', stock=50)
    cls.supplier = Supplier.objects.create(company=cls.company, name='Supplier')


class AccountingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_book(cls)

    def setUp(self):
        self.client.force_login(self.user)
        self.serial = 0

    def payload(self, **extra):
        self.serial += 1
        return dict({'request_key':f'acc-{self.serial}'}, **extra)

    def send(self, action, p, company=None):
        return self.client.post(f'/api/companies/{(company or self.company).pk}/{action}', json.dumps(p), content_type='application/json')

    def ok(self, action, p):
        r = self.send(action, p)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def context(self, **extra):
        return dict({'journal_id':self.journal.pk, 'period_id':self.period.pk, 'date':'2026-02-01'}, **extra)

    def manual(self, debit='12', credit='12', **extra):
        data = self.payload(**self.context(), memo='Manual', lines=[{'account_id':self.accounts['BANK'].pk, 'debit':debit},
                   {'account_id':self.accounts['AR'].pk, 'credit':credit}])
        data.update(extra)
        return JournalEntry.objects.get(pk=self.ok('accounting-entry', data)['id'])

    def sale(self):
        result = CommercialService(self.company,self.user).mutate('sales',self.payload(items=[{'product_id':self.product.pk,'quantity':1}],tax_bps=2000))
        return Sale.objects.get(pk=result['id'])

    def transfer(self, source, **extra):
        sale = isinstance(source, Sale)
        data = self.payload(**self.context(), kind='sale' if sale else 'purchase', source_id=source.pk,
                            counter_account_id=self.accounts['AR' if sale else 'AP'].pk,
                            net_account_id=self.accounts['REV' if sale else 'EXP'].pk, tax_account_id=self.accounts['TAX'].pk)
        data.update(extra)
        return JournalEntry.objects.get(pk=self.ok('accounting-transfer',data)['id'])

    def post(self, entry):
        data=self.payload(id=entry.pk,version=entry.version)
        result=self.ok('accounting-post',data)
        entry.refresh_from_db()
        return data,result

    def report(self, **extra):
        return AccountingService(self.company,self.user).reports(dict({'period_id':self.period.pk},**extra))

    def test_account_and_journal_create_edit_and_used_codes(self):
        account=self.ok('accounting-account',self.payload(code='test',name='Test'))
        self.assertEqual(account['code'],'TEST')
        self.assertEqual(self.send('accounting-account',self.payload(code='test',name='Duplicate')).status_code,400)
        self.assertEqual(self.send('accounting-account',self.payload(code='<bad>',name='Invalid')).status_code,400)
        journal=self.ok('accounting-journal',self.payload(code='od',name='Opérations diverses'))
        self.assertEqual(journal['code'],'OD')
        self.manual()
        self.assertEqual(self.send('accounting-account',self.payload(id=self.accounts['AR'].pk,code='CHANGED',name='No')).status_code,400)
        self.assertEqual(self.send('accounting-journal',self.payload(id=self.journal.pk,code='CHANGED',name='No')).status_code,400)
        self.ok('accounting-account',self.payload(id=self.accounts['AR'].pk,code='AR',name='Renamed'))

    def test_draft_unbalanced_edit_stale_and_posting_checks(self):
        entry=self.manual(debit='13',credit='12')
        self.assertEqual(self.report()['ledger'],[])
        self.assertEqual(self.send('accounting-post',self.payload(id=entry.pk,version=1)).status_code,400)
        self.journal.refresh_from_db();self.assertEqual(self.journal.next_number,1)
        self.manual(id=entry.pk,version=1)
        entry.refresh_from_db();self.assertEqual(entry.version,2)
        self.assertEqual(self.send('accounting-post',self.payload(id=entry.pk,version=1)).status_code,400)
        self.post(entry)
        self.assertEqual((entry.status,entry.number),('posted',1))
        self.assertEqual(self.send('accounting-discard',self.payload(id=entry.pk,version=entry.version,reason='No')).status_code,400)
        self.assertEqual(len(self.report()['ledger']),2)

    def test_sale_transfer_snapshots_and_deduplicates_without_changing_stock(self):
        source=self.sale();before=self.product.__class__.objects.get(pk=self.product.pk).stock
        entry=self.transfer(source);again=self.transfer(source)
        self.assertEqual(entry.pk,again.pk)
        rows=list(entry.entryline_set.order_by('id'))
        self.assertEqual([(r.account.code,r.debit,r.credit) for r in rows],[('AR',1200,0),('REV',0,1000),('TAX',0,200)])
        self.assertEqual(entry.source_snapshot['total'],1200)
        self.product.refresh_from_db();self.assertEqual(self.product.stock,before)
        self.post(entry)
        self.assertEqual(self.report()['totals'],{'opening':0,'debit':1200,'credit':1200,'closing':0})

    def test_purchase_transfer_requires_receipt_and_debits_expense_and_tax(self):
        service=CommercialService(self.company,self.user)
        p=service.mutate('purchases',self.payload(supplier_id=self.supplier.pk,supplier_reference='P-1',invoice_date='2026-01-20',items=[{'product_id':self.product.pk,'quantity':2,'price':'5','tax_bps':2000}]))
        purchase=Purchase.objects.get(pk=p['id'])
        invalid=self.payload(**self.context(),kind='purchase',source_id=purchase.pk)
        self.assertEqual(self.send('accounting-transfer',invalid).status_code,400)
        service.mutate('purchase-receive',self.payload(purchase_id=purchase.pk,version=1))
        purchase.refresh_from_db();entry=self.transfer(purchase)
        rows=list(entry.entryline_set.order_by('id'))
        self.assertEqual([(r.account.code,r.debit,r.credit) for r in rows],[('AP',0,1200),('EXP',1000,0),('TAX',200,0)])
        self.post(entry)

    def test_cancel_source_requires_discard_or_posted_reversal(self):
        source=self.sale();entry=self.transfer(source)
        self.assertEqual(self.send('cancel',{'sale_id':source.pk}).status_code,400)
        self.ok('accounting-discard',self.payload(id=entry.pk,version=entry.version,reason='Wrong mapping'))
        replacement=self.transfer(source)
        self.assertNotEqual(entry.pk,replacement.pk)
        self.post(replacement)
        reverse=self.ok('accounting-reverse',self.payload(id=replacement.pk,reason='Cancel source',**self.context()))
        self.assertEqual(self.send('cancel',{'sale_id':source.pk}).status_code,400)
        reversal=JournalEntry.objects.get(pk=reverse['id']);self.post(reversal)
        self.assertEqual(self.send('cancel',{'sale_id':source.pk}).status_code,200)
        self.assertEqual(self.report()['totals']['closing'],0)
        self.assertTrue(all(row['closing']==0 for row in self.report()['trial_balance']))
        self.assertEqual(JournalEntry.objects.get(pk=replacement.pk).status,'posted')

    def test_post_rechecks_source_and_active_accounts(self):
        sale=self.sale();entry=self.transfer(sale)
        Sale.objects.filter(pk=sale.pk).update(subtotal=999)
        self.assertEqual(self.send('accounting-post',self.payload(id=entry.pk,version=entry.version)).status_code,400)
        manual=self.manual()
        Account.objects.filter(pk=self.accounts['AR'].pk).update(active=False)
        self.assertEqual(self.send('accounting-post',self.payload(id=manual.pk,version=manual.version)).status_code,400)

    def test_period_overlap_close_pending_drafts_and_reopen(self):
        self.assertEqual(self.send('accounting-period',self.payload(name='Overlap',start='2026-12-31',end='2027-01-01')).status_code,400)
        self.ok('accounting-period',self.payload(name='Next',start='2027-01-01',end='2027-12-31'))
        entry=self.manual()
        data=self.payload(id=self.period.pk,closed=True,expected_closed=False,reason='Period complete')
        self.assertEqual(self.send('accounting-period-state',data).status_code,400)
        self.post(entry)
        self.ok('accounting-period-state',data)
        invalid=self.payload(**self.context(),memo='Closed',lines=[])
        self.assertEqual(self.send('accounting-entry',invalid).status_code,400)
        self.ok('accounting-period-state',self.payload(id=self.period.pk,closed=False,expected_closed=True,reason='Approved correction'))
        self.assertEqual(self.send('accounting-period-state',data).status_code,200)  # Exact retry has no second effect.
        self.period.refresh_from_db();self.assertFalse(self.period.closed)

    def test_reversal_is_unique_balanced_and_can_use_new_period(self):
        entry=self.manual();self.post(entry)
        self.ok('accounting-period-state',self.payload(id=self.period.pk,closed=True,expected_closed=False,reason='Close'))
        next_period=AccountingPeriod.objects.create(company=self.company,name='Next',start=date(2027,1,1),end=date(2027,12,31))
        data=self.payload(id=entry.pk,journal_id=self.journal.pk,period_id=next_period.pk,date='2027-01-02',reason='Correction')
        r=self.ok('accounting-reverse',data)
        again=self.ok('accounting-reverse',dict(data,request_key='other-reverse-key'))
        self.assertEqual(r['id'],again['id'])
        reversal=JournalEntry.objects.get(pk=r['id']);self.post(reversal)
        self.assertEqual(reversal.reversal_of_id,entry.pk)
        self.assertEqual(self.report()['totals']['debit'],1200)
        self.assertEqual(AccountingService(self.company,self.user).reports({'period_id':next_period.pk})['totals']['debit'],1200)

    def test_reports_include_opening_running_balances_and_only_posted_dates(self):
        opening=self.manual(date='2026-01-01',debit='10',credit='10');self.post(opening)
        feb=self.manual(date='2026-02-10',debit='7',credit='7');self.post(feb)
        self.manual(date='2026-02-15',debit='99',credit='99')
        future=self.manual(date='2026-03-01',debit='8',credit='8');self.post(future)
        report=self.report(date_from='2026-02-01',date_to='2026-02-28')
        bank=next(r for r in report['trial_balance'] if r['code']=='BANK')
        self.assertEqual((bank['opening'],bank['debit'],bank['credit'],bank['closing']),(1000,700,0,1700))
        self.assertEqual(next(r for r in report['ledger'] if r['code']=='BANK')['balance'],1700)
        self.assertEqual(report['totals'],{'opening':0,'debit':700,'credit':700,'closing':0})
        self.assertEqual(len(report['ledger']),2)
        with self.assertRaises(ValidationError):self.report(date_from='2025-01-01')

    def test_account_name_snapshot_survives_rename(self):
        entry=self.manual();self.post(entry)
        self.ok('accounting-account',self.payload(id=self.accounts['AR'].pk,code='AR',name='New name'))
        self.assertEqual(entry.entryline_set.get(account=self.accounts['AR']).account_name,'AR')

    def test_exact_retry_and_payload_conflict(self):
        entry=self.manual();data,result=self.post(entry)
        self.assertEqual(self.ok('accounting-post',data),result)
        self.assertEqual(self.send('accounting-post',dict(data,version=999)).status_code,400)
        self.journal.refresh_from_db();self.assertEqual(self.journal.next_number,2)
        self.assertEqual(AuditEvent.objects.filter(company=self.company,action='accounting-post').count(),1)

    def test_role_boundaries_and_exports(self):
        entry=self.manual(reference='=SUM(1)');self.post(entry)
        user=User.objects.create_user(username='accounting-viewer',organization=self.org)
        member=Membership.objects.create(company=self.company,user=user,role='viewer')
        self.client.force_login(user)
        url=f'/api/companies/{self.company.pk}/accounting/'
        self.assertEqual(self.client.get(url+'state').status_code,200)
        self.assertEqual(self.client.get(url+'reports',{'period_id':self.period.pk}).status_code,200)
        self.assertEqual(self.client.get(url+'export',{'period_id':self.period.pk}).status_code,403)
        for action in ['accounting-entry','accounting-transfer','accounting-post','accounting-reverse','accounting-period-state','accounting-account']:
            self.assertEqual(self.send(action,{}).status_code,403)
        member.role='commercial';member.save()
        self.assertEqual(self.client.get(url+'state').status_code,403)
        member.role='accountant';member.save()
        self.assertEqual(self.send('accounting-account',self.payload(code='NEW',name='New')).status_code,200)
        response=self.client.get(url+'export',{'period_id':self.period.pk,'report':'journal'})
        self.assertEqual(response.status_code,200);self.assertIn("'=SUM(1)",response.content.decode())
        self.assertEqual(self.client.get(f'/api/companies/{self.other.pk}/accounting/state').status_code,404)
        self.client.logout();self.assertEqual(self.client.get(url+'state').status_code,401)

    def test_all_foreign_ids_are_company_scoped(self):
        other_account=Account.objects.create(company=self.other,code='OTHER',name='Other')
        other_journal=Journal.objects.create(company=self.other,code='OTHER',name='Other')
        other_period=AccountingPeriod.objects.create(company=self.other,name='Other',start=date(2026,1,1),end=date(2026,12,31))
        entry=self.manual()
        for action,p in [('accounting-post',{'id':entry.pk,'version':1}),('accounting-discard',{'id':entry.pk,'version':1,'reason':'No'}),
                         ('accounting-reverse',{'id':entry.pk}),('accounting-account',{'id':self.accounts['AR'].pk,'code':'AR','name':'No'})]:
            self.assertEqual(self.send(action,self.payload(**p),self.other).status_code,400)
        for change in [{'journal_id':other_journal.pk},{'period_id':other_period.pk},
                       {'lines':[{'account_id':other_account.pk,'debit':1},{'account_id':self.accounts['AR'].pk,'credit':1}]}]:
            p=self.payload(**self.context(),memo='Invalid',lines=[{'account_id':self.accounts['BANK'].pk,'debit':1},{'account_id':self.accounts['AR'].pk,'credit':1}]);p.update(change)
            self.assertEqual(self.send('accounting-entry',p).status_code,400)
        self.assertEqual(self.client.get(f'/api/companies/{self.company.pk}/accounting/reports',{'period_id':other_period.pk}).status_code,400)

    def test_invalid_lines_dates_and_zero_invoice(self):
        base=self.payload(**self.context(),memo='Bad')
        for lines in [[],[{}],[None,{}],[{'account_id':self.accounts['AR'].pk,'debit':1,'credit':1}]*2,
                      [{'account_id':self.accounts['AR'].pk,'debit':'1.001'}]*2]:
            self.assertEqual(self.send('accounting-entry',dict(base,lines=lines)).status_code,400)
        self.assertFalse(JournalEntry.objects.exists())
        self.assertEqual(self.send('accounting-period',self.payload(name='Bad',start='no',end='2026-01-01')).status_code,400)

    @skipUnless(connection.vendor=='postgresql','PostgreSQL constraints and immutability')
    def test_database_posted_entries_lines_and_relationships_are_protected(self):
        entry=self.manual()
        other_account=Account.objects.create(company=self.other,code='OTHER',name='Other')
        with self.assertRaises(IntegrityError),transaction.atomic():
            entry.entryline_set.update(account=other_account)
        self.post(entry)
        with self.assertRaises(IntegrityError),transaction.atomic():JournalEntry.objects.filter(pk=entry.pk).update(memo='Rewrite')
        with self.assertRaises(IntegrityError),transaction.atomic():entry.entryline_set.update(debit=999)
        with self.assertRaises(IntegrityError),transaction.atomic():entry.entryline_set.all().delete()
        with self.assertRaises(IntegrityError),transaction.atomic():
            EntryLine.objects.create(company=self.company,entry=entry,account=self.accounts['AR'],account_code='AR',account_name='AR',debit=1)
        draft=self.manual(debit='13',credit='12')
        with self.assertRaises(IntegrityError),transaction.atomic():
            JournalEntry.objects.filter(pk=draft.pk).update(status='posted',number=2,journal_code='GEN',posted_by=self.user,posted_at=timezone.now())


@skipUnless(connection.vendor=='postgresql','Requires PostgreSQL row locks')
class ConcurrentAccountingTests(TransactionTestCase):
    def test_concurrent_transfer_and_post_are_once_only(self):
        setup_book(self)
        sale=CommercialService(self.company,self.user).mutate('sales',{'request_key':'sale','items':[{'product_id':self.product.pk,'quantity':1}]})
        def run(args):
            close_old_connections()
            try:return CommercialService(self.company,self.user).mutate(*args)
            finally:close_old_connections()
        base={'kind':'sale','source_id':sale['id'],'journal_id':self.journal.pk,'period_id':self.period.pk,'date':'2026-02-01',
              'counter_account_id':self.accounts['AR'].pk,'net_account_id':self.accounts['REV'].pk}
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows=list(pool.map(run,[('accounting-transfer',dict(base,request_key=k)) for k in ['transfer-1','transfer-2']]))
        self.assertEqual(rows[0]['id'],rows[1]['id']);self.assertEqual(JournalEntry.objects.count(),1)
        post={'id':rows[0]['id'],'version':1,'request_key':'post'}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(run,[('accounting-post',post)]*2))
        self.assertEqual(results[0],results[1])
        self.journal.refresh_from_db();self.assertEqual(self.journal.next_number,2)
