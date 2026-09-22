'use strict';
window.AtlasPurchases = {
  lines: [], key: null, saving: false,
  reset() { this.lines=[];this.key=null; },
  can(permission) { return window.AtlasPlatform.enabled && window.AtlasPlatform.can(permission); },
  code(p) { return `AC-${String(p.number).padStart(4,'0')}`; },
  today() { return new Intl.DateTimeFormat('sv-SE',{timeZone:'Africa/Casablanca'}).format(new Date()); },
  overdue(p) { return p.status==='received' && p.paid<p.total && p.due_date && p.due_date<this.today(); },
  status(p) {
    if(p.status==='draft')return badge('Brouillon','neutral');
    if(p.status==='cancelled')return badge('Annulée','neutral');
    if(p.paid===p.total)return badge('Réglée');
    if(this.overdue(p))return badge('En retard','danger');
    return badge(p.paid?'Règlement partiel':'À régler','warning');
  },
  view() {
    const received=state.purchases.filter(p=>p.status==='received'),due=received.filter(p=>p.paid<p.total),late=due.filter(p=>this.overdue(p));
    const actions=`${this.can('export')?`<a class="btn" href="/api/companies/${AtlasPlatform.companyId}/export/purchases">${icon('download')}Exporter</a>`:''}${this.can('purchases')?`<button class="btn primary" data-action="purchase-new">${icon('plus')}Nouvel achat</button>`:''}`;
    return heading('DE LA FACTURE AU STOCK','Vos achats','Préparez vos factures, réceptionnez vos produits et suivez vos règlements.',actions)+
      `<section class="stats-grid purchase-stats" aria-label="Indicateurs des achats">${statsCard('Reste à régler',amount(sum(due,'total')-sum(due,'paid')),'DH',`${due.length} factures réceptionnées`,'wallet',true)}${statsCard('Échéances dépassées',amount(sum(late,'total')-sum(late,'paid')),'DH',`${late.length} factures en retard`,'clock')}${statsCard('En préparation',number(state.purchases.filter(p=>p.status==='draft').length),'', 'Brouillons · aucun effet sur le stock','edit')}${statsCard('Achats réceptionnés',amount(sum(received,'total')),'DH','Total TTC · toutes les périodes','box')}</section>`+
      `<div class="toolbar purchase-toolbar"><div class="tabs" role="group" aria-label="Filtrer les achats">${[['all','Tous'],['draft','Brouillons'],['received','Réceptionnés'],['unpaid','À régler'],['overdue','En retard'],['cancelled','Annulés']].map(([id,name])=>`<button class="tab ${filter===id?'active':''}" data-filter="${id}">${name}</button>`).join('')}</div>${searchControl('N° achat, fournisseur ou référence…')}</div><section class="card" id="list-content">${this.content()}</section><p class="table-count">Les brouillons ne modifient ni le stock ni le solde à régler. Les taxes sont saisies selon la facture fournisseur.</p>`;
  },
  content() {
    const rows=state.purchases.filter(p=>(filter==='all'||p.status===filter||filter==='unpaid'&&p.status==='received'&&p.paid<p.total||filter==='overdue'&&this.overdue(p))&&`${this.code(p)} ${p.supplier_name} ${p.supplier_reference}`.toLowerCase().includes(query.toLowerCase()));
    if(!rows.length)return empty('Aucun achat ici','Enregistrez une facture fournisseur pour préparer votre prochaine réception.',this.can('purchases')?'purchase-new':'','Nouvel achat');
    return `<div class="table-scroll"><table><thead><tr><th>Facture</th><th>Fournisseur</th><th>Échéance</th><th>Statut</th><th class="amount">Total TTC</th><th class="amount">Reste dû</th><th></th></tr></thead><tbody>${rows.map(p=>`<tr><td><button class="edit-link" data-action="purchase-view" data-id="${p.id}">${this.code(p)}</button><small class="purchase-sub">${date(p.invoice_date+'T12:00:00')}</small></td><td><strong>${esc(p.supplier_name)}</strong><small class="purchase-sub">${esc(p.supplier_reference)}</small></td><td>${p.due_date?date(p.due_date+'T12:00:00'):'—'}</td><td>${this.status(p)}</td><td class="amount">${currency(p.total)}</td><td class="amount">${p.status==='received'?currency(p.total-p.paid):'—'}</td><td><button class="icon-btn" data-action="purchase-view" data-id="${p.id}" aria-label="Ouvrir ${this.code(p)}">${icon('arrow')}</button></td></tr>`).join('')}</tbody></table></div>`;
  },
  suppliersView() {
    return heading('VOTRE RÉSEAU AU QUOTIDIEN','Vos fournisseurs','Des coordonnées à jour et une vue claire de vos achats.',this.can('catalog')?`<button class="btn primary" data-action="purchase-new-supplier">${icon('plus')}Nouveau fournisseur</button>`:'')+`<div class="toolbar"><span class="stat-note">${state.suppliers.length} fournisseurs dans votre carnet</span>${searchControl('Fournisseur, ville ou téléphone…')}</div><section class="card" id="list-content">${this.suppliersContent()}</section>`;
  },
  suppliersContent() {
    const rows=state.suppliers.filter(s=>`${s.name} ${s.city} ${s.phone} ${s.ice}`.toLowerCase().includes(query.toLowerCase()));
    if(!rows.length)return empty('Votre carnet fournisseurs','Ajoutez votre premier fournisseur pour enregistrer une facture.',this.can('catalog')?'purchase-new-supplier':'','Nouveau fournisseur');
    return `<div class="table-scroll"><table><thead><tr><th>Fournisseur</th><th>Contact</th><th>Factures reçues</th><th class="amount">Reste dû</th><th></th></tr></thead><tbody>${rows.map(s=>{const rows=state.purchases.filter(p=>p.supplier_id===s.id&&p.status==='received');return `<tr><td><strong>${esc(s.name)}</strong><small class="purchase-sub">${esc(s.city||'Ville non renseignée')}</small></td><td>${esc(s.phone||'—')}<small class="purchase-sub">${esc(s.email)}</small></td><td>${rows.length}</td><td class="amount">${currency(sum(rows,'total')-sum(rows,'paid'))}</td><td><button class="btn small" data-action="purchase-supplier" data-id="${s.id}">${this.can('catalog')?'Modifier':'Consulter'}</button></td></tr>`;}).join('')}</tbody></table></div>`;
  },
  supplierModal(id) {
    const s=state.suppliers.find(s=>s.id===id),editable=this.can('catalog');
    modal(s?'Fiche fournisseur':'Un nouveau fournisseur','Les coordonnées restent propres à la société active.',`<input type="hidden" name="id" value="${s?.id||''}"><fieldset class="purchase-fieldset" ${editable?'':'disabled'}><div class="form-grid">${field('Raison sociale','name',s?.name||'','text',true,true)}${field('Téléphone','phone',s?.phone||'','tel',false)}${field('Ville','city',s?.city||'','text',false)}${field('Email','email',s?.email||'','email',false,true)}${field('Identifiant fiscal','fiscal_id',s?.fiscal_id||'','text',false)}${field('ICE','ice',s?.ice||'','text',false,false,'pattern="[0-9]{15}"')}<label class="field full"><span>Adresse</span><textarea name="address" maxlength="500">${esc(s?.address||'')}</textarea></label></div></fieldset>`,`${cancelButton}${editable?'<button class="btn primary" type="submit">Enregistrer le fournisseur</button>':''}`,false,'purchase-supplier-form');
  },
  edit(id) {
    if(!this.can('purchases'))return;
    if(!state.suppliers.length)return modal('Ajoutez un fournisseur','Une facture doit être rattachée à un fournisseur.',empty('Un premier contact','Créez sa fiche dans le carnet fournisseurs.'),`${cancelButton}<button class="btn primary" data-action="purchase-new-supplier">Nouveau fournisseur</button>`);
    if(!state.products.length)return modal('Ajoutez un produit','Les achats de cette étape concernent les produits stockés.',empty('Un catalogue à compléter','Créez vos produits avant de saisir leur achat.'),`${cancelButton}${this.can('catalog')?'<button class="btn primary" data-action="new-product">Nouveau produit</button>':''}`);
    const p=state.purchases.find(p=>p.id===id);if(p&&p.status!=='draft')return this.details(id);
    this.lines=p?state.purchase_items.filter(i=>i.purchase_id===id).sort((a,b)=>a.id-b.id).map(i=>({product_id:i.product_id,quantity:String(i.quantity),price:(i.price/100).toFixed(2),tax_percent:(i.tax_bps/100).toFixed(2)})):[];
    this.key=crypto.randomUUID();
    modal(p?`Modifier ${this.code(p)}`:'Un nouvel achat','Enregistrez un brouillon, puis confirmez la réception des produits.',`<input type="hidden" name="id" value="${p?.id||''}"><input type="hidden" name="version" value="${p?.version||''}"><div class="form-grid"><label class="field full"><span>Fournisseur *</span><select name="supplier_id" required>${state.suppliers.map(s=>`<option value="${s.id}" ${s.id===p?.supplier_id?'selected':''}>${esc(s.name)}</option>`).join('')}</select></label>${field('Référence facture fournisseur','supplier_reference',p?.supplier_reference||'','text',true,true,'maxlength="80"')}${field('Date de facture','invoice_date',p?.invoice_date||this.today(),'date')}${field('Échéance','due_date',p?.due_date||'','date',false)}</div><div class="purchase-add"><label class="field"><span>Produit à acheter</span><select id="purchase-product">${state.products.map(i=>`<option value="${i.id}">${esc(i.name)} · ${esc(i.sku)}</option>`).join('')}</select></label><button type="button" class="btn" data-action="purchase-add-line">${icon('plus')}Ajouter une ligne</button></div><div id="purchase-lines"></div><div id="purchase-totals" class="detail-totals" aria-live="polite"></div><label class="field"><span>Note</span><textarea name="note" maxlength="1000">${esc(p?.note||'')}</textarea></label><div class="notice">Saisissez les prix HT et les taux figurant sur la facture. Le stock augmente uniquement à la réception. Le prix d’achat du catalogue reste inchangé.</div>`,`${cancelButton}<button class="btn primary" type="submit">Enregistrer le brouillon</button>`,true,'purchase-draft-form');
    this.renderLines();
  },
  cents(value) { const s=String(value).replace(',','.');if(!/^\d+(\.\d{0,2})?$/.test(s))return null;const [a,b='']=s.split('.');const n=Number(a)*100+Number(b.padEnd(2,'0'));return Number.isSafeInteger(n)?n:null; },
  totals(line) { const price=this.cents(line.price),rate=this.cents(line.tax_percent),quantity=Number(line.quantity);if(price===null||rate===null||!Number.isInteger(quantity)||quantity<1||quantity>1000000||price>1000000000||rate>10000)return null;const subtotal=price*quantity,tax=Math.floor((subtotal*rate+5000)/10000);return {subtotal,tax,total:subtotal+tax}; },
  renderLines() {
    document.querySelector('#purchase-lines').innerHTML=this.lines.length?this.lines.map((line,index)=>{const product=state.products.find(p=>p.id===line.product_id);return `<div class="purchase-line" data-index="${index}"><div class="purchase-line-name"><strong>${esc(product.name)}</strong><small>${esc(product.sku)}</small></div><label class="field"><span>Quantité</span><input aria-label="Quantité ${esc(product.name)}" type="number" min="1" max="1000000" step="1" required data-purchase-field="quantity" value="${esc(line.quantity)}"></label><label class="field"><span>Prix HT · DH</span><input aria-label="Prix achat ${esc(product.name)}" type="number" min="0" max="10000000" step="0.01" required data-purchase-field="price" value="${esc(line.price)}"></label><label class="field"><span>Taxe · %</span><input aria-label="Taxe achat ${esc(product.name)}" type="number" min="0" max="100" step="0.01" required data-purchase-field="tax_percent" value="${esc(line.tax_percent)}"></label><div class="purchase-line-total">${currency(this.totals(line)?.total||0)}</div><button type="button" class="icon-btn" data-action="purchase-remove-line" data-id="${index}" aria-label="Retirer ${esc(product.name)}">${icon('trash')}</button></div>`;}).join(''):empty('Ajoutez les produits achetés','Le prix d’achat du catalogue est proposé et reste modifiable.','','',true);
    this.updateTotals();
  },
  updateTotals() {
    const rows=this.lines.map(l=>this.totals(l)),valid=rows.every(Boolean);
    document.querySelector('#purchase-totals').innerHTML=valid?`<div class="total-row"><span>Total HT</span><strong>${currency(sum(rows,'subtotal'))}</strong></div><div class="total-row"><span>Taxe · arrondie par ligne</span><strong>${currency(sum(rows,'tax'))}</strong></div><div class="total-row final"><span>Total TTC</span><strong>${currency(sum(rows,'total'))}</strong></div>`:'<p class="form-error">Vérifiez les quantités, prix et taux de taxe.</p>';
  },
  itemsTable(items) {
    return `<div class="table-scroll"><table><thead><tr><th>Produit</th><th>Qté</th><th class="amount">Prix HT</th><th>Taxe</th><th class="amount">Total TTC</th></tr></thead><tbody>${items.map(i=>`<tr><td>${esc(i.name)}<small class="purchase-sub">${esc(i.sku)}</small></td><td>${number(i.quantity)}</td><td class="amount">${currency(i.price)}</td><td>${number(i.tax_bps/100)} %</td><td class="amount">${currency(i.total)}</td></tr>`).join('')}</tbody></table></div>`;
  },
  details(id) {
    const p=state?.purchases.find(p=>p.id===id);if(!p)return;
    const payments=state.supplier_payments.filter(x=>x.purchase_id===id),items=state.purchase_items.filter(x=>x.purchase_id===id).sort((a,b)=>a.id-b.id);
    const actions=`${cancelButton}<button class="btn" data-action="purchase-print" data-id="${id}">${icon('print')}Imprimer</button>${p.status==='draft'&&this.can('purchases')?`<button class="btn" data-action="purchase-edit" data-id="${id}">Modifier</button><button class="btn primary" data-action="purchase-receive" data-id="${id}">${icon('box')}Réceptionner les produits</button>`:''}${p.status==='received'&&p.paid<p.total&&this.can('payments')?`<button class="btn primary" data-action="purchase-payment" data-id="${id}">${icon('wallet')}Régler le fournisseur</button>`:''}`;
    modal(`Achat ${this.code(p)}`,`${p.supplier_name} · Réf. ${p.supplier_reference}`,`<div class="sale-details-meta"><div><small>STATUT</small>${this.status(p)}</div><div><small>DATE DE FACTURE</small><strong>${date(p.invoice_date+'T12:00:00')}</strong></div><div><small>ÉCHÉANCE</small><strong>${p.due_date?date(p.due_date+'T12:00:00'):'Non précisée'}</strong></div></div>${p.status==='draft'?'<div class="notice">Brouillon : aucun stock ajouté, aucun règlement enregistré.</div>':''}${p.received_at?`<div class="notice">Produits réceptionnés le ${date(p.received_at)}.${p.status==='cancelled'?' Réception annulée et quantités retirées du stock.':''}</div>`:''}${this.itemsTable(items)}<div class="detail-totals"><div class="total-row"><span>Total HT</span><strong>${currency(p.subtotal)}</strong></div><div class="total-row"><span>Taxe</span><strong>${currency(p.tax)}</strong></div><div class="total-row final"><span>Total TTC</span><strong>${currency(p.total)}</strong></div><div class="total-row"><span>Réglé</span><strong>${currency(p.paid)}</strong></div><div class="total-row"><span>Reste dû</span><strong>${p.status==='received'?currency(p.total-p.paid):'—'}</strong></div></div>${p.note?`<div class="notice">${esc(p.note)}</div>`:''}${p.cancellation_reason?`<div class="notice warning">Annulation : ${esc(p.cancellation_reason)}</div>`:''}${payments.length?`<h3>Règlements fournisseur</h3><div class="payment-list">${payments.map(r=>`<div class="payment-item"><span>${date(r.payment_date+'T12:00:00')} · ${esc(r.method)}${r.reference?` · ${esc(r.reference)}`:''}</span><strong>${currency(r.amount)}</strong></div>`).join('')}</div>`:''}${p.status!=='cancelled'&&p.paid===0&&this.can('cancel')?`<button class="edit-link purchase-cancel-link" data-action="purchase-cancel" data-id="${id}">Annuler cet achat</button>`:''}`,actions,true);
  },
  receiveModal(id) {
    const p=state.purchases.find(p=>p.id===id),items=state.purchase_items.filter(i=>i.purchase_id===id);
    modal(`Réceptionner ${this.code(p)}`,p.supplier_name,`<input type="hidden" name="purchase_id" value="${id}"><input type="hidden" name="version" value="${p.version}"><input type="hidden" name="request_key" value="${crypto.randomUUID()}"><div class="notice">Confirmez uniquement après réception de tous les produits : <strong>${number(sum(items,'quantity'))} unités</strong> seront ajoutées au stock. La facture sera ensuite verrouillée.</div>${this.itemsTable(items)}`,`${cancelButton}<button class="btn primary" type="submit">Confirmer la réception</button>`,true,'purchase-receive-form');
  },
  paymentModal(id) {
    const p=state.purchases.find(p=>p.id===id);
    modal('Régler le fournisseur',`${this.code(p)} · ${p.supplier_name}`,`<input type="hidden" name="purchase_id" value="${id}"><input type="hidden" name="request_key" value="${crypto.randomUUID()}"><div class="notice">Reste à régler : <strong>${currency(p.total-p.paid)}</strong></div><div class="form-grid">${field('Montant du règlement · DH','amount',((p.total-p.paid)/100).toFixed(2),'number',true,false,`min="0.01" max="${(p.total-p.paid)/100}"`)}<label class="field"><span>Mode de règlement</span><select name="method">${['Virement','Espèces','Carte','Chèque'].map(m=>`<option>${m}</option>`).join('')}</select></label>${field('Date du règlement','payment_date',this.today(),'date',true,false,`min="${p.invoice_date}" max="${this.today()}"`)}${field('Référence du règlement','reference','','text',false,false,'maxlength="80"')}</div>`,`${cancelButton}<button class="btn primary" type="submit">Enregistrer le règlement fournisseur</button>`,false,'purchase-payment-form');
  },
  cancelModal(id) {
    const p=state.purchases.find(p=>p.id===id);
    modal(`Annuler ${this.code(p)}`,p.supplier_name,`<input type="hidden" name="purchase_id" value="${id}"><input type="hidden" name="version" value="${p.version}"><input type="hidden" name="request_key" value="${crypto.randomUUID()}"><div class="notice warning">${p.status==='received'?'Les quantités réceptionnées seront retirées du stock. Confirmez uniquement si cette réception doit réellement être annulée. Le stock disponible doit être suffisant.':'Ce brouillon sera conservé avec le statut Annulé.'} La référence de facture restera réservée dans l’historique.</div><label class="field"><span>Motif d’annulation *</span><textarea name="reason" maxlength="300" required></textarea></label>`,`${cancelButton}<button class="btn danger" type="submit">Confirmer l’annulation</button>`,false,'purchase-cancel-form');
  },
  print(id) {
    const p=state.purchases.find(p=>p.id===id);
    document.querySelector('#print-area').innerHTML=`<h1>${esc(state.settings.name)}</h1><h2>Achat ${this.code(p)} · Copie interne</h2><p>Fournisseur : ${esc(p.supplier_name)}<br>Référence fournisseur : ${esc(p.supplier_reference)}<br>Date : ${date(p.invoice_date+'T12:00:00')} · Échéance : ${p.due_date?date(p.due_date+'T12:00:00'):'—'}</p>${this.status(p)}${this.itemsTable(state.purchase_items.filter(i=>i.purchase_id===id))}<p>Total HT : ${currency(p.subtotal)} · Taxe : ${currency(p.tax)} · Total TTC : ${currency(p.total)}</p><p>Réglé : ${currency(p.paid)} · Reste dû : ${p.status==='received'?currency(p.total-p.paid):'—'}</p><p>${esc(p.note)}</p>${p.cancellation_reason?`<p>Annulation : ${esc(p.cancellation_reason)}</p>`:''}<small>Document de suivi interne. Conservez la facture originale du fournisseur.</small>`;
    window.print();
  }
};

