"""Landing page with an intact pet illustration and a short scroll story."""
import base64
from pathlib import Path

import streamlit as st


@st.cache_data
def _hero_image():
    return base64.b64encode((Path(__file__).parent / "assets" / "home-pets.webp").read_bytes()).decode("ascii")


def show_home(open_planner):
    with st.container(key="homepage_navigation", horizontal=True, vertical_alignment="center"):
        st.button("PawPal AI Planner", key="home_brand")
        st.button("Open planner", type="primary", on_click=open_planner, key="home_open_planner")
    image = _hero_image()
    st.html(f'''<style>
    .stApp:has(.st-key-homepage_navigation) [data-testid="stSidebar"],
    .stApp:has(.st-key-homepage_navigation) [data-testid="stSidebarCollapsedControl"] {{display:none!important;}}
    .stApp:has(.st-key-homepage_navigation) .stMainBlockContainer {{max-width:var(--paw-width);padding:0!important;}}
    .st-key-homepage_navigation {{padding:var(--paw-space-4) var(--paw-space-8);justify-content:space-between;}}
    .st-key-homepage_navigation button {{font-family:system-ui,sans-serif!important;font-size:var(--paw-small)!important;line-height:20px!important;}}
    .st-key-homepage_navigation .st-key-home_brand button {{border:0;background:transparent;color:var(--paw-text);font-weight:700;padding-left:0;}}
    .paw-landing {{font-family:system-ui,sans-serif;color:var(--paw-text);}}
    .paw-hero {{display:grid;grid-template-columns: minmax(260px, .8fr) minmax(0,1.3fr);gap:var(--paw-space-8);
      align-items:center;padding:var(--paw-space-6) var(--paw-space-8) var(--paw-space-8);min-height:68vh;}}
    .paw-hero h1 {{font-size:clamp(32px,4vw,48px)!important;line-height:1.15!important;margin:0 0 var(--paw-space-4);}}
    .paw-hero p {{max-width:330px;line-height:1.5;}}
    .paw-hero-art {{padding-bottom:var(--paw-space-6);}}
    .paw-hero-art img {{display:block;width:100%;height:auto;border-radius:var(--paw-radius);will-change:transform;}}
    .paw-landing a {{display:inline-flex;align-items:center;min-height:var(--paw-control);padding:var(--paw-space-3) var(--paw-space-4);
      background:var(--paw-primary);color:var(--paw-rail-text);border-radius:var(--paw-radius);text-decoration:none;font-size:var(--paw-small);font-weight:600;}}
    .paw-landing a:focus-visible {{outline:3px solid var(--paw-blue);outline-offset:3px;}}
    .paw-home-cards {{padding:var(--paw-space-8);display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--paw-space-6);}}
    .paw-home-card {{padding:var(--paw-space-6);background:var(--paw-surface);border:1px solid var(--paw-border);border-radius:var(--paw-radius);}}
    .paw-home-card h2 {{margin:0 0 var(--paw-space-3);font-size:var(--paw-heading);}}
    .paw-home-card p {{color:var(--paw-muted);line-height:1.5;}}
    .paw-home-example {{padding:var(--paw-space-4);background:var(--paw-muted-surface);border-radius:var(--paw-radius);}}
    .paw-home-example small,.paw-home-example strong {{display:block;margin-bottom:var(--paw-space-2);}}
    .paw-home-example small {{color:var(--paw-muted);}}
    .paw-home-footer {{padding:0 var(--paw-space-8) var(--paw-space-8);}}
    .paw-home-footer a {{color:var(--paw-primary);background:transparent;padding-left:0;}}
    @media(max-width:768px) {{.st-key-homepage_navigation {{padding:var(--paw-space-4);}}
      .paw-hero {{grid-template-columns:1fr;min-height:0;padding:var(--paw-space-6) var(--paw-space-4);gap:var(--paw-space-6);}}
      .paw-hero h1 {{max-width:330px;}}
      .paw-home-cards {{grid-template-columns:1fr;padding:var(--paw-space-6) var(--paw-space-4);}}
      .paw-home-footer {{padding:0 var(--paw-space-4) var(--paw-space-6);}}}}
    @media(prefers-reduced-motion:reduce) {{.paw-hero-art img {{transform:none!important;will-change:auto;}}}}
    </style>
    <div class="paw-landing" id="paw-home-top" tabindex="-1">
    <section class="paw-hero"><div><h1>Care comes together.</h1>
      <p>Plan your pet’s day, one thoughtful task at a time.</p><a href="#paw-home-cards" id="paw-explore">Explore story</a></div>
      <div class="paw-hero-art"><img width="1400" height="933" src="data:image/webp;base64,{image}" alt="A golden dog resting beside a stretching tabby cat at home"></div></section>
    <div class="paw-home-cards" id="paw-home-cards" tabindex="-1">
      <section class="paw-home-card"><h2>Tell PawPal</h2><p>Describe the care your pet needs.</p>
        <div class="paw-home-example"><small>Example request</small>Walk Luna tomorrow at 9 AM.</div></section>
      <section class="paw-home-card"><h2>Review the details</h2><p>Check the task before you save it.</p>
        <div class="paw-home-example"><small>Example preview</small><strong>Walk Luna</strong>Tomorrow · 9:00 AM</div></section>
      <section class="paw-home-card"><h2>See your plan</h2><p>Find your confirmed task on the calendar.</p>
        <div class="paw-home-example"><small>Example calendar</small><strong>Tomorrow</strong>9:00 AM · Walk Luna</div></section></div>
    <div class="paw-home-footer"><a href="#paw-home-top" id="paw-back-top">Back to top</a></div></div>
    <script>
    (() => {{
      if (window.pawHomeCleanup) window.pawHomeCleanup();
      const main=document.querySelector('[data-testid="stMain"]'), root=document.getElementById('paw-home-top');
      if (!main || !root) return;
      const art=root.querySelector('.paw-hero-art img'), explore=document.getElementById('paw-explore'),
        back=document.getElementById('paw-back-top'), brand=document.querySelector('.st-key-home_brand button'),
        reduce=matchMedia('(prefers-reduced-motion: reduce)');
      const behavior=()=>reduce.matches?'auto':'smooth';
      function top(e) {{e.preventDefault();e.stopPropagation();main.scrollTo({{top:0,behavior:behavior()}});root.focus({{preventScroll:true}});}}
      function go(e) {{e.preventDefault();const target=document.getElementById('paw-home-cards');target.scrollIntoView({{block:'start',behavior:behavior()}});target.focus({{preventScroll:true}});}}
      let queued=false;
      function update() {{queued=false;if(!root.isConnected){{cleanup();return;}}
        art.style.transform=`translateY(${{reduce.matches?0:-Math.min(16,main.scrollTop*.04)}}px)`;}}
      function schedule() {{if(!queued){{queued=true;requestAnimationFrame(update);}}}}
      function cleanup() {{main.removeEventListener('scroll',schedule);reduce.removeEventListener('change',schedule);
        explore.removeEventListener('click',go);back.removeEventListener('click',top);brand?.removeEventListener('click',top);}}
      window.pawHomeCleanup=cleanup; main.addEventListener('scroll',schedule,{{passive:true}});
      reduce.addEventListener('change',schedule); explore.addEventListener('click',go);back.addEventListener('click',top);
      brand?.addEventListener('click',top);main.scrollTo({{top:0,behavior:'instant'}});update();
    }})();
    </script>''', unsafe_allow_javascript=True)
