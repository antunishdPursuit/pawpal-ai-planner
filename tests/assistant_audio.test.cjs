const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/assistant_audio.js','utf8').replace('export function createLive','function createLive')+';globalThis.make=createLive;';
function fixture(denied=false){
 const events=[],sockets=[],tracks=[{id:'track-one',stop(){this.stopped=true;}}];
 class Audio {constructor(){this.sampleRate=16000;this.currentTime=0;this.audioWorklet={addModule:async()=>{}};}async resume(){}async close(){this.closed=true;}createGain(){return {gain:{},connect(){},disconnect(){}};}createMediaStreamSource(){return {connect(){},disconnect(){}};}}
 class Worklet {constructor(){this.port={};}connect(){}disconnect(){}}
 class Socket {constructor(){this.readyState=1;this.sent=[];sockets.push(this);}send(value){this.sent.push(JSON.parse(value));}close(){this.closed=true;}}
 const env={AudioContext:Audio,AudioWorkletNode:Worklet,WebSocket:Socket,navigator:{mediaDevices:{getUserMedia:async()=>{if(denied)throw Object.assign(new Error(),{name:'NotAllowedError'});return {getTracks:()=>tracks};}}}};
 const sandbox={window:env,Blob,URL,Map,Set,Uint8Array,DataView,Float32Array,setTimeout,clearTimeout,atob,btoa};vm.createContext(sandbox);vm.runInContext(source,sandbox);
 const live=sandbox.make({phase:v=>events.push(['phase',v]),end:(h,r)=>events.push(['end',r]),transcript:(r,t)=>events.push(['text',t]),tool:v=>events.push(['tool',v]),resources:v=>events.push(['resources',v])},env);
 return {live,events,sockets,tracks,env};
}
const credential={token:'test-only',model:'test-model',session_id:'test-session'};
test('save receipt returns to same socket without stopping voice, and next action works',async()=>{
 const f=fixture();await f.live.start(credential);const socket=f.sockets[0];socket.onopen();
 await socket.onmessage({data:JSON.stringify({setupComplete:{}})});
 await socket.onmessage({data:JSON.stringify({toolCall:{functionCalls:[{id:'save-one',name:'save_task',args:{proposal_id:'proposal'}}]}})});
 f.live.receipt({session_id:'wrong-session',call:{id:'save-one'},result:{ok:true}});
 assert.equal(socket.sent.filter(s=>s.toolResponse).length,0);
 f.live.receipt({session_id:'test-session',call:{id:'save-one'},result:{ok:true,saved:true}});
 assert.equal(socket.sent.at(-1).toolResponse.functionResponses[0].response.saved,true);
 assert.equal(f.live.isActive(),true);assert.equal(f.tracks[0].stopped,undefined);
 await socket.onmessage({data:JSON.stringify({toolCall:{functionCalls:[{id:'lookup-two',name:'list_owners',args:{}}]}})});
 assert.equal(f.events.filter(e=>e[0]==='tool').length,2);
 f.live.stop();assert.equal(f.tracks[0].stopped,true);assert.equal(socket.closed,true);
});
test('parallel calls each receive a correlated result, duplicate receipt ignored',async()=>{
 const f=fixture();await f.live.start(credential);const s=f.sockets[0];s.onopen();
 await s.onmessage({data:JSON.stringify({toolCall:{functionCalls:[{id:'a',name:'find_pets',args:{}},{id:'b',name:'show_pets',args:{}}]}})});
 for(const id of ['b','a','a'])f.live.receipt({session_id:'test-session',call:{id},result:{ok:true}});
 assert.equal(s.sent.filter(v=>v.toolResponse).length,2);f.live.stop();
});
test('microphone denial gives typed fallback and no socket',async()=>{
 const f=fixture(true);await f.live.start(credential);
 assert.equal(f.sockets.length,0);assert.equal(f.live.isActive(),false);
 assert.match(f.events.find(e=>e[0]==='end')[1],/microphone access/);
});
test('provider interruption preserves the session and disconnect cleans resources',async()=>{
 const f=fixture();await f.live.start(credential);const s=f.sockets[0];s.onopen();
 await s.onmessage({data:JSON.stringify({serverContent:{interrupted:true}})});assert.equal(f.live.isActive(),true);
 s.onclose();assert.equal(f.live.isActive(),false);assert.equal(f.tracks[0].stopped,true);
});

test('Stop during pending permission releases a late microphone without connecting',async()=>{
 const f=fixture();let allow;
 f.env.navigator.mediaDevices.getUserMedia=()=>new Promise(resolve=>{allow=resolve;});
 const starting=f.live.start(credential);await new Promise(resolve=>setImmediate(resolve));
 f.live.stop();allow({getTracks:()=>f.tracks});await starting;
 assert.equal(f.tracks[0].stopped,true);assert.equal(f.sockets.length,0);
});

test('late permission from stopped attempt cannot attach to a newer voice session',async()=>{
 const f=fixture(),requests=[];
 f.env.navigator.mediaDevices.getUserMedia=()=>new Promise(resolve=>requests.push(resolve));
 const attemptA=f.live.start(credential);await new Promise(resolve=>setImmediate(resolve));
 f.live.stop();const attemptB=f.live.start({...credential,session_id:'session-b'});
 await new Promise(resolve=>setImmediate(resolve));
 const trackB={id:'track-b',stop(){this.stopped=true;}};
 requests[1]({getTracks:()=>[trackB]});await attemptB;
 requests[0]({getTracks:()=>f.tracks});await attemptA;
 assert.equal(f.sockets.length,1);assert.equal(f.tracks[0].stopped,true);
 assert.equal(trackB.stopped,undefined);assert.equal(f.live.isActive(),true);
 f.live.stop();assert.equal(trackB.stopped,true);
});