document.addEventListener('click',event=>{
  const button=event.target.closest('[data-action^="purchase-"]');if(!button)return;
  event.preventDefault();event.stopImmediatePropagation();
  const p=AtlasPurchases,id=Number(button.dataset.id);if(p.saving)return;
  const actions={
    'purchase-new':()=>p.edit(),'purchase-edit':()=>p.edit(id),'purchase-view':()=>p.details(id),
    'purchase-new-supplier':()=>p.supplierModal(),'purchase-supplier':()=>p.supplierModal(id),
    'purchase-receive':()=>p.receiveModal(id),'purchase-payment':()=>p.paymentModal(id),
    'purchase-cancel':()=>p.cancelModal(id),'purchase-print':()=>p.print(id),
    'purchase-add-line':()=>{const product=state.products.find(x=>x.id===Number(document.querySelector('#purchase-product').value)),line=p.lines.find(l=>l.product_id===product.id);if(line)line.quantity=String(Number(line.quantity)+1);else p.lines.push({product_id:product.id,quantity:'1',price:(product.cost/100).toFixed(2),tax_percent:'0'});p.renderLines();},
    'purchase-remove-line':()=>{p.lines.splice(id,1);p.renderLines();}
  };
  if(actions[button.dataset.action])actions[button.dataset.action]();
});
document.addEventListener('input',event=>{
  const key=event.target.dataset.purchaseField;if(!key)return;
  const line=AtlasPurchases.lines[Number(event.target.closest('[data-index]').dataset.index)];
  line[key]=event.target.value;
  event.target.closest('.purchase-line').querySelector('.purchase-line-total').textContent=currency(AtlasPurchases.totals(line)?.total||0);
  AtlasPurchases.updateTotals();
});
document.addEventListener('submit',async event=>{
  const form=event.target,name=form.getAttribute('id');if(!name?.startsWith('purchase-'))return;
  event.preventDefault();event.stopImmediatePropagation();
  const p=AtlasPurchases;if(p.saving)return;
  const button=form.querySelector('[type=submit]');if(!button)return;
  const errorBox=form.querySelector('.form-error'),company=AtlasPlatform.companyId;
  p.saving=true;AtlasPlatform.busy++;button.disabled=true;errorBox.textContent='';
  try{
    const data=Object.fromEntries(new FormData(form));let action,message;
    if(name==='purchase-supplier-form'){action='suppliers';message='Fournisseur enregistré.';}
    if(name==='purchase-draft-form'){
      if(!p.lines.length||p.lines.some(l=>!p.totals(l)))throw new Error('Ajoutez des lignes valides à la facture.');
      Object.assign(data,{request_key:p.key,items:p.lines.map(l=>({product_id:l.product_id,quantity:l.quantity,price:l.price,tax_bps:p.cents(l.tax_percent)}))});
      action='purchases';message='Brouillon enregistré. Le stock reste inchangé.';
    }
    if(name==='purchase-receive-form'){action='purchase-receive';message='Réception confirmée. Le stock est à jour.';}
    if(name==='purchase-payment-form'){action='supplier-payments';message='Règlement fournisseur enregistré.';}
    if(name==='purchase-cancel-form'){action='purchase-cancel';message='Achat annulé.';}
    const result=await api(action,data);if(company!==AtlasPlatform.companyId)return;
    dialog.close();await refresh();if(company!==AtlasPlatform.companyId)return;
    if(action!=='suppliers')p.details(result.id);
    toast(message);
  }catch(error){if(form.isConnected)errorBox.textContent=error.message;else toast(error.message,true);}
  finally{button.disabled=false;p.saving=false;AtlasPlatform.busy--;}
});
