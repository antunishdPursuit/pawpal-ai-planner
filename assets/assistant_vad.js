/** Silero V5 speech probability, entirely local. Pinned assets: vendor/. */
export async function createVoiceDetector(model, wasm, runtime=ort) {
 const decode=value=>Uint8Array.from(atob(value),c=>c.charCodeAt(0));
 runtime.env.logLevel='error';runtime.env.wasm.numThreads=1;runtime.env.wasm.simd=true;runtime.env.wasm.proxy=false;
 runtime.env.wasm.wasmPaths={'ort-wasm-simd.wasm':'data:application/octet-stream;base64,'+wasm};
 const session=await runtime.InferenceSession.create(decode(model),{executionProviders:['wasm'],logSeverityLevel:3});
 const fresh=()=>new runtime.Tensor('float32',new Float32Array(256),[2,1,128]);
 const sr=new runtime.Tensor('int64',BigInt64Array.from([16000n]),[]);
 let state=fresh(),disposed=false;
 const detector={frameSamples:512,
  async process(frame,rate){
   if(disposed||rate!==16000||frame.length!==512)throw new Error('Invalid speech frame');
   const result=await session.run({input:new runtime.Tensor('float32',frame,[1,512]),state,sr});
   if(disposed)return 0;state=result.stateN;return Number(result.output.data[0]);
  },
  reset(){state=fresh();},
  async destroy(){if(!disposed){disposed=true;await session.release();}}
 };
 try{await detector.process(new Float32Array(512),16000);detector.reset();return detector;}
 catch(error){await detector.destroy();throw error;}
}

/** Serialize recurrent inference and discard stale audio on mute/Stop/output gates. */
export function createSpeechGate(detector,accept,fail) {
 let epoch=0,tail=Promise.resolve(),pending=0,remainder=new Float32Array(0),source=new Float32Array(0),position=0,reset=false;
 let metadata=null;
 function clear(){epoch++;remainder=new Float32Array(0);source=new Float32Array(0);position=0;metadata=null;reset=true;}
 function push(chunk,rate,preview){
  if(!Number.isFinite(rate)||rate<16000||rate>96000)throw new Error('Unsupported microphone rate');
  const input=new Float32Array(source.length+chunk.length);input.set(source);input.set(chunk,source.length);
  const normalized=[],step=rate/16000;
  while(position+1<input.length){const i=Math.floor(position),fraction=position-i;normalized.push(input[i]*(1-fraction)+input[i+1]*fraction);position+=step;}
  const used=Math.floor(position);source=input.slice(Math.min(used,input.length));position-=Math.min(used,input.length);
  if(!remainder.length)metadata=preview;
  const combined=new Float32Array(remainder.length+normalized.length);combined.set(remainder);combined.set(normalized,remainder.length);
  let offset=0;
  for(;offset+512<=combined.length;offset+=512){
   if(pending>=32){clear();fail(new Error('Speech detector could not keep up'));return;}
   const frame=combined.slice(offset,offset+512),captured=epoch,tag=metadata;pending++;
   tail=tail.then(async()=>{
    if(captured!==epoch)return;
    if(reset){detector.reset();reset=false;}
    const probability=await detector.process(frame,16000);
    if(captured===epoch)accept(frame,probability,tag);
   }).catch(error=>{if(captured===epoch){clear();fail(error);}}).finally(()=>pending--);
   metadata=preview;
  }
  remainder=combined.slice(offset);
 }
 return {push,invalidate:clear,drain:()=>tail};
}
