/* Optional browser test: npm install --prefix /tmp/atlas-browser playwright
   PLAYWRIGHT_MODULE=/tmp/atlas-browser/node_modules/playwright node tests/browser.cjs */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

(async()=>{
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'atlas-browser-'));
  const root=path.resolve(__dirname,'..');
  const server=spawn('python3',['server.py','--port','8765','--db',path.join(temp,'test.sqlite3')],{cwd:root,stdio:['ignore','pipe','pipe']});
  let browser, page;
  try{
    await new Promise((resolve,reject)=>{server.stdout.once('data',resolve);server.once('error',reject);server.once('exit',code=>reject(new Error(`Server exited ${code}`)));setTimeout(()=>reject(new Error('Server timeout')),10000).unref();});
    browser=await chromium.launch({headless:true,...(process.env.ATLAS_CHROME?{executablePath:process.env.ATLAS_CHROME}:{}),args:['--no-sandbox']});
    page=await browser.newPage({viewport:{width:1440,height:1050},deviceScaleFactor:1,reducedMotion:'reduce'});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto('http://localhost:8765');
    await page.getByRole('heading',{name:'Chaque jour, une vue plus claire.'}).waitFor();
    fs.mkdirSync(path.join(root,'test-results'),{recursive:true});
    await page.screenshot({path:path.join(root,'test-results/dashboard-desktop.png'),fullPage:true});

    await page.getByRole('button',{name:'Ajouter un produit',exact:true}).click();
    await page.getByLabel('Nom du produit').fill('Produit navigateur');
    await page.getByLabel('Référence', {exact:false}).fill('BROWSER-001');
    await page.getByLabel('Catégorie',{exact:false}).fill('Tests');
    await page.getByLabel('Prix d’achat').fill('8.00');
    await page.getByLabel('Prix de vente').fill('12.50');
    await page.getByLabel('Stock initial').fill('10');
    await page.getByLabel('Seuil d’alerte').fill('3');
    await page.getByRole('button',{name:'Créer le produit',exact:true}).click();
    await page.locator('dialog').waitFor({state:'hidden'});
    await page.getByRole('link',{name:/Produits & stock/}).click();
    await page.getByLabel('Nom ou référence…').fill('BROWSER-001');
    await page.getByRole('button',{name:'Mouvement de stock pour Produit navigateur'}).click();
    await page.getByLabel('Quantité').fill('5');
    await page.getByLabel('Motif').fill('Réception de test');
    await page.getByRole('button',{name:'Enregistrer le mouvement'}).click();
    await page.locator('dialog').waitFor({state:'hidden'});
    assert.match(await page.locator('main tbody').innerText(),/15/);

    await page.getByRole('link',{name:'Clients',exact:true}).click();
    await page.getByRole('button',{name:'Nouveau client',exact:true}).click();
    await page.getByLabel('Nom ou raison sociale').fill('Client navigateur <test>');
    await page.getByLabel('Téléphone',{exact:true}).fill('0600000000');
    await page.getByLabel('Ville',{exact:true}).fill('Casablanca');
    await page.getByRole('button',{name:'Enregistrer le client'}).click();
    await page.locator('dialog').waitFor({state:'hidden'});

    await page.getByRole('link',{name:'Ventes',exact:true}).click();
    await page.getByRole('button',{name:'Nouvelle vente',exact:true}).click();
    await page.locator('[name=customer_id]').selectOption({label:'Client navigateur <test>'});
    await page.getByLabel('Produit à ajouter').selectOption({label:'Produit navigateur · 12,50 DH'});
    await page.getByRole('button',{name:'Ajouter le produit',exact:true}).click();
    await page.getByLabel('Quantité Produit navigateur').fill('3');
    await page.getByLabel('Taxe · taux').fill('20');
    await page.getByLabel('Montant encaissé').fill('15');
    assert.equal(await page.locator('#sale-total').textContent(),'45,00 DH');
    await page.getByRole('button',{name:'Valider la vente'}).click();
    await page.getByRole('heading',{name:'Vente VT-0011',exact:true}).waitFor();
    assert.match(await page.locator('dialog').innerText(),/Client navigateur <test>/);
    assert.match(await page.locator('dialog').innerText(),/Partielle/);
    await page.screenshot({path:path.join(root,'test-results/sale-desktop.png'),fullPage:true});
    await page.getByRole('button',{name:'Ajouter un règlement'}).click();
    await page.getByRole('button',{name:'Enregistrer le règlement'}).click();
    await page.getByRole('heading',{name:'Vente VT-0011',exact:true}).waitFor();
    assert.match(await page.locator('dialog').innerText(),/Payée/);
    await page.evaluate(()=>{window.print=()=>{window.__printed=true;};});
    await page.getByRole('button',{name:'Imprimer',exact:true}).click();
    assert.equal(await page.evaluate(()=>window.__printed),true);
    assert.match(await page.locator('#print-area').textContent(),/45,00 DH/);
    await page.getByRole('button',{name:'Fermer',exact:true}).last().click();

    await page.getByRole('button',{name:'Nouvelle vente',exact:true}).click();
    await page.getByLabel('Produit à ajouter').selectOption({label:'Produit navigateur · 12,50 DH'});
    await page.getByRole('button',{name:'Ajouter le produit',exact:true}).click();
    await page.getByRole('button',{name:'Valider la vente'}).click();
    await page.getByRole('button',{name:'Annuler cette vente et remettre les produits en stock'}).click();
    await page.getByRole('button',{name:'Annuler la vente',exact:true}).click();
    await page.getByRole('heading',{name:'Vente VT-0012',exact:true}).waitFor();
    assert.match(await page.locator('dialog').innerText(),/Annulée/);
    await page.getByRole('button',{name:'Fermer',exact:true}).last().click();

    await page.getByRole('link',{name:/Produits & stock/}).click();
    await page.getByLabel('Nom ou référence…').fill('BROWSER-001');
    assert.match(await page.locator('main tbody').innerText(),/12/);
    await page.reload();
    await page.getByLabel('Nom ou référence…').fill('BROWSER-001');
    assert.match(await page.locator('main tbody').innerText(),/Produit navigateur/);
    const downloadPromise=page.waitForEvent('download');
    await page.getByRole('link',{name:'Exporter',exact:true}).click();
    const download=await downloadPromise;assert.equal(download.suggestedFilename(),'atlas-produits.csv');
    await page.getByRole('button',{name:'Importer',exact:true}).click();
    await page.locator('#csv-file').setInputFiles({name:'products.csv',mimeType:'text/csv',buffer:Buffer.from('sku,name,category,cost,price,stock,minimum\nCSV-TEST,Produit importé,Tests,2,5,20,3\n')});
    await page.getByRole('button',{name:'Importer les produits'}).click();
    await page.locator('dialog').waitFor({state:'hidden'});
    await page.getByLabel('Nom ou référence…').fill('CSV-TEST');
    assert.match(await page.locator('main tbody').innerText(),/Produit importé/);

    await page.getByRole('link',{name:'Paramètres',exact:true}).first().click();
    await page.getByLabel('Nom de l’entreprise').fill('Atlas test entreprise');
    await page.getByRole('button',{name:'Enregistrer',exact:true}).click();
    await page.getByRole('link',{name:/Atlas test entreprise Espace de travail local/}).waitFor();
    const backupPromise=page.waitForEvent('download');
    await page.getByRole('link',{name:'Télécharger la sauvegarde'}).click();
    const backup=await backupPromise;assert.match(backup.suggestedFilename(),/\.sqlite3$/);

    await page.setViewportSize({width:390,height:844});
    await page.getByRole('button',{name:'Ouvrir le menu'}).click();
    await page.getByRole('link',{name:'Vue d’ensemble',exact:true}).click();
    await page.getByRole('heading',{name:'Chaque jour, une vue plus claire.'}).waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.screenshot({path:path.join(root,'test-results/dashboard-mobile.png'),fullPage:true});
    await page.getByRole('button',{name:'Nouvelle vente',exact:true}).click();
    assert.equal(await page.locator('dialog').evaluate(el=>el.scrollWidth<=el.clientWidth),true);
    await page.screenshot({path:path.join(root,'test-results/sale-mobile.png'),fullPage:true});
    await page.keyboard.press('Escape');
    await page.getByRole('button',{name:'Ouvrir le menu'}).click();
    await page.getByRole('link',{name:/Produits & stock/}).click();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.screenshot({path:path.join(root,'test-results/products-mobile.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    console.log('PASS: dashboard, product creation, stock receipt, customer creation, sale/tax, partial/full payment, print document, cancellation/restock, persistence, CSV import/export, settings, backup, mobile navigation/layout. No JavaScript errors.');
  }catch(error){
    if(page){console.error("Form error:",await page.locator(".form-error").allTextContents());console.error("Invalid inputs:",await page.locator(":invalid").evaluateAll(nodes=>nodes.map(n=>({name:n.name,message:n.validationMessage}))));await page.screenshot({path:path.join(root,"test-results/failure.png"),fullPage:true});}
    throw error;
  }finally{
    if(browser) await browser.close();
    server.kill('SIGTERM');
    await new Promise(resolve=>server.once('exit',resolve));
    fs.rmSync(temp,{recursive:true,force:true});
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
