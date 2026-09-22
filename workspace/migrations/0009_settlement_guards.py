from django.db import migrations

RELATIONS = [('journalentry', 'customer_payment', 'payment'), ('journalentry', 'supplier_payment', 'supplierpayment'),
             ('journalentry', 'settlement_invoice', 'journalentry'),
             ('settlementmatch', 'invoice_entry', 'journalentry'), ('settlementmatch', 'payment_entry', 'journalentry')]


def install(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    for table, field, target in RELATIONS:
        schema_editor.execute(f'ALTER TABLE workspace_{table} ADD CONSTRAINT {table}_{field}_same_company '
                              f'FOREIGN KEY ({field}_id, company_id) REFERENCES workspace_{target} (id, company_id)')
    schema_editor.execute('''
    CREATE FUNCTION atlas_payment_entry_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE inv workspace_journalentry; a bigint; source_id bigint; counter bigint; n bigint;
    BEGIN
      PERFORM 1 FROM workspace_company WHERE id=NEW.company_id FOR UPDATE;
      IF NEW.status = 'discarded' THEN RETURN NEW; END IF;
      IF NEW.customer_payment_id IS NOT NULL OR NEW.supplier_payment_id IS NOT NULL THEN
        IF EXISTS (SELECT 1 FROM workspace_journalentry e WHERE e.company_id=NEW.company_id AND e.id<>NEW.id
          AND e.status<>'discarded' AND (e.customer_payment_id=NEW.customer_payment_id OR e.supplier_payment_id=NEW.supplier_payment_id)
          AND NOT EXISTS (SELECT 1 FROM workspace_journalentry r WHERE r.reversal_of_id=e.id AND r.status='posted')) THEN
          RAISE EXCEPTION 'Payment already transferred' USING ERRCODE='23514';
        END IF;
        SELECT * INTO inv FROM workspace_journalentry WHERE id=NEW.settlement_invoice_id AND company_id=NEW.company_id;
        IF inv.id IS NULL OR inv.status<>'posted' OR EXISTS (
          SELECT 1 FROM workspace_journalentry WHERE reversal_of_id=inv.id AND status<>'discarded') THEN
          RAISE EXCEPTION 'Payment requires an unreversed posted invoice' USING ERRCODE='23514';
        END IF;
        IF NEW.customer_payment_id IS NOT NULL THEN
          SELECT amount,sale_id INTO a,source_id FROM workspace_payment WHERE id=NEW.customer_payment_id AND company_id=NEW.company_id;
          IF inv.sale_id IS DISTINCT FROM source_id OR source_id IS NULL THEN
            RAISE EXCEPTION 'Payment invoice mismatch' USING ERRCODE='23514';
          END IF;
        ELSE
          SELECT amount,purchase_id INTO a,source_id FROM workspace_supplierpayment WHERE id=NEW.supplier_payment_id AND company_id=NEW.company_id;
          IF inv.purchase_id IS DISTINCT FROM source_id OR source_id IS NULL THEN
            RAISE EXCEPTION 'Payment invoice mismatch' USING ERRCODE='23514';
          END IF;
        END IF;
        IF NEW.status='posted' THEN
          SELECT count(*),min(account_id) INTO n,counter FROM workspace_entryline
            WHERE entry_id=inv.id AND ((inv.sale_id IS NOT NULL AND debit>0) OR (inv.purchase_id IS NOT NULL AND credit>0));
          IF n<>1 OR NEW.date<inv.date OR a<=0 OR (NEW.source_snapshot->>'total')::bigint IS DISTINCT FROM a
            OR (SELECT count(*) FROM workspace_entryline WHERE entry_id=NEW.id)<>2
            OR NOT EXISTS (SELECT 1 FROM workspace_entryline WHERE entry_id=NEW.id AND account_id=counter
              AND ((inv.sale_id IS NOT NULL AND credit=a AND debit=0) OR (inv.purchase_id IS NOT NULL AND debit=a AND credit=0)))
            OR NOT EXISTS (SELECT 1 FROM workspace_entryline WHERE entry_id=NEW.id AND account_id<>counter
              AND ((inv.sale_id IS NOT NULL AND debit=a AND credit=0) OR (inv.purchase_id IS NOT NULL AND credit=a AND debit=0))) THEN
            RAISE EXCEPTION 'Payment posting must settle the invoice counterparty' USING ERRCODE='23514';
          END IF;
        END IF;
      END IF;
      IF NEW.reversal_of_id IS NOT NULL THEN
        IF EXISTS (SELECT 1 FROM workspace_settlementmatch WHERE voided_at IS NULL
                   AND (invoice_entry_id=NEW.reversal_of_id OR payment_entry_id=NEW.reversal_of_id))
          OR EXISTS (SELECT 1 FROM workspace_journalentry e WHERE e.settlement_invoice_id=NEW.reversal_of_id AND e.status<>'discarded'
                     AND NOT EXISTS (SELECT 1 FROM workspace_journalentry r WHERE r.reversal_of_id=e.id AND r.status='posted')) THEN
          RAISE EXCEPTION 'Unmatch and reverse linked payments first' USING ERRCODE='23514';
        END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER accounting_payment_guard BEFORE INSERT OR UPDATE ON workspace_journalentry
      FOR EACH ROW EXECUTE FUNCTION atlas_payment_entry_guard();

    CREATE FUNCTION atlas_match_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE inv workspace_journalentry; pay workspace_journalentry; a bigint; used numeric;
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Matching history cannot be deleted' USING ERRCODE='23514'; END IF;
      PERFORM 1 FROM workspace_company WHERE id=NEW.company_id FOR UPDATE;
      IF TG_OP='UPDATE' THEN
        IF OLD.voided_at IS NOT NULL OR NEW.voided_at IS NULL OR
           (to_jsonb(NEW)-ARRAY['voided_at','voided_by_id','void_reason']) IS DISTINCT FROM
           (to_jsonb(OLD)-ARRAY['voided_at','voided_by_id','void_reason']) THEN
          RAISE EXCEPTION 'Only an audited unmatch is allowed' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
      END IF;
      IF NEW.voided_at IS NOT NULL THEN RAISE EXCEPTION 'New match must be active' USING ERRCODE='23514'; END IF;
      SELECT * INTO inv FROM workspace_journalentry WHERE id=NEW.invoice_entry_id AND company_id=NEW.company_id;
      SELECT * INTO pay FROM workspace_journalentry WHERE id=NEW.payment_entry_id AND company_id=NEW.company_id;
      IF inv.id IS NULL OR pay.id IS NULL OR inv.status<>'posted' OR pay.status<>'posted'
         OR pay.settlement_invoice_id IS DISTINCT FROM inv.id
         OR EXISTS (SELECT 1 FROM workspace_journalentry WHERE reversal_of_id IN (inv.id,pay.id) AND status<>'discarded') THEN
        RAISE EXCEPTION 'Match requires related unreversed posted entries' USING ERRCODE='23514';
      END IF;
      a := (pay.source_snapshot->>'total')::bigint;
      SELECT coalesce(sum(amount),0) INTO used FROM workspace_settlementmatch WHERE invoice_entry_id=inv.id AND voided_at IS NULL;
      IF a IS NULL OR NEW.amount<>a OR used+a>(inv.source_snapshot->>'total')::bigint THEN
        RAISE EXCEPTION 'Match amount exceeds invoice or differs from payment' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER accounting_match_guard BEFORE INSERT OR UPDATE OR DELETE ON workspace_settlementmatch
      FOR EACH ROW EXECUTE FUNCTION atlas_match_guard();
    ''')


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute('DROP TRIGGER accounting_match_guard ON workspace_settlementmatch; DROP FUNCTION atlas_match_guard(); '
                          'DROP TRIGGER accounting_payment_guard ON workspace_journalentry; DROP FUNCTION atlas_payment_entry_guard();')
    for table, field, _ in RELATIONS:
        schema_editor.execute(f'ALTER TABLE workspace_{table} DROP CONSTRAINT {table}_{field}_same_company')


class Migration(migrations.Migration):
    dependencies = [('workspace', '0008_settlements')]
    operations = [migrations.RunPython(install, uninstall)]
