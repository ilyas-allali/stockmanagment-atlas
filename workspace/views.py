import csv
import hashlib
import io
import json
import mimetypes
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.http import FileResponse, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from server import ValidationError, integer, label, require, safe_csv
from .models import AuditEvent, Company, LoginAttempt, Membership, Organization, ROLES, User
from .services import ACTION_CAPABILITY, CAPABILITIES, CommercialService, log


def error(message, status):
    return JsonResponse({'error': message}, status=status)


def endpoint(authenticated=True):
    def decorate(fn):
        @wraps(fn)
        def wrapped(request, *args, **kwargs):
            if authenticated and not request.user.is_authenticated:
                return error('Connectez-vous pour accéder à cet espace.', 401)
            try:
                return fn(request, *args, **kwargs)
            except ValidationError as exc:
                return error(str(exc), 400)
            except DjangoValidationError as exc:
                return error(' '.join(exc.messages), 400)
            except IntegrityError:
                return error('Référence ou identifiant déjà utilisé, ou relation invalide.', 400)
        return wrapped
    return decorate


def body(request):
    require(request.content_type == 'application/json', 'Format JSON attendu.')
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValidationError('JSON invalide.')
    require(isinstance(data, dict), 'Un objet JSON est attendu.')
    return data


def csrf_failure(request, reason=''):
    return error('Session de sécurité expirée. Actualisez la page.', 403)


@ensure_csrf_cookie
def index(request):
    return FileResponse((settings.BASE_DIR / 'web/index.html').open('rb'), content_type='text/html; charset=utf-8')


def asset(request, asset):
    if asset not in ('app.js', 'platform.js', 'purchases.js', 'accounting.js', 'settlements.js', 'vat.js', 'vat.css', 'styles.css', 'platform.css', 'purchases.css', 'accounting.css', 'favicon.svg'):
        return error('Page introuvable.', 404)
    return FileResponse((settings.BASE_DIR / 'web' / asset).open('rb'), content_type=mimetypes.guess_type(asset)[0])


def role_for(user, company):
    if company.organization_id != user.organization_id:
        return None
    if user.is_org_admin:
        return 'admin'
    return Membership.objects.filter(user=user, company=company).values_list('role', flat=True).first()


def company_list(user):
    rows = Company.objects.filter(organization=user.organization).order_by('name', 'id')
    if not user.is_org_admin:
        rows = rows.filter(membership__user=user)
    return [{'id': c.pk, 'name': c.name, 'role': role_for(user, c), 'permissions': sorted(CAPABILITIES[role_for(user, c)])} for c in rows]


def identity(request):
    user = request.user
    result = {'authenticated': user.is_authenticated, 'csrf_token': get_token(request)}
    if user.is_authenticated:
        result.update(user={'id': user.pk, 'username': user.username, 'name': user.first_name or user.username,
                            'is_org_admin': user.is_org_admin}, companies=company_list(user),
                      organization={'name': user.organization.name, 'company_limit': user.organization.company_limit})
    else:
        result['setup_required'] = not User.objects.exists()
    return result


@endpoint(authenticated=False)
def auth(request, action):
    if request.method == 'GET' and action == 'me':
        return JsonResponse(identity(request))
    if request.method != 'POST':
        return error('Méthode non autorisée.', 405)
    p = body(request)
    if action == 'login':
        username = label(p.get('username', ''), 'Identifiant', limit=150)
        password = p.get('password')
        require(isinstance(password, str) and len(password) <= 1024, 'Mot de passe invalide.')
        keys = [hashlib.sha256(value.encode()).hexdigest() for value in (
            'ip:' + request.META.get('REMOTE_ADDR', ''), 'user:' + username.casefold())]
        with transaction.atomic():
            attempts = []
            for key in sorted(keys):
                LoginAttempt.objects.get_or_create(key=key, defaults={'window_start': timezone.now()})
                attempt = LoginAttempt.objects.select_for_update().get(key=key)
                if attempt.window_start < timezone.now() - timedelta(minutes=15):
                    attempt.failures = 0
                    attempt.window_start = timezone.now()
                attempts.append(attempt)
            if any(a.failures >= 10 for a in attempts):
                return error('Trop de tentatives. Réessayez dans 15 minutes.', 429)
            user = authenticate(request, username=username, password=password)
            if user is None:
                for attempt in attempts:
                    attempt.failures += 1
                    attempt.save()
                return error('Identifiant ou mot de passe incorrect.', 401)
            for attempt in attempts:
                attempt.save()
        login(request, user)
        return JsonResponse(identity(request))
    if not request.user.is_authenticated:
        return error('Connexion requise.', 401)
    if action == 'logout':
        logout(request)
        return JsonResponse(identity(request))
    if action == 'password':
        require(request.user.check_password(p.get('current_password', '')), 'Mot de passe actuel incorrect.')
        password = p.get('password')
        require(isinstance(password, str) and len(password) <= 1024, 'Mot de passe invalide.')
        validate_password(password, request.user)
        request.user.set_password(password)
        request.user.save(update_fields=['password'])
        update_session_auth_hash(request, request.user)
        return JsonResponse({'ok': True, 'csrf_token': get_token(request)})
    return error('Action inconnue.', 404)


