from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute('''
    CREATE FUNCTION atlas_vat_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'VAT review history cannot be deleted' USING ERRCODE='23514'; END IF;
      PERFORM 1 FROM workspace_company WHERE id=NEW.company_id FOR UPDATE;
      IF TG_OP='UPDATE' AND OLD.status<>'draft' THEN
        IF OLD.status<>'approved' OR NEW.status<>'voided' OR NEW.version<>OLD.version+1 OR
          (to_jsonb(NEW)-ARRAY['status','version','voided_at','voided_by_id','void_reason']) IS DISTINCT FROM
          (to_jsonb(OLD)-ARRAY['status','version','voided_at','voided_by_id','void_reason']) THEN
          RAISE EXCEPTION 'Approved VAT snapshots are immutable; only audited voiding is allowed' USING ERRCODE='23514';
        END IF;
      END IF;
      IF NEW.status IN ('draft','approved') AND EXISTS (SELECT 1 FROM workspace_vatworksheet
          WHERE company_id=NEW.company_id AND id<>NEW.id AND status IN ('draft','approved')
          AND start<=NEW."end" AND "end">=NEW.start) THEN
        RAISE EXCEPTION 'VAT periods overlap' USING ERRCODE='23514';
      END IF;
      IF NEW.start<>date_trunc('month',NEW.start)::date OR
        (NEW.cadence='quarterly' AND extract(month from NEW.start)::int NOT IN (1,4,7,10)) OR
        NEW."end"<>(NEW.start + CASE WHEN NEW.cadence='monthly' THEN interval '1 month' ELSE interval '3 months' END - interval '1 day')::date THEN
        RAISE EXCEPTION 'VAT period must be a calendar month or quarter' USING ERRCODE='23514';
      END IF;
      IF jsonb_typeof(NEW.lines)<>'array' THEN RAISE EXCEPTION 'VAT lines must be an array' USING ERRCODE='23514'; END IF;
      IF NEW.status='approved' THEN
        IF EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.lines) l WHERE l->'reviewed' IS DISTINCT FROM 'true'::jsonb)
          OR NEW.approved_snapshot->'lines' IS DISTINCT FROM NEW.lines THEN
          RAISE EXCEPTION 'All VAT lines must be reviewed and snapshotted' USING ERRCODE='23514';
        END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER vat_worksheet_guard BEFORE INSERT OR UPDATE OR DELETE ON workspace_vatworksheet
      FOR EACH ROW EXECUTE FUNCTION atlas_vat_guard();
    ''')


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute('DROP TRIGGER vat_worksheet_guard ON workspace_vatworksheet; DROP FUNCTION atlas_vat_guard();')


class Migration(migrations.Migration):
    dependencies = [('workspace', '0010_vat_worksheets')]
    operations = [migrations.RunPython(install, uninstall)]
