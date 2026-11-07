/** Plays the bundled drawings; assistant events select intent, never redraw art. */
export function createSable(canvas, button, assets, env=window) {
 const ctx=canvas.getContext('2d'),media=env.matchMedia('(prefers-reduced-motion: reduce)');
 const movement=name=>name==='walk'||name==='run';
 const cues=new Set(['awake','listen','think','friendly']);
 let images={},name='sleep',desired='sleep',frames,durations,elapsed=0,last=null,frameRequest,cueDwell=0,exitingCue=false;
 let facing='left',x=0,roaming=false,destination=0,hovered=false,focused=false,paused=false,disposed=false,loaded=false,loops=0;
 const document=env.document;
 function play(next,cell=null) {
  name=next;const clip=assets.clips[name];frames=clip.frames.slice();durations=clip.durations.slice();elapsed=0;
  exitingCue=false;cueDwell=cues.has(name)&&name!=='awake'?200:0;
  // An event enters the gesture now; subsequent loops retain the full timing.
  if(cueDwell)elapsed=durations[0];
  // Enter walking on the exact support pose shared with the posture strip.
  if(name==='walk'){frames=frames.slice(3).concat(frames.slice(0,3));durations=durations.slice(3).concat(durations.slice(0,3));}
  if(cell){const i=frames.findIndex(f=>f[0]===cell[0]&&f[1]===cell[1]);if(i>=0)elapsed=durations.slice(0,i).reduce((a,b)=>a+b,0);}
 }
 function index(){let left=elapsed;for(let i=0;i<durations.length;i++){if(left<durations[i]-1e-7)return i;left-=durations[i];}return durations.length-1;}
 const cell=()=>frames[index()];
 const duration=()=>durations.reduce((a,b)=>a+b,0);
 function base(){const f=cell();return cues.has(name)&&f[1]===0;}
 function reconcile(boundary=false) {
  if(desired===name)return;
  if(name==='stand'||name==='lie'){
   if((name==='stand'&&!movement(desired))||(name==='lie'&&movement(desired)))play(name==='stand'?'lie':'stand',cell());
   return;
  }
  if(name==='wake'||name==='settle'){
   if(name==='wake'&&desired==='sleep')play('settle',cell());
   else if(name==='settle'&&desired!=='sleep')play('wake',cell());
   return;
  }
  if(name==='sleep'){if(desired!=='sleep')play('wake');return;}
  if(movement(name)){
   if(!boundary)return;
   if(movement(desired)){facing=destination<x?'left':'right';play(desired);}
   else if(name==='run')play('walk');
   else {facing='left';play('lie');}
   return;
  }
  if(!boundary&&!base()){
   if(cueDwell<=0&&!exitingCue){
    // Leave through the existing return poses, keeping the displayed cell.
    const visible=cell();let i=frames.length-1;
    while(i>0&&(frames[i][0]!==visible[0]||frames[i][1]!==visible[1]))i--;
    elapsed=durations.slice(0,i).reduce((a,b)=>a+b,0)+Math.max(0,durations[i]-60);
    exitingCue=true;
   }
   return;
  }
  if(movement(desired)){facing='left';play('stand');}
  else if(desired==='sleep')play('settle');
  else play(desired);
 }
 function setIntent(next) {
  if(!assets.clips[next]||!['sleep','awake','listen','think','friendly','walk','run'].includes(next))throw new Error('Unknown companion intent');
  if(next==='sleep'&&Math.abs(x)>.01){roaming=true;destination=0;desired='run';}
  else {desired=next;roaming=false;}
  reconcile();draw();
 }
 function finish() {
  if(assets.clips[name].loop){loops++;elapsed=0;reconcile(true);return;}
  if(name==='stand'){play(movement(desired)?desired:'walk');reconcile(true);}
  else if(name==='lie'){play('awake');reconcile();}
  else if(name==='wake'){play('awake');reconcile();}
  else if(name==='settle'){play('sleep');reconcile();}
 }
 function draw() {
  if(!loaded||disposed)return;
  const [row,col]=cell(),clip=assets.clips[name];
  const image=clip.atlas==='posture'?images.posture:images[movement(name)&&facing==='left'?'left':'right'];
  ctx.clearRect(0,0,156,128);ctx.imageSmoothingEnabled=false;
  ctx.drawImage(image,col*156,row*128,156,128,clip.offset[0],clip.offset[1],156,128);
  button.style.transform='translateX('+Math.round(x)+'px)';
  Object.assign(canvas.dataset,{state:name,intent:desired,frame:String(index()),pose:clip.atlas==='posture'?String(col):'',facing,x:String(Math.round(x)),loops:String(loops),paused:String(paused||media.matches)});
 }
 function travel(dt) {
  if(!roaming||!movement(name)||desired!==name)return;
  const step=(name==='run'?160:70)*dt/1000;
  x+=Math.sign(destination-x)*Math.min(Math.abs(destination-x),step);
  if(Math.abs(destination-x)>.01)return;
  if(destination<0){destination=0;desired='run';}
  else {roaming=false;desired='sleep';}
 }
 function tick(now) {
  if(disposed)return;
  const stopped=paused||media.matches||document.hidden||((hovered||focused)&&roaming);
  if(loaded&&!stopped){
   const dt=last===null?0:Math.min(100,now-last);elapsed+=dt;cueDwell=Math.max(0,cueDwell-dt);travel(dt);
   let guard=0;while(elapsed>=duration()&&guard++<20){const extra=elapsed-duration();finish();elapsed+=extra;}
   reconcile();draw();
  } else if(loaded&&media.matches){
   // Reduced motion communicates current intent using one complete still pose.
   name=movement(desired)?'awake':desired;frames=assets.clips[name].frames.slice();durations=assets.clips[name].durations.slice();
   elapsed=cues.has(name)&&name!=='awake'?durations.slice(0,name==='friendly'?3:Math.min(2,durations.length-1)).reduce((a,b)=>a+b,0):0;
   roaming=false;x=0;draw();
  }
  last=stopped?null:now;frameRequest=env.requestAnimationFrame(tick);
 }
 function wander() {
  if(disposed||paused||media.matches||document.hidden||hovered||focused)return;
  const limit=Math.max(0,Math.min(220,env.innerWidth-188));if(limit<48)return;
  roaming=true;destination=-limit;desired='walk';reconcile();
 }
 const enter=()=>{hovered=true;},leave=()=>{hovered=false;};
 const focus=()=>{focused=true;},blur=()=>{focused=false;};
 button.addEventListener('pointerenter',enter);button.addEventListener('pointerleave',leave);
 button.addEventListener('focus',focus);button.addEventListener('blur',blur);
 const visibility=()=>{last=null;};document.addEventListener('visibilitychange',visibility);
 const resize=()=>{x=Math.max(-Math.max(0,Math.min(220,env.innerWidth-188)),Math.min(0,x));destination=Math.max(-Math.max(0,Math.min(220,env.innerWidth-188)),destination);draw();};
 env.addEventListener('resize',resize);
 play('sleep');
 const ready=Promise.all(Object.entries(assets.images).map(([key,url])=>new Promise((resolve,reject)=>{const image=new env.Image();image.onload=()=>{images[key]=image;resolve();};image.onerror=()=>reject(new Error('Companion image unavailable'));image.src=url;}))).then(()=>{
  if(disposed)return;loaded=true;button.dataset.art='ready';draw();frameRequest=env.requestAnimationFrame(tick);
 }).catch(()=>{if(!disposed){button.dataset.art='unavailable';canvas.hidden=true;}});
 return {ready,setIntent,wander,setPaused(value){paused=Boolean(value);last=null;draw();},isPaused:()=>paused,
  cleanup(){disposed=true;env.cancelAnimationFrame(frameRequest);button.removeEventListener('pointerenter',enter);button.removeEventListener('pointerleave',leave);button.removeEventListener('focus',focus);button.removeEventListener('blur',blur);document.removeEventListener('visibilitychange',visibility);env.removeEventListener('resize',resize);}
 };
}
