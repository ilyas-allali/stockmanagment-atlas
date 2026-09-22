'use strict';
window.AtlasVat = {
  selected:null,saving:false,key:null,
  reset(){this.selected=null;},
  data(){return state.vat.worksheets;},
  current(){return this.data().find(s=>s.id===this.selected);},
  can(){return AtlasPlatform.can('vat_write');},
  name(s){return s.cadence==='quarterly'?`T${Math.floor((Number(s.start.slice(5,7))-1)/3)+1} · ${s.start.slice(0,4)}`:`${date(s.start+'T12:00:00',{month:'long',year:'numeric'})}`;},
  status(s){return badge({draft:'À préparer',approved:'Approuvée en interne',voided:'Approbation annulée',discarded:'Abandonnée'}[s.status],s.status==='approved'?'':s.status==='draft'?'warning':'neutral');},
  button(action,text,id='',primary=false){return `<button type="button" class="btn ${primary?'primary':''}" data-action="vat-${action}" data-id="${id}">${esc(text)}</button>`;},
  basis(value){return value==='invoices'?'Factures':'Règlements';},
  view(){
    const s=this.current();
    return heading('PRÉPARER, VÉRIFIER, CONSERVER','Votre TVA','Une préparation par société, avec des montants justifiés et une revue explicite.',this.can()?this.button('new','Nouvelle préparation','',true):'')+
      `<div class="notice">Préparation interne pour revue comptable. Le choix des sources ne détermine pas le régime fiscal ni la déductibilité. L’export XML DGI et le dépôt ne sont pas encore disponibles.</div>`+(s?this.detail(s):this.list());
  },
  list(){
    const rows=this.data();
    return `<section class="card vat-list">${rows.length?`<div class="table-scroll"><table><thead><tr><th>Période</th><th>État</th><th>Lignes à vérifier</th><th class="amount">TVA à payer estimée</th><th></th></tr></thead><tbody>${rows.map(s=>`<tr><td><strong>${esc(this.name(s))}</strong><small class="purchase-sub">${s.start} → ${s.end}</small></td><td>${this.status(s)}</td><td>${s.totals.pending}</td><td class="amount">${currency(s.totals.payable)}</td><td>${this.button('open','Ouvrir',s.id)}</td></tr>`).join('')}</tbody></table></div>`:empty('Aucune préparation TVA','Créez une période, importez les sources puis vérifiez chaque montant.','','',true)}</section>`;
  },
  detail(s){
    const draft=s.status==='draft',edit=draft&&this.can(),t=s.totals,checks=s.diagnostics;
    return `<div class="toolbar vat-toolbar">${this.button('back','Toutes les périodes')}<h2>${esc(this.name(s))}</h2>${this.status(s)}</div><section class="stats-grid vat-stats">${statsCard('TVA collectée retenue',amount(t.sales_tax),'DH','Lignes vérifiées uniquement','sale',true)}${statsCard('TVA déductible retenue',amount(t.deductible_tax),'DH','Traitement validé ligne par ligne','check')}${statsCard('À payer estimé',amount(t.payable),'DH',`${t.pending} lignes restant à vérifier`,'wallet')}${statsCard('Crédit restant estimé',amount(t.carryforward),'DH','Report à confirmer dans la période suivante','arrows')}</section><section class="card vat-context"><div><strong>Sources proposées</strong><p>Ventes : ${this.basis(s.sales_basis)} · Achats : ${this.basis(s.purchase_basis)}<br>${s.start} → ${s.end}</p></div><div><strong>Crédit antérieur : ${currency(s.opening_credit)}</strong><p>${esc(s.credit_note||'Aucun crédit reporté')}</p></div>${edit?this.button('settings','Crédit & notes',s.id):''}</section>${t.pending?`<div class="notice">Calcul partiel : ${t.pending} lignes ne contribuent pas encore aux totaux. Une TVA retenue à zéro doit aussi être justifiée.</div>`:''}${checks?.stale.length?`<div class="notice">${checks.stale.length} sources ont changé ou disparu. Réimportez les sources modifiées et retirez les lignes devenues obsolètes.</div>`:''}${checks?.missing.length?`<div class="notice">${checks.missing.length} sources disponibles à importer avant approbation.</div>`:''}<div class="toolbar vat-toolbar"><p class="stat-note">${s.lines.length} lignes · montants en MAD</p><div class="vat-actions">${edit?`${this.button('import','Importer / actualiser',s.id)}${this.button('manual','Ajouter une ligne',s.id)}${this.button('approve','Approuver la préparation',s.id,true)}`:''}${s.status==='approved'&&AtlasPlatform.can('export')?`<a class="btn" href="/api/companies/${AtlasPlatform.companyId}/vat/export?id=${s.id}&format=csv">Exporter CSV</a><a class="btn" href="/api/companies/${AtlasPlatform.companyId}/vat/export?id=${s.id}&format=json">Télécharger l’instantané</a>`:''}</div></div><section class="card">${s.lines.length?`<div class="table-scroll"><table><thead><tr><th>Document / tiers</th><th>Origine</th><th class="amount">HT proposé</th><th class="amount">TVA source</th><th class="amount">TVA retenue</th><th>Revue</th><th></th></tr></thead><tbody>${s.lines.map(l=>`<tr data-vat-key="${esc(l.key)}"><td><strong>${esc(l.reference)}</strong><small class="purchase-sub">${esc(l.party)} · ${l.date}</small></td><td>${l.direction==='sale'?'Vente':'Achat'}<small class="purchase-sub">${l.source?this.basis(l.source.basis):'Manuelle'}</small></td><td class="amount">${currency(l.net)}</td><td class="amount">${currency(l.tax)}</td><td class="amount">${l.reviewed?currency(l.retained_tax):'—'}</td><td>${badge(l.reviewed?'Vérifiée':'À vérifier',l.reviewed?'':'warning')}${checks?.stale.includes(l.key)?'<small class="purchase-sub">Source obsolète</small>':''}</td><td><button class="btn" data-action="vat-line" data-key="${esc(l.key)}">${edit?'Vérifier':'Consulter'}</button></td></tr>`).join('')}</tbody></table></div>`:empty('Aucune ligne','Importez les sources de la période ou saisissez une ligne manuelle.','','',true)}</section>${s.note?`<div class="notice">${esc(s.note)}</div>`:''}${s.checksum?`<div class="vat-approval"><strong>Instantané approuvé le ${date(s.approved_at)}</strong><p>Société : ${esc(s.company_snapshot.name)} · IF : ${esc(s.company_snapshot.fiscal_id||'Non renseigné')} · ICE : ${esc(s.company_snapshot.ice||'Non renseigné')}</p><small>SHA-256 : ${esc(s.checksum)}</small><p>Approbation interne · aucune déclaration déposée par Atlas.</p></div>`:''}${s.void_reason?`<div class="notice">Motif d’annulation : ${esc(s.void_reason)}</div>`:''}${this.can()&&['draft','approved'].includes(s.status)?`<div class="vat-footer">${this.button('void',draft?'Abandonner la préparation':'Annuler l’approbation',s.id)}</div>`:''}`;
  },
  hidden(s){return `<input type="hidden" name="id" value="${s.id}"><input type="hidden" name="version" value="${s.version}">`;},
  form(title,subtitle,body,action,submit,wide=false){modal(title,subtitle,body,`${cancelButton}<button type="submit" class="btn primary">${submit}</button>`,wide,`vat-${action}-form`);this.key=crypto.randomUUID();},
  create(){
    const basis=(label,name)=>AtlasAccounting.select(label,name,[{id:'payments',name:'Règlements de la période'},{id:'invoices',name:'Factures de la période'}],'payments');
    this.form('Une préparation TVA','Sélectionnez la période et les sources à examiner.',`<div class="form-grid">${field('Premier jour de la période','start',AtlasPurchases.today().slice(0,7)+'-01','date')}${AtlasAccounting.select('Périodicité','cadence',[{id:'monthly',name:'Mensuelle'},{id:'quarterly',name:'Trimestrielle'}],'monthly')}${basis('Base d’import des ventes','sales_basis')}${basis('Base d’import des achats','purchase_basis')}</div><div class="notice">Ces bases servent à proposer les sources. Pour un règlement partiel, la TVA est répartie proportionnellement au TTC, avec arrondi cumulé au centime. Vérifiez le traitement applicable, notamment en présence de plusieurs taux ou de retenues.</div>`,'create','Créer la préparation',true);
  },
  line(key){
    const s=this.current(),l=s.lines.find(l=>l.key===key),edit=s.status==='draft'&&this.can();
    if(!edit){modal('Détail TVA',l.reference,`<div class="notice">${esc(l.party)} · ${l.date}<br>HT ${currency(l.net)} · TVA source ${currency(l.tax)} · TVA retenue ${currency(l.retained_tax)}<br>${esc(l.reason)}</div>`,cancelButton);return;}
    const source=l?.source;
    const fields=source?`<div class="notice">${esc(l.reference)} · ${esc(l.party)}<br>Date facture : ${source.invoice_date} · Date source : ${source.date}<br>HT proposé ${currency(l.net)} · TVA source ${currency(l.tax)}<br>${esc(source.method)} ${esc(source.payment_reference)}<br>IF : ${esc(source.fiscal_id||'Non renseigné')} · ICE : ${esc(source.ice||'Non renseigné')}</div>`:`<div class="form-grid">${AtlasAccounting.select('Nature','direction',[{id:'sale',name:'Vente / TVA collectée'},{id:'purchase',name:'Achat / TVA déductible'}],l?.direction||'purchase')}${field('Date de prise en compte','date',l?.date||s.start,'date')}${field('Référence du document','reference',l?.reference||'')}${field('Tiers','party',l?.party||'')}${field('Montant HT','net',((l?.net||0)/100).toFixed(2),'number',true,false,'min="0" max="10000000" step="0.01"')}${field('TVA du document','tax',((l?.tax||0)/100).toFixed(2),'number',true,false,'min="0" max="10000000" step="0.01"')}</div>`;
    this.form(l?'Vérifier la ligne':'Une ligne TVA manuelle','Indiquez le montant retenu et justifiez son traitement.',`${this.hidden(s)}<input type="hidden" name="key" value="${esc(l?.key||'')}">${fields}<div class="form-grid">${field('TVA retenue pour cette période','retained_tax',((l?.retained_tax||0)/100).toFixed(2),'number',true,true,`min="0" max="${source?l.tax/100:10000000}" step="0.01"`)}${field('Justification du traitement','reason',l?.reason||'','text',true,true)}</div>${l?`<button type="button" class="btn" data-action="vat-remove" data-key="${esc(l.key)}">Retirer cette ligne</button>`:''}`,'line','Enregistrer la revue',true);
  },
  settings(){const s=this.current();this.form('Crédit antérieur & notes',this.name(s),`${this.hidden(s)}<div class="form-grid">${field('Crédit antérieur à reprendre','opening_credit',(s.opening_credit/100).toFixed(2),'number',true,true,'min="0" max="10000000" step="0.01"')}${field('Origine et validation du crédit','credit_note',s.credit_note,'text',false,true)}${field('Note de préparation','note',s.note,'text',false,true)}</div><div class="notice">Le report est saisi et validé manuellement. Atlas ne reprend pas automatiquement le crédit d’une autre période.</div>`,'settings','Enregistrer les notes');},
  decision(action,key){
    const s=this.current(),approve=action==='approve',remove=action==='remove';
    this.form(approve?'Approuver cette préparation ?':remove?'Retirer cette ligne ?':s.status==='draft'?'Abandonner la préparation ?':'Annuler cette approbation ?',this.name(s),`${this.hidden(s)}${remove?`<input type="hidden" name="key" value="${esc(key)}">`:''}${approve?`<div class="notice">À payer estimé : ${currency(s.totals.payable)} · Crédit restant estimé : ${currency(s.totals.carryforward)}. L’instantané sera verrouillé. Cette action n’effectue aucun dépôt auprès de la DGI.</div><label class="vat-confirm"><input type="checkbox" name="confirmed" required> J’ai vérifié le périmètre, les traitements TVA, les montants et le crédit antérieur.</label>`:`<div class="notice">${remove?'Une source de la période retirée devra être réimportée avant approbation. Pour l’exclure du calcul, retenez plutôt zéro avec une justification.':'L’historique sera conservé. Une nouvelle préparation pourra être créée pour cette période. Vérifiez séparément les éventuels reports vers les périodes suivantes.'}</div>${field('Motif','reason','','text',true,true)}`}`,action,approve?'Confirmer l’approbation':remove?'Confirmer le retrait':'Confirmer l’annulation');
  },
  async mutate(action,data,form){
    if(this.saving)return;this.saving=true;AtlasPlatform.busy++;
    const company=AtlasPlatform.companyId,button=form?.querySelector('[type=submit]'),errorBox=form?.querySelector('.form-error');
    if(button)button.disabled=true;if(errorBox)errorBox.textContent='';
    try{
      const result=await api(`vat-${action}`,{...data,request_key:form?this.key:crypto.randomUUID()});
      if(company!==AtlasPlatform.companyId)return;
      this.selected=result.id;await refresh();if(company!==AtlasPlatform.companyId)return;
      if(form){dialog.close();main.focus({preventScroll:true});}
      toast(action==='import'?`${result.added} sources ajoutées · ${result.changed} actualisées.`:action==='approve'?'Préparation approuvée en interne.':'Enregistrement effectué.');
    }catch(error){if(errorBox&&form.isConnected)errorBox.textContent=error.message;else toast(error.message,true);}
    finally{this.saving=false;AtlasPlatform.busy--;if(button)button.disabled=false;}
  }
};
document.addEventListener('click',event=>{
  const b=event.target.closest('[data-action^="vat-"]');if(!b)return;
  event.preventDefault();event.stopImmediatePropagation();const v=AtlasVat;if(v.saving)return;
  const action=b.dataset.action.slice(4),s=v.current();
  ({new:()=>v.create(),open:()=>{v.selected=Number(b.dataset.id);render();},back:()=>{v.selected=null;render();},
    import:()=>v.mutate('import',{id:s.id,version:s.version}),manual:()=>v.line(),line:()=>v.line(b.dataset.key),
    settings:()=>v.settings(),approve:()=>v.decision('approve'),void:()=>v.decision('void'),remove:()=>v.decision('remove',b.dataset.key)})[action]?.();
});
document.addEventListener('submit',event=>{
  const form=event.target,name=form.getAttribute('id');if(!name?.startsWith('vat-'))return;
  event.preventDefault();event.stopImmediatePropagation();
  const data=Object.fromEntries(new FormData(form));if(name==='vat-approve-form')data.confirmed=data.confirmed==='on';
  AtlasVat.mutate(name.slice(4,-5),data,form);
});
