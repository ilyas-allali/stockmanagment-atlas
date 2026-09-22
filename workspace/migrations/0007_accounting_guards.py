from django.db import migrations

RELATIONS = [('journalentry', 'journal', 'journal'), ('journalentry', 'period', 'accountingperiod'),
             ('journalentry', 'sale', 'sale'), ('journalentry', 'purchase', 'purchase'),
             ('journalentry', 'reversal_of', 'journalentry'), ('entryline', 'entry', 'journalentry'),
             ('entryline', 'account', 'account')]


def install(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    for table, field, target in RELATIONS:
        schema_editor.execute(f'ALTER TABLE workspace_{table} ADD CONSTRAINT {table}_{field}_same_company '
                              f'FOREIGN KEY ({field}_id, company_id) REFERENCES workspace_{target} (id, company_id)')
    schema_editor.execute('''
      CREATE FUNCTION atlas_entry_guard() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE n bigint; d numeric; c numeric;
      BEGIN
        IF TG_OP <> 'INSERT' AND OLD.status = 'posted' THEN
          RAISE EXCEPTION 'Posted entries are immutable' USING ERRCODE='23514';
        END IF;
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        IF NEW.status = 'posted' THEN
          SELECT count(*), sum(debit), sum(credit) INTO n, d, c FROM workspace_entryline WHERE entry_id=NEW.id;
          IF n < 2 OR d IS NULL OR d <> c OR d <= 0 THEN
            RAISE EXCEPTION 'Posted entry must balance' USING ERRCODE='23514';
          END IF;
          IF NOT EXISTS (SELECT 1 FROM workspace_accountingperiod WHERE id=NEW.period_id
                         AND company_id=NEW.company_id AND NOT closed AND NEW.date BETWEEN start AND "end") THEN
            RAISE EXCEPTION 'Posting period is closed or invalid' USING ERRCODE='23514';
          END IF;
          IF NOT EXISTS (SELECT 1 FROM workspace_journal WHERE id=NEW.journal_id AND active)
             OR EXISTS (SELECT 1 FROM workspace_entryline l JOIN workspace_account a ON a.id=l.account_id
                        WHERE l.entry_id=NEW.id AND NOT a.active) THEN
            RAISE EXCEPTION 'Inactive account or journal' USING ERRCODE='23514';
          END IF;
        END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER accounting_entry_guard BEFORE INSERT OR UPDATE OR DELETE ON workspace_journalentry
      FOR EACH ROW EXECUTE FUNCTION atlas_entry_guard();

      CREATE FUNCTION atlas_line_guard() RETURNS trigger LANGUAGE plpgsql AS $$
      DECLARE s text;
      BEGIN
        IF TG_OP <> 'INSERT' THEN
          SELECT status INTO s FROM workspace_journalentry WHERE id=OLD.entry_id FOR UPDATE;
          IF s = 'posted' THEN
            RAISE EXCEPTION 'Posted lines are immutable' USING ERRCODE='23514';
          END IF;
        END IF;
        IF TG_OP <> 'DELETE' THEN
          SELECT status INTO s FROM workspace_journalentry WHERE id=NEW.entry_id FOR UPDATE;
          IF s = 'posted' THEN
            RAISE EXCEPTION 'Cannot add lines to a posted entry' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END IF;
        RETURN OLD;
      END $$;
      CREATE TRIGGER accounting_line_guard BEFORE INSERT OR UPDATE OR DELETE ON workspace_entryline
      FOR EACH ROW EXECUTE FUNCTION atlas_line_guard();
    ''')


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute('DROP TRIGGER accounting_line_guard ON workspace_entryline; DROP FUNCTION atlas_line_guard(); '
                          'DROP TRIGGER accounting_entry_guard ON workspace_journalentry; DROP FUNCTION atlas_entry_guard();')
    for table, field, _ in RELATIONS:
        schema_editor.execute(f'ALTER TABLE workspace_{table} DROP CONSTRAINT {table}_{field}_same_company')


class Migration(migrations.Migration):
    dependencies = [('workspace', '0006_accounting')]
    operations = [migrations.RunPython(install, uninstall)]
