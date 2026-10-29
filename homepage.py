"""PawPal landing page; artwork and motion never access planner data."""
import base64
from pathlib import Path

import streamlit as st


def _image(name):
    data = (Path(__file__).parent / "assets" / name).read_bytes()
    return "data:image/webp;base64," + base64.b64encode(data).decode("ascii")


def show_home(open_planner):
    with st.container(key="homepage_navigation", horizontal=True, vertical_alignment="center"):
        st.html('<div class="paw-home-brand">PawPal <span>AI Planner</span></div>')
        st.button("Open planner", type="primary", on_click=open_planner, key="home_open_planner")
    room, dog = (_image(name) for name in ("home-room.webp", "home-dog.webp"))
    st.html(f'''<style>
    .stApp:has(.st-key-homepage_navigation) [data-testid="stSidebar"],
    .stApp:has(.st-key-homepage_navigation) [data-testid="stSidebarCollapsedControl"] {{display:none!important;}}
    .stApp:has(.st-key-homepage_navigation) .stMainBlockContainer {{max-width:none; padding:0!important;}}
    .st-key-homepage_navigation {{max-width:var(--paw-width); margin:auto;
      padding:var(--paw-space-4) var(--paw-space-8); justify-content:space-between;}}
    .paw-home-brand {{font-size:var(--paw-heading); font-weight:700; color:var(--paw-text);}}
    .paw-home-brand span {{font-size:var(--paw-small); font-weight:400;}}
    .paw-home-travel {{height:300vh; min-height:1400px; position:relative;}}
    .paw-home-scene {{height:calc(100vh - 80px); min-height:440px; position:sticky;
      top:0; overflow:hidden; background:var(--paw-page);}}
    .paw-home-layer {{position:absolute; will-change:transform;}}
    .paw-home-room {{inset:-6% 0; background:url("{room}") center/cover no-repeat;}}
    .paw-home-copy {{left:7%; top:14%; z-index:2; color:var(--paw-text);
      max-width:390px; padding:var(--paw-space-6); border-radius:var(--paw-radius);
      background:color-mix(in srgb,var(--paw-page) 93%,transparent);}}
    .paw-home-copy h1 {{font-size:clamp(32px, 4vw, 48px)!important; line-height:1.15!important; margin:0;}}
    .paw-home-copy p {{font-size:var(--paw-body); line-height:1.5;}}
    .paw-home-copy a {{display:inline-flex; min-height:var(--paw-control); align-items:center;
      padding:0 var(--paw-space-4); border-radius:var(--paw-radius); color:var(--paw-rail-text);
      background:var(--paw-primary); text-decoration:none; font-weight:600;}}
    .paw-home-copy a:focus-visible {{outline:3px solid var(--paw-blue); outline-offset:3px;}}
    .paw-home-dog {{width:49%; right:3%; bottom:10%; z-index:3;}}
    .paw-home-fade {{position:absolute; bottom:0; left:0; right:0; height:90px;
      z-index:4; background:linear-gradient(transparent,var(--paw-page)); pointer-events:none;}}
    .paw-home-cards {{max-width:1200px; margin:auto; padding:var(--paw-space-8);
      display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:var(--paw-space-6);}}
    .paw-home-card {{background:var(--paw-surface); border:1px solid var(--paw-border);
      border-radius:var(--paw-radius); padding:var(--paw-space-6);}}
    .paw-home-card h2 {{margin:0 0 var(--paw-space-3); font-size:var(--paw-heading);}}
    .paw-home-card p {{margin:0; color:var(--paw-muted); line-height:1.5;}}
    .paw-home-example {{margin-top:var(--paw-space-6); padding:var(--paw-space-4);
      background:var(--paw-muted-surface); border-radius:var(--paw-radius); color:var(--paw-text);}}
    .paw-home-example small {{display:block; color:var(--paw-muted); margin-bottom:var(--paw-space-2);}}
    .paw-home-example strong {{display:block; margin-bottom:var(--paw-space-2);}}
    @media(max-width:768px) {{.st-key-homepage_navigation {{padding:var(--paw-space-4);}}
      .paw-home-copy {{left:var(--paw-space-4);right:var(--paw-space-4);top:var(--paw-space-6); max-width:350px;}}
      .paw-home-dog {{width:75%;right:-2%;bottom:10%;}}
      .paw-home-room {{background-position:58% center;}}
      .paw-home-cards {{grid-template-columns:1fr;padding:var(--paw-space-6) var(--paw-space-4);}}}}
    @media(prefers-reduced-motion:reduce) {{.paw-home-travel {{height:auto;min-height:0;}}
      .paw-home-layer {{will-change:auto!important;transform:none!important;}}}}
    </style>
    <div class="paw-home-travel" id="paw-home-travel"><div class="paw-home-scene">
      <div class="paw-home-room paw-home-layer" role="img" aria-label="A dog relaxing at home"></div>
      <div class="paw-home-copy paw-home-layer"><h1>Care comes together.</h1>
      <p>Plan your pet’s day, one thoughtful task at a time.</p>
      <a href="#paw-home-cards" id="paw-explore">Explore story</a></div>
      <img class="paw-home-dog paw-home-layer" src="{dog}" alt="">
      <div class="paw-home-fade"></div></div></div>
    <div class="paw-home-cards" id="paw-home-cards">
      <section class="paw-home-card"><h2>Tell PawPal</h2><p>Describe the care your pet needs.</p>
        <div class="paw-home-example"><small>Example request</small>Walk Luna tomorrow at 9 AM.</div></section>
      <section class="paw-home-card"><h2>Review the details</h2><p>Check the task before you save it.</p>
        <div class="paw-home-example"><small>Example preview</small><strong>Walk Luna</strong>Tomorrow · 9:00 AM</div></section>
      <section class="paw-home-card"><h2>See your plan</h2><p>Find your confirmed task on the calendar.</p>
        <div class="paw-home-example"><small>Example calendar</small><strong>Tomorrow</strong>9:00 AM · Walk Luna</div></section>
    </div>
    <script>
    (() => {{
      if (window.pawHomeCleanup) window.pawHomeCleanup();
      const area = document.getElementById('paw-home-travel');
      const main = document.querySelector('[data-testid="stMain"]');
      const explore = document.getElementById('paw-explore');
      const cards = document.getElementById('paw-home-cards');
      if (!area || !main || !explore || !cards) return;
      const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
      const room = area.querySelector('.paw-home-room');
      const copy = area.querySelector('.paw-home-copy');
      const dog = area.querySelector('.paw-home-dog');
      let queued = false;
      function update() {{
        queued = false;
        if (!area.isConnected) {{ cleanup(); return; }}
        const d = reduce.matches ? 0 : Math.max(0, Math.min(area.offsetHeight - area.firstElementChild.offsetHeight,
          main.getBoundingClientRect().top - area.getBoundingClientRect().top));
        room.style.transform = `translateY(${{d * .06}}px)`;
        copy.style.transform = `translateY(${{d * .32}}px)`;
        dog.style.transform = `translate(${{d * .08}}px, ${{d * .22}}px)`;
      }}
      function schedule() {{ if (!queued) {{ queued = true; requestAnimationFrame(update); }} }}
      function go(e) {{e.preventDefault(); cards.scrollIntoView({{behavior:reduce.matches?'auto':'smooth',block:'start'}});}}
      function cleanup() {{ main.removeEventListener('scroll', schedule); reduce.removeEventListener('change', schedule); explore.removeEventListener('click',go); }}
      window.pawHomeCleanup = cleanup;
      main.addEventListener('scroll', schedule, {{passive:true}});
      reduce.addEventListener('change', schedule); explore.addEventListener('click',go); update();
    }})();
    </script>''', unsafe_allow_javascript=True)
