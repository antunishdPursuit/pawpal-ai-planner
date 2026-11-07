/** Local WebRTC speech classifier. Pinned binary and license: vendor/libfvad/. */
export async function createVoiceDetector(encoded, engine=WebAssembly) {
 const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
 const {instance}=await engine.instantiate(bytes),lib=instance.exports;
 const handle=lib.fvad_new(),pointer=lib.malloc(960*2);let rate=0,disposed=false;
 if(!handle||!pointer)throw new Error('Speech detector unavailable');
 lib.fvad_set_mode(handle,2);
 return {
  process(frame,sampleRate){
   if(disposed)throw new Error('Speech detector disposed');
   if(rate!==sampleRate){if(lib.fvad_set_sample_rate(handle,sampleRate)<0)throw new Error('Unsupported microphone rate');rate=sampleRate;}
   const pcm=new Int16Array(lib.memory.buffer,pointer,frame.length);
   for(let i=0;i<frame.length;i++)pcm[i]=Math.round(Math.max(-1,Math.min(1,frame[i]))*32767);
   const result=lib.fvad_process(handle,pointer,frame.length);
   if(result<0)throw new Error('Invalid speech frame');
   return result===1;
  },
  destroy(){if(!disposed){disposed=true;lib.free(pointer);lib.fvad_free(handle);}}
 };
}
