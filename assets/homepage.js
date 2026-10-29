(() => {
  window.pawHomeCleanup?.();
  const main = document.querySelector('[data-testid="stMain"]');
  const root = document.getElementById('paw-home-top');
  if (!main || !root) return;

  const travel = root.querySelector('.paw-home-travel');
  const scene = root.querySelector('.paw-home-scene');
  const room = root.querySelector('.paw-home-room');
  const dog = root.querySelector('.paw-home-dog');
  const cat = root.querySelector('.paw-home-cat');
  const copy = root.querySelector('.paw-home-copy');
  const story = document.getElementById('paw-home-cards');
  const steps = [...root.querySelectorAll('.paw-home-card')];
  const links = [...root.querySelectorAll('#paw-explore, .paw-next')];
  const back = document.getElementById('paw-back-top');
  const brand = document.querySelector('.st-key-home_brand button');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  // Scroll distances are viewport units: opening hold, departure, three reading stops.
  const stops = [1.2, 2.05, 2.9];
  const switches = [[1.65, 2.05], [2.5, 2.9]];
  let queued = false, frame = 0, pendingFocus = null;
  const clamp = value => Math.max(0, Math.min(1, value));
  const smooth = value => { value = clamp(value); return value * value * (3 - 2 * value); };
  const navHeight = () => parseFloat(getComputedStyle(root).getPropertyValue('--paw-home-nav-height'));
  const viewport = () => main.clientHeight;
  const travelStart = () => main.scrollTop + travel.getBoundingClientRect().top - main.getBoundingClientRect().top - navHeight();
  const behavior = () => reduce.matches ? 'auto' : 'smooth';

  function top(event) {
    event.preventDefault();
    event.stopPropagation();
    pendingFocus = null;
    main.scrollTo({top: 0, behavior: behavior()});
    root.focus({preventScroll: true});
  }

  function go(event) {
    event.preventDefault();
    const target = document.getElementById(event.currentTarget.hash.slice(1));
    const index = steps.indexOf(target);
    if (reduce.matches) {
      target.scrollIntoView({block: 'start', behavior: 'auto'});
      target.focus({preventScroll: true});
    } else {
      const position = travelStart() + stops[index] * viewport();
      pendingFocus = {target, position};
      main.scrollTo({top: position, behavior: behavior()});
      schedule();
    }
  }

  function update() {
    queued = false;
    if (!root.isConnected) { cleanup(); return; }
    const units = Math.max(0, (main.scrollTop - travelStart()) / viewport());
    const p = reduce.matches ? 0 : clamp(units - .2);
    const part = smooth(p / .95);
    const reveal = smooth((p - .12) / .88);
    const width = scene.clientWidth;
    room.style.transform = `translateY(${-12 * p}px)`;
    dog.style.transform = `translateX(${(width * .52 + 24) * part}px)`;
    cat.style.transform = `translateX(${-(width * .36 + 24) * part}px)`;
    copy.style.opacity = String(1 - smooth(p / .48));
    copy.style.transform = `translateY(${-32 * p}px)`;
    copy.inert = !reduce.matches && p > .48;
    story.style.transform = `translateY(${(1 - reveal) * 100}%)`;
    story.inert = !reduce.matches && reveal < .01;

    const firstSwitch = smooth((units - switches[0][0]) / (switches[0][1] - switches[0][0]));
    const secondSwitch = smooth((units - switches[1][0]) / (switches[1][1] - switches[1][0]));
    const exposure = [1 - firstSwitch, firstSwitch * (1 - secondSwitch), secondSwitch];
    const shift = [-100 * firstSwitch, 100 * (1 - firstSwitch - secondSwitch), 100 * (1 - secondSwitch)];
    const activeIndex = units < 1.85 ? 0 : units < 2.7 ? 1 : 2;
    steps.forEach((step, index) => {
      step.style.opacity = '1';
      step.style.transform = `translateY(${shift[index]}%)`;
      step.style.visibility = reduce.matches || exposure[index] > .001 ? 'visible' : 'hidden';
      step.inert = !reduce.matches && (index !== activeIndex || reveal < .01);
    });
    if (pendingFocus && Math.abs(main.scrollTop - pendingFocus.position) < 2) {
      pendingFocus.target.focus({preventScroll: true});
      pendingFocus = null;
    }
    root.dataset.progress = p.toFixed(3);
    root.dataset.step = reveal < .01 ? 'hero' : String(activeIndex + 1);
  }

  function schedule() {
    if (!queued) { queued = true; frame = requestAnimationFrame(update); }
  }
  const observer = new MutationObserver(() => { if (!root.isConnected) cleanup(); });
  function cleanup() {
    main.removeEventListener('scroll', schedule);
    window.removeEventListener('resize', schedule);
    reduce.removeEventListener('change', schedule);
    links.forEach(link => link.removeEventListener('click', go));
    back.removeEventListener('click', top);
    brand?.removeEventListener('click', top);
    cancelAnimationFrame(frame);
    observer.disconnect();
  }
  window.pawHomeCleanup = cleanup;
  main.addEventListener('scroll', schedule, {passive: true});
  window.addEventListener('resize', schedule);
  reduce.addEventListener('change', schedule);
  links.forEach(link => link.addEventListener('click', go));
  back.addEventListener('click', top);
  brand?.addEventListener('click', top);
  observer.observe(main, {childList: true, subtree: true});
  main.scrollTo({top: 0, behavior: 'instant'});
  update();
})();
