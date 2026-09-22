"""Explicit, read-only source import into an empty company; original SQLite stays untouched."""
import sqlite3
from datetime import datetime
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from workspace.models import Company, Customer, Movement, Payment, Product, Sale, SaleItem, User, Supplier, Purchase, Account, Journal, AccountingPeriod, JournalEntry, VatWorksheet
from workspace.services import log


def stamp(value):
    dt = datetime.fromisoformat(value)
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


class Command(BaseCommand):
    help = 'Import a prototype SQLite database into an empty company, preserving source data.'

    def add_arguments(self, parser):
        parser.add_argument('source', type=Path)
        parser.add_argument('--company', type=int, required=True)
        parser.add_argument('--actor', required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        company = Company.objects.select_for_update().filter(pk=options['company']).first()
        actor = User.objects.filter(username=options['actor'], is_org_admin=True, is_active=True).first()
        if not company or not actor or company.organization_id != actor.organization_id:
            raise CommandError('Société et administrateur de la même organisation requis.')
        if any(model.objects.filter(company=company).exists() for model in (Product, Customer, Sale, Movement, Payment, Supplier, Purchase, Account, Journal, AccountingPeriod, JournalEntry, VatWorksheet)):
            raise CommandError('La société doit être vide. Aucun remplacement automatique.')
        path = options['source'].resolve()
        if not path.is_file():
            raise CommandError('Base source introuvable.')
        source = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        source.row_factory = sqlite3.Row
        try:
            source.execute('BEGIN')
            products, customers, sales = {}, {}, {}
            for row in source.execute('SELECT * FROM products ORDER BY id'):
                data = dict(row); old = data.pop('id')
                products[old] = Product.objects.create(company=company, **data)
            for row in source.execute('SELECT * FROM customers ORDER BY id'):
                data = dict(row); old = data.pop('id')
                customers[old] = Customer.objects.create(company=company, **data)
            for row in source.execute('SELECT * FROM sales ORDER BY id'):
                data = dict(row); old = data.pop('id')
                customer_id = data.pop('customer_id')
                data['customer'] = customers[customer_id] if customer_id else None
                data['created_at'] = stamp(data['created_at'])
                sales[old] = Sale.objects.create(company=company, number=old, **data)
            for row in source.execute('SELECT * FROM sale_items ORDER BY id'):
                data = dict(row); data.pop('id')
                data['sale'] = sales[data.pop('sale_id')]
                data['product'] = products[data.pop('product_id')]
                SaleItem.objects.create(company=company, **data)
            for row in source.execute('SELECT * FROM movements ORDER BY id'):
                data = dict(row); data.pop('id')
                sid = data.pop('sale_id')
                data['sale'] = sales[sid] if sid else None
                data['product'] = products[data.pop('product_id')]
                data['created_at'] = stamp(data['created_at'])
                Movement.objects.create(company=company, **data)
            for row in source.execute('SELECT * FROM payments ORDER BY id'):
                data = dict(row); data.pop('id')
                data['sale'] = sales[data.pop('sale_id')]
                data['created_at'] = stamp(data['created_at'])
                Payment.objects.create(company=company, **data)
            profile = dict(source.execute('SELECT * FROM settings WHERE id=1').fetchone())
            for key in ['name', 'address', 'phone', 'demo']:
                setattr(company, key, profile[key])
            company.next_sale_number = max(sales, default=0) + 1
            company.save()
            log(company, actor, 'prototype.imported', {'products': len(products), 'customers': len(customers), 'sales': len(sales)})
        except (sqlite3.Error, KeyError, ValueError) as exc:
            raise CommandError(f'Import annulé : {exc}') from exc
        finally:
            source.close()
        self.stdout.write(self.style.SUCCESS(f'Import terminé : {len(products)} produits, {len(sales)} ventes. Source inchangée.'))
