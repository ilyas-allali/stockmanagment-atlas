import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest import skipUnless

from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from server import ValidationError
from .models import (AuditEvent, Company, Membership, Movement, Organization, Product,
                     Purchase, PurchaseItem, Supplier, SupplierPayment, User)
from .services import CommercialService


class PurchaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name='Purchasing')
        cls.a = Company.objects.create(organization=cls.org, name='Casablanca')
        cls.b = Company.objects.create(organization=cls.org, name='Rabat')
        cls.user = User.objects.create_user(username='purchasing-owner', organization=cls.org, is_org_admin=True)
        cls.supplier = Supplier.objects.create(company=cls.a, name='Fournisseur A')
        cls.other_supplier = Supplier.objects.create(company=cls.b, name='Fournisseur B')
        cls.product = Product.objects.create(company=cls.a, sku='A', name='Article A', category='Test', cost=99, price=500, stock=5)
        cls.other_product = Product.objects.create(company=cls.b, sku='B', name='Article B', category='Test', cost=99, price=500, stock=5)

    def setUp(self):
        self.client.force_login(self.user)
        self.serial = 0

    def post(self, action, payload, company=None):
        return self.client.post(f'/api/companies/{(company or self.a).pk}/{action}', json.dumps(payload), content_type='application/json')

    def data(self, **changes):
        self.serial += 1
        return dict({'request_key': f'draft-{self.serial}', 'supplier_id': self.supplier.pk,
                     'supplier_reference': f'FA-{self.serial}', 'invoice_date': timezone.localdate().isoformat(),
                     'items': [{'product_id': self.product.pk, 'quantity': 3, 'price': '2.75', 'tax_bps': 2000}]}, **changes)

    def draft(self, **changes):
        response = self.post('purchases', self.data(**changes))
        self.assertEqual(response.status_code, 200, response.content)
        return Purchase.objects.get(pk=response.json()['id'])

    def action(self, purchase, **changes):
        self.serial += 1
        return dict({'request_key': f'operation-{self.serial}', 'purchase_id': purchase.pk, 'version': purchase.version}, **changes)

    def receive(self, p):
        response = self.post('purchase-receive', self.action(p))
        self.assertEqual(response.status_code, 200, response.content)
        p.refresh_from_db()

    def test_supplier_crud_scoped_and_historical_snapshot(self):
        result = self.post('suppliers', {'name': 'Atlas Supply', 'ice': '123456789012345', 'email': 'hello@example.test'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(Supplier.objects.get(pk=result.json()['id']).company, self.a)
        self.assertEqual(self.post('suppliers', {'name': 'Bad ICE', 'ice': '123'}).status_code, 400)
        self.assertEqual(self.post('suppliers', {'id': self.other_supplier.pk, 'name': 'Changed'}).status_code, 400)
        p = self.draft()
        self.post('suppliers', {'id': self.supplier.pk, 'name': 'Renamed'})
        p.refresh_from_db()
        self.assertEqual(p.supplier_name, 'Fournisseur A')

    def test_draft_line_rounding_and_no_stock_or_payable_effect(self):
        product = Product.objects.create(company=self.a, sku='C', name='C', category='Test', cost=0, price=0)
        p = self.draft(items=[{'product_id': self.product.pk, 'quantity': 3, 'price': '0.05', 'tax_bps': 1000},
                              {'product_id': product.pk, 'quantity': 1, 'price': '2.00', 'tax_bps': 2000}])
        self.assertEqual((p.subtotal, p.tax, p.total, p.paid, p.status), (215, 42, 257, 0, 'draft'))
        self.product.refresh_from_db();self.assertEqual(self.product.stock, 5)
        self.assertEqual(Movement.objects.count(), 0)
        self.assertEqual(self.post('supplier-payments', self.action(p, amount='1', payment_date=timezone.localdate().isoformat())).status_code, 400)

    def test_draft_edits_require_current_version_and_are_atomic(self):
        p = self.draft()
        payload = self.data(id=p.pk, version=p.version, supplier_reference=p.supplier_reference,
                            items=[{'product_id': self.product.pk, 'quantity': 4, 'price': '3', 'tax_bps': 0}])
        result = self.post('purchases', payload)
        self.assertEqual(result.status_code, 200)
        p.refresh_from_db();self.assertEqual((p.total, p.version, p.purchaseitem_set.count()), (1200, 2, 1))
        payload.update(request_key='stale-edit', note='Stale')
        self.assertEqual(self.post('purchases', payload).status_code, 400)
        invalid = self.data(id=p.pk, version=p.version, supplier_reference=p.supplier_reference, items=[])
        self.assertEqual(self.post('purchases', invalid).status_code, 400)
        p.refresh_from_db();self.assertEqual(p.total, 1200)
        self.assertEqual(p.purchaseitem_set.get().quantity, 4)

    def test_duplicate_reference_casefold_whitespace_and_company_numbering(self):
        a = self.draft(supplier_reference='FA-ONE')
        self.assertEqual(self.post('purchases', self.data(supplier_reference=' fa-one ')).status_code, 400)
        data = self.data(supplier_reference='FA-ONE', supplier_id=self.other_supplier.pk,
                         items=[{'product_id': self.other_product.pk, 'quantity': 1, 'price': 2}])
        response = self.post('purchases', data, self.b)
        self.assertEqual(response.status_code, 200)
        self.assertEqual((a.number, Purchase.objects.get(pk=response.json()['id']).number), (1, 1))
        self.post('purchase-cancel', self.action(a, reason='Duplicate entry'))
        self.assertEqual(self.post('purchases', self.data(supplier_reference='FA-ONE')).status_code, 400)

    def test_retry_protection_for_create_receive_and_payment(self):
        data = self.data()
        one = self.post('purchases', data);two = self.post('purchases', data)
        self.assertEqual(one.json(), two.json());self.assertEqual(Purchase.objects.count(), 1)
        data['note'] = 'Different request'
        self.assertEqual(self.post('purchases', data).status_code, 400)
        p = Purchase.objects.get(pk=one.json()['id'])
        receive = self.action(p)
        self.assertEqual(self.post('purchase-receive', receive).status_code, 200)
        self.assertEqual(self.post('purchase-receive', receive).status_code, 200)
        self.assertEqual(self.post('purchase-receive', self.action(p)).status_code, 400)
        self.product.refresh_from_db();self.assertEqual((self.product.stock, self.product.cost), (8, 99))
        self.assertEqual(Movement.objects.filter(purchase=p).count(), 1)
        payment = self.action(p, amount='4.90', payment_date=timezone.localdate().isoformat(), reference='BANK-12')
        self.assertEqual(self.post('supplier-payments', payment).status_code, 200)
        self.assertEqual(self.post('supplier-payments', payment).status_code, 200)
        p.refresh_from_db();self.assertEqual((p.paid, p.supplierpayment_set.count()), (490, 1))
        self.assertEqual(self.post('supplier-payments', self.action(p, amount='5.01', payment_date=timezone.localdate().isoformat())).status_code, 400)
        self.assertEqual(self.post('supplier-payments', self.action(p, amount='5', payment_date=timezone.localdate().isoformat())).status_code, 200)
        self.assertEqual(AuditEvent.objects.filter(company=self.a, action='purchase-receive').count(), 1)

    def test_received_invoice_is_immutable_and_paid_cannot_cancel(self):
        p = self.draft();self.receive(p)
        self.assertEqual(self.post('purchases', self.data(id=p.pk, version=p.version)).status_code, 400)
        self.post('supplier-payments', self.action(p, amount='1', payment_date=timezone.localdate().isoformat()))
        p.refresh_from_db()
        self.assertEqual(self.post('purchase-cancel', self.action(p, reason='No refund')).status_code, 400)
        p.refresh_from_db();self.assertEqual((p.status, p.paid), ('received', 100))

    def test_cancellation_restores_original_stock_once_and_blocks_payment(self):
        p = self.draft();self.receive(p)
        request = self.action(p, reason='Goods returned before payment')
        for _ in range(2):self.assertEqual(self.post('purchase-cancel', request).status_code, 200)
        self.product.refresh_from_db();self.assertEqual(self.product.stock, 5)
        p.refresh_from_db();self.assertEqual(p.cancellation_reason, request['reason'])
        self.assertEqual(Movement.objects.filter(purchase=p, kind='purchase_cancel').count(), 1)
        self.assertEqual(self.post('supplier-payments', self.action(p, amount=1, payment_date=timezone.localdate().isoformat())).status_code, 400)
        draft = self.draft()
        self.assertEqual(self.post('purchase-cancel', self.action(draft, reason='Entry error')).status_code, 200)
        self.assertFalse(Movement.objects.filter(purchase=draft).exists())

    def test_receipt_and_cancellation_are_atomic_across_lines(self):
        limited = Product.objects.create(company=self.a, sku='LIMIT', name='Full', category='Test', cost=0, price=0, stock=1000000)
        p = self.draft(items=[{'product_id': self.product.pk, 'quantity': 3, 'price': 1}, {'product_id': limited.pk, 'quantity': 1, 'price': 1}])
        self.assertEqual(self.post('purchase-receive', self.action(p)).status_code, 400)
        self.product.refresh_from_db();self.assertEqual(self.product.stock, 5)
        self.assertEqual(Movement.objects.count(), 0)
        limited.stock=0;limited.save();self.receive(p)
        limited.stock=0;limited.save()  # Goods consumed after receipt.
        self.assertEqual(self.post('purchase-cancel', self.action(p, reason='Cannot reverse missing goods')).status_code, 400)
        self.product.refresh_from_db();self.assertEqual(self.product.stock, 8)
        p.refresh_from_db();self.assertEqual(p.status, 'received')

    def test_cross_company_supplier_product_purchase_ids_rejected(self):
        self.assertEqual(self.post('purchases', self.data(supplier_id=self.other_supplier.pk)).status_code, 400)
        self.assertEqual(self.post('purchases', self.data(items=[{'product_id': self.other_product.pk, 'quantity': 1, 'price': 1}])).status_code, 400)
        p = self.draft()
        for action in ['purchase-receive', 'purchase-cancel', 'supplier-payments']:
            self.assertEqual(self.post(action, self.action(p, reason='No', amount=1), self.b).status_code, 400)
        self.assertEqual(self.post('purchases', self.data(id=p.pk, version=p.version), self.b).status_code, 400)

    def test_role_permissions_and_anonymous_access(self):
        p = self.draft();self.receive(p)
        user = User.objects.create_user(username='staff', organization=self.org)
        membership = Membership.objects.create(user=user, company=self.a, role='viewer')
        self.client.force_login(user)
        for action in ['suppliers','purchases','purchase-receive','purchase-cancel','supplier-payments']:
            self.assertEqual(self.post(action, {}).status_code, 403)
        url = f'/api/companies/{self.a.pk}/export/purchases'
        self.assertEqual(self.client.get(url).status_code, 403)
        membership.role='accountant';membership.save()
        for action in ['suppliers','purchases','purchase-receive','purchase-cancel']:
            self.assertEqual(self.post(action, {}).status_code, 403)
        self.assertEqual(self.post('supplier-payments', self.action(p, amount=1, payment_date=timezone.localdate().isoformat())).status_code, 200)
        membership.role='commercial';membership.save()
        self.assertEqual(self.post('purchase-cancel', {}).status_code, 403)
        self.assertEqual(self.post('purchases', self.data()).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.post('purchases', self.data()).status_code, 401)

    def test_input_validation_no_partial_writes(self):
        for changes in [{'invoice_date':'bad'}, {'invoice_date':None}, {'due_date':'1900-01-01'},
                        {'supplier_reference':''}, {'items':[]}, {'items':[None]}, {'request_key':None},
                        {'items':[{'product_id':self.product.pk, 'quantity':-1, 'price':1}]},
                        {'items':[{'product_id':self.product.pk, 'quantity':1, 'price':'1.001'}]},
                        {'items':[{'product_id':self.product.pk, 'quantity':1, 'price':1, 'tax_bps':10001}]},
                        {'items':[{'product_id':self.product.pk, 'quantity':1000000, 'price':10000000}]},
                        {'items':[{'product_id':self.product.pk, 'quantity':1, 'price':1}]*2}]:
            with self.subTest(changes=changes):self.assertEqual(self.post('purchases', self.data(**changes)).status_code, 400)
        self.assertEqual(Purchase.objects.count(), 0)
        self.a.refresh_from_db();self.assertEqual(self.a.next_purchase_number, 1)

    def test_payment_dates_amount_and_method(self):
        p = self.draft();self.receive(p)
        for changes in [{'amount':0}, {'amount':-1}, {'method':'Unknown'}, {'payment_date':'wrong'},
                        {'payment_date':(timezone.localdate()+timedelta(days=1)).isoformat()}, {'payment_date':'1900-01-01'}]:
            data=self.action(p, amount=1, payment_date=timezone.localdate().isoformat());data.update(changes)
            self.assertEqual(self.post('supplier-payments',data).status_code,400)
        self.assertFalse(SupplierPayment.objects.exists())

    def test_exports_include_purchases_and_escape_spreadsheet_formulas(self):
        p=self.draft(supplier_reference='=SUM(1)');self.receive(p)
        state=self.client.get(f'/api/companies/{self.a.pk}/state').json()
        self.assertEqual([s['id'] for s in state['suppliers']],[self.supplier.pk])
        self.assertEqual([x['id'] for x in state['purchases']],[p.pk])
        exported=self.client.get(f'/api/companies/{self.a.pk}/backup').json()
        self.assertEqual(exported['version'],5)
        self.assertEqual(len(exported['purchase_items']),1)
        csv=self.client.get(f'/api/companies/{self.a.pk}/export/purchases').content.decode()
        self.assertIn("'=SUM(1)",csv);self.assertIn('9.90',csv);self.assertNotIn('Fournisseur B',csv)
        self.assertIn('purchase-receive',[e['action'] for e in exported['audit']])

    @skipUnless(connection.vendor=='postgresql','PostgreSQL relationship guards')
    def test_database_rejects_cross_company_purchase_relationships(self):
        p=self.draft();self.receive(p)
        with self.assertRaises(IntegrityError),transaction.atomic():
            Purchase.objects.filter(pk=p.pk).update(supplier=self.other_supplier)
        with self.assertRaises(IntegrityError),transaction.atomic():
            PurchaseItem.objects.filter(purchase=p).update(product=self.other_product)
        with self.assertRaises(IntegrityError),transaction.atomic():
            SupplierPayment.objects.create(company=self.b,purchase=p,amount=1,method='Espèces',payment_date=timezone.localdate())
        with self.assertRaises(IntegrityError),transaction.atomic():
            Movement.objects.create(company=self.b,product=self.other_product,purchase=p,quantity=1,kind='purchase',note='Bad',created_at=timezone.now())


@skipUnless(connection.vendor=='postgresql','Requires real row locks')
class ConcurrentPurchaseTests(TransactionTestCase):
    def test_concurrent_receipts_and_payments_do_not_duplicate(self):
        org=Organization.objects.create(name='Concurrent purchases')
        company=Company.objects.create(organization=org,name='A')
        user=User.objects.create_user(username='buyer',organization=org,is_org_admin=True)
        supplier=Supplier.objects.create(company=company,name='S')
        product=Product.objects.create(company=company,sku='ONE',name='P',category='T',cost=0,price=0,stock=1)
        service=CommercialService(company,user)
        p=service.mutate('purchases',{'request_key':'draft','supplier_id':supplier.pk,'supplier_reference':'REF',
                                    'invoice_date':timezone.localdate().isoformat(),
                                    'items':[{'product_id':product.pk,'quantity':5,'price':2}]})
        def run(request):
            close_old_connections()
            try:
                CommercialService(company,user).mutate(*request)
                return True
            except ValidationError:
                return False
            finally:
                close_old_connections()
        receive={'request_key':'receive','purchase_id':p['id'],'version':1}
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(run,[('purchase-receive',receive)]*2)),[True,True])
        product.refresh_from_db();self.assertEqual(product.stock,6)
        self.assertEqual(Movement.objects.filter(purchase_id=p['id']).count(),1)
        base={'purchase_id':p['id'],'amount':8,'payment_date':timezone.localdate().isoformat()}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(run,[('supplier-payments',dict(base,request_key=key)) for key in ['payment-a','payment-b']]))
        self.assertEqual(sorted(results),[False,True])
        self.assertEqual(Purchase.objects.get(pk=p['id']).paid,800)
