'use strict';
window.AtlasPlatform = {
  enabled:false, session:null, companyId:null, busy:0, userRows:[],
  async request(path, body) {
    if(body !== undefined) this.busy++;
    try {
      const response = await fetch(`/api/${path}`, body === undefined ? {} : {
        method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':this.session?.csrf_token || ''}, body:JSON.stringify(body)
      });
      const data = await response.json();
      if(!response.ok) {
        if(response.status===401 && path!=='auth/login' && this.enabled) this.showLogin();
        const error = new Error(data.error || 'Une erreur est survenue.'); error.status=response.status; throw error;
      }
      return data;
    } finally { if(body !== undefined) this.busy--; }
  },
  async initialize() {
    try { this.session=await this.request('auth/me'); }
    catch(error) { if(error.status===404){this.enabled=false;return true;} throw error; }
    this.enabled=true;
    if(!this.session.authenticated){this.showLogin();return false;}
    document.body.classList.remove('auth-mode');
    const saved=Number(sessionStorage.getItem('atlas-company'));
    this.companyId=this.session.companies.find(c=>c.id===saved)?.id || this.session.companies[0]?.id || null;
    if(!this.companyId){this.showNoAccess();return false;}
    return true;
  },
  showLogin() {
    this.companyId=null;
    window.AtlasPurchases?.reset();
    window.AtlasAccounting?.reset();
    window.AtlasVat?.reset();
    state=null;
    dialog.close();dialog.innerHTML='';
    document.querySelector('#print-area').innerHTML='';
    document.querySelector('#sidebar').innerHTML='';document.querySelector('#topbar').innerHTML='';
    document.querySelector('.mobile-backdrop')?.classList.remove('show');
    document.body.classList.add('auth-mode');
    main.innerHTML=`<div class="auth-layout"><section class="auth-story"><div class="auth-brand">atlas<span>.</span></div><div class="eyebrow">UN ESPACE. TOUTES VOS SOCIÉTÉS.</div><h1>Votre activité,<br>en bonne compagnie.</h1><p>Retrouvez vos équipes, vos produits et vos ventes dans un espace organisé pour chaque société.</p><div class="auth-points"><span>${icon('building')}Des sociétés bien séparées</span><span>${icon('users')}Les bons accès pour chacun</span><span>${icon('shield')}Un historique de vos actions</span></div><small>Gestion commerciale · Première étape de votre suite Atlas</small></section><section class="auth-card"><span class="auth-icon">${icon('shield')}</span><h2>Bienvenue dans votre espace</h2><p>Connectez-vous avec votre compte Atlas.</p>${this.session?.setup_required?'<div class="notice">Votre espace attend sa première configuration. Lancez <code>python manage.py setup_atlas</code> sur le serveur pour créer votre compte administrateur.</div>':''}<form id="platform-login"><label class="field"><span>Identifiant</span><input name="username" autocomplete="username" required maxlength="150" autofocus></label><label class="field"><span>Mot de passe</span><input name="password" type="password" autocomplete="current-password" required maxlength="1024"></label><div class="form-error" role="alert"></div><button type="submit" class="btn primary">Se connecter ${icon('arrow')}</button></form><small>Un accès manquant ? Contactez l’administrateur de votre organisation.</small></section></div>`;
    document.title='Connexion · Atlas';
    main.querySelector('[name=username]')?.focus();
  },
  showNoAccess() {
    state=null;dialog.close();document.querySelector('#sidebar').innerHTML='';document.querySelector('#topbar').innerHTML='';
    document.querySelector('#print-area').innerHTML='';
    main.innerHTML=`<div class="empty"><h3>Aucune société accessible</h3><p>Votre administrateur peut vous attribuer un accès.</p>${this.session.user.is_org_admin?'<button class="btn primary" data-action="platform-new-company">Créer une société</button>':''}<button class="btn" data-action="platform-logout">Se déconnecter</button></div>`;
  },
  can(permission) {return !this.enabled || (state?.permissions || []).includes(permission);},
  async switchCompany(id) {
    if(this.busy){const select=document.querySelector('#platform-company-select');if(select)select.value=String(this.companyId);return toast('Attendez la fin de l’enregistrement avant de changer de société.',true);}
    if(!this.session.companies.some(c=>c.id===id))return;
    window.AtlasPurchases?.reset();
    window.AtlasAccounting?.reset();
    window.AtlasVat?.reset();
    this.companyId=id;sessionStorage.setItem('atlas-company',String(id));
    dialog.close();dialog.innerHTML='';cart=[];state=null;query='';filter='all';category='';
    document.querySelector('#print-area').innerHTML='';
    document.querySelector('#sidebar').classList.remove('open');document.querySelector('.mobile-backdrop')?.classList.remove('show');
    main.innerHTML='<div class="loading">Ouverture de la société…</div>';
    try {await refresh();}catch(error){main.innerHTML='<div class="empty">Impossible de charger cette société. Actualisez la page.</div>';toast(error.message,true);}
  },
  enhance() {
    if(!this.enabled || !state)return;
    const user=this.session.user;
    const selected=this.session.companies.find(c=>c.id===this.companyId);if(selected)selected.name=state.settings.name;
    const sw=document.querySelector('.workspace-switch');
    if(sw)sw.outerHTML=`<label class="company-switch"><span>SOCIÉTÉ ACTIVE</span><select id="platform-company-select" aria-label="Société active">${this.session.companies.map(c=>`<option value="${c.id}" ${c.id===this.companyId?'selected':''}>${esc(c.name)}</option>`).join('')}</select><small>${esc({admin:'Administrateur',commercial:'Commercial',accountant:'Comptable',supervisor:'Superviseur',viewer:'Lecture seule'}[state.role])}</small></label>`;
    document.querySelector('.sidebar-bottom').innerHTML=`<div class="local-card"><div>${icon('building')}${esc(this.session.organization.name)}</div><p>Chaque société conserve son propre catalogue, ses clients et son activité.</p></div><div class="profile"><span class="avatar">${esc(initials(user.name))}</span><div><strong>${esc(user.name)}</strong><small>${user.is_org_admin?'Administrateur organisation':'Compte personnel'}</small></div><button class="icon-btn" data-action="platform-logout" aria-label="Se déconnecter" title="Se déconnecter">${icon('arrow')}</button></div>`;
    const nav=document.querySelector('.nav');
    nav.querySelectorAll('[data-action^="platform-"]').forEach(el=>el.remove());
    if(user.is_org_admin)nav.insertAdjacentHTML('beforeend',`<button data-action="platform-companies">${icon('building')}Sociétés</button><button data-action="platform-users">${icon('users')}Utilisateurs & accès</button>`);
    if(this.can('audit'))nav.insertAdjacentHTML('beforeend',`<button data-action="platform-audit">${icon('clock')}Journal d’activité</button>`);
    nav.insertAdjacentHTML('beforeend',`<button data-action="platform-password">${icon('shield')}Mon mot de passe</button>`);
    const map={'new-product':'catalog','edit-product':'catalog','new-customer':'catalog','edit-customer':'catalog','import':'catalog',receive:'stock','new-sale':'sales','payment':'payments','cancel-sale':'cancel'};
    for(const [action,permission] of Object.entries(map)) if(!this.can(permission))document.querySelectorAll(`[data-action="${action}"]`).forEach(b=>b.hidden=true);
    document.querySelectorAll('a[href="/api/export/products"]').forEach(a=>{a.href=`/api/companies/${this.companyId}/export/products`;a.hidden=!this.can('export');});
    document.querySelectorAll('a[href="/api/backup"]').forEach(a=>{a.href=`/api/companies/${this.companyId}/backup`;a.innerHTML=`${icon('download')}Exporter cette société (JSON)`;a.hidden=!this.can('settings');});
    if(route==='settings'){
      const form=document.querySelector('#settings-form');
      if(form&&!form.querySelector('[name=fiscal_id]')){form.querySelector('.form-grid').insertAdjacentHTML('beforeend',`${field('Identifiant fiscal','fiscal_id',state.settings.fiscal_id||'','text',false)}${field('ICE','ice',state.settings.ice||'','text',false)}`);if(!this.can('settings'))form.querySelectorAll('input,textarea,button').forEach(el=>el.disabled=true);}
      const stack=document.querySelector('.settings-grid .stack');
      stack.innerHTML=`<section class="card"><div class="card-body"><div class="settings-badge">${icon('shield')}Les données de cette société uniquement</div><h2 style="margin-top:15px">Exportez votre dossier.</h2><p>Le fichier JSON contient les produits, clients, fournisseurs, ventes, achats, règlements, mouvements et données comptables de la société active. Il ne contient aucun compte utilisateur ni mot de passe.</p>${this.can('settings')?`<a class="btn primary" href="/api/companies/${this.companyId}/backup">${icon('download')}Exporter cette société (JSON)</a>`:'<div class="notice">Cet export est réservé à l’administrateur de la société.</div>'}<p class="stat-note">Cet export n’est pas une sauvegarde complète du serveur. Les sauvegardes PostgreSQL se gèrent séparément.</p></div></section><section class="card"><div class="card-body"><h2>Votre accès</h2><div class="settings-info" style="margin-top:20px"><div class="info-row"><span>Société</span><strong>${esc(state.settings.name)}</strong></div><div class="info-row"><span>Utilisateur</span><strong>${esc(user.name)}</strong></div><div class="info-row"><span>Devise</span><strong>MAD · Dirham marocain</strong></div></div>${state.settings.demo?'<div class="notice warning">Cette société contient des données de démonstration.</div>':''}</div></section>`;
    }
    document.querySelector('#connection').textContent='Espace partagé · Société isolée';
  },
  companyModal() {
    modal('Vos sociétés','Choisissez un dossier ou créez une nouvelle société.',`<div class="company-list">${this.session.companies.map(c=>`<button data-action="platform-switch" data-id="${c.id}">${icon('building')}<span><strong>${esc(c.name)}</strong><small>${c.id===this.companyId?'Société active':'Ouvrir ce dossier'}</small></span>${icon('arrow')}</button>`).join('')}</div>`,`${cancelButton}<button class="btn primary" data-action="platform-new-company">${icon('plus')}Nouvelle société</button>`);
  },
  newCompany() {
    modal('Une nouvelle société','Un catalogue, des clients et une activité séparés.',`<div class="form-grid">${field('Nom de la société','name','','text',true,true)}${field('Identifiant fiscal','fiscal_id','','text',false)}${field('ICE','ice','','text',false)}${field('Téléphone','phone','','tel',false,true)}<label class="field full"><span>Adresse</span><textarea name="address" maxlength="500"></textarea></label></div><div class="notice">Les utilisateurs n’auront accès à ce dossier que si vous le leur attribuez. L’administrateur de l’organisation accède à toutes ses sociétés.</div>`,`${cancelButton}<button type="submit" class="btn primary">Créer la société</button>`,false,'platform-company');
  },
  async usersModal() {
    const data=await this.request('users');this.userRows=data.users;
    modal('Utilisateurs & accès','Gérez les comptes et les accès par société.',`<div class="table-scroll"><table><thead><tr><th>Utilisateur</th><th>Accès</th><th>État</th><th></th></tr></thead><tbody>${data.users.map(u=>`<tr><td><strong>${esc(u.name||u.username)}</strong><br><small>${esc(u.username)}</small></td><td>${u.is_org_admin?'Toutes les sociétés':`${u.memberships.length} société(s)`}</td><td>${badge(u.active?'Actif':'Désactivé',u.active?'':'neutral')}</td><td>${u.is_org_admin?'':`<button class="btn small" data-action="platform-edit-user" data-id="${u.id}">Gérer les accès</button>`}</td></tr>`).join('')}</tbody></table></div>`,`${cancelButton}<button class="btn primary" data-action="platform-new-user">${icon('plus')}Nouvel utilisateur</button>`,true);
  },
  userModal(id) {
    const user=this.userRows.find(u=>u.id===id);
    modal(user?'Modifier les accès':'Un nouvel utilisateur','Attribuez un rôle pour chaque société accessible.',`<input type="hidden" name="id" value="${user?.id||''}"><div class="form-grid">${field('Nom','name',user?.name||'','text',false,true)}${user?'':`${field('Identifiant de connexion','username')}${field('Mot de passe initial','password','','password',true,false,'autocomplete="new-password" minlength="10"')}`}${user?`<label class="field full"><span>État du compte</span><select name="active"><option value="true" ${user.active?'selected':''}>Actif</option><option value="false" ${!user.active?'selected':''}>Désactivé</option></select></label>`:''}</div><h3 class="section-label">Accès aux sociétés</h3><div class="membership-list">${this.session.companies.map(c=>{const role=user?.memberships.find(m=>m.company_id===c.id)?.role||'';return `<label class="field"><span>${esc(c.name)}</span><select data-membership="${c.id}"><option value="">Aucun accès</option>${Object.entries({admin:'Administrateur société',commercial:'Commercial',accountant:'Comptable',supervisor:'Superviseur',viewer:'Lecture seule'}).map(([id,name])=>`<option value="${id}" ${role===id?'selected':''}>${name}</option>`).join('')}</select></label>`;}).join('')}</div><div class="notice">Lecture seule : consultation sans modification ni export. Comptable : comptabilité, règlements et exports. Commercial : opérations quotidiennes. Superviseur : opérations et annulations. Administrateur société : accès complet au dossier.</div>`,`${cancelButton}<button class="btn primary" type="submit">Enregistrer les accès</button>`,true,'platform-user');
  },
  passwordModal() {
    modal('Changer mon mot de passe','Les autres sessions de votre compte seront déconnectées.',`<div class="form-grid">${field('Mot de passe actuel','current_password','','password',true,true,'autocomplete="current-password"')}${field('Nouveau mot de passe','password','','password',true,true,'autocomplete="new-password" minlength="10"')}${field('Confirmer le nouveau mot de passe','confirm','','password',true,true,'autocomplete="new-password" minlength="10"')}</div>`,`${cancelButton}<button type="submit" class="btn primary">Changer le mot de passe</button>`,false,'platform-password');
  },
  async auditModal() {
    const data=await this.request(`companies/${this.companyId}/audit`);
    modal('Journal d’activité',`${state.settings.name} · 200 dernières actions`,data.events.length?`<div class="table-scroll"><table><thead><tr><th>Date</th><th>Utilisateur</th><th>Action</th><th>Détails</th></tr></thead><tbody>${data.events.map(e=>`<tr><td>${esc(new Date(e.created_at).toLocaleString('fr-FR'))}</td><td>${esc(e.actor__username||'Système')}</td><td>${esc(e.action)}</td><td><code>${esc(JSON.stringify(e.details))}</code></td></tr>`).join('')}</tbody></table></div>`:empty('Aucune action enregistrée','Les prochaines opérations apparaîtront ici.'),cancelButton,true);
  }
};

