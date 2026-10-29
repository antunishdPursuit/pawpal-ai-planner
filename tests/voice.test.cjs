const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'..','assets','voice.js'),'utf8').replace('export default function','module.exports = function');

// Exercise the shipped component's lifecycle with a deterministic audio/socket clock.
// Real browser layout and the short real-service connection are checked separately.
function voice({credential=true,denied=false,pendingMicrophone=false}={}){
 let clock=1_000_000,id=0,tracksStopped=0,micRequests=0,resolveMicrophone;
 const timers=new Map(),events=[],sockets=[],storage=new Map();
 const elements=Object.fromEntries(['dictate','live','stop','review','status','transcript'].map(id=>[id,{disabled:false,hidden:false,textContent:'',attrs:{},setAttribute(k,v){this.attrs[k]=v;}}]));
 const stream={getTracks:()=>[{stop(){tracksStopped++;}}]};
 const node=()=>({connect(){},disconnect(){},gain:{value:1},port:{onmessage:null}});
 class AudioContext{
  constructor({sampleRate}){this.sampleRate=sampleRate;this.currentTime=0;this.audioWorklet={addModule:async()=>{}};}
  async resume(){} async close(){} createMediaStreamSource(){return node();} createGain(){return node();}
 }
 class Socket{
  static OPEN=1;
  constructor(){this.readyState=0;this.sent=[];sockets.push(this);}
  send(s){this.sent.push(JSON.parse(s));}
  close(){this.readyState=3;}
  open(){this.readyState=1;this.onopen?.();}
  async message(data){await this.onmessage?.({data:JSON.stringify(data)});}
  drop(code,reason='',wasClean=false){this.readyState=3;this.onclose?.({code,reason,wasClean});}
 }
 const window={AudioContext,addEventListener(){},removeEventListener(){}};
 const context={module:{exports:{}},window,AudioContext,AudioWorkletNode:class{constructor(){Object.assign(this,node());}},
  navigator:{mediaDevices:{getUserMedia:async()=>{micRequests++;if(denied)throw Object.assign(new Error(),{name:'NotAllowedError'});if(pendingMicrophone)return new Promise(r=>resolveMicrophone=r);return stream;}}},
  Date:class extends Date{static now(){return clock;}},WebSocket:Socket,Blob,URL:{createObjectURL:()=>'',revokeObjectURL(){}},btoa,atob,
  sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
  setTimeout:(fn,ms)=>{const key=++id;timers.set(key,{fn,at:clock+ms});return key;},clearTimeout:key=>timers.delete(key)};
 vm.createContext(context);vm.runInContext(source,context);
 const data={configured:true,replace_allowed:true,credential:credential?{issued_at:clock/1000,session_id:'fake-session',token:'test-only',model:'test'}:null};
 const cleanup=context.module.exports({parentElement:{querySelector:s=>elements[s.slice(1)]},data,setStateValue:(_,v)=>events.push(v)});
 return {elements,events,sockets,cleanup,get tracksStopped(){return tracksStopped;},get micRequests(){return micRequests;},
  resolveMic(){resolveMicrophone(stream);},async flush(){await new Promise(setImmediate);},
  advance(ms){const end=clock+ms;while(true){const next=[...timers].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;clock=next[1].at;timers.delete(next[0]);next[1].fn();}clock=end;}};
}
async function connected(){const p=voice();p.elements.live.onclick();await p.flush();p.sockets[0].open();await p.sockets[0].message({setupComplete:{}});return p;}

