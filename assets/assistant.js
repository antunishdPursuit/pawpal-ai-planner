export default function(args) {
 const host=args.parentElement;
 if(host.pawpalAssistant){host.pawpalAssistant.update(args);return host.pawpalAssistant.cleanup;}
 const root=host.querySelector(".paw-assistant-root");
 root.innerHTML=`<section class="paw-panel" aria-label="PawPal assistant" hidden>
 <header><h2>PawPal assistant</h2><button type="button" class="paw-minimize" aria-label="Minimize assistant">-</button></header>
 <p class="paw-scope">Demo assistant  |  access to all local profiles.</p>
 <div class="paw-messages" role="log" aria-label="Assistant conversation"></div>
 <div class="paw-proposal" aria-label="Task preview" hidden></div>
  <p class="paw-status" role="status">Ask about users, pets, or care plans.</p>
 <form><textarea aria-label="Message PawPal" placeholder="Ask PawPal..." maxlength="2000" rows="2"></textarea><button type="submit">Send</button></form>
  <div class="paw-voice"><button class="paw-live" type="button" disabled>Prepare voice</button><button class="paw-mute" type="button" aria-pressed="false" hidden>Mute microphone</button><button class="paw-stop" type="button" hidden>Stop voice</button><span class="paw-wave" aria-label="Speech detected" hidden><i></i><i></i><i></i></span><button class="paw-motion" type="button" aria-pressed="false">Pause animation</button></div>
 </section><div class="paw-companion"><button class="paw-orb" aria-label="Open PawPal assistant" aria-expanded="false" title="Sable · Open PawPal assistant"><canvas width="156" height="128" aria-hidden="true"></canvas><span class="paw-companion-fallback">Chat</span></button></div>`;
 const el=s=>root.querySelector(s),panel=el('.paw-panel'),orb=el('.paw-orb'),status=el('.paw-status'),log=el('.paw-messages'),form=el('form'),text=el('textarea');
 let current=args,outbox=[],seen=new Set((args.data.receipts||[]).map(r=>r.id)),busy=false,preparing=false,usedCredential=null,lastRole=null;
 let voicePhase='idle',voiceStatus='Ask about users, pets, or care plans.',credentialId=null,credentialReceivedAt=0;
 const liveButton=el('.paw-live'),stopButton=el('.paw-stop'),muteButton=el('.paw-mute'),wave=el('.paw-wave');
 const pet=createSable(el('canvas'),orb,JSON.parse(host.querySelector('.paw-sable-assets').textContent));
 let greetingUntil=0,greetingTimer,idleTimer,disposed=false,petHovered=false,petFocused=false,lastIntent,navigationId=null,cancelNavigation;
 const available=()=>{const c=current.data.credential;return c&&c.session_id!==usedCredential&&performance.now()-credentialReceivedAt<110000;};
 function greet(){greetingUntil=Date.now()+2500;clearTimeout(greetingTimer);greetingTimer=setTimeout(()=>{if(!disposed)controls();},2500);}
 function idle(){clearTimeout(idleTimer);idleTimer=setTimeout(()=>{if(disposed||!panel.hidden)return;pet.wander();idle();},45000);}
 const audio=createLive({
  detector:()=>createVoiceDetector(host.querySelector('.paw-voice-detector').textContent),
  phase(value){voicePhase=value;voiceStatus={idle:'Voice stopped. You can keep chatting.',connecting:'Connecting microphone...',listening:'Microphone on. Listening...',hearing:'Speech detected. Listening...',muted:'Microphone muted. PawPal cannot hear you.',speaking:'PawPal is speaking...',working:'Working in PawPal...'}[value];controls();},
  mute(){controls();},
  transcript(role,value){if(lastRole===role&&log.lastElementChild){log.lastElementChild.append(document.createTextNode(value));log.scrollTop=log.scrollHeight;}else message(role,value);lastRole=role;},
  tool(value){emit({kind:'live_tool',...value});},
  turn(value){emit({kind:'voice_turn',...value});},
  commit(value){emit({kind:'live_commit',...value});},
  cancel(value){emit({kind:'cancel_tools',...value});},
  resources(value){root.dataset.connection=value.connection;root.dataset.track=value.track;},
  end(history,reason,turn){voiceStatus=reason;emit({kind:'voice_end',history,turn,session_id:current.data.credential?.session_id});controls();}
 });
 function controls(){const active=audio.isActive();const c=current.data.credential;
  const prepared=available();
  liveButton.disabled=busy||preparing||active||!current.data.configured;
  liveButton.textContent=preparing?'Getting voice ready...':prepared?'Start voice':'Prepare voice';
  liveButton.setAttribute('aria-busy',String(preparing||voicePhase==='connecting'));
  stopButton.hidden=!active;muteButton.hidden=!active;
  const muted=audio.isMuted();muteButton.textContent=muted?'Unmute microphone':'Mute microphone';muteButton.setAttribute('aria-pressed',String(muted));
  wave.hidden=!active||!['hearing','speaking'].includes(voicePhase);wave.setAttribute('aria-label',voicePhase==='speaking'?'PawPal is speaking':'Speech detected');
  orb.setAttribute('aria-label',active?'PawPal assistant, voice is on':'Open PawPal assistant');
  text.disabled=active||preparing;form.querySelector('button').disabled=busy||active||preparing;
  status.textContent=preparing?'Getting voice ready...':busy?'Thinking...':voiceStatus;
  const intent=panel.hidden?(petHovered||petFocused?'listen':'sleep'):busy||preparing||voicePhase==='connecting'||voicePhase==='working'?'think':active&&['listening','hearing'].includes(voicePhase)?'listen':active&&voicePhase==='speaking'||Date.now()<greetingUntil?'friendly':'awake';
  if(intent!==lastIntent){lastIntent=intent;pet.setIntent(intent);}
 }
 root.dataset.instance=crypto.randomUUID();root.dataset.updates='0';
 function message(role,value){lastRole=null;const item=document.createElement('div');item.className='paw-message';item.dataset.role=role;const label=document.createElement('strong');label.textContent=role==='user'?'You':'PawPal';item.append(label,document.createTextNode(value));log.append(item);while(log.children.length>80)log.firstChild.remove();log.scrollTop=log.scrollHeight;}
 function emit(payload){const event={id:crypto.randomUUID(),...payload};outbox.push(event);current.setStateValue('outbox',outbox.slice());return event.id;}
 function update(next){const pendingCount=outbox.length;current=next;if(next.data.credential?.session_id!==credentialId){credentialId=next.data.credential?.session_id;credentialReceivedAt=performance.now();}root.dataset.updates=String(Number(root.dataset.updates)+1);for(const receipt of next.data.receipts||[]){if(seen.has(receipt.id))continue;seen.add(receipt.id);outbox=outbox.filter(e=>e.id!==receipt.id);if(receipt.message){message('assistant',receipt.message);voiceStatus=receipt.failed?receipt.message:'Ask about users, pets, or care plans.';if(!receipt.failed)greet();}if(receipt.call)audio.receipt(receipt);if(receipt.prepared||receipt.failed)preparing=false;busy=false;}const preview=el('.paw-proposal');preview.hidden=!next.data.proposal;preview.replaceChildren();if(next.data.proposal){const s=next.data.proposal.summary;const item=document.createElement('p');item.textContent=`${s.owner}  |  ${s.pet}\n${s.title}\n${s.date}  |  ${s.time} (${s.timezone})\n${s.repeat}${s.repeat==='CUSTOM'?' every '+s.interval_days+' days':''}\n${s.location||'No location'}\n${s.description||''}`;preview.append(item);for(const conflict of next.data.proposal.conflicts||[]){const warning=document.createElement('p');warning.textContent=conflict;preview.append(warning);}}
 audio.setPreview(next.data.proposal?.id);controls();if(outbox.length!==pendingCount)current.setStateValue('outbox',outbox.slice());
 const trip=next.data.navigation,key=trip?trip.id+(trip.entering?':enter':':exit'):null;
 root.dataset.navigation=trip?(trip.entering?'entering':trip.arrived?'acknowledged':'pending'):'none';
 if(key!==navigationId){cancelNavigation?.();navigationId=key;if(trip){
  cancelNavigation=pet.navigate(()=>{
   root.dataset.navigation=trip.entering?'settled':'arrived';
   if(!disposed&&navigationId===key)emit({kind:trip.entering?'navigation_entered':'navigation_done',navigation_id:trip.id});
  },Boolean(trip.entering));
 }}}
 function minimize(){audio.stop();panel.hidden=true;orb.setAttribute('aria-expanded','false');orb.focus();controls();idle();}
 orb.onclick=()=>{if(!panel.hidden){minimize();return;}clearTimeout(idleTimer);panel.hidden=false;orb.setAttribute('aria-expanded','true');greet();controls();text.focus();};el('.paw-minimize').onclick=minimize;
 form.onsubmit=e=>{e.preventDefault();const value=text.value.trim();if(!value||busy||audio.isActive()||preparing)return;busy=true;message('user',value);text.value='';emit({kind:'chat',text:value});controls();};
 text.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();form.requestSubmit();}};
 root.onkeydown=e=>{if(e.key==='Escape'&&!panel.hidden){e.stopPropagation();minimize();}};
 liveButton.onclick=()=>{const c=current.data.credential;if(available()){usedCredential=c.session_id;lastRole=null;emit({kind:'voice_start',session_id:c.session_id});audio.start(c);}else{preparing=true;emit({kind:'prepare_voice'});controls();}};
 stopButton.onclick=()=>audio.stop();
  muteButton.onclick=()=>audio.setMuted(!audio.isMuted());
 const petEnter=()=>{petHovered=true;if(panel.hidden)controls();},petLeave=()=>{petHovered=false;if(panel.hidden){controls();idle();}};
 const petFocus=()=>{petFocused=true;if(panel.hidden)controls();},petBlur=()=>{petFocused=false;if(panel.hidden){controls();idle();}};
 orb.addEventListener('pointerenter',petEnter);orb.addEventListener('pointerleave',petLeave);orb.addEventListener('focus',petFocus);orb.addEventListener('blur',petBlur);
 el('.paw-motion').onclick=()=>{pet.setPaused(!pet.isPaused());el('.paw-motion').textContent=pet.isPaused()?'Resume animation':'Pause animation';el('.paw-motion').setAttribute('aria-pressed',String(pet.isPaused()));};
 const hide=()=>{if(document.hidden)audio.stop('Voice stopped because this page was hidden.');};document.addEventListener('visibilitychange',hide);
 function cleanup(){if(disposed)return;disposed=true;clearTimeout(idleTimer);clearTimeout(greetingTimer);audio.stop();pet.cleanup();orb.removeEventListener('pointerenter',petEnter);orb.removeEventListener('pointerleave',petLeave);orb.removeEventListener('focus',petFocus);orb.removeEventListener('blur',petBlur);document.removeEventListener('visibilitychange',hide);delete host.pawpalAssistant;}
 for(const item of args.data.history||[])message(item.role,item.text);
 host.pawpalAssistant={update,cleanup};update(args);idle();return cleanup;
}
