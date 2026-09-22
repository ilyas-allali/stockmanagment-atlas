"""Company-scoped commercial services. Money is integer centimes."""
import csv
import io
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone
from server import ValidationError, integer, label, money, require
from .models import AuditEvent, Company, Customer, Movement, OperationRequest, Payment, Product, Sale, SaleItem, Supplier, Purchase, PurchaseItem, SupplierPayment

CAPABILITIES = {
    'admin': {'read', 'catalog', 'stock', 'sales', 'purchases', 'payments', 'cancel', 'settings', 'export', 'audit'},
    'commercial': {'read', 'catalog', 'stock', 'sales', 'purchases', 'payments', 'export'},
    'accountant': {'read', 'payments', 'export'},
    'supervisor': {'read', 'catalog', 'stock', 'sales', 'purchases', 'payments', 'cancel', 'export', 'audit'},
    'viewer': {'read'},
}
for role in ('admin', 'accountant', 'supervisor', 'viewer'):
    CAPABILITIES[role].update({'accounting_read', 'vat_read'})
for role in ('admin', 'accountant'):
    CAPABILITIES[role].update({'accounting_write', 'vat_write'})
ACTION_CAPABILITY = {'products': 'catalog', 'customers': 'catalog', 'stock': 'stock', 'sales': 'sales',
                     'payments': 'payments', 'cancel': 'cancel', 'settings': 'settings', 'import': 'catalog',
                     'suppliers': 'catalog', 'purchases': 'purchases', 'purchase-receive': 'purchases',
                     'purchase-cancel': 'cancel', 'supplier-payments': 'payments'}
PURCHASE_ACTIONS = {'purchases', 'purchase-receive', 'purchase-cancel', 'supplier-payments'}
ACCOUNTING_ACTIONS = {'accounting-account', 'accounting-journal', 'accounting-period', 'accounting-period-state',
                      'accounting-entry', 'accounting-transfer', 'accounting-post', 'accounting-discard', 'accounting-reverse', 'accounting-payment-transfer', 'accounting-match', 'accounting-unmatch'}
ACTION_CAPABILITY.update({action: 'accounting_write' for action in ACCOUNTING_ACTIONS})


VAT_ACTIONS = {'vat-create', 'vat-import', 'vat-line', 'vat-remove', 'vat-settings', 'vat-approve', 'vat-void'}
ACTION_CAPABILITY.update({action: 'vat_write' for action in VAT_ACTIONS})


def scoped(model, company, pk):
    obj = model.objects.filter(company=company, pk=integer(pk, 'Identifiant', 1, 2**53-1)).first()
    require(obj is not None, 'Enregistrement introuvable dans cette société.')
    return obj


def log(company, actor, action, details=None):
    AuditEvent.objects.create(company=company, actor=actor, action=action, details=details or {})


