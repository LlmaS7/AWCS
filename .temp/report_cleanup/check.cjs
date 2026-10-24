const { chromium } = require('C:/Users/25489/.codex/mcp/free-search-mcp/.venv/Lib/site-packages/playwright/driver/package');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL, fileURLToPath } = require('node:url');
const root = path.resolve(__dirname, '../..');
const report = path.join(root, '.report/AWCS_测试报告.html');
(async () => {
  const downloadsPath = path.join(__dirname, 'downloads');
  fs.mkdirSync(downloadsPath, {recursive:true});
  const browser = await chromium.launch({headless:true,
    downloadsPath,
    executablePath:'C:/Users/25489/AppData/Local/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-win64/chrome-headless-shell.exe',
    args:['--disable-background-networking']});
  const page = await browser.newPage({viewport:{width:1440,height:1000}});
  const errors = [], external = [], checks = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => {if (/^https?:/.test(r.url())) external.push(r.url());});
  function check(name, condition, value) {
    checks.push({name, pass:condition, value});
    if (!condition) throw Error(name + ': ' + JSON.stringify(value));
  }
  try {
    await page.goto(pathToFileURL(report).href);
    await page.waitForFunction(() => window.AWCSReport?.agent);
    const state = await page.evaluate(() => ({
      chapters: document.querySelectorAll('section.chapter').length,
      maps: document.querySelectorAll('.map-card').length,
      algorithmRows: document.querySelectorAll('#case-rows tr').length,
      agentRows: document.querySelectorAll('#agent-rows tr').length,
      reviews: Object.keys(AWCSReport.agent.reviews).length,
      counts: AWCSReport.agent.summary.matrix_effective,
      retest: AWCSReport.agent.d07Retest,
      copy: document.getElementById('submission-text').innerText,
    }));
    check('Historical data and chapter counts retained', state.chapters===12 && state.maps===14 && state.algorithmRows===50 && state.agentRows===60 && state.reviews===157 && state.counts.PASS===146 && state.counts.FAIL===10, state);
    check('D07 supplement and copyable conclusion updated', state.retest.calls===22 && state.retest.targetChecks===9 && state.copy.includes('三轮真实模型定向复测'), state.retest);
    const links = await page.locator('a[href]').evaluateAll(nodes => nodes.map(n => n.getAttribute('href')));
    const bad = [];
    for (const href of links) {
      if (href.startsWith('#')) {
        if (!await page.evaluate(id=>Boolean(document.getElementById(id)), href.slice(1))) bad.push(href);
      } else {
        const url = new URL(href, pathToFileURL(report));
        if (url.protocol==='file:' && !fs.existsSync(fileURLToPath(url))) bad.push(href);
      }
    }
    check('Every HTML source link and anchor resolves', bad.length===0, bad);
    await page.locator('#agent-search').fill('D07');
    check('Historical matrix still interactive', await page.locator('#agent-rows tr:visible').count()===1);
    await page.locator('#agent-rows [data-agent-case="D07/r3"]').click();
    check('Historical critical modal still opens', await page.locator('#agent-dialog').evaluate(n=>n.open));
    await page.keyboard.press('Escape');
    await page.locator('#agent-search').fill('');
    const download = page.waitForEvent('download');
    await page.locator('#download-evidence').click();
    await (await download).saveAs(path.join(__dirname, 'export.json'));
    const exported = JSON.parse(fs.readFileSync(path.join(__dirname, 'export.json'), 'utf8'));
    check('Export keeps original score and adds retest separately', exported.reportDate==='2026-10-22' && exported.consolidated.summary.matrix_effective.FAIL===10 && exported.consolidated.d07Retest.targetChecks===9);
    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({width, height:1000});
      for (const id of ['overview','d07-retest','sources','conclusion']) {
        await page.locator('#'+id).scrollIntoViewIfNeeded();
        const sizes = await page.evaluate(()=>({width:innerWidth, scroll:document.documentElement.scrollWidth}));
        check('No overflow '+width+' '+id, sizes.scroll<=sizes.width, sizes);
      }
      await page.locator('#d07-retest').scrollIntoViewIfNeeded();
      await page.screenshot({path:path.join(__dirname, 'd07-'+width+'.png')});
    }
    check('No JavaScript errors or external requests', !errors.length && !external.length, {errors, external});
    fs.writeFileSync(path.join(__dirname, 'browser_check.json'), JSON.stringify({status:'PASS', checks}, null, 2));
    console.log(JSON.stringify({status:'PASS', checks:checks.length}));
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
