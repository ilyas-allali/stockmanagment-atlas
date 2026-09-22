'use strict';
window.AtlasAccounting = {
  tab:'entries', entryFilter:'all', lines:[], key:null, report:null, reportKind:'trial_balance', reportAccount:'', reportParams:null, saving:false,
  reset(){this.tab='entries';this.entryFilter='all';this.lines=[];this.report=null;this.reportParams=null;this.reportAccount='';},
  invalidateReport(){this.report=null;},
  data(){return state.accounting;},
  can(){return AtlasPlatform.can('accounting_write');},
  code(e){return e.status==='posted'?`${e.journal_code}-${String(e.number).padStart(6,'0')}`:`BR-${e.id}`;},
  status(e){return badge({draft:'À vérifier',posted:'Comptabilisée',discarded:'Abandonnée'}[e.status],e.status==='draft'?'warning':e.status==='discarded'?'neutral':'');},
  button(action,text,id='',primary=false){return `<button type="button" class="btn ${primary?'primary':''}" data-action="accounting-${action}" data-id="${id}">${esc(text)}</button>`;},
  select(title,name,rows,value='',optional=false){return `<label class="field"><span>${esc(title)}${optional?'':' *'}</span><select aria-label="${esc(title)}" name="${name}" ${optional?'':'required'}>${optional?'<option value="">Non utilisé</option>':''}${rows.map(r=>`<option value="${r.id}" ${String(r.id)===String(value)?'selected':''}>${esc(r.code?`${r.code} · ${r.name}`:r.name)}</option>`).join('')}</select></label>`;},
  totals(e){const lines=this.data().lines.filter(l=>l.entry_id===e.id);return {debit:sum(lines,'debit'),credit:sum(lines,'credit')};},
  view(){
    const d=this.data(),drafts=d.entries.filter(e=>e.status==='draft'),posted=d.entries.filter(e=>e.status==='posted');
    return heading('DES CHIFFRES QUE VOUS POUVEZ SUIVRE','Votre comptabilité','Préparez, vérifiez, puis comptabilisez. Chaque montant garde sa trace.',this.can()?this.button('new-entry','Nouvelle écriture','',true):'')+
      `<section class="stats-grid accounting-stats">${statsCard('À vérifier',drafts.length,'écritures','Les brouillons sont exclus des rapports','edit',true)}${statsCard('Comptabilisées',posted.length,'écritures','Écritures verrouillées après validation','shield')}${statsCard('Comptes actifs',d.accounts.filter(a=>a.active).length,'comptes','Plan de comptes de cette société','building')}${statsCard('Périodes ouvertes',d.periods.filter(p=>!p.closed).length,'périodes','Dates de saisie autorisées','calendar')}</section>`+
      `<div class="tabs accounting-tabs" role="group" aria-label="Sections comptables">${[['entries','Écritures'],['transfer','Transfert des factures'],['settlements','Règlements & lettrage'],['reports','Rapports'],['setup','Paramétrage']].map(([id,name])=>`<button class="tab ${this.tab===id?'active':''}" data-action="accounting-tab" data-tab="${id}">${name}</button>`).join('')}</div>`+
      ({entries:()=>this.entriesView(),transfer:()=>this.transferView(),settlements:()=>this.settlementsView(),reports:()=>this.reportsView(),setup:()=>this.setupView()}[this.tab])();
  },
  entriesView(){
    const rows=this.data().entries.filter(e=>this.entryFilter==='all'||e.status===this.entryFilter).slice().reverse();
    return `<div class="toolbar"><p class="stat-note">${rows.length} écritures · montants en MAD</p><label class="field"><span>État des écritures</span><select id="accounting-entry-filter">${[['all','Tous les états'],['draft','À vérifier'],['posted','Comptabilisées'],['discarded','Abandonnées']].map(([id,name])=>`<option value="${id}" ${this.entryFilter===id?'selected':''}>${name}</option>`).join('')}</select></label></div><section class="card">${rows.length?`<div class="table-scroll"><table><thead><tr><th>Écriture</th><th>Date</th><th>Libellé</th><th>Origine</th><th>État</th><th class="amount">Débit</th><th class="amount">Crédit</th></tr></thead><tbody>${rows.map(e=>{const t=this.totals(e);return `<tr><td><button class="edit-link" data-action="accounting-view" data-id="${e.id}">${this.code(e)}</button></td><td>${date(e.date+'T12:00:00')}</td><td>${esc(e.memo)}<small class="purchase-sub">${esc(e.reference)}</small></td><td>${e.sale_id?'Vente':e.purchase_id?'Achat':e.customer_payment_id?'Règlement client':e.supplier_payment_id?'Règlement fournisseur':e.reversal_of_id?'Contrepassation':'Manuelle'}</td><td>${this.status(e)}${t.debit!==t.credit?'<small class="purchase-sub">À équilibrer</small>':''}</td><td class="amount">${currency(t.debit)}</td><td class="amount">${currency(t.credit)}</td></tr>`;}).join('')}</tbody></table></div>`:empty('Aucune écriture pour le moment','Configurez vos comptes, un journal et une période, puis transférez une facture ou saisissez une écriture.')}</section>`;
  },
  setupView(){
    const d=this.data();
    const master=(title,key,kind)=>`<section class="card"><div class="card-head"><h2>${title}</h2>${this.can()?this.button(`new-${kind}`,'Ajouter'):''}</div>${d[key].length?`<div class="table-scroll"><table><thead><tr><th>Code</th><th>Libellé</th><th>État</th><th></th></tr></thead><tbody>${d[key].map(a=>`<tr><td>${esc(a.code)}</td><td>${esc(a.name)}</td><td>${badge(a.active?'Actif':'Désactivé',a.active?'':'neutral')}</td><td>${this.can()?this.button(`edit-${kind}`,'Modifier',a.id):''}</td></tr>`).join('')}</tbody></table></div>`:empty(`Aucun ${kind==='account'?'compte':'journal'}`,'Ajoutez les éléments utilisés par votre comptable.','','',true)}</section>`;
    return `<div class="notice">Utilisez le plan de comptes et les journaux validés par votre comptable. Atlas ne choisit pas de comptes fiscaux à votre place.</div><div class="accounting-setup">${master('Plan de comptes','accounts','account')}${master('Journaux','journals','journal')}</div><section class="card"><div class="card-head"><h2>Périodes comptables</h2>${this.can()?this.button('new-period','Nouvelle période'):''}</div>${d.periods.length?`<div class="table-scroll"><table><thead><tr><th>Période</th><th>Début</th><th>Fin</th><th>État</th><th></th></tr></thead><tbody>${d.periods.map(p=>`<tr><td>${esc(p.name)}</td><td>${date(p.start+'T12:00:00')}</td><td>${date(p.end+'T12:00:00')}</td><td>${badge(p.closed?'Fermée':'Ouverte',p.closed?'neutral':'')}</td><td>${this.can()?this.button('period-state',p.closed?'Rouvrir':'Fermer la période',p.id):''}</td></tr>`).join('')}</tbody></table></div>`:empty('Définissez une période','Les périodes ne doivent pas se chevaucher.','','',true)}</section><p class="table-count">La fermeture bloque les nouvelles écritures de la période. Elle ne réalise pas une clôture annuelle ni un report automatique des soldes.</p>`;
  },
  masterModal(kind,id){
    const obj=this.data()[kind==='account'?'accounts':'journals'].find(x=>x.id===id),account=kind==='account';
    modal(obj?`Modifier ${account?'le compte':'le journal'}`:`${account?'Un nouveau compte':'Un nouveau journal'}`,'Les codes déjà utilisés sont conservés dans l’historique.',`<input type="hidden" name="id" value="${obj?.id||''}"><div class="form-grid">${field('Code','code',obj?.code||'','text',true,false,`pattern="[A-Za-z0-9][A-Za-z0-9.-]*"`)}<label class="field"><span>État</span><select name="active"><option value="true" ${obj?.active!==false?'selected':''}>Actif</option><option value="false" ${obj?.active===false?'selected':''}>Désactivé</option></select></label>${field('Libellé','name',obj?.name||'','text',true,true)}</div>`,`${cancelButton}<button class="btn primary" type="submit">Enregistrer ${account?'le compte':'le journal'}</button>`,false,`accounting-${kind}-form`);
    this.key=crypto.randomUUID();
  },
  periodModal(){
    modal('Une période comptable','Choisissez des dates sans chevauchement avec une période existante.',`<div class="form-grid">${field('Nom de la période','name','','text',true,true)}${field('Début de période','start','','date')}${field('Fin de période','end','','date')}</div>`,`${cancelButton}<button class="btn primary" type="submit">Créer la période</button>`,false,'accounting-period-form');this.key=crypto.randomUUID();
  },
  periodState(id){
    const p=this.data().periods.find(p=>p.id===id);
    modal(p.closed?'Rouvrir la période':'Fermer la période',p.name,`<input type="hidden" name="id" value="${id}"><input type="hidden" name="closed" value="${!p.closed}"><input type="hidden" name="expected_closed" value="${p.closed}"><div class="notice">${p.closed?'La saisie et la comptabilisation seront de nouveau autorisées pour ces dates.':'Tous les brouillons doivent être comptabilisés ou abandonnés. Les écritures déjà comptabilisées resteront consultables.'}</div>${field('Motif','reason','','text',true,true)}`,`${cancelButton}<button class="btn primary" type="submit">Confirmer ${p.closed?'la réouverture':'la fermeture'}</button>`,false,'accounting-period-state-form');this.key=crypto.randomUUID();
  },
  ready(){
    const d=this.data();
    if(d.accounts.filter(a=>a.active).length>=2&&d.journals.some(j=>j.active)&&d.periods.some(p=>!p.closed))return true;
    modal('Préparez votre comptabilité','Un minimum de configuration est nécessaire.',`<div class="notice">Ajoutez au moins deux comptes actifs, un journal actif et une période ouverte dans Paramétrage.</div>`,`${cancelButton}${this.button('setup','Ouvrir le paramétrage','',true)}`);return false;
  },
  contextFields(e={},withReference=true){
    const d=this.data(),periods=d.periods.filter(p=>!p.closed),period=periods.find(p=>p.id===e.period_id)||periods.find(p=>p.start<=AtlasPurchases.today()&&p.end>=AtlasPurchases.today())||periods[0];
    const day=e.date||(period&&period.start<=AtlasPurchases.today()&&period.end>=AtlasPurchases.today()?AtlasPurchases.today():period?.start)||'';
    return this.select('Journal','journal_id',d.journals.filter(j=>j.active),e.journal_id)+this.select('Période','period_id',periods,period?.id)+field('Date comptable','date',day,'date')+(withReference?field('Référence','reference',e.reference||'','text',false):'');
  },
  edit(id){
    if(!this.ready())return;
    const e=this.data().entries.find(e=>e.id===id);
    if(e&&(e.status!=='draft'||e.sale_id||e.purchase_id||e.customer_payment_id||e.supplier_payment_id||e.reversal_of_id))return this.details(id);
    this.lines=e?this.data().lines.filter(l=>l.entry_id===id).map(l=>({account_id:l.account_id,label:l.label,debit:(l.debit/100).toFixed(2),credit:(l.credit/100).toFixed(2)})):[{account_id:this.data().accounts.find(a=>a.active).id,label:'',debit:'0',credit:'0'},{account_id:this.data().accounts.filter(a=>a.active)[1].id,label:'',debit:'0',credit:'0'}];
    modal(e?`Modifier ${this.code(e)}`:'Une nouvelle écriture','Les brouillons restent modifiables et sont exclus des rapports.',`<input type="hidden" name="id" value="${e?.id||''}"><input type="hidden" name="version" value="${e?.version||''}"><div class="form-grid">${this.contextFields(e||{})}${field('Libellé de l’écriture','memo',e?.memo||'','text',true,true)}</div><div id="accounting-lines"></div><div class="accounting-line-footer">${this.button('add-line','Ajouter une ligne')}<strong id="accounting-entry-totals" aria-live="polite"></strong></div>`,`${cancelButton}<button type="submit" class="btn primary">Enregistrer le brouillon comptable</button>`,true,'accounting-entry-form');this.key=crypto.randomUUID();this.renderLines();
  },
  renderLines(){
    const accounts=this.data().accounts.filter(a=>a.active);
    document.querySelector('#accounting-lines').innerHTML=this.lines.map((l,i)=>`<div class="accounting-line" data-index="${i}"><label class="field"><span>Compte ${i+1}</span><select aria-label="Compte ${i+1}" data-acc-field="account_id" required>${accounts.map(a=>`<option value="${a.id}" ${a.id===Number(l.account_id)?'selected':''}>${esc(a.code+' · '+a.name)}</option>`).join('')}</select></label><label class="field"><span>Libellé ligne ${i+1}</span><input data-acc-field="label" maxlength="300" value="${esc(l.label)}"></label><label class="field"><span>Débit ligne ${i+1}</span><input type="number" min="0" max="10000000" step="0.01" required data-acc-field="debit" value="${esc(l.debit)}"></label><label class="field"><span>Crédit ligne ${i+1}</span><input type="number" min="0" max="10000000" step="0.01" required data-acc-field="credit" value="${esc(l.credit)}"></label><button type="button" class="icon-btn" data-action="accounting-remove-line" data-id="${i}" aria-label="Retirer la ligne ${i+1}">${icon('trash')}</button></div>`).join('');this.lineTotals();
  },
  lineTotals(){const debit=this.lines.reduce((n,l)=>n+(AtlasPurchases.cents(l.debit)||0),0),credit=this.lines.reduce((n,l)=>n+(AtlasPurchases.cents(l.credit)||0),0);document.querySelector('#accounting-entry-totals').textContent=`Débit ${currency(debit)} · Crédit ${currency(credit)} · Écart ${currency(debit-credit)}`;},
  transferView(){
    const d=this.data(),sources=[...state.sales.filter(s=>s.status==='active'&&s.total>0).map(s=>({kind:'sale',id:s.id,number:`VT-${String(s.number).padStart(4,'0')}`,party:s.customer_name,total:s.total})),...state.purchases.filter(p=>p.status==='received'&&p.total>0).map(p=>({kind:'purchase',id:p.id,number:AtlasPurchases.code(p),party:p.supplier_name,total:p.total}))];
    return `<div class="notice">Le transfert prépare les écritures des factures. Choisissez leurs comptes, puis vérifiez le brouillon avant de le comptabiliser. Retrouvez ensuite les paiements dans Règlements & lettrage.</div><section class="card">${sources.length?`<div class="table-scroll"><table><thead><tr><th>Facture</th><th>Tiers</th><th class="amount">Total TTC</th><th>Comptabilité</th><th></th></tr></thead><tbody>${sources.map(s=>{const e=d.entries.find(e=>e[`${s.kind}_id`]===s.id&&e.status!=='discarded');return `<tr><td>${s.number}<small class="purchase-sub">${s.kind==='sale'?'Vente':'Achat'}</small></td><td>${esc(s.party)}</td><td class="amount">${currency(s.total)}</td><td>${e?this.status(e):badge('À transférer','neutral')}</td><td>${e?this.button('view',this.code(e),e.id):this.can()?`<button class="btn small" data-action="accounting-transfer" data-kind="${s.kind}" data-id="${s.id}">Préparer le transfert</button>`:'—'}</td></tr>`;}).join('')}</tbody></table></div>`:empty('Aucune facture à transférer','Les ventes actives et les achats réceptionnés apparaîtront ici.')}</section>`;
  },
  transferModal(kind,id){
    if(!this.ready())return;
    const source=(kind==='sale'?state.sales:state.purchases).find(s=>s.id===id),accounts=this.data().accounts.filter(a=>a.active),sourceDate=kind==='sale'?new Intl.DateTimeFormat('sv-SE',{timeZone:'Africa/Casablanca'}).format(new Date(source.created_at)):source.invoice_date;
    const period=this.data().periods.find(p=>!p.closed&&p.start<=sourceDate&&p.end>=sourceDate);
    modal('Préparer le transfert',`${kind==='sale'?'Vente':'Achat'} · ${kind==='sale'?source.customer_name:source.supplier_name}`,`<input type="hidden" name="kind" value="${kind}"><input type="hidden" name="source_id" value="${id}"><div class="notice">HT ${currency(source.subtotal)} · Taxe ${currency(source.tax)} · TTC ${currency(source.total)}<br>Date du document : ${date(sourceDate+'T12:00:00')}. Vérifiez la date comptable et les comptes retenus.</div><div class="form-grid">${this.contextFields({period_id:period?.id,date:period?sourceDate:undefined},false)}${this.select(kind==='sale'?'Compte client / tiers':'Compte fournisseur / tiers','counter_account_id',accounts)}${this.select(kind==='sale'?'Compte de produits HT':'Compte de charges HT','net_account_id',accounts,accounts[1]?.id)}${source.tax?this.select('Compte de taxe selon votre traitement comptable','tax_account_id',accounts,accounts[2]?.id):''}</div><div class="notice">La sélection du compte de taxe ne détermine pas sa déductibilité ni sa période de déclaration. Un transfert ne modifie pas le stock.</div>`,`${cancelButton}<button class="btn primary" type="submit">Créer le brouillon de transfert</button>`,true,'accounting-transfer-form');this.key=crypto.randomUUID();
  },
  linesTable(lines){return `<div class="table-scroll"><table><thead><tr><th>Compte</th><th>Libellé</th><th class="amount">Débit</th><th class="amount">Crédit</th></tr></thead><tbody>${lines.map(l=>`<tr><td>${esc(l.account_code)}<small class="purchase-sub">${esc(l.account_name)}</small></td><td>${esc(l.label)}</td><td class="amount">${currency(l.debit)}</td><td class="amount">${currency(l.credit)}</td></tr>`).join('')}</tbody></table></div>`;},
  details(id){
    const d=this.data(),e=d.entries.find(e=>e.id===id);if(!e)return;
    const lines=d.lines.filter(l=>l.entry_id===id),t=this.totals(e),reversal=d.entries.find(r=>r.reversal_of_id===e.id&&r.status!=='discarded');
    modal(`Écriture ${this.code(e)}`,e.memo,`<div class="sale-details-meta"><div><small>ÉTAT</small>${this.status(e)}</div><div><small>DATE COMPTABLE</small><strong>${date(e.date+'T12:00:00')}</strong></div><div><small>PÉRIODE</small><strong>${esc(d.periods.find(p=>p.id===e.period_id)?.name)}</strong></div></div>${e.reference?`<div class="notice">Référence : ${esc(e.reference)}</div>`:''}${e.sale_id||e.purchase_id?`<div class="notice">Source : ${esc(e.source_snapshot.reference)} · ${esc(e.source_snapshot.party)} · Total ${currency(e.source_snapshot.total)}. Pour changer les comptes d’un transfert non comptabilisé, abandonnez ce brouillon puis transférez à nouveau la facture.</div>`:''}${e.settlement_invoice_id?`<div class="notice">Règlement de ${esc(e.source_snapshot.invoice_reference)} · ${esc(e.source_snapshot.party)} · ${currency(e.source_snapshot.total)}. ${this.button('view','Voir la facture comptable',e.settlement_invoice_id)}</div>`:''}${e.reversal_of_id?`<div class="notice">Contrepassation de ${esc(this.code(d.entries.find(x=>x.id===e.reversal_of_id)))}. La facture commerciale n’est pas annulée automatiquement.</div>`:''}${reversal?`<div class="notice">Contrepassation liée : ${this.button('view',this.code(reversal),reversal.id)} ${this.status(reversal)}</div>`:''}${this.linesTable(lines)}<div class="detail-totals"><div class="total-row"><span>Total débit</span><strong>${currency(t.debit)}</strong></div><div class="total-row"><span>Total crédit</span><strong>${currency(t.credit)}</strong></div><div class="total-row final"><span>Écart</span><strong>${currency(t.debit-t.credit)}</strong></div></div>${e.status==='draft'&&this.can()?`<div class="accounting-detail-actions">${this.button('discard','Abandonner le brouillon',id)}</div>`:''}`,`${cancelButton}${this.can()&&e.status==='draft'?`${!e.sale_id&&!e.purchase_id&&!e.customer_payment_id&&!e.supplier_payment_id&&!e.reversal_of_id?this.button('edit-entry','Modifier',id):''}${this.button('post','Comptabiliser',id,true)}`:''}${this.can()&&e.status==='posted'&&!e.reversal_of_id&&!reversal?this.button('reverse','Préparer une contrepassation',id):''}`,true);
  },
  decision(action,id){
    const e=this.data().entries.find(e=>e.id===id),post=action==='post';
    modal(post?'Comptabiliser cette écriture ?':'Abandonner ce brouillon ?',this.code(e),`<input type="hidden" name="id" value="${id}"><input type="hidden" name="version" value="${e.version}"><div class="notice">${post?'Après validation, l’écriture sera numérotée, incluse dans les rapports et verrouillée. Une correction nécessitera une contrepassation.':'Le brouillon sera conservé dans l’historique et exclu des rapports. Sa facture pourra être transférée à nouveau.'}</div>${post?'':field('Motif','reason','','text',true,true)}`,`${cancelButton}<button class="btn primary" type="submit">${post?'Confirmer la comptabilisation':'Confirmer l’abandon'}</button>`,false,`accounting-${action}-form`);this.key=crypto.randomUUID();
  },
  reverse(id){
    if(!this.ready())return;
    const e=this.data().entries.find(e=>e.id===id);
    modal('Préparer une contrepassation',this.code(e),`<input type="hidden" name="id" value="${id}"><div class="form-grid">${this.contextFields({journal_id:e.journal_id},false)}${field('Motif','reason','','text',true,true)}</div><div class="notice">Un brouillon inversera les débits et crédits d’origine. Vérifiez-le puis comptabilisez-le. La date doit être égale ou postérieure à celle de l’écriture d’origine.</div>`,`${cancelButton}<button class="btn primary" type="submit">Créer la contrepassation</button>`,false,'accounting-reverse-form');this.key=crypto.randomUUID();
  },
  reportsView(){
    const d=this.data(),params=this.reportParams,period=d.periods.find(p=>String(p.id)===params?.period_id)||d.periods[0];
    if(!period)return empty('Aucune période définie','Ajoutez une période dans Paramétrage pour consulter les rapports.');
    const r=this.report;
    return `<form id="accounting-report-form" class="card accounting-report-controls"><div class="form-grid">${this.select('Période du rapport','period_id',d.periods,period.id)}${field('Du','date_from',params?.date_from||period.start,'date')}${field('Au','date_to',params?.date_to||period.end,'date')}<button class="btn primary" type="submit">Afficher le rapport</button></div><div class="form-error" role="alert"></div></form><div class="notice">Seules les écritures comptabilisées sont incluses. L’ouverture correspond aux mouvements antérieurs dans la période choisie ; les soldes des périodes précédentes ne sont pas reportés automatiquement.</div>${r?`<div class="toolbar"><div class="tabs" role="group" aria-label="Choisir le rapport">${[['trial_balance','Balance'],['journal','Journal général'],['ledger','Grand livre']].map(([id,name])=>`<button class="tab ${this.reportKind===id?'active':''}" data-action="accounting-report-kind" data-kind="${id}">${name}</button>`).join('')}</div>${AtlasPlatform.can('export')?`<a class="btn" href="/api/companies/${AtlasPlatform.companyId}/accounting/export?${new URLSearchParams({...this.reportParams,report:this.reportKind})}">${icon('download')}Exporter le rapport</a>`:''}</div><div class="accounting-reconciliation">Débit <strong>${currency(r.totals.debit)}</strong> · Crédit <strong>${currency(r.totals.credit)}</strong> · Écart <strong>${currency(r.totals.debit-r.totals.credit)}</strong></div>${this.reportKind==='ledger'?`<div class="toolbar"><label class="field"><span>Compte du grand livre</span><select id="accounting-ledger-account"><option value="">Tous les comptes</option>${r.trial_balance.map(a=>`<option value="${a.account_id}" ${String(a.account_id)===this.reportAccount?'selected':''}>${esc(a.code+' · '+a.name)}</option>`).join('')}</select></label></div>`:''}<section class="card">${this.reportTable()}</section>`:empty('Choisissez votre période','Affichez la balance, le journal général et le grand livre à partir des mêmes écritures comptabilisées.')}`;
  },
  reportTable(){
    const r=this.report;
    if(!r.trial_balance.length)return empty('Aucune écriture comptabilisée','Les brouillons ne sont pas pris en compte.');
    if(this.reportKind==='trial_balance')return `<div class="table-scroll"><table><thead><tr><th>Compte</th><th>Libellé</th><th class="amount">Ouverture D − C</th><th class="amount">Débit</th><th class="amount">Crédit</th><th class="amount">Clôture D − C</th></tr></thead><tbody>${r.trial_balance.map(a=>`<tr><td>${esc(a.code)}</td><td>${esc(a.name)}</td>${['opening','debit','credit','closing'].map(k=>`<td class="amount">${currency(a[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
    const ledger=this.reportKind==='ledger',rows=r.ledger.filter(l=>!ledger||!this.reportAccount||String(l.account_id)===this.reportAccount).slice();
    if(ledger)rows.sort((a,b)=>a.code.localeCompare(b.code)||a.date.localeCompare(b.date)||a.journal.localeCompare(b.journal)||a.number-b.number);
    const opening=ledger?r.trial_balance.filter(a=>!this.reportAccount||String(a.account_id)===this.reportAccount).map(a=>`<span>${esc(a.code)} : ${currency(a.opening)}</span>`).join(' · '):'';
    return `${ledger?`<p class="accounting-opening">Soldes d’ouverture (D − C) : ${opening}</p>`:''}<div class="table-scroll"><table><thead><tr><th>Date</th><th>Écriture</th><th>Compte</th><th>Libellé</th><th class="amount">Débit</th><th class="amount">Crédit</th>${ledger?'<th class="amount">Solde D − C</th>':''}</tr></thead><tbody>${rows.map(l=>`<tr><td>${date(l.date+'T12:00:00')}</td><td><button class="edit-link" data-action="accounting-view" data-id="${l.entry_id}">${esc(l.journal)}-${String(l.number).padStart(6,'0')}</button></td><td>${esc(l.code)}</td><td>${esc(l.memo)}<small class="purchase-sub">${esc(l.reference)} ${esc(l.label)}</small></td><td class="amount">${currency(l.debit)}</td><td class="amount">${currency(l.credit)}</td>${ledger?`<td class="amount">${currency(l.balance)}</td>`:''}</tr>`).join('')}</tbody></table></div>`;
  }
};

document.addEventListener('click',event=>{
  const button=event.target.closest('[data-action^="accounting-"]');if(!button)return;
  event.preventDefault();event.stopImmediatePropagation();const a=AtlasAccounting,id=Number(button.dataset.id);if(a.saving)return;
  const actions={
    tab:()=>{a.tab=button.dataset.tab;render();},setup:()=>{dialog.close();a.tab='setup';render();},
    'new-account':()=>a.masterModal('account'),'edit-account':()=>a.masterModal('account',id),
    'new-journal':()=>a.masterModal('journal'),'edit-journal':()=>a.masterModal('journal',id),
    'new-period':()=>a.periodModal(),'period-state':()=>a.periodState(id),
    'new-entry':()=>a.edit(),'edit-entry':()=>a.edit(id),view:()=>a.details(id),
    'payment-transfer':()=>a.paymentTransferModal(button.dataset.kind,id),
    match:()=>a.matchModal(id),unmatch:()=>a.unmatchModal(id),
    transfer:()=>a.transferModal(button.dataset.kind,id),post:()=>a.decision('post',id),discard:()=>a.decision('discard',id),reverse:()=>a.reverse(id),
    'add-line':()=>{a.lines.push({account_id:a.data().accounts.find(x=>x.active).id,label:'',debit:'0',credit:'0'});a.renderLines();},
    'remove-line':()=>{a.lines.splice(id,1);a.renderLines();},
    'report-kind':()=>{a.reportKind=button.dataset.kind;render();}
  };actions[button.dataset.action.slice(11)]?.();
});
document.addEventListener('input',event=>{
  const key=event.target.dataset.accField;if(!key)return;
  AtlasAccounting.lines[Number(event.target.closest('[data-index]').dataset.index)][key]=event.target.value;
  AtlasAccounting.lineTotals();
});
document.addEventListener('change',event=>{
  const a=AtlasAccounting;
  if(event.target.id==='accounting-entry-filter'){a.entryFilter=event.target.value;render();}
  if(event.target.id==='accounting-ledger-account'){a.reportAccount=event.target.value;render();}
  if(event.target.closest('#accounting-report-form')&&event.target.name==='period_id'){
    const p=a.data().periods.find(p=>p.id===Number(event.target.value));
    const form=event.target.form;form.elements.date_from.value=p.start;form.elements.date_to.value=p.end;
  }
});
document.addEventListener('submit',async event=>{
  const form=event.target,name=form.getAttribute('id');if(!name?.startsWith('accounting-'))return;
  event.preventDefault();event.stopImmediatePropagation();const a=AtlasAccounting;if(a.saving)return;
  const button=form.querySelector('[type=submit]'),errorBox=form.querySelector('.form-error'),company=AtlasPlatform.companyId;
  a.saving=true;AtlasPlatform.busy++;button.disabled=true;errorBox.textContent='';
  try{
    const data=Object.fromEntries(new FormData(form));
    if(name==='accounting-report-form'){
      const report=await api(`accounting/reports?${new URLSearchParams(data)}`);
      if(company!==AtlasPlatform.companyId)return;a.reportParams=data;a.report=report;render();return;
    }
    const action=name.replace(/-form$/,'');data.request_key=a.key;
    if(['accounting-account','accounting-journal'].includes(action))data.active=data.active==='true';
    if(action==='accounting-period-state'){data.closed=data.closed==='true';data.expected_closed=data.expected_closed==='true';}
    if(action==='accounting-entry')data.lines=a.lines;
    const result=await api(action,data);if(company!==AtlasPlatform.companyId)return;
    await refresh();if(company!==AtlasPlatform.companyId)return;dialog.close();main.focus({preventScroll:true});
    if(['accounting-entry','accounting-transfer','accounting-payment-transfer','accounting-post','accounting-discard','accounting-reverse'].includes(action))a.details(result.id);
    toast(action==='accounting-post'?'Écriture comptabilisée. Les rapports sont à jour.':'Enregistrement effectué.');
  }catch(error){if(form.isConnected)errorBox.textContent=error.message;else toast(error.message,true);}
  finally{a.saving=false;AtlasPlatform.busy--;button.disabled=false;}
});