class CommercialService:
    def __init__(self, company, actor):
        self.company = company
        self.actor = actor

    @transaction.atomic
    def mutate(self, action, payload):
        require(action in ACTION_CAPABILITY, 'Action inconnue.')
        self.company = Company.objects.select_for_update().get(pk=self.company.pk)
        key = payload.get('request_key') if action in PURCHASE_ACTIONS | ACCOUNTING_ACTIONS | VAT_ACTIONS | {'stock', 'payments'} else None
        fingerprint = None
        if action in PURCHASE_ACTIONS | ACCOUNTING_ACTIONS | VAT_ACTIONS:
            key = label(key, 'Identifiant de requête', limit=80)
            fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
        if key:
            key = label(key, 'Identifiant', limit=80)
            prior = OperationRequest.objects.filter(company=self.company, key=key).first()
            if prior:
                require(prior.action == action, 'Identifiant déjà utilisé.')
                if fingerprint:
                    require(prior.result.get('request_fingerprint') == fingerprint,
                            'Cette requête a déjà été enregistrée avec un contenu différent. Actualisez la page.')
                    return prior.result['response']
                return prior.result
        handler = {'products': self.product, 'customers': self.customer, 'stock': self.stock,
                   'sales': self.sale, 'payments': self.payment, 'cancel': self.cancel,
                   'settings': self.settings, 'import': self.import_products}.get(action)
        if handler:
            result = handler(payload)
        elif action in VAT_ACTIONS:
            from .vat import VatService
            result = VatService(self.company, self.actor).handle(action, payload)
        elif action in ACCOUNTING_ACTIONS:
            from .accounting import AccountingService
            result = AccountingService(self.company, self.actor).handle(action, payload)
        else:
            from .purchases import PurchaseService
            result = PurchaseService(self.company, self.actor).handle(action, payload)
        if key:
            saved = {'request_fingerprint': fingerprint, 'response': result} if fingerprint else result
            OperationRequest.objects.create(company=self.company, key=key, action=action, result=saved)
        log(self.company, self.actor, action, result)
        return result

    def product(self, p):
        data = dict(sku=label(p.get('sku'), 'Référence', limit=40), name=label(p.get('name'), 'Nom'),
                    category=label(p.get('category', 'Général'), 'Catégorie', limit=60),
                    cost=money(p.get('cost')), price=money(p.get('price')), minimum=integer(p.get('minimum', 5), 'Seuil'))
        if p.get('id'):
            product = scoped(Product, self.company, p['id'])
            for key, value in data.items():
                setattr(product, key, value)
            product.save()
        else:
            product = Product.objects.create(company=self.company, stock=integer(p.get('stock', 0), 'Stock initial'), **data)
            if product.stock:
                Movement.objects.create(company=self.company, product=product, kind='opening', quantity=product.stock, note='Stock initial', created_at=timezone.now())
        return {'id': product.pk}

    def customer(self, p):
        data = dict(name=label(p.get('name'), 'Nom'), email=label(p.get('email', ''), 'Email', False),
                    phone=label(p.get('phone', ''), 'Téléphone', False, 40), city=label(p.get('city', ''), 'Ville', False, 80))
        if p.get('id'):
            customer = scoped(Customer, self.company, p['id'])
            for key, value in data.items():
                setattr(customer, key, value)
            customer.save()
        else:
            customer = Customer.objects.create(company=self.company, **data)
        return {'id': customer.pk}

    def stock(self, p):
        product = scoped(Product, self.company, p.get('product_id'))
        qty = integer(p.get('quantity'), 'Quantité', 1)
        kind = p.get('kind', 'receipt')
        require(kind in ('receipt', 'adjustment'), 'Type de mouvement invalide.')
        delta = qty if kind == 'receipt' else -qty
        require(0 <= product.stock + delta <= 1_000_000, 'Stock insuffisant ou maximum dépassé.')
        note = label(p.get('note', ''), 'Motif', limit=500)
        product.stock += delta
        product.save(update_fields=['stock'])
        Movement.objects.create(company=self.company, product=product, kind=kind, quantity=delta, note=note, created_at=timezone.now())
        return {'id': product.pk}

    def method(self, p):
        method = p.get('method', 'Espèces')
        require(method in ('Espèces', 'Virement', 'Carte', 'Chèque'), 'Mode de paiement invalide.')
        return method

    def sale(self, p):
        key = label(p.get('request_key'), 'Identifiant', limit=80)
        prior = Sale.objects.filter(company=self.company, request_key=key).first()
        if prior:
            return {'id': prior.pk, 'already_saved': True}
        items = p.get('items')
        require(isinstance(items, list) and 0 < len(items) <= 100, 'Ajoutez au moins un produit (100 maximum).')
        quantities = {}
        for item in items:
            require(isinstance(item, dict), 'Ligne invalide.')
            pid = integer(item.get('product_id'), 'Produit', 1, 2**53-1)
            quantities[pid] = quantities.get(pid, 0) + integer(item.get('quantity'), 'Quantité', 1)
        rows = []
        for pid, qty in quantities.items():
            product = scoped(Product, self.company, pid)
            require(qty <= product.stock, f'Stock insuffisant : {product.name} ({product.stock} disponible).')
            rows.append((product, qty))
        customer = scoped(Customer, self.company, p['customer_id']) if p.get('customer_id') else None
        subtotal = sum(product.price * qty for product, qty in rows)
        rate = integer(p.get('tax_bps', 0), 'Taux de taxe', 0, 10000)
        tax = int((Decimal(subtotal) * rate / 10000).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        total = subtotal + tax
        require(total <= 1_000_000_000, 'Maximum par vente : 10 000 000 DH.')
        paid = money(p.get('paid', 0))
        require(paid <= total, 'Le paiement dépasse le total.')
        stamp = timezone.now()
        sale = Sale.objects.create(company=self.company, number=self.company.next_sale_number, request_key=key,
            customer=customer, customer_name=customer.name if customer else 'Client de passage', created_at=stamp,
            subtotal=subtotal, tax_bps=rate, tax=tax, total=total, paid=paid, note=label(p.get('note', ''), 'Note', False, 1000))
        self.company.next_sale_number += 1
        self.company.save(update_fields=['next_sale_number'])
        for product, qty in rows:
            SaleItem.objects.create(company=self.company, sale=sale, product=product, name=product.name, sku=product.sku, quantity=qty, price=product.price, cost=product.cost)
            product.stock -= qty
            product.save(update_fields=['stock'])
            Movement.objects.create(company=self.company, sale=sale, product=product, kind='sale', quantity=-qty, note=f'Vente VT-{sale.number:04d}', created_at=stamp)
        if paid:
            Payment.objects.create(company=self.company, sale=sale, amount=paid, created_at=stamp, method=self.method(p))
        return {'id': sale.pk}

    def payment(self, p):
        sale = scoped(Sale, self.company, p.get('sale_id'))
        require(sale.status == 'active', 'Vente annulée.')
        amount = money(p.get('amount'))
        require(0 < amount <= sale.total - sale.paid, 'Le paiement doit être positif et ne pas dépasser le reste dû.')
        sale.paid += amount
        sale.save(update_fields=['paid'])
        Payment.objects.create(company=self.company, sale=sale, amount=amount, created_at=timezone.now(), method=self.method(p))
        return {'id': sale.pk}

    def cancel(self, p):
        sale = scoped(Sale, self.company, p.get('sale_id'))
        if sale.status == 'cancelled':
            return {'id': sale.pk}
        require(sale.paid == 0, 'Une vente encaissée nécessite un traitement de remboursement séparé.')
        from .accounting import ensure_source_can_cancel
        ensure_source_can_cancel(self.company, sale=sale)
        for item in SaleItem.objects.filter(company=self.company, sale=sale):
            product = scoped(Product, self.company, item.product_id)
            product.stock += item.quantity
            product.save(update_fields=['stock'])
            Movement.objects.create(company=self.company, product=product, sale=sale, kind='return', quantity=item.quantity, note=f'Annulation VT-{sale.number:04d}', created_at=timezone.now())
        sale.status = 'cancelled'
        sale.save(update_fields=['status'])
        return {'id': sale.pk}

    def settings(self, p):
        self.company.name = label(p.get('name'), 'Entreprise')
        self.company.address = label(p.get('address', ''), 'Adresse', False, 500)
        self.company.phone = label(p.get('phone', ''), 'Téléphone', False, 40)
        self.company.fiscal_id = label(p.get('fiscal_id', self.company.fiscal_id), 'Identifiant fiscal', False, 40)
        self.company.ice = label(p.get('ice', self.company.ice), 'ICE', False, 15)
        require(not self.company.ice or self.company.ice.isdigit() and len(self.company.ice) == 15, 'L’ICE doit contenir 15 chiffres.')
        self.company.save()
        return {'ok': True}

    def import_products(self, p):
        content = label(p.get('csv'), 'CSV', limit=1_000_000).lstrip('\ufeff')
        reader = csv.DictReader(io.StringIO(content))
        expected = {'sku', 'name', 'category', 'cost', 'price', 'stock', 'minimum'}
        require(reader.fieldnames and set(reader.fieldnames) == expected and len(reader.fieldnames) == 7, 'Colonnes attendues : sku,name,category,cost,price,stock,minimum')
        count = 0
        for count, row in enumerate(reader, 1):
            require(count <= 5000 and None not in row, f'Ligne {count+1} invalide ou limite dépassée.')
            self.product(row)
        require(count, 'Aucun produit à importer.')
        return {'count': count}

    @transaction.atomic
    def state(self):
        c = Company.objects.select_for_update().get(pk=self.company.pk)
        result = {'settings': {k: getattr(c, k) for k in ['id', 'name', 'phone', 'address', 'demo', 'fiscal_id', 'ice']}}
        for key, model in [('products', Product), ('customers', Customer), ('sales', Sale), ('sale_items', SaleItem), ('payments', Payment),
                           ('suppliers', Supplier), ('purchases', Purchase), ('purchase_items', PurchaseItem), ('supplier_payments', SupplierPayment)]:
            result[key] = list(model.objects.filter(company=c).order_by('-id').values())
        result['movements'] = list(Movement.objects.filter(company=c).order_by('-id').values()[:1000])
        products = {p['id']: p for p in result['products']}
        for m in result['movements']:
            m.update(name=products[m['product_id']]['name'], sku=products[m['product_id']]['sku'])
        return result
