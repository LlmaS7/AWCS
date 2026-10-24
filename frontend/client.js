/** Shared read/command transport. Both windows talk to one simulation. */
export class SimulationClient {
  constructor({onState=()=>{},onStatus=()=>{},onError=()=>{}}={}) {
    this.state=null;this.connected=false;this.pending=0;this.receivedAt=0;
    this.onState=onState;this.onStatus=onStatus;this.onError=onError;this.stopped=false;
  }
  accept(value) {
    if(!value.map && this.state) value={...value,map:this.state.map};
    // Revision also increases across resets, so late replies cannot rewind a view.
    if(this.state && value.revision<this.state.revision) return;
    const previous=this.state;this.state=value;this.receivedAt=performance.now();
    this.onState(value,previous);
  }
  async poll() {
    if(this.stopped) return;
    try {
      const query=this.state?new URLSearchParams({map_hash:this.state.map.hash||'',generation:this.state.generation}):'';
      const response=await fetch('./api/state?'+query,{cache:'no-store'});
      if(!response.ok) throw new Error('连接未就绪');
      const value=await response.json();this.connected=true;
      if(!this.state || value.revision!==this.state.revision) this.accept(value);
    } catch(error) {this.connected=false;}
    finally {this.onStatus();if(!this.stopped) setTimeout(()=>this.poll(),this.connected?110:1000);}
  }
  async command(operation,data={}) {
    if(!this.connected) {this.onError('尚未连接仿真，请稍后再试');return false;}
    this.pending++;this.onStatus();
    try {
      const command_id=crypto.randomUUID().replaceAll('-','');
      const response=await fetch('./api/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({operation,data,command_id})});
      let result=await response.json();
      if(!response.ok || !result.ok) throw new Error(result.error || '操作未完成');
      if(result.state)this.accept(result.state);
      if(result.pending) {
        const deadline=performance.now()+30000;
        while(performance.now()<deadline) {
          await new Promise(resolve=>setTimeout(resolve,120));
          const poll=await fetch('./api/operation?id='+encodeURIComponent(command_id),{cache:'no-store'});
          const status=await poll.json();
          if(status.status==='finished') {result=status;break;}
          if(status.status==='unknown')throw new Error(status.error);
        }
        if(result.pending)throw new Error('操作已接收，结果仍待核实；请查看当前状态，不要重复提交。');
        if(!result.ok)throw new Error(result.error || '操作未完成');
      }
      this.accept(result.state);return true;
    } catch(error) {this.onError(error.message);return false;}
    finally {this.pending--;this.onStatus();}
  }
}

export async function openDebugWindow() {
  if(window.pywebview?.api?.open_debug) return window.pywebview.api.open_debug();
  const child=window.open('./debug.html','sditadc-debug','width=900,height=800');
  if(!child) throw new Error('调试窗口被拦截，请允许本机页面打开窗口');
  return {ok:true};
}

export async function focusMainWindow() {
  if(window.pywebview?.api?.focus_main) return window.pywebview.api.focus_main();
  if(window.opener && !window.opener.closed) window.opener.focus();
  else window.open('./','sditadc-main');
  return {ok:true};
}
