const {chromium}=require('C:/Users/25489/AppData/Local/npm-cache/_npx/31e32ef8478fbf80/node_modules/playwright');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL,fileURLToPath}=require('node:url');
const crypto=require('node:crypto');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'.report/AWCS_测试报告.html');
const sha=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const checks=[],errors=[],external=[];
function check(name,pass,detail){checks.push({name,pass,detail});if(!pass)throw Error(name+': '+JSON.stringify(detail))}
(async()=>{
 const downloadsPath=path.join(__dirname,'downloads');fs.mkdirSync(downloadsPath,{recursive:true});
 const browser=await chromium.launch({headless:true,downloadsPath,executablePath:'C:/Users/25489/AppData/Local/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-win64/chrome-headless-shell.exe',args:['--disable-background-networking']});
 const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))external.push(r.url())});
 try{
  await page.goto(pathToFileURL(out).href);await page.waitForFunction(()=>window.AWCSReport?.agent);
  const initial=await page.evaluate(()=>({chapters:document.querySelectorAll('section.chapter').length,maps:document.querySelectorAll('.map-card').length,algorithmCases:document.querySelectorAll('#case-rows tr').length,agentRows:document.querySelectorAll('#agent-rows tr').length,reviews:Object.keys(AWCSReport.agent.reviews).length,counts:AWCSReport.agent.summary.matrix_effective,replay:AWCSReport.getPlayback(),overflow:document.documentElement.scrollWidth>innerWidth}));
  check('Initial report counts and preserved replay',initial.chapters===12&&initial.maps===14&&initial.algorithmCases===50&&initial.agentRows===60&&initial.reviews===157&&initial.counts.PASS===146&&initial.counts.FAIL===10&&initial.replay.tick>1&&!initial.overflow,initial);
  await page.screenshot({path:path.join(__dirname,'desktop-overview.png')});
  const references=await page.evaluate(()=>[...document.querySelectorAll('a[href]')].map(a=>({href:a.getAttribute('href'),text:a.textContent.trim()})));
  const badLinks=[];for(const ref of references){if(ref.href.startsWith('#')){const exists=await page.locator('[id="'+ref.href.slice(1)+'"]').count();if(!exists)badLinks.push(ref)}else if(!/^data:/.test(ref.href)){const target=new URL(ref.href,pathToFileURL(out));if(target.protocol==='file:'&&!fs.existsSync(fileURLToPath(target)))badLinks.push(ref)}}
  check('All rendered source links and anchors exist',badLinks.length===0,badLinks);
  const ids=await page.evaluate(()=>{const a=[...document.querySelectorAll('[id]')].map(e=>e.id);return a.filter((id,i)=>a.indexOf(id)!==i)});check('Unique HTML ids',ids.length===0,ids);
  await page.locator('#agent-outcome').selectOption('FAIL');check('Failure scene filter',await page.locator('#agent-rows tr:visible').count()===7);
  await page.locator('#agent-outcome').selectOption('STABLE');check('Three passes filter',await page.locator('#agent-rows tr:visible').count()===33);
  await page.locator('#agent-outcome').selectOption('NOT_RUN');check('Not-run scene filter',await page.locator('#agent-rows tr:visible').count()===23);
  await page.locator('#agent-outcome').selectOption('all');await page.locator('#agent-search').fill('D07');check('Search scenario',await page.locator('#agent-rows tr:visible').count()===1);
  await page.locator('#agent-rows [data-agent-case="D07/r3"]').click();check('Critical review modal',await page.locator('#agent-dialog').evaluate(e=>e.open)&&/critical/.test(await page.locator('#agent-dialog-result').innerText()));
  await page.screenshot({path:path.join(__dirname,'critical-modal.png')});await page.keyboard.press('Escape');check('Modal Escape closes',!(await page.locator('#agent-dialog').evaluate(e=>e.open)));
  await page.locator('#agent-search').fill('');await page.locator('#agent-group').selectOption('F');check('Group filter',await page.locator('#agent-rows tr:visible').count()===10);
  await page.locator('#agent-rows [data-agent-case="F01/r3"]').click();check('Not-run has no invented evidence',await page.locator('#agent-dialog-source').isHidden()&&/NOT_RUN/.test(await page.locator('#agent-dialog-result').innerText()));await page.keyboard.press('Escape');await page.locator('#agent-group').selectOption('all');
  await page.locator('#agent').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(__dirname,'desktop-agent.png')});
  await page.locator('#critical').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(__dirname,'desktop-critical.png')});
  await page.locator('[data-filter="rooms"]').click();check('Map atlas filter retained',await page.locator('.map-card:visible').count()===2);await page.locator('[data-filter="all"]').click();
  await page.locator('.map-card').first().click();check('Map modal retained',await page.locator('#map-dialog').evaluate(e=>e.open));await page.locator('#dialog-close').click();
  await page.locator('#replay-select').selectOption('rectangle-20261018');await page.locator('#play').click();await page.waitForTimeout(450);await page.locator('#play').click();check('Archived replay plays',await page.evaluate(()=>AWCSReport.getPlayback().tick)>1);
  await page.locator('#timeline').fill(await page.locator('#timeline').getAttribute('max'));check('Replay reaches actual completion',await page.evaluate(()=>AWCSReport.getPlayback().done)===32);
  await page.locator('#only-unfinished').click();check('Original five unfinished records retained',await page.locator('#case-rows tr:visible').count()===5);
  await page.locator('#case-status').selectOption('all');
  const prePresentation=await page.evaluate(()=>{document.getElementById('agent').scrollIntoView({block:'start',behavior:'instant'});return {y:scrollY,agent:document.getElementById('agent').getBoundingClientRect().top}});
  // Native pointer coordinates avoid Playwright scrolling the sticky header's normal-flow position.
  const presentButton=await page.locator('#present-toggle').boundingBox();await page.mouse.click(presentButton.x+presentButton.width/2,presentButton.y+presentButton.height/2);const presentation=await page.evaluate(()=>({...AWCSReport.getPresentation(),activeId:document.querySelector('.chapter-active')?.id}));check('Presentation includes new chapter',presentation.active&&presentation.activeId==='agent',{prePresentation,presentation});
  await page.keyboard.press('ArrowRight');check('Presentation advances to critical chapter',await page.locator('#critical').isVisible());await page.locator('[data-agent-case="D07/r3"]').first().click();const before=await page.evaluate(()=>AWCSReport.getPresentation().chapter);await page.keyboard.press('ArrowRight');check('Modal owns presentation arrow keys',await page.evaluate(()=>AWCSReport.getPresentation().chapter)===before);await page.keyboard.press('Escape');await page.locator('#presentation-exit').click();
  await page.locator('#notes-toggle').click();check('Speaker notes retained',await page.locator('.speaker-note').first().isVisible());await page.locator('#notes-toggle').click();
  const downloadPromise=page.waitForEvent('download');await page.locator('#download-evidence').click();const download=await downloadPromise;const downloadPath=path.join(__dirname,'downloaded-summary.json');await download.saveAs(downloadPath);const exported=JSON.parse(fs.readFileSync(downloadPath,'utf8'));check('Consolidated export includes both evidence sets',exported.consolidated.summary.matrix_effective.PASS===146&&exported.cases.length===50&&exported.consolidated.provenance.rawPathOnlyChangeVerified);
  for(const width of [390,768,1440]){
   await page.setViewportSize({width,height:1000});
   for(const anchor of ['overview','agent','critical','agent-matrix','sources']){await page.locator('#'+anchor).scrollIntoViewIfNeeded();const overflow=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));check('No page overflow '+width+' '+anchor,overflow.scroll<=overflow.width,overflow)}
   if(width===390){await page.locator('#overview').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(__dirname,'mobile-overview.png')});await page.locator('#agent').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(__dirname,'mobile-agent.png')});}
  }
  await page.emulateMedia({media:'print'});const printState=await page.evaluate(()=>({chapters:[...document.querySelectorAll('.chapter')].filter(e=>getComputedStyle(e).display!=='none').length,rows:[...document.querySelectorAll('#agent-rows tr')].filter(e=>getComputedStyle(e).display!=='none').length}));check('Print contains all report chapters and matrix rows',printState.chapters===12&&printState.rows===60,printState);
  await page.pdf({path:path.join(__dirname,'print-preview.pdf'),printBackground:true,preferCSSPageSize:true});
  check('No JavaScript errors',errors.length===0,errors);check('Offline page makes no network requests',external.length===0,external);
  const audit=JSON.parse(fs.readFileSync(path.join(__dirname,'build_audit.json'),'utf8'));const changedSources=Object.entries(audit.sourceHashes).filter(([file,hash])=>sha(path.isAbsolute(file)?file:path.join(root,file))!==hash);check('All source reports and reviewed evidence remain unchanged',changedSources.length===0,changedSources);
  fs.writeFileSync(path.join(__dirname,'qa_results.json'),JSON.stringify({status:'PASS',checks,errors,external},null,2));console.log(JSON.stringify({status:'PASS',checks:checks.length,errors,external}));
 }finally{await browser.close()}
})().catch(e=>{fs.writeFileSync(path.join(__dirname,'qa_results.json'),JSON.stringify({status:'FAIL',checks,errors,error:e.stack},null,2));console.error(e);process.exitCode=1});
