import asyncio,json,base64,urllib.request,subprocess,time
from pathlib import Path
from websockets.sync.client import connect
ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'.temp'/'video_technical_qa'
HTML=ROOT/'.report'/'演示视频_20261022'/'04_关键技术与测试_录屏讲解.html'
class CDP:
 def __init__(self,ws):self.ws=ws;self.i=0;self.events=[]
 def call(self,method,params=None):
  self.i+=1;idx=self.i
  self.ws.send(json.dumps({'id':idx,'method':method,'params':params or {}}))
  while True:
   msg=json.loads(self.ws.recv())
   if msg.get('id')==idx:
    if 'error' in msg:raise RuntimeError(msg['error'])
    return msg.get('result',{})
   self.events.append(msg)
 def evaluate(self,expression):
  result=self.call('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True})
  if result.get('exceptionDetails'):raise RuntimeError(result['exceptionDetails'])
  return result['result'].get('value')
def main():
 edge=Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
 log=(QA/'edge.log').open('w')
 browser=subprocess.Popen([str(edge),'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=9336','--user-data-dir='+str(QA/'profile3'),'about:blank'],stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
 for attempt in range(40):
  try:
   tabs=json.load(urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://[::1]:9336/json',timeout=1));break
  except Exception:
   time.sleep(.25)
 else: raise RuntimeError('Edge did not expose CDP: '+(QA/'edge.log').read_text(errors='replace'))
 with connect(next(t['webSocketDebuggerUrl'] for t in tabs if t['type']=='page'),max_size=20_000_000,proxy=None) as ws:
  c=CDP(ws);c.call('Runtime.enable');c.call('Page.enable')
  c.call('Emulation.setDeviceMetricsOverride',{'width':1920,'height':1080,'deviceScaleFactor':1,'mobile':False})
  c.call('Page.navigate',{'url':HTML.as_uri()});time.sleep(.7)
  results=[]
  for index in range(7):
   c.evaluate(f'show({index});document.body.classList.add("recording");paused=true;')
   time.sleep(.35)
   result=c.evaluate('''(()=>{const s=slides[current],r=s.getBoundingClientRect();return {slide:current+1,title:s.querySelector('h1').textContent,codeOverflow:[...s.querySelectorAll('.codebody,.line code')].filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>({cls:e.className,scroll:e.scrollWidth,width:e.clientWidth,text:e.textContent})),outside:[...s.querySelectorAll('*')].filter(e=>{const a=e.getBoundingClientRect();return a.width&&a.height&&(a.bottom>r.bottom+2||a.right>r.right+2)}).map(e=>e.className),bottomOverlap:[...s.children].filter(e=>!e.classList.contains('bottom')&&e.getBoundingClientRect().bottom>(s.querySelector('.bottom')?.getBoundingClientRect().top||r.bottom)-8).map(e=>({cls:e.className,bottom:e.getBoundingClientRect().bottom})),stage:{w:innerWidth,h:innerHeight}}})()''')
   shot=c.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
   (QA/f'slide_{index+1}.png').write_bytes(base64.b64decode(shot['data']));results.append(result)
  c.evaluate('document.body.classList.remove("recording");show(0);')
  c.call('Input.dispatchKeyEvent',{'type':'keyDown','key':'ArrowRight','code':'ArrowRight','windowsVirtualKeyCode':39});c.call('Input.dispatchKeyEvent',{'type':'keyUp','key':'ArrowRight','code':'ArrowRight','windowsVirtualKeyCode':39})
  assert c.evaluate('current')==1
  c.evaluate('toggleRecord()');assert c.evaluate('getComputedStyle($("toolbar")).display')=='none'
  c.evaluate('toggleNotes()');assert c.evaluate('$("notes").classList.contains("open")&&!document.body.classList.contains("recording")')
  c.evaluate('$("notes").classList.remove("open");show(2);frame=5000;drawMatching();');assert c.evaluate('$("matchCost").textContent')=='6'
  c.evaluate('show(3);frame=3000;drawPath();');assert c.evaluate('$("tick").textContent')=='2'
  c.evaluate('show(0);auto=true;timerRunning=true;pageElapsed=notes[0][1]*1000-1;last=performance.now()-100;')
  time.sleep(.1);assert c.evaluate('current')==1
  c.evaluate('auto=false;timerRunning=false;show(0);toggleRecord();')
  c.call('Emulation.setDeviceMetricsOverride',{'width':1280,'height':720,'deviceScaleFactor':1,'mobile':False})
  time.sleep(.2)
  assert c.evaluate('Math.abs($("stage").getBoundingClientRect().width-innerWidth)<2')
  errors=[e for e in c.events if e.get('method')=='Runtime.exceptionThrown']
  report={'slides':results,'runtime_errors':errors,'controls':'keyboard,recording,notes,matching,path,auto_advance,1280x720 scaling PASS'}
  (QA/'qa.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps(report,ensure_ascii=False))
main()