@endpoint()
def companies(request):
    if request.method == 'GET':
        return JsonResponse({'companies': company_list(request.user)})
    if request.method != 'POST':
        return error('Méthode non autorisée.', 405)
    if not request.user.is_org_admin:
        return error('Seul l’administrateur de l’organisation peut créer une société.', 403)
    p = body(request)
    with transaction.atomic():
        org = Organization.objects.select_for_update().get(pk=request.user.organization_id)
        require(org.company_limit is None or Company.objects.filter(organization=org).count() < org.company_limit,
                'Le nombre de sociétés autorisé a été atteint.')
        c = Company.objects.create(organization=org, name=label(p.get('name'), 'Société'))
        CommercialService(c, request.user).settings(p)
        log(c, request.user, 'company.created')
    return JsonResponse({'id': c.pk, 'companies': company_list(request.user)}, status=201)


@endpoint()
def users(request):
    if not request.user.is_org_admin:
        return error('Administration de l’organisation requise.', 403)
    if request.method == 'GET':
        rows = []
        for user in User.objects.filter(organization=request.user.organization).order_by('username'):
            rows.append({'id': user.pk, 'username': user.username, 'name': user.first_name, 'active': user.is_active,
                         'is_org_admin': user.is_org_admin, 'memberships': list(Membership.objects.filter(user=user).values('company_id', 'role'))})
        return JsonResponse({'users': rows, 'roles': dict(ROLES)})
    if request.method != 'POST':
        return error('Méthode non autorisée.', 405)
    p = body(request)
    with transaction.atomic():
        Organization.objects.select_for_update().get(pk=request.user.organization_id)
        memberships = p.get('memberships', [])
        require(isinstance(memberships, list) and len(memberships) <= 500, 'Liste des accès invalide.')
        allowed = set(Company.objects.filter(organization=request.user.organization).values_list('id', flat=True))
        normalized = {}
        for m in memberships:
            require(isinstance(m, dict), 'Accès invalide.')
            cid = integer(m.get('company_id'), 'Société', 1, 2**53-1)
            require(cid in allowed and m.get('role') in dict(ROLES) and cid not in normalized, 'Société ou rôle invalide.')
            normalized[cid] = m['role']
        if p.get('id'):
            user = User.objects.filter(organization=request.user.organization, pk=integer(p['id'], 'Utilisateur', 1)).first()
            require(user and not user.is_org_admin, 'Cet utilisateur ne peut pas être modifié ici.')
            require(isinstance(p.get('active', True), bool), 'État utilisateur invalide.')
            user.is_active = p.get('active', True)
            user.first_name = label(p.get('name', ''), 'Nom', False, 150)
            user.save(update_fields=['is_active', 'first_name'])
        else:
            username = label(p.get('username'), 'Identifiant', limit=150)
            user = User(organization=request.user.organization, username=username,
                        first_name=label(p.get('name', ''), 'Nom', False, 150))
            password = p.get('password')
            require(isinstance(password, str) and len(password) <= 1024, 'Mot de passe invalide.')
            validate_password(password, user)
            user.set_password(password)
            user.full_clean()
            user.save()
        previous = set(Membership.objects.filter(user=user).values_list('company_id', flat=True))
        Membership.objects.filter(user=user).delete()
        for cid, role in normalized.items():
            Membership.objects.create(user=user, company_id=cid, role=role)
        for cid in previous | set(normalized):
            log(Company.objects.get(pk=cid), request.user, 'user.access_changed', {'user_id': user.pk, 'active': user.is_active, 'role': normalized.get(cid)})
    return JsonResponse({'id': user.pk})


