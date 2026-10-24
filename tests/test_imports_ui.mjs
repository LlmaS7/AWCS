import assert from 'node:assert/strict';
import test, {afterEach} from 'node:test';
import {Imports} from '../frontend/imports.js';

// Exercise the real renderer and HTTP/event paths without a browser dependency.
class Element {
  constructor(){this.textContent='';this.children=[];this.hidden=false;this.disabled=false;this.open=false;}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  close(){this.open=false;}
  showModal(){this.open=true;}
  focus(){}
}
const originalDocument=globalThis.document,originalFetch=globalThis.fetch;
afterEach(()=>{globalThis.document=originalDocument;globalThis.fetch=originalFetch;});
const operation=(status='finished')=>({submission_id:'confirmation-123456',generation:1,status,result:null});
const candidate=changes=>({candidate_id:'c1',count:2,created_count:0,reserved_count:0,remaining:2,ready:true,deleted:false,...changes});
const draft=(candidates=[candidate()],operations=[],state='ready')=>({
  draft_id:'draft-1',document_id:'draft-1',revision:1,filename:'orders.txt',format:'txt',
  generation:1,state,candidates,operations,duplicates:[],warnings:[],excluded:[]
});
function view(){
  const elements=new Map();
  globalThis.document={getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},createElement(){return new Element();}};
  const imports=Object.assign(Object.create(Imports.prototype),{
    draft:null,loading:false,selection:new Set(),counts:new Map(),quantityErrors:new Set(),
    pendingConfirmation:null,syncEpoch:0,page:0,retryButton:new Element(),
    chat:{busy:false,submitting:false,state:()=>({generation:1}),controls(){}}
  });
  // Table layout is independent of the attachment and draft status indicators.
  imports.renderTable=()=>{};
  return {imports,get:id=>document.getElementById(id)};
}
function assertStatus(v,expected){
  assert.equal(v.get('import-attachment-status').textContent,expected);
  assert.equal(v.get('import-draft-state').textContent,expected);
}

for(const [name,data,expected] of [
  ['new draft',draft(),'草稿已就绪，等待检查确认'],
  ['all tasks created',draft([candidate({created_count:2,remaining:0,ready:false})],[operation()]),'已全部创建，共 2 项任务'],
  ['batch limit leaves tasks',draft([candidate({count:25,created_count:20,remaining:5})],[operation()]),'已创建 20 项任务，剩余 5 项待检查确认'],
  ['unresolved quantity remains',draft([candidate({created_count:2,remaining:0,ready:false}),candidate({candidate_id:'c2',count:null,remaining:0,ready:false})],[operation()]),'已创建 2 项任务，剩余需求待补充、检查确认'],
  ['no tasks applied',draft([candidate()],[operation()]),'尚未创建任务，请查看结果后重新检查确认'],
  ['empty extraction',draft([]),'当前无待创建任务，请核对原文与排除说明'],
  ['running submission',draft([candidate({reserved_count:2,remaining:0,ready:false})],[operation('running')],'submitting'),'正在提交，请等待逐项回执'],
  ['unknown receipt is not completion',draft([candidate({reserved_count:2,remaining:0,ready:false})],[operation('unknown')],'submitting'),'创建结果待核实，已确认创建 0 项；请先核实结果，勿重复创建'],
  ['scene change overrides old success',draft([candidate({created_count:2,remaining:0,ready:false})],[operation()],'invalid'),'场景已变化，草稿只读；请重新导入'],
])test(name,()=>{
  const v=view();v.imports.setDraft(data);assertStatus(v,expected);
  assert.equal(v.get('import-open').textContent,data.operations.length?'查看草稿与创建结果':'查看草稿');
});

test('commit response already finished updates both indicators and clears busy flag',async()=>{
  const v=view();v.imports.setDraft(draft());
  v.imports.selection.add('c1');v.imports.controls();
  const requests=[];
  globalThis.fetch=async(url,options)=>{
    requests.push([url,options]);
    return {ok:true,json:async()=>url.endsWith('/commit')?operation():{draft:draft([candidate({created_count:2,remaining:0,ready:false})],[operation()])}};
  };
  await v.imports.commit();
  assertStatus(v,'已全部创建，共 2 项任务');
  assert.equal(v.imports.chat.busy,false);
  assert.equal(v.imports.pendingConfirmation,null);
  assert.equal(v.imports.selection.size,0);
  assert.equal(v.get('import-commit').disabled,true);
  assert.equal(requests.filter(([url])=>url.endsWith('/commit')).length,1);
  const sent=JSON.parse(requests[0][1].body);
  assert.deepEqual(sent.selections,[{candidate_id:'c1',count:2}]);
});

