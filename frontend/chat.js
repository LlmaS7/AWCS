import {api} from './settings.js';
import {Imports} from './imports.js';
const $=id=>document.getElementById(id);
const names={get_status:'查询业务状态',get_locations:'查询作业点',create_tasks:'创建任务',raise_task_priorities:'提升优先级',cancel_tasks:'取消任务',get_metrics:'查询业务指标',assign_task:'指定执行',release_task_assignment:'解除指定',set_task_preference:'设置软偏好',copy_task:'复制任务'};
const outcomes={applied:'已生效',no_change:'无需改变',rejected:'未能执行',not_executed:'未执行'};
export class Chat {
  constructor(options){
    Object.assign(this,options);this.cursor=0;this.rows=new Map();this.busy=false;this.submitting=false;this.request=null;this.ready=false;
    this.settings.onChange=v=>this.configure(v);
    $('chat-send').onclick=()=>this.send();$('chat-stop').onclick=()=>api('stop',{request_id:this.request}).catch(e=>this.notice(e.message));
    $('chat-clear').onclick=()=>api('clear',{}).catch(e=>this.notice(e.message));$('chat-unlink').onclick=()=>this.unlink();
    $('chat-input').oninput=()=>this.controls();$('chat-input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();if(!$('chat-send').disabled)this.send();}};
    this.imports=new Imports(this);
    this.settings.refresh().catch(()=>{});this.poll();
  }
  configure(v){this.ready=v.has_key&&!!v.model;$('ai-status').textContent=v.has_key?(v.model?`${v.model} · ${v.verified?'已验证':'未验证'}`:'请选择模型'):'先配置 DeepSeek，即可使用';this.controls();}
  controls(){const attached=this.imports?.pendingInput;const localBusy=this.imports?.loading;$('chat-send').textContent=attached?'分析文件':'发送';$('chat-send').disabled=this.busy||this.submitting||localBusy||!this.ready||!this.state()||(!attached&&!$('chat-input').value.trim())||(attached&&!this.imports.canAnalyze);$('chat-stop').disabled=!this.busy;this.imports?.controls();}
  updateAssociation(){
    const state=this.state(),task=state?.tasks.find(t=>t.id===this.selected());
    const signature=JSON.stringify([state?.generation,task?[task.id,task.status,task.label,task.priority,task.pickup_number,task.delivery_number,task.robot_id,task.assignment_mode,task.assignment_robot_id]:null]);
    if(signature!==this.associationSignature){
      this.associationSignature=signature;
      $('chat-association').textContent=task?`当前关联：T${String(task.id).padStart(3,'0')}`:'未关联任务';
      $('chat-unlink').disabled=!task;
      $('chat-task-summary').hidden=!task;$('chat-task-empty').hidden=!!task;
      $('chat-task-status').textContent=task?.label||'';
      $('chat-task-priority').textContent=task?(task.priority===5?'紧急 · 5级':`等级 ${task.priority}`):'';
      $('chat-task-priority').classList.toggle('urgent',task?.priority===5);
      $('chat-task-route').textContent=task?`取货点 ${String(task.pickup_number).padStart(2,'0')} → 配送点 D${task.delivery_number}`:'';
      const owner=task?.robot_id?`${task.status==='reserved'?'预约接手':task.status==='completed'?'完成机器人':'执行机器人'}：R${task.robot_id}`:'尚未分配机器人';
      const policy=task?.assignment_mode==='forced'?`人工指定 R${task.assignment_robot_id}`:task?.assignment_mode==='preferred'?`优先使用 R${task.assignment_robot_id}`:'自动分配';
      $('chat-task-meta').textContent=task?`${owner} · ${policy}`:'';
    }
    this.controls();
  }
  append(className,text){const p=document.createElement('div');p.className=className;p.textContent=text;$('chat-messages').append(p);return p;}
  notice(text){this.append('chat-notice',text);}
  async send(){const state=this.state();if(!state||this.busy||this.submitting)return;if(this.imports.pendingInput)return this.imports.analyze();const text=$('chat-input').value.trim();if(!text)return;this.busy=true;this.submitting=true;this.controls();try{await api('messages',{text,task_id:this.selected(),generation:state.generation});if($('chat-input').value.trim()===text)$('chat-input').value='';}catch(e){this.busy=false;this.notice(e.message);}finally{this.submitting=false;this.controls();}}
  row(e){let row=this.rows.get(e.request_id);if(!row){const article=document.createElement('article');article.className='chat-reply';const progress=document.createElement('p');progress.className='subtle';const text=document.createElement('div');text.className='chat-text';const results=document.createElement('div');results.className='chat-results';article.append(progress,text,results);$('chat-messages').append(article);row={article,progress,text,results,generation:e.generation};this.rows.set(e.request_id,row);}return row;}
  event(e){
    this.imports.event(e);
    if(e.kind==='clear'){$('chat-messages').replaceChildren();this.rows.clear();return;}
    if(e.kind==='context'){this.notice(e.message);return;}
    if(e.kind==='start'){
      this.settings.value&&(this.settings.value.request_id=e.request_id);this.request=e.request_id;
      if(e.job==='message'){document.querySelector('.chat-welcome')?.remove();this.append('chat-user',e.text);const row=this.row(e);row.progress.textContent='正在处理…';}
      else if(e.job?.startsWith('import_')){document.querySelector('.chat-welcome')?.remove();this.append('chat-user',`${e.job==='import_extract'?'分析文件':'确认创建'}：${e.filename}`);this.row(e).progress.textContent=e.job==='import_extract'?'正在分析文件；尚未创建任务':'正在逐项创建并规划路线';}
      else this.settings.message(e.job==='models'?'正在获取模型…':'正在测试连接与只读工具…');
      return;
    }
    this.settings.event(e);
    const row=this.rows.get(e.request_id);
    if(e.kind==='text'&&row)row.text.textContent+=e.text;
    if(e.kind==='progress'&&row)row.progress.textContent=names[e.tool]||'正在处理业务请求';
    if(e.kind==='import_progress'&&row)row.progress.textContent=e.stage+(e.total?` · ${e.completed}/${e.total}`:'');
    if(e.kind==='import_ready'&&row){row.progress.textContent=`已提取 ${e.count} 条需求，等待检查确认`;const b=document.createElement('button');b.className='small';b.textContent='查看任务草稿';b.onclick=()=>this.imports.open();row.results.append(b);}
    if(e.kind==='result'&&row){
      row.progress.textContent='业务结果已返回';
      if(e.result.error){const p=document.createElement('p');p.className='result-error';p.textContent=e.result.error;row.results.append(p);}
      for(const item of e.result.actions||[]){const card=document.createElement('div');card.className='result-card '+(item.outcome==='applied'?'success':'');const title=document.createElement('strong');title.textContent=`${names[e.tool]||'业务操作'} · ${outcomes[item.outcome]||item.outcome}`;card.append(title);
        if(item.task_id){const b=document.createElement('button');b.className='text-button task-link';b.textContent=item.task_id;b.onclick=()=>this.select(Number(item.task_id.slice(1)),e.generation);card.append(b);}
        if(item.pickup_label&&item.delivery_name){const route=document.createElement('p');route.textContent=`${item.pickup_label} → ${item.delivery_name}`;card.append(route);}
        const detail=document.createElement('p');detail.textContent=[item.phase_label,item.assigned_robot,item.priority?`等级 ${item.priority}`:'',item.planning==='available'?'路线可用':item.planning==='unavailable'?'路线暂不可用':'',item.assignment_mode!=='auto'&&item.requested_robot?`${item.assignment_label} ${item.requested_robot}`:'',item.copied_from?`复制自 ${item.copied_from}`:'',item.reason].filter(Boolean).join(' · ');card.append(detail);row.results.append(card);}
    }
    if(['notice','error'].includes(e.kind)){if(row){const p=document.createElement('p');p.className=e.kind==='error'?'result-error':'chat-notice';p.textContent=e.message;row.article.append(p);}else if(!e.request_id)this.notice(e.message);}
    if(e.kind==='done'&&row)row.progress.textContent='本轮处理结束 · 操作以结果卡为准';
  }
  async poll(){try{const v=await api('events?after='+this.cursor);const area=$('chat-messages');const nearBottom=area.scrollHeight-area.scrollTop-area.clientHeight<70;for(const e of v.events)this.event(e);if(v.gap)this.notice('部分旧消息已超出本次显示缓存；当前任务以任务列表为准');this.cursor=v.cursor;this.busy=v.busy;this.request=v.request_id;this.settings.status(v);if(nearBottom)area.scrollTop=area.scrollHeight;this.controls();if(v.events.some(e=>['done','context'].includes(e.kind)))this.settings.refresh().catch(()=>{});}catch{this.controls();}finally{setTimeout(()=>this.poll(),180);}}
}
