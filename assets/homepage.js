(() => {
  if(window.pawHomeCleanup)window.pawHomeCleanup();
  const main=document.querySelector('[data-testid="stMain"]'),root=document.getElementById('paw-home-top');
  if(!main||!root)return;
  const travel=root.querySelector('.paw-home-travel'),scene=root.querySelector('.paw-home-scene'),room=root.querySelector('.paw-home-room'),
    dog=root.querySelector('.paw-home-dog'),cat=root.querySelector('.paw-home-cat'),copy=root.querySelector('.paw-home-copy'),
    cards=document.getElementById('paw-home-cards'),explore=document.getElementById('paw-explore'),back=document.getElementById('paw-back-top'),
    brand=document.querySelector('.st-key-home_brand button'),reduce=matchMedia('(prefers-reduced-motion: reduce)');
  let queued=false,frame=0,focusCards=false;
  const clamp=n=>Math.max(0,Math.min(1,n));
  const smooth=n=>{n=clamp(n);return n*n*(3-2*n);};
  const behavior=()=>reduce.matches?'auto':'smooth';
  function top(e){focusCards=false;e.preventDefault();e.stopPropagation();main.scrollTo({top:0,behavior:behavior()});root.focus({preventScroll:true});}
  function endPosition(){return main.scrollTop+travel.getBoundingClientRect().top-main.getBoundingClientRect().top-92+travel.offsetHeight-scene.offsetHeight;}
  function go(e){e.preventDefault();if(reduce.matches){cards.scrollIntoView({block:'start',behavior:'auto'});cards.focus({preventScroll:true});}else{focusCards=true;main.scrollTo({top:endPosition(),behavior:behavior()});schedule();}}
  function update(){queued=false;if(!root.isConnected){cleanup();return;}
    const distance=Math.max(1,travel.offsetHeight-scene.offsetHeight),w=scene.clientWidth;
    const p=reduce.matches?0:clamp((main.getBoundingClientRect().top+92-travel.getBoundingClientRect().top)/distance);
    const part=smooth(p/.95),reveal=smooth((p-.12)/.88);
    room.style.transform=`translateY(${-12*p}px)`;
    dog.style.transform=`translateX(${(w*.52+24)*part}px)`;
    cat.style.transform=`translateX(${-(w*.36+24)*part}px)`;
    copy.style.opacity=reduce.matches?'1':String(1-smooth(p/.48));
    copy.style.transform=`translateY(${-32*p}px)`;
    copy.inert=!reduce.matches&&p>.48;
    cards.style.transform=reduce.matches?'translateY(100%)':`translateY(${(1-reveal)*100}%)`;
    cards.inert=!reduce.matches&&reveal<.01;
    if(focusCards&&p>=.999){focusCards=false;cards.focus({preventScroll:true});}
    root.dataset.progress=p.toFixed(3);
  }
  function schedule(){if(!queued){queued=true;frame=requestAnimationFrame(update);}}
  const observer=new MutationObserver(()=>{if(!root.isConnected)cleanup();});
  function cleanup(){main.removeEventListener('scroll',schedule);window.removeEventListener('resize',schedule);reduce.removeEventListener('change',schedule);
    explore.removeEventListener('click',go);back.removeEventListener('click',top);brand?.removeEventListener('click',top);cancelAnimationFrame(frame);observer.disconnect();}
  window.pawHomeCleanup=cleanup;main.addEventListener('scroll',schedule,{passive:true});window.addEventListener('resize',schedule);reduce.addEventListener('change',schedule);
  explore.addEventListener('click',go);back.addEventListener('click',top);brand?.addEventListener('click',top);observer.observe(main,{childList:true,subtree:true});
  main.scrollTo({top:0,behavior:'instant'});update();
})();
