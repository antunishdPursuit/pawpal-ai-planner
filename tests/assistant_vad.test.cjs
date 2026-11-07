const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const ort=new Function('process','window','document','require','__dirname',fs.readFileSync('assets/vendor/onnxruntime/ort.wasm.min.js','utf8')+';return ort;')(undefined,{}, {currentScript:null},require,path.resolve('assets/vendor/onnxruntime'));
const code=fs.readFileSync('assets/assistant_vad.js','utf8').replaceAll('export async function','async function').replaceAll('export function','function')+'\n'+fs.readFileSync('assets/assistant_audio.js','utf8').replaceAll('export function','function')+';this.detector=createVoiceDetector;this.turns=createSpeechTurns;';
const binary=fs.readFileSync('assets/vendor/silero/silero_vad_v5.onnx').toString('base64');
const wasm=fs.readFileSync('assets/vendor/onnxruntime/ort-wasm-simd.wasm').toString('base64');
async function fixture(){
 const context=vm.createContext({WebAssembly,Uint8Array,Int16Array,Float32Array,DataView,Math,Number,Error,BigInt64Array,ort,atob,btoa});vm.runInContext(code,context);
 const detector=await context.detector(binary,wasm),events=[],probabilities=[],sent=[];
 const turns=context.turns({preview:()=>null,start:r=>events.push(['start',r.turn]),end:r=>events.push(['end',r.turn]),audio:part=>sent.push(part.slice()),error:e=>{throw Error(e);}},detector);
 const gate=context.createSpeechGate(detector,(chunk,probability)=>{probabilities.push(probability);turns.pushClassified(chunk,16000,probability>=.65);},error=>{throw error;});
 return {detector,turns,events,gate,probabilities,sent,async push(chunk,rate=16000){for(let i=0;i<chunk.length;i+=128){gate.push(chunk.slice(i,i+128),rate);await gate.drain();}}};
}
function recordedSpeech(){const raw=fs.readFileSync('tests/fixtures/webrtc/test-audio.raw');return Float32Array.from({length:Math.floor(raw.length/2)*2},(_,i)=>raw.readInt16LE(Math.floor(i/2)*2)/32768);}
test('real WASM detector rejects digital silence, quiet noise, louder stationary noise and a 50ms tone',async()=>{
 for(const kind of ['silence','quiet','noise','tone']){
  const f=await fixture();let seed=1;
  for(let n=0;n<300;n++){
   const chunk=Float32Array.from({length:160},(_,i)=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return kind==='tone'?(n<5?.03*Math.sin(2*Math.PI*1000*(n*160+i)/16000):0):kind==='silence'?0:(kind==='quiet'?.001:.05)*(2*seed/4294967296-1);});
   await f.push(chunk,16000);
  }
  assert.equal(f.events.length,0,kind);await f.detector.destroy();
 }
});
test('real speech fixture survives irregular capture chunks and closes as one audio turn',async()=>{
 const f=await fixture(),speech=recordedSpeech();
 for(let i=0;i<speech.length;i+=128)await f.push(speech.slice(i,i+128),16000);
 await f.push(new Float32Array(16000),16000);
 assert.deepEqual(f.events,[['start',1],['end',1]]);assert.ok(f.turns.latest().closed);await f.detector.destroy();
});
test('an isolated clipped fragment does not become a phantom request',async()=>{
 const f=await fixture();await f.push(recordedSpeech().slice(4800,7360),16000);await f.push(new Float32Array(16000),16000);
 assert.deepEqual(f.events,[]);await f.detector.destroy();
});


test('neural model rejects 30 seconds of repeated bursts and keyboard-like transients',async()=>{
 for(const kind of ['bursts','keys']){
  const f=await fixture();let seed=1;
  for(let n=0;n<3000;n++){
   const frame=Float32Array.from({length:160},(_,i)=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;const noise=2*seed/4294967296-1,k=n*160+i;
    return kind==='bursts'?(n%200<40?.07*noise:0):.2*noise*Math.exp(-(k%1120)/70);
   });await f.push(frame);
  }
  assert.deepEqual(f.events,[],kind);assert.ok(Math.max(...f.probabilities)<.65,kind);await f.detector.destroy();
 }
});

