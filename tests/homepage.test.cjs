const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '..', 'assets', 'homepage.js'), 'utf8');

// A deterministic DOM/animation clock for interaction and visibility regressions.
// Real layout, images, and the Streamlit callback are checked in the browser.
class Events {
  constructor() { this.listeners = new Map(); }
  addEventListener(type, fn) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(fn);
  }
  removeEventListener(type, fn) { this.listeners.get(type)?.delete(fn); }
  emit(type, event = {}) {
    event.target ??= {closest: () => null};
    for (const fn of [...(this.listeners.get(type) || [])]) fn(event);
  }
}
function element() {
  return Object.assign(new Events(), {
    style: {}, dataset: {}, attrs: {}, isConnected: true,
    setAttribute(k, v) { this.attrs[k] = v; },
    getBoundingClientRect() { return {left: 0, top: 0, width: 600}; },
    focus() {},
  });
}
function page({hidden = false, reduced = false} = {}) {
  const window = new Events();
  const document = Object.assign(new Events(), {hidden});
  const main = element(), root = element(), scene = element();
  const stages = Array.from({length: 4}, element);
  const messages = Array.from({length: 3}, element);
  const travel = element(), dog = element(), cat = element();
  const footer = element(), brand = element(), status = element();
  const media = Object.assign(new Events(), {matches: reduced});
  Object.assign(scene, {clientHeight: 720, clientWidth: 1280});
  Object.assign(dog, {offsetLeft: 614, offsetWidth: 627});
  Object.assign(cat, {offsetLeft: 102, offsetWidth: 448});
  Object.assign(main, {clientWidth: 1270, clientHeight: 720, scrollHeight: 2952});
  main.scrollTop = 0;
  main.scrollTo = ({top}) => {
    main.scrollTop = Math.max(0, Math.min(2232, top));
    main.emit('scroll');
  };
  travel.getBoundingClientRect = () => ({top: -main.scrollTop});
  const nodes = {
    '.paw-home-travel': travel, '.paw-home-scene': scene,
    '.paw-home-dog': dog, '.paw-home-cat': cat,
    '.paw-home-brand': brand, '.paw-home-planner-slot': element(),
  };
  root.querySelector = selector => nodes[selector];
  root.querySelectorAll = selector => selector === '.paw-home-stage' ? stages : messages;
  root.focus = () => document.emit('focusin');
  document.querySelector = selector => selector === '[data-testid="stMain"]' ? main : null;
  document.getElementById = id => ({
    'paw-home-top': root, 'paw-home-status': status, 'paw-footer-top': footer,
  })[id];
  let now = 0, next = 0;
  const frames = new Map();
  const context = vm.createContext({
    window, document, matchMedia: () => media,
    requestAnimationFrame(fn) { frames.set(++next, fn); return next; },
    cancelAnimationFrame(id) { frames.delete(id); },
    MutationObserver: class { observe() {} disconnect() {} },
  });
  const mount = () => vm.runInContext(source, context);
  const advance = ms => {
    while (ms > 0) {
      const delta = Math.min(16, ms);
      now += delta; ms -= delta;
      const pending = [...frames.values()];
      frames.clear();
      for (const fn of pending) fn(now);
    }
  };
  const visibility = hidden => { document.hidden = hidden; document.emit('visibilitychange'); advance(32); };
  mount(); advance(32);
  return {window, document, main, root, stages, messages, footer, mount, advance, visibility};
}

test('picture clicks and taps leave automatic scrolling running', () => {
  const p = page(); p.advance(2200);
  const before = p.main.scrollTop;
  p.main.emit('pointerdown'); p.main.emit('touchstart');
  p.advance(1000);
  assert.equal(p.root.dataset.playing, 'true');
  assert.ok(p.main.scrollTop > before);
});
test('a hidden initial mount, including an early rerender, waits for visibility', () => {
  const p = page({hidden: true}); p.advance(3000);
  assert.equal(p.main.scrollTop, 0);
  assert.equal(p.window.pawHomeAutoplaySeen, undefined);
  p.mount(); p.advance(1000); p.visibility(false); p.advance(2200);
  assert.equal(p.root.dataset.playing, 'true');
  assert.ok(p.main.scrollTop > 0);
});
test('hiding automatic playback pauses it and showing it resumes without a jump', () => {
  const p = page(); p.advance(2200); p.visibility(true);
  const paused = p.main.scrollTop; p.advance(5000);
  assert.equal(p.main.scrollTop, paused);
  p.visibility(false); p.advance(500);
  assert.equal(p.root.dataset.playing, 'true');
  assert.ok(p.main.scrollTop > paused && p.main.scrollTop - paused < 100);
});
for (const gesture of ['wheel', 'touchmove']) {
  test(`${gesture} takes over and does not resume on visibility changes`, () => {
    const p = page(); p.advance(2200); p.main.emit(gesture); p.advance(32);
    const paused = p.main.scrollTop;
    p.visibility(true); p.advance(1000); p.visibility(false); p.advance(1000);
    assert.equal(p.root.dataset.playing, 'false');
    assert.equal(p.main.scrollTop, paused);
  });
}
test('keyboard takeover stops movement and reveals the complete example', () => {
  const p = page(); p.document.emit('keydown', {key: 'Tab'}); p.advance(32);
  assert.equal(p.root.dataset.playing, 'false');
  assert.equal(p.root.dataset.chatCount, '3');
});
test('shorter opening still moves pets before Review and preserves later spacing', () => {
  const p = page(); p.main.emit('wheel');
  p.main.scrollTo({top: 315}); p.advance(32);
  assert.equal(p.root.dataset.step, '0');
  assert.ok(Number(p.root.dataset.petProgress) > 0);
  assert.equal(p.stages[1].style.visibility, 'hidden');
  for (const [scroll, stage] of [[468, 1], [1188, 2], [1908, 3]]) {
    p.main.scrollTo({top: scroll}); p.advance(32);
    assert.equal(p.root.dataset.step, String(stage));
    assert.ok(Number(p.stages[stage].style.opacity) > .999);
  }
  p.main.scrollTo({top: 0}); p.advance(32);
  assert.equal(p.root.dataset.petProgress, '0.000');
});
test('reduced motion never autoplays and all stages remain manually reachable', () => {
  const p = page({reduced: true}); p.advance(5000);
  assert.equal(p.root.dataset.playing, 'false');
  assert.equal(p.main.scrollTop, 0);
  p.main.scrollTo({top: 1188}); p.advance(32);
  assert.equal(p.root.dataset.step, '2');
  assert.equal(p.root.dataset.petProgress, '1.000');
});

test('the scrollbar gutter still takes control of automatic scrolling', () => {
  const p = page(); p.advance(2200);
  p.main.emit('pointerdown', {clientX: 1278}); p.advance(32);
  const paused = p.main.scrollTop; p.advance(1000);
  assert.equal(p.root.dataset.playing, 'false');
  assert.equal(p.main.scrollTop, paused);
});
