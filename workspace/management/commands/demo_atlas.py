import json
import os
import secrets
import tempfile
from pathlib import Path
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from server import Store
from workspace.models import Company, Organization, User


class Command(BaseCommand):
    help = 'Create a fresh local demonstration with generated credentials, never production/default passwords.'

    @transaction.atomic
    def handle(self, *args, **options):
        if settings.PRODUCTION or User.objects.exists():
            raise CommandError('La démonstration exige une base sans utilisateur, en environnement local.')
        org = Organization.objects.create(name='Atlas démonstration')
        password = secrets.token_urlsafe(18)
        user = User.objects.create_user(username='atlas-demo', password=password, first_name='Administrateur démo', organization=org, is_org_admin=True)
        company = Company.objects.create(organization=org, name='Société de démonstration')
        Company.objects.create(organization=org, name='Deuxième société', demo=True)
        with tempfile.TemporaryDirectory(prefix='atlas-demo-') as directory:
            path = Path(directory) / 'source.sqlite3'
            Store(path)
            call_command('import_prototype', str(path), company=company.pk, actor=user.username, verbosity=0)
        target = settings.BASE_DIR / 'data' / 'demo-login.json'
        fd = os.open(target, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as file:
            json.dump({'username': user.username, 'password': password, 'url': 'http://localhost:8001', 'purpose': 'Local demonstration only'}, file, indent=2)
        self.stdout.write(self.style.SUCCESS(f'Démonstration créée. Identifiants enregistrés dans {target}'))
