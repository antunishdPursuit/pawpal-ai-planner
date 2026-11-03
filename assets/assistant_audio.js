/** Audio transport owns one socket; app actions run through the server bridge. */
export function createLive(callbacks, env=window) {
 let socket,stream,input,output,source,processor,silent,ready=false,credential;
 let timer,connectTimer,nextTime=0,history=[],turn=0,ended=true,generation=0;
 const playing=new Set(),pending=new Map();
 const phase=value=>callbacks.phase(value);
 function send(value){if(socket?.readyState===1)socket.send(JSON.stringify(value));}
 function stopPlayback(){for(const p of playing){try{p.stop();}catch{}}playing.clear();nextTime=0;}
 function stop(reason='Voice stopped. You can keep chatting.'){
  if(ended)return;ended=true;generation++;ready=false;clearTimeout(timer);clearTimeout(connectTimer);
  for(const item of pending.values())clearTimeout(item.timer);pending.clear();
  if(processor){processor.port.onmessage=null;processor.disconnect();}source?.disconnect();silent?.disconnect();
  stream?.getTracks().forEach(t=>t.stop());stopPlayback();
  if(socket){socket.onmessage=null;socket.onerror=null;socket.onclose=null;socket.close();}
  input?.close().catch(()=>{});output?.close().catch(()=>{});
  socket=stream=input=output=source=processor=silent=null;
  phase('idle');callbacks.end(history,reason,turn);
 }
 function append(role,text){
  if(!text)return;
  if(role==='user'&&history.at(-1)?.role!=='user')turn++;
  if(history.at(-1)?.role===role)history.at(-1).text=(history.at(-1).text+text).slice(-2000);
  else history.push({role,text:text.slice(-2000)});
  history=history.slice(-12);callbacks.transcript(role,text);
 }
 function play(encoded){
  if(!output||ended)return;
  const raw=atob(encoded),view=new DataView(Uint8Array.from(raw,c=>c.charCodeAt(0)).buffer);
  const buffer=output.createBuffer(1,raw.length/2,24000),channel=buffer.getChannelData(0);
  for(let i=0;i<channel.length;i++)channel[i]=view.getInt16(i*2,true)/32768;
  const p=output.createBufferSource();p.buffer=buffer;p.connect(output.destination);
  nextTime=Math.max(output.currentTime,nextTime);p.start(nextTime);nextTime+=buffer.duration;
  playing.add(p);p.onended=()=>playing.delete(p);
 }
 async function microphone(attempt){
  if(!env.navigator.mediaDevices?.getUserMedia||!env.AudioContext)throw new Error('unsupported');
  const capture=new env.AudioContext({sampleRate:16000});input=capture;await capture.resume();
  if(ended||attempt!==generation){capture.close().catch(()=>{});return;}
  const acquired=await env.navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true},video:false});
  if(ended||attempt!==generation){acquired.getTracks().forEach(t=>t.stop());capture.close().catch(()=>{});return;}stream=acquired;
  const code=`class Capture extends AudioWorkletProcessor {process(inputs){if(inputs[0]?.[0])this.port.postMessage(inputs[0][0].slice());return true;}}registerProcessor("pawpal-assistant-capture",Capture);`;
  const url=URL.createObjectURL(new Blob([code],{type:'application/javascript'}));
  try{await capture.audioWorklet.addModule(url);}finally{URL.revokeObjectURL(url);}
  if(ended||attempt!==generation){acquired.getTracks().forEach(t=>t.stop());capture.close().catch(()=>{});return;}
  source=capture.createMediaStreamSource(stream);processor=new env.AudioWorkletNode(input,'pawpal-assistant-capture');silent=input.createGain();silent.gain.value=0;
  processor.port.onmessage=({data:chunk})=>{
   if(!ready||ended)return;const bytes=new Uint8Array(chunk.length*2),view=new DataView(bytes.buffer);
   for(let i=0;i<chunk.length;i++)view.setInt16(i*2,Math.round(Math.max(-1,Math.min(1,chunk[i]))*32767),true);
   let binary='';for(let i=0;i<bytes.length;i+=16384)binary+=String.fromCharCode(...bytes.subarray(i,i+16384));
   send({realtimeInput:{audio:{data:btoa(binary),mimeType:`audio/pcm;rate=${input.sampleRate}`}}});
  };
  source.connect(processor);processor.connect(silent);silent.connect(input.destination);
  callbacks.resources({connection:credential.session_id,track:stream.getTracks()[0]?.id||'active'});
 }
 async function start(value){
  if(!ended)return;const attempt=++generation;ended=false;credential=value;history=[];turn=0;phase('connecting');
  try{
   connectTimer=setTimeout(()=>{if(attempt===generation)stop('Microphone permission was not received. Allow access and try again, or keep typing.');},25000);
   const speaker=new env.AudioContext({sampleRate:24000});output=speaker;await speaker.resume();
   if(ended||attempt!==generation){speaker.close().catch(()=>{});return;}
   await microphone(attempt);if(ended||attempt!==generation)return;
   socket=new env.WebSocket('wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained?access_token='+encodeURIComponent(value.token));
   socket.onopen=()=>send({setup:{model:`models/${value.model}`,generationConfig:{responseModalities:['AUDIO']}}});
   clearTimeout(connectTimer);connectTimer=setTimeout(()=>stop('Voice took too long to connect. Prepare voice and try again.'),15000);
   socket.onmessage=async event=>{
    if(ended||attempt!==generation)return;
    try{
     let raw=event.data;if(raw instanceof Blob)raw=await raw.text();if(ended||attempt!==generation)return;const result=JSON.parse(raw);
     if(result.error){stop('The speech service rejected this session. Prepare voice and try again.');return;}
     if(result.setupComplete){clearTimeout(connectTimer);ready=true;phase('listening');timer=setTimeout(()=>stop('Voice session ended. Prepare voice to continue.'),8*60*1000);send({clientContent:{turns:[{role:'user',parts:[{text:'Greet briefly and ask how you can help with PawPal.'}]}],turnComplete:true}});}
     const c=result.serverContent;
     if(c){
      if(c.interrupted){stopPlayback();phase('listening');}
      if(c.inputTranscription?.text)append('user',c.inputTranscription.text);
      if(c.outputTranscription?.text)append('assistant',c.outputTranscription.text);
      for(const part of c.modelTurn?.parts||[])if(part.inlineData?.data){if(history.at(-1)?.role==='user')history.push({role:'assistant',text:''});play(part.inlineData.data);phase('speaking');}
      if(c.turnComplete){if(history.at(-1)?.role==='user')history.push({role:'assistant',text:''});phase('listening');}
     }
     for(const call of result.toolCall?.functionCalls||[]){
      if(pending.has(call.id))continue;
      const wait=setTimeout(()=>{pending.delete(call.id);send({toolResponse:{functionResponses:[{id:call.id,name:call.name,response:{ok:false,error:'The app did not return an action result. Check the calendar before retrying a save.'}}]}});phase('listening');},35000);
      pending.set(call.id,{name:call.name,timer:wait});phase('working');
      callbacks.tool({session_id:credential.session_id,call,turn,
       utterance:[...history].reverse().find(i=>i.role==='user')?.text||'',history});
     }
     if(result.toolCallCancellation?.ids?.length)callbacks.cancel?.({session_id:credential.session_id,call_ids:result.toolCallCancellation.ids});
     for(const id of result.toolCallCancellation?.ids||[]){const item=pending.get(id);if(item)clearTimeout(item.timer);pending.delete(id);}
     if(result.goAway)stop('The speech service is ending this connection. Prepare voice to reconnect; your chat is retained.');
    }catch{stop('Voice response unavailable. Your chat is retained. Try again.');}
   };
   socket.onerror=()=>stop('Voice connection failed. Check your connection and prepare voice again.');
   socket.onclose=()=>stop('Voice disconnected. Your chat is retained. Prepare voice to reconnect.');
  }catch(error){if(ended||attempt!==generation)return;stop(error?.name==='NotAllowedError'?'Allow microphone access to use voice. You can still type.':'Microphone unavailable. You can still type.');}
 }
 function receipt(value){
  if(ended||value.session_id!==credential?.session_id)return;
  const item=pending.get(value.call?.id);if(!item)return;clearTimeout(item.timer);pending.delete(value.call.id);
  send({toolResponse:{functionResponses:[{id:value.call.id,name:item.name,response:value.result}]}});phase('listening');
 }
 return {start,stop,receipt,isActive:()=>!ended};
}
