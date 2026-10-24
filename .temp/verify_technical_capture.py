from pathlib import Path
import subprocess,json,re
ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'.temp'/'video_technical_qa'
page=(ROOT/'.report'/'演示视频_20261022'/'04_关键技术与测试_录屏讲解.html').read_text(encoding='utf-8')
checks=r'''
<script>
addEventListener('load',()=>{setTimeout(()=>{
try{
show(1);dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight'}));if(current!==2)throw Error('keyboard');
toggleRecord();if(getComputedStyle($('toolbar')).display!=='none')throw Error('recording');
toggleNotes();if(!$('notes').classList.contains('open'))throw Error('notes');$('notes').classList.remove('open');
frame=5000;drawMatching();if($('matchCost').textContent!=='6')throw Error('matching');
show(3);frame=3000;drawPath();if($('tick').textContent!=='2')throw Error('path');
show(0);auto=true;timerRunning=true;pageElapsed=notes[0][1]*1000-1;last=performance.now()-100;update(performance.now());if(current!==1)throw Error('auto');auto=false;timerRunning=false;
show(__INDEX__);document.body.classList.add('recording');paused=true;
setTimeout(()=>{const s=slides[current],r=s.getBoundingClientRect();const result={slide:current+1,codeOverflow:[...s.querySelectorAll('.codebody,.line code')].filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>({cls:e.className,scroll:e.scrollWidth,width:e.clientWidth,text:e.textContent})),outside:[...s.querySelectorAll('*')].filter(e=>{const a=e.getBoundingClientRect();return a.width&&a.height&&(a.bottom>r.bottom+2||a.right>r.right+2)}).map(e=>e.className.baseVal||e.className),bottomOverlap:[...s.children].filter(e=>!e.classList.contains('bottom')&&e.getBoundingClientRect().bottom>(s.querySelector('.bottom')?.getBoundingClientRect().top||r.bottom)-8).map(e=>e.className)};const report=document.createElement('pre');report.id='qa-result';report.style.display='none';report.textContent=JSON.stringify(result);document.body.append(report);},100);
}catch(e){document.body.dataset.qaError=e.stack;}
},50);});
</script>
'''
index=__import__('sys').argv[1:]
indices=[int(x) for x in index] if index else range(7)
for i in indices:
 target=QA/f'qa_slide_{i+1}.html';target.write_text(page.replace('</body>',checks.replace('__INDEX__',str(i))+'</body>'),encoding='utf-8')
 args=[r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe','--headless=new','--disable-gpu','--no-sandbox','--disable-features=RendererCodeIntegrity','--no-first-run','--no-default-browser-check','--disable-extensions','--hide-scrollbars','--window-size=1920,1080','--virtual-time-budget=1400','--screenshot='+str(QA/f'slide_{i+1}.png'),'--dump-dom','--user-data-dir='+str(QA/f'capture_nosandbox_{i+1}'),target.as_uri()]
 result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=25,creationflags=subprocess.CREATE_NO_WINDOW)
 dom=result.stdout.decode('utf-8',errors='replace');(QA/f'dom_{i+1}.html').write_text(dom,encoding='utf-8')
 found=re.search(r'<pre id="qa-result"[^>]*>(.*?)</pre>',dom,re.S)
 report=__import__('html').unescape(found[1]) if found else 'NO_RESULT '+result.stderr.decode('utf-8',errors='replace')[-700:]
 print(report,flush=True)
