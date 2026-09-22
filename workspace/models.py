from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone


class Organization(models.Model):
    name = models.CharField(max_length=160)
    company_limit = models.PositiveIntegerField(null=True, blank=True)


class User(AbstractUser):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    is_org_admin = models.BooleanField(default=False)


class Company(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    name = models.CharField(max_length=160)
    address = models.CharField(max_length=500, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    fiscal_id = models.CharField(max_length=40, blank=True)
    ice = models.CharField(max_length=15, blank=True)
    demo = models.BooleanField(default=False)
    next_sale_number = models.PositiveIntegerField(default=1)
    next_purchase_number = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)


ROLES = [('admin', 'Administrateur société'), ('commercial', 'Commercial'), ('accountant', 'Comptable'),
         ('supervisor', 'Superviseur'), ('viewer', 'Lecture seule')]


class Membership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLES)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'company'], name='unique_company_membership'),
                       models.CheckConstraint(condition=Q(role__in=[x[0] for x in ROLES]), name='valid_membership_role')]


class CompanyRecord(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)

    class Meta:
        abstract = True


class Product(CompanyRecord):
    sku = models.CharField(max_length=40)
    name = models.CharField(max_length=160)
    category = models.CharField(max_length=60)
    cost = models.PositiveBigIntegerField()
    price = models.PositiveBigIntegerField()
    stock = models.PositiveIntegerField(default=0)
    minimum = models.PositiveIntegerField(default=5)

    class Meta:
        constraints = [models.UniqueConstraint(Lower('sku'), 'company', name='unique_company_sku'),
                       models.UniqueConstraint(fields=['id', 'company'], name='product_company_pair')]


class Customer(CompanyRecord):
    name = models.CharField(max_length=160)
    email = models.CharField(max_length=160, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    city = models.CharField(max_length=80, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='customer_company_pair')]


class Sale(CompanyRecord):
    number = models.PositiveIntegerField()
    request_key = models.CharField(max_length=80)
    customer = models.ForeignKey(Customer, null=True, on_delete=models.PROTECT)
    customer_name = models.CharField(max_length=160)
    created_at = models.DateTimeField()
    subtotal = models.PositiveBigIntegerField()
    tax_bps = models.PositiveIntegerField(default=0)
    tax = models.PositiveBigIntegerField()
    total = models.PositiveBigIntegerField()
    paid = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=12, default='active')
    note = models.CharField(max_length=1000, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['company', 'request_key'], name='unique_company_sale_request'),
                       models.UniqueConstraint(fields=['company', 'number'], name='unique_company_sale_number'),
                       models.UniqueConstraint(fields=['id', 'company'], name='sale_company_pair'),
                       models.CheckConstraint(condition=Q(paid__lte=models.F('total')), name='sale_not_overpaid'),
                       models.CheckConstraint(condition=Q(status__in=['active', 'cancelled']), name='valid_sale_status')]


class SaleItem(CompanyRecord):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    name = models.CharField(max_length=160)
    sku = models.CharField(max_length=40)
    quantity = models.PositiveIntegerField()
    price = models.PositiveBigIntegerField()
    cost = models.PositiveBigIntegerField()


class Movement(CompanyRecord):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    sale = models.ForeignKey(Sale, null=True, on_delete=models.PROTECT)
    purchase = models.ForeignKey('Purchase', null=True, on_delete=models.PROTECT)
    kind = models.CharField(max_length=20)
    quantity = models.IntegerField()
    note = models.CharField(max_length=500)
    created_at = models.DateTimeField()


class Payment(CompanyRecord):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT)
    amount = models.PositiveBigIntegerField()
    created_at = models.DateTimeField()
    method = models.CharField(max_length=20)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='payment_company_pair')]


class OperationRequest(CompanyRecord):
    key = models.CharField(max_length=80)
    action = models.CharField(max_length=30)
    result = models.JSONField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['company', 'key'], name='unique_company_operation')]


class AuditEvent(CompanyRecord):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=50)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    failures = models.PositiveIntegerField(default=0)
    window_start = models.DateTimeField()


class Supplier(CompanyRecord):
    name = models.CharField(max_length=160)
    email = models.CharField(max_length=160, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    city = models.CharField(max_length=80, blank=True)
    address = models.CharField(max_length=500, blank=True)
    fiscal_id = models.CharField(max_length=40, blank=True)
    ice = models.CharField(max_length=15, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='supplier_company_pair')]


