/* VAT preparation end-to-end checks. Uses a disposable local PostgreSQL database. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const {spawn,spawnSync}=require('node:child_process');
const {randomBytes}=require('node:crypto');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),python=path.join(root,'.venv/bin/python');
const db=`atlas_browser_${randomBytes(6).toString('hex')}`,base='http://localhost:8770',shots=path.join(root,'test-results');
(async()=>{
  let browser,server,page;
  try{
    const fixture=spawnSync(python,['tests/platform_fixture.py','create',db],{cwd:root,encoding:'utf8'});
    if(fixture.status!==0)throw new Error(fixture.stderr);
    const data=JSON.parse(fixture.stdout);
    server=spawn(python,['manage.py','runserver','127.0.0.1:8770','--noreload'],{cwd:root,env:{...process.env,DATABASE_URL:data.database_url},stdio:'ignore'});
    let ready=false;for(let i=0;i<100;i++){try{if((await fetch(base+'/api/auth/me')).ok){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,100));}assert(ready);
    browser=await chromium.launch({headless:true,...(process.env.ATLAS_CHROME?{executablePath:process.env.ATLAS_CHROME}:{}),args:['--no-sandbox']});
    const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
    page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));fs.mkdirSync(shots,{recursive:true});
    async function login(target,user){await target.goto(base);await target.getByLabel('Identifiant',{exact:true}).fill(user);await target.getByLabel('Mot de passe',{exact:true}).fill('Browser-Atlas-Password-729!');await target.getByRole('button',{name:'Se connecter',exact:true}).click();await target.getByRole('heading',{name:'Chaque jour, une vue plus claire.'}).waitFor();}
    await login(page,'browser-owner');
    const identity=await (await page.request.get(base+'/api/auth/me')).json();
    async function post(action,payload){const response=await page.request.post(`${base}/api/companies/${data.a}/${action}`,{data:payload,headers:{'X-CSRFToken':identity.csrf_token}});assert.equal(response.status(),200,await response.text());return response.json();}
    async function accounting(){return (await page.request.get(`${base}/api/companies/${data.a}/accounting/state`)).json();}
    const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Africa/Casablanca'}).format(new Date()),start=today.slice(0,7)+'-01';
    const sale=await post('sales',{request_key:'vat-sale',items:[{product_id:data.product,quantity:2}],tax_bps:2000});
    await post('payments',{request_key:'vat-sale-pay',sale_id:sale.id,amount:'15',method:'Virement'});
    const supplier=await post('suppliers',{name:'Fournisseur TVA'});
    const purchase=await post('purchases',{request_key:'vat-purchase',supplier_id:supplier.id,supplier_reference:'VAT-ACHAT',invoice_date:start,items:[{product_id:data.product,quantity:1,price:'10',tax_bps:2000}]});
    await post('purchase-receive',{request_key:'vat-receive',purchase_id:purchase.id,version:1});
    await post('supplier-payments',{request_key:'vat-purchase-pay',purchase_id:purchase.id,amount:'6',payment_date:today,method:'Virement'});
    async function vat(){return (await page.request.get(`${base}/api/companies/${data.a}/vat/state`)).json();}
    await page.reload();await page.getByRole('link',{name:'TVA',exact:true}).click();
    await page.getByRole('button',{name:'Nouvelle préparation',exact:true}).click();
    await page.getByLabel('Premier jour de la période').fill(start);
    await page.getByLabel('Périodicité',{exact:true}).selectOption('monthly');
    await page.getByLabel('Base d’import des ventes').selectOption('payments');await page.getByLabel('Base d’import des achats').selectOption('payments');
    await page.getByRole('button',{name:'Créer la préparation',exact:true}).click();await page.locator('dialog').waitFor({state:'hidden'});
    await page.getByRole('button',{name:'Importer / actualiser',exact:true}).waitFor();
    const close=async()=>page.getByRole('button',{name:'Fermer',exact:true}).last().click();
    async function approve(){
      await page.getByRole('button',{name:'Approuver la préparation',exact:true}).click();
      await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Confirmer l’approbation',exact:true}).click();
    }
    await approve();await page.locator('dialog .form-error').filter({hasText:'sources'}).waitFor();await close();
    await page.getByRole('button',{name:'Importer / actualiser',exact:true}).click();
    await page.locator('[data-vat-key]').first().waitFor();
    assert.equal(await page.locator('[data-vat-key]').count(),2);
    await page.getByRole('button',{name:'Importer / actualiser',exact:true}).click();
    await page.getByText('0 sources ajoutées · 0 actualisées.',{exact:true}).waitFor();assert.equal(await page.locator('[data-vat-key]').count(),2);
    async function review(reference,amount){
      await page.locator('[data-vat-key]').filter({hasText:reference}).getByRole('button',{name:'Vérifier',exact:true}).click();
      await page.getByLabel('TVA retenue pour cette période').fill(amount);
      await page.getByLabel('Justification du traitement').fill('Périmètre et traitement vérifiés par le comptable');
      await page.getByRole('button',{name:'Enregistrer la revue',exact:true}).click();await page.locator('dialog').waitFor({state:'hidden'});
    }
    await review('VT-0001','2.50');await review('VAT-ACHAT','1');
    await page.getByRole('button',{name:'Ajouter une ligne',exact:true}).click();
    await page.getByLabel('Nature',{exact:true}).selectOption('purchase');
    await page.getByLabel('Référence du document').fill('TVA-MANUELLE');await page.getByLabel('Tiers').fill('Frais externes');
    await page.getByLabel('Montant HT').fill('5');await page.getByLabel('TVA du document').fill('1');
    await page.getByLabel('TVA retenue pour cette période').fill('0.50');await page.getByLabel('Justification du traitement').fill('Déduction partielle validée');
    await page.getByRole('button',{name:'Enregistrer la revue',exact:true}).click();await page.locator('dialog').waitFor({state:'hidden'});
    await page.getByRole('button',{name:'Crédit & notes',exact:true}).click();
    await page.getByLabel('Crédit antérieur à reprendre').fill('0.50');await page.getByLabel('Origine et validation du crédit').fill('Crédit antérieur vérifié');
    await page.getByLabel('Note de préparation').fill('Périmètre mensuel examiné');await page.getByRole('button',{name:'Enregistrer les notes',exact:true}).click();await page.locator('dialog').waitFor({state:'hidden'});
    const before=(await vat()).worksheets[0];assert.equal(before.totals.payable,50);assert.equal(before.totals.pending,0);
    await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(shots,'vat-review.png'),fullPage:true});
    await approve();await page.locator('dialog').waitFor({state:'hidden'});await page.getByRole('link',{name:'Exporter CSV',exact:true}).waitFor();
    assert.equal(await page.getByRole('button',{name:'Importer / actualiser',exact:true}).count(),0);
    const approved=(await vat()).worksheets[0];assert.equal(approved.status,'approved');assert.equal(approved.checksum.length,64);
    const csv=await page.request.get(base+await page.getByRole('link',{name:'Exporter CSV',exact:true}).getAttribute('href'));
    assert.equal(csv.status(),200);assert.match(await csv.text(),/TVA-MANUELLE/);
    const snapshot=await page.request.get(base+await page.getByRole('link',{name:'Télécharger l’instantané',exact:true}).getAttribute('href'));
    assert.equal((await snapshot.json()).snapshot.totals.payable,50);
    await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(shots,'vat-approved.png'),fullPage:true});
    await page.getByLabel('Société active',{exact:true}).selectOption(String(data.b));
    await page.getByRole('heading',{name:'Aucune préparation TVA',exact:true}).waitFor();
    assert.doesNotMatch(await page.locator('main').innerText(),/TVA-MANUELLE/);
    await page.getByLabel('Société active',{exact:true}).selectOption(String(data.a));
    await page.getByRole('button',{name:'Ouvrir',exact:true}).click();await page.getByRole('button',{name:'Annuler l’approbation',exact:true}).click();
    await page.getByLabel('Motif').fill('Revue complémentaire');await page.getByRole('button',{name:'Confirmer l’annulation',exact:true}).click();await page.locator('dialog').waitFor({state:'hidden'});
    assert.equal(await page.getByRole('link',{name:'Exporter CSV',exact:true}).count(),0);
    assert.equal((await vat()).worksheets[0].status,'voided');
    const viewer=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'}),mobile=await viewer.newPage();mobile.on('pageerror',e=>errors.push(e.message));
    await login(mobile,'browser-reader');await mobile.getByRole('button',{name:'Ouvrir le menu'}).click();await mobile.getByRole('link',{name:'TVA',exact:true}).click();
    assert.equal(await mobile.getByRole('button',{name:'Nouvelle préparation',exact:true}).count(),0);
    await mobile.getByRole('button',{name:'Ouvrir',exact:true}).click();await mobile.getByText('Approbation annulée',{exact:true}).waitFor();
    assert.equal(await mobile.getByRole('button',{name:'Vérifier',exact:true}).count(),0);
    assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await mobile.screenshot({path:path.join(shots,'vat-mobile.png'),fullPage:true});assert.deepEqual(errors,[]);
    console.log('PASS: VAT monthly preparation, missing-source approval rejection, partial-payment import/deduplication, line review, manual deduction, prior credit, immutable approval, CSV/JSON, voiding, company isolation and mobile read-only access.');
  }catch(error){if(page){console.error('Form errors:',await page.locator('.form-error').allTextContents());await page.screenshot({path:path.join(shots,'vat-failure.png'),fullPage:true});}throw error;}
  finally{
    if(browser)await browser.close();if(server&&server.exitCode===null){const exited=new Promise(r=>server.once('exit',r));server.kill('SIGTERM');await exited;}
    const cleanup=spawnSync(python,['tests/platform_fixture.py','drop',db],{cwd:root,encoding:'utf8'});if(cleanup.status!==0)console.error(cleanup.stderr);
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
