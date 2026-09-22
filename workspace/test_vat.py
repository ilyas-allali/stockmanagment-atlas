from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest import skipUnless

from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.core.management import call_command, CommandError
from django.utils import timezone
from . import test_accounting as fixtures
from .models import AuditEvent, Membership, Payment, Purchase, Sale, User, VatWorksheet
from .services import CommercialService
from .vat import VatService, fingerprint


class VatTests(TestCase):
    @classmethod
    def setUpTestData(cls):fixtures.setup_book(cls)
    setUp=fixtures.AccountingTests.setUp
    payload=fixtures.AccountingTests.payload
    send=fixtures.AccountingTests.send
    ok=fixtures.AccountingTests.ok

    def sheet(self, **extra):
        p=self.payload(start='2026-02-01',cadence='monthly',sales_basis='invoices',purchase_basis='invoices');p.update(extra)
        return VatWorksheet.objects.get(pk=self.ok('vat-create',p)['id'])

    def change(self, action, sheet, **extra):
        sheet.refresh_from_db()
        result=self.ok(action,self.payload(id=sheet.pk,version=sheet.version,**extra));sheet.refresh_from_db();return result

    def sale(self, day='2026-02-05'):
        r=self.ok('sales',self.payload(items=[{'product_id':self.product.pk,'quantity':1}],tax_bps=2000))
        Sale.objects.filter(pk=r['id']).update(created_at=timezone.make_aware(datetime.fromisoformat(day+'T12:00:00')))
        return Sale.objects.get(pk=r['id'])

    def pay(self, sale, amount, day):
        self.ok('payments',self.payload(sale_id=sale.pk,amount=amount,method='Virement'))
        payment=Payment.objects.latest('id')
        Payment.objects.filter(pk=payment.pk).update(created_at=timezone.make_aware(datetime.fromisoformat(day+'T12:00:00')))
        return payment

    def import_all(self,sheet):self.change('vat-import',sheet)
    def review(self,sheet,row,amount):self.change('vat-line',sheet,key=row['key'],retained_tax=amount,reason='Traitement vérifié')
    def approve(self,sheet):return self.change('vat-approve',sheet,confirmed=True)
    def manual(self,sheet,**extra):
        p=dict(direction='purchase',date=sheet.start.isoformat(),reference='MAN-1',party='Fournisseur externe',net='10',tax='2',retained_tax='1',reason='Déduction partielle justifiée');p.update(extra)
        return self.change('vat-line',sheet,**p)

    def test_import_review_totals_credit_approval_and_frozen_export(self):
        self.sale();sheet=self.sheet();self.import_all(sheet)
        self.assertEqual((sheet.lines[0]['tax'],sheet.lines[0]['retained_tax'],sheet.lines[0]['reviewed']),(200,0,False))
        self.assertEqual(self.send('vat-approve',self.payload(id=sheet.pk,version=sheet.version,confirmed=True)).status_code,400)
        self.review(sheet,sheet.lines[0],'2');self.manual(sheet)
        self.change('vat-settings',sheet,opening_credit='0.50',credit_note='Crédit validé janvier',note='Revue de février')
        self.approve(sheet)
        self.assertEqual(sheet.approved_snapshot['totals'],dict(sales_tax=200,deductible_tax=100,opening_credit=50,payable=50,carryforward=0,pending=0))
        self.assertEqual(fingerprint(sheet.approved_snapshot),sheet.checksum)
        old=sheet.approved_snapshot
        self.company.name='Changed later';self.company.save()
        url=f'/api/companies/{self.company.pk}/vat/export'
        response=self.client.get(url,{'id':sheet.pk,'format':'json'});self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['snapshot'],old)
        self.assertEqual(self.client.get(url,{'id':sheet.pk,'format':'xml'}).status_code,400)
        self.assertEqual(self.send('vat-line',self.payload(id=sheet.pk,version=sheet.version)).status_code,400)

    def test_partial_payment_rounding_across_periods_deduplicates(self):
        sale=self.sale();self.pay(sale,'5','2026-02-10');self.pay(sale,'7','2026-03-10')
        feb=self.sheet(sales_basis='payments');march=self.sheet(start='2026-03-01',sales_basis='payments')
        self.import_all(feb);self.import_all(feb);self.import_all(march)
        self.assertEqual(len(feb.lines),1)
        self.assertEqual((feb.lines[0]['tax'],march.lines[0]['tax']),(83,117))
        self.assertEqual((feb.lines[0]['net'],march.lines[0]['net']),(417,583))
        self.review(feb,feb.lines[0],'0.83');self.approve(feb)
        self.review(march,march.lines[0],'1.17');self.approve(march)

    def test_purchase_candidates_require_receipt_and_never_assume_deductibility(self):
        r=self.ok('purchases',self.payload(supplier_id=self.supplier.pk,supplier_reference='P-VAT',invoice_date='2026-02-03',items=[{'product_id':self.product.pk,'quantity':1,'price':'10','tax_bps':2000}]))
        sheet=self.sheet();self.import_all(sheet);self.assertEqual(sheet.lines,[])
        self.ok('purchase-receive',self.payload(purchase_id=r['id'],version=1))
        self.import_all(sheet);self.assertEqual(sheet.lines[0]['direction'],'purchase');self.assertEqual(sheet.lines[0]['retained_tax'],0)
        self.review(sheet,sheet.lines[0],'0');self.approve(sheet)
        self.assertEqual(sheet.approved_snapshot['totals']['deductible_tax'],0)

    def test_sources_changed_missing_and_cancelled_block_approval(self):
        sale=self.sale();sheet=self.sheet();self.import_all(sheet);self.review(sheet,sheet.lines[0],'2')
        Sale.objects.filter(pk=sale.pk).update(customer_name='Updated customer')
        self.assertEqual(self.send('vat-approve',self.payload(id=sheet.pk,version=sheet.version,confirmed=True)).status_code,400)
        self.import_all(sheet);self.assertFalse(sheet.lines[0]['reviewed']);self.review(sheet,sheet.lines[0],'2')
        self.sale();self.assertEqual(self.send('vat-approve',self.payload(id=sheet.pk,version=sheet.version,confirmed=True)).status_code,400)
        self.import_all(sheet)
        self.ok('cancel',{'sale_id':sale.pk})
        self.assertEqual(self.send('vat-approve',self.payload(id=sheet.pk,version=sheet.version,confirmed=True)).status_code,400)
        self.change('vat-remove',sheet,key=f'sale:{sale.pk}',reason='Facture annulée')
        self.review(sheet,sheet.lines[0],'2');self.approve(sheet)

    def test_overlap_calendar_bounds_discard_and_replacement(self):
        sheet=self.sheet()
        for change in [dict(start='2026-02-15'),dict(start='2026-02-01',cadence='quarterly'),dict(start='2026-01-01',cadence='quarterly'),dict(start='2026-02-01')]:
            base=self.payload(start='2026-02-01',cadence='monthly',sales_basis='invoices',purchase_basis='payments');base.update(change)
            self.assertEqual(self.send('vat-create',base).status_code,400)
        self.change('vat-void',sheet,reason='Mauvaise base');self.assertEqual(sheet.status,'discarded')
        replacement=self.sheet();self.assertNotEqual(replacement.pk,sheet.pk)
        quarter=self.sheet(start='2026-04-01',cadence='quarterly');self.assertEqual(str(quarter.end),'2026-06-30')

    def test_invoice_and_payment_bases_cannot_double_recognize_tax(self):
        sale=self.sale(day='2026-01-05');self.pay(sale,'12','2026-02-10')
        january=self.sheet(start='2026-01-01');self.import_all(january);self.review(january,january.lines[0],'2');self.approve(january)
        feb=self.sheet(sales_basis='payments');self.import_all(feb);self.review(feb,feb.lines[0],'2')
        self.assertEqual(self.send('vat-approve',self.payload(id=feb.pk,version=feb.version,confirmed=True)).status_code,400)
        self.review(feb,feb.lines[0],'0');self.approve(feb)

    def test_manual_validation_credit_balance_retry_and_stale_version(self):
        sheet=self.sheet()
        base=self.payload(id=sheet.pk,version=sheet.version,direction='purchase',date='2026-02-01',reference='M',party='Supplier',net='10',tax='2',retained_tax='3',reason='Review')
        for change in [{},{'retained_tax':'1.001'},{'retained_tax':'1','date':'2026-01-01'},{'retained_tax':'1','reason':''}]:
            self.assertEqual(self.send('vat-line',dict(base,**change)).status_code,400)
        base['retained_tax']='1';saved=self.ok('vat-line',base);self.assertEqual(self.ok('vat-line',base),saved)
        self.assertEqual(self.send('vat-line',dict(base,reason='Changed retry')).status_code,400)
        self.assertEqual(self.send('vat-settings',self.payload(id=sheet.pk,version=1)).status_code,400)
        sheet.refresh_from_db();self.assertEqual(len(sheet.lines),1)
        self.assertEqual(self.send('vat-settings',self.payload(id=sheet.pk,version=sheet.version,opening_credit='1')).status_code,400)
        self.approve(sheet);self.assertEqual(sheet.approved_snapshot['totals']['carryforward'],100)
        self.assertEqual(AuditEvent.objects.filter(action='vat-line').count(),1)

    def test_roles_scope_export_escaping_and_backup(self):
        sheet=self.sheet();self.manual(sheet,reference='=FORMULA');self.approve(sheet)
        url=f'/api/companies/{self.company.pk}/vat/'
        response=self.client.get(url+'export',{'id':sheet.pk});self.assertIn("'=FORMULA",response.content.decode())
        backup=self.client.get(f'/api/companies/{self.company.pk}/backup').json();self.assertEqual(backup['version'],5);self.assertEqual(len(backup['vat']['worksheets']),1)
        self.assertEqual(self.client.get(f'/api/companies/{self.other.pk}/vat/state').json()['worksheets'],[])
        self.assertEqual(self.send('vat-void',self.payload(id=sheet.pk,version=sheet.version,reason='Wrong company'),self.other).status_code,400)
        user=User.objects.create_user(username='vat-reader',organization=self.org)
        member=Membership.objects.create(company=self.company,user=user,role='viewer');self.client.force_login(user)
        self.assertEqual(self.client.get(url+'state').status_code,200);self.assertEqual(self.client.get(url+'export',{'id':sheet.pk}).status_code,403)
        for action in ['vat-create','vat-import','vat-line','vat-remove','vat-settings','vat-approve','vat-void']:
            self.assertEqual(self.send(action,{}).status_code,403)
        member.role='commercial';member.save();self.assertEqual(self.client.get(url+'state').status_code,403)
        member.role='accountant';member.save();self.assertEqual(self.client.get(url+'export',{'id':sheet.pk}).status_code,200)
        self.client.logout();self.assertEqual(self.client.get(url+'state').status_code,401)

    def test_legacy_import_refuses_company_with_vat_history(self):
        response=self.send('vat-create',self.payload(start='2026-02-01',cadence='monthly',sales_basis='invoices',purchase_basis='invoices'),self.other)
        self.assertEqual(response.status_code,200)
        with self.assertRaisesMessage(CommandError,'La société doit être vide'):
            call_command('import_prototype','/tmp/unused-source.sqlite3',company=self.other.pk,actor=self.user.username)

    @skipUnless(connection.vendor=='postgresql','PostgreSQL immutability')
    def test_approved_snapshot_and_void_history_are_immutable(self):
        sheet=self.sheet();self.approve(sheet)
        with self.assertRaises(IntegrityError),transaction.atomic():VatWorksheet.objects.filter(pk=sheet.pk).update(note='Rewrite')
        with self.assertRaises(IntegrityError),transaction.atomic():sheet.delete()
        original=sheet.approved_snapshot
        self.change('vat-void',sheet,reason='Correction');self.assertEqual(sheet.status,'voided');self.assertEqual(sheet.approved_snapshot,original)
        with self.assertRaises(IntegrityError),transaction.atomic():VatWorksheet.objects.filter(pk=sheet.pk).update(void_reason='Rewrite history')
        self.assertEqual(self.client.get(f'/api/companies/{self.company.pk}/vat/export',{'id':sheet.pk}).status_code,400)
        self.sheet()  # Period can be prepared again; old approval remains available in state/backup.


@skipUnless(connection.vendor=='postgresql','Requires company row locks')
class ConcurrentVatTests(TransactionTestCase):
    def test_concurrent_import_and_approval_are_idempotent(self):
        fixtures.setup_book(self)
        service=CommercialService(self.company,self.user)
        sheet=service.mutate('vat-create',dict(request_key='create',start='2026-02-01',cadence='monthly',sales_basis='invoices',purchase_basis='invoices'))
        def run(args):
            close_old_connections()
            try:return CommercialService(self.company,self.user).mutate(*args)
            finally:close_old_connections()
        for action,version,extra in [('vat-import',1,{}),('vat-approve',2,{'confirmed':True})]:
            p=dict(request_key=action,id=sheet['id'],version=version,**extra)
            with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(run,[(action,p)]*2))
            self.assertEqual(rows[0],rows[1])
        self.assertEqual(VatWorksheet.objects.get(pk=sheet['id']).status,'approved')
        self.assertEqual(AuditEvent.objects.filter(action='vat-approve').count(),1)
