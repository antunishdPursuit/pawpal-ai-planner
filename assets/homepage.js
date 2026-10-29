(() => {
  if (window.pawHomeCleanup) window.pawHomeCleanup();
  const main=document.querySelector('[data-testid="stMain"]'), root=document.getElementById('paw-home-top');
  if (!main || !root) return;
  const travel=root.querySelector('.paw-home-travel'),scene=root.querySelector('.paw-home-scene'),
    room=root.querySelector('.paw-home-room'),dog=root.querySelector('.paw-home-dog'),cat=root.querySelector('.paw-home-cat'),
    copy=root.querySelector('.paw-home-copy'),cards=document.getElementById('paw-home-cards'),
    explore=document.getElementById('paw-explore'),back=document.getElementById('paw-back-top'),
    brand=document.querySelector('.st-key-home_brand button'),reduce=matchMedia('(prefers-reduced-motion: reduce)');
  let queued=false,frame=0;
  const behavior=()=>reduce.matches?'auto':'smooth';
  function top(e){e.preventDefault();e.stopPropagation();main.scrollTo({top:0,behavior:behavior()});root.focus({preventScroll:true});}
  function go(e){e.preventDefault();cards.scrollIntoView({block:'start',behavior:behavior()});cards.focus({preventScroll:true});}
  function update(){
    queued=false;if(!root.isConnected){cleanup();return;}
    const distance=Math.max(1,scene.offsetHeight*.55);
    const p=reduce.matches?0:Math.max(0,Math.min(1,(main.getBoundingClientRect().top-travel.getBoundingClientRect().top)/distance));
    room.style.transform=`translateY(${-12*p}px)`;
    dog.style.transform=`translate(${28*p}px,${-20*p}px)`;
    cat.style.transform=`translate(${-36*p}px,${-36*p}px)`;
    copy.style.transform=`translateY(${-8*p}px)`;
    root.dataset.progress=p.toFixed(3);
  }
  function schedule(){if(!queued){queued=true;frame=requestAnimationFrame(update);}}
  const observer=new MutationObserver(()=>{if(!root.isConnected)cleanup();});
  function cleanup(){main.removeEventListener('scroll',schedule);window.removeEventListener('resize',schedule);
    reduce.removeEventListener('change',schedule);explore.removeEventListener('click',go);back.removeEventListener('click',top);
    brand?.removeEventListener('click',top);cancelAnimationFrame(frame);observer.disconnect();}
  window.pawHomeCleanup=cleanup;main.addEventListener('scroll',schedule,{passive:true});window.addEventListener('resize',schedule);
  reduce.addEventListener('change',schedule);explore.addEventListener('click',go);back.addEventListener('click',top);brand?.addEventListener('click',top);
  observer.observe(main,{childList:true,subtree:true});main.scrollTo({top:0,behavior:'instant'});update();
})();
