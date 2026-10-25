export default function({parentElement,data,setStateValue}) {
 const el=id=>parentElement.querySelector(`#${id}`), dictate=el("dictate"),live=el("live"),stop=el("stop"),review=el("review"),status=el("status"),transcript=el("transcript");
 let stream,input,output,source,processor,silent,socket,timer,connectTimer;
 let mode=null,disposed=false,ended=false,ready=false,proposal=null,history=[],buffers=[],frames=0,parts=[],partFrames=0,nextTime=0;
 const playing=new Set(),message=text=>status.textContent=text;
 const usedKey="pawpal-voice-used-sessions";
 function usedSessions(){try{return JSON.parse(sessionStorage.getItem(usedKey)||"{}");}catch{return {};}}
 function available(){const c=data.credential;return c&&Date.now()/1000-c.issued_at<110&&!usedSessions()[c.session_id];}
 function markUsed(){try{const used=usedSessions(),now=Date.now();for(const id in used)if(now-used[id]>300000)delete used[id];used[data.credential.session_id]=now;sessionStorage.setItem(usedKey,JSON.stringify(used));}catch{}}
 const emit=payload=>{if(!disposed)setStateValue("event",{id:Date.now().toString(36)+Math.random().toString(36),...payload});};
 function controls(active) {
  dictate.disabled=active||!data.configured;live.disabled=active||!data.configured||!data.replace_allowed;
  stop.hidden=!active;review.hidden=!active||!proposal;
  dictate.setAttribute("aria-pressed",String(active&&mode==="dictation"));live.setAttribute("aria-pressed",String(active&&mode==="live"));
 }
 function stopPlayback(){for(const p of playing){try{p.stop();}catch{}}playing.clear();nextTime=0;}
 function release(){
  clearTimeout(timer);clearTimeout(connectTimer);
  if(processor){processor.port.onmessage=null;processor.disconnect();}source?.disconnect();silent?.disconnect();stream?.getTracks().forEach(t=>t.stop());
  if(socket){socket.onmessage=null;socket.onerror=null;socket.onclose=null;socket.close();}
  stopPlayback();input?.close().catch(()=>{});output?.close().catch(()=>{});
  stream=input=output=socket=source=processor=silent=null;buffers=[];parts=[];frames=partFrames=0;
 }
 function base64(bytes){let text="";for(let i=0;i<bytes.length;i+=16384)text+=String.fromCharCode(...bytes.subarray(i,i+16384));return btoa(text);}
 function pcm(chunks,count){const bytes=new Uint8Array(count*2),view=new DataView(bytes.buffer);let i=0;for(const chunk of chunks)for(const v of chunk)view.setInt16(i++*2,Math.round(Math.max(-1,Math.min(1,v))*32767),true);return bytes;}
 function wav(chunks,count,rate){
  const samples=pcm(chunks,count),bytes=new Uint8Array(44+samples.length),v=new DataView(bytes.buffer);
  const text=(at,s)=>{for(let i=0;i<s.length;i++)bytes[at+i]=s.charCodeAt(i);};
  text(0,"RIFF");v.setUint32(4,36+samples.length,true);text(8,"WAVE");text(12,"fmt ");v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);
  v.setUint32(24,rate,true);v.setUint32(28,rate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);text(36,"data");v.setUint32(40,samples.length,true);bytes.set(samples,44);return base64(bytes);
 }
 function append(role,text){
  if(!text)return;if(history.at(-1)?.role===role)history.at(-1).text=(history.at(-1).text+text).slice(-2000);else history.push({role,text:text.slice(-2000)});
  history=history.slice(-6);transcript.textContent=history.map(i=>`${i.role==="user"?"You":"PawPal"}: ${i.text}`).join("\n").slice(-1500);transcript.scrollTop=transcript.scrollHeight;
 }
 function finish(error=""){
  if(ended||disposed)return;ended=true;const which=mode,count=frames,chunks=buffers.slice(),rate=input?.sampleRate,result=!error&&proposal?{...proposal}:null;
  if(result)delete result._callId;release();controls(false);message(error||"Stopped");
  if(which==="dictation"){if(count&&!error)emit({kind:"dictation",audio:wav(chunks,count,rate)});}
  else emit({kind:"live_complete",proposal:result,history,error});
 }
 function send(value){if(socket?.readyState===WebSocket.OPEN)socket.send(JSON.stringify(value));}
 function play(encoded){
  if(!output||ended)return;const raw=atob(encoded),v=new DataView(Uint8Array.from(raw,c=>c.charCodeAt(0)).buffer),buffer=output.createBuffer(1,raw.length/2,24000),channel=buffer.getChannelData(0);
  for(let i=0;i<channel.length;i++)channel[i]=v.getInt16(i*2,true)/32768;
  const p=output.createBufferSource();p.buffer=buffer;p.connect(output.destination);nextTime=Math.max(output.currentTime,nextTime);p.start(nextTime);nextTime+=buffer.duration;playing.add(p);p.onended=()=>playing.delete(p);
 }
 async function microphone(){
  if(disposed||ended)return false;
  if(!navigator.mediaDevices?.getUserMedia||!window.AudioContext)throw new Error("unsupported");
  input=new AudioContext({sampleRate:16000});await input.resume();
  if(disposed||ended)return false;
  const acquired=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true},video:false});
  if(disposed||ended){acquired.getTracks().forEach(t=>t.stop());return false;}stream=acquired;
  const code=`class Capture extends AudioWorkletProcessor {process(inputs){if(inputs[0]?.[0])this.port.postMessage(inputs[0][0].slice());return true;}}registerProcessor("pawpal-capture",Capture);`;
  const url=URL.createObjectURL(new Blob([code],{type:"application/javascript"}));try{await input.audioWorklet.addModule(url);}finally{URL.revokeObjectURL(url);}
  if(disposed||ended)return false;
  source=input.createMediaStreamSource(stream);processor=new AudioWorkletNode(input,"pawpal-capture");silent=input.createGain();silent.gain.value=0;
  processor.port.onmessage=({data:chunk})=>{
   if(ended||disposed)return;
   if(mode==="dictation"){buffers.push(chunk);frames+=chunk.length;if(frames>=input.sampleRate*30)finish();}
   else if(ready){parts.push(chunk);partFrames+=chunk.length;if(partFrames>=1024){send({realtimeInput:{audio:{data:base64(pcm(parts,partFrames)),mimeType:`audio/pcm;rate=${input.sampleRate}`}}});parts=[];partFrames=0;}}
  };
  source.connect(processor);processor.connect(silent);silent.connect(input.destination);return true;
 }
 async function start(which){
  mode=which;ended=false;ready=false;proposal=null;history=[];buffers=[];frames=0;transcript.textContent="";controls(true);message(which==="dictation"?"Listening...":"Connecting...");
  try{
   if(which==="live"){output=new AudioContext({sampleRate:24000});await output.resume();}
   if(disposed||ended)return;
   if(!await microphone())return;if(which==="dictation"){timer=setTimeout(()=>finish(),30000);return;}
   const credential=data.credential;markUsed();
   socket=new WebSocket("wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained?access_token="+encodeURIComponent(credential.token));
   socket.onopen=()=>send({setup:{model:`models/${credential.model}`,generationConfig:{responseModalities:["AUDIO"]}}});
   connectTimer=setTimeout(()=>finish("Voice connection timed out. Try again."),15000);
   socket.onmessage=async event=>{
    if(ended||disposed)return;let raw=event.data;if(raw instanceof Blob)raw=await raw.text();if(ended||disposed)return;let result;try{result=JSON.parse(raw);}catch{finish("Voice response unavailable. Try again.");return;}
    if(result.setupComplete){clearTimeout(connectTimer);ready=true;message("Listening...");timer=setTimeout(()=>finish(),180000);send({clientContent:{turns:[{role:"user",parts:[{text:"Greet the current user briefly and ask what they want to plan."}]}],turnComplete:true}});}
    const c=result.serverContent;
    if(c){
     if(c.interrupted){stopPlayback();proposal=null;review.hidden=true;}
     if(c.inputTranscription?.text){proposal=null;review.hidden=true;append("user",c.inputTranscription.text);}
     if(c.outputTranscription?.text)append("assistant",c.outputTranscription.text);
     for(const p of c.modelTurn?.parts||[])if(p.inlineData?.data){message("PawPal is speaking...");try{play(p.inlineData.data);}catch{message("Audio unavailable. Read the transcript.");}}
     if(c.turnComplete)message(proposal?"Task ready":"Listening...");
    }
    for(const call of result.toolCall?.functionCalls||[]){
     if(call.name!=="preview_task"){send({toolResponse:{functionResponses:[{id:call.id,name:call.name,response:{error:"Unsupported action"}}]}});continue;}
     if(!call.args||typeof call.args!=="object"||Array.isArray(call.args)){proposal=null;review.hidden=true;send({toolResponse:{functionResponses:[{id:call.id,name:call.name,response:{error:"Invalid preview"}}]}});continue;}
     proposal=call.args;proposal._callId=call.id;review.hidden=false;message("Task ready");
     send({toolResponse:{functionResponses:[{id:call.id,name:call.name,response:{status:"preview_ready_not_saved",instruction:"Ask the user to review the task in the app."}}]}});
    }
    if(result.toolCallCancellation?.ids?.includes(proposal?._callId)){proposal=null;review.hidden=true;}
    if(result.goAway)finish("Session ended. Start a new conversation.");
   };
   socket.onerror=()=>finish("Voice connection failed. Try again or type.");socket.onclose=()=>{if(!ended)finish("Voice disconnected. Try again or type.");};
  }catch(error){release();ended=true;controls(false);message(error?.name==="NotAllowedError"?"Allow the microphone to use voice.":"Microphone unavailable. You can type instead.");}
 }
 dictate.onclick=()=>start("dictation");live.textContent=available()?"Start live":"Talk live";
 live.onclick=()=>{if(available())start("live");else{live.disabled=true;message("Preparing voice...");emit({kind:"connect"});}};
 stop.onclick=()=>finish();review.onclick=()=>finish();controls(false);if(!data.configured)message("Voice unavailable");else if(available())message("Ready");
 const hide=()=>{if(mode&&!ended)finish();};window.addEventListener("pagehide",hide);
 return()=>{disposed=true;ended=true;release();window.removeEventListener("pagehide",hide);};
}
