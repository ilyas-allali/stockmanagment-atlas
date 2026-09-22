from django.db import migrations


RELATIONS = [('sale', 'customer', 'customer'), ('saleitem', 'sale', 'sale'), ('saleitem', 'product', 'product'),
             ('movement', 'sale', 'sale'), ('movement', 'product', 'product'), ('payment', 'sale', 'sale')]


def add_constraints(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    for table, field, target in RELATIONS:
        schema_editor.execute(f'ALTER TABLE workspace_{table} ADD CONSTRAINT {table}_{field}_same_company '
                              f'FOREIGN KEY ({field}_id, company_id) REFERENCES workspace_{target} (id, company_id)')
    schema_editor.execute('''
        CREATE FUNCTION atlas_membership_org_check() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF (SELECT organization_id FROM workspace_user WHERE id=NEW.user_id)
              IS DISTINCT FROM (SELECT organization_id FROM workspace_company WHERE id=NEW.company_id) THEN
            RAISE EXCEPTION 'Company membership must remain in the user organization' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER membership_org_check BEFORE INSERT OR UPDATE ON workspace_membership
        FOR EACH ROW EXECUTE FUNCTION atlas_membership_org_check();
    ''')


def remove_constraints(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute('DROP TRIGGER membership_org_check ON workspace_membership; DROP FUNCTION atlas_membership_org_check();')
    for table, field, target in RELATIONS:
        schema_editor.execute(f'ALTER TABLE workspace_{table} DROP CONSTRAINT {table}_{field}_same_company')


class Migration(migrations.Migration):
    dependencies = [('workspace', '0001_initial')]
    operations = [migrations.RunPython(add_constraints, remove_constraints)]
