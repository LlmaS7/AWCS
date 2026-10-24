const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('C:/Users/25489/.codex/mcp/free-search-mcp/.venv/Lib/site-packages/playwright/driver/package');
const root=path.resolve('frontend'),uploads=[],errors=[];
let draft=null,checks=0;
async function serve(route){
  const req=route.request(),url=new URL(req.url());
  if(url.pathname.startsWith('/api/ai/imports/')){
    if(url.pathname.endsWith('/upload')){
      const filename=decodeURIComponent(req.headers()['x-import-filename']);
      uploads.push({filename,generation:req.headers()['x-scene-generation'],body:req.postDataBuffer().toString()});
      draft={draft_id:'d'+uploads.length,document_id:'b'+uploads.length,state:'uploaded',filename,format:filename.split('.').pop().toLowerCase(),duplicates:[],candidates:[],excluded:[],operations:[],warnings:[],locations:{pickup:[],delivery:[]}};
      await route.fulfill({json:{draft}});return;
    }
    if(url.pathname.endsWith('/discard'))draft=null;
    await route.fulfill({json:{draft}});return;
  }
  const name=path.resolve(root,'.'+decodeURIComponent(url.pathname==='/'?'/index.html':url.pathname));
  if(!name.startsWith(root+path.sep)||!fs.existsSync(name)){await route.fulfill({status:404,body:''});return;}
  let body=fs.readFileSync(name);
  if(name.endsWith('index.html'))body=body.toString().replace('<script type="module" src="./app.js"></script>','');
  await route.fulfill({contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':name.endsWith('.svg')?'image/svg+xml':name.endsWith('.html')?'text/html':'application/octet-stream',body});
}
function check(value,message){assert.ok(value,message);checks++;console.log('PASS '+message);}
(async()=>{
  let browser;
  try{
    browser=await chromium.launch({headless:true,executablePath:'C:/Users/25489/AppData/Local/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-win64/chrome-headless-shell.exe'});
    const page=await browser.newPage({viewport:{width:1460,height:940}});
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',serve);
    await page.goto('http://awcs.test/');
    await page.evaluate(async()=>{
      const {Imports}=await import('/imports.js');
      document.getElementById('chat-content').hidden=false;
      document.querySelector('[aria-labelledby="tab-tasks"]').hidden=true;
      window.notices=[];window.scene={generation:7};
      window.chat={busy:false,submitting:false,state:()=>window.scene,controls:()=>window.importer?.controls(),notice:v=>notices.push(v)};
      window.importer=new Imports(chat);
    });
    await page.waitForFunction(()=>window.importer&&!window.importer.refreshing);
    async function drag(type,target='#chat-input',files=[{name:'sample.md',text:'从P01到D1搬运1次'}],extra={}){
      return page.evaluate(({type,target,files,extra})=>{
        const transfer=new DataTransfer();
        Object.defineProperty(transfer,'dropEffect',{value:'none',writable:true});
        if(extra.textOnly)transfer.setData('text/plain','普通文字');
        else for(const f of files)transfer.items.add(new File([f.text??'x'],f.name));
        if(extra.directory)Object.defineProperty(transfer,'items',{value:[{webkitGetAsEntry:()=>({isDirectory:true})}]});
        const event=new DragEvent(type,{bubbles:true,cancelable:true,dataTransfer:transfer});
        document.querySelector(target).dispatchEvent(event);
        return {prevented:event.defaultPrevented,effect:transfer.dropEffect,hint:!document.getElementById('import-drop-hint').hidden,label:document.getElementById('import-drop-label').textContent,error:document.getElementById('import-compose-error').textContent};
      },{type,target,files,extra});
    }
    let r=await drag('dragover','#chat-input',[],{textOnly:true});check(!r.prevented&&!r.hint,'normal text dragging is unchanged');
    r=await drag('dragover','.topbar');check(r.prevented&&r.effect==='none'&&!r.hint,'outside file drag prevents navigation without highlighting');
    await drag('dragenter','#chat-content');await drag('dragenter','#chat-input');
    r=await drag('dragleave','#chat-input');check(r.hint,'nested child dragleave keeps highlight');
    r=await drag('dragleave','#chat-content');check(!r.hint,'leaving drop area clears highlight');
    r=await drag('dragover');check(r.prevented&&r.effect==='copy'&&r.hint&&r.label==='松开以导入文件','valid file drag shows import prompt and copy cursor');
    await page.screenshot({path:'.temp/word_import_qa/import_drop_preview.png'});
    r=await drag('drop');await page.waitForFunction(()=>window.notices.length===1);
    check(r.prevented&&!r.hint&&uploads.length===1,'single file drop uploads exactly once and clears highlight');
    check(uploads[0].generation==='7'&&uploads[0].body==='从P01到D1搬运1次','upload preserves file bytes and scene generation');
    check(await page.locator('#import-filename').textContent()==='sample.md','existing attachment UI displays dropped file');
    r=await drag('drop','#chat-input',[{name:'a.md'},{name:'b.txt'}]);check(r.error.includes('一个文件')&&uploads.length===1,'multiple files rejected before replacing attachment');
    r=await drag('drop','#chat-input',[{name:'folder'}],{directory:true});check(r.error.includes('文件夹')&&uploads.length===1,'folder drops rejected');
    r=await drag('drop','#chat-input',[{name:'a.pdf'}]);check(r.error.includes('请选择 MD/TXT')&&uploads.length===1,'unsupported extension uses existing validation');
    r=await drag('drop','#chat-input',[{name:'empty.txt',text:''}]);check(r.error.includes('请选择 MD/TXT')&&uploads.length===1,'empty file rejected');
    r=await drag('drop','#chat-input',[{name:'large.txt',text:'a'.repeat(1024**2+1)}]);check(r.error.includes('请选择 MD/TXT')&&uploads.length===1,'oversized file rejected');
    for(const key of ['busy','submitting','loading']){
      await page.evaluate(key=>{(key==='loading'?importer:chat)[key]=true;chat.controls();},key);
      r=await drag('dragover');check(r.effect==='none'&&r.label.includes('等待'),'blocked drag feedback during '+key);
      r=await drag('drop');check(r.error.includes('等待')&&uploads.length===1,'drop blocked during '+key);
      await page.evaluate(key=>{(key==='loading'?importer:chat)[key]=false;chat.controls();},key);
    }
    await page.evaluate(()=>{window.scene=null;chat.controls();});r=await drag('drop');check(r.error.includes('尚未就绪')&&uploads.length===1,'uninitialized scene blocks drop');
    await page.evaluate(()=>{window.scene={generation:7};chat.controls();});
    const cancel=dialog=>dialog.dismiss();page.on('dialog',cancel);
    await drag('drop','#chat-input',[{name:'replacement.txt'}]);await page.waitForTimeout(100);
    check(uploads.length===1&&await page.locator('#import-filename').textContent()==='sample.md','cancelled replacement preserves original attachment');page.off('dialog',cancel);
    page.once('dialog',dialog=>dialog.accept());
    await drag('drop','#chat-input',[{name:'replacement.DOCX'}]);await page.waitForFunction(()=>window.notices.length===2);
    check(uploads.length===2&&uploads[1].filename==='replacement.DOCX','confirmed replacement accepts uppercase DOCX extension');
    page.once('dialog',dialog=>dialog.accept());
    await page.locator('#import-file').setInputFiles({name:'button-path.txt',mimeType:'text/plain',buffer:Buffer.from('existing picker upload')});
    await page.waitForFunction(()=>window.notices.length===3);check(uploads.length===3&&uploads[2].filename==='button-path.txt','file picker upload still works');
    await drag('drop','.topbar');check(uploads.length===3,'outside drop cannot upload');
    await drag('dragover');await page.evaluate(()=>window.dispatchEvent(new Event('blur')));check(await page.locator('#import-drop-hint').isHidden(),'window blur clears highlight');
    await drag('dragover');await drag('dragend');check(await page.locator('#import-drop-hint').isHidden(),'dragend clears highlight');
    check(errors.length===0,'no browser JavaScript errors: '+errors.join('; '));
    console.log('All '+checks+' browser checks passed. Upload API mocked; native OS/WebView drag not exercised.');
  }finally{if(browser)await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
