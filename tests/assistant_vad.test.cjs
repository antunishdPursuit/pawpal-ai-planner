const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const code=fs.readFileSync('assets/assistant_vad.js','utf8').replace('export async function','async function')+'\n'+fs.readFileSync('assets/assistant_audio.js','utf8').replaceAll('export function','function')+';this.detector=createVoiceDetector;this.turns=createSpeechTurns;';
const binary=fs.readFileSync('assets/vendor/libfvad/libfvad.wasm').toString('base64');
async function fixture(){
 const context=vm.createContext({WebAssembly,Uint8Array,Int16Array,Float32Array,DataView,Math,Number,Error,atob,btoa});vm.runInContext(code,context);
 const detector=await context.detector(binary),events=[];
 const turns=context.turns({preview:()=>null,start:r=>events.push(['start',r.turn]),end:r=>events.push(['end',r.turn]),audio(){},error:e=>{throw Error(e);}},detector);
 return {detector,turns,events};
}
function recordedSpeech(){const raw=fs.readFileSync('tests/fixtures/webrtc/test-audio.raw');return Float32Array.from({length:Math.floor(raw.length/2)*2},(_,i)=>raw.readInt16LE(Math.floor(i/2)*2)/32768);}
test('real WASM detector rejects digital silence, quiet noise, louder stationary noise and a 50ms tone',async()=>{
 for(const kind of ['silence','quiet','noise','tone']){
  const f=await fixture();let seed=1;
  for(let n=0;n<300;n++){
   const chunk=Float32Array.from({length:160},(_,i)=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return kind==='tone'?(n<5?.03*Math.sin(2*Math.PI*1000*(n*160+i)/16000):0):kind==='silence'?0:(kind==='quiet'?.001:.05)*(2*seed/4294967296-1);});
   f.turns.push(chunk,16000);
  }
  assert.equal(f.events.length,0,kind);f.detector.destroy();
 }
});
test('real speech fixture survives irregular capture chunks and closes as one audio turn',async()=>{
 const f=await fixture(),speech=recordedSpeech();
 for(let i=0;i<speech.length;i+=128)f.turns.push(speech.slice(i,i+128),16000);
 f.turns.push(new Float32Array(16000),16000);
 assert.deepEqual(f.events,[['start',1],['end',1]]);assert.ok(f.turns.latest().closed);f.detector.destroy();
});
test('a short 160ms segment of recorded speech can start a turn',async()=>{
 const f=await fixture();f.turns.push(recordedSpeech().slice(4800,7360),16000);f.turns.push(new Float32Array(16000),16000);
 assert.deepEqual(f.events,[['start',1],['end',1]]);f.detector.destroy();
});
