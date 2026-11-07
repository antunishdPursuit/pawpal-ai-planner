const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const assets=JSON.parse(fs.readFileSync('assets/livy/sable.json','utf8'));
const source=fs.readFileSync('assets/sable.js','utf8').replace('export function','function')+';globalThis.make=createSable;';
class Events {
 constructor(){this.listeners=new Map();}
 addEventListener(type,fn){if(!this.listeners.has(type))this.listeners.set(type,new Set());this.listeners.get(type).add(fn);}
 removeEventListener(type,fn){this.listeners.get(type)?.delete(fn);}
 emit(type){for(const fn of this.listeners.get(type)||[])fn();}
}
async function fixture({reduced=false,width=1280}={}) {
 const document=Object.assign(new Events(),{hidden:false});
 const media=Object.assign(new Events(),{matches:reduced});
 const button=Object.assign(new Events(),{style:{},dataset:{}}),draws=[];
 const canvas={dataset:{},getContext:()=>({clearRect(){},drawImage(...args){draws.push(args.slice(1));}})};
 let now=0,id=0;const frames=new Map();
 class Image {set src(value){this.value=value;queueMicrotask(()=>this.onload());}}
 const env=Object.assign(new Events(),{document,Image,innerWidth:width,matchMedia:()=>media,
  requestAnimationFrame(fn){frames.set(++id,fn);return id;},cancelAnimationFrame(key){frames.delete(key);}});
 const context=vm.createContext({Set,Map,Promise,Math,Error});vm.runInContext(source,context);
 const pet=context.make(canvas,button,assets,env);await pet.ready;
 function advance(ms){for(let left=ms;left>0;){const dt=Math.min(16,left);left-=dt;now+=dt;const callbacks=[...frames.values()];frames.clear();for(const cb of callbacks)cb(now);}}
 advance(16);
 return {pet,canvas,button,draws,advance,env,media,frames,document};
}
test('sleep wakes through the approved eye-opening clip before listening and thinking',async()=>{
 const f=await fixture();assert.equal(f.canvas.dataset.state,'sleep');
 f.pet.setIntent('listen');assert.equal(f.canvas.dataset.state,'wake');f.advance(1000);assert.equal(f.canvas.dataset.state,'listen');
 f.pet.setIntent('think');f.advance(2600);assert.equal(f.canvas.dataset.state,'think');f.pet.cleanup();
});
test('interrupted eye opening reverses on the same atlas cell',async()=>{
 const f=await fixture();f.pet.setIntent('awake');f.advance(400);assert.equal(f.canvas.dataset.state,'wake');
 const before=f.draws.at(-1);f.pet.setIntent('sleep');assert.equal(f.canvas.dataset.state,'settle');assert.deepEqual(f.draws.at(-1),before);
 f.advance(1500);assert.equal(f.canvas.dataset.state,'sleep');f.pet.cleanup();
});
test('short work/reply events show a gesture instead of disappearing inside a resting hold',async()=>{
 const f=await fixture();f.pet.setIntent('awake');f.advance(1000);
 f.pet.setIntent('think');assert.equal(f.canvas.dataset.state,'think');assert.equal(f.canvas.dataset.frame,'1');
 f.pet.setIntent('friendly');f.advance(100);assert.equal(f.canvas.dataset.state,'think');
 f.advance(400);assert.equal(f.canvas.dataset.state,'friendly');assert.notEqual(f.canvas.dataset.frame,'0');f.pet.cleanup();
});
test('listening yields promptly through its existing return poses when work starts',async()=>{
 const f=await fixture();f.pet.setIntent('listen');f.advance(1100);const before=f.draws.at(-1);
 f.pet.setIntent('think');assert.deepEqual(f.draws.at(-1),before);
 f.advance(500);assert.equal(f.canvas.dataset.state,'think');assert.notEqual(f.canvas.dataset.frame,'0');f.pet.cleanup();
});
test('stand-up and lying-down reverse from the displayed posture without endpoint reset',async()=>{
 const f=await fixture();f.pet.setIntent('walk');f.advance(1200);assert.equal(f.canvas.dataset.state,'stand');
 const before=f.canvas.dataset.pose;assert.notEqual(before,'6');f.pet.setIntent('think');assert.equal(f.canvas.dataset.state,'lie');assert.equal(f.canvas.dataset.pose,before);
 f.pet.setIntent('walk');assert.equal(f.canvas.dataset.state,'stand');assert.equal(f.canvas.dataset.pose,before);
 f.advance(2500);assert.equal(f.canvas.dataset.state,'walk');f.pet.setIntent('awake');f.advance(1000);assert.equal(f.canvas.dataset.state,'lie');
 const downPose=f.canvas.dataset.pose;f.pet.setIntent('walk');assert.equal(f.canvas.dataset.state,'stand');assert.equal(f.canvas.dataset.pose,downPose);f.pet.cleanup();
});
test('bounded ambient walk returns running, lies down, and sleeps; hover freezes travel',async()=>{
 const f=await fixture({width:320});f.pet.wander();f.advance(3500);
 assert.ok(Number(f.canvas.dataset.x)<0);assert.ok(Number(f.canvas.dataset.x)>=-132);
 f.button.emit('pointerenter');const x=f.canvas.dataset.x,frame=f.canvas.dataset.frame;f.advance(1000);assert.equal(f.canvas.dataset.x,x);assert.equal(f.canvas.dataset.frame,frame);
 f.button.emit('focus');f.button.emit('pointerleave');f.advance(1000);assert.equal(f.canvas.dataset.x,x);
 f.button.emit('blur');f.advance(18000);assert.equal(f.canvas.dataset.state,'sleep');assert.equal(f.canvas.dataset.x,'0');f.pet.cleanup();
});
test('pause and hidden document freeze the clock; cleanup releases the animation and listeners',async()=>{
 const f=await fixture();f.pet.setIntent('listen');f.advance(1100);f.pet.setPaused(true);const frame=f.canvas.dataset.frame;
 f.advance(5000);assert.equal(f.canvas.dataset.frame,frame);f.pet.setPaused(false);f.document.hidden=true;f.advance(4000);assert.equal(f.canvas.dataset.frame,frame);
 f.document.hidden=false;f.advance(16);assert.equal(f.canvas.dataset.frame,frame);
 f.pet.cleanup();assert.equal(f.frames.size,0);assert.equal(f.button.listeners.get('pointerenter').size,0);
});
test('reduced motion uses expressive stills with no roaming',async()=>{
 const f=await fixture({reduced:true});f.pet.setIntent('think');f.advance(32);assert.equal(f.canvas.dataset.state,'think');const frame=f.canvas.dataset.frame;
 f.pet.wander();f.advance(3000);assert.equal(f.canvas.dataset.frame,frame);assert.equal(f.canvas.dataset.x,'0');
 f.pet.setIntent('friendly');f.advance(32);assert.equal(f.canvas.dataset.state,'friendly');assert.equal(f.canvas.dataset.frame,'3');f.pet.cleanup();
});