test('recognizable short yes, no, and stop utterances remain usable',async()=>{
 for(const word of ['yes','no','stop']){
  const f=await fixture(),wav=fs.readFileSync('tests/fixtures/voice/speech-'+word+'.wav');
  const start=wav.indexOf(Buffer.from('data'))+8,length=wav.readUInt32LE(start-4);
  const speech=Float32Array.from({length:length/2},(_,i)=>wav.readInt16LE(start+i*2)/32768);
  await f.push(speech);await f.push(new Float32Array(20000));
  assert.deepEqual(f.events,[['start',1],['end',1]],word+': '+Math.max(...f.probabilities));await f.detector.destroy();
 }
});


test('queued recurrent inference is serial and invalidation discards stale frames',async()=>{
 const context=vm.createContext({Float32Array,Number,Promise,Math,Error});
 vm.runInContext(fs.readFileSync('assets/assistant_vad.js','utf8').replaceAll('export async function','async function').replaceAll('export function','function'),context);
 let release,running=0,maxRunning=0,resets=0;const accepted=[];
 const detector={reset(){resets++;},async process(){running++;maxRunning=Math.max(maxRunning,running);await new Promise(r=>release=r);running--;return .9;}};
 const gate=context.createSpeechGate(detector,(f,p,tag)=>accepted.push(tag),e=>{throw e;});
 gate.push(new Float32Array(1025),16000,'old-preview');await new Promise(setImmediate);
 gate.invalidate();release();await gate.drain();assert.deepEqual(accepted,[]);
 gate.push(new Float32Array(513),16000,'new-preview');await new Promise(setImmediate);release();await gate.drain();
 assert.deepEqual(accepted,['new-preview']);assert.equal(maxRunning,1);assert.equal(resets,1);
});

test('48kHz input is resampled to bounded 16kHz model frames',async()=>{
 const context=vm.createContext({Float32Array,Number,Promise,Math,Error});
 vm.runInContext(fs.readFileSync('assets/assistant_vad.js','utf8').replaceAll('export async function','async function').replaceAll('export function','function'),context);
 const lengths=[],detector={reset(){},async process(frame,rate){lengths.push([frame.length,rate]);return 0;}};
 const gate=context.createSpeechGate(detector,()=>{},e=>{throw e;});
 gate.push(new Float32Array(3073),48000);await gate.drain();assert.deepEqual(lengths,[[512,16000],[512,16000]]);
});


test('detector startup warms the model and releases a failed session before capture',async()=>{
 const context=vm.createContext({Uint8Array,Float32Array,BigInt64Array,Number,Promise,Error,atob});
 vm.runInContext(fs.readFileSync('assets/assistant_vad.js','utf8').replaceAll('export async function','async function').replaceAll('export function','function'),context);
 let released=false,frames=0;
 const runtime={env:{wasm:{}},Tensor:class{},InferenceSession:{async create(){return {async run(){frames++;throw Error('warm-up failed');},async release(){released=true;}};}}};
 await assert.rejects(context.createVoiceDetector('','',runtime),/warm-up failed/);assert.equal(frames,1);assert.equal(released,true);
});


test('guarded noise in pre-roll cannot make real neural keyboard classification open a turn',async()=>{
 const f=await fixture();f.turns.seed([new Float32Array(3200).fill(.03)],16000,null);let seed=8;
 for(let n=0;n<300;n++){
  const frame=Float32Array.from({length:160},(_,i)=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return .2*(2*seed/4294967296-1)*Math.exp(-((n*160+i)%1120)/70);});
  await f.push(frame);
 }
 assert.deepEqual(f.events,[]);await f.detector.destroy();
});


test('real Silero speech confirmation preserves a seeded first-phoneme prefix',async()=>{
 const f=await fixture(),wav=fs.readFileSync('tests/fixtures/voice/speech-yes.wav');
 const start=wav.indexOf(Buffer.from('data'))+8,length=wav.readUInt32LE(start-4);
 const samples=Float32Array.from({length:length/2},(_,i)=>wav.readInt16LE(start+i*2)/32768);
 const onset=samples.findIndex(v=>Math.abs(v)>.004),speech=samples.slice(onset),prefix=speech.slice(0,1600);
 f.turns.seed([prefix],16000,null);assert.equal(f.events.length,0);assert.equal(f.sent.length,0);
 await f.push(speech.slice(1600));await f.push(new Float32Array(16000));
 assert.deepEqual(f.events,[['start',1],['end',1]]);assert.deepEqual([...f.sent[0]],[...prefix]);await f.detector.destroy();
});
