'use strict';
const icons = {
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  box:'<path d="m12 3 9 5v8l-9 5-9-5V8Z"/><path d="m3 8 9 5 9-5M12 13v8M7.5 5.5l9 5"/>',
  sale:'<path d="M6 3h12v18l-3-2-3 2-3-2-3 2Z"/><path d="M9 7h6M9 11h6M9 15h3"/>',
  users:'<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6M18 15a5 5 0 0 1 3 5"/>',
  arrows:'<path d="M4 7h15l-4-4M20 17H5l4 4M19 7l-4 4M5 17l4-4"/>',
  settings:'<path d="m9 3-1 3-3 1-1 3 2 2-1 3 2 3 3-1 2 3 3-1 1-3 3-1 1-3-2-2 1-3-2-3-3 1-2-3Z"/><circle cx="12" cy="11.5" r="3"/>',
  search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
  bell:'<path d="M5 16h14l-2-3V9a5 5 0 0 0-10 0v4ZM10 20h4"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  chevron:'<path d="m9 5 7 7-7 7"/>',
  down:'<path d="m6 9 6 6 6-6"/>',
  arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
  trend:'<path d="m3 17 6-6 4 3 8-10M15 4h6v6"/>',
  wallet:'<path d="M20 8V5H5a2 2 0 0 0 0 4h16v10H5a2 2 0 0 1-2-2V7"/><path d="M21 12h-6v4h6"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
  building:'<rect x="5" y="3" width="14" height="18" rx="1"/><path d="M9 7h1m4 0h1M9 11h1m4 0h1M10 21v-6h4v6"/>',
  download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  upload:'<path d="M12 16V4m-5 5 5-5 5 5M4 16v5h16v-5"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  edit:'<path d="m14 5 5 5M3 21l5-1L21 7l-5-5L3 15Z"/>',
  mail:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 6 9 7 9-7"/>',
  phone:'<path d="M7 3H3c-1 10 8 19 18 18v-4l-5-2-2 2c-4-2-5-3-7-7l2-2Z"/>',
  pin:'<path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 0 1 14 0Z"/><circle cx="12" cy="10" r="2"/>',
  calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18"/>',
  menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
  print:'<path d="M6 9V3h12v6M6 17H3V9h18v8h-3M6 14h12v7H6Z"/><path d="M17 12h1"/>',
  trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
  tool:'<path d="m14 3 1 5 5 1a6 6 0 0 1-7 5l-7 7-3-3 7-7a6 6 0 0 1 4-8Z"/>',
  bolt:'<path d="m13 2-9 12h7l-1 8 10-13h-8Z"/>',
  drop:'<path d="M12 3s-7 7-7 12a7 7 0 0 0 14 0c0-5-7-12-7-12Z"/>',
  paint:'<rect x="3" y="3" width="14" height="6" rx="2"/><path d="M17 6h4v7h-9v8H9v-8"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.box}</svg>`;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const amount = cents => new Intl.NumberFormat('fr-MA', {minimumFractionDigits:2, maximumFractionDigits:2}).format(cents / 100);
const currency = cents => `${amount(cents)} DH`;
const number = value => new Intl.NumberFormat('fr-FR').format(value);
const date = (value, opts={day:'2-digit',month:'short',year:'numeric'}) => new Date(value).toLocaleDateString('fr-FR', opts);
const shortDate = value => date(value, {day:'2-digit',month:'short'});
const dayKey = value => { const d=new Date(value);return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-'); };
const initials = name => name.split(/\s+/).map(w=>w[0]).slice(0,2).join('').toUpperCase();
const routes = {dashboard:'Vue d’ensemble',products:'Produits & stock',sales:'Ventes',purchases:'Achats',customers:'Clients',suppliers:'Fournisseurs',movements:'Mouvements',accounting:'Comptabilité',vat:'TVA',settings:'Paramètres'};
let state, route = 'dashboard', filter = 'all', category = '', query = '', toastTimer, cart = [], saleKey;
const main = document.querySelector('#main');
const dialog = document.querySelector('#dialog');

async function api(path, body) {
  if(window.AtlasPlatform?.enabled) return window.AtlasPlatform.request(`companies/${window.AtlasPlatform.companyId}/${path}`,body);
  const res = await fetch(`/api/${path}`, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-Atlas-Request':'1'}, body:JSON.stringify(body)});
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Une erreur est survenue.');
  return data;
}
async function refresh() { const company=window.AtlasPlatform?.companyId; const next=await api('state'); if(company!==window.AtlasPlatform?.companyId)return; if(next.permissions?.includes('accounting_read')){next.accounting=await api('accounting/state');if(company!==window.AtlasPlatform?.companyId)return;} if(next.permissions?.includes('vat_read')){next.vat=await api('vat/state');if(company!==window.AtlasPlatform?.companyId)return;} window.AtlasAccounting?.invalidateReport(); state=next; render(); }
function toast(message, error=false) {
  const el = document.querySelector('#toast'); el.textContent = message; el.className = `show${error ? ' error' : ''}`;
  clearTimeout(toastTimer); toastTimer = setTimeout(()=>el.className='',4500);
}
const activeSales = () => state.sales.filter(s=>s.status==='active');
const lowProducts = () => state.products.filter(p=>p.stock<=p.minimum).sort((a,b)=>a.stock-b.stock);
const sum = (rows,key) => rows.reduce((total,row)=>total+row[key],0);
function salesStatus(s) { return s.status==='cancelled' ? ['Annulée','neutral'] : s.paid>=s.total ? ['Payée',''] : s.paid>0 ? ['Partielle','warning'] : ['À encaisser','warning']; }
function badge(text,tone='') { return `<span class="badge ${tone}"><i></i>${esc(text)}</span>`; }
function productStatus(p) { return p.stock===0 ? badge('Rupture','danger') : p.stock<=p.minimum ? badge('Stock faible','warning') : badge('En stock'); }
function symbol(p) { const names=['Outillage','Électricité','Plomberie','Peinture','Quincaillerie']; const idx=Math.max(0,names.indexOf(p.category)); return `<span class="product-symbol tone-${idx}">${icon(['tool','bolt','drop','paint','box'][idx])}</span>`; }
function empty(title, message, action='', text='Ajouter', compact=false) {return `<div class="empty ${compact?'compact':''}">${icon('box')}<h3>${esc(title)}</h3><p>${esc(message)}</p>${action?`<button class="btn primary" data-action="${action}">${icon('plus')}${esc(text)}</button>`:''}</div>`;}
function statsCard(title, value, suffix, foot, glyph, featured=false) { return `<article class="stat ${featured?'featured':''}"><div class="stat-top">${title}<span class="stat-icon">${icon(glyph)}</span></div><div class="stat-number">${value}${suffix?`<span>${suffix}</span>`:''}</div><div class="stat-foot">${foot}</div></article>`; }
function heading(eyebrow, title, subtitle, actions='') { return `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p class="subtitle">${subtitle}</p></div><div class="heading-actions">${actions}</div></div>`; }
const saleButton = `<button class="btn primary" data-action="new-sale">${icon('plus')}Nouvelle vente</button>`;

function renderShell() {
  document.querySelector('#sidebar').innerHTML = `<a href="#dashboard" class="brand" aria-label="Atlas, accueil"><svg viewBox="0 0 40 40" aria-hidden="true"><path d="m5 32 15-26 15 26h-8l-7-13-7 13Z"/><path d="M16 32h8l-4-7Z"/></svg>atlas<span class="brand-dot">.</span></a><div class="brand-sub">Gestion commerciale</div>
  <a href="#settings" class="workspace-switch"><span class="workspace-icon">${icon('building')}</span><div><strong>${esc(state.settings.name)}</strong><small>Espace de travail local</small></div></a>
  <p class="nav-label">VOTRE ACTIVITÉ</p><nav class="nav" aria-label="Navigation principale">${Object.entries(routes).filter(([r])=>r!=='settings'&&(window.AtlasPlatform?.enabled||!['purchases','suppliers','accounting','vat'].includes(r))&&(r!=='accounting'||state.permissions?.includes('accounting_read'))&&(r!=='vat'||state.permissions?.includes('vat_read'))).map(([r,name])=>`<a href="#${r}" class="${route===r?'active':''}" ${route===r?'aria-current="page"':''}>${icon({dashboard:'grid',products:'box',sales:'sale',customers:'users',movements:'arrows',purchases:'sale',suppliers:'building',accounting:'building',vat:'sale'}[r])}${name}${r==='products'?`<span class="nav-badge">${state.products.length}</span>`:''}</a>`).join('')}<div class="nav-divider"></div><a href="#settings" class="${route==='settings'?'active':''}" ${route==='settings'?'aria-current="page"':''}>${icon('settings')}Paramètres</a></nav>
  <div class="sidebar-bottom"><div class="local-card"><div>${icon('shield')}Votre activité, chez vous.</div><p>Vos données restent sur cet ordinateur. Pensez à les sauvegarder.</p></div><div class="profile"><span class="avatar">${esc(initials(state.settings.name))}</span><div><strong>Mon espace</strong><small>${state.settings.demo?'Démonstration':'Gestion locale'}</small></div><a href="#settings" aria-label="Paramètres">${icon('settings')}</a></div></div>`;
  document.querySelector('#topbar').innerHTML = `<button class="mobile-menu icon-btn" data-action="menu" aria-label="Ouvrir le menu">${icon('menu')}</button><div class="breadcrumbs">${icon('grid')}<span>Espace de travail</span>${icon('chevron')}<strong>${routes[route]}</strong></div><div class="topbar-right"><form class="global-search" id="global-search">${icon('search')}<input name="search" aria-label="Rechercher un produit" placeholder="Rechercher un produit…" autocomplete="off"><kbd>/</kbd></form><span class="topbar-date">${date(new Date(),{day:'numeric',month:'long',year:'numeric'})}</span><button class="notification" data-action="low-stock" aria-label="Voir les alertes de stock">${icon('bell')}</button><span class="avatar">${esc(initials(state.settings.name))}</span></div>`;
}
function render() {
  if (!state) return;
  if(!window.AtlasPlatform?.enabled && ['purchases','suppliers','accounting','vat'].includes(route))route='dashboard';
  if(route==='accounting'&&!state.accounting)route='dashboard';
  if(route==='vat'&&!state.vat)route='dashboard';
  renderShell();
  main.innerHTML = ({dashboard:dashboardView,products:productsView,sales:salesView,customers:customersView,movements:movementsView,settings:settingsView,purchases:()=>AtlasPurchases.view(),suppliers:()=>AtlasPurchases.suppliersView(),accounting:()=>AtlasAccounting.view(),vat:()=>AtlasVat.view()}[route])();
  document.title = `${routes[route]} · Atlas`;
  window.AtlasPlatform?.enhance();
}
function navigate(next, nextFilter='all', nextQuery='') {
  const changed = route!==next;
  route=next; filter=nextFilter; query=nextQuery; category='';
  if (location.hash!==`#${next}`) history.pushState(null,'',`#${next}`);
  document.querySelector('#sidebar').classList.remove('open');
  document.querySelector('.mobile-backdrop')?.classList.remove('show');
  render();
  if(changed) window.scrollTo(0,0);
}

function dashboardView() {
  const active=activeSales(), recent=active.filter(s=>new Date(s.created_at)>=new Date(Date.now()-30*86400000));
  const revenue=sum(recent,'subtotal'), pending=sum(active,'total')-sum(active,'paid'), units=sum(state.products,'stock');
  const low=lowProducts();
  const days=Array.from({length:7},(_,i)=>{const d=new Date();d.setDate(d.getDate()-6+i);const key=[d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');return {label:i===6?'Auj.':date(d,{weekday:'short'}),value:sum(active.filter(s=>dayKey(s.created_at)===key),'subtotal'),date:key};});
  const maximum=Math.max(10000,...days.map(d=>d.value));
  return heading('VOTRE COMMERCE, EN UN COUP D’ŒIL', 'Chaque jour, une vue plus claire.', 'Retrouvez l’essentiel de votre activité et passez à la suite.', `${state.settings.demo?'<span class="demo-label"><i></i>Données démo</span>':''}${saleButton}`)+
    `<section class="stats-grid" aria-label="Indicateurs de votre activité">${statsCard('Chiffre d’affaires HT',amount(revenue),'DH',`${icon('trend')}<span class="positive">${recent.length} ventes</span> sur les 30 derniers jours`,'wallet',true)}${statsCard('Ventes réalisées',number(recent.length),'ventes',`${icon('calendar')}30 derniers jours · hors annulations`,'sale')}${statsCard('Produits en stock',number(units),'unités',`${state.products.length} références dans votre catalogue`,'box')}${statsCard('Reste à encaisser',amount(pending),'DH',`${active.filter(s=>s.paid<s.total).length} ventes avec un solde restant`,'clock')}</section>
    <div class="dashboard-middle"><section class="card"><div class="card-head"><div><h2>Le rythme de vos ventes</h2><p class="subtitle">Une semaine d’activité, en un regard.</p></div><span class="period">${icon('calendar')}7 derniers jours</span></div><div class="chart-legend"><i></i>Chiffre d’affaires HT · DH</div><div class="chart-wrap" role="img" aria-label="Ventes des 7 derniers jours : ${esc(days.map(d=>`${d.label} ${currency(d.value)}`).join(', '))}"><div class="chart-axis">${[1,.75,.5,.25,0].map(m=>`<span>${number(Math.round(maximum*m/100))}</span>`).join('')}</div><div class="chart-plot"><div class="chart-grid">${'<i></i>'.repeat(5)}</div><div class="bars">${days.map(d=>`<div class="bar-column"><div class="bar-fill" tabindex="0" style="height:${d.value/maximum*100}%" aria-label="${esc(d.label)} : ${currency(d.value)}"><span class="chart-tooltip">${currency(d.value)}</span></div><span class="bar-label">${d.label}</span></div>`).join('')}</div></div></div><div class="chart-summary"><span>Total sur la période</span><strong>${currency(sum(days,'value'))}</strong></div></section>
    <section class="card attention"><div class="card-head"><div><h2>Un œil sur votre stock</h2><p class="subtitle">Les produits à réapprovisionner.</p></div><span class="count-badge">${low.length} alerte${low.length!==1?'s':''}</span></div><div class="alert-list">${low.length?low.slice(0,3).map(p=>`<div class="alert-item">${symbol(p)}<div class="alert-info"><strong>${esc(p.name)}</strong><small>Seuil d’alerte : ${p.minimum} unités</small></div><button class="stock-pill ${p.stock===0?'out':''}" data-action="receive" data-id="${p.id}" title="Réapprovisionner ${esc(p.name)}">${p.stock===0?'Rupture':`${p.stock} restants`}</button></div>`).join(''):empty('Tout est au vert','Vos stocks sont au-dessus des seuils.','','',true)}</div><div class="alert-footer"><button class="text-btn" data-action="low-stock">Voir les produits concernés ${icon('arrow')}</button></div></section></div>
    <div class="dashboard-bottom"><section class="card"><div class="card-head"><div><h2>Vos dernières ventes</h2><p class="subtitle">Les dernières nouvelles de votre activité.</p></div><a class="text-btn" href="#sales">Tout voir ${icon('arrow')}</a></div>${salesTable(state.sales.slice(0,5),true)}</section><section class="card quick-card"><div class="eyebrow">FAITES SIMPLE</div><h2>Moins de clics.<br>Plus de temps pour vous.</h2><p>Vos actions du quotidien, toujours à portée de main.</p><div class="quick-links"><button data-action="new-product">${icon('plus')}Ajouter un produit${icon('arrow')}</button><button data-action="receive">${icon('box')}Réceptionner du stock${icon('arrow')}</button><button data-action="new-customer">${icon('users')}Créer une fiche client${icon('arrow')}</button></div></section></div>`;
}

function searchControl(placeholder) {return `<div class="search-field">${icon('search')}<input id="list-search" aria-label="${esc(placeholder)}" placeholder="${esc(placeholder)}" value="${esc(query)}" autocomplete="off"></div>`;}
function productsView() {
  return heading('LE BON PRODUIT, AU BON MOMENT','Produits & stock','Un catalogue organisé. Un stock que vous pouvez suivre.',`<button class="btn" data-action="import">${icon('upload')}Importer</button><button class="btn primary" data-action="new-product">${icon('plus')}Nouveau produit</button>`)+
  `<div class="toolbar"><div class="tabs" role="group" aria-label="Filtrer par stock">${[['all','Tous les produits',state.products.length],['low','Stock faible',lowProducts().length],['out','En rupture',state.products.filter(p=>!p.stock).length]].map(([id,text,count])=>`<button class="tab ${filter===id?'active':''}" data-filter="${id}">${text}<span>${count}</span></button>`).join('')}</div><div class="filters">${searchControl('Nom ou référence…')}<select id="category-filter" aria-label="Filtrer par catégorie"><option value="">Toutes les catégories</option>${[...new Set(state.products.map(p=>p.category))].sort().map(c=>`<option ${category===c?'selected':''}>${esc(c)}</option>`).join('')}</select><a class="btn" href="/api/export/products">${icon('download')}Exporter</a></div></div><div id="list-content">${productsContent()}</div>`;
}
function productsContent() {
  const rows=state.products.filter(p=>(filter==='all'||filter==='low'&&p.stock<=p.minimum||filter==='out'&&p.stock===0)&&(!category||p.category===category)&&`${p.name} ${p.sku}`.toLowerCase().includes(query.toLowerCase()));
  return `<section class="card">${rows.length?`<div class="table-scroll"><table><thead><tr><th>Produit</th><th>Catégorie</th><th class="amount">Prix de vente HT</th><th>Stock disponible</th><th>État</th><th>Actions</th></tr></thead><tbody>${rows.map(p=>`<tr><td><div class="table-product">${symbol(p)}<div><strong>${esc(p.name)}</strong><small>${esc(p.sku)}</small></div></div></td><td>${esc(p.category)}</td><td class="amount">${currency(p.price)}</td><td><strong class="mono">${number(p.stock)}</strong> <span class="muted">unités</span></td><td>${productStatus(p)}</td><td><div class="row-actions"><button class="icon-btn" data-action="edit-product" data-id="${p.id}" aria-label="Modifier ${esc(p.name)}" title="Modifier">${icon('edit')}</button><button class="icon-btn" data-action="receive" data-id="${p.id}" aria-label="Mouvement de stock pour ${esc(p.name)}" title="Mouvement de stock">${icon('arrows')}</button></div></td></tr>`).join('')}</tbody></table></div>`:empty('Aucun produit ici',state.products.length?'Essayez une autre recherche ou un autre filtre.':'Ajoutez votre premier produit pour commencer.',state.products.length?'':'new-product','Ajouter un produit')}</section><p class="table-count">${rows.length} produit${rows.length!==1?'s':''} · Prix en dirhams marocains, hors taxe</p>`;
}
function salesTable(rows,compact=false) {
  return rows.length?`<div class="table-scroll"><table class="${compact?'recent-table':''}"><thead><tr><th>Référence</th><th>Client</th>${compact?'':'<th>Date</th>'}<th class="amount">Total TTC</th><th>Statut</th>${compact?'':'<th class="amount">Reste dû</th>'}</tr></thead><tbody>${rows.map(s=>{const [text,tone]=salesStatus(s);return `<tr><td><button class="table-link" data-action="view-sale" data-id="${s.id}">VT-${String(s.number||s.id).padStart(4,'0')}</button>${compact?`<div style="font-size:9px;margin-top:5px;color:#9aa58e">${shortDate(s.created_at)}</div>`:''}</td><td>${esc(s.customer_name)}</td>${compact?'':`<td>${date(s.created_at)}</td>`}<td class="amount">${currency(s.total)}</td><td>${badge(text,tone)}</td>${compact?'':`<td class="amount">${s.status==='cancelled'?'—':currency(s.total-s.paid)}</td>`}</tr>`;}).join('')}</tbody></table></div>`:empty('La première vente vous attend','Vos ventes et leur suivi de paiement apparaîtront ici.','new-sale','Créer une vente',compact);
}
function salesView() {
  const active=activeSales();
  return heading('DE LA VENTE À L’ENCAISSEMENT','Vos ventes, bien suivies.','Créez une vente, suivez les règlements, gardez le fil.',saleButton)+`<section class="stats-grid">${statsCard('Total vendu TTC',amount(sum(active,'total')),'DH','Depuis le début de votre activité','sale',true)}${statsCard('Montant encaissé',amount(sum(active,'paid')),'DH','Paiements enregistrés','wallet')}${statsCard('Reste à encaisser',amount(sum(active,'total')-sum(active,'paid')),'DH','Toutes les ventes actives','clock')}${statsCard('Ventes actives',number(active.length),'ventes',`${state.sales.filter(s=>s.status==='cancelled').length} vente(s) annulée(s)`,'check')}</section><div class="toolbar"><div class="tabs" role="group" aria-label="Filtrer les ventes">${[['all','Toutes'],['unpaid','À encaisser'],['paid','Payées'],['cancelled','Annulées']].map(([id,text])=>`<button class="tab ${filter===id?'active':''}" data-filter="${id}">${text}</button>`).join('')}</div><div class="filters">${searchControl('Client ou référence…')}</div></div><section class="card" id="list-content">${salesContent()}</section>`;
}
function salesContent() {return salesTable(state.sales.filter(s=>(filter==='all'||filter==='unpaid'&&s.status==='active'&&s.paid<s.total||filter==='paid'&&s.status==='active'&&s.paid===s.total||filter==='cancelled'&&s.status==='cancelled')&&`${s.customer_name} VT-${String(s.number||s.id).padStart(4,'0')}`.toLowerCase().includes(query.toLowerCase())));}
function customersView() { return heading('DES RELATIONS QUI COMPTENT','Vos clients','Leurs coordonnées et leur activité, au même endroit.',`<button class="btn primary" data-action="new-customer">${icon('plus')}Nouveau client</button>`)+`<div class="toolbar"><span class="stat-note">${state.customers.length} clients dans votre carnet</span><div class="filters">${searchControl('Nom, ville ou téléphone…')}</div></div><div id="list-content">${customersContent()}</div>`; }
function customersContent() {
  const rows=state.customers.filter(c=>`${c.name} ${c.city} ${c.phone} ${c.email}`.toLowerCase().includes(query.toLowerCase()));
  return rows.length?`<div class="customer-grid">${rows.map(c=>{const sales=activeSales().filter(s=>s.customer_id===c.id);return `<article class="card customer-card"><div class="customer-head"><span class="avatar">${esc(initials(c.name))}</span><div><h3>${esc(c.name)}</h3><small>${sales.length} vente${sales.length!==1?'s':''}</small></div><button class="icon-btn" data-action="edit-customer" data-id="${c.id}" aria-label="Modifier ${esc(c.name)}">${icon('edit')}</button></div><div class="customer-contact"><div>${icon('pin')}${esc(c.city)||'Ville non renseignée'}</div><div>${icon('phone')}${esc(c.phone)||'Téléphone non renseigné'}</div><div>${icon('mail')}${esc(c.email)||'Email non renseigné'}</div></div><div class="customer-stats"><div>Total des achats<strong>${currency(sum(sales,'total'))}</strong></div><div>Reste à régler<strong>${currency(sum(sales,'total')-sum(sales,'paid'))}</strong></div></div></article>`;}).join('')}</div>`:empty('Aucun client trouvé','Créez une fiche pour retrouver facilement votre client.','new-customer','Ajouter un client');
}
function movementsView() {return heading('CHAQUE ENTRÉE, CHAQUE SORTIE','L’histoire de votre stock','Un journal des mouvements pour comprendre ce qui a changé.',`<button class="btn primary" data-action="receive">${icon('arrows')}Mouvement de stock</button>`)+`<div class="toolbar"><div class="tabs" role="group" aria-label="Filtrer les mouvements">${[['all','Tous'],['in','Entrées'],['out','Sorties']].map(([id,text])=>`<button class="tab ${filter===id?'active':''}" data-filter="${id}">${text}</button>`).join('')}</div><div class="filters">${searchControl('Produit, référence ou motif…')}</div></div><section class="card" id="list-content">${movementsContent()}</section><p class="table-count">Les 1 000 derniers mouvements au maximum · Historique complet conservé dans la base</p>`;}
function movementsContent() {const rows=state.movements.filter(m=>(filter==='all'||filter==='in'&&m.quantity>0||filter==='out'&&m.quantity<0)&&`${m.name} ${m.sku} ${m.note}`.toLowerCase().includes(query.toLowerCase()));return rows.length?`<div class="table-scroll"><table><thead><tr><th>Date</th><th>Produit</th><th>Type</th><th class="amount">Quantité</th><th>Motif</th></tr></thead><tbody>${rows.map(m=>`<tr><td>${date(m.created_at)}<small class="muted" style="display:block;margin-top:5px">${new Date(m.created_at).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'})}</small></td><td><div class="table-product"><div><strong>${esc(m.name)}</strong><small>${esc(m.sku)}</small></div></div></td><td>${badge({receipt:'Réception',adjustment:'Sortie manuelle',sale:'Vente',opening:'Stock initial',return:'Annulation',purchase:'Achat réceptionné',purchase_cancel:'Annulation achat'}[m.kind]||m.kind,m.quantity>0?'':'neutral')}</td><td class="amount ${m.quantity>0?'movement-positive':'movement-negative'}">${m.quantity>0?'+':''}${number(m.quantity)}</td><td>${esc(m.note)}</td></tr>`).join('')}</tbody></table></div>`:empty('Aucun mouvement','Les ventes et les réceptions alimenteront automatiquement ce journal.');}
function settingsView() {
  const s=state.settings;
  return heading('UN ESPACE À VOTRE IMAGE','Paramètres','Les informations de votre entreprise et vos sauvegardes.')+`<div class="settings-grid"><section class="card"><div class="card-head"><h2>Votre entreprise</h2>${icon('building')}</div><form id="settings-form" class="card-body"><div class="form-grid">${field('Nom de l’entreprise','name',s.name,'text',true,true)}${field('Téléphone','phone',s.phone,'tel',false,true)}<label class="field full"><span>Adresse</span><textarea name="address" maxlength="500">${esc(s.address)}</textarea></label></div><div class="form-error" role="alert"></div><div class="settings-footer"><button class="btn primary" type="submit">${icon('check')}Enregistrer</button></div></form></section><div class="stack"><section class="card"><div class="card-body"><div class="settings-badge">${icon('shield')}Vos données restent chez vous</div><h2 style="margin-top:15px">Gardez une copie de votre activité.</h2><p>La sauvegarde contient vos produits, clients, ventes, paiements et mouvements. Conservez une copie sur un autre support.</p><a class="btn primary" href="/api/backup">${icon('download')}Télécharger la sauvegarde</a><p style="font-size:10px;margin-bottom:0">Pour restaurer : arrêtez Atlas, conservez l’ancienne base puis relancez avec le fichier de sauvegarde. Instructions dans le README.</p></div></section><section class="card"><div class="card-body"><h2>Votre espace</h2><div class="settings-info" style="margin-top:22px"><div class="info-row"><span>Mode</span><strong>${s.demo?'Démonstration':'Base de travail'}</strong></div><div class="info-row"><span>Devise</span><strong>Dirham marocain · MAD</strong></div><div class="info-row"><span>Stock</span><strong>Quantités entières</strong></div><div class="info-row"><span>Stockage</span><strong>Local · SQLite</strong></div></div>${s.demo?'<div class="notice warning">Cet espace contient des données fictives. Pour travailler avec une base vide, suivez « Démarrer sans exemples » dans le README.</div>':''}<div class="notice">La taxe est saisie pour chaque vente. Les documents de vente ne remplacent pas votre logiciel de comptabilité.</div></div></section></div></div>`;
}

function field(title,name,value='',type='text',required=true,full=false,extra='') {return `<label class="field ${full?'full':''}"><span>${title}${required?' *':''}</span><input name="${name}" value="${esc(value)}" type="${type}" ${required?'required':''} ${type==='number'?`${extra.includes('min=')?'':'min="0"'} ${extra.includes('step=')?'':'step="0.01"'}`:'maxlength="160"'} ${extra}></label>`;}
function modal(title,subtitle,body,actions='',wide=false,formId='') {
  dialog.className=wide?'wide':'';
  dialog.innerHTML=`${formId?`<form id="${formId}">`:''}<div class="dialog-head"><div><h2 id="dialog-title">${esc(title)}</h2><p>${esc(subtitle)}</p></div><button type="button" class="icon-btn" data-action="close" aria-label="Fermer">${icon('close')}</button></div><div class="dialog-body">${body}<div class="form-error" role="alert"></div></div>${actions?`<div class="dialog-actions">${actions}</div>`:''}${formId?'</form>':''}`;
  if(!dialog.open) dialog.showModal();
}
const cancelButton = '<button type="button" class="btn" data-action="close">Fermer</button>';
function productModal(id) {
  const p=state.products.find(p=>p.id===id);
  modal(p?'Modifier le produit':'Un nouveau produit',p?'Les modifications de prix s’appliqueront aux prochaines ventes.':'Renseignez l’essentiel. Vous pourrez le modifier plus tard.',`<input type="hidden" name="id" value="${p?.id||''}"><div class="form-grid">${field('Nom du produit','name',p?.name||'','text',true,true)}${field('Référence','sku',p?.sku||'')}${field('Catégorie','category',p?.category||'Général','text',true,false,'list="categories"')}<datalist id="categories">${[...new Set(state.products.map(p=>p.category))].map(c=>`<option value="${esc(c)}">`).join('')}</datalist>${field('Prix d’achat HT · DH','cost',p?amount(p.cost).replace(/\s/g,'').replace(',','.'):0,'number')}${field('Prix de vente HT · DH','price',p?String(p.price/100):'','number')}${p?`<label class="field"><span>Stock actuel</span><input disabled value="${p.stock} unités"><small>Utilisez « Mouvement de stock » pour le modifier.</small></label>`:field('Stock initial · unités','stock',0,'number',true,false,'step="1"')}${field('Seuil d’alerte · unités','minimum',p?.minimum??5,'number',true,false,'step="1"')}</div>`,`${cancelButton}<button type="submit" class="btn primary">${icon('check')}${p?'Enregistrer':'Créer le produit'}</button>`,false,'product-form');
}
function customerModal(id) {
  const c=state.customers.find(c=>c.id===id);
  modal(c?'Modifier le client':'Un nouveau client','Un contact facile à retrouver pour vos prochaines ventes.',`<input type="hidden" name="id" value="${c?.id||''}"><div class="form-grid">${field('Nom ou raison sociale','name',c?.name||'','text',true,true)}${field('Téléphone','phone',c?.phone||'','tel',false)}${field('Ville','city',c?.city||'','text',false)}${field('Email','email',c?.email||'','email',false,true)}</div>`,`${cancelButton}<button type="submit" class="btn primary">${icon('check')}Enregistrer le client</button>`,false,'customer-form');
}
function stockModal(id) {
  if(!state.products.length){toast('Ajoutez d’abord un produit.');return productModal();}
  modal('Un mouvement de stock','Chaque modification est conservée dans votre historique.',`<input type="hidden" name="request_key" value="${crypto.randomUUID()}"><div class="form-grid"><label class="field full"><span>Produit *</span><select name="product_id" required>${state.products.map(p=>`<option value="${p.id}" ${p.id===id?'selected':''}>${esc(p.name)} · ${p.stock} en stock</option>`).join('')}</select></label><label class="field"><span>Type de mouvement</span><select name="kind"><option value="receipt">Entrée de stock</option><option value="adjustment">Sortie manuelle</option></select></label>${field('Quantité · unités','quantity',1,'number',true,false,'step="1" min="1"')}<label class="field full"><span>Motif *</span><textarea name="note" required maxlength="500" placeholder="Ex. Réception fournisseur, inventaire, casse…"></textarea></label></div>`,`${cancelButton}<button type="submit" class="btn primary">${icon('check')}Enregistrer le mouvement</button>`,false,'stock-form');
}

function newSale() {
  if(!state.products.some(p=>p.stock>0)){toast('Ajoutez du stock avant de créer une vente.');return stockModal();}
  cart=[];saleKey=crypto.randomUUID();
  modal('Une nouvelle vente','Choisissez vos produits. Atlas s’occupe du suivi de stock.',`<div class="sale-layout"><div><label class="field"><span>Client</span><select name="customer_id"><option value="">Client de passage</option>${state.customers.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></label><div class="section-label">Ajouter un produit</div><div style="display:flex;gap:8px;align-items:end"><label class="field" style="flex:1"><select id="sale-product" aria-label="Produit à ajouter">${state.products.filter(p=>p.stock>0).map(p=>`<option value="${p.id}">${esc(p.name)} · ${currency(p.price)}</option>`).join('')}</select></label><button type="button" class="btn" data-action="add-line" aria-label="Ajouter le produit">${icon('plus')}</button></div><div id="sale-lines" class="sale-lines"></div><label class="field" style="margin-top:22px"><span>Note (facultatif)</span><textarea name="note" maxlength="1000" placeholder="Une précision pour cette vente…"></textarea></label></div><aside class="sale-summary"><h3>Récapitulatif</h3><div class="total-row"><span>Sous-total HT</span><strong id="sale-subtotal">0,00 DH</strong></div><label class="field"><span>Taxe · taux en %</span><input name="tax_percent" type="number" value="0" min="0" max="100" step="0.01" required><small>À définir selon votre activité.</small></label><div class="total-row"><span>Montant de la taxe</span><strong id="sale-tax">0,00 DH</strong></div><div class="total-row final"><span>Total TTC</span><span id="sale-total">0,00 DH</span></div>${field('Montant encaissé · DH','paid',0,'number')}<button type="button" class="btn small" data-action="pay-full">Tout encaisser</button><label class="field"><span>Mode de paiement</span><select name="method">${methods()}</select></label><div class="notice">Le stock est déduit lorsque vous validez la vente.</div></aside></div>`,`${cancelButton}<button class="btn primary" type="submit">${icon('check')}Valider la vente</button>`,true,'sale-form');
  renderCart();
}
function methods(){return ['Espèces','Virement','Carte','Chèque'].map(m=>`<option>${m}</option>`).join('');}
function renderCart() {
  document.querySelector('#sale-lines').innerHTML=cart.length?cart.map(item=>{const p=state.products.find(p=>p.id===item.product_id);return `<div class="sale-line"><div class="sale-line-info"><strong>${esc(p.name)}</strong><small>${currency(p.price)} HT · ${p.stock} disponibles</small></div><input type="number" class="quantity-input" aria-label="Quantité ${esc(p.name)}" value="${item.quantity}" min="1" max="${p.stock}" step="1" data-quantity="${p.id}" required><span class="line-total">${currency(p.price*item.quantity)}</span><button type="button" class="icon-btn" data-action="remove-line" data-id="${p.id}" aria-label="Retirer ${esc(p.name)}">${icon('close')}</button></div>`;}).join(''):empty('Votre panier est encore vide','Sélectionnez un produit puis cliquez sur +.','','',true);
  updateTotals();
}
function cartTotals() {
  const subtotal=cart.reduce((n,item)=>n+(state.products.find(p=>p.id===item.product_id)?.price||0)*(Number(item.quantity)||0),0);
  const rate=Number(document.querySelector('[name="tax_percent"]')?.value)||0;
  const bps=Math.round(rate*100);
  const tax=Math.round(subtotal*bps/10000);
  return {subtotal,tax,total:subtotal+tax,bps};
}
function updateTotals() {const t=cartTotals();for(const key of ['subtotal','tax','total']) document.querySelector(`#sale-${key}`).textContent=currency(t[key]);}
function saleDetails(id) {
  const s=state.sales.find(s=>s.id===id), items=state.sale_items.filter(i=>i.sale_id===id), payments=state.payments.filter(p=>p.sale_id===id);
  if(!s) return;
  const [text,tone]=salesStatus(s);
  modal(`Vente VT-${String(s.number||s.id).padStart(4,'0')}`,`${date(s.created_at)} · ${s.customer_name}`,`<div class="sale-details-meta"><div><small>CLIENT</small><strong>${esc(s.customer_name)}</strong></div><div><small>STATUT</small>${badge(text,tone)}</div><div><small>RÈGLEMENT RESTANT</small><strong>${s.status==='cancelled'?'—':currency(s.total-s.paid)}</strong></div></div>${saleItemsTable(items)}<div class="detail-totals"><div class="total-row"><span>Total HT</span><strong>${currency(s.subtotal)}</strong></div><div class="total-row"><span>Taxe (${number(s.tax_bps/100)} %)</span><strong>${currency(s.tax)}</strong></div><div class="total-row final"><span>Total TTC</span><span>${currency(s.total)}</span></div></div>${s.note?`<div class="notice">${esc(s.note)}</div>`:''}${payments.length?`<h3>Historique des règlements</h3><div class="payment-list">${payments.map(p=>`<div class="payment-item"><span>${date(p.created_at)} · ${esc(p.method)}</span><strong>${currency(p.amount)}</strong></div>`).join('')}</div>`:''}${s.status==='active'&&s.paid===0&&(!window.AtlasPlatform?.enabled||window.AtlasPlatform.can('cancel'))?`<div style="margin-top:20px"><button class="edit-link" data-action="cancel-sale" data-id="${id}">Annuler cette vente et remettre les produits en stock</button></div>`:''}`,`${cancelButton}<button class="btn" data-action="print-sale" data-id="${id}">${icon('print')}Imprimer</button>${s.status==='active'&&s.paid<s.total&&(!window.AtlasPlatform?.enabled||window.AtlasPlatform.can('payments'))?`<button class="btn primary" data-action="payment" data-id="${id}">${icon('wallet')}Ajouter un règlement</button>`:''}`,true);
}
function saleItemsTable(items) {return `<div class="table-scroll"><table><thead><tr><th>Produit</th><th>Qté</th><th class="amount">Prix HT</th><th class="amount">Total HT</th></tr></thead><tbody>${items.map(i=>`<tr><td>${esc(i.name)}<small class="muted" style="display:block;margin-top:4px">${esc(i.sku)}</small></td><td>${i.quantity}</td><td class="amount">${currency(i.price)}</td><td class="amount">${currency(i.price*i.quantity)}</td></tr>`).join('')}</tbody></table></div>`;}
function paymentModal(id) {
  const s=state.sales.find(s=>s.id===id);
  modal('Enregistrer un règlement',`VT-${String(state.sales.find(s=>s.id===id)?.number||id).padStart(4,'0')} · ${s.customer_name}`,`<input type="hidden" name="request_key" value="${crypto.randomUUID()}"><input type="hidden" name="sale_id" value="${id}"><div class="notice">Reste à encaisser : <strong>${currency(s.total-s.paid)}</strong></div><div class="form-grid">${field('Montant · DH','amount',(s.total-s.paid)/100,'number',true,false,`max="${(s.total-s.paid)/100}"`)}<label class="field"><span>Mode de paiement</span><select name="method">${methods()}</select></label></div>`,`${cancelButton}<button class="btn primary" type="submit">${icon('check')}Enregistrer le règlement</button>`,false,'payment-form');
}
function cancelSale(id) {modal('Annuler cette vente ?',`VT-${String(state.sales.find(s=>s.id===id)?.number||id).padStart(4,'0')}`,`<p style="font-size:13px;line-height:1.8">Les produits seront remis en stock. La vente restera dans votre historique avec le statut « Annulée ».</p>`,`${cancelButton}<button class="btn danger" data-action="confirm-cancel" data-id="${id}">Annuler la vente</button>`);}
function printSale(id) {
  const s=state.sales.find(s=>s.id===id), c=state.settings, items=state.sale_items.filter(i=>i.sale_id===id);
  document.querySelector('#print-area').innerHTML=`<div class="print-head"><div><h1>${esc(c.name)}</h1><p>${esc(c.address).replace(/\n/g,'<br>')}<br>${esc(c.phone)}</p></div><div><h2>Bon de vente</h2><p>VT-${String(state.sales.find(s=>s.id===id)?.number||id).padStart(4,'0')}<br>${date(s.created_at)}<br>${s.status==='cancelled'?'ANNULÉE':salesStatus(s)[0]}</p></div></div><p><strong>Client</strong><br>${esc(s.customer_name)}</p>${saleItemsTable(items)}<div class="detail-totals"><div class="total-row"><span>Total HT</span><strong>${currency(s.subtotal)}</strong></div><div class="total-row"><span>Taxe (${number(s.tax_bps/100)} %)</span><strong>${currency(s.tax)}</strong></div><div class="total-row final"><span>Total TTC</span><strong>${currency(s.total)}</strong></div><div class="total-row"><span>Encaissé</span><strong>${currency(s.paid)}</strong></div><div class="total-row"><span>Reste dû</span><strong>${s.status==='cancelled'?'—':currency(s.total-s.paid)}</strong></div></div>${s.note?`<p>${esc(s.note)}</p>`:''}<p class="print-note">${c.demo?'DÉMONSTRATION — Données fictives. ':''}Bon de vente interne · Édité avec Atlas. Ce document n’est pas une facture fiscale.</p>`;
  window.print();
}
function importModal() {
  modal('Importer votre catalogue','Ajoutez des produits à partir d’un fichier CSV.',`<p style="font-size:12px;line-height:1.8;color:#839371">Colonnes : <strong>sku, name, category, cost, price, stock, minimum</strong><br>Prix en DH, avec un point décimal. Quantités entières. Séparateur : virgule.</p><button type="button" class="text-btn" data-action="csv-template" style="margin-top:14px">${icon('download')}Télécharger le modèle CSV</button><div class="file-drop"><label for="csv-file">Choisissez votre fichier (1 Mo maximum)</label><input id="csv-file" name="file" type="file" accept=".csv,text/csv" required></div><div id="csv-preview"></div><div class="notice">Les nouvelles références seront ajoutées. Si une référence existe déjà ou si une ligne est invalide, rien ne sera importé. Vos produits actuels sont conservés.</div>`,`${cancelButton}<button class="btn primary" type="submit">${icon('upload')}Importer les produits</button>`,false,'import-form');
}
function downloadTemplate() {const blob=new Blob(['sku,name,category,cost,price,stock,minimum\nPRD-001,Mon produit,Général,50.00,80.00,10,3\n'],{type:'text/csv;charset=utf-8'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='modele-produits-atlas.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}

document.addEventListener('click',async event=>{
  const nav=event.target.closest('a[href^="#"]');
  if(nav && routes[nav.hash.slice(1)]){event.preventDefault();navigate(nav.hash.slice(1));return;}
  const tab=event.target.closest('[data-filter]');
  if(tab){filter=tab.dataset.filter;render();return;}
  const button=event.target.closest('[data-action]');if(!button)return;
  const id=Number(button.dataset.id), action=button.dataset.action;
  const actions={
    close:()=>dialog.close(), 'new-product':()=>productModal(), 'edit-product':()=>productModal(id),
    'new-customer':()=>customerModal(),'edit-customer':()=>customerModal(id),receive:()=>stockModal(id),
    'new-sale':newSale,'view-sale':()=>saleDetails(id),payment:()=>paymentModal(id),'cancel-sale':()=>cancelSale(id),
    'print-sale':()=>printSale(id),import:importModal,'csv-template':downloadTemplate,
    'low-stock':()=>navigate('products','low'),
    menu:()=>{document.querySelector('#sidebar').classList.toggle('open');let backdrop=document.querySelector('.mobile-backdrop');if(!backdrop){backdrop=document.createElement('div');backdrop.className='mobile-backdrop';document.body.append(backdrop);backdrop.addEventListener('click',()=>{backdrop.classList.remove('show');document.querySelector('#sidebar').classList.remove('open');});}backdrop.classList.toggle('show');},
    'add-line':()=>{const pid=Number(document.querySelector('#sale-product').value),p=state.products.find(p=>p.id===pid);const existing=cart.find(i=>i.product_id===pid);if(existing){if(existing.quantity>=p.stock)return toast('Tout le stock disponible est déjà dans le panier.',true);existing.quantity++;}else cart.push({product_id:pid,quantity:1});renderCart();},
    'remove-line':()=>{cart=cart.filter(i=>i.product_id!==id);renderCart();},
    'pay-full':()=>{document.querySelector('[name="paid"]').value=(cartTotals().total/100).toFixed(2);},
    'confirm-cancel':async()=>{button.disabled=true;try{await api('cancel',{sale_id:id});await refresh();saleDetails(id);toast('Vente annulée. Les produits sont de retour en stock.');}catch(e){dialog.querySelector('.form-error').textContent=e.message;button.disabled=false;}},
  };
  if(actions[action])actions[action]();
});
document.addEventListener('input',event=>{
  if(event.target.id==='list-search'){query=event.target.value;renderList();}
  if(event.target.name==='tax_percent') updateTotals();
  if(event.target.dataset.quantity){const item=cart.find(i=>i.product_id===Number(event.target.dataset.quantity));item.quantity=Number(event.target.value);const p=state.products.find(p=>p.id===item.product_id);event.target.closest('.sale-line').querySelector('.line-total').textContent=currency(p.price*item.quantity);updateTotals();}
});
document.addEventListener('change',async event=>{
  if(event.target.id==='category-filter'){category=event.target.value;renderList();}
  if(event.target.id==='csv-file'){
    const file=event.target.files[0];const preview=document.querySelector('#csv-preview');
    if(!file){preview.innerHTML='';return;}
    if(file.size>1_000_000){event.target.value='';return toast('Le fichier dépasse 1 Mo.',true);}
    preview.innerHTML=`<p class="stat-note">Aperçu des 5 premières lignes · ${esc(file.name)}</p><pre class="import-preview">${esc((await file.text()).split('\n').slice(0,5).join('\n'))}</pre>`;
  }
});
function renderList(){const views={products:productsContent,sales:salesContent,customers:customersContent,movements:movementsContent,purchases:()=>AtlasPurchases.content(),suppliers:()=>AtlasPurchases.suppliersContent()};if(views[route]){document.querySelector('#list-content').innerHTML=views[route]();window.AtlasPlatform?.enhance();}}
document.addEventListener('submit',async event=>{
  event.preventDefault();const form=event.target, formName=form.getAttribute('id');
  if(formName==='global-search'){navigate('products','all',new FormData(form).get('search'));return;}
  const submit=form.querySelector('[type="submit"]');if(submit?.disabled)return;
  const error=form.querySelector('.form-error');if(error)error.textContent='';
  if(submit)submit.disabled=true;
  try{
    const data=Object.fromEntries(new FormData(form));let result, message;
    if(formName==='product-form'){result=await api('products',data);message='Produit enregistré.';}
    if(formName==='customer-form'){result=await api('customers',data);message='Client enregistré.';}
    if(formName==='stock-form'){result=await api('stock',data);message='Mouvement de stock enregistré.';}
    if(formName==='settings-form'){result=await api('settings',data);message='Informations de l’entreprise enregistrées.';}
    if(formName==='payment-form'){result=await api('payments',data);message='Règlement enregistré.';}
    if(formName==='sale-form'){result=await api('sales',{...data,request_key:saleKey,items:cart,tax_bps:cartTotals().bps});message='Vente enregistrée. Le stock est à jour.';}
    if(formName==='import-form'){const file=form.querySelector('[type="file"]').files[0];if(!file||file.size>1_000_000)throw new Error('Choisissez un fichier CSV de moins de 1 Mo.');result=await api('import',{csv:await file.text()});message=`${result.count} produits importés.`;}
    if(!result)return;
    await refresh();dialog.close();main.focus({preventScroll:true});toast(message);
    if(formName==='sale-form'||formName==='payment-form')saleDetails(result.id);
  }catch(e){if(error)error.textContent=e.message;else toast(e.message,true);}
  finally{if(submit)submit.disabled=false;}
});
document.addEventListener('keydown',event=>{
  if(event.key==='/'&&!dialog.open&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)){event.preventDefault();document.querySelector('#global-search input')?.focus();}
});
window.addEventListener('popstate',()=>{const hash=location.hash.slice(1);navigate(routes[hash]?hash:'dashboard');});
async function start(){route=routes[location.hash.slice(1)]?location.hash.slice(1):'dashboard';try{if(!window.AtlasPlatform || await window.AtlasPlatform.initialize())await refresh();}catch(e){main.innerHTML=`<div class="empty"><h3>Impossible d’ouvrir votre espace</h3><p>${esc(e.message)}<br>Vérifiez que le serveur Atlas est démarré, puis actualisez la page.</p><button class="btn primary" id="retry">Réessayer</button></div>`;document.querySelector('#retry').onclick=start;}}
start();
