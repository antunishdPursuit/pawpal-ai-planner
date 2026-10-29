(() => {
  window.pawHomeCleanup?.();
  const main = document.querySelector('[data-testid="stMain"]');
  const root = document.getElementById('paw-home-top');
  if (!main || !root) return;

  const travel = root.querySelector('.paw-home-travel');
  const scene = root.querySelector('.paw-home-scene');
  const dog = root.querySelector('.paw-home-dog');
  const cat = root.querySelector('.paw-home-cat');
  const stages = [...root.querySelectorAll('.paw-home-stage')];
  const progress = root.querySelector('.paw-home-progress');
  const dots = [...progress.querySelectorAll('button')];
  const explore = document.getElementById('paw-explore');
  const footerBack = document.getElementById('paw-footer-top');
  const brand = root.querySelector('.paw-home-brand');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const stops = [0, .8, 1.65, 2.5];
  const clamp = value => Math.max(0, Math.min(1, value));
  const smooth = value => { value = clamp(value); return value * value * (3 - 2 * value); };
  const start = () => main.scrollTop + travel.getBoundingClientRect().top - main.getBoundingClientRect().top;
  let queued = false, frame = 0, reducedStage = 0, pendingFocus = null;

  function update() {
    queued = false;
    if (!root.isConnected) { cleanup(); return; }
    const units = reduce.matches ? stops[reducedStage] : Math.max(0, (main.scrollTop - start()) / scene.clientHeight);
    const active = units < .4 ? 0 : units < 1.15 ? 1 : units < 2.3 ? 2 : 3;
    const alpha = reduce.matches ? stages.map((_, index) => Number(index === active)) : [
      1 - smooth((units - .25) / .15),
      smooth((units - .4) / .15) * (1 - smooth((units - 1) / .15)),
      smooth((units - 1.15) / .15) * (1 - smooth((units - 2.15) / .15)),
      smooth((units - 2.3) / .15),
    ];
    // Reuse the original images at a constant scale. Only their X position changes.
    // Tell is complete before departure starts; both full image boxes exit before See.
    const petProgress = smooth((units - 1.15) / 1);
    const dogExit = scene.clientWidth - dog.offsetLeft + 8;
    const catExit = cat.offsetLeft + cat.offsetWidth + 8;
    dog.style.transform = `translateX(${dogExit * petProgress}px)`;
    cat.style.transform = `translateX(${-catExit * petProgress}px)`;

    stages.forEach((stage, index) => {
      stage.style.opacity = String(alpha[index]);
      stage.style.visibility = alpha[index] > .001 ? 'visible' : 'hidden';
      stage.inert = index !== active || alpha[index] < .001;
      stage.setAttribute('aria-hidden', String(stage.inert));
    });
    progress.style.visibility = active > 0 ? 'visible' : 'hidden';
    progress.inert = active === 0;
    progress.setAttribute('aria-hidden', String(active === 0));
    dots.forEach(dot => {
      if (Number(dot.dataset.step) === active) dot.setAttribute('aria-current', 'step');
      else dot.removeAttribute('aria-current');
    });
    if (pendingFocus && (reduce.matches || Math.abs(main.scrollTop - pendingFocus.position) < 2)) {
      pendingFocus.target.focus({preventScroll:true});
      pendingFocus = null;
    }
    root.dataset.step = String(active);
    root.dataset.units = units.toFixed(3);
    root.dataset.petProgress = petProgress.toFixed(3);
  }

  function schedule() {
    if (!queued) { queued = true; frame = requestAnimationFrame(update); }
  }
  function go(index, focus = false) {
    reducedStage = index;
    const position = index === 0 ? 0 : start() + stops[index] * scene.clientHeight;
    if (focus) pendingFocus = {target:index === 0 ? root : stages[index], position};
    else pendingFocus = null;
    main.scrollTo({top:reduce.matches ? 0 : position, behavior:reduce.matches ? 'auto' : 'smooth'});
    schedule();
  }
  function toTop(event) { event.preventDefault(); go(0, true); }
  function toStory(event) { event.preventDefault(); go(1, true); }
  function toStep(event) { go(Number(event.currentTarget.dataset.step)); }
  function preferenceChanged() {
    reducedStage = Number(root.dataset.step || 0);
    if (!reduce.matches) main.scrollTo({top:start() + stops[reducedStage] * scene.clientHeight, behavior:'instant'});
    schedule();
  }
  const observer = new MutationObserver(() => { if (!root.isConnected) cleanup(); });
  function cleanup() {
    main.removeEventListener('scroll', schedule);
    window.removeEventListener('resize', schedule);
    reduce.removeEventListener('change', preferenceChanged);
    explore.removeEventListener('click', toStory);
    footerBack.removeEventListener('click', toTop);
    brand.removeEventListener('click', toTop);
    dots.forEach(dot => dot.removeEventListener('click', toStep));
    observer.disconnect();
    cancelAnimationFrame(frame);
  }
  window.pawHomeCleanup = cleanup;
  main.addEventListener('scroll', schedule, {passive:true});
  window.addEventListener('resize', schedule);
  reduce.addEventListener('change', preferenceChanged);
  explore.addEventListener('click', toStory);
  footerBack.addEventListener('click', toTop);
  brand.addEventListener('click', toTop);
  dots.forEach(dot => dot.addEventListener('click', toStep));
  observer.observe(main, {childList:true, subtree:true});
  main.scrollTo({top:0, behavior:'instant'});
  update();
})();
