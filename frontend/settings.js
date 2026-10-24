const $=id=>document.getElementById(id);
export async function api(path,data) {
  const response=await fetch('/api/ai/'+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const result=await response.json();if(!response.ok){const error=new Error(result.error||'请求未完成');error.status=response.status;throw error;}return result;
}
export class Settings {
  constructor(){
    this.value=null;this.busy=false;this.onChange=()=>{};
    $('ai-settings').onclick=()=>this.open();$('chat-configure').onclick=()=>this.open();
    $('settings-close').onclick=()=>$('settings-dialog').close();
    $('settings-form').onsubmit=async e=>{e.preventDefault();await this.action(async()=>{await this.save();this.message('设置已保存');});};
    $('settings-models').onclick=()=>this.action(async()=>{await this.save();await api('models',{});this.message('正在获取模型…');});
    $('settings-test').onclick=()=>this.action(async()=>{await this.save();await api('test',{});this.message('正在测试连接与只读工具…');});
    $('settings-delete').onclick=()=>this.action(async()=>{this.value=await api('settings',{delete_key:true});$('settings-key').value='';this.fill();this.onChange(this.value);this.message('密钥已删除');});
    $('settings-model').oninput=()=>this.efforts();
    $('settings-url').oninput=()=>this.keyIndicator();
    this.refresh().catch(()=>{});
  }
  async refresh(){this.value=await api('settings');this.onChange(this.value);return this.value;}
  async open(){try{await this.refresh();this.fill();$('settings-dialog').showModal();}catch(e){this.message(e.message);}}
  fill(){const v=this.value;if(!v)return;$('settings-url').value=v.base_url;$('settings-model').value=v.model;$('settings-effort').value=v.effort;$('settings-timeout').value=v.timeout;$('settings-remember').checked=v.remember;$('settings-key').value='';this.keyIndicator();this.populate(v.models||[]);this.message(v.warning||'');}
  keyIndicator(){
    const base=$('settings-url').value.trim().replace(/\/+$/,'');
    const configured=!!this.value?.has_key&&base===this.value.base_url;
    // Show a fixed mask as a placeholder; never submit it as a replacement key.
    $('settings-key').placeholder=configured?'••••••••••••••••••••••••':'输入密钥；留空保留同地址已配置密钥';
    $('settings-key').dataset.configured=String(configured);
    $('key-state').textContent=configured?'已配置':'未配置';
  }
  populate(models){this.models=models;const list=$('model-options');list.replaceChildren();for(const m of models){const o=document.createElement('option');o.value=m.id;o.label=m.name||m.id;list.append(o);}this.efforts();}
  efforts(){const m=this.models?.find(m=>m.id===$('settings-model').value);for(const o of $('settings-effort').options)o.disabled=o.value!=='off'&&!!m?.efforts?.length&&!m.efforts.includes(o.value);$('model-note').textContent=m?`${m.name||m.id} · ID：${m.id}`:'模型列表查询失败时仍可手动填写。';}
  message(text){$('settings-message').textContent=text;}
  async save(){
    const base=$('settings-url').value.trim().replace(/\/+$/,'');const key=$('settings-key').value;
    if(this.value&&base!==this.value.base_url&&!key.trim())throw new Error('地址已更改，请明确填写要提交到新地址的密钥');
    const data={base_url:base,model:$('settings-model').value.trim(),effort:$('settings-effort').value,timeout:Number($('settings-timeout').value),remember:$('settings-remember').checked};
    if(key.trim())data.api_key=key;
    this.value=await api('settings',data);$('settings-key').value='';this.keyIndicator();$('settings-remember').checked=this.value.remember;this.onChange(this.value);
  }
  async action(fn){try{await fn();}catch(e){this.message(e.message);}}
  status(value){this.busy=value.busy;for(const id of ['settings-models','settings-test'])$(id).disabled=this.busy;}
  event(e){if(e.kind==='models'){this.populate(e.models);this.message(`已获取 ${e.models.length} 个模型；请选择或填写模型ID`);}if(['notice','error'].includes(e.kind)&&this.value?.request_id===e.request_id)this.message(e.message);}
}