class Purchase(CompanyRecord):
    number = models.PositiveIntegerField()
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    supplier_name = models.CharField(max_length=160)
    supplier_reference = models.CharField(max_length=80)
    invoice_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, default='draft')
    version = models.PositiveIntegerField(default=1)
    subtotal = models.PositiveBigIntegerField()
    tax = models.PositiveBigIntegerField()
    total = models.PositiveBigIntegerField()
    paid = models.PositiveBigIntegerField(default=0)
    note = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    received_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['id', 'company'], name='purchase_company_pair'),
            models.UniqueConstraint(fields=['company', 'number'], name='unique_company_purchase_number'),
            models.UniqueConstraint(Lower('supplier_reference'), 'supplier', 'company', name='unique_supplier_invoice'),
            models.CheckConstraint(condition=Q(status__in=['draft', 'received', 'cancelled']), name='valid_purchase_status'),
            models.CheckConstraint(condition=Q(paid__lte=models.F('total')), name='purchase_not_overpaid'),
            models.CheckConstraint(condition=Q(status='received') | Q(paid=0), name='only_received_purchase_paid'),
            models.CheckConstraint(condition=Q(total=models.F('subtotal') + models.F('tax')), name='purchase_total_matches'),
            models.CheckConstraint(condition=Q(due_date__isnull=True) | Q(due_date__gte=models.F('invoice_date')), name='purchase_due_date_order'),
        ]


class PurchaseItem(CompanyRecord):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    name = models.CharField(max_length=160)
    sku = models.CharField(max_length=40)
    quantity = models.PositiveIntegerField()
    price = models.PositiveBigIntegerField()
    tax_bps = models.PositiveIntegerField(default=0)
    subtotal = models.PositiveBigIntegerField()
    tax = models.PositiveBigIntegerField()
    total = models.PositiveBigIntegerField()

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name='purchase_positive_quantity'),
                       models.CheckConstraint(condition=Q(tax_bps__lte=10000), name='purchase_tax_limit')]


class SupplierPayment(CompanyRecord):
    purchase = models.ForeignKey(Purchase, on_delete=models.PROTECT)
    amount = models.PositiveBigIntegerField()
    method = models.CharField(max_length=20)
    payment_date = models.DateField()
    reference = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='supplier_payment_positive'),
                       models.UniqueConstraint(fields=['id', 'company'], name='supplierpayment_company_pair')]


class Account(CompanyRecord):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=160)
    active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(Lower('code'), 'company', name='unique_company_account'),
                       models.UniqueConstraint(fields=['id', 'company'], name='account_company_pair')]


class Journal(CompanyRecord):
    code = models.CharField(max_length=12)
    name = models.CharField(max_length=160)
    active = models.BooleanField(default=True)
    next_number = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(Lower('code'), 'company', name='unique_company_journal'),
                       models.UniqueConstraint(fields=['id', 'company'], name='journal_company_pair')]


class AccountingPeriod(CompanyRecord):
    name = models.CharField(max_length=100)
    start = models.DateField()
    end = models.DateField()
    closed = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='period_company_pair'),
                       models.CheckConstraint(condition=Q(end__gte=models.F('start')), name='period_dates_order')]


class JournalEntry(CompanyRecord):
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT)
    period = models.ForeignKey(AccountingPeriod, on_delete=models.PROTECT)
    date = models.DateField()
    memo = models.CharField(max_length=300)
    reference = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=12, default='draft')
    version = models.PositiveIntegerField(default=1)
    number = models.PositiveIntegerField(null=True)
    journal_code = models.CharField(max_length=12, blank=True)
    sale = models.ForeignKey(Sale, null=True, on_delete=models.PROTECT)
    purchase = models.ForeignKey(Purchase, null=True, on_delete=models.PROTECT)
    customer_payment = models.ForeignKey(Payment, null=True, on_delete=models.PROTECT)
    supplier_payment = models.ForeignKey(SupplierPayment, null=True, on_delete=models.PROTECT)
    settlement_invoice = models.ForeignKey('self', null=True, on_delete=models.PROTECT, related_name='settlement_entries')
    source_snapshot = models.JSONField(default=dict)
    reversal_of = models.ForeignKey('self', null=True, on_delete=models.PROTECT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    posted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['id', 'company'], name='entry_company_pair'),
            models.UniqueConstraint(fields=['journal', 'number'], name='unique_journal_entry_number'),
            models.UniqueConstraint(fields=['company', 'sale'], condition=~Q(status='discarded'), name='one_sale_transfer'),
            models.UniqueConstraint(fields=['company', 'purchase'], condition=~Q(status='discarded'), name='one_purchase_transfer'),
            models.UniqueConstraint(fields=['reversal_of'], condition=~Q(status='discarded'), name='one_entry_reversal'),
            models.CheckConstraint(condition=Q(status__in=['draft', 'posted', 'discarded']), name='valid_entry_status'),
            models.CheckConstraint(condition=(
                Q(sale__isnull=True, purchase__isnull=True, customer_payment__isnull=True) |
                Q(sale__isnull=True, purchase__isnull=True, supplier_payment__isnull=True) |
                Q(sale__isnull=True, customer_payment__isnull=True, supplier_payment__isnull=True) |
                Q(purchase__isnull=True, customer_payment__isnull=True, supplier_payment__isnull=True)), name='one_accounting_source'),
            models.CheckConstraint(condition=(
                Q(customer_payment__isnull=True, supplier_payment__isnull=True, settlement_invoice__isnull=True) |
                (Q(settlement_invoice__isnull=False) & (Q(customer_payment__isnull=False) | Q(supplier_payment__isnull=False)))), name='payment_invoice_required'),
            models.CheckConstraint(condition=Q(reversal_of__isnull=True) | Q(sale__isnull=True, purchase__isnull=True, customer_payment__isnull=True, supplier_payment__isnull=True), name='reversal_without_source'),
            models.CheckConstraint(condition=(Q(status='posted', number__isnull=False, posted_at__isnull=False, posted_by__isnull=False) |
                                              (~Q(status='posted') & Q(number__isnull=True, posted_at__isnull=True, posted_by__isnull=True))), name='entry_posting_metadata'),
        ]


