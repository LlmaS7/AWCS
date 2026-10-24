import { Map2D } from './map2d.js';
import { Scene3D } from './scene3d.js';
import { SimulationClient, openDebugWindow } from './client.js';
import { robotColor } from './robot-colors.js';
import { Chat } from './chat.js';
import { Settings } from './settings.js';

const $=id=>document.getElementById(id);
const map2d=new Map2D($('map2d')),scene3d=new Scene3D($('scene3d'));
let state=null,selected=null,selectionInitialized=false,filter='all',signature='',mapKey='';
let transient='',transientUntil=0,positions={};
let robotSignature='',legendCount=0;
const finished=t=>t.status==='completed';
const taskName=id=>'T'+String(id).padStart(3,'0');
const chosen=()=>state?.tasks.find(t=>t.id===selected) || null;
const filtered=()=>state.tasks.filter(t=>filter==='all' || (filter==='completed'?finished(t):!finished(t)));
const toast=message=>{transient=message;transientUntil=performance.now()+4500;};
const client=new SimulationClient({onState:accept,onStatus:controls,onError:toast});
window.name='sditadc-main';
const switchTab=tab=>{for(const name of ['tasks','chat']) {$('tab-'+name).classList.toggle('active',name===tab);$('tab-'+name).setAttribute('aria-selected',String(name===tab));$(name==='tasks'?'task-content':'chat-content').hidden=name!==tab;}};
const settings=new Settings();
const chat=new Chat({state:()=>state,selected:()=>selected,unlink:()=>{selected=null;selectionInitialized=true;renderTasks();},select:(id,generation)=>{if(state?.generation!==generation)return;selected=id;selectionInitialized=true;filter='all';document.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('active',b.dataset.filter==='all'));switchTab('tasks');renderTasks();},settings});
const sourceDetail=document.createElement('div');sourceDetail.id='detail-source';sourceDetail.hidden=true;$('detail-note').after(sourceDetail);
$('tab-tasks').onclick=()=>switchTab('tasks');$('tab-chat').onclick=()=>switchTab('chat');

function controls() {
  if(!state) return;
  const busy=client.pending>0 || !client.connected,t=chosen();
  $('pause').disabled=!client.connected;$('speed').disabled=!client.connected;
  $('pause').textContent=state.paused?'继续':'暂停';$('speed').value=String(state.speed);
  $('raise').disabled=busy || !t || finished(t) || t.priority===5;
  $('urgent').disabled=$('raise').disabled;
  $('cancel').disabled=!client.connected || !t || !['pending','reserved','to_pickup'].includes(t.status);
}

function renderTasks() {
  if(!state) return;
  const list=filtered();
  if(!selectionInitialized) {selected=list[0]?.id ?? null;selectionInitialized=true;}
  if(selected!==null && !list.some(t=>t.id===selected)) selected=list[0]?.id ?? null;
  const nextSignature=JSON.stringify([filter,selected,list]);
  if(nextSignature!==signature) {
    signature=nextSignature;
    const scroll=$('tasks').scrollTop,fragment=document.createDocumentFragment();
    for(const t of list) {
      const row=document.createElement('button');
      row.className='task-card'+(t.id===selected?' selected':'');row.dataset.taskId=t.id;
      row.setAttribute('aria-label',`${taskName(t.id)} ${t.label}`);
      row.innerHTML=`<span class="task-top"><span class="task-id">${taskName(t.id)} <span class="priority-tag${t.priority===5?' urgent':''}">${t.priority===5?'紧急':'等级 '+t.priority}</span></span><span class="task-owner">${t.label}${t.robot_id?' · R'+t.robot_id:''}</span></span><span class="task-route">取货点 ${String(t.pickup_number).padStart(2,'0')} → 配送点 D${t.delivery_number}</span>`;
      if(t.assignment_mode!=='auto'&&t.assignment_robot_id){const policy=document.createElement('span');policy.className='subtle';policy.textContent=`${t.assignment_mode==='forced'?'人工指定':'优先使用'} R${t.assignment_robot_id}`;row.append(policy);}
      fragment.append(row);
    }
    if(!list.length) {const p=document.createElement('p');p.className='empty';p.textContent='当前筛选下没有任务';fragment.append(p);}
    $('tasks').replaceChildren(fragment);$('tasks').scrollTop=scroll;
  }
  const t=chosen();
  $('detail-title').textContent=t?`${taskName(t.id)} · ${t.label}`:'选择一个任务';
  $('detail-route').textContent=t?`取货点 ${t.pickup_number} → 配送点 D${t.delivery_number}`:'点击任务查看其取送位置';
  const policy=t?.assignment_mode==='forced'?`人工指定 R${t.assignment_robot_id}`:t?.assignment_mode==='preferred'?`优先使用 R${t.assignment_robot_id}，可由其他机器人接手`:'';
  const stage=t?.status==='reserved'?`R${t.robot_id} 完成当前搬运后接手`:t?.status==='pending'&&t.priority===5?'暂无立即可用的机器人，等待安全接手':t?'地图高亮所选任务的取货与配送位置':'';
  $('detail-note').textContent=[policy,stage].filter(Boolean).join(' · ');
  sourceDetail.hidden=!t?.source;
  const sourceSignature=JSON.stringify(t?.source||null);
  if(sourceSignature!==sourceDetail.dataset.signature){sourceDetail.dataset.signature=sourceSignature;sourceDetail.replaceChildren();if(t?.source){const source=t.source,p=document.createElement('p');p.className='subtle';p.textContent=`来源：${source.filename} · ${source.candidate_id} 第${source.occurrence_index}次${source.human_edited?' · 已人工修改':''}`;const b=document.createElement('button');b.className='text-button';b.textContent='查看文件来源';b.onclick=()=>chat.imports.openSource(source);sourceDetail.append(p,b);}}
  scene3d.highlight(t);controls();
  chat.updateAssociation();
}

