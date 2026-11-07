const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/assistant_audio.js','utf8').replaceAll('export function','function')+';globalThis.make=createLive;';
function fixture(denied=false){
 const worklets=[],events=[],sockets=[],players=[],tracks=[{id:'track-one',stop(){this.stopped=true;}}];
 class Audio {constructor(){this.sampleRate=16000;this.currentTime=0;this.audioWorklet={addModule:async()=>{}};}async resume(){}async close(){this.closed=true;}createGain(){return {gain:{},connect(){},disconnect(){}};}createMediaStreamSource(){return {connect(){},disconnect(){}};}createBuffer(c,n,rate){return {duration:n/rate,getChannelData:()=>new Float32Array(n)};}createBufferSource(){const p={connect(){},start(){},stop(){},onended:null};players.push(p);return p;}}
 class Worklet {constructor(){this.port={};worklets.push(this);}connect(){}disconnect(){}}
 class Socket {constructor(){this.readyState=1;this.sent=[];sockets.push(this);}send(value){this.sent.push(JSON.parse(value));}close(){this.closed=true;}}
 const env={AudioContext:Audio,AudioWorkletNode:Worklet,WebSocket:Socket,navigator:{mediaDevices:{getUserMedia:async()=>{if(denied)throw Object.assign(new Error(),{name:'NotAllowedError'});return {getTracks:()=>tracks};}}}};
 const sandbox={window:env,Blob,URL,Map,Set,Uint8Array,DataView,Float32Array,setTimeout,clearTimeout,atob,btoa};vm.createContext(sandbox);vm.runInContext(source,sandbox);
 const live=sandbox.make({phase:v=>events.push(['phase',v]),end:(h,r)=>events.push(['end',r]),transcript:(r,t)=>events.push(['text',t]),tool:v=>events.push(['tool',v]),turn:v=>events.push(['turn',v]),commit:v=>events.push(['commit',v]),cancel:v=>events.push(['cancel',v]),resources:v=>events.push(['resources',v]),detector:async()=>({process:frame=>frame.some(x=>Math.abs(x)>.01),destroy(){}})},env);
 return {live,events,sockets,tracks,env,worklets,players};
}
function speak(f){f.worklets.at(-1).port.onmessage({data:new Float32Array(8000).fill(.1)});f.worklets.at(-1).port.onmessage({data:new Float32Array(16000)});}
const credential={token:'test-only',model:'test-model',session_id:'test-session'};

