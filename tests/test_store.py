import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from server import Store, ValidationError, safe_csv


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'test.sqlite3'
        self.store = Store(self.path, demo=False)
        self.pid = self.store.mutate('products', {'sku': 'TEST-1', 'name': 'Produit test', 'category': 'Test', 'cost': '1.25', 'price': '2.75', 'stock': 10, 'minimum': 3})['id']

    def tearDown(self):
        self.temp.cleanup()

    def sale(self, **overrides):
        data = {'request_key': 'sale-1', 'items': [{'product_id': self.pid, 'quantity': 3}], 'paid': 0, 'tax_bps': 2000}
        data.update(overrides)
        return self.store.mutate('sales', data)

    def test_sale_tax_payment_and_stock_commit_together(self):
        self.sale(paid='5.00')
        state = self.store.state()
        sale = state['sales'][0]
        self.assertEqual((sale['subtotal'], sale['tax'], sale['total'], sale['paid']), (825, 165, 990, 500))
        self.assertEqual(state['products'][0]['stock'], 7)
        self.assertEqual(state['movements'][0]['quantity'], -3)
        self.assertEqual(state['payments'][0]['amount'], 500)

    def test_overselling_rejected_without_partial_writes(self):
        before = self.store.state()
        with self.assertRaisesRegex(ValidationError, 'Stock insuffisant'):
            self.sale(items=[{'product_id': self.pid, 'quantity': 8}, {'product_id': self.pid, 'quantity': 8}])
        self.assertEqual(before, self.store.state())

    def test_failure_on_later_line_rolls_back_every_product(self):
        with self.assertRaises(ValidationError):
            self.sale(items=[{'product_id': self.pid, 'quantity': 2}, {'product_id': 999, 'quantity': 1}])
        self.assertEqual(self.store.state()['products'][0]['stock'], 10)
        self.assertEqual(self.store.state()['sales'], [])

    def test_sale_retry_is_idempotent(self):
        first = self.sale()
        self.assertEqual(self.sale()['id'], first['id'])
        self.assertEqual(len(self.store.state()['sales']), 1)
        self.assertEqual(self.store.state()['products'][0]['stock'], 7)

    def test_concurrent_sales_cannot_oversell(self):
        def buy(key):
            try:
                self.sale(request_key=key, items=[{'product_id': self.pid, 'quantity': 7}])
                return True
            except ValidationError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(buy, ['concurrent-1', 'concurrent-2']))
        self.assertEqual(sorted(result), [False, True])
        self.assertEqual(self.store.state()['products'][0]['stock'], 3)

    def test_cancel_restores_stock_exactly_once(self):
        sid = self.sale()['id']
        self.store.mutate('cancel', {'sale_id': sid})
        self.store.mutate('cancel', {'sale_id': sid})
        state = self.store.state()
        self.assertEqual(state['products'][0]['stock'], 10)
        self.assertEqual(state['sales'][0]['status'], 'cancelled')
        self.assertEqual(len([m for m in state['movements'] if m['kind'] == 'return']), 1)

    def test_paid_sale_cannot_be_cancelled(self):
        sid = self.sale(paid='0.01')['id']
        with self.assertRaisesRegex(ValidationError, 'encaissée'):
            self.store.mutate('cancel', {'sale_id': sid})
        self.assertEqual(self.store.state()['products'][0]['stock'], 7)

    def test_payments_do_not_change_stock_and_cannot_overpay(self):
        sid = self.sale()['id']
        self.store.mutate('payments', {'sale_id': sid, 'amount': '9.90', 'method': 'Carte'})
        with self.assertRaises(ValidationError):
            self.store.mutate('payments', {'sale_id': sid, 'amount': '0.01'})
        state = self.store.state()
        self.assertEqual(state['products'][0]['stock'], 7)
        self.assertEqual(state['sales'][0]['paid'], 990)

    def test_invalid_payment_rolls_back_sale(self):
        for paid in ['9.91', '-1', 'NaN', 'Infinity', '0.001']:
            with self.subTest(paid=paid), self.assertRaises(ValidationError):
                self.sale(paid=paid)
        self.assertEqual(self.store.state()['sales'], [])
        self.assertEqual(self.store.state()['products'][0]['stock'], 10)

    def test_payment_and_receipt_retry_do_not_double_apply(self):
        sid = self.sale()['id']
        payment = {'sale_id': sid, 'amount': '2.00', 'request_key': 'payment-retry'}
        self.store.mutate('payments', payment)
        self.store.mutate('payments', payment)
        receipt = {'product_id': self.pid, 'quantity': 2, 'note': 'Réception', 'request_key': 'receipt-retry'}
        self.store.mutate('stock', receipt)
        self.store.mutate('stock', receipt)
        self.assertEqual(self.store.state()['sales'][0]['paid'], 200)
        self.assertEqual(self.store.state()['products'][0]['stock'], 9)

    def test_rounding_uses_cents(self):
        self.store.mutate('products', {'id': self.pid, 'sku': 'TEST-1', 'name': 'Produit test', 'category': 'Test', 'cost': 0, 'price': '0.05', 'minimum': 0})
        self.sale(items=[{'product_id': self.pid, 'quantity': 1}], tax_bps=1000)
        self.assertEqual(self.store.state()['sales'][0]['tax'], 1)

    def test_historical_prices_and_names_are_preserved(self):
        self.sale()
        self.store.mutate('products', {'id': self.pid, 'sku': 'TEST-1', 'name': 'Nouveau nom', 'category': 'Test', 'cost': 20, 'price': 30, 'minimum': 3})
        item = self.store.state()['sale_items'][0]
        self.assertEqual((item['name'], item['price'], item['cost']), ('Produit test', 275, 125))
        self.assertEqual(self.store.state()['products'][0]['stock'], 7)

    def test_stock_adjustment_requires_reason_and_available_stock(self):
        for data in [{'quantity': 11, 'note': 'Casse'}, {'quantity': 1, 'note': ''}, {'quantity': -1, 'note': 'Erreur'}, {'quantity': 1.5, 'note': 'Erreur'}]:
            with self.subTest(data=data), self.assertRaises(ValidationError):
                self.store.mutate('stock', {'product_id': self.pid, 'kind': 'adjustment', **data})
        self.store.mutate('stock', {'product_id': self.pid, 'kind': 'receipt', 'quantity': 5, 'note': 'Livraison'})
        self.assertEqual(self.store.state()['products'][0]['stock'], 15)

    def test_csv_import_is_atomic_and_case_insensitive_unique(self):
        header = 'sku,name,category,cost,price,stock,minimum\n'
        with self.assertRaises(ValidationError):
            self.store.mutate('import', {'csv': header + 'NEW,New,Test,1,2,5,1\ntest-1,Duplicate,Test,1,2,5,1\n'})
        self.assertEqual(len(self.store.state()['products']), 1)
        result = self.store.mutate('import', {'csv': header + 'NEW,"New, name",Test,1.25,2.75,5,1\n'})
        self.assertEqual(result['count'], 1)
        self.assertEqual(self.store.state()['products'][0]['name'], 'New, name')

    def test_data_survives_restart_and_backup_restores(self):
        self.sale()
        self.assertEqual(Store(self.path, demo=True).state(), self.store.state())
        backup = Path(self.temp.name) / 'backup.sqlite3'
        backup.write_bytes(self.store.backup())
        self.assertEqual(Store(backup, demo=False).state(), self.store.state())

    def test_demo_seed_is_only_applied_once(self):
        path = Path(self.temp.name) / 'demo.sqlite3'
        state = Store(path).state()
        self.assertEqual(len(state['products']), 12)
        self.assertEqual(len(state['sales']), 10)
        self.assertEqual(Store(path).state(), state)

    def test_csv_formula_prefix_is_neutralized(self):
        for value in ['=HYPERLINK("bad")', '+SUM(1,1)', '-1', '@SUM(1)', '  =1+1']:
            self.assertTrue(safe_csv(value).startswith("'"))
        self.assertEqual(safe_csv('Ordinary product'), 'Ordinary product')


if __name__ == '__main__':
    unittest.main()
