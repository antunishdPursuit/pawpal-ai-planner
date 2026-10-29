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
  const dots = [...root.querySelectorAll('[data-step]')];
  const play = document.getElementById('paw-home-play');
  const replay = document.getElementById('paw-home-replay');
  const status = document.getElementById('paw-home-status');
  const footerBack = document.getElementById('paw-footer-top');
  const brand = root.querySelector('.paw-home-brand');
  const slot = root.querySelector('.paw-home-planner-slot');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const stops = [0, 1.3, 2.3, 3.4];
  const times = [0, 8000, 14500, 20000];
  const clamp = value => Math.max(0, Math.min(1, value));
  const smooth = value => { value = clamp(value); return value * value * (3 - 2 * value); };
  const start = () => main.scrollTop + travel.getBoundingClientRect().top - main.getBoundingClientRect().top;
  const units = () => reduce.matches ? staticUnits : Math.max(0, (main.scrollTop - start()) / scene.clientHeight);
  let running = false, finished = false, autoMode = false, elapsed = 0, last = 0;
  let staticUnits = 0, active = 0, queued = false, frame = 0, pendingFocus = null;
  let keyboardNavigation = false, history = [], closing = null;

  function controls() {
    play.textContent = running ? 'Pause' : 'Play';
    play.setAttribute('aria-label', running ? 'Pause automatic story' : 'Play automatic story');
    play.disabled = reduce.matches;
    status.textContent = reduce.matches ? 'Reduced motion. Choose a story step.' : running ? 'Story playing once.' : finished ? 'Story finished.' : 'Story paused.';
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
    const petProgress = smooth((u - .8) / 1);
    dog.style.transform = `translateX(${(scene.clientWidth - dog.offsetLeft + 8) * petProgress}px)`;
    cat.style.transform = `translateX(${-(cat.offsetLeft + cat.offsetWidth + 8) * petProgress}px)`;
    stages.forEach((stage, i) => {
      stage.style.opacity = String(alpha[i]);
      stage.style.visibility = alpha[i] > .001 ? 'visible' : 'hidden';
      stage.inert = i !== active || alpha[i] < .001;
      stage.setAttribute('aria-hidden', String(stage.inert));
    });
    const chatCount = autoMode && !reduce.matches ? elapsed < 800 ? 1 : elapsed < 2200 ? 2 : 3 : 3;
    messages.forEach((message, i) => {
      const visible = i < chatCount;
      message.style.opacity = visible ? '1' : '0';
      message.style.transform = `translateY(${visible || reduce.matches ? 0 : 8}px)`;
      message.style.visibility = visible ? 'visible' : 'hidden';
      message.setAttribute('aria-hidden', String(!visible));
    });
    dots.forEach(dot => {
      if (Number(dot.dataset.step) === active) dot.setAttribute('aria-current', 'step');
      else dot.removeAttribute('aria-current');
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

  function timeline(t) {
    if (t < 6500) return 0;
    if (t < 8000) return 1.3 * smooth((t - 6500) / 1500);
    if (t < 13000) return 1.3;
    if (t < 14500) return 1.3 + smooth((t - 13000) / 1500);
    if (t < 18500) return 2.3;
    return 2.3 + 1.1 * smooth((t - 18500) / 1500);
  }
  function timeAt(u) {
    if (u <= 0) return 0;
    if (u >= 3.4) return 20000;
    const inverse = value => {
      let lo = 0, hi = 1;
      for (let i = 0; i < 20; i++) {
        const mid = (lo + hi) / 2;
        if (smooth(mid) < value) lo = mid; else hi = mid;
      }
      return (lo + hi) / 2;
    };
    if (u < 1.3) return 6500 + 1500 * inverse(u / 1.3);
    if (u < 2.3) return 13000 + 1500 * inverse(u - 1.3);
    return 18500 + 1500 * inverse((u - 2.3) / 1.1);
  }
  function tick(now) {
    queued = false;
    if (!root.isConnected) { cleanup(); return; }
    if (running) {
      if (last) elapsed = Math.min(20000, elapsed + Math.min(now - last, 80));
      last = now;
      main.scrollTo({top:start() + timeline(elapsed) * scene.clientHeight, behavior:'instant'});
      if (elapsed >= 20000) { running = false; finished = true; controls(); }
    } else last = 0;
    update();
    if (running) schedule();
  }
  function schedule() {
    if (!queued) { queued = true; frame = requestAnimationFrame(tick); }
  }
  function stop() {
    if (running) { running = false; last = 0; controls(); }
    schedule();
  }
  function reset(startPlaying, focus = false) {
    running = startPlaying && !reduce.matches;
    autoMode = running;
    finished = false; elapsed = 0; last = 0; staticUnits = 0; history = [];
    pendingFocus = focus ? {target:root, position:0} : null;
    main.scrollTo({top:0, behavior:'instant'});
    controls(); schedule();
  }
  function toTop(event) { event.preventDefault(); reset(false, true); }
  function toStep(event) {
    stop(); autoMode = false; pendingFocus = null;
    const i = Number(event.currentTarget.dataset.step);
    staticUnits = stops[i]; elapsed = times[i]; finished = i === 3;
    main.scrollTo({top:reduce.matches ? 0 : start() + staticUnits * scene.clientHeight, behavior:reduce.matches ? 'instant' : 'smooth'});
    controls(); schedule();
  }
  function toggle() {
    if (running) { stop(); return; }
    if (finished || units() >= 3.39) { reset(true); return; }
    const u = units();
    if (Math.abs(u - timeline(elapsed)) > .01) elapsed = timeAt(u);
    running = !reduce.matches; autoMode = running; last = 0;
    controls(); schedule();
  }
  function replayStory() { reset(true); }
  function manual(event) {
    if (event.type === 'pointerdown') keyboardNavigation = false;
    if (event.type === 'pointerdown' && event.target.closest('.paw-home-controls')) return;
    autoMode = false; stop();
  }
  function keydown(event) {
    if (event.key === 'Tab') { keyboardNavigation = true; stop(); }
    if (!event.target.closest('button,a') && ['ArrowDown','ArrowUp','PageDown','PageUp','Home','End',' '].includes(event.key)) {
      autoMode = false; stop();
    }
  }
  function focusin() { if (keyboardNavigation) stop(); }
  function reading() { stop(); }
  function visibility() { if (document.hidden) stop(); last = 0; }
  function preferenceChanged() {
    staticUnits = stops[active]; stop(); autoMode = false; elapsed = times[active];
    main.scrollTo({top:reduce.matches ? 0 : start() + staticUnits * scene.clientHeight, behavior:'instant'});
    controls(); schedule();
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
    stages.forEach(stage => stage.removeEventListener('pointerenter', reading));
    footerBack.removeEventListener('click', toTop);
    brand.removeEventListener('click', toTop);
    play.removeEventListener('click', toggle);
    replay.removeEventListener('click', replayStory);
    dots.forEach(dot => dot.removeEventListener('click', toStep));
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
  stages.forEach(stage => stage.addEventListener('pointerenter', reading));
  footerBack.addEventListener('click', toTop);
  brand.addEventListener('click', toTop);
  play.addEventListener('click', toggle);
  replay.addEventListener('click', replayStory);
  dots.forEach(dot => dot.addEventListener('click', toStep));
  observer.observe(main, {childList:true, subtree:true});
  const autoplay = !window.pawHomeAutoplaySeen;
  window.pawHomeAutoplaySeen = true;
  reset(autoplay);
})();