class EntryLine(CompanyRecord):
    entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    account_code = models.CharField(max_length=20)
    account_name = models.CharField(max_length=160)
    label = models.CharField(max_length=300, blank=True)
    debit = models.PositiveBigIntegerField(default=0)
    credit = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [models.CheckConstraint(condition=(Q(debit__gt=0, credit=0) | Q(credit__gt=0, debit=0)), name='line_one_positive_side')]


class SettlementMatch(CompanyRecord):
    invoice_entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name='invoice_matches')
    payment_entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name='payment_matches')
    amount = models.PositiveBigIntegerField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='+')
    voided_at = models.DateTimeField(null=True)
    void_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['payment_entry'], condition=Q(voided_at__isnull=True), name='one_active_payment_match'),
            models.CheckConstraint(condition=Q(amount__gt=0), name='settlement_match_positive'),
            models.CheckConstraint(condition=(Q(voided_at__isnull=True, voided_by__isnull=True, void_reason='') |
                (Q(voided_at__isnull=False, voided_by__isnull=False) & ~Q(void_reason=''))), name='match_void_metadata'),
        ]


class VatWorksheet(CompanyRecord):
    start = models.DateField()
    end = models.DateField()
    cadence = models.CharField(max_length=10)
    sales_basis = models.CharField(max_length=10)
    purchase_basis = models.CharField(max_length=10)
    status = models.CharField(max_length=10, default='draft')
    version = models.PositiveIntegerField(default=1)
    lines = models.JSONField(default=list)
    opening_credit = models.PositiveBigIntegerField(default=0)
    credit_note = models.CharField(max_length=300, blank=True)
    note = models.CharField(max_length=1000, blank=True)
    company_snapshot = models.JSONField(default=dict)
    approved_snapshot = models.JSONField(default=dict)
    checksum = models.CharField(max_length=64, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='+')
    approved_at = models.DateTimeField(null=True)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='+')
    voided_at = models.DateTimeField(null=True)
    void_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(status__in=['draft', 'approved', 'voided', 'discarded']), name='vat_valid_status'),
            models.CheckConstraint(condition=Q(cadence__in=['monthly', 'quarterly']), name='vat_valid_cadence'),
            models.CheckConstraint(condition=Q(sales_basis__in=['invoices', 'payments']) & Q(purchase_basis__in=['invoices', 'payments']), name='vat_valid_basis'),
            models.CheckConstraint(condition=Q(end__gte=models.F('start')), name='vat_date_order'),
            models.CheckConstraint(condition=Q(status__in=['draft', 'discarded'], approved_by__isnull=True, approved_at__isnull=True, checksum='') |
                (Q(status__in=['approved', 'voided']) & Q(approved_by__isnull=False, approved_at__isnull=False) & ~Q(checksum='')), name='vat_approval_metadata'),
            models.CheckConstraint(condition=(~Q(status__in=['voided', 'discarded']) & Q(voided_by__isnull=True, voided_at__isnull=True, void_reason='')) |
                (Q(status__in=['voided', 'discarded'], voided_by__isnull=False, voided_at__isnull=False) & ~Q(void_reason='')), name='vat_void_metadata'),
        ]
