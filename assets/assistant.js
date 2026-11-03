export default function(args) {
 const host=args.parentElement;
 if(host.pawpalAssistant){host.pawpalAssistant.update(args);return host.pawpalAssistant.cleanup;}
 const root=host.querySelector(".paw-assistant-root");
 root.innerHTML=`<section class="paw-panel" aria-label="PawPal assistant" hidden>
 <header><h2>PawPal assistant</h2><button type="button" class="paw-minimize" aria-label="Minimize assistant">-</button></header>
 <p class="paw-scope">Demo assistant  |  access to all local profiles.</p>
 <div class="paw-messages" role="log" aria-label="Assistant conversation"></div>
 <div class="paw-proposal" aria-label="Task preview" hidden></div>
 <p class="paw-status" role="status">Ask about owners, pets, or care plans.</p>
 <form><textarea aria-label="Message PawPal" placeholder="Ask PawPal..." maxlength="2000" rows="2"></textarea><button type="submit">Send</button></form>
 <div class="paw-voice"><button class="paw-live" type="button" disabled>Prepare voice</button><button class="paw-stop" type="button" hidden>Stop voice</button><span class="paw-wave" aria-label="Voice is live" hidden><i></i><i></i><i></i></span></div>
 </section><button class="paw-orb" aria-label="Open PawPal assistant" aria-expanded="false"><span></span></button>`;
 const el=s=>root.querySelector(s),panel=el('.paw-panel'),orb=el('.paw-orb'),status=el('.paw-status'),log=el('.paw-messages'),form=el('form'),text=el('textarea');
 let current=args,outbox=[],seen=new Set(),busy=false,preparing=false,usedCredential=null,lastRole=null;
 let voicePhase='idle',voiceStatus='Ask about owners, pets, or care plans.';
 const liveButton=el('.paw-live'),stopButton=el('.paw-stop'),wave=el('.paw-wave');
 const audio=createLive({
  phase(value){voicePhase=value;voiceStatus={idle:'Voice stopped. You can keep chatting.',connecting:'Connecting microphone...',listening:'Live is on. Listening...',speaking:'PawPal is speaking...',working:'Working in PawPal...'}[value];controls();},
  transcript(role,value){if(lastRole===role&&log.lastElementChild){log.lastElementChild.append(document.createTextNode(value));log.scrollTop=log.scrollHeight;}else message(role,value);lastRole=role;},
  tool(value){emit({kind:'live_tool',...value});},
  cancel(value){emit({kind:'cancel_tools',...value});},
  resources(value){root.dataset.connection=value.connection;root.dataset.track=value.track;},
  end(history,reason,turn){voiceStatus=reason;emit({kind:'voice_end',history,turn,session_id:current.data.credential?.session_id});controls();}
 });
 function controls(){const active=audio.isActive();const c=current.data.credential;
  const available=c&&c.session_id!==usedCredential&&Date.now()/1000-c.issued_at<110;
  liveButton.disabled=busy||preparing||active||!current.data.configured;
  liveButton.textContent=preparing?'Getting voice ready...':available?'Start voice':'Prepare voice';
  liveButton.setAttribute('aria-busy',String(preparing||voicePhase==='connecting'));
  stopButton.hidden=!active;wave.hidden=!active||voicePhase==='connecting';
  orb.setAttribute('aria-label',active?'PawPal assistant, voice is on':'Open PawPal assistant');
  text.disabled=active||preparing;form.querySelector('button').disabled=busy||active||preparing;
  status.textContent=preparing?'Getting voice ready...':busy?'Thinking...':voiceStatus;
 }
 root.dataset.instance=crypto.randomUUID();root.dataset.updates='0';
 function message(role,value){lastRole=null;const item=document.createElement('div');item.className='paw-message';item.dataset.role=role;const label=document.createElement('strong');label.textContent=role==='user'?'You':'PawPal';item.append(label,document.createTextNode(value));log.append(item);while(log.children.length>80)log.firstChild.remove();log.scrollTop=log.scrollHeight;}
 function emit(payload){const event={id:crypto.randomUUID(),...payload};outbox.push(event);current.setStateValue('outbox',outbox.slice());return event.id;}
 function update(next){current=next;root.dataset.updates=String(Number(root.dataset.updates)+1);for(const receipt of next.data.receipts||[]){if(seen.has(receipt.id))continue;seen.add(receipt.id);outbox=outbox.filter(e=>e.id!==receipt.id);if(receipt.message){message('assistant',receipt.message);voiceStatus=receipt.failed?receipt.message:'Ask about owners, pets, or care plans.';}if(receipt.call)audio.receipt(receipt);if(receipt.prepared||receipt.failed)preparing=false;busy=false;}const preview=el('.paw-proposal');preview.hidden=!next.data.proposal;preview.replaceChildren();if(next.data.proposal){const s=next.data.proposal.summary;const item=document.createElement('p');item.textContent=`${s.owner}  |  ${s.pet}\n${s.title}\n${s.date}  |  ${s.time} (${s.timezone})\n${s.repeat}${s.repeat==='CUSTOM'?' every '+s.interval_days+' days':''}\n${s.location||'No location'}\n${s.description||''}`;preview.append(item);for(const conflict of next.data.proposal.conflicts||[]){const warning=document.createElement('p');warning.textContent=conflict;preview.append(warning);}}
 controls();}
 function minimize(){audio.stop();panel.hidden=true;orb.setAttribute('aria-expanded','false');orb.focus();}
 orb.onclick=()=>{if(!panel.hidden){minimize();return;}panel.hidden=false;orb.setAttribute('aria-expanded','true');text.focus();};el('.paw-minimize').onclick=minimize;
 form.onsubmit=e=>{e.preventDefault();const value=text.value.trim();if(!value||busy||audio.isActive()||preparing)return;busy=true;message('user',value);text.value='';emit({kind:'chat',text:value});status.textContent='Thinking...';form.querySelector('button').disabled=true;};
 text.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();form.requestSubmit();}};
 root.onkeydown=e=>{if(e.key==='Escape'&&!panel.hidden){e.stopPropagation();minimize();}};
 liveButton.onclick=()=>{const c=current.data.credential;if(c&&c.session_id!==usedCredential&&Date.now()/1000-c.issued_at<110){usedCredential=c.session_id;lastRole=null;emit({kind:'voice_start',session_id:c.session_id});audio.start(c);}else{preparing=true;emit({kind:'prepare_voice'});controls();}};
 stopButton.onclick=()=>audio.stop();
 const hide=()=>{if(document.hidden)audio.stop('Voice stopped because this page was hidden.');};document.addEventListener('visibilitychange',hide);
 function cleanup(){audio.stop();document.removeEventListener('visibilitychange',hide);delete host.pawpalAssistant;}
 host.pawpalAssistant={update,cleanup};update(args);return cleanup;
}
