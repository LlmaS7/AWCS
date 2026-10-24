import { SimulationClient, focusMainWindow } from './client.js';

const $=id=>document.getElementById(id);
let state=null,mapKey='',transient='',transientUntil=0,seedTouched=false;
let mapTouched=false,planningTouched=false;
let countTouched=false,maps=new Map();
const note=message=>{transient=message;transientUntil=performance.now()+4500;};
const client=new SimulationClient({onState:accept,onStatus:controls,onError:note});
const taskName=id=>id===null?'—':'T'+String(id).padStart(3,'0');

function controls() {
  if(!state) return;
  const busy=client.pending>0 || !client.connected;
  for(const id of ['step','random','new-task','auto','save','retry']) $(id).disabled=busy;
  for(const id of ['pause','load','reset','planning-apply']) $(id).disabled=!client.connected;
  $('map-choice').disabled=!client.connected;$('refresh-maps').disabled=busy;
  $('robot-count').disabled=!client.connected || !$('robot-count').options.length;
  $('speed').disabled=busy;$('pause').textContent=state.paused?'继续':'暂停';$('speed').value=String(state.speed);
  $('auto').textContent=state.auto?'自动生成：开':'自动生成：关';$('auto').setAttribute('aria-pressed',String(state.auto));
  $('connection').textContent=!client.connected?'连接中断':state.planning?'规划中':state.paused?'已暂停':'运行中';
  $('connection').classList.toggle('offline',!client.connected);
}
function accept(value,previous) {
  state=value;
  if(previous && value.generation!==previous.generation) {
    $('task-dialog').close();seedTouched=false;mapTouched=false;countTouched=false;
  }
  const key=state.generation+':'+state.map.seed;
  if(key!==mapKey) {
    mapKey=key;
    $('pickup').replaceChildren(...state.map.pickups.map((p,i)=>new Option(`取货点 ${i+1} · (${p})`,i+1)));
    $('delivery').replaceChildren(...state.map.deliveries.map((p,i)=>new Option(`配送点 D${i+1} · (${p})`,i+1)));
  }
  const m=state.metrics;
  const fields={tick:state.tick,seed:state.map.seed,'map-size':`${state.map.width} × ${state.map.height}`,generation:state.generation,revision:state.revision,'visible-total':m.visible_total,'record-total':m.total,replaying:state.replaying?'开':'关','plan-ms':`${m.last_plan_ms.toFixed(1)} ms`,'cbs-nodes':m.cbs_nodes,plans:m.plans,recoveries:m.recovery_attempts,distance:`${m.distance} 格`,waits:`${m.waits} 步`,'avg-completion':`${m.avg_completion.toFixed(1)} 步`,preemptions:`${m.preemptions} 次`};
  Object.entries(fields).forEach(([id,value])=>$(id).textContent=value);
  $('planner').textContent=m.planner==='reservations'?'预约寻路（备用）':m.planner;
  $('reservation-plans').textContent=m.reservation_plans;
  $('cbs-nodes').title=`另有 ${m.reservation_orders||0} 次安全区间预约顺序尝试；不计作CBS节点`;
  if(!seedTouched) $('reset-seed').value=state.map.seed;
  $('map-name').textContent=state.map.name;
  if(!mapTouched) {
    const select=$('map-choice');
    if(![...select.options].some(o=>o.value===state.map.id)) select.add(new Option(`${state.map.name}（当前记录）`,state.map.id));
    select.value=state.map.id;
  }
  countOptions(!countTouched && !mapTouched ? state.robot_count : undefined);
  $('fleet-size').textContent=`${state.robot_count} 台 / 上限 ${state.map.max_robots}`;
  $('assignment-note').textContent=`匹配ETA：${state.assignment.eta_sum ?? 0} 步；${state.assignment.scope||'待规划'}。候选 ${state.assignment.candidate_count||0}；不是在线全局最优。`;
  if(!planningTouched) { $('planner-mode').value=state.planning_profile.mode;$('coupling-mode').value=state.planning_profile.coupling;$('plan-budget').value=state.planning_profile.seconds; }
  const topology=state.map.topology;
  $('topology-info').textContent=topology?`可通行 ${topology.free_cells} 格 · 割点 ${topology.cutpoints} · 走廊 ${topology.corridors} · 死胡同 ${topology.dead_ends}；不是多机可解证明。`:'';
  $('robot-data').innerHTML=state.robots.map(r=>`<tr><td>R${r.id}</td><td>(${r.position})</td><td>${r.label}</td><td>${taskName(r.task_id)}</td><td>${taskName(r.next_task_id)}</td><td>${Math.max(0,r.path.length-1)}</td><td>${r.loaded?'是':'否'}</td></tr>`).join('');
  controls();
}
$('pause').onclick=()=>client.command('pause',{paused:!state.paused});
$('step').onclick=()=>client.command('step');
$('speed').onchange=()=>client.command('speed',{value:Number($('speed').value)});
$('random').onclick=()=>client.command('random');
$('auto').onclick=()=>client.command('auto',{enabled:!state.auto});
$('save').onclick=()=>client.command('save');
$('load').onclick=()=>client.command('load');
$('retry').onclick=()=>client.command('retry');
$('reset-seed').oninput=()=>seedTouched=true;
$('robot-count').onchange=()=>countTouched=true;
function countOptions(requested) {
  const id=$('map-choice').value;
  const definition=maps.get(id) || (id===state?.map.id?state.map:null);
  const max=definition?.max_robots || 0,input=$('robot-count');
  const current=requested ?? (input.value?Number(input.value):definition?.default_robots || 3);
  if(input.options.length!==max) input.replaceChildren(...Array.from({length:max},(_,i)=>new Option(`${i+1} 台`,i+1)));
  if(max) input.value=String(Math.max(1,Math.min(max,current)));
  $('robot-limit').textContent=max?`本地图上限：${max} 台`:'请选择有效地图';
}
$('map-choice').onchange=()=>{mapTouched=true;countTouched=true;countOptions();};
async function refreshMaps() {
  try {
    const response=await fetch('/api/maps',{cache:'no-store'});
    if(!response.ok) throw new Error('无法读取地图列表');
    const responseMaps=(await response.json()).maps,select=$('map-choice'),value=select.value;
    maps=new Map(responseMaps.map(m=>[m.id,m]));
    select.replaceChildren(...responseMaps.map(m=>{
      const option=new Option(m.available?`${m.name} · ${m.width}×${m.height}`:`${m.name} · 格式错误`,m.id);
      option.disabled=!m.available;option.title=m.error || '';return option;
    }));
    if([...select.options].some(o=>o.value===(mapTouched?value:state?.map.id))) select.value=mapTouched?value:state.map.id;
    const errors=responseMaps.filter(m=>!m.available);
    $('map-errors').textContent=errors.map(m=>`${m.id}：${m.error}`).join('；');
    $('map-errors').hidden=!errors.length;
    countOptions();controls();
  } catch(e) {note(e.message);}
}
$('refresh-maps').onclick=refreshMaps;
$('map-studio').onclick=()=>{
  const child=window.open('./map-studio','awcs-map-studio','width=1440,height=960');
  if(!child) note('地图工坊窗口被拦截，请允许本机页面打开窗口，或使用 map_studio/launch.bat。');
};
$('reset').onclick=()=>{
  const input=$('reset-seed');
  if(!input.checkValidity() || input.value==='') {input.reportValidity();note('请输入合法的地图种子');return;}
  if(!$('map-choice').value) {note('请先选择有效地图');return;}
  const count=Number($('robot-count').value);
  if(!Number.isInteger(count) || count<1) {note('请选择机器人数量');return;}
  client.command('reset',{seed:Number(input.value),map_id:$('map-choice').value,robot_count:count});
};
$('focus-main').onclick=async()=>{try{await focusMainWindow();}catch(e){note(e.message);}};
$('new-task').onclick=async()=>{if(await client.command('pause',{paused:true})) $('task-dialog').showModal();};
$('close-dialog').onclick=$('back-dialog').onclick=()=>$('task-dialog').close();
$('task-form').onsubmit=async e=>{e.preventDefault();if(await client.command('add',{pickup:Number($('pickup').value),delivery:Number($('delivery').value),priority:Number($('priority').value)})) $('task-dialog').close();};
document.addEventListener('keydown',e=>{
  if($('task-dialog').open || ['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName) || client.pending || !client.connected || e.ctrlKey || e.altKey || e.metaKey) return;
  const actions={n:'step',a:'random',r:'retry',s:'save'};
  if(e.code==='Space') {e.preventDefault();$('pause').click();}
  else if(actions[e.key.toLowerCase()]) $(actions[e.key.toLowerCase()]).click();
});
setInterval(()=>{if(state) $('status-message').textContent=performance.now()<transientUntil?transient:!client.connected?'连接中断，等待恢复':state.message;},120);
window.debugInspect=()=>({ready:!!state,tick:state?.tick,seed:state?.map.seed,robotCount:state?.robot_count,mapId:state?.map.id,maxRobots:state?.map.max_robots,generation:state?.generation,revision:state?.revision,paused:state?.paused,auto:state?.auto,taskIds:state?.tasks.map(t=>t.id) || []});
client.poll();refreshMaps();

for(const id of ['planner-mode','coupling-mode','plan-budget']) $(id).onchange=()=>planningTouched=true;
$('planning-apply').onclick=async()=>{if(await client.command('planning',{mode:$('planner-mode').value,coupling:$('coupling-mode').value,seconds:Number($('plan-budget').value)})) planningTouched=false;};
