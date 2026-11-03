export default function(args) {
 const host=args.parentElement;
 if(host.pawpalAssistant){host.pawpalAssistant.update(args);return host.pawpalAssistant.cleanup;}
 const root=host.querySelector(".paw-assistant-root");
 root.innerHTML=`<section class="paw-panel" aria-label="PawPal assistant" hidden>
 <header><h2>PawPal assistant</h2><button type="button" class="paw-minimize" aria-label="Minimize assistant">−</button></header>
 <p class="paw-scope">Demo assistant · access to all local profiles.</p>
 <div class="paw-messages" role="log" aria-label="Assistant conversation"></div>
 <p class="paw-status" role="status">Ask about owners, pets, or care plans.</p>
 <form><textarea aria-label="Message PawPal" placeholder="Ask PawPal…" maxlength="2000" rows="2"></textarea><button type="submit">Send</button></form>
 <div class="paw-voice"><button class="paw-live" type="button" disabled>Prepare voice</button><button class="paw-stop" type="button" hidden>Stop voice</button><span class="paw-wave" aria-label="Voice is live" hidden><i></i><i></i><i></i></span></div>
 </section><button class="paw-orb" aria-label="Open PawPal assistant" aria-expanded="false"><span></span></button>`;
 const el=s=>root.querySelector(s),panel=el('.paw-panel'),orb=el('.paw-orb'),status=el('.paw-status'),log=el('.paw-messages'),form=el('form'),text=el('textarea');
 let current=args,outbox=[],seen=new Set(),busy=false;
 root.dataset.instance=crypto.randomUUID();root.dataset.updates='0';
 function message(role,value){const item=document.createElement('div');item.className='paw-message';item.dataset.role=role;const label=document.createElement('strong');label.textContent=role==='user'?'You':'PawPal';item.append(label,document.createTextNode(value));log.append(item);while(log.children.length>80)log.firstChild.remove();log.scrollTop=log.scrollHeight;}
 function emit(payload){const event={id:crypto.randomUUID(),...payload};outbox.push(event);current.setStateValue('outbox',outbox.slice());return event.id;}
 function update(next){current=next;root.dataset.updates=String(Number(root.dataset.updates)+1);for(const receipt of next.data.receipts||[]){if(seen.has(receipt.id))continue;seen.add(receipt.id);outbox=outbox.filter(e=>e.id!==receipt.id);if(receipt.message)message('assistant',receipt.message);busy=false;}form.querySelector('button').disabled=busy;status.textContent=busy?'Thinking…':'Ask about owners, pets, or care plans.';}
 function minimize(){panel.hidden=true;orb.setAttribute('aria-expanded','false');orb.focus();}
 orb.onclick=()=>{if(!panel.hidden){minimize();return;}panel.hidden=false;orb.setAttribute('aria-expanded','true');text.focus();};el('.paw-minimize').onclick=minimize;
 form.onsubmit=e=>{e.preventDefault();const value=text.value.trim();if(!value||busy)return;busy=true;message('user',value);text.value='';emit({kind:'chat',text:value});status.textContent='Thinking…';form.querySelector('button').disabled=true;};
 text.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();form.requestSubmit();}};
 root.onkeydown=e=>{if(e.key==='Escape'&&!panel.hidden){e.stopPropagation();minimize();}};
 function cleanup(){delete host.pawpalAssistant;}
 host.pawpalAssistant={update,cleanup};update(args);return cleanup;
}
