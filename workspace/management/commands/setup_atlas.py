import getpass
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from workspace.models import Company, Organization, User
from workspace.services import log


class Command(BaseCommand):
    help = 'Create the first organization administrator and company (interactive; no default password).'

    def handle(self, *args, **options):
        if User.objects.exists():
            raise CommandError('Atlas est déjà configuré. Connectez-vous pour gérer les sociétés et utilisateurs.')
        username = input('Identifiant administrateur : ').strip()
        name = input('Nom de votre organisation : ').strip()
        company = input('Nom de votre première société : ').strip()
        password = getpass.getpass('Mot de passe (10 caractères minimum) : ')
        if password != getpass.getpass('Confirmer le mot de passe : '):
            raise CommandError('Les mots de passe ne correspondent pas.')
        if not username or not name or not company:
            raise CommandError('Tous les champs sont obligatoires.')
        with transaction.atomic():
            org = Organization.objects.create(name=name[:160])
            user = User(username=username, organization=org, is_org_admin=True)
            validate_password(password, user)
            user.set_password(password)
            user.full_clean()
            user.save()
            c = Company.objects.create(organization=org, name=company[:160])
            log(c, user, 'company.created')
        self.stdout.write(self.style.SUCCESS('Espace créé. Connectez-vous avec votre identifiant.'))
