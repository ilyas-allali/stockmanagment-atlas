from django.db import migrations


RELATIONS = [('purchase', 'supplier', 'supplier'), ('purchaseitem', 'purchase', 'purchase'),
             ('purchaseitem', 'product', 'product'), ('supplierpayment', 'purchase', 'purchase'),
             ('movement', 'purchase', 'purchase')]


def add_constraints(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    for table, field, target in RELATIONS:
        schema_editor.execute(f'ALTER TABLE workspace_{table} ADD CONSTRAINT {table}_{field}_same_company '
                              f'FOREIGN KEY ({field}_id, company_id) REFERENCES workspace_{target} (id, company_id)')


def remove_constraints(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    for table, field, _ in RELATIONS:
        schema_editor.execute(f'ALTER TABLE workspace_{table} DROP CONSTRAINT {table}_{field}_same_company')


class Migration(migrations.Migration):
    dependencies = [('workspace', '0004_purchase_rules')]
    operations = [migrations.RunPython(add_constraints, remove_constraints)]
