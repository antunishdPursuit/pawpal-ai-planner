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
  const messages = [...root.querySelectorAll('.paw-chat li')];
  const status = document.getElementById('paw-home-status');
  const footerBack = document.getElementById('paw-footer-top');
  const brand = root.querySelector('.paw-home-brand');
  const slot = root.querySelector('.paw-home-planner-slot');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const stops = [0, 1.3, 2.3, 3.4];
  const duration = 16000;
  const clamp = value => Math.max(0, Math.min(1, value));
  const smooth = value => { value = clamp(value); return value * value * (3 - 2 * value); };
  const start = () => main.scrollTop + travel.getBoundingClientRect().top - main.getBoundingClientRect().top;
  const units = () => Math.max(0, (main.scrollTop - start()) / scene.clientHeight);
  let running = false, finished = false, autoMode = false, elapsed = 0, last = 0;
  let active = 0, queued = false, frame = 0, pendingFocus = null;
  let keyboardNavigation = false, history = [], closing = null;

  function announceStatus() {
    status.textContent = reduce.matches ? 'Reduced motion. Scroll to explore the story.' : running ? 'Story playing once.' : finished ? 'Story finished.' : 'Story paused.';
  }

  function update() {
    const u = units();
    active = u < .8 ? 0 : u < 1.8 ? 1 : u < 2.8 ? 2 : 3;
    const alpha = reduce.matches ? stages.map((_, i) => Number(i === active)) : [
      1 - smooth((u - .65) / .15),
      smooth((u - .8) / .15) * (1 - smooth((u - 1.65) / .15)),
      smooth((u - 1.8) / .15) * (1 - smooth((u - 2.65) / .15)),
      smooth((u - 2.8) / .15),
    ];
    // Original pet image bytes, pose, scale and Y stay fixed. Only X changes.
    const petProgress = reduce.matches ? [0, .5, 1, 1][active] : smooth((u - .8) / 1);
    dog.style.transform = `translateX(${(scene.clientWidth - dog.offsetLeft + 8) * petProgress}px)`;
    cat.style.transform = `translateX(${-(cat.offsetLeft + cat.offsetWidth + 8) * petProgress}px)`;
    stages.forEach((stage, i) => {
      stage.style.opacity = String(alpha[i]);
      stage.style.transform = reduce.matches ? 'none' : `translateY(calc(${stops[i] - u} * var(--paw-space-8)))`;
      stage.style.visibility = alpha[i] > .001 ? 'visible' : 'hidden';
      stage.inert = i !== active || alpha[i] < .001;
      stage.setAttribute('aria-hidden', String(stage.inert));
    });
    const chatCount = autoMode && !reduce.matches ? elapsed < 650 ? 1 : elapsed < 1500 ? 2 : 3 : 3;
    messages.forEach((message, i) => {
      const visible = i < chatCount;
      message.style.opacity = visible ? '1' : '0';
      message.style.transform = `translateY(${visible || reduce.matches ? 0 : 8}px)`;
      message.style.visibility = visible ? 'visible' : 'hidden';
      message.setAttribute('aria-hidden', String(!visible));
    });
    // Keep the closing action native, with the same Streamlit callback as the header.
    closing = document.querySelector('.st-key-homepage_closing');
    if (closing) {
      const rect = slot.getBoundingClientRect();
      const visible = active === 3 && alpha[3] > .001;
      closing.style.left = `${rect.left}px`;
      closing.style.top = `${rect.top}px`;
      closing.style.width = `${rect.width}px`;
      closing.style.opacity = String(alpha[3]);
      closing.style.visibility = visible ? 'visible' : 'hidden';
      closing.inert = !visible;
      closing.setAttribute('aria-hidden', String(!visible));
    }
    if (pendingFocus && (reduce.matches || Math.abs(main.scrollTop - pendingFocus.position) < 2)) {
      pendingFocus.target.focus({preventScroll:true});
      pendingFocus = null;
    }
    if ((running || finished) && history.at(-1) !== active) history.push(active);
    root.dataset.step = String(active);
    root.dataset.units = u.toFixed(3);
    root.dataset.petProgress = petProgress.toFixed(3);
    root.dataset.chatCount = String(chatCount);
    root.dataset.playing = String(running);
    root.dataset.autoSteps = JSON.stringify(history);
  }

  // One constant-speed pass; no per-panel holds or scroll snapping.
  const timeline = t => 3.4 * clamp(t / duration);
  function tick(now) {
    queued = false;
    if (!root.isConnected) { cleanup(); return; }
    if (running) {
      if (last) elapsed = Math.min(duration, elapsed + Math.min(now - last, 80));
      last = now;
      main.scrollTo({top:start() + timeline(elapsed) * scene.clientHeight, behavior:'instant'});
      if (elapsed >= duration) { running = false; finished = true; announceStatus(); }
    } else last = 0;
    update();
    if (running) schedule();
  }
  function schedule() {
    if (!queued) { queued = true; frame = requestAnimationFrame(tick); }
  }
  function stop() {
    if (running) { running = false; last = 0; announceStatus(); }
    schedule();
  }
  function reset(startPlaying, focus = false) {
    running = startPlaying && !reduce.matches;
    autoMode = running;
    finished = false; elapsed = 0; last = 0; history = [];
    pendingFocus = focus ? {target:root, position:0} : null;
    main.scrollTo({top:0, behavior:'instant'});
    announceStatus(); schedule();
  }
  function toTop(event) { event.preventDefault(); reset(false, true); }
  function manual(event) {
    if (event.type === 'pointerdown') keyboardNavigation = false;
    autoMode = false; stop();
  }
  function keydown(event) {
    if (event.key === 'Tab') { keyboardNavigation = true; autoMode = false; stop(); }
    if (!event.target.closest('button,a') && ['ArrowDown','ArrowUp','PageDown','PageUp','Home','End',' '].includes(event.key)) {
      autoMode = false; stop();
    }
  }
  function focusin() { if (keyboardNavigation) stop(); }
  function visibility() { if (document.hidden) stop(); last = 0; }
  function preferenceChanged() {
    stop(); autoMode = false;
    announceStatus(); schedule();
  }
  const observer = new MutationObserver(() => { if (!root.isConnected) cleanup(); else schedule(); });
  function cleanup() {
    running = false;
    main.removeEventListener('scroll', schedule);
    window.removeEventListener('resize', schedule);
    ['wheel','touchstart','pointerdown'].forEach(name => main.removeEventListener(name, manual));
    document.removeEventListener('keydown', keydown);
    document.removeEventListener('focusin', focusin);
    document.removeEventListener('visibilitychange', visibility);
    reduce.removeEventListener('change', preferenceChanged);
    footerBack.removeEventListener('click', toTop);
    brand.removeEventListener('click', toTop);
    observer.disconnect(); cancelAnimationFrame(frame);
    if (closing) { closing.style.visibility = 'hidden'; closing.inert = true; }
  }
  window.pawHomeCleanup = cleanup;
  main.addEventListener('scroll', schedule, {passive:true});
  window.addEventListener('resize', schedule);
  ['wheel','touchstart','pointerdown'].forEach(name => main.addEventListener(name, manual, {passive:true}));
  document.addEventListener('keydown', keydown);
  document.addEventListener('focusin', focusin);
  document.addEventListener('visibilitychange', visibility);
  reduce.addEventListener('change', preferenceChanged);
  footerBack.addEventListener('click', toTop);
  brand.addEventListener('click', toTop);
  observer.observe(main, {childList:true, subtree:true});
  const autoplay = !window.pawHomeAutoplaySeen;
  window.pawHomeAutoplaySeen = true;
  reset(autoplay);
})();
