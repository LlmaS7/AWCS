const $=id=>document.getElementById(id);
const scopeNames={library:'我的地图',app:'仿真地图 · 只读',archive:'已归档'};
let catalog=[],current=null,selected=null,analysis=null,busy=false;
const status=(message,error=false)=>{$('status').textContent=message;$('status').className='status'+(error?' error':busy?' busy':'');};
async function request(path,data) {
  const response=await fetch('./api/'+path,data===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const value=await response.json();if(!response.ok)throw new Error(value.error||'操作失败');return value;
}
function controls() {
  for(const item of document.querySelectorAll('button,input,select'))item.disabled=busy;
  for(const item of document.querySelectorAll('[data-map]'))item.disabled=busy||!current;
  $('rename').disabled=$('archive').disabled=$('publish').disabled=busy||selected?.scope!=='library';
}
async function action(work) {
  if(busy)return;busy=true;controls();
  try {await work();}catch(e){status(e.message,true);}finally{busy=false;controls();$('status').classList.remove('busy');}
}
async function job(type,data) {
  const value=await request(type,data);
  while(true) {
    await new Promise(resolve=>setTimeout(resolve,250));
    const result=await request('job?id='+encodeURIComponent(value.id));
    if(result.status==='error')throw new Error(result.error);
    if(result.status==='done')return result;
  }
}
function text(tag,value,className='') {const el=document.createElement(tag);el.textContent=value;if(className)el.className=className;return el;}
function renderList() {
  const needle=$('search').value.toLowerCase(),scope=$('scope').value;
  const items=catalog.filter(m=>(scope==='all'?m.scope!=='archive':m.scope===scope)&&(`${m.name} ${m.id}`.toLowerCase().includes(needle)));
  $('count').textContent=items.length;
  $('maps').replaceChildren(...items.map(m=>{
    const button=text('button','',`map-item${selected?.id===m.id&&selected?.scope===m.scope?' active':''}`);
    button.setAttribute('aria-pressed',String(selected?.id===m.id&&selected?.scope===m.scope));
    button.append(text('strong',m.name),text('small',m.available?`${m.width} × ${m.height} · 上限 ${m.max_robots} 台`:'文件无效'),text('small',scopeNames[m.scope]));
    button.title=m.available?m.id:m.error;button.disabled=busy;
    button.onclick=()=>action(async()=>{
      status('正在读取并检查地图…');
      const definition=await request(`map?id=${encodeURIComponent(m.id)}&scope=${m.scope}`);
      try{const result=await job('validate',{definition});show(definition,{id:m.id,scope:m.scope});showAnalysis(result.analysis);status('已载入 '+definition.name);}
      catch(e){$('check-result').textContent=e.message;$('check-result').className='check-result error';throw e;}
    });return button;
  }));
  if(!items.length)$('maps').append(text('p','暂无地图','muted'));
}
async function refresh() {catalog=(await request('catalog')).maps;renderList();}
function uniqueId(prefix='map') {return `${prefix}_${Date.now().toString(36)}_${crypto.getRandomValues(new Uint32Array(1))[0].toString(36).slice(0,4)}`;}
function show(definition,selection=null) {
  current=definition;selected=selection;analysis=null;
  const parameters=definition.metadata?.parameters;
  if(parameters && typeof parameters==='object')for(const id of ['shape','width','height','robots','seed','aisle','density','obstacles']) {
    const input=$(id),value=parameters[id];
    if(id==='shape'?[...input.options].some(o=>o.value===value):Number.isInteger(value)&&value>=Number(input.min)&&value<=Number(input.max))input.value=value;
  }
  $('map-name').textContent=definition.name||'导入地图';$('draft').textContent=selection?scopeNames[selection.scope]:'预览 · 尚未保存';
  $('name').value=definition.name||'';$('map-id').value=uniqueId(definition.metadata?.parameters?.shape||'map');
  $('target-id').value='studio_'+(selection?.id||$('map-id').value);
  $('probe-robots').max=definition.robots?.max_count||definition.points?.starts?.length||1;
  $('probe-robots').value=definition.robots?.default_count||Math.min(3,Number($('probe-robots').max));
  $('check-result').className='check-result';$('check-result').textContent='等待静态检查…';
  $('stats').replaceChildren(text('span','等待检查'));
  preview.set(definition);renderList();controls();
}
function showAnalysis(value) {
  analysis=value;
  const fields=[['尺寸',`${value.width} × ${value.height}`],['地面',`${value.floor_cells} 格`],['地图外',`${value.void_cells} 格`],['货架',value.shelves],['停车位',value.parking],['机器人上限',value.max_robots]];
  $('stats').replaceChildren(...fields.map(([name,val])=>{const el=text('span',name);el.append(text('strong',String(val)));return el;}));
  const p=value.probe;
  const lines=[`静态检查通过 · ${value.pickups} 个取货点 / ${value.deliveries} 个配送点 / ${value.free_cells} 个可通行格`,
    `拓扑提示：${value.topology.cutpoints} 个割点，${value.topology.dead_ends} 个死胡同。`];
  if(value.pending_obstacles)lines.push(`此图是模板，另含最多 ${value.pending_obstacles} 个待生成障碍（未绘出）；试运行按下方种子生成。新生成地图的障碍已固定。`);
  if(p)lines.push(`规划试运行${p.status==='passed'?'通过':'未通过或未完成'} · ${p.robots} 台 · 种子 ${p.seed} · 完成 ${p.completed}/${p.tasks} · ${p.tick} 步 · ${p.elapsed} 秒`,p.failure||p.note);
  else lines.push('尚未进行多机器人规划试运行。');
  $('check-result').className='check-result'+(p&&p.status!=='passed'?' error':'');$('check-result').textContent=lines.join('\n');
}
function validInput(id) {const input=$(id);if(!input.value||!input.reportValidity())throw new Error('请填写有效的'+(id==='map-id'?'新文件标识':id==='target-id'?'仿真地图标识':'参数'));return input.value;}
$('generate-form').onsubmit=e=>{e.preventDefault();action(async()=>{
  const parameters={shape:$('shape').value};for(const id of ['width','height','robots','seed','aisle','density','obstacles'])parameters[id]=Number(validInput(id));
  status('正在构造轮廓、布置作业点并检查连通性…');
  const result=await job('generate',{parameters});show(result.definition);showAnalysis(result.analysis);status('新地图已生成，尚未保存；当前仿真不受影响。');
});};
$('new-seed').onclick=()=>{$('seed').value=crypto.getRandomValues(new Uint32Array(1))[0]%2147483648;};
$('refresh').onclick=()=>action(async()=>{await refresh();status('地图库已刷新。');});
$('scope').onchange=$('search').oninput=renderList;
$('validate').onclick=()=>action(async()=>{status('正在检查地图…');showAnalysis((await job('validate',{definition:current})).analysis);status('静态检查完成。');});
$('probe').onclick=()=>action(async()=>{status('正在独立试运行；通常需要数秒，最多约90秒…');const result=await job('probe',{definition:current,robots:Number(validInput('probe-robots')),seed:Number(validInput('probe-seed'))});showAnalysis(result.analysis);status('规划试运行完成，报告已保存在地图库 reports 中。');});
$('save').onclick=()=>action(async()=>{
  const id=validInput('map-id'),name=validInput('name');status('正在检查并保存新地图…');
  const result=await request('save',{id,name,definition:current});show(result.definition,{id,scope:'library'});await refresh();
  showAnalysis((await job('validate',{definition:current})).analysis);status('已保存到“我的地图”；可继续导出到 v0.4。');
});
$('rename').onclick=()=>action(async()=>{const result=await request('rename',{id:selected.id,name:validInput('name')});show(result.definition,selected);await refresh();showAnalysis((await job('validate',{definition:current})).analysis);status('地图名称已更新；此前导出的副本不受影响。');});
$('publish').onclick=()=>action(async()=>{status('正在检查并导出地图…');const result=await request('publish',{id:selected.id,target_id:validInput('target-id')});await refresh();status(result.message);});
$('archive').onclick=()=>{$('archive-dialog').showModal();};
$('archive-dialog').addEventListener('close',()=>{if($('archive-dialog').returnValue==='archive')action(async()=>{const previous=analysis,item=await request('archive',{id:selected.id});show(current,item);if(previous)showAnalysis(previous);await refresh();status('已归档。可在已归档分组载入，并保存为新地图恢复。');});});
$('import').onclick=()=>$('file').click();
$('file').onchange=()=>action(async()=>{
  const file=$('file').files[0];$('file').value='';if(!file)return;
  if(file.size>2*1024*1024)throw new Error('地图超过2 MB');
  const definition=JSON.parse((await file.text()).replace(/^\uFEFF/,''));status('正在检查导入文件…');
  const result=await job('validate',{definition});show(result.definition);showAnalysis(result.analysis);status('导入检查通过；尚未保存到地图库。');
});
$('export').onclick=()=>{
  const blob=new Blob([JSON.stringify(current,null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;a.download=(selected?.id||$('map-id').value||'map')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);status('已开始下载当前地图快照。');
};

class Preview {
  constructor() {
    this.canvas=$('canvas');this.ctx=this.canvas.getContext('2d');this.zoom=1;this.map=null;this.drag=null;
    new ResizeObserver(()=>this.draw()).observe(this.canvas);
    this.canvas.onwheel=e=>{e.preventDefault();this.scale(e.deltaY<0?1.15:1/1.15);};
    this.canvas.onpointerdown=e=>{if(e.button!==0||!this.map)return;this.drag=[e.pointerId,e.clientX,e.clientY];this.canvas.setPointerCapture(e.pointerId);this.canvas.classList.add('dragging');};
    this.canvas.onpointermove=e=>{if(!this.drag||this.drag[0]!==e.pointerId)return;this.x-=(e.clientX-this.drag[1])/this.cell;this.y-=(e.clientY-this.drag[2])/this.cell;this.drag=[e.pointerId,e.clientX,e.clientY];this.draw();};
    this.canvas.onpointerup=this.canvas.onpointercancel=()=>{this.drag=null;this.canvas.classList.remove('dragging');};
    $('zoom-in').onclick=()=>this.scale(1.3);$('zoom-out').onclick=()=>this.scale(1/1.3);$('fit').onclick=()=>this.fit();
  }
  set(map) {this.map=map;this.fit();}
  fit() {if(!this.map?.grid)return;this.zoom=1;this.x=this.map.grid.width/2;this.y=this.map.grid.height/2;this.draw();}
  scale(value) {this.zoom=Math.max(1,Math.min(10,this.zoom*value));this.draw();}
  draw() {
    const box=this.canvas.getBoundingClientRect(),dpr=Math.min(2,devicePixelRatio||1);
    this.canvas.width=Math.max(1,box.width*dpr);this.canvas.height=Math.max(1,box.height*dpr);
    const c=this.ctx;c.scale(dpr,dpr);c.fillStyle='#151a1d';c.fillRect(0,0,box.width,box.height);
    if(!this.map?.grid?.rows)return;$('empty').hidden=true;
    const {width,height,rows}=this.map.grid;this.cell=Math.min((box.width-36)/width,(box.height-50)/height)*this.zoom;
    this.x=Math.max(0,Math.min(width,this.x));this.y=Math.max(0,Math.min(height,this.y));
    const ox=box.width/2-this.x*this.cell,oy=box.height/2-this.y*this.cell,s=this.cell;
    const palette={'.':'#242e33','#':'#45545b','R':'#75848a','O':'#b9a278'};
    for(let y=Math.max(0,Math.floor(-oy/s));y<Math.min(height,Math.ceil((box.height-oy)/s));y++)for(let x=Math.max(0,Math.floor(-ox/s));x<Math.min(width,Math.ceil((box.width-ox)/s));x++) {
      const ch=rows[y][x];if(ch==='~')continue;c.fillStyle=palette[ch]||'#c76d6d';c.fillRect(ox+x*s,oy+y*s,s,s);
      if(s>=3){c.strokeStyle='#35434a';c.lineWidth=.4;c.strokeRect(ox+x*s,oy+y*s,s,s);}
      if(ch==='O'&&s>5){c.strokeStyle='#746245';c.beginPath();c.moveTo(ox+x*s+1,oy+y*s+1);c.lineTo(ox+(x+1)*s-1,oy+(y+1)*s-1);c.stroke();}
    }
    const parking=new Set((this.map.points?.parking||[]).map(p=>p.join(','))),remaining=new Set(parking);
    c.fillStyle='#b7a9cd';for(const p of parking){const [x,y]=p.split(',').map(Number);c.fillRect(ox+x*s,oy+y*s,s,s);}
    c.strokeStyle='#ddc9ef';c.lineWidth=.75;c.beginPath();
    for(const p of parking){const [x,y]=p.split(',').map(Number);for(const [dx,dy,a,b] of [[-1,0,[x,y],[x,y+1]],[1,0,[x+1,y],[x+1,y+1]],[0,-1,[x,y],[x+1,y]],[0,1,[x,y+1],[x+1,y+1]]])if(!parking.has([x+dx,y+dy].join(','))){c.moveTo(ox+a[0]*s,oy+a[1]*s);c.lineTo(ox+b[0]*s,oy+b[1]*s);}}c.stroke();
    const label=(word,x,y,color)=>{if(s<6)return;c.fillStyle=color;c.font=`600 ${Math.max(7,s*.64)}px Segoe UI,Microsoft YaHei,sans-serif`;c.textAlign='center';c.textBaseline='middle';c.fillText(word,ox+(x+.5)*s,oy+(y+.5)*s);};
    for(const origin of parking){if(!remaining.delete(origin))continue;const queue=[origin];for(let i=0;i<queue.length;i++){const[x,y]=queue[i].split(',').map(Number);for(const q of [[x-1,y],[x+1,y],[x,y-1],[x,y+1]])if(remaining.delete(q.join(',')))queue.push(q.join(','));}const[x,y]=queue[Math.floor(queue.length/2)].split(',').map(Number);label('P',x,y,'#25222d');}
    for(const[kind,color,prefix]of[['pickups','#97c7d7',''],['deliveries','#9bd6b9','D']])this.map.points?.[kind]?.forEach(([x,y],i)=>{c.fillStyle=color;c.fillRect(ox+(x+.1)*s,oy+(y+.1)*s,.8*s,.8*s);label(prefix+(i+1),x,y,'#17262d');});
    (this.map.points?.starts||[]).forEach(([x,y],i)=>{c.fillStyle='#66b9eb';c.beginPath();c.arc(ox+(x+.5)*s,oy+(y+.5)*s,s*.34,0,Math.PI*2);c.fill();if(s>10)label(String(i+1),x,y,'#14232b');});
    this.last={cell:s,origin:[ox,oy],width:box.width,height:box.height};
  }
}
const preview=new Preview();
window.mapStudioInspect=()=>({ready:true,busy,selected,name:current?.name,analysis,grid:current?.grid,view:preview.last});
action(async()=>{await refresh();status('就绪 · 可生成新地图，或载入现有地图。');});
