/* Payment accounting and matching end-to-end checks. Uses a disposable local PostgreSQL database. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const {spawn,spawnSync}=require('node:child_process');
const {randomBytes}=require('node:crypto');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),python=path.join(root,'.venv/bin/python');
const db=`atlas_browser_${randomBytes(6).toString('hex')}`,base='http://localhost:8769',shots=path.join(root,'test-results');
(async()=>{
  let browser,server,page;
  try{
    const fixture=spawnSync(python,['tests/platform_fixture.py','create',db],{cwd:root,encoding:'utf8'});
    if(fixture.status!==0)throw new Error(fixture.stderr);
    const data=JSON.parse(fixture.stdout);
    server=spawn(python,['manage.py','runserver','127.0.0.1:8769','--noreload'],{cwd:root,env:{...process.env,DATABASE_URL:data.database_url},stdio:'ignore'});
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

    const pay1=await post('payments',{sale_id:sale.id,amount:'10',method:'Virement',request_key:'payment-one'});
    await post('supplier-payments',{purchase_id:purchase.id,amount:'18',method:'Virement',payment_date:'2026-02-02',reference:'BANK-SUPPLIER',request_key:'supplier-payment'});
    await page.reload();await page.getByRole('link',{name:'Comptabilité',exact:true}).click();
    await page.getByRole('button',{name:'Règlements & lettrage',exact:true}).click();
    const invoiceCard=page.locator(`[data-settlement-invoice="sale-${sale.id}"]`);
    async function transferPayment(card){
      await card.getByRole('button',{name:'Transférer le règlement',exact:true}).click();
      await page.getByLabel('Compte de banque ou caisse').selectOption(accounts.BANK);
      await page.getByRole('button',{name:'Créer le brouillon du règlement',exact:true}).click();
      await page.getByRole('heading',{name:/Écriture BR-/}).waitFor();
      assert.equal(await page.locator('dialog').getByRole('button',{name:'Modifier',exact:true}).count(),0);
      await postDialog();await close();
    }
    async function matchPayment(card){
      await card.getByRole('button',{name:'Lettrer',exact:true}).click();
      await page.getByRole('button',{name:'Confirmer le lettrage',exact:true}).click();
      await page.locator('dialog').waitFor({state:'hidden'});
    }
    await transferPayment(invoiceCard);await matchPayment(invoiceCard);
    await invoiceCard.getByText('Partiellement lettrée',{exact:true}).waitFor();
    let summary=(await accounting()).reconciliation.find(r=>r.kind==='sale');
    assert.equal(summary.matched,1000);assert.equal(summary.accounting_remaining,2000);assert.equal(summary.payment_gap,0);
    await page.screenshot({path:path.join(shots,'settlements-partial.png'),fullPage:true});
    await post('payments',{sale_id:sale.id,amount:'20',method:'Virement',request_key:'payment-two'});
    await page.reload();await page.getByRole('link',{name:'Comptabilité',exact:true}).click();await page.getByRole('button',{name:'Règlements & lettrage',exact:true}).click();
    await transferPayment(invoiceCard);await matchPayment(invoiceCard);
    await invoiceCard.getByText('Lettrée',{exact:true}).waitFor();
    const purchaseCard=page.locator(`[data-settlement-invoice="purchase-${purchase.id}"]`);
    await transferPayment(purchaseCard);await matchPayment(purchaseCard);await purchaseCard.getByText('Lettrée',{exact:true}).waitFor();
    summary=(await accounting()).reconciliation.find(r=>r.kind==='purchase');assert.equal(summary.matched,1800);assert.equal(summary.accounting_remaining,0);

    // Matched entries cannot be reversed; unmatch records a reason, then correction is possible.
    const firstPayment=invoiceCard.locator('[data-settlement-payment]').first();
    await firstPayment.getByRole('button',{name:/GEN-/}).click();
    await page.getByRole('button',{name:'Préparer une contrepassation'}).click();await page.getByLabel('Motif').fill('Compte de banque à corriger');
    await page.getByRole('button',{name:'Créer la contrepassation'}).click();
    await page.locator('dialog .form-error').filter({hasText:'Délettrez'}).waitFor();await close();
    await firstPayment.getByRole('button',{name:'Délettrer',exact:true}).click();await page.getByLabel('Motif').fill('Correction du compte de banque');
    await page.getByRole('button',{name:'Confirmer le délettrage'}).click();await page.locator('dialog').waitFor({state:'hidden'});
    await firstPayment.getByRole('button',{name:/GEN-/}).click();await page.getByRole('button',{name:'Préparer une contrepassation'}).click();await page.getByLabel('Motif').fill('Correction de banque');
    await page.getByRole('button',{name:'Créer la contrepassation'}).click();await page.getByRole('heading',{name:/Écriture BR-/}).waitFor();await postDialog();await close();
    await transferPayment(invoiceCard);await matchPayment(invoiceCard);await invoiceCard.getByText('Lettrée',{exact:true}).waitFor();
    const final=await accounting();assert.equal(final.matches.length,4);assert.equal(final.matches.filter(m=>!m.voided_at).length,3);
    assert.equal(final.reconciliation.find(r=>r.kind==='sale').posted_payments,3000);
    const csv=await page.request.get(base+await page.getByRole('link',{name:'Exporter le suivi'}).getAttribute('href'));
    assert.equal(csv.status(),200);assert.match(await csv.text(),/VT-0001/);
    await page.screenshot({path:path.join(shots,'settlements-desktop.png'),fullPage:true});
    await page.getByLabel('Société active',{exact:true}).selectOption(String(data.b));
    await page.getByRole('heading',{name:'Aucune écriture pour le moment'}).waitFor();
    await page.getByRole('button',{name:'Règlements & lettrage',exact:true}).click();await page.getByRole('heading',{name:'Aucune facture à rapprocher'}).waitFor();
    assert.doesNotMatch(await page.locator('main').innerText(),/VT-0001/);
    const viewer=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'}),mobile=await viewer.newPage();mobile.on('pageerror',e=>errors.push(e.message));
    await login(mobile,'browser-reader');await mobile.getByRole('button',{name:'Ouvrir le menu'}).click();await mobile.getByRole('link',{name:'Comptabilité',exact:true}).click();
    await mobile.getByRole('button',{name:'Règlements & lettrage',exact:true}).click();
    await mobile.getByText('VT-0001 · Client de passage',{exact:true}).waitFor();
    assert.equal(await mobile.getByRole('button',{name:'Délettrer',exact:true}).count(),0);
    assert.equal(await mobile.getByRole('link',{name:'Exporter le suivi'}).count(),0);
    assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await mobile.screenshot({path:path.join(shots,'settlements-mobile.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    console.log('PASS: customer/supplier payment transfer, reviewed posting, partial/full matching, reversal protection, audited unmatch, corrected replacement, CSV, company isolation and mobile read-only access.');
  }catch(error){if(page){console.error('Form errors:',await page.locator('.form-error').allTextContents());await page.screenshot({path:path.join(shots,'settlements-failure.png'),fullPage:true});}throw error;}
  finally{
    if(browser)await browser.close();if(server&&server.exitCode===null){const exited=new Promise(r=>server.once('exit',r));server.kill('SIGTERM');await exited;}
    const cleanup=spawnSync(python,['tests/platform_fixture.py','drop',db],{cwd:root,encoding:'utf8'});if(cleanup.status!==0)console.error(cleanup.stderr);
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
