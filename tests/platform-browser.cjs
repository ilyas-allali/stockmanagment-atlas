/* PLAYWRIGHT_MODULE=/tmp/atlascom-browser/node_modules/playwright node tests/platform-browser.cjs
   PostgreSQL from compose.yaml must be running. All business data here is temporary. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const {spawn,spawnSync}=require('node:child_process');
const {randomBytes}=require('node:crypto');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'), python=path.join(root,'.venv/bin/python');
const db=`atlas_browser_${randomBytes(6).toString('hex')}`;
const password='Browser-Atlas-Password-729!';
const screenshots=path.join(root,'test-results');

(async()=>{
  let browser, server, page;
  try{
    const fixture=spawnSync(python,['tests/platform_fixture.py','create',db],{cwd:root,encoding:'utf8'});
    if(fixture.status!==0)throw new Error(fixture.stderr);
    const data=JSON.parse(fixture.stdout);
    server=spawn(python,['manage.py','runserver','127.0.0.1:8766','--noreload'],{cwd:root,env:{...process.env,DATABASE_URL:data.database_url},stdio:'ignore'});
    let ready=false;
    for(let i=0;i<100;i++){try{const response=await fetch('http://localhost:8766/api/auth/me');if(response.ok){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,100));}
    assert(ready,'Django server started');
    browser=await chromium.launch({headless:true,...(process.env.ATLAS_CHROME?{executablePath:process.env.ATLAS_CHROME}:{}),args:['--no-sandbox']});
    const owner=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
    page=await owner.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
    fs.mkdirSync(screenshots,{recursive:true});
    await page.goto('http://localhost:8766');
    await page.getByRole('button',{name:'Se connecter'}).waitFor();
    await page.screenshot({path:path.join(screenshots,'platform-login.png'),fullPage:true});
    await page.getByLabel('Identifiant',{exact:true}).fill('browser-owner');
    await page.getByLabel('Mot de passe',{exact:true}).fill(password);
    await page.getByRole('button',{name:'Se connecter'}).click();
    await page.getByRole('heading',{name:'Chaque jour, une vue plus claire.'}).waitFor();
    await page.getByRole('link',{name:/Produits & stock/}).click();
    assert.match(await page.locator('main').innerText(),/Produit Casablanca/);
    assert.doesNotMatch(await page.locator('main').innerText(),/Produit Rabat/);
    await page.getByLabel('Société active',{exact:true}).selectOption(String(data.b));
    await page.getByText('Produit Rabat',{exact:true}).waitFor();
    assert.doesNotMatch(await page.locator('main').innerText(),/Produit Casablanca/);
    await page.getByLabel('Société active',{exact:true}).selectOption(String(data.a));
    await page.getByText('Produit Casablanca',{exact:true}).waitFor();

    // Same browser session, independent per-tab selected companies.
    const second=await owner.newPage();await second.goto('http://localhost:8766/#products');
    await second.getByLabel('Société active',{exact:true}).selectOption(String(data.b));
    await second.getByText('Produit Rabat',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Nouveau produit',exact:true}).click();
    await page.getByLabel('Nom du produit').fill('Produit créé en société A');
    await page.locator('dialog').getByLabel('Référence').fill('CASA-NEW');
    await page.getByLabel('Prix de vente').fill('20');
    await page.getByLabel('Stock initial').fill('10');
    await page.getByRole('button',{name:'Créer le produit',exact:true}).click();
    await page.locator('dialog').waitFor({state:'hidden'});
    await page.getByText('Produit créé en société A',{exact:true}).waitFor();
    await second.reload();await second.getByText('Produit Rabat',{exact:true}).waitFor();
    assert.doesNotMatch(await second.locator('main').innerText(),/Produit créé en société A/);

    await page.getByRole('link',{name:'Ventes',exact:true}).click();
    await page.getByRole('button',{name:'Nouvelle vente',exact:true}).click();
    await page.getByLabel('Produit à ajouter').selectOption(String(data.product));
    await page.getByRole('button',{name:'Ajouter le produit',exact:true}).click();
    await page.getByLabel('Quantité Produit Casablanca').fill('3');
    await page.getByLabel('Taxe · taux').fill('20');
    await page.getByLabel('Montant encaissé').fill('15');
    await page.getByRole('button',{name:'Valider la vente'}).click();
    await page.getByRole('heading',{name:'Vente VT-0001',exact:true}).waitFor();
    assert.match(await page.locator('dialog').innerText(),/45,00 DH/);
    await page.getByRole('button',{name:'Ajouter un règlement'}).click();
    await page.getByRole('button',{name:'Enregistrer le règlement'}).click();
    await page.getByRole('heading',{name:'Vente VT-0001',exact:true}).waitFor();
    assert.match(await page.locator('dialog').innerText(),/Payée/);
    await page.getByRole('button',{name:'Fermer',exact:true}).last().click();

    await page.getByRole('button',{name:'Sociétés',exact:true}).click();
    await page.getByRole('button',{name:'Nouvelle société',exact:true}).click();
    await page.getByLabel('Nom de la société').fill('Atlas Tanger');
    await page.getByRole('button',{name:'Créer la société'}).click();
    await page.locator('dialog').waitFor({state:'hidden'});
    await page.waitForFunction(()=>document.querySelector('#platform-company-select')?.selectedOptions[0]?.textContent==='Atlas Tanger');
    await page.getByRole('link',{name:/Produits & stock/}).click();
    await page.getByRole('heading',{name:'Aucun produit ici'}).waitFor();

    await page.getByRole('button',{name:'Utilisateurs & accès'}).click();
    await page.getByRole('button',{name:'Nouvel utilisateur'}).click();
    await page.locator('dialog').getByLabel('Nom',{exact:true}).fill('Comptable test');
    await page.getByLabel('Identifiant de connexion').fill('new-accountant');
    await page.getByLabel('Mot de passe initial').fill('Cedar-River-83-Moon!');
    await page.locator(`[data-membership="${data.a}"]`).selectOption('accountant');
    await page.getByRole('button',{name:'Enregistrer les accès'}).click();
    await page.getByText('Comptable test',{exact:true}).waitFor();
    await page.screenshot({path:path.join(screenshots,'platform-users.png'),fullPage:true});
    await page.getByRole('button',{name:'Fermer',exact:true}).last().click();

    const readerContext=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'});
    const reader=await readerContext.newPage();reader.on('pageerror',e=>errors.push(e.message));
    await reader.goto('http://localhost:8766');
    await reader.getByLabel('Identifiant',{exact:true}).fill('browser-reader');
    await reader.getByLabel('Mot de passe',{exact:true}).fill(password);
    await reader.getByRole('button',{name:'Se connecter'}).click();
    await reader.getByRole('heading',{name:'Chaque jour, une vue plus claire.'}).waitFor();
    assert.equal(await reader.getByRole('button',{name:'Nouvelle vente',exact:true}).count(),0);
    await reader.getByRole('button',{name:'Ouvrir le menu'}).click();
    assert.equal(await reader.locator('#platform-company-select option').count(),1);
    await reader.getByRole('link',{name:/Produits & stock/}).click();
    assert.equal(await reader.getByRole('button',{name:'Nouveau produit',exact:true}).count(),0);
    assert.equal((await reader.request.get(`http://localhost:8766/api/companies/${data.b}/state`)).status(),404);
    assert.equal((await reader.request.get(`http://localhost:8766/api/companies/${data.a}/backup`)).status(),403);
    assert.equal(await reader.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await reader.screenshot({path:path.join(screenshots,'platform-readonly-mobile.png'),fullPage:true});

    // Revoke the viewer's membership through the actual administration UI.
    await page.getByRole('button',{name:'Utilisateurs & accès'}).click();
    await page.locator('dialog tr').filter({hasText:'browser-reader'}).getByRole('button',{name:'Gérer les accès'}).click();
    await page.locator(`[data-membership="${data.a}"]`).selectOption('');
    await page.getByRole('button',{name:'Enregistrer les accès'}).click();
    await page.getByRole('heading',{name:'Utilisateurs & accès'}).waitFor();
    assert.equal((await reader.request.get(`http://localhost:8766/api/companies/${data.a}/state`)).status(),404);
    await page.getByRole('button',{name:'Fermer',exact:true}).last().click();
    await page.getByRole('button',{name:'Se déconnecter'}).click();
    await page.getByRole('button',{name:'Se connecter'}).waitFor();
    assert.equal((await owner.request.get(`http://localhost:8766/api/companies/${data.a}/state`)).status(),401);
    assert.equal(await page.locator('#print-area').innerText(),'');
    assert.deepEqual(errors,[]);
    console.log('PASS: login/logout, company switching and creation, isolated tabs, products/sales/payments, user creation, per-company roles, revoked access, protected exports, mobile read-only UI.');
  }catch(error){if(page){console.error('Form errors:',await page.locator('.form-error').allTextContents());await page.screenshot({path:path.join(screenshots,'platform-failure.png'),fullPage:true});}throw error;}
  finally{
    if(browser)await browser.close();
    if(server){server.kill('SIGTERM');await new Promise(resolve=>server.once('exit',resolve));}
    const result=spawnSync(python,['tests/platform_fixture.py','drop',db],{cwd:root,encoding:'utf8'});
    if(result.status!==0)console.error('Temporary database cleanup failed:',result.stderr);
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