function accept(value,previous) {
  state=value;
  if(previous && value.generation!==previous.generation) {
    selected=null;selectionInitialized=true;signature='';filter='all';
    document.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('active',b.dataset.filter==='all'));
  }
  const key=state.generation+':'+state.map.seed;
  if(key!==mapKey) {mapKey=key;map2d.setMap(state.map);scene3d.setMap(state.map);}
  $('overview-completed').textContent=state.metrics.completed;
  $('overview-running').textContent=state.robots.filter(r=>r.task_id!==null).length;
  $('overview-pending').textContent=state.metrics.pending;
  $('task-count').textContent=state.metrics.visible_total;
  $('completed-count').textContent=`完成 ${state.metrics.completed} / ${state.metrics.visible_total}`;
  const nextRobots=JSON.stringify(state.robots.map(r=>[r.id,r.phase,r.task_id,r.next_task_id,r.completed,r.loaded]));
  if(nextRobots!==robotSignature) {
    robotSignature=nextRobots;
    $('robots').innerHTML=state.robots.map(r=>`<article class="robot-card"><h3><span style="color:${robotColor(r.id)}">R${r.id}</span><span>${r.label}</span></h3><p>${r.task_id?taskName(r.task_id):'等待接单'}${r.next_task_id?' · 随后 '+taskName(r.next_task_id):''}</p><p>已完成 ${r.completed} 项${r.loaded?' · 已载货':''}</p></article>`).join('');
  }
  $('fleet-summary').textContent=`${state.robots.length} 台机器人 · 单件搬运`;
  if(legendCount!==state.robots.length) {
    legendCount=state.robots.length;
    $('robot-legend').innerHTML=state.robots.map(r=>`<span class="robot-key"><i class="dot" style="background:${robotColor(r.id)}"></i> R${r.id}</span>`).join('')+'<span class="legend-note">货架 · 作业点 · 路线</span>';
  }
  renderTasks();scene3d.update(state,chosen());
}

$('pause').onclick=()=>client.command('pause',{paused:!state.paused});
$('speed').onchange=()=>client.command('speed',{value:Number($('speed').value)});
$('debug-window').onclick=async()=>{try{await openDebugWindow();}catch(e){toast(e.message);}};
$('recenter').onclick=()=>scene3d.recenter();
$('recenter-2d').onclick=()=>map2d.recenter();
$('raise').onclick=()=>{const t=chosen();if(t) client.command('priority',{task_id:t.id,priority:t.priority+1});};
$('urgent').onclick=()=>{const t=chosen();if(t) client.command('priority',{task_id:t.id,priority:5});};
$('cancel').onclick=()=>{const t=chosen();if(t) client.command('cancel',{task_id:t.id});};
$('clear-selection').onclick=()=>{selected=null;selectionInitialized=true;renderTasks();};
$('tasks').onclick=e=>{const row=e.target.closest('[data-task-id]');if(row){selected=Number(row.dataset.taskId);selectionInitialized=true;renderTasks();}};
document.querySelectorAll('[data-filter]').forEach(button=>button.onclick=()=>{filter=button.dataset.filter;$('tasks').scrollTop=0;document.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('active',b===button));renderTasks();});
document.addEventListener('keydown',e=>{
  if(document.querySelector('dialog[open]') || ['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName) || client.pending || !client.connected || e.ctrlKey || e.altKey || e.metaKey) return;
  if(e.code==='Space') {e.preventDefault();$('pause').click();}
});

function renderFrame() {
  if(!state) return;
  const alpha=state.paused || state.planning || !client.connected?1:Math.min(1,(state.seconds_since_step+(performance.now()-client.receivedAt)/1000)*state.speed);
  positions=Object.fromEntries(state.robots.map(r=>[r.id,[r.previous[0]+(r.position[0]-r.previous[0])*alpha,r.previous[1]+(r.position[1]-r.previous[1])*alpha]]));
  map2d.draw(state,positions,chosen());scene3d.draw(state,positions);
  $('connection').textContent=!client.connected?'连接中断':state.planning?'路线更新中':state.paused?'已暂停':'运行中';
  $('connection').classList.toggle('offline',!client.connected);
  const failed=/安全暂停|连续无执行进展/.test(state.message);
  $('status-message').textContent=performance.now()<transientUntil?transient:!client.connected?'连接中断，画面保留最后状态':failed?'路线暂时不可用，系统已暂停。可在调试窗口查看详情。':state.message;
}
function animate(){renderFrame();requestAnimationFrame(animate);}
window.previewDebug={inspect:()=>{renderFrame();return {ready:!!state,mapId:state?.map.id,mapSize:state?[state.map.width,state.map.height]:null,tick:state?.tick,generation:state?.generation,viewTicks:[$('map2d').dataset.tick,$('scene3d').dataset.tick],map2d:map2d.inspect(),...scene3d.inspect(),canvas2d:Object.entries(positions).map(([id,p])=>({id:Number(id),x:p[0],y:p[1]})),taskIds:state?.tasks.map(t=>t.id) || []};}};
client.poll();animate();
