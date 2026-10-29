"""Homepage artwork and scroll effect, independent of planner data."""
import base64
from pathlib import Path

import streamlit as st


def _image(name):
    data = (Path(__file__).parent / "assets" / name).read_bytes()
    return "data:image/webp;base64," + base64.b64encode(data).decode("ascii")


def show_home(open_planner):
    with st.container(key="homepage_action"):
        st.button("Open planner", type="primary", on_click=open_planner)
    room, dog, cat = (_image(name) for name in ("home-room.webp", "home-dog.webp", "home-cat.webp"))
    st.html(f'''<style>
    .paw-home-travel {{height: min(1600px, 190vh); position:relative;}}
    .paw-home-scene {{height: min(76vh, 700px); min-height:420px; position:sticky; top:0;
      overflow:hidden; border-radius:var(--paw-radius); background:var(--paw-muted-surface);}}
    .paw-home-layer {{position:absolute; will-change:transform;}}
    .paw-home-room {{inset:-5% 0; background:url("{room}") center/cover no-repeat;}}
    .paw-home-copy {{left:6%; top:10%; z-index:2; max-width:45%; color:var(--paw-text);
      background:color-mix(in srgb, var(--paw-page) 90%, transparent);
      padding:var(--paw-space-4); border-radius:var(--paw-radius);}}
    .paw-home-copy h1 {{font-size:clamp(32px, 4vw, 48px)!important; line-height:1.15!important;}}
    .paw-home-copy p {{font-size:var(--paw-body); line-height:1.5; max-width:280px;}}
    .paw-home-dog {{width:49%; right:3%; bottom:10%; z-index:3;}}
    .paw-home-cat {{width:35%; left:8%; bottom:5%; z-index:4;}}
    .paw-home-fade {{position:absolute; bottom:0; left:0; right:0; height:80px;
      z-index:5; background:linear-gradient(transparent,var(--paw-page)); pointer-events:none;}}
    .paw-home-after {{padding:var(--paw-space-8) 0;}}
    @media(max-width:768px) {{.paw-home-copy {{max-width:75%;}}
      .paw-home-dog {{width:68%;right:-4%;bottom:20%;}}
      .paw-home-cat {{width:49%;left:0;bottom:8%;}}
      .paw-home-room {{background-position:58% center;}}}}
    @media(prefers-reduced-motion:reduce) {{.paw-home-travel {{height:auto;}}
      .paw-home-layer {{will-change:auto!important;transform:none!important;}}}}
    </style>
    <div class="paw-home-travel" id="paw-home-travel"><div class="paw-home-scene">
      <div class="paw-home-room paw-home-layer" role="img" aria-label="Illustration of a dog and cat relaxing at home"></div>
      <div class="paw-home-copy paw-home-layer"><h1>Care comes together.</h1>
      <p>Plan your pet’s day, one thoughtful task at a time.</p></div>
      <img class="paw-home-dog paw-home-layer" src="{dog}" alt="">
      <img class="paw-home-cat paw-home-layer" src="{cat}" alt="">
      <div class="paw-home-fade"></div></div></div>
    <div class="paw-home-after"><h2>A little more time for care.</h2>
    <p>Describe a task, review the details, and add it to your calendar.</p></div>
    <script>
    (() => {{
      if (window.pawHomeCleanup) window.pawHomeCleanup();
      const area = document.getElementById('paw-home-travel');
      const main = document.querySelector('[data-testid="stMain"]');
      if (!area || !main) return;
      const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
      const room = area.querySelector('.paw-home-room');
      const copy = area.querySelector('.paw-home-copy');
      const dog = area.querySelector('.paw-home-dog');
      const cat = area.querySelector('.paw-home-cat');
      let queued = false;
      function update() {{
        queued = false;
        if (!area.isConnected) {{ cleanup(); return; }}
        const d = reduce.matches ? 0 : Math.max(0, Math.min(area.offsetHeight - area.firstElementChild.offsetHeight,
          main.getBoundingClientRect().top - area.getBoundingClientRect().top));
        room.style.transform = `translateY(${{d * .08}}px)`;
        copy.style.transform = `translateY(${{d * .55}}px)`;
        dog.style.transform = `translate(${{d * .10}}px, ${{d * .30}}px)`;
        cat.style.transform = `translate(${{-d * .12}}px, ${{d * .43}}px)`;
      }}
      function schedule() {{ if (!queued) {{ queued = true; requestAnimationFrame(update); }} }}
      function cleanup() {{ main.removeEventListener('scroll', schedule); reduce.removeEventListener('change', schedule); }}
      window.pawHomeCleanup = cleanup;
      main.addEventListener('scroll', schedule, {{passive:true}});
      reduce.addEventListener('change', schedule); update();
    }})();
    </script>''', unsafe_allow_javascript=True)