@endpoint()
def company_api(request, company_id, action):
    company = Company.objects.filter(pk=company_id, organization=request.user.organization).first()
    role = role_for(request.user, company) if company else None
    if role is None:
        return error('Société introuvable ou accès retiré.', 404)
    capabilities = CAPABILITIES[role]
    service = CommercialService(company, request.user)
    if request.method == 'POST':
        if action not in ACTION_CAPABILITY:
            return error('Action inconnue.', 404)
        if ACTION_CAPABILITY[action] not in capabilities:
            return error('Votre rôle ne permet pas cette action.', 403)
        return JsonResponse(service.mutate(action, body(request)))
    if request.method != 'GET':
        return error('Méthode non autorisée.', 405)
    if action in ('vat/state', 'vat/export'):
        if 'vat_read' not in capabilities or (action == 'vat/export' and 'export' not in capabilities):
            return error('Votre rôle ne permet pas cet accès TVA.', 403)
        from .vat import VatService
        from .models import VatWorksheet
        from .services import scoped
        if action == 'vat/state':
            return JsonResponse(VatService(company, request.user).state())
        sheet = scoped(VatWorksheet, company, request.GET.get('id'))
        require(sheet.status == 'approved', 'Seule une préparation approuvée peut être exportée.')
        kind = request.GET.get('format', 'csv')
        require(kind in ('csv', 'json'), 'Export interne CSV ou JSON attendu. XML DGI non disponible.')
        snapshot = sheet.approved_snapshot
        if kind == 'json':
            response = JsonResponse({'snapshot': snapshot, 'sha256': sheet.checksum})
        else:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['Préparation TVA interne — non déposée', safe_csv(snapshot['company']['name']), snapshot['start'], snapshot['end'], sheet.checksum])
            writer.writerow(['source', 'sens', 'date', 'reference', 'tiers', 'ht', 'tva_source', 'tva_retenue', 'justification'])
            for row in snapshot['lines']:
                writer.writerow([safe_csv(row[k]) for k in ('key', 'direction', 'date', 'reference', 'party')] +
                    [f"{row[k]/100:.2f}" for k in ('net', 'tax', 'retained_tax')] + [safe_csv(row['reason'])])
            writer.writerow([])
            for key, value in snapshot['totals'].items():
                if key != 'pending': writer.writerow([key, f'{value/100:.2f}'])
            response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
        log(company, request.user, 'export.vat', {'id':sheet.pk, 'sha256':sheet.checksum, 'format':kind})
        response['Content-Disposition'] = f'attachment; filename="atlas-{company.pk}-tva-{sheet.pk}.{kind}"'
        return response
    if action in ('accounting/state', 'accounting/reports', 'accounting/export', 'accounting/reconciliation-export'):
        if 'accounting_read' not in capabilities or (action in ('accounting/export', 'accounting/reconciliation-export') and 'export' not in capabilities):
            return error('Votre rôle ne permet pas cet accès comptable.', 403)
        from .accounting import AccountingService
        accounting = AccountingService(company, request.user)
        if action == 'accounting/state':
            return JsonResponse(accounting.state())
        if action == 'accounting/reconciliation-export':
            rows = accounting.state()['reconciliation']
            output = io.StringIO()
            writer = csv.writer(output)
            fields = ['number', 'party', 'invoice_status', 'total', 'paid', 'posted_payments', 'matched', 'payment_gap', 'accounting_remaining']
            writer.writerow(fields)
            for row in rows:
                writer.writerow([('' if row[k] is None else f"{row[k] / 100:.2f}") if k in fields[3:] else safe_csv(row[k]) for k in fields])
            log(company, request.user, 'export.reconciliation')
            response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="atlas-{company.pk}-lettrage.csv"'
            return response
        report = accounting.reports(request.GET)
        if action == 'accounting/reports':
            return JsonResponse(report)
        kind = request.GET.get('report', 'trial_balance')
        require(kind in ('trial_balance', 'journal', 'ledger'), 'Rapport inconnu.')
        output = io.StringIO()
        writer = csv.writer(output)
        if kind == 'trial_balance':
            fields = ['code', 'name', 'opening', 'debit', 'credit', 'closing']
            rows = report['trial_balance']
        else:
            fields = ['date', 'journal', 'number', 'reference', 'memo', 'code', 'name', 'label', 'debit', 'credit']
            if kind == 'ledger':
                fields.append('balance')
            rows = sorted(report['ledger'], key=lambda r: (r['code'], r['date'], r['journal'], r['number'])) if kind == 'ledger' else report['ledger']
        writer.writerow(fields)
        for row in rows:
            writer.writerow([f"{row[k] / 100:.2f}" if k in ('opening', 'debit', 'credit', 'closing', 'balance') else safe_csv(row[k]) for k in fields])
        log(company, request.user, 'export.accounting', {'report': kind, 'period_id': report['period_id'], 'date_from': str(report['date_from']), 'date_to': str(report['date_to'])})
        response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="atlas-{company.pk}-{kind}.csv"'
        return response
    if action == 'state':
        data = service.state()
        data.update(role=role, permissions=sorted(capabilities))
        return JsonResponse(data)
    if action == 'audit':
        if 'audit' not in capabilities:
            return error('Accès au journal non autorisé.', 403)
        rows = list(AuditEvent.objects.filter(company=company).order_by('-id').values('id', 'actor__username', 'action', 'details', 'created_at')[:200])
        return JsonResponse({'events': rows})
    if action == 'export/products':
        if 'export' not in capabilities:
            return error('Export non autorisé.', 403)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['sku', 'name', 'category', 'cost', 'price', 'stock', 'minimum'])
        for p in service.state()['products']:
            writer.writerow([safe_csv(p['sku']), safe_csv(p['name']), safe_csv(p['category']), f"{p['cost']/100:.2f}", f"{p['price']/100:.2f}", p['stock'], p['minimum']])
        log(company, request.user, 'export.products')
        response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="atlas-{company.pk}-produits.csv"'
        return response
    if action == 'backup':
        if 'settings' not in capabilities:
            return error('Export de société réservé à son administrateur.', 403)
        with transaction.atomic():
            data = service.state()
            from .accounting import AccountingService
            data['accounting'] = AccountingService(company, request.user).state()
            from .vat import VatService
            data['vat'] = VatService(company, request.user).state()
            data['movements'] = list(company.movement_set.order_by('id').values())
            data['audit'] = list(AuditEvent.objects.filter(company=company).order_by('id').values())
            data['operations'] = list(company.operationrequest_set.order_by('id').values())
            data.update(format='atlas-company-export', version=5, exported_at=timezone.now())
            log(company, request.user, 'export.company')
        response = JsonResponse(data)
        response['Content-Disposition'] = f'attachment; filename="atlas-societe-{company.pk}.json"'
        return response
    if action == 'export/purchases':
        if 'export' not in capabilities:
            return error('Export non autorisé.', 403)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['numero', 'fournisseur', 'reference', 'date_facture', 'echeance', 'statut', 'ht', 'taxe', 'ttc', 'regle', 'reste_du'])
        for p in service.state()['purchases']:
            writer.writerow([f"AC-{p['number']:04d}", safe_csv(p['supplier_name']), safe_csv(p['supplier_reference']),
                             p['invoice_date'], p['due_date'] or '', p['status'],
                             *[f"{p[k] / 100:.2f}" for k in ('subtotal', 'tax', 'total', 'paid')],
                             f"{(p['total'] - p['paid']) / 100:.2f}" if p['status'] == 'received' else '0.00'])
        log(company, request.user, 'export.purchases')
        response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="atlas-{company.pk}-achats.csv"'
        return response
    return error('Action inconnue.', 404)
