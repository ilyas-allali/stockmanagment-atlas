import threading
import webbrowser
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from workspace.models import User


class Command(BaseCommand):
    help = 'Start the local Atlas web application, configuring its first administrator if needed.'

    def add_arguments(self, parser):
        parser.add_argument('--port', type=int, default=8001)
        parser.add_argument('--open', action='store_true')

    def handle(self, *args, **options):
        if settings.PRODUCTION:
            raise CommandError('Utilisez un serveur WSGI de production pour le déploiement.')
        call_command('migrate', interactive=False)
        if not User.objects.exists():
            call_command('setup_atlas')
        if options['open']:
            threading.Timer(1, lambda: webbrowser.open(f"http://localhost:{options['port']}")).start()
        call_command('runserver', f"127.0.0.1:{options['port']}", use_reloader=False)
