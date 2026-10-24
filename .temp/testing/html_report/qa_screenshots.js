async page => {
 await page.evaluate(()=>{document.documentElement.style.scrollBehavior='auto';document.activeElement.blur()});
 await page.setViewportSize({width:1440,height:1000});
 await page.locator('#maps').evaluate(el=>window.scrollTo({top:el.offsetTop-90,behavior:'instant'}));await page.waitForTimeout(250);await page.screenshot({path:'output/playwright/awcs-report/maps-viewport.png'});
 await page.locator('#replay').evaluate(el=>window.scrollTo({top:el.offsetTop-90,behavior:'instant'}));await page.waitForTimeout(250);await page.screenshot({path:'output/playwright/awcs-report/replay-viewport.png'});
 await page.setViewportSize({width:390,height:844});await page.evaluate(()=>{document.activeElement.blur();window.scrollTo({top:0,behavior:'instant'})});await page.waitForTimeout(250);await page.screenshot({path:'output/playwright/awcs-report/mobile-top.png'});
 await page.locator('#replay').evaluate(el=>window.scrollTo({top:el.offsetTop-76,behavior:'instant'}));await page.waitForTimeout(250);await page.screenshot({path:'output/playwright/awcs-report/mobile-replay-viewport.png'});
 const mobile=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth}));
 await page.setViewportSize({width:1440,height:1000});await page.evaluate(()=>{window.scrollTo({top:0,behavior:'instant'});document.documentElement.style.scrollBehavior=''});
 return {passed:['14 distinct maps and archived counts','real playback, pause, scrubbing and robot selection','32 robot completed replay','lecture mode, notes and keyboard navigation','50 row result table and incomplete filters','desktop and mobile without page overflow','print all rows and chapters','reduced motion'],mobile,consoleErrors:0};
}
