const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('assets/assistant.js','utf8').replace('export default function','function component')+';globalThis.component=component;';
function node(){return {hidden:false,dataset:{},style:{},attrs:{},children:[],listeners:new Map(),value:'',setAttribute(k,v){this.attrs[k]=v;},addEventListener(k,fn){if(!this.listeners.has(k))this.listeners.set(k,new Set());this.listeners.get(k).add(fn);},removeEventListener(k,fn){this.listeners.get(k)?.delete(fn);},emit(k){for(const fn of this.listeners.get(k)||[])fn();},focus(){this.emit('focus');},replaceChildren(){this.children=[];},append(...values){for(const v of values){v.parent=this;this.children.push(v);}},remove(){const i=this.parent.children.indexOf(this);this.parent.children.splice(i,1);},get firstChild(){return this.children[0];},get lastElementChild(){return this.children.at(-1);}};}
function fixture(realPet=false,initial={}){
 const selectors=['.paw-panel','.paw-orb','.paw-status','.paw-messages','form','textarea','.paw-live','.paw-stop','.paw-mute','.paw-wave','.paw-proposal','.paw-minimize','.paw-motion','canvas'];
 const nodes=Object.fromEntries(selectors.map(s=>[s,node()]));nodes['.paw-panel'].hidden=true;
 const send=node();nodes.form.querySelector=()=>send;const root=Object.assign(node(),{querySelector:s=>nodes[s]});
 const host={querySelector:s=>s==='.paw-assistant-root'?root:{textContent:'{}'}};
 let active=false,callbacks,paused=false,disposed=false,pet,now=0;const intents=[],events=[],timers=new Map(),due=new Map(),frames=new Map();let serial=0;
 const doc=Object.assign(node(),{hidden:false,createElement:()=>node(),createTextNode:text=>({text})});
 const environment=Object.assign(node(),{document:doc,innerWidth:1280,matchMedia:()=>Object.assign(node(),{matches:false}),Image:class {set src(value){queueMicrotask(()=>this.onload());}},requestAnimationFrame(fn){frames.set(++serial,fn);return serial;},cancelAnimationFrame(id){frames.delete(id);}});
 nodes.canvas.getContext=()=>({clearRect(){},drawImage(){}});
 class Clock extends Date {static now(){return now;}}
 const audio={isActive:()=>active,isMuted:()=>false,setMuted(){},setPreview(){},receipt(){},start(){active=true;callbacks.phase('listening');},stop(){active=false;callbacks.phase('idle');callbacks.end([],'Stopped',0);}};
 const context=vm.createContext({JSON,Date:Clock,performance:{now:()=>now},Set,Map,Promise,Math,Error,Number,Boolean,String,crypto:{randomUUID:()=>String(++serial)},
  document:doc,
  setTimeout(fn,ms){timers.set(++serial,fn);due.set(serial,now+ms);return serial;},clearTimeout(id){timers.delete(id);due.delete(id);},
  createLive(value){callbacks=value;return audio;},createSable(canvas,button){pet=realPet?context.realSable(canvas,button,JSON.parse(fs.readFileSync('assets/livy/sable.json','utf8')),environment):{setIntent:value=>intents.push(value),wander(){},isPaused:()=>paused,setPaused:v=>{paused=v;},cleanup(){disposed=true;}};return pet;}});
 if(realPet)vm.runInContext(fs.readFileSync('assets/sable.js','utf8').replace('export function createSable','function realSable'),context);
 vm.runInContext(source,context);
 const args={parentElement:host,data:{configured:true,receipts:[],...initial},setStateValue:(key,value)=>events.push(...value)};
 const cleanup=context.component(args);
 function advance(ms,observe=()=>{}){for(let left=ms;left>0;){const dt=Math.min(16,left);left-=dt;now+=dt;for(const [id,fn] of [...timers]){if(due.get(id)<=now){timers.delete(id);due.delete(id);fn();}}const pending=[...frames.values()];frames.clear();for(const fn of pending)fn(now);observe();}}
 return {nodes,intents,events,host,root,args,cleanup,timers,send,pet,advance,phase:value=>callbacks.phase(value),setActive:value=>{active=value;},disposed:()=>disposed};
}
test('launcher wakes Sable, typed submission thinks, and a receipt retains the existing chat flow',()=>{
 const f=fixture();assert.equal(f.intents.at(-1),'sleep');f.nodes['.paw-orb'].onclick();assert.equal(f.nodes['.paw-panel'].hidden,false);assert.equal(f.intents.at(-1),'friendly');
 f.nodes.textarea.value='Which pets are registered?';f.nodes.form.onsubmit({preventDefault(){}});
 assert.equal(f.intents.at(-1),'think');assert.equal(f.send.disabled,true);assert.equal(f.events.at(-1).kind,'chat');
 f.host.pawpalAssistant.update({...f.args,data:{configured:true,receipts:[{id:f.events.at(-1).id,message:'Here are your pets.'}]}});
 assert.equal(f.intents.at(-1),'friendly');assert.equal(f.send.disabled,false);assert.equal(f.nodes['.paw-messages'].children.length,2);f.cleanup();
});
test('Live phase changes select listening/thinking/friendly drawings without changing the transport',()=>{
 const f=fixture();f.nodes['.paw-orb'].onclick();f.setActive(true);
 f.phase('listening');assert.equal(f.intents.at(-1),'listen');assert.equal(f.nodes.textarea.disabled,true);
 f.phase('working');assert.equal(f.intents.at(-1),'think');f.phase('speaking');assert.equal(f.intents.at(-1),'friendly');
 f.nodes['.paw-minimize'].onclick();assert.equal(f.nodes['.paw-panel'].hidden,true);assert.equal(f.intents.at(-1),'listen');assert.equal(f.nodes['.paw-messages'].children.length,0);f.cleanup();
});
test('hover and keyboard focus wake the closed companion without replacing active Live feedback',()=>{
 const f=fixture(),orb=f.nodes['.paw-orb'];orb.emit('pointerenter');assert.equal(f.intents.at(-1),'listen');
 orb.emit('focus');orb.emit('pointerleave');assert.equal(f.intents.at(-1),'listen');orb.emit('blur');assert.equal(f.intents.at(-1),'sleep');
 orb.onclick();f.setActive(true);f.phase('working');orb.emit('pointerenter');assert.equal(f.intents.at(-1),'think');
 orb.emit('pointerleave');assert.equal(f.intents.at(-1),'think');f.cleanup();assert.equal(orb.listeners.get('pointerenter').size,0);
});
test('animation pause is independent of Live and disposal clears idle/greeting timers',()=>{
 const f=fixture();f.nodes['.paw-orb'].onclick();f.nodes['.paw-motion'].onclick();assert.equal(f.nodes['.paw-motion'].attrs['aria-pressed'],'true');
 f.setActive(true);f.phase('listening');assert.equal(f.intents.at(-1),'listen');assert.equal(f.nodes['.paw-stop'].hidden,false);
 f.nodes['.paw-motion'].onclick();assert.equal(f.nodes['.paw-motion'].attrs['aria-pressed'],'false');f.cleanup();assert.equal(f.disposed(),true);assert.equal(f.timers.size,0);
});

