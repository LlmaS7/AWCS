from pathlib import Path
import json
from html.parser import HTMLParser
r=Path('.report/AWCS_项目测试报告.html');s=r.read_text(encoding='utf-8')
class Parse(HTMLParser):
    def __init__(self):super().__init__();self.ids=[];self.refs=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag in ('script','link') and ('src' in a or (a.get('rel')=='stylesheet')):self.refs.append(a)
p=Parse();p.feed(s);assert len(p.ids)==len(set(p.ids));assert not p.refs;assert '__REPORT_DATA__' not in s
exp=json.loads(Path('.temp/testing/output/playwright/AWCS_evidence_export.json').read_text(encoding='utf-8'));assert len(exp['trials'])==19 and len(exp['replay_sources'])==2
print(json.dumps(dict(html_bytes=r.stat().st_size,unique_ids=len(p.ids),external_dependencies=len(p.refs),export_trials=len(exp['trials'])),ensure_ascii=False))