test('navigation runs before arrival and honors pause or reduced motion immediately',async()=>{
 const f=await fixture();let arrived=0;const states=new Set();const cancel=f.pet.navigate(()=>arrived++);
 for(let i=0;i<180;i++){f.advance(16);states.add(f.canvas.dataset.state);if(arrived)break;}
 assert.ok(states.has('stand'));assert.ok(states.has('run'));assert.equal(arrived,1);assert.equal(f.canvas.dataset.x,'188');assert.equal(f.canvas.dataset.facing,'right');f.advance(2000);assert.equal(arrived,1);cancel();assert.equal(f.canvas.dataset.x,'0');f.pet.cleanup();
 const r=await fixture({reduced:true});let immediate=0;r.pet.navigate(()=>immediate++);assert.equal(immediate,1);r.pet.cleanup();
});

test('page entrance starts offscreen and runs left to the resting position',async()=>{
 const f=await fixture();let arrived=0;const cancel=f.pet.navigate(()=>arrived++,true);
 assert.equal(f.canvas.dataset.x,'188');assert.equal(f.canvas.dataset.facing,'left');
 f.advance(280);assert.ok(Number(f.canvas.dataset.x)>0&&Number(f.canvas.dataset.x)<188);
 f.advance(400);assert.equal(arrived,1);assert.equal(f.canvas.dataset.x,'0');cancel();assert.equal(f.canvas.dataset.x,'0');f.pet.cleanup();
});

test('entrance skips safely when paused and resize does not snap a traveling sprite home',async()=>{
 const f=await fixture();f.pet.setPaused(true);let entered=0;
 f.pet.navigate(()=>entered++,true);assert.equal(entered,1);assert.equal(f.canvas.dataset.x,'0');
 f.pet.setPaused(false);f.pet.navigate(()=>entered++,true);f.advance(200);
 const x=f.canvas.dataset.x;f.env.innerWidth=320;f.env.emit('resize');assert.equal(f.canvas.dataset.x,x);
 f.advance(600);assert.equal(entered,2);assert.equal(f.canvas.dataset.x,'0');f.pet.cleanup();
});
