from pathlib import Path
from html.parser import HTMLParser
import json,re
root=Path.cwd();folder=root/'.report'/'演示视频_20261022';page=folder/'04_关键技术与测试_录屏讲解.html'
text=page.read_text(encoding='utf-8')
class Check(HTMLParser):
 def __init__(self):super().__init__();self.ids=[];self.slides=0;self.links=[];self.external=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if 'id' in a:self.ids.append(a['id'])
  if tag=='section' and a.get('class')=='slide':self.slides+=1
  if tag=='a':self.links.append(a.get('href',''))
  if tag in ['script','link','img','iframe'] and (a.get('src') or a.get('href')):self.external.append(a.get('src') or a.get('href'))
p=Check();p.feed(text)
assert len(set(p.ids))==len(p.ids),'duplicate IDs'
assert p.slides==7
assert not p.external
assert all((folder/link).exists() for link in p.links),'missing local link'
js=re.search(r'<script>(.*?)</script>',text,re.S)[1]
(root/'.temp'/'video_technical_script.js').write_text(js,encoding='utf-8')
assert '__NOTES__' not in text and '__SLIDES__' not in text
notes=json.loads(re.search(r'const\s+notes\s*=\s*(.*?);\s*\n',js,re.S)[1])
assert sum(n[1] for n in notes)==240
md=(folder/'05_关键技术与测试_配套讲稿.md').read_text(encoding='utf-8')
assert all(n[3] in md for n in notes)
print(json.dumps({'slides':p.slides,'local_links':len(p.links),'external_assets':len(p.external),'duration_seconds':sum(n[1] for n in notes),'spoken_characters':sum(len(n[3]) for n in notes),'per_page_seconds':[n[1] for n in notes],'paired_notes':'identical','html_bytes':page.stat().st_size},ensure_ascii=False))
