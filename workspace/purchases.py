"""Purchasing rules. Called inside CommercialService's company lock and transaction."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone
from server import ValidationError, integer, label, money, require
from .models import Movement, Product, Purchase, PurchaseItem, Supplier, SupplierPayment
from .services import scoped


def calendar_date(value, title, optional=False):
    if optional and value in (None, ''):
        return None
    try:
        require(isinstance(value, str) and len(value) == 10, f'{title} : date attendue (AAAA-MM-JJ).')
        result = date.fromisoformat(value)
        require(result.isoformat() == value, f'{title} invalide.')
        return result
    except ValueError:
        raise ValidationError(f'{title} invalide.')


class PurchaseService:
    def __init__(self, company, actor):
        self.company, self.actor = company, actor

    def handle(self, action, payload):
        return {'suppliers': self.supplier, 'purchases': self.save_draft,
                'purchase-receive': self.receive, 'purchase-cancel': self.cancel,
                'supplier-payments': self.payment}[action](payload)

    def supplier(self, p):
        fields = {'name': (True, 160), 'email': (False, 160), 'phone': (False, 40),
                  'city': (False, 80), 'address': (False, 500), 'fiscal_id': (False, 40), 'ice': (False, 15)}
        data = {key: label(p.get(key, ''), key, required, limit) for key, (required, limit) in fields.items()}
        require(not data['ice'] or data['ice'].isascii() and data['ice'].isdigit() and len(data['ice']) == 15,
                'L’ICE doit contenir 15 chiffres.')
        supplier = scoped(Supplier, self.company, p['id']) if p.get('id') else Supplier(company=self.company)
        for key, value in data.items():
            setattr(supplier, key, value)
        supplier.save()
        return {'id': supplier.pk}

    def check_version(self, purchase, p):
        require(integer(p.get('version'), 'Version', 1) == purchase.version,
                'Cette facture a été modifiée. Actualisez la page avant de continuer.')

    def save_draft(self, p):
        purchase = scoped(Purchase, self.company, p['id']) if p.get('id') else None
        if purchase:
            require(purchase.status == 'draft', 'Seul un brouillon peut être modifié.')
            self.check_version(purchase, p)
        supplier = scoped(Supplier, self.company, p.get('supplier_id'))
        reference = label(p.get('supplier_reference'), 'Référence de facture fournisseur', limit=80)
        duplicate = Purchase.objects.filter(company=self.company, supplier=supplier, supplier_reference__iexact=reference)
        if purchase:
            duplicate = duplicate.exclude(pk=purchase.pk)
        require(not duplicate.exists(), 'Cette référence de facture existe déjà pour ce fournisseur (y compris les annulations).')
        invoice_date = calendar_date(p.get('invoice_date'), 'Date de facture')
        due_date = calendar_date(p.get('due_date'), 'Échéance', optional=True)
        require(due_date is None or due_date >= invoice_date, 'L’échéance doit suivre la date de facture.')
        items = p.get('items')
        require(isinstance(items, list) and 0 < len(items) <= 100, 'Ajoutez entre 1 et 100 lignes.')
        rows, seen = [], set()
        for item in items:
            require(isinstance(item, dict), 'Ligne de facture invalide.')
            product = scoped(Product, self.company, item.get('product_id'))
            require(product.pk not in seen, 'Regroupez les quantités d’un même produit sur une seule ligne.')
            seen.add(product.pk)
            quantity = integer(item.get('quantity'), 'Quantité', 1)
            price = money(item.get('price'), 'Prix d’achat HT')
            rate = integer(item.get('tax_bps', 0), 'Taux de taxe', 0, 10000)
            subtotal = quantity * price
            tax = int((Decimal(subtotal) * rate / 10000).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            rows.append(dict(product=product, name=product.name, sku=product.sku, quantity=quantity,
                             price=price, tax_bps=rate, subtotal=subtotal, tax=tax, total=subtotal + tax))
        subtotal, tax = sum(row['subtotal'] for row in rows), sum(row['tax'] for row in rows)
        require(subtotal + tax <= 1_000_000_000, 'Maximum par facture : 10 000 000 DH.')
        if not purchase:
            purchase = Purchase(company=self.company, number=self.company.next_purchase_number)
            self.company.next_purchase_number += 1
            self.company.save(update_fields=['next_purchase_number'])
        else:
            purchase.version += 1
        purchase.supplier, purchase.supplier_name = supplier, supplier.name
        purchase.supplier_reference, purchase.invoice_date, purchase.due_date = reference, invoice_date, due_date
        purchase.subtotal, purchase.tax, purchase.total = subtotal, tax, subtotal + tax
        purchase.note = label(p.get('note', ''), 'Note', False, 1000)
        purchase.save()
        PurchaseItem.objects.filter(company=self.company, purchase=purchase).delete()
        PurchaseItem.objects.bulk_create([PurchaseItem(company=self.company, purchase=purchase, **row) for row in rows])
        return {'id': purchase.pk, 'number': purchase.number, 'version': purchase.version, 'status': purchase.status}

    def receive(self, p):
        purchase = scoped(Purchase, self.company, p.get('purchase_id'))
        require(purchase.status == 'draft', 'Cette facture a déjà été réceptionnée ou annulée.')
        self.check_version(purchase, p)
        items = list(PurchaseItem.objects.filter(company=self.company, purchase=purchase))
        require(items, 'La facture ne contient aucun produit.')
        stamp = timezone.now()
        for item in items:
            product = scoped(Product, self.company, item.product_id)
            require(product.stock + item.quantity <= 1_000_000, f'Stock maximum dépassé : {product.name}.')
            product.stock += item.quantity
            product.save(update_fields=['stock'])
            Movement.objects.create(company=self.company, product=product, purchase=purchase,
                                    kind='purchase', quantity=item.quantity,
                                    note=f'Réception achat AC-{purchase.number:04d}', created_at=stamp)
        purchase.status, purchase.received_at = 'received', stamp
        purchase.version += 1
        purchase.save(update_fields=['status', 'received_at', 'version'])
        return {'id': purchase.pk, 'version': purchase.version, 'status': purchase.status}

    def cancel(self, p):
        purchase = scoped(Purchase, self.company, p.get('purchase_id'))
        require(purchase.status != 'cancelled', 'Cette facture est déjà annulée.')
        self.check_version(purchase, p)
        require(purchase.paid == 0, 'Une facture déjà réglée nécessite un avoir et un remboursement séparés.')
        from .accounting import ensure_source_can_cancel
        ensure_source_can_cancel(self.company, purchase=purchase)
        reason = label(p.get('reason'), 'Motif d’annulation', limit=300)
        stamp = timezone.now()
        if purchase.status == 'received':
            for item in PurchaseItem.objects.filter(company=self.company, purchase=purchase):
                product = scoped(Product, self.company, item.product_id)
                require(product.stock >= item.quantity, f'Stock insuffisant pour annuler : {product.name}.')
                product.stock -= item.quantity
                product.save(update_fields=['stock'])
                Movement.objects.create(company=self.company, product=product, purchase=purchase,
                                        kind='purchase_cancel', quantity=-item.quantity,
                                        note=f'Annulation achat AC-{purchase.number:04d} · {reason}', created_at=stamp)
        purchase.status, purchase.cancelled_at = 'cancelled', stamp
        purchase.cancellation_reason = reason
        purchase.version += 1
        purchase.save(update_fields=['status', 'cancelled_at', 'cancellation_reason', 'version'])
        return {'id': purchase.pk, 'version': purchase.version, 'status': purchase.status, 'reason': reason}

    def payment(self, p):
        purchase = scoped(Purchase, self.company, p.get('purchase_id'))
        require(purchase.status == 'received', 'Réceptionnez la facture avant de la régler.')
        amount = money(p.get('amount'))
        require(0 < amount <= purchase.total - purchase.paid, 'Le règlement doit être positif et ne pas dépasser le reste dû.')
        payment_date = calendar_date(p.get('payment_date'), 'Date de règlement')
        require(purchase.invoice_date <= payment_date <= timezone.localdate(),
                'Le règlement doit dater du jour ou d’une date passée, à partir de la date de facture.')
        method = p.get('method', 'Virement')
        require(method in ('Espèces', 'Virement', 'Carte', 'Chèque'), 'Mode de paiement invalide.')
        SupplierPayment.objects.create(company=self.company, purchase=purchase, amount=amount, method=method,
                                       payment_date=payment_date, reference=label(p.get('reference', ''), 'Référence', False, 80))
        purchase.paid += amount
        purchase.version += 1
        purchase.save(update_fields=['paid', 'version'])
        return {'id': purchase.pk, 'paid': purchase.paid, 'version': purchase.version}
