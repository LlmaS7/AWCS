from pathlib import Path
p=Path('.temp/testing/output/playwright/report-qa.js');s=p.read_text(encoding='utf-8')
s=s.replace("  const fs = require('fs');\n",'')
s=s.replace("  const exported=JSON.parse(fs.readFileSync('output/playwright/AWCS_evidence_export.json','utf8'));", "  const exported=await page.evaluate(()=>JSON.parse(document.getElementById('reportData').textContent));")
s=s.replace("exported.replay_sources.length===2", "exported.replays.length===2")
s=s.replace("  fs.writeFileSync('output/playwright/report_qa.json',JSON.stringify({checks,errors,requests},null,2));",'')
s=s.replace("return {passed:checks.length,errors,mobile,exportTrials:exported.trials.length}","return {passed:checks.length,checks,errors,mobile,exportTrials:exported.trials.length}")
s=s.replace("'output/playwright/", "'E:/_PROJECTS/AWCS/.temp/testing/output/playwright/")
p.write_text(s,encoding='utf-8')
