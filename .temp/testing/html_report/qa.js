async page => {
 const assert=(ok,msg)=>{if(!ok)throw new Error(msg)};const checks=[];
 const data=await page.evaluate(()=>window.AWCSReport.data);
 assert(data.maps.filter(m=>m.shape!=='fleet').length===14,'14 maps');
 assert(new Set(data.maps.filter(m=>m.shape!=='fleet').map(m=>JSON.stringify(m.rows))).size===14,'unique geometry');
 assert(data.cases.length===50&&Math.max(...data.cases.map(c=>c.n))===32,'scope');
 assert(data.cases.filter(c=>c.status==='INCONCLUSIVE').length===5,'incomplete retained');
 assert(data.replays.every(r=>r.frames.length===r.tick&&r.frames.at(-1)[1]===r.total),'complete replay data');checks.push('data');
 await page.locator('#maps').scrollIntoViewIfNeeded();await page.getByRole('button',{name:'房间',exact:true}).click();
 assert(await page.locator('.map-card:visible').count()===2,'map filter');await page.locator('.map-card:visible').first().click();assert(await page.locator('#map-dialog').isVisible(),'map dialog');
 await page.screenshot({path:'output/playwright/awcs-report/map-dialog.png'});await page.locator('#dialog-replay').click();
 assert(await page.evaluate(()=>window.AWCSReport.getPlayback().id)==='rooms-20261018','map replay');
 await page.getByRole('button',{name:'播放真实轨迹',exact:true}).click();await page.waitForFunction(()=>window.AWCSReport.getPlayback().tick>5);await page.getByRole('button',{name:'暂停真实轨迹',exact:true}).click();
 const paused=await page.evaluate(()=>window.AWCSReport.getPlayback().tick);await page.waitForTimeout(200);assert(await page.evaluate(()=>window.AWCSReport.getPlayback().tick)===paused,'pause');
 await page.locator('#robot-select').selectOption('7');assert(await page.evaluate(()=>window.AWCSReport.getPlayback().robot)===7,'robot selection');
 await page.locator('#timeline').press('End');assert(await page.evaluate(()=>window.AWCSReport.getPlayback().done)===32,'final frame');
 await page.locator('#timeline').evaluate(el=>{el.value='130';el.dispatchEvent(new Event('input',{bubbles:true}))});assert(await page.evaluate(()=>window.AWCSReport.getPlayback().tick)===130,'scrub');
 await page.locator('#replay').screenshot({path:'output/playwright/awcs-report/replay-desktop.png'});
 await page.locator('#replay-select').selectOption('fleet-32');assert(await page.locator('#robot-select option').count()===32,'32 robots');await page.locator('#timeline').press('End');assert(await page.evaluate(()=>window.AWCSReport.getPlayback().done)===64,'32 run completed');checks.push('replay');
 await page.getByRole('button',{name:'讲解提示',exact:true}).click();assert(await page.locator('#replay .speaker-note').isVisible(),'notes');await page.getByRole('button',{name:'讲解视图',exact:true}).click();
 const start=await page.evaluate(()=>window.AWCSReport.getPresentation().chapter);assert(await page.locator('.chapter:visible').count()===1,'one chapter');await page.locator('#present-toggle').focus();await page.keyboard.press('ArrowRight');assert(await page.evaluate(()=>window.AWCSReport.getPresentation().chapter)===Math.min(start+1,6),'next chapter');await page.keyboard.press('Escape');assert(!await page.evaluate(()=>window.AWCSReport.getPresentation().active),'exit lecture');await page.getByRole('button',{name:'讲解提示',exact:true}).click();checks.push('lecture');
 await page.locator('#only-unfinished').click();assert(await page.locator('#case-rows tr:visible').count()===5,'5 unfinished');await page.locator('#case-category').selectOption({label:'规模验证'});assert(await page.locator('#case-rows tr:visible').count()===3,'3 scale unfinished');
 await page.locator('#case-status').selectOption('all');await page.locator('#case-category').selectOption('all');await page.locator('#more-results').click();assert(await page.locator('#case-rows tr:visible').count()===50,'50 rows');await page.locator('#more-results').click();checks.push('table');
 await page.getByRole('button',{name:'全部 14 张',exact:true}).click();await page.locator('#maps').screenshot({path:'output/playwright/awcs-report/maps-desktop.png'});assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),'desktop overflow');
 await page.setViewportSize({width:390,height:844});await page.evaluate(()=>window.scrollTo(0,0));await page.waitForTimeout(200);assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),'mobile overflow');await page.screenshot({path:'output/playwright/awcs-report/mobile.png'});await page.locator('#maps').screenshot({path:'output/playwright/awcs-report/maps-mobile.png'});await page.locator('#replay').screenshot({path:'output/playwright/awcs-report/replay-mobile.png'});checks.push('mobile');
 await page.setViewportSize({width:1440,height:1000});await page.emulateMedia({media:'print'});assert(await page.locator('#case-rows tr:visible').count()===50,'print all rows');assert(await page.locator('.chapter:visible').count()===7,'print all sections');await page.emulateMedia({media:'screen',reducedMotion:'reduce'});assert(await page.evaluate(()=>getComputedStyle(document.documentElement).scrollBehavior)==='auto','reduced motion');await page.emulateMedia({reducedMotion:'no-preference'});checks.push('print and reduced motion');
 await page.locator('#replay-select').selectOption('rooms-20261018');await page.locator('#timeline').evaluate(el=>{el.value='101';el.dispatchEvent(new Event('input',{bubbles:true}))});await page.evaluate(()=>window.scrollTo(0,0));
 console.log(JSON.stringify({passed:checks,maps:14,replays:data.replays.length,cases:data.cases.length}));
}
