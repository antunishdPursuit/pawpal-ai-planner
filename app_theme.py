"""Private-approved semantic tokens implemented in the public UI."""
from pathlib import Path
import streamlit as st

CSS = """
<style>
:root {
 --paw-page:#F7F8F4; --paw-surface:#FFFFFF; --paw-text:#18332B;
 --paw-primary:#245C45; --paw-border:#CBD5CB; --paw-muted:#4C6358;
 --paw-muted-surface:#EEF2E9; --paw-selected:#DDEDD9; --paw-rail-text:#FFFFFF;
 --paw-rail-muted:#DBE8DF; --paw-blue:#275A73; --paw-blue-bg:#EAF1F7;
 --paw-rust:#8A4C2E; --paw-rust-bg:#FBEEE5;
 --paw-warning:#784600; --paw-warning-bg:#FFF4DC;
 --paw-error:#8C2525; --paw-error-bg:#FDECEC;
 --paw-success:#245C45; --paw-success-bg:#EAF4EC;
 --paw-space-1:4px; --paw-space-2:8px; --paw-space-3:12px;
 --paw-space-4:16px; --paw-space-6:24px; --paw-space-8:32px;
 --paw-radius:12px; --paw-width:1280px; --paw-rail:232px; --paw-control:44px;
 --paw-title:32px; --paw-heading:20px; --paw-body:16px; --paw-small:14px;
}
.st-key-mobile_nav {display:none;}
.stApp {background:var(--paw-page); color:var(--paw-text);}
.stMainBlockContainer {max-width:var(--paw-width); padding:var(--paw-space-6) var(--paw-space-8);}
h1 {font-size:var(--paw-title)!important; line-height:40px!important; padding-bottom:var(--paw-space-2)!important;}
h2,h3 {font-size:var(--paw-heading)!important;}
button,input,[data-baseweb="select"],[data-testid="stRadio"] label {
 min-height:var(--paw-control);
}
.stButton button,.stFormSubmitButton button,[data-testid="stLinkButton"] a,
.st-key-mobile_nav [role="radio"],.st-key-task_editor [role="radio"] {
 min-height:var(--paw-control)!important; min-width:var(--paw-control)!important;
}
button:focus-visible,input:focus-visible,textarea:focus-visible,
[role="radio"]:focus-visible,[role="tab"]:focus-visible,summary:focus-visible,
a:focus-visible {outline:3px solid var(--paw-primary)!important; outline-offset:3px;}
[data-testid="stSidebar"] {background:var(--paw-text); min-width:var(--paw-rail); width:var(--paw-rail)!important; max-width:var(--paw-rail);}
[data-testid="stSidebar"] * {color:var(--paw-rail-text);}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {color:var(--paw-rail-muted);}
[data-testid="stSidebar"] [data-testid="stRadio"] label {
 padding:var(--paw-space-3) var(--paw-space-4); border-radius:var(--paw-radius);
 margin-bottom:var(--paw-space-2); width:100%;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {background:var(--paw-primary);}
[data-testid="stSidebar"] button:focus-visible,[data-testid="stSidebar"] input:focus-visible {
 outline-color:var(--paw-rail-muted)!important;
}
[data-testid="stCaptionContainer"] {color:var(--paw-muted); font-size:var(--paw-small);}
.paw-brand {display:flex; align-items:center; gap:var(--paw-space-3); font-size:var(--paw-heading); line-height:1.3; margin:var(--paw-space-2) 0 var(--paw-space-8);}
.paw-brand img {width:40px; height:40px; flex-shrink:0;}
.paw-brand small {display:block; font-size:var(--paw-small); color:var(--paw-rail-muted);}
.paw-summary {display:flex; flex-wrap:wrap; gap:var(--paw-space-6); padding:var(--paw-space-4) var(--paw-space-6);
 border:1px solid var(--paw-border); border-radius:var(--paw-radius); background:var(--paw-surface);}
.paw-summary span {color:var(--paw-muted); font-size:var(--paw-small);}
.paw-summary strong {font-size:var(--paw-heading); color:var(--paw-text); margin-right:var(--paw-space-2);}
.st-key-calendar_surface,.st-key-profile_surface,.st-key-settings_surface {
 background:var(--paw-surface); border:1px solid var(--paw-border);
 border-radius:var(--paw-radius); padding:var(--paw-space-6);
}
.st-key-week_grid [data-testid="stHorizontalBlock"] {gap:0;}
.st-key-week_grid [data-testid="stColumn"] {
 background:var(--paw-surface); border-top:1px solid var(--paw-border);
 border-bottom:1px solid var(--paw-border); border-left:1px solid var(--paw-border);
 padding:var(--paw-space-2); min-width:0; min-height:240px;
}
.st-key-week_grid [data-testid="stColumn"]:last-child {border-right:1px solid var(--paw-border);}
.st-key-week_grid button {border:0; width:100%;}
.paw-chip {border-left:3px solid var(--paw-primary); border-radius:var(--paw-space-1);
 padding:var(--paw-space-2); margin:var(--paw-space-2) 0;
 background:var(--paw-success-bg); color:var(--paw-primary); overflow-wrap:anywhere;}
.paw-chip.blue {background:var(--paw-blue-bg); color:var(--paw-blue); border-color:var(--paw-blue);}
.paw-chip.rust {background:var(--paw-rust-bg); color:var(--paw-rust); border-color:var(--paw-rust);}
.paw-chip strong {display:block; font-size:var(--paw-small);}
.paw-chip small {font-size:var(--paw-small);}
.paw-chip.projected {border-left-style:dashed;}
.paw-empty-day {font-size:var(--paw-small); color:var(--paw-muted); padding:var(--paw-space-4) var(--paw-space-2);}
.paw-pet {display:inline-block; color:var(--paw-primary); background:var(--paw-success-bg);
 padding:var(--paw-space-1) var(--paw-space-2); border-radius:var(--paw-space-2); font-size:var(--paw-small);}
.paw-pet.blue {color:var(--paw-blue); background:var(--paw-blue-bg);}
.paw-pet.rust {color:var(--paw-rust); background:var(--paw-rust-bg);}
.paw-state.warning {color:var(--paw-warning); background:var(--paw-warning-bg); padding:var(--paw-space-1) var(--paw-space-2); border-radius:var(--paw-space-2);}
.paw-state.success {color:var(--paw-success); background:var(--paw-success-bg);}
.paw-state {font-size:var(--paw-small); color:var(--paw-muted); margin-left:var(--paw-space-2);}
.paw-task-title {font-weight:600; font-size:var(--paw-body); overflow-wrap:anywhere; margin-bottom:var(--paw-space-2);}
.paw-time {font-size:var(--paw-body); font-weight:600; color:var(--paw-text);}
.paw-task-row {border-left:3px solid var(--paw-primary);}
.paw-empty {padding:var(--paw-space-6); border-radius:var(--paw-radius); background:var(--paw-muted-surface);}
.paw-empty h2 {margin:0 0 var(--paw-space-2);}
.paw-empty p {margin:0; color:var(--paw-muted); max-width:65ch;}
.paw-mobile-heading {display:none;}
[data-testid="stDialog"] [role="dialog"] {
 border-radius:var(--paw-radius); max-height:calc(100dvh - 3 * var(--paw-space-8)); overflow:auto; background:var(--paw-surface)!important;
}
.st-key-task_editor > [data-testid="stLayoutWrapper"]:has(> .st-key-confirm_actions) {position:sticky; bottom:0; z-index:2;}
.st-key-confirm_actions {background:var(--paw-surface);
 padding:var(--paw-space-3) 0; border-top:1px solid var(--paw-border);}
[data-testid="stCheckbox"] label {min-height:var(--paw-control);}
.st-key-task_editor [data-testid="stVerticalBlock"] {gap:var(--paw-space-3);}
@media(max-width:768px) {
 [data-testid="stSidebar"],[data-testid="stExpandSidebarButton"],[data-testid="stHeader"] {display:none!important;}
 .st-key-mobile_nav {display:block;}
 .st-key-week_grid,.st-key-view_switch,.paw-week-title {display:none;}
 .paw-mobile-heading {display:block;}
 .stMainBlockContainer {padding:var(--paw-space-4);}
 .st-key-calendar_surface,.st-key-profile_surface,.st-key-settings_surface {padding:var(--paw-space-4);}
 .paw-summary {gap:var(--paw-space-4); padding:var(--paw-space-3) var(--paw-space-4);}
 .paw-summary strong {font-size:var(--paw-body);}
 [data-testid="stHorizontalBlock"] {flex-wrap:wrap;}
 [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {min-width:0; flex:1 1 100%;}
 .st-key-confirm_actions [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {flex:1 1 40%;}
 [data-testid="stDialog"] [role="dialog"] {max-width:calc(100vw - var(--paw-space-4))!important;}
}
@media(prefers-reduced-motion:reduce) {
 *,*::before,*::after {animation:none!important; transition:none!important;}
}
</style>
"""


def apply_theme():
    st.markdown(CSS, unsafe_allow_html=True)


def favicon():
    return str(Path(__file__).parent / "assets" / "favicon.png")
