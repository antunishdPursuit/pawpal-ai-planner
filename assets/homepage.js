
    (() => {
      if (window.pawHomeCleanup) window.pawHomeCleanup();
      const main=document.querySelector('[data-testid="stMain"]'), root=document.getElementById('paw-home-top');
      if (!main || !root) return;
      const art=root.querySelector('.paw-hero-art img'), explore=document.getElementById('paw-explore'),
        back=document.getElementById('paw-back-top'), brand=document.querySelector('.st-key-home_brand button'),
        reduce=matchMedia('(prefers-reduced-motion: reduce)');
      const behavior=()=>reduce.matches?'auto':'smooth';
      function top(e) {e.preventDefault();e.stopPropagation();main.scrollTo({top:0,behavior:behavior()});root.focus({preventScroll:true});}
      function go(e) {e.preventDefault();const target=document.getElementById('paw-home-cards');target.scrollIntoView({block:'start',behavior:behavior()});target.focus({preventScroll:true});}
      let queued=false;
      function update() {queued=false;if(!root.isConnected){cleanup();return;}
        art.style.transform=`translateY(${reduce.matches?0:-Math.min(16,main.scrollTop*.04)}px)`;}
      function schedule() {if(!queued){queued=true;requestAnimationFrame(update);}}
      function cleanup() {main.removeEventListener('scroll',schedule);reduce.removeEventListener('change',schedule);
        explore.removeEventListener('click',go);back.removeEventListener('click',top);brand?.removeEventListener('click',top);}
      window.pawHomeCleanup=cleanup; main.addEventListener('scroll',schedule,{passive:true});
      reduce.addEventListener('change',schedule); explore.addEventListener('click',go);back.addEventListener('click',top);
      brand?.addEventListener('click',top);main.scrollTo({top:0,behavior:'instant'});update();
    })();
