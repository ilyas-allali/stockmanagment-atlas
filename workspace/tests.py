import hashlib
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import skipUnless

from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone
from server import Store, ValidationError
from .models import AuditEvent, Company, Customer, Membership, Organization, Payment, Product, Sale, User
from .services import CommercialService

PASSWORD = 'Atlas-Test-Password-729!'


class PlatformTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Groupe A')
        self.org2 = Organization.objects.create(name='Groupe B')
        self.a = Company.objects.create(organization=self.org, name='Société A')
        self.b = Company.objects.create(organization=self.org, name='Société B')
        self.foreign = Company.objects.create(organization=self.org2, name='Autre organisation')
        self.admin = User.objects.create_user(username='owner', password=PASSWORD, organization=self.org, is_org_admin=True)
        self.member = User.objects.create_user(username='commercial', password=PASSWORD, organization=self.org)
        self.viewer = User.objects.create_user(username='viewer', password=PASSWORD, organization=self.org)
        Membership.objects.create(user=self.member, company=self.a, role='commercial')
        Membership.objects.create(user=self.viewer, company=self.a, role='viewer')
        self.pa = self.product(self.a, 'A-1')
        self.pb = self.product(self.b, 'B-1')
        self.client.force_login(self.admin)

    def product(self, company, sku):
        return Product.objects.create(company=company, sku=sku, name=f'Produit {sku}', category='Test', cost=100, price=275, stock=10, minimum=2)

    def post(self, path, data, client=None):
        return (client or self.client).post(path, json.dumps(data), content_type='application/json')

    def url(self, company, action):
        return f'/api/companies/{company.pk}/{action}'

    def sale(self, company=None, product=None, key='sale-1', paid=0):
        c = company or self.a
        p = product or self.pa
        return self.post(self.url(c, 'sales'), {'request_key': key, 'items': [{'product_id': p.pk, 'quantity': 3}], 'tax_bps': 2000, 'paid': paid})

    def test_every_company_route_requires_authentication(self):
        self.client.logout()
        for action in ['state', 'backup', 'audit', 'export/products']:
            self.assertEqual(self.client.get(self.url(self.a, action)).status_code, 401)
        self.assertEqual(self.sale().status_code, 401)
        self.assertEqual(self.client.get('/api/companies').status_code, 401)
        self.assertEqual(self.client.get('/api/users').status_code, 401)

    def test_login_csrf_logout_and_session_expiry(self):
        c = Client(enforce_csrf_checks=True)
        token = c.get('/api/auth/me').json()['csrf_token']
        self.assertEqual(self.post('/api/auth/login', {'username': 'owner', 'password': PASSWORD}, c).status_code, 403)
        response = c.post('/api/auth/login', data=json.dumps({'username':'owner','password':PASSWORD}), content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.cookies['sessionid']['httponly'])
        self.assertNotEqual(response.json()['csrf_token'], token)
        current = response.json()['csrf_token']
        response = c.post('/api/auth/logout', data='{}', content_type='application/json', HTTP_X_CSRFTOKEN=current)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(c.get(self.url(self.a, 'state')).status_code, 401)

    def test_login_is_rate_limited(self):
        self.client.logout()
        for _ in range(10):
            self.assertEqual(self.post('/api/auth/login', {'username':'owner', 'password':'bad'}).status_code, 401)
        self.assertEqual(self.post('/api/auth/login', {'username':'owner', 'password':PASSWORD}).status_code, 429)

    def test_company_list_follows_membership_and_organization(self):
        self.assertEqual({c['id'] for c in self.client.get('/api/companies').json()['companies']}, {self.a.pk, self.b.pk})
        self.client.force_login(self.member)
        self.assertEqual([c['id'] for c in self.client.get('/api/companies').json()['companies']], [self.a.pk])
        for c in [self.b, self.foreign]:
            for action in ['state', 'backup', 'export/products', 'audit']:
                self.assertEqual(self.client.get(self.url(c, action)).status_code, 404)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url(self.foreign, 'state')).status_code, 404)

    def test_guessed_product_ids_cannot_cross_companies(self):
        response = self.post(self.url(self.a, 'stock'), {'product_id':self.pb.pk, 'quantity':2,'note':'Wrong company'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.sale(product=self.pb).status_code, 400)
        self.pb.refresh_from_db();self.assertEqual(self.pb.stock, 10)
        self.assertEqual(Sale.objects.count(), 0)

    def test_cross_company_customer_payment_and_cancellation_rejected(self):
        customer = Customer.objects.create(company=self.b, name='Other customer')
        response = self.post(self.url(self.a,'sales'),{'request_key':'invalid', 'customer_id':customer.pk,'items':[{'product_id':self.pa.pk,'quantity':1}]})
        self.assertEqual(response.status_code,400)
        sid=self.sale(company=self.b,product=self.pb).json()['id']
        for action,data in [('payments',{'sale_id':sid,'amount':1}),('cancel',{'sale_id':sid})]:
            self.assertEqual(self.post(self.url(self.a,action),data).status_code,400)
        self.assertEqual(Sale.objects.get(pk=sid).status,'active')

    def test_viewer_cannot_modify_or_export(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.url(self.a, 'state')).status_code, 200)
        for action in ['products','customers','sales','stock','payments','cancel','settings','import']:
            self.assertEqual(self.post(self.url(self.a,action),{}).status_code,403)
        for action in ['backup','export/products','audit']:
            self.assertEqual(self.client.get(self.url(self.a,action)).status_code,403)
        self.assertEqual(self.post('/api/companies',{'name':'Forbidden'}).status_code,403)
        self.assertEqual(self.client.get('/api/users').status_code,403)

    def test_commercial_cannot_administer_or_cancel(self):
        self.client.force_login(self.member)
        self.assertEqual(self.sale().status_code,200)
        for action in ['settings','cancel']:
            self.assertEqual(self.post(self.url(self.a,action),{}).status_code,403)
        self.assertEqual(self.client.get(self.url(self.a,'backup')).status_code,403)
        self.assertEqual(self.client.get(self.url(self.a,'export/products')).status_code,200)

    def test_access_revocation_and_user_disable_apply_to_existing_session(self):
        c=Client();c.force_login(self.member)
        Membership.objects.filter(user=self.member).delete()
        self.assertEqual(c.get(self.url(self.a,'state')).status_code,404)
        self.member.is_active=False;self.member.save()
        self.assertEqual(c.get('/api/companies').status_code,401)

    def test_create_company_limit_and_isolation(self):
        self.org.company_limit=3;self.org.save()
        response=self.post('/api/companies',{'name':'Nouvelle société'})
        self.assertEqual(response.status_code,201)
        new=Company.objects.get(pk=response.json()['id'])
        self.assertEqual(self.client.get(self.url(new,'state')).json()['products'],[])
        self.assertEqual(self.post('/api/companies',{'name':'Au-delà'}).status_code,400)

    def test_user_creation_memberships_and_no_privilege_escalation(self):
        result=self.post('/api/users',{'username':'new-user','name':'New','password':PASSWORD,'is_org_admin':True,
                                     'memberships':[{'company_id':self.b.pk,'role':'viewer'}]})
        self.assertEqual(result.status_code,200)
        user=User.objects.get(pk=result.json()['id']);self.assertFalse(user.is_org_admin)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(Membership.objects.get(user=user).company_id,self.b.pk)
        response=self.post('/api/users',{'id':user.pk,'active':True,'memberships':[{'company_id':self.foreign.pk,'role':'admin'}]})
        self.assertEqual(response.status_code,400)
        self.assertEqual(Membership.objects.get(user=user).company_id,self.b.pk)

    def test_password_change_invalidates_other_sessions(self):
        other=Client();other.force_login(self.admin)
        response=self.post('/api/auth/password',{'current_password':PASSWORD,'password':'Changed-atlas-password-829!'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(other.get('/api/companies').status_code,401)
        self.assertEqual(self.client.get('/api/companies').status_code,200)

    def test_sale_payment_cancel_retry_and_company_numbering(self):
        a=self.sale().json()['id'];b=self.sale(company=self.b,product=self.pb).json()['id']
        self.assertEqual(self.sale().json()['id'],a)
        for sid in [a,b]:self.assertEqual(Sale.objects.get(pk=sid).number,1)
        self.pa.refresh_from_db();self.assertEqual(self.pa.stock,7)
        sale=Sale.objects.get(pk=a);self.assertEqual((sale.subtotal,sale.tax,sale.total),(825,165,990))
        p={'sale_id':a,'amount':'2.00','request_key':'pay-retry'}
        self.post(self.url(self.a,'payments'),p);self.post(self.url(self.a,'payments'),p)
        self.assertEqual(Payment.objects.filter(sale_id=a).count(),1)
        self.assertEqual(self.post(self.url(self.a,'cancel'),{'sale_id':a}).status_code,400)
        for _ in range(2):self.post(self.url(self.b,'cancel'),{'sale_id':b})
        self.pb.refresh_from_db();self.assertEqual(self.pb.stock,10)

    def test_exports_and_audit_only_contain_current_company(self):
        self.sale()
        data=self.client.get(self.url(self.a,'backup')).json()
        self.assertEqual([p['sku'] for p in data['products']],['A-1'])
        self.assertNotIn('users',data)
        self.assertNotIn('password',json.dumps(data))
        audit=self.client.get(self.url(self.a,'audit')).json()['events']
        self.assertTrue(any(e['action']=='sales' and e['actor__username']=='owner' for e in audit))
        csv=self.client.get(self.url(self.a,'export/products')).content.decode()
        self.assertIn('A-1',csv);self.assertNotIn('B-1',csv)

    def test_sku_unique_per_company_and_import_atomic(self):
        data={'sku':'A-1','name':'Same SKU','category':'Test','cost':1,'price':2,'stock':1,'minimum':0}
        self.assertEqual(self.post(self.url(self.b,'products'),data).status_code,200)
        data['sku']='a-1'
        self.assertEqual(self.post(self.url(self.a,'products'),data).status_code,400)
        csv='sku,name,category,cost,price,stock,minimum\nNEW,New,Test,1,2,3,1\nA-1,Duplicate,Test,1,2,3,1\n'
        self.assertEqual(self.post(self.url(self.a,'import'),{'csv':csv}).status_code,400)
        self.assertFalse(Product.objects.filter(company=self.a,sku='NEW').exists())

    @skipUnless(connection.vendor=='postgresql','PostgreSQL constraint test')
    def test_database_rejects_cross_company_relation_even_without_api(self):
        customer=Customer.objects.create(company=self.b,name='Other')
        sid=self.sale().json()['id']
        with self.assertRaises(IntegrityError),transaction.atomic():
            Sale.objects.filter(pk=sid).update(customer=customer)
        with self.assertRaises(IntegrityError),transaction.atomic():
            Membership.objects.create(user=self.member,company=self.foreign,role='admin')

    def test_prototype_import_is_read_only_and_requires_empty_company(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'legacy.sqlite3';Store(path)
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            c=Company.objects.create(organization=self.org,name='Migration')
            call_command('import_prototype',str(path),company=c.pk,actor=self.admin.username,verbosity=0)
            self.assertEqual(c.product_set.count(),12);self.assertEqual(c.sale_set.count(),10)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
            with self.assertRaises(Exception):call_command('import_prototype',str(path),company=c.pk,actor=self.admin.username,verbosity=0)


@skipUnless(connection.vendor=='postgresql','Concurrent row-lock test requires PostgreSQL')
class ConcurrentSalesTests(TransactionTestCase):
    def test_two_sessions_cannot_oversell(self):
        org=Organization.objects.create(name='Concurrent')
        company=Company.objects.create(organization=org,name='Concurrent')
        user=User.objects.create_user(username='concurrent',password=PASSWORD,organization=org,is_org_admin=True)
        product=Product.objects.create(company=company,sku='ONE',name='Limited stock',category='Test',cost=100,price=200,stock=5,minimum=1)
        def buy(key):
            close_old_connections()
            try:
                CommercialService(company,user).mutate('sales',{'request_key':key,'items':[{'product_id':product.pk,'quantity':4}]})
                return True
            except ValidationError:
                return False
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            result=list(pool.map(buy,['concurrent-a','concurrent-b']))
        self.assertEqual(sorted(result),[False,True])
        product.refresh_from_db();self.assertEqual(product.stock,1)