test('completion events refresh submitting state and preserve explicit batching',async()=>{
  const v=view();v.imports.setDraft(draft([candidate({count:25,remaining:25})]));
  v.imports.selection.add('c1');v.imports.controls();
  let current=draft([candidate({count:25,reserved_count:20,remaining:5,ready:false})],[operation('running')],'submitting');
  const requests=[];
  globalThis.fetch=async url=>{requests.push(url);return {ok:true,json:async()=>url.endsWith('/commit')?operation('running'):{draft:structuredClone(current)}};};
  await v.imports.commit();
  assertStatus(v,'正在提交，请等待逐项回执');
  current=draft([candidate({count:25,created_count:20,remaining:5})],[operation()]);
  current.revision=2;
  v.imports.event({kind:'result'});v.imports.event({kind:'done'});
  await v.imports.refresh();
  assertStatus(v,'已创建 20 项任务，剩余 5 项待检查确认');
  assert.equal(v.imports.counts.get('c1'),5);
  assert.equal(v.imports.selection.size,0);
  assert.equal(requests.filter(url=>url.endsWith('/commit')).length,1,'refresh must not create tasks');
  v.imports.chat.busy=false;v.imports.controls();
  assert.equal(v.get('import-commit').disabled,true,'remaining tasks need a new explicit selection');
  v.imports.selection.add('c1');v.imports.controls();
  assert.equal(v.get('import-commit').disabled,false);
});


test('completed attachment hides automatically and history can reopen it across refreshes',async()=>{
  const v=view();
  const completed=draft([candidate({created_count:2,remaining:0,ready:false})],[operation()]);
  v.imports.setDraft(completed);
  assert.equal(v.get('import-attachment').hidden,true);
  assert.equal(v.get('import-history').hidden,false);
  globalThis.fetch=async()=>({ok:true,json:async()=>({draft:structuredClone(completed)})});
  await v.imports.open();
  assert.equal(v.get('import-dialog').open,true);
  assert.equal(v.get('import-attachment').hidden,false);
  assert.equal(v.get('import-history').hidden,true);
  await v.imports.refresh();
  assert.equal(v.get('import-attachment').hidden,false,'polling must not undo explicit reopening');
});

test('manual close preserves draft and receipts and is not undone by polling',async()=>{
  const v=view();const partial=draft([candidate({created_count:1,remaining:1})],[operation()]);
  v.imports.setDraft(partial);v.get('import-dialog').open=true;
  globalThis.fetch=async url=>{
    assert.ok(url.endsWith('/draft'),'closing must not discard data or write business state');
    return {ok:true,json:async()=>({draft:structuredClone(partial)})};
  };
  v.imports.dismiss();
  assert.equal(v.get('import-attachment').hidden,true);
  assert.equal(v.get('import-dialog').open,false);
  assert.equal(v.get('import-history').hidden,false);
  assert.equal(v.imports.draft,partial);
  await v.imports.refresh();
  assert.equal(v.get('import-attachment').hidden,true);
  assert.equal(v.imports.draft.operations.length,1);
  v.imports.showAttachment();
  assert.equal(v.get('import-attachment').hidden,false);
});

test('partial, failed, unknown and unresolved drafts stay visible by default',()=>{
  for(const data of [
    draft([candidate({created_count:1,remaining:1})],[operation()]),
    draft([candidate()],[operation()]),
    draft([candidate({reserved_count:2,remaining:0,ready:false})],[operation('unknown')],'submitting'),
    draft([candidate({created_count:2,remaining:0,ready:false}),candidate({candidate_id:'c2',count:null,remaining:0,ready:false})],[operation()]),
  ]){
    const v=view();v.imports.setDraft(data);
    assert.equal(v.get('import-attachment').hidden,false);
    assert.equal(v.get('import-history').hidden,true);
  }
});

test('new attachment is visible after closing a previous draft',()=>{
  const v=view();v.imports.setDraft(draft());v.imports.dismiss();
  v.imports.setDraft({...draft(),draft_id:'draft-2',document_id:'draft-2',state:'uploaded'});
  assert.equal(v.get('import-attachment').hidden,false);
  v.imports.dismiss();assert.equal(v.get('import-history').textContent,'查看附件');
  v.imports.event({kind:'clear'});
  assert.equal(v.get('import-history').hidden,true);
  assert.equal(v.get('import-attachment').hidden,true);
});

test('completion arriving through polling automatically hides attachment',async()=>{
  const v=view();v.imports.setDraft(draft());
  const completed=draft([candidate({created_count:2,remaining:0,ready:false})],[operation()]);
  globalThis.fetch=async()=>({ok:true,json:async()=>({draft:completed})});
  v.imports.event({kind:'result'});v.imports.event({kind:'done'});
  await v.imports.refresh();
  assert.equal(v.get('import-attachment').hidden,true);
  assert.equal(v.get('import-history').hidden,false);
  assert.equal(v.imports.draft.operations.length,1);
});

test('replacing a completed attachment does not ask to abandon unfinished work',async()=>{
  const v=view();v.imports.setDraft(draft([candidate({created_count:2,remaining:0,ready:false})],[operation()]));
  globalThis.fetch=async(url,options)=>{
    assert.ok(url.endsWith('/discard'));
    assert.deepEqual(JSON.parse(options.body),{draft_id:'draft-1'});
    return {ok:true,json:async()=>({draft:null})};
  };
  // No window.confirm implementation: completed drafts should not prompt.
  assert.equal(await v.imports.discard(true),true);
  assert.equal(v.get('import-history').hidden,true);
});
