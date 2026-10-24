from pathlib import Path
import json,re
p=Path('.temp/testing/output/playwright/report_qa_output.txt');s=p.read_text(encoding='utf-8-sig');m=re.search(r'### Result\s*\n([^\n]+)',s);q=json.loads(m.group(1));assert q['passed']==28 and not q['errors'];Path('.temp/testing/output/playwright/report_qa.json').write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf-8');print('Report QA: 28 checks passed; no runtime errors.')