test('real widget and renderer retry a focused idle attempt, retain roam through receipts, run home and sleep',async()=>{
 const f=fixture(true),orb=f.nodes['.paw-orb'],states=new Set();await f.pet.ready;
 orb.emit('focus');f.advance(46000);assert.equal(f.nodes.canvas.dataset.x,'0');
 orb.emit('blur');f.advance(45000);f.advance(3000,()=>states.add(f.nodes.canvas.dataset.state));
 assert.ok(Number(f.nodes.canvas.dataset.x)<0);
 f.host.pawpalAssistant.update({...f.args,data:{configured:true,receipts:[]}});
 f.advance(15000,()=>states.add(f.nodes.canvas.dataset.state));
 assert.ok(states.has('walk'));assert.ok(states.has('run'));assert.equal(f.nodes.canvas.dataset.x,'0');assert.equal(f.nodes.canvas.dataset.state,'sleep');f.cleanup();
});

test('remount restores both speakers once and ignores historical receipts',()=>{
 const f=fixture(false,{history:[{role:'user',text:'How many users?'},{role:'assistant',text:'Three local profiles.'}],receipts:[{id:'old',message:'Three local profiles.'}]});
 const log=f.nodes['.paw-messages'];assert.equal(log.children.length,2);assert.equal(log.children[0].dataset.role,'user');assert.equal(log.children[1].dataset.role,'assistant');assert.equal(f.timers.size,1);f.cleanup();
});
test('voice preparation uses local elapsed time rather than a skewed server clock',()=>{
 const f=fixture();f.host.pawpalAssistant.update({...f.args,data:{configured:true,receipts:[],credential:{session_id:'clock-test',issued_at:-1000000}}});
 assert.equal(f.nodes['.paw-live'].textContent,'Start voice');f.nodes['.paw-live'].onclick();assert.equal(f.events.at(-1).kind,'voice_start');f.cleanup();
});

test('real renderer emits arrival only after running, and the page update restores position',async()=>{
 const f=fixture(true);await f.pet.ready;f.nodes['.paw-orb'].onclick();
 const update=data=>f.host.pawpalAssistant.update({...f.args,data:{configured:true,receipts:[],...data}});
 update({navigation:{id:'trip',page:'Pets'}});assert.equal(f.events.filter(e=>e.kind==='navigation_done').length,0);
 f.advance(4000);assert.equal(f.events.filter(e=>e.kind==='navigation_done').length,1);assert.ok(Number(f.nodes.canvas.dataset.x)<0);
 update({navigation:{id:'trip',page:'Pets'}});assert.equal(f.events.filter(e=>e.kind==='navigation_done').length,1);
 update({page:'Pets',navigation:null});assert.equal(f.nodes.canvas.dataset.x,'0');f.cleanup();
});