document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-action^="platform-"]');if(!button)return;
  event.stopImmediatePropagation();event.preventDefault();
  const p=window.AtlasPlatform,id=Number(button.dataset.id);
  try{
    switch(button.dataset.action){
      case 'platform-companies':p.companyModal();break;
      case 'platform-new-company':p.newCompany();break;
      case 'platform-switch':await p.switchCompany(id);break;
      case 'platform-users':await p.usersModal();break;
      case 'platform-new-user':p.userModal();break;
      case 'platform-edit-user':p.userModal(id);break;
      case 'platform-password':p.passwordModal();break;
      case 'platform-audit':await p.auditModal();break;
      case 'platform-logout':p.session=await p.request('auth/logout',{});sessionStorage.removeItem('atlas-company');p.showLogin();break;
    }
  }catch(error){toast(error.message,true);}
});
document.addEventListener('change',async event=>{
  if(event.target.id==='platform-company-select')await window.AtlasPlatform.switchCompany(Number(event.target.value));
});
document.addEventListener('submit',async event=>{
  const form=event.target, name=form.getAttribute('id');if(!name?.startsWith('platform-'))return;
  event.preventDefault();event.stopImmediatePropagation();
  const button=form.querySelector('[type=submit]');if(button.disabled)return;button.disabled=true;
  const errorBox=form.querySelector('.form-error');errorBox.textContent='';
  const p=window.AtlasPlatform,data=Object.fromEntries(new FormData(form));
  try{
    if(name==='platform-login'){
      p.session=await p.request('auth/login',data);
      document.body.classList.remove('auth-mode');
      if(!p.session.companies.length){p.showNoAccess();return;}
      await p.switchCompany(p.session.companies[0].id);return;
    }
    if(name==='platform-company'){
      const result=await p.request('companies',data);p.session.companies=result.companies;
      await p.switchCompany(result.id);toast('Société créée.');return;
    }
    if(name==='platform-user'){
      data.active=data.active!=='false';
      data.memberships=[...form.querySelectorAll('[data-membership]')].filter(el=>el.value).map(el=>({company_id:Number(el.dataset.membership),role:el.value}));
      await p.request('users',data);await p.usersModal();toast('Accès enregistrés.');return;
    }
    if(name==='platform-password'){
      if(data.password!==data.confirm)throw new Error('Les mots de passe ne correspondent pas.');
      const result=await p.request('auth/password',data);p.session.csrf_token=result.csrf_token;dialog.close();toast('Mot de passe modifié.');
    }
  }catch(error){errorBox.textContent=error.message;}
  finally{button.disabled=false;}
});
