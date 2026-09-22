/* Accounting end-to-end checks. Uses a disposable local PostgreSQL database. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const {spawn,spawnSync}=require('node:child_process');
const {randomBytes}=require('node:crypto');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),python=path.join(root,'.venv/bin/python');
const db=`atlas_browser_${randomBytes(6).toString('hex')}`,base='http://localhost:8768',shots=path.join(root,'test-results');
(async()=>{
  let browser,server,page;
  try{
    const fixture=spawnSync(python,['tests/platform_fixture.py','create',db],{cwd:root,encoding:'utf8'});
    if(fixture.status!==0)throw new Error(fixture.stderr);
    const data=JSON.parse(fixture.stdout);
    server=spawn(python,['manage.py','runserver','127.0.0.1:8768','--noreload'],{cwd:root,env:{...process.env,DATABASE_URL:data.database_url},stdio:'ignore'});
    let ready=false;for(let i=0;i<100;i++){try{if((await fetch(base+'/api/auth/me')).ok){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,100));}assert(ready);
    browser=await chromium.launch({headless:true,...(process.env.ATLAS_CHROME?{executablePath:process.env.ATLAS_CHROME}:{}),args:['--no-sandbox']});
    const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
    page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));fs.mkdirSync(shots,{recursive:true});
    async function login(target,user){await target.goto(base);await target.getByLabel('Identifiant',{exact:true}).fill(user);await target.getByLabel('Mot de passe',{exact:true}).fill('Browser-Atlas-Password-729!');await target.getByRole('button',{name:'Se connecter',exact:true}).click();await target.getByRole('heading',{name:'Chaque jour, une vue plus claire.'}).waitFor();}
    await login(page,'browser-owner');
    const identity=await (await page.request.get(base+'/api/auth/me')).json();
    async function post(action,payload){const response=await page.request.post(`${base}/api/companies/${data.a}/${action}`,{data:payload,headers:{'X-CSRFToken':identity.csrf_token}});assert.equal(response.status(),200,await response.text());return response.json();}
    async function accounting(){return (await page.request.get(`${base}/api/companies/${data.a}/accounting/state`)).json();}
    const sale=await post('sales',{request_key:'accounting-browser-sale',items:[{product_id:data.product,quantity:2}],tax_bps:2000});
    const supplier=await post('suppliers',{name:'Fournisseur comptabilité'});
    const purchase=await post('purchases',{request_key:'accounting-browser-purchase',supplier_id:supplier.id,supplier_reference:'FA-COMPTA',invoice_date:'2026-02-01',items:[{product_id:data.product,quantity:3,price:'5',tax_bps:2000}]});
    await post('purchase-receive',{request_key:'accounting-browser-receive',purchase_id:purchase.id,version:1});
    await page.reload();await page.getByRole('link',{name:'Comptabilité',exact:true}).click();
    await page.getByRole('button',{name:'Paramétrage',exact:true}).click();
    for(const [code,name] of [['AR','Clients'],['REV','Produits'],['TAX','Taxe à affecter'],['AP','Fournisseurs'],['EXP','Charges'],['BANK','Banque']]){
      await page.locator('[data-action="accounting-new-account"]').click();
      await page.locator('dialog').getByLabel('Code').fill(code);
      await page.locator('dialog').getByLabel('Libellé').fill(name);
      await page.getByRole('button',{name:'Enregistrer le compte',exact:true}).click();
      await page.locator('dialog').waitFor({state:'hidden'});
      await page.locator('main td').getByText(code,{exact:true}).waitFor();
    }
    await page.locator('[data-action="accounting-new-journal"]').click();
    await page.locator('dialog').getByLabel('Code').fill('GEN');
    await page.locator('dialog').getByLabel('Libellé').fill('Journal général');
    await page.getByRole('button',{name:'Enregistrer le journal',exact:true}).click();await page.locator('dialog').waitFor({state:'hidden'});
    await page.getByRole('button',{name:'Nouvelle période',exact:true}).click();
    await page.getByLabel('Nom de la période').fill('Exercice test 2026');
    await page.getByLabel('Début de période').fill('2026-01-01');await page.getByLabel('Fin de période').fill('2026-12-31');
    await page.getByRole('button',{name:'Créer la période',exact:true}).click();await page.locator('dialog').waitFor({state:'hidden'});
    await page.getByText('Exercice test 2026',{exact:true}).waitFor();
    await page.screenshot({path:path.join(shots,'accounting-setup.png'),fullPage:true});
    const book=await accounting(),accounts=Object.fromEntries(book.accounts.map(a=>[a.code,String(a.id)]));
    const close=async()=>{await page.getByRole('button',{name:'Fermer',exact:true}).last().click();};
    async function postDialog(){await page.getByRole('button',{name:'Comptabiliser',exact:true}).click();await page.getByRole('button',{name:'Confirmer la comptabilisation',exact:true}).click();await page.getByRole('heading',{name:/Écriture GEN-/}).waitFor();}
    await page.getByRole('button',{name:'Transfert des factures',exact:true}).click();
    await page.locator('tr').filter({hasText:'VT-0001'}).getByRole('button',{name:'Préparer le transfert'}).click();
    await page.getByLabel('Compte client / tiers').selectOption(accounts.AR);
    await page.getByLabel('Compte de produits HT').selectOption(accounts.REV);
    await page.getByLabel('Compte de taxe selon').selectOption(accounts.TAX);
    await page.getByRole('button',{name:'Créer le brouillon de transfert'}).click();
    await page.getByRole('heading',{name:/Écriture BR-/}).waitFor();
    assert.match(await page.locator('dialog').innerText(),/30,00 DH/);
    await page.screenshot({path:path.join(shots,'accounting-transfer.png'),fullPage:true});
    await postDialog();await close();
    assert.equal((await accounting()).entries.filter(e=>e.sale_id===sale.id).length,1);
    await page.locator('tr').filter({hasText:'AC-0001'}).getByRole('button',{name:'Préparer le transfert'}).click();
    await page.getByLabel('Compte fournisseur / tiers').selectOption(accounts.AP);
    await page.getByLabel('Compte de charges HT').selectOption(accounts.EXP);
    await page.getByLabel('Compte de taxe selon').selectOption(accounts.TAX);
    await page.getByRole('button',{name:'Créer le brouillon de transfert'}).click();
    await page.getByRole('heading',{name:/Écriture BR-/}).waitFor();await postDialog();await close();

    // Manual draft can be saved unbalanced; posting rejects it until corrected.
    await page.getByRole('button',{name:'Nouvelle écriture',exact:true}).click();
    await page.getByLabel('Libellé de l’écriture').fill('Règlement client manuel');
    await page.getByLabel('Compte 1',{exact:true}).selectOption(accounts.BANK);await page.getByLabel('Compte 2',{exact:true}).selectOption(accounts.AR);
    await page.getByLabel('Débit ligne 1').fill('10');await page.getByLabel('Crédit ligne 2').fill('9');
    await page.getByRole('button',{name:'Enregistrer le brouillon comptable'}).click();await page.getByRole('heading',{name:/Écriture BR-/}).waitFor();
    await page.getByRole('button',{name:'Comptabiliser',exact:true}).click();await page.getByRole('button',{name:'Confirmer la comptabilisation'}).click();
    await page.locator('dialog .form-error').filter({hasText:'équilibrée'}).waitFor();await close();
    await page.getByRole('button',{name:'Écritures',exact:true}).click();
    await page.locator('tr').filter({hasText:'Règlement client manuel'}).getByRole('button',{name:/BR-/}).click();
    await page.getByRole('button',{name:'Modifier',exact:true}).click();await page.getByLabel('Crédit ligne 2').fill('10');
    await page.getByRole('button',{name:'Enregistrer le brouillon comptable'}).click();await page.getByRole('heading',{name:/Écriture BR-/}).waitFor();await postDialog();await close();

    await page.getByRole('button',{name:'Rapports',exact:true}).click();await page.getByRole('button',{name:'Afficher le rapport'}).click();
    await page.getByRole('button',{name:'Balance',exact:true}).waitFor();
    assert.match(await page.locator('.accounting-reconciliation').innerText(),/58,00 DH/);
    assert.match(await page.locator('.accounting-reconciliation').innerText(),/Écart\s+0,00 DH/);
    await page.screenshot({path:path.join(shots,'accounting-balance.png'),fullPage:true});
    const download=await page.request.get(await page.getByRole('link',{name:'Exporter le rapport'}).getAttribute('href').then(p=>base+p));
    assert.equal(download.status(),200);assert.match(await download.text(),/AR/);
    await page.getByRole('button',{name:'Grand livre',exact:true}).click();await page.getByLabel('Compte du grand livre').selectOption(accounts.AR);
    assert.match(await page.locator('main').innerText(),/20,00 DH/);
    await page.getByRole('button',{name:'Journal général',exact:true}).click();
    await page.getByRole('button',{name:'GEN-000001',exact:true}).first().click();
    await page.getByRole('button',{name:'Préparer une contrepassation'}).click();await page.getByLabel('Motif').fill('Annulation de la vente test');
    await page.getByRole('button',{name:'Créer la contrepassation'}).click();await page.getByRole('heading',{name:/Écriture BR-/}).waitFor();await postDialog();await close();
    await page.getByRole('button',{name:'Paramétrage',exact:true}).click();await page.getByRole('button',{name:'Fermer la période'}).click();
    await page.getByLabel('Motif').fill('Révision terminée');await page.getByRole('button',{name:'Confirmer la fermeture'}).click();await page.locator('dialog').waitFor({state:'hidden'});
    await page.getByRole('button',{name:'Rouvrir',exact:true}).waitFor();
    const final=await accounting();assert.equal(final.entries.filter(e=>e.status==='posted').length,4);assert.equal(final.periods[0].closed,true);
    await page.getByLabel('Société active',{exact:true}).selectOption(String(data.b));
    await page.getByRole('heading',{name:'Aucune écriture pour le moment'}).waitFor();
    await page.getByRole('button',{name:'Paramétrage',exact:true}).click();
    await page.getByText('Aucun compte',{exact:true}).waitFor();assert.doesNotMatch(await page.locator('main').innerText(),/Exercice test 2026/);

    const viewer=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'}),mobile=await viewer.newPage();mobile.on('pageerror',e=>errors.push(e.message));
    await login(mobile,'browser-reader');await mobile.getByRole('button',{name:'Ouvrir le menu'}).click();await mobile.getByRole('link',{name:'Comptabilité',exact:true}).click();
    assert.equal(await mobile.getByRole('button',{name:'Nouvelle écriture',exact:true}).count(),0);
    await mobile.getByRole('button',{name:'Rapports',exact:true}).click();await mobile.getByRole('button',{name:'Afficher le rapport'}).click();await mobile.getByRole('button',{name:'Balance',exact:true}).waitFor();
    assert.equal(await mobile.getByRole('link',{name:'Exporter le rapport'}).count(),0);
    assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await mobile.screenshot({path:path.join(shots,'accounting-mobile.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    console.log('PASS: company accounting setup, sale/purchase transfer, balanced posting, rejected unbalanced draft and correction, journal/ledger/trial balance, CSV, reversal, period closing, company isolation and mobile read-only access.');
  }catch(error){if(page){console.error('Form errors:',await page.locator('.form-error').allTextContents());await page.screenshot({path:path.join(shots,'accounting-failure.png'),fullPage:true});}throw error;}
  finally{
    if(browser)await browser.close();if(server&&server.exitCode===null){const exited=new Promise(r=>server.once('exit',r));server.kill('SIGTERM');await exited;}
    const cleanup=spawnSync(python,['tests/platform_fixture.py','drop',db],{cwd:root,encoding:'utf8'});if(cleanup.status!==0)console.error(cleanup.stderr);
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