test('credential preparation is disabled, busy, explicit, and cannot double-submit',()=>{
 const p=voice({credential:false});p.elements.live.onclick();p.elements.live.onclick();
 assert.equal(p.elements.live.textContent,'Getting speech ready...');assert.equal(p.elements.live.disabled,true);
 assert.equal(p.elements.dictate.disabled,true);assert.equal(p.elements.live.attrs['aria-busy'],'true');
 assert.deepEqual(p.events.map(e=>e.kind),['connect']);assert.equal(p.micRequests,0);p.cleanup();
});
test('prepared credentials do not falsely announce a connected live session',async()=>{
 const p=voice();assert.equal(p.elements.live.textContent,'Start live');assert.match(p.elements.status.textContent,/Select Start live/);
 p.elements.live.onclick();await p.flush();assert.equal(p.elements.live.disabled,true);assert.equal(p.elements.live.attrs['aria-busy'],'true');
 assert.equal(p.elements.live.textContent,'Getting speech ready...');assert.doesNotMatch(p.elements.status.textContent,/Live is ready/);
 p.sockets[0].open();await p.sockets[0].message({setupComplete:{}});
 assert.equal(p.elements.live.textContent,'Live connected');assert.equal(p.elements.live.attrs['aria-busy'],'false');assert.match(p.elements.status.textContent,/Live is ready/);p.cleanup();
});
test('socket error waits for close details and emits one credential-free end event',async()=>{
 const p=await connected();p.sockets[0].onerror();p.advance(50);p.sockets[0].drop(1008,'Unsupported session options',true);p.advance(2000);
 assert.equal(p.events.length,1);const e=p.events[0];assert.equal(e.diagnostic.code,1008);assert.equal(e.diagnostic.provider_reason,'Unsupported session options');
 assert.equal(e.diagnostic.phase,'listening');assert.equal(e.save_requested,false);assert.doesNotMatch(JSON.stringify(e),/test-only/);assert.equal(p.tracksStopped,1);
});
test('network error without a close event still ends and releases audio',async()=>{
 const p=await connected();p.sockets[0].onerror();p.advance(1001);assert.equal(p.events.length,1);assert.equal(p.events[0].diagnostic.cause,'connection_error');assert.equal(p.tracksStopped,1);
});
test('advance GoAway notice keeps the live session active for its grace period',async()=>{
 const p=await connected();await p.sockets[0].message({goAway:{timeLeft:'30s'}});assert.equal(p.events.length,0);assert.equal(p.sockets[0].readyState,1);
 p.advance(29999);assert.equal(p.events.length,0);p.advance(2);assert.equal(p.events.length,1);assert.equal(p.events[0].diagnostic.cause,'server_go_away');
});
test('permission denial releases audio and provides a distinct failure',async()=>{
 const p=voice({denied:true});p.elements.live.onclick();await p.flush();assert.equal(p.sockets.length,0);assert.equal(p.events[0].diagnostic.cause,'microphone_denied');assert.equal(p.elements.live.disabled,false);
});
test('setup timeout and component disposal do not leave a microphone active',async()=>{
 const p=voice();p.elements.live.onclick();await p.flush();p.sockets[0].open();p.advance(15001);assert.equal(p.events[0].diagnostic.cause,'connection_timeout');assert.equal(p.tracksStopped,1);
 const q=voice({pendingMicrophone:true});q.elements.live.onclick();await q.flush();q.cleanup();q.resolveMic();await q.flush();assert.equal(q.sockets.length,0);assert.equal(q.tracksStopped,1);assert.equal(q.events.length,0);
});
test('disconnect retains spoken history and never saves an unconfirmed preview',async()=>{
 const p=await connected(),s=p.sockets[0];await s.message({serverContent:{inputTranscription:{text:'Walk Luna tomorrow'}}});await s.message({serverContent:{outputTranscription:{text:'Shall I save it?'}}});
 await s.message({toolCall:{functionCalls:[{name:'preview_task',id:'proposal-1',args:{title:'Walk Luna'}}]}});
 await s.message({toolCall:{functionCalls:[{name:'save_task',id:'save-1',args:{proposal_id:'proposal-1'}}]}});
 s.drop(1006);assert.equal(p.events[0].save_requested,false);assert.equal(p.events[0].history[0].text,'Walk Luna tomorrow');assert.equal(p.events[0].diagnostic.code,1006);
});
test('explicit confirmation still completes one task after the closing turn',async()=>{
 const p=await connected(),s=p.sockets[0];await s.message({serverContent:{inputTranscription:{text:'Walk Luna tomorrow'}}});await s.message({serverContent:{outputTranscription:{text:'Shall I save it?'}}});
 await s.message({toolCall:{functionCalls:[{name:'preview_task',id:'proposal-1',args:{title:'Walk Luna'}}]}});
 await s.message({serverContent:{inputTranscription:{text:'Yes, please'}}});await s.message({toolCall:{functionCalls:[{name:'save_task',id:'save-1',args:{proposal_id:'proposal-1'}}]}});
 await s.message({serverContent:{outputTranscription:{text:"I'll save that now."},turnComplete:true}});p.advance(101);
 assert.equal(p.events.length,1);assert.equal(p.events[0].save_requested,true);assert.equal(p.events[0].confirmation_after_preview,true);assert.equal(p.events[0].proposal_id,'proposal-1');assert.equal(p.events[0].diagnostic.phase,'finishing');
});

test('connection milestones stay local until the end and contain no speech or credentials',async()=>{
 const p=await connected(),s=p.sockets[0];assert.equal(p.events.length,0);
 await s.message({serverContent:{outputTranscription:{text:'PRIVATE DIALOGUE'},modelTurn:{parts:[{inlineData:{data:'AAA='}}]},turnComplete:true}});
 assert.equal(p.events.length,0);s.drop(1006);
 assert.equal(p.events.length,1);const d=p.events[0].diagnostic;
 assert.deepEqual(Array.from(d.milestones,m=>m.stage),['microphone','connecting','socket_open','listening','speaking','listening','ended']);
 assert.equal(d.output_chunks,1);assert.equal(d.input_chunks,0);
 assert.doesNotMatch(JSON.stringify(d),/PRIVATE|test-only|fake-session/);
});
