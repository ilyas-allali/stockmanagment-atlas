"""Temporary PostgreSQL database for browser tests. Never touches the business database."""
import json
import os
import re
import sys
from urllib.parse import urlparse, urlunparse
import psycopg
from psycopg import sql

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
action, name = sys.argv[1:]
if not re.fullmatch(r'atlas_browser_[a-f0-9]{12}', name):
    raise RuntimeError('Invalid temporary database name')
from atlas import settings as atlas_settings  # Load the private .env consistently with Django.
base = urlparse(os.environ['DATABASE_URL'])
if base.hostname not in ('localhost', '127.0.0.1') or os.environ.get('ATLAS_ENV') == 'production':
    raise RuntimeError('Browser fixture only operates on a local development PostgreSQL server')
with psycopg.connect(urlunparse(base._replace(path='/postgres')), autocommit=True) as conn:
    if action == 'drop':
        conn.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(name)))
        sys.exit()
    conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
os.environ['DATABASE_URL'] = urlunparse(base._replace(path='/' + name))
os.environ['DJANGO_SETTINGS_MODULE'] = 'atlas.settings'
import django
django.setup()
from django.core.management import call_command
from workspace.models import Company, Membership, Organization, Product, User
call_command('migrate', verbosity=0, interactive=False)
org = Organization.objects.create(name='Groupe navigateur')
a = Company.objects.create(organization=org, name='Atlas Casablanca')
b = Company.objects.create(organization=org, name='Atlas Rabat')
owner = User.objects.create_user(username='browser-owner', password='Browser-Atlas-Password-729!', organization=org, is_org_admin=True)
reader = User.objects.create_user(username='browser-reader', password='Browser-Atlas-Password-729!', organization=org)
Membership.objects.create(user=reader, company=a, role='viewer')
product = Product.objects.create(company=a, sku='CASA-001', name='Produit Casablanca', category='Tests', cost=100, price=1250, stock=10, minimum=3)
Product.objects.create(company=b, sku='RABAT-001', name='Produit Rabat', category='Tests', cost=100, price=500, stock=20, minimum=3)
print(json.dumps({'database_url':os.environ['DATABASE_URL'], 'a':a.pk, 'b':b.pk, 'product':product.pk}))
