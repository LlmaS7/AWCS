import {api} from './settings.js';
const $=id=>document.getElementById(id);
const node=(tag,className,text)=>{const n=document.createElement(tag);if(className)n.className=className;if(text!==undefined)n.textContent=text;return n;};
const locatorText=l=>l.type==='text_line'?`第${l.line}行`:l.type==='docx_paragraph'?`正文第${l.paragraph}段`:l.type==='docx_table'?`表格${l.table} · 第${l.row}行第${l.column}列${l.parent?'（嵌套）':''}`:'本次附件说明';

export class Imports {
  constructor(chat){
    this.chat=chat;this.draft=null;this.loading=false;this.selection=new Set();this.counts=new Map();this.page=0;this.pendingConfirmation=null;this.quantityErrors=new Set();this.liveAnalysis=null;this.syncEpoch=0;this.hiddenDraft=null;this.completedRevision=null;
    $('import-add').onclick=()=>$('import-file').click();
    $('import-file').onchange=()=>this.choose($('import-file').files[0]);
    $('import-remove').onclick=()=>this.discard();
    $('import-dismiss').onclick=()=>this.dismiss();
    $('import-history').onclick=()=>this.pendingInput?this.showAttachment():this.open();
    $('import-open').onclick=()=>this.open();
    $('import-close').onclick=$('import-collapse').onclick=()=>$('import-dialog').close();
    $('import-reimport').onchange=()=>chat.controls();
    $('import-select-ready').onclick=()=>this.selectReady();
    $('import-unselect').onclick=()=>{this.selection.clear();this.render();};
    $('import-commit').onclick=()=>this.commit();
    $('import-refresh').onclick=()=>this.verify();
    this.retryButton=node('button','small','重发同次确认');this.retryButton.hidden=true;
    this.retryButton.onclick=()=>this.retryConfirmation();$('import-refresh').after(this.retryButton);
    const pagination=node('div','import-pagination');
    this.prev=node('button','small','上一页');this.next=node('button','small','下一页');this.pageLabel=node('span','subtle');
    this.prev.onclick=()=>{this.page--;this.renderTable();};this.next.onclick=()=>{this.page++;this.renderTable();};
    pagination.append(this.prev,this.pageLabel,this.next);$('import-rows').closest('.import-table-wrap').after(pagination);
    this.bindFileDrop();
    this.refresh().catch(()=>{});
  }
  get pendingInput(){return ['uploaded','error'].includes(this.draft?.state);}
  get canAnalyze(){return !this.draft?.duplicates.length||$('import-reimport').checked;}
  get uploadBlocked(){
    if(this.loading||this.chat.busy||this.chat.submitting)return '请等待当前请求完成后再导入文件';
    return this.chat.state()?'':'场景尚未就绪，请稍后再导入文件';
  }
  bindFileDrop(){
    const area=$('chat-content'),hint=$('import-drop-hint');let depth=0;
    const hasFiles=e=>Array.from(e.dataTransfer?.types||[]).includes('Files');
    const inside=e=>!area.hidden&&area.contains(e.target);
    const reset=()=>{depth=0;hint.hidden=true;area.classList.remove('import-dragover');};
    const show=()=>{
      const blocked=this.uploadBlocked;
      $('import-drop-label').textContent=blocked||'松开以导入文件';
      hint.classList.toggle('import-drop-blocked',!!blocked);
      hint.hidden=false;area.classList.add('import-dragover');
    };
    // Prevent file drops anywhere from navigating away from the running app.
    // Only file drags are intercepted; ordinary text dragging keeps its behavior.
    document.addEventListener('dragenter',e=>{
      if(hasFiles(e)&&inside(e)){depth++;show();}
    });
    document.addEventListener('dragover',e=>{
      if(!hasFiles(e))return;
      e.preventDefault();
      const accepted=inside(e);
      e.dataTransfer.dropEffect=accepted&&!this.uploadBlocked?'copy':'none';
      if(accepted)show();else reset();
    });
    document.addEventListener('dragleave',e=>{
      if(inside(e)&&depth>0&&--depth===0)reset();
    });
    document.addEventListener('drop',e=>{
      if(!hasFiles(e))return;
      e.preventDefault();reset();
      if(!inside(e))return;
      if(this.uploadBlocked){this.error(this.uploadBlocked,false);return;}
      const items=Array.from(e.dataTransfer.items||[]);
      if(items.some(item=>item.webkitGetAsEntry?.()?.isDirectory)){
        this.error('暂不支持导入文件夹，请拖入一个 MD、TXT 或 DOCX 文件。',false);return;
      }
      const files=Array.from(e.dataTransfer.files||[]);
      if(files.length!==1){this.error('每次仅支持导入一个文件，请重新拖入。',false);return;}
      this.choose(files[0]);
    });
    document.addEventListener('dragend',reset);
    window.addEventListener('blur',reset);
  }
  controls(){
    const busy=this.loading||this.chat.busy||this.chat.submitting;
    $('import-add').disabled=!!this.uploadBlocked;$('import-file').disabled=$('import-add').disabled;
    $('import-remove').disabled=busy;$('import-refresh').disabled=this.loading;
    this.retryButton.disabled=busy;
    $('import-select-ready').disabled=busy||this.draft?.state!=='ready';
    const selected=this.selected();const total=selected.reduce((n,s)=>n+s.count,0);
    const eligible=selected.every(s=>!this.quantityErrors.has(s.candidate_id)&&this.draft?.candidates.find(r=>r.candidate_id===s.candidate_id)?.ready);
    $('import-commit').disabled=busy||this.draft?.state!=='ready'||!eligible||!total||total>20||!!this.pendingConfirmation;
    $('import-commit').textContent=total?`确认创建 ${total} 项任务`:'确认创建';
    $('import-selection-count').textContent=total?`已选择 ${selected.length} 条需求，本次创建 ${total} 项任务${total>20?'，超过20项上限':''}`:'未选择任务';
  }
  error(message,modal=$('import-dialog').open){
    const target=$(modal?'import-error':'import-compose-error');target.textContent=message;target.hidden=!message;
    if(message&&modal)target.focus();
  }
  async refresh(){
    if(this.refreshing)return this.refreshing;
    this.refreshing=(async()=>{for(;;){const epoch=this.syncEpoch;const v=await api('imports/draft');if(epoch===this.syncEpoch){this.setDraft(v.draft);return v.draft;}}})().finally(()=>{this.refreshing=null;});
    return this.refreshing;
  }
  isComplete(d=this.draft){
    return !!d&&d.state==='ready'&&d.operations.length>0&&d.operations.every(op=>op.status==='finished')
      &&d.candidates.some(row=>row.created_count>0)&&d.candidates.every(row=>!row.reserved_count&&(row.deleted||(row.count!==null&&row.remaining===0)));
  }
  dismiss(){
    if(!this.draft)return;
    this.hiddenDraft=this.draft.draft_id;$('import-dialog').close();this.render();this.chat.controls();
  }
  showAttachment(){this.hiddenDraft=null;this.render();this.chat.controls();}
  setDraft(d){
    if(this.draft?.draft_id!==d?.draft_id){this.hiddenDraft=null;this.completedRevision=null;this.selection.clear();this.counts.clear();this.quantityErrors.clear();this.page=0;$('import-reimport').checked=false;$('import-source').hidden=true;$('import-source-content').replaceChildren();}
    this.draft=d;
    // Hide each completed revision once; explicit reopening survives later refreshes.
    const completed=this.isComplete(d)?`${d.draft_id}:${d.revision}`:null;
    if(completed&&completed!==this.completedRevision)this.hiddenDraft=d.draft_id;
    this.completedRevision=completed;
    if(d){for(const row of d.candidates){if(!row.ready)this.selection.delete(row.candidate_id);const old=this.counts.get(row.candidate_id);this.counts.set(row.candidate_id,Math.min(old||20,row.remaining||0,20));}}
    this.render();this.chat.controls();
  }
  async choose(file){
    $('import-file').value='';if(!file)return;
    if(this.uploadBlocked){this.error(this.uploadBlocked,false);return;}
    const extension=file.name.split('.').pop().toLowerCase(),limit=extension==='docx'?10*1024**2:1024**2;
    if(!['md','txt','docx'].includes(extension)||!file.size||file.size>limit){this.error('请选择 MD/TXT（≤1 MiB）或 DOCX（≤10 MiB）文件。');return;}
    if(this.draft&&!await this.discard(true))return;
    if(this.uploadBlocked){this.error(this.uploadBlocked,false);return;}
    this.syncEpoch++;this.loading=true;this.chat.controls();this.error('');
    try{
      const response=await fetch('/api/ai/imports/upload',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Import-Filename':encodeURIComponent(file.name),'X-Scene-Generation':String(this.chat.state().generation)},body:file});
      const v=await response.json();if(!response.ok)throw new Error(v.error||'读取文件失败');
      this.syncEpoch++;this.setDraft(v.draft);
      this.chat.notice(`已读取附件：${file.name}。提取文本将发送至当前 AI 服务，确认前不会创建任务。`);
    }catch(e){this.error(e.message,false);await this.refresh().catch(()=>{});}
    finally{this.loading=false;this.chat.controls();}
  }
  async discard(replacing=false){
    if(!this.draft)return true;
    if(!this.isComplete()&&!window.confirm(replacing?'放弃当前附件及未提交草稿，改为导入新文件？已创建任务会保留。':'放弃当前附件及未提交草稿？已创建任务和防重复记录会保留。'))return false;
    this.loading=true;this.chat.controls();
    try{await api('imports/discard',{draft_id:this.draft.draft_id});this.syncEpoch++;this.setDraft(null);this.pendingConfirmation=null;return true;}
    catch(e){this.error(e.message);return false;}
    finally{this.loading=false;this.chat.controls();}
  }
  async analyze(){
    if(!this.pendingInput||!this.canAnalyze)return;
    const instruction=$('chat-input').value.trim();
    this.chat.submitting=true;this.chat.busy=true;this.chat.controls();this.error('');
    try{const request=await api('imports/analyze',{document_id:this.draft.document_id,generation:this.chat.state().generation,instruction,reimport_ack:$('import-reimport').checked});this.liveAnalysis=request.request_id;if($('chat-input').value.trim()===instruction)$('chat-input').value='';await this.refresh();}
    catch(e){this.chat.busy=false;this.error(e.message,false);await this.refresh().catch(()=>{});}
    finally{this.chat.submitting=false;this.chat.controls();}
  }
  async open(){try{await this.refresh();if(!this.draft)throw new Error('草稿已清除，请重新导入');this.showAttachment();if(!$('import-dialog').open)$('import-dialog').showModal();}catch(e){this.error(e.message,false);}}
  async openSource(source){
    await this.refresh().catch(()=>{});
    if(this.draft?.document_id!==source.import_batch_id){this.chat.notice(`来源：${source.filename} · ${source.locators.map(locatorText).join('；')}。原文未保存或已释放。`);return;}
    await this.open();
    const row=this.draft.candidates.find(r=>r.candidate_id===source.candidate_id);
    if(row)await this.showSource(row.source_ids);
  }
  statusText(d){
    const states={uploaded:'已读取，可填写说明后分析',analyzing:'正在分析，确认前不会创建任务',submitting:'正在提交，请等待逐项回执',invalid:'场景已变化，草稿只读；请重新导入',error:d.error||'分析未完成，请重试'};
    if(!['ready','submitting'].includes(d.state))return states[d.state]||d.state;
    const created=d.candidates.reduce((n,row)=>n+row.created_count,0);
    if(d.operations.some(op=>op.status==='unknown')||(d.state==='ready'&&d.candidates.some(row=>row.reserved_count>0)))return `创建结果待核实，已确认创建 ${created} 项；请先核实结果，勿重复创建`;
    if(d.state==='submitting')return states.submitting;
    const remaining=d.candidates.filter(row=>!row.deleted&&(row.count===null||row.remaining>0));
    if(!remaining.length)return created?`已全部创建，共 ${created} 项任务`:'当前无待创建任务，请核对原文与排除说明';
    if(created){
      const count=remaining.reduce((n,row)=>n+row.remaining,0);
      return `已创建 ${created} 项任务，${remaining.some(row=>row.count===null)?'剩余需求待补充、检查确认':`剩余 ${count} 项待检查确认`}`;
    }
    return d.operations.length?'尚未创建任务，请查看结果后重新检查确认':'草稿已就绪，等待检查确认';
  }
  render(){
    const d=this.draft;$('import-attachment').hidden=!d||this.hiddenDraft===d.draft_id;
    $('import-history').hidden=!d||!$('import-attachment').hidden;
    $('import-history').textContent=this.pendingInput?'查看附件':'导入记录';
    if(!d){$('import-dialog').close();for(const id of ['import-rows','import-excluded-content','import-result-content','import-warnings'])$(id).replaceChildren();$('import-document-note').textContent='';this.controls();return;}
    $('import-filename').textContent=d.filename;
    const status=this.statusText(d);
    $('import-attachment-status').textContent=status;
    $('import-duplicates').hidden=!this.pendingInput||!d.duplicates.length;
    const previous=$('import-previous');previous.replaceChildren();
    for(const entry of d.duplicates){const p=node('p','subtle',`${entry.filename} · 场景${entry.generation}${entry.submissions.length?' · 已有提交记录':' · 未创建任务'}`);for(const id of entry.submissions){const b=node('button','text-button','查看原结果');b.onclick=async()=>{try{const op=await api('imports/operation?id='+encodeURIComponent(id));this.renderResults([op]);if(!$('import-dialog').open)$('import-dialog').showModal();}catch(e){this.error(e.message,false);}};p.append(b);}previous.append(p);}
    $('import-open').hidden=!['ready','submitting','invalid'].includes(d.state);
    $('import-open').textContent=d.operations.length?'查看草稿与创建结果':'查看草稿';
    $('import-document-note').textContent=`${d.filename} · ${d.format.toUpperCase()}${d.model?' · 分析模型：'+d.model:''} · 原文仅本次运行保留`;
    $('import-draft-state').textContent=status;
    $('import-warnings').replaceChildren(...d.warnings.map(w=>node('p','',w)));
    this.renderTable();
    const excluded=$('import-excluded-content');excluded.replaceChildren();
    for(const item of d.excluded){const p=node('p','',item.reason);const b=node('button','text-button','查看依据');b.onclick=()=>this.showSource(item.source_ids);p.append(' ',b);excluded.append(p);}
    if(!d.excluded.length)excluded.append(node('p','subtle','没有额外的排除说明。请结合原文核对是否漏项。'));
    this.renderResults(d.operations);this.controls();
  }
  renderTable(){
    const d=this.draft;if(!d)return;
    const rows=d.candidates.filter(r=>!r.deleted),pages=Math.max(1,Math.ceil(rows.length/25));this.page=Math.max(0,Math.min(this.page,pages-1));
    this.prev.disabled=this.page===0;this.next.disabled=this.page===pages-1;this.pageLabel.textContent=`第 ${this.page+1}/${pages} 页 · 共 ${rows.length} 条需求`;
    const body=$('import-rows');body.replaceChildren();
    if(!rows.length){const tr=node('tr'),td=node('td','empty',d.state==='analyzing'?'正在分析，请等待完整草稿。':'没有可执行候选，请查看排除说明并核对原文。');td.colSpan=6;tr.append(td);body.append(tr);}
    for(const row of rows.slice(this.page*25,(this.page+1)*25)){
      const tr=node('tr',row.ready?'':'import-needs-review');tr.dataset.candidateId=row.candidate_id;
      const cell=label=>{const td=node('td');td.dataset.label=label;tr.append(td);return td;};
      const select=cell('选择'),check=node('input');check.type='checkbox';check.checked=this.selection.has(row.candidate_id);check.disabled=!row.ready||this.loading||this.chat.busy;check.setAttribute('aria-label',`选择 ${row.candidate_id}`);check.onchange=()=>{if(check.checked)this.selection.add(row.candidate_id);else this.selection.delete(row.candidate_id);this.controls();};select.append(check,node('span','subtle',row.candidate_id));
      for(const [field,group,label] of [['pickup_id','pickup','取货点'],['delivery_id','delivery','配送点']]){
        const td=cell(label),input=node('select');input.dataset.field=field;input.setAttribute('aria-label',`${row.candidate_id} ${label}`);input.append(new Option(`请选择${label}`,''));
        for(const place of d.locations[group]||[]){const shelves=group==='pickup'?(d.locations.shelf||[]).filter(s=>s.pickup_id===place.id).map(s=>s.name):[];input.append(new Option(`${place.id} · ${place.name}${shelves.length?'（'+shelves.join('、')+'）':''}`,place.id));}
        input.value=row[field]||'';input.disabled=d.state!=='ready'||this.loading||this.chat.busy;input.onchange=()=>this.edit(row,{[field]:input.value||null},field);td.append(input);
      }
      const level=cell('等级'),priority=node('select');priority.dataset.field='priority';priority.setAttribute('aria-label',`${row.candidate_id} 等级`);for(let i=1;i<=5;i++)priority.append(new Option(i===5?'5 · 紧急':String(i),String(i)));priority.value=String(row.priority);priority.disabled=d.state!=='ready'||this.loading||this.chat.busy;priority.onchange=()=>this.edit(row,{priority:Number(priority.value)},'priority');level.append(priority);
      const counts=cell('次数');
      const target=node('input');target.type='number';target.min='1';target.max='2000';target.step='1';target.value=row.count??'';target.dataset.field='count';target.setAttribute('aria-label',`${row.candidate_id} 目标搬运次数`);target.disabled=d.state!=='ready'||this.loading||this.chat.busy;target.onchange=()=>this.edit(row,{count:target.value===''?null:Number(target.value)},'count');
      const targetLabel=node('label','import-count-label','目标次数');targetLabel.append(target);counts.append(targetLabel);
      const quantity=node('input');quantity.type='number';quantity.min='1';quantity.max=String(Math.min(row.remaining,20));quantity.step='1';quantity.value=this.counts.get(row.candidate_id)||'';quantity.setAttribute('aria-label',`${row.candidate_id} 本次提交次数`);quantity.disabled=!row.ready||this.loading||this.chat.busy;quantity.onchange=()=>{const value=Number(quantity.value);if(!Number.isInteger(value)||value<1||value>Math.min(row.remaining,20)){this.quantityErrors.add(row.candidate_id);quantity.setAttribute('aria-invalid','true');this.controls();this.error('本次次数必须是1至20的整数，且不能超过剩余次数。');return;}this.quantityErrors.delete(row.candidate_id);quantity.removeAttribute('aria-invalid');this.counts.set(row.candidate_id,value);this.error('');this.controls();};
      const quantityLabel=node('label','import-count-label','本次次数');quantityLabel.append(quantity);counts.append(quantityLabel,node('p','subtle',`已创建 ${row.created_count} · 剩余 ${row.remaining}${row.reserved_count?' · 待核实 '+row.reserved_count:''}`));
      const detail=cell('核对与来源');detail.append(node('strong',row.ready?'import-ready':'import-warning',row.ready?'就绪':d.state==='invalid'?'旧场景 · 只读':row.reserved_count?'结果待核实':row.created_count>0&&row.remaining===0?'已完成创建':'待处理'));
      if(row.quantity_text)detail.append(node('p','subtle','原数量：'+row.quantity_text));
      for(const message of [...row.problems,...row.notes,...row.overrides.map(x=>'本次覆盖：'+x)])detail.append(node('p','subtle',message));
      if(row.similar.length)detail.append(node('p','import-warning',`与 ${row.similar.join('、')} 路线相同，请核对；不会自动合并。`));
      for(const [field,values,label] of [['reviewed',row.issues,'已核对识别疑点'],['ignore_constraints',row.constraints,'接受本次忽略以下执行约束']]){
        if(!values.length)continue;const l=node('label','import-check'),input=node('input');input.type='checkbox';input.checked=row[field];input.disabled=d.state!=='ready'||this.loading||this.chat.busy;input.dataset.field=field;input.onchange=()=>this.edit(row,{[field]:input.checked},field);l.append(input,node('span','',`${label}：${values.join('；')}`));detail.append(l);
      }
      if(row.human_edited)detail.append(node('p','subtle','已人工修改；已创建的任务保持原值。'));
      const actions=node('div','import-row-actions'),source=node('button','text-button','查看来源'),remove=node('button','text-button','删除草稿');source.onclick=()=>this.showSource(row.source_ids);remove.disabled=d.state!=='ready'||this.loading||this.chat.busy;remove.onclick=()=>this.edit(row,{deleted:true});actions.append(source,remove);detail.append(actions);body.append(tr);
    }
  }
  async edit(row,changes,focusField){
    this.loading=true;this.controls();this.error('');
    const epoch=this.syncEpoch;
    try{const v=await api('imports/draft',{draft_id:this.draft.draft_id,expected_revision:this.draft.revision,candidate_id:row.candidate_id,changes});if(epoch===this.syncEpoch){this.syncEpoch++;this.setDraft(v.draft);}else await this.refresh();}
    catch(e){this.error(e.message);await this.refresh().catch(()=>{});}
    finally{this.loading=false;this.renderTable();this.chat.controls();if(focusField)$('import-rows').querySelector(`[data-candidate-id="${row.candidate_id}"] [data-field="${focusField}"]`)?.focus();}
  }
  selected(){return [...this.selection].map(candidate_id=>({candidate_id,count:this.counts.get(candidate_id)||0}));}
  selectReady(){
    const ready=this.draft.candidates.filter(r=>r.ready&&r.remaining>0);
    const total=ready.reduce((n,r)=>n+(this.counts.get(r.candidate_id)||0),0);
    if(total>20){this.error('全部就绪项合计超过20次，请逐项选择并调整本次次数；没有自动截取。');return;}
    if(ready.some(r=>this.quantityErrors.has(r.candidate_id))){this.error('请先修正标出的本次次数。');return;}
    this.selection=new Set(ready.map(r=>r.candidate_id));this.error('');this.render();
  }
  async showSource(ids){
    const documentId=this.draft?.document_id;if(!documentId)return;
    try{const blocks=await Promise.all(ids.map(id=>api(`imports/source?document_id=${encodeURIComponent(documentId)}&block_id=${encodeURIComponent(id)}`)));if(this.draft?.document_id!==documentId)return;const area=$('import-source-content');area.replaceChildren();for(const block of blocks)area.append(node('p','subtle',locatorText(block.locator)),node('pre','',block.text));$('import-source').hidden=false;$('import-source').focus();}
    catch(e){this.error(e.message);}
  }
  async commit(){
    if($('import-commit').disabled)return;
    const data={draft_id:this.draft.draft_id,expected_revision:this.draft.revision,confirmation_id:crypto.randomUUID(),selections:this.selected()};
    this.pendingConfirmation=data;this.loading=true;this.chat.submitting=true;this.chat.controls();this.error('');
    try{const op=await api('imports/commit',data);this.pendingConfirmation=null;this.selection.clear();this.chat.busy=op.status==='running';await this.refresh();}
    catch(e){if(e.status&&e.status<500)this.pendingConfirmation=null;this.error(`${this.pendingConfirmation?'提交结果待核实：':''}${e.message}${this.pendingConfirmation?'。请先点击“核实结果”，不要重复创建。':''}`);await this.refresh().catch(()=>{});}
    finally{this.loading=false;this.chat.submitting=false;this.chat.controls();this.renderTable();}
  }
  async verify(){
    this.loading=true;this.controls();
    try{
      if(this.pendingConfirmation){const op=await api('imports/operation?id='+encodeURIComponent(this.pendingConfirmation.confirmation_id));if(op.draft_id){this.pendingConfirmation=null;this.retryButton.hidden=true;this.selection.clear();}else{this.error((op.error||'结果仍待核实')+'。可重发同次确认以查询或受理原提交，确认标识和参数保持不变。');this.retryButton.hidden=false;}}
      await this.refresh();
      if(!this.pendingConfirmation)this.error('');
    }catch(e){this.error(e.message);}
    finally{this.loading=false;this.chat.controls();this.renderTable();}
  }
  async retryConfirmation(){
    if(!this.pendingConfirmation||this.loading)return;
    this.loading=true;this.chat.submitting=true;this.chat.controls();
    try{const op=await api('imports/commit',this.pendingConfirmation);this.pendingConfirmation=null;this.retryButton.hidden=true;this.selection.clear();this.chat.busy=op.status==='running';this.error('');await this.refresh();}
    catch(e){if(e.status&&e.status<500){this.pendingConfirmation=null;this.retryButton.hidden=true;}this.error(e.message);}
    finally{this.loading=false;this.chat.submitting=false;this.chat.controls();this.renderTable();}
  }
  renderResults(operations=[]){
    const target=$('import-result-content');target.replaceChildren();$('import-results').hidden=!operations.length;
    for(const op of operations){
      target.append(node('p','subtle',`提交 ${op.submission_id.slice(0,8)} · 场景${op.generation} · ${op.status==='finished'?'已结束':op.status==='unknown'?'结果待核实，请勿重复创建':'处理中'}`));
      if(op.result?.error)target.append(node('p','result-error',op.result.error));
      for(const item of op.result?.actions||[]){const card=node('div','result-card'),applied=item.outcome==='applied';card.append(node('strong','',applied?(item.planning==='available'?'已创建 · 路线可用':item.planning==='superseded'?'原场景已创建':item.planning==='unavailable'?'已创建 · 路线暂不可用':'已创建 · 路线状态待核实'):'未创建'));
        if(item.task_id&&applied){const b=node('button','text-button',item.task_id);b.disabled=this.chat.state()?.generation!==op.generation;b.onclick=()=>{$('import-dialog').close();this.chat.select(Number(item.task_id.slice(1)),op.generation);};card.append(b);}
        if(item.reason)card.append(node('p','subtle',item.reason));target.append(card);
      }
    }
  }
  event(e){
    if(e.kind==='clear'){this.syncEpoch++;this.pendingConfirmation=null;this.liveAnalysis=null;this.retryButton.hidden=true;this.setDraft(null);return;}
    if(e.kind==='import_ready'){this.syncEpoch++;this.refresh().then(()=>{if(this.liveAnalysis===e.request_id){this.liveAnalysis=null;if(this.hiddenDraft!==this.draft?.draft_id)return this.open();}}).catch(err=>this.error(err.message,false));}
    if(['done','context','result'].includes(e.kind)){this.syncEpoch++;this.refresh().catch(()=>{});}
    if(e.kind==='import_progress'){$('import-draft-state').textContent=e.stage+(e.total?` · ${e.completed}/${e.total}`:'');}
  }
}