test('spoken input shows listening then working as soon as the utterance closes',async()=>{
 const f=fixture();await f.live.start(credential);const s=f.sockets[0];s.onopen();await s.onmessage({data:JSON.stringify({setupComplete:{}})});
 const push=data=>f.worklets.at(-1).port.onmessage({data});push(new Float32Array(3200).fill(.1));
 assert.equal(f.events.filter(e=>e[0]==='phase').at(-1)[1],'hearing');
 push(new Float32Array(16000));assert.equal(f.events.filter(e=>e[0]==='phase').at(-1)[1],'working');
 assert.equal(f.events.filter(e=>e[0]==='turn'&&e[1].closed).length,1);
 await s.onmessage({data:JSON.stringify({serverContent:{turnComplete:true}})});
 assert.equal(f.events.filter(e=>e[0]==='phase').at(-1)[1],'listening');f.live.stop();
});
test('save receipt returns to same socket without stopping voice, and next action works',async()=>{
 const f=fixture();await f.live.start(credential);const socket=f.sockets[0];socket.onopen();
 await socket.onmessage({data:JSON.stringify({setupComplete:{}})});
 speak(f);await socket.onmessage({data:JSON.stringify({toolCall:{functionCalls:[{id:'save-one',name:'save_task',args:{proposal_id:'proposal'}}]}})});
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
 speak(f);await s.onmessage({data:JSON.stringify({toolCall:{functionCalls:[{id:'a',name:'find_pets',args:{}},{id:'b',name:'show_pets',args:{}}]}})});
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

test('delayed and interleaved transcripts never change audio turn or save audio',async()=>{
 const f=fixture();await f.live.start(credential);const s=f.sockets[0];s.onopen();
 await s.onmessage({data:JSON.stringify({setupComplete:{}})});
 speak(f);
 await s.onmessage({data:JSON.stringify({serverContent:{inputTranscription:{text:'Create a walk.'}}})});
 await s.onmessage({data:JSON.stringify({toolCall:{functionCalls:[{id:'preview',name:'preview_task',args:{}}]}})});
 f.live.receipt({session_id:'test-session',call:{id:'preview'},result:{ok:true}});
 await s.onmessage({data:JSON.stringify({serverContent:{outputTranscription:{text:'Shall I save it?'},turnComplete:true}})});
 speak(f);
 await s.onmessage({data:JSON.stringify({toolCall:{functionCalls:[{id:'save',name:'save_task',args:{proposal_id:'p'}}]}})});
 const save=f.events.filter(e=>e[0]==='tool').at(-1)[1];
 assert.equal(save.turn,2);assert.equal(save.audio_turn,2);assert.ok(save.audio.startsWith('UklGR'));
 await s.onmessage({data:JSON.stringify({serverContent:{inputTranscription:{text:'Yes, '}}})});
 await s.onmessage({data:JSON.stringify({serverContent:{outputTranscription:{text:'Checking.'}}})});
 await s.onmessage({data:JSON.stringify({serverContent:{inputTranscription:{text:'save it.'}}})});
 assert.equal(f.events.filter(e=>e[0]==='turn'&&e[1].closed).length,2);
 assert.equal(f.events.filter(e=>e[0]==='tool'&&e[1].call.name==='save_task').length,1);
 f.live.receipt({session_id:'test-session',call:{id:'save',name:'save_task'},verification_id:'verified'});
 assert.equal(f.events.filter(e=>e[0]==='commit').length,1);
 assert.equal(f.events.find(e=>e[0]==='commit')[1].audio_turn,2);f.live.stop();
});
test('tool request waits for utterance closure, including a negative suffix after a short pause',async()=>{
 const f=fixture();await f.live.start(credential);const s=f.sockets[0];s.onopen();await s.onmessage({data:JSON.stringify({setupComplete:{}})});
 const push=data=>f.worklets.at(-1).port.onmessage({data});
 push(new Float32Array(3200).fill(.1));push(new Float32Array(8000));
 await s.onmessage({data:JSON.stringify({toolCall:{functionCalls:[{id:'save',name:'save_task',args:{}}]}})});
 assert.equal(f.events.filter(e=>e[0]==='tool').length,0);
 push(new Float32Array(3200).fill(.1));push(new Float32Array(16000));
 const tool=f.events.find(e=>e[0]==='tool')[1];const raw=Buffer.from(tool.audio,'base64');
 assert.equal(raw.readUInt32LE(40),(3200+8000+3200+14400)*2);
 assert.equal(f.events.filter(e=>e[0]==='turn'&&e[1].closed).length,1);f.live.stop();
});
test('Stop or a newer utterance prevents committing a delayed verified confirmation',async()=>{
 for(const stop of [false,true]){
  const f=fixture();await f.live.start(credential);const s=f.sockets[0];s.onopen();await s.onmessage({data:JSON.stringify({setupComplete:{}})});speak(f);
  await s.onmessage({data:JSON.stringify({toolCall:{functionCalls:[{id:'save',name:'save_task',args:{}}]}})});
  if(stop)f.live.stop();else speak(f);
  f.live.receipt({session_id:'test-session',call:{id:'save',name:'save_task'},verification_id:'verified'});
  assert.equal(f.events.filter(e=>e[0]==='commit').length,0);f.live.stop();
 }
});
test('overlong utterances stop instead of authorizing a truncated recording',async()=>{
 const f=fixture();await f.live.start(credential);const s=f.sockets[0];s.onopen();await s.onmessage({data:JSON.stringify({setupComplete:{}})});
 const push=data=>f.worklets.at(-1).port.onmessage({data});push(new Float32Array(16000).fill(.1));push(new Float32Array(30*16000).fill(.1));
 assert.equal(f.live.isActive(),false);assert.equal(f.events.filter(e=>e[0]==='tool').length,0);
 assert.match(f.events.find(e=>e[0]==='end')[1],/under 30 seconds/);
});

test('speech stays bound to the preview visible at its first voiced samples',async()=>{
 const f=fixture();await f.live.start(credential);const s=f.sockets[0];s.onopen();await s.onmessage({data:JSON.stringify({setupComplete:{}})});
 const push=data=>f.worklets.at(-1).port.onmessage({data});
 push(new Float32Array(256).fill(.1));f.live.setPreview('late-preview');
 push(new Float32Array(8000).fill(.1));push(new Float32Array(16000));
 await s.onmessage({data:JSON.stringify({toolCall:{functionCalls:[{id:'save',name:'save_task',args:{proposal_id:'late-preview'}}]}})});
 assert.equal(f.events.find(e=>e[0]==='tool')[1].preview_id,null);f.live.stop();
});

test('mute invalidates an open confirmation, pairs activityEnd, blocks capture and resumes on the same socket',async()=>{
 const f=fixture();await f.live.start(credential);const s=f.sockets[0];s.onopen();await s.onmessage({data:JSON.stringify({setupComplete:{}})});
 const push=data=>f.worklets.at(-1).port.onmessage({data});push(new Float32Array(3200).fill(.1));
 await s.onmessage({data:JSON.stringify({toolCall:{functionCalls:[{id:'save',name:'save_task',args:{}}]}})});
 f.live.setMuted(true);assert.equal(f.tracks[0].enabled,false);assert.equal(f.live.isActive(),true);
 assert.equal(s.sent.filter(x=>x.realtimeInput?.activityStart).length,1);assert.equal(s.sent.filter(x=>x.realtimeInput?.activityEnd).length,1);
 const count=s.sent.length;speak(f);assert.equal(s.sent.length,count);
 f.live.receipt({session_id:'test-session',call:{id:'save'},verification_id:'late'});assert.equal(f.events.filter(x=>x[0]==='commit').length,0);
 f.live.setMuted(false);assert.equal(f.tracks[0].enabled,true);speak(f);assert.equal(f.sockets.length,1);assert.equal(f.events.filter(x=>x[0]==='turn'&&x[1].closed).length,1);f.live.stop();
});
test('speaking continues until all scheduled audio ends, including a tool receipt',async()=>{
 const f=fixture();await f.live.start(credential);const s=f.sockets[0];s.onopen();await s.onmessage({data:JSON.stringify({setupComplete:{}})});speak(f);
 await s.onmessage({data:JSON.stringify({toolCall:{functionCalls:[{id:'owners',name:'list_owners',args:{}}]}})});
 await s.onmessage({data:JSON.stringify({serverContent:{modelTurn:{parts:[{inlineData:{data:Buffer.alloc(4800).toString('base64')}}]},turnComplete:true}})});
 f.live.receipt({session_id:'test-session',call:{id:'owners'},result:{ok:true}});assert.equal(f.events.filter(x=>x[0]==='phase').at(-1)[1],'speaking');
 f.players[0].onended();assert.equal(f.events.filter(x=>x[0]==='phase').at(-1)[1],'listening');f.live.stop();
});

test('muting before permission arrives disables the eventual track',async()=>{
 const f=fixture();let allow;f.env.navigator.mediaDevices.getUserMedia=()=>new Promise(r=>{allow=r;});
 const starting=f.live.start(credential);await new Promise(r=>setImmediate(r));f.live.setMuted(true);
 allow({getTracks:()=>f.tracks});await starting;assert.equal(f.tracks[0].enabled,false);assert.equal(f.live.isMuted(),true);f.live.stop();
});

test('provider interruption does not replace an in-progress hearing cue',async()=>{
 const f=fixture();await f.live.start(credential);const s=f.sockets[0];s.onopen();await s.onmessage({data:JSON.stringify({setupComplete:{}})});
 f.worklets.at(-1).port.onmessage({data:new Float32Array(3200).fill(.1)});
 await s.onmessage({data:JSON.stringify({serverContent:{interrupted:true}})});
 assert.equal(f.events.filter(x=>x[0]==='phase').at(-1)[1],'hearing');f.live.stop();
});
