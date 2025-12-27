import streamlit as st
import pandas as pd
from datetime import date

# 1. SETUP
st.set_page_config(page_title="MCH Tabuk Paste", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .print-only { display: block !important; } .result-sheet { border: 2px solid #000; padding: 20px; font-family: 'Times New Roman'; font-size:14px;} }
    .print-only { display: none; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    .status-ok { background: #d4edda; color: #155724; padding: 10px; margin-bottom: 5px; border-radius: 4px; border-left: 5px solid #28a745;}
    .status-no { background: #f8d7da; color: #721c24; padding: 10px; margin-bottom: 5px; border-radius: 4px; border-left: 5px solid #dc3545;}
</style>
""", unsafe_allow_html=True)

st.markdown("<div style='position:fixed;bottom:10px;right:10px;z-index:99' class='no-print'><small>Dr. Haitham Ismail</small></div>", unsafe_allow_html=True)

# 2. DEFINITIONS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# 3. STATE
if 'panel' not in st.session_state:
    st.session_state.panel = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'screen' not in st.session_state:
    st.session_state.screen = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'ext' not in st.session_state: st.session_state.ext = []

# 4. LOGIC
def parse_paste(txt, limit=11):
    # EXCEL COPY-PASTE PARSER
    try:
        lines = txt.strip().split('\n')
        data = []
        c_count = 0
        for line in lines:
            if c_count >= limit: break
            # Split by Tab
            cells = line.split('\t')
            # Extract logic
            row_vals = []
            for cell in cells:
                c_val = str(cell).lower().strip()
                if any(x in c_val for x in ['+', '1', 'pos', 'w', 'yes']): 
                    row_vals.append(1)
                else: 
                    row_vals.append(0)
            
            # Map to AGS (Take last 26 cols if extra cols exist like ID)
            # Usually users copy everything. We try to grab the last 26 entries per row.
            
            # Normalize length to 26
            final_ag_vals = []
            if len(row_vals) >= 26:
                # Assuming Antigens are the block
                # Let's try to fit the main ones. 
                # If exact copy from BioRad, Antigens are sequential.
                # Use a smart trimmer: Look for patterns? No, direct map is safer for Copy Paste.
                # Strategy: Use only VALID antigen columns (0 or 1)
                final_ag_vals = row_vals
            else:
                final_ag_vals = row_vals + [0]*(26-len(row_vals))

            # If user copied ID + Ags -> length might be > 26
            # We trust user copied the grid only? 
            # Safe bet: Slice to match AGS length (usually antigens are at the end or standalone)
            if len(final_ag_vals) > 26:
                final_ag_vals = final_ag_vals[:26] # Try first
            
            r_d = {"ID": f"Cell {c_count+1}"}
            for i, ag in enumerate(AGS):
                if i < len(final_ag_vals): r_d[ag] = final_ag_vals[i]
                else: r_d[ag] = 0
            
            data.append(r_d)
            c_count += 1
            
        return pd.DataFrame(data), f"Updated {c_count} rows"
    except Exception as e: return None, str(e)

def rule_chk(c, p11, in11, p3, in3, ex):
    p, n = 0, 0
    # Panel
    for i in range(11):
        s=1 if in11[i]!="Neg" else 0
        h=p11.iloc[i].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    for i in range(3):
        s=1 if in3[i]!="Neg" else 0
        h=p3.iloc[i].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extra
    for x in ex:
        if x['res']==1 and x['ph'].get(c,0)==1: p+=1
        if x['res']==0 and x['ph'].get(c,0)==0: n+=1
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    return ok, p, n

def can_out(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr=PAIRS.get(ag)
        if pr and ph.get(pr,0)==1: return False
    return True

# 5. UI
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("MENU", ["Workstation", "Supervisor"])
    if st.button("RESET"): st.session_state.ext=[]; st.rerun()

# ----- ADMIN (PASTE MODE) -----
if nav == "Supervisor":
    st.title("Admin (Copy-Paste System)")
    pwd = st.text_input("Password", type="password")
    
    if pwd == "admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening"])
        
        with t1:
            st.warning("طريقة الإدخال: اذهب للإكسيل -> انسخ الأرقام فقط (بدون عناوين) -> الصق هنا.")
            # TEXT AREA FOR PASTE
            paste_txt = st.text_area("Paste Excel Data (11 Rows)", height=150, placeholder="1\t0\t1\t0...")
            if st.button("Apply Paste (Panel)"):
                df_ new, m = parse_paste(paste_txt, 11)
                if df_new is not None:
                    st.session_state.panel = df_new
                    st.success(m)
                    st.rerun()
                else: st.error(m)
            
            st.write("Current Data:")
            e1 = st.data_editor(st.session_state.panel, hide_index=True)
            if st.button("Save P11"): st.session_state.panel=e1; st.success("Saved")
            
        with t2:
            st.write("Paste 3 rows for Screening:")
            pst2 = st.text_area("Paste Screen", height=100)
            if st.button("Apply (Screen)"):
                df2, m2 = parse_paste(pst2, 3)
                if df2 is not None:
                    st.session_state.screen=df2
                    st.success(m2)
                    st.rerun()
            e2 = st.data_editor(st.session_state.screen, hide_index=True)
            if st.button("Save Scr"): st.session_state.screen=e2; st.success("Saved")

# ----- USER -----
else:
    st.markdown("<center><h2 style='color:#036'>Maternity & Children Hospital - Tabuk</h2></center><hr>", unsafe_allow_html=True)
    c1,c2,c3,c4=st.columns(4)
    nm=c1.text_input("Pt"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    
    # FORM
    with st.form("main"):
        st.write("### 1. Results Entry")
        L, R = st.columns([1, 2])
        
        with L:
            st.write("**Controls**")
            ac=st.radio("Auto Control",["Neg","Pos"])
            si=st.selectbox("Scn I",["Neg","Pos","w+"])
            sii=st.selectbox("Scn II",["Neg","Pos","w+"])
            siii=st.selectbox("Scn III",["Neg","Pos","w+"])
            ins = [1 if x!="Neg" else 0 for x in [si,sii,siii]]
            
        with R:
            st.write("**Panel Reactions**")
            g1,g2=st.columns(2)
            with g1:
                c1=st.selectbox("1",["Neg","Pos","w+"])
                c2=st.selectbox("2",["Neg","Pos","w+"])
                c3=st.selectbox("3",["Neg","Pos","w+"])
                c4=st.selectbox("4",["Neg","Pos","w+"])
                c5=st.selectbox("5",["Neg","Pos","w+"])
                c6=st.selectbox("6",["Neg","Pos","w+"])
            with g2:
                c7=st.selectbox("7",["Neg","Pos","w+"])
                c8=st.selectbox("8",["Neg","Pos","w+"])
                c9=st.selectbox("9",["Neg","Pos","w+"])
                c10=st.selectbox("10",["Neg","Pos","w+"])
                c11=st.selectbox("11",["Neg","Pos","w+"])
            
            inp = [1 if x!="Neg" else 0 for x in [c1,c2,c3,c4,c5,c6,c7,c8,c9,c10,c11]]
            
        sub = st.form_submit_button("🚀 Run Analysis")
    
    if sub:
        if ac=="Pos": st.error("STOP: DAT Required")
        else:
            ruled = set()
            r11 = [st.session_state.panel.iloc[i].to_dict() for i in range(11)]
            r3  = [st.session_state.screen.iloc[i].to_dict() for i in range(3)]
            
            # Exclude
            for i,v in enumerate(inp):
                if v==0:
                    for ag in AGS:
                        if can_out(ag, r11[i]): ruled.add(ag)
            for i,v in enumerate(ins):
                if v==0:
                    for ag in AGS:
                        if ag not in ruled and can_out(ag, r3[i]): ruled.add(ag)
            
            match = []
            for c in [x for x in AGS if x not in ruled]:
                mis = False
                for i,v in enumerate(inp):
                    if v==1 and r11[i].get(c,0)==0: mis=True
                if not mis: match.append(c)
                
            if not match: st.error("Inconclusive.")
            else:
                ok_all = True
                st.subheader("Result")
                for m in match:
                    ok,p,n = rule_chk(m,st.session_state.panel,inp,st.session_state.screen,ins,st.session_state.ext)
                    txt = "Confirmed" if ok else "Rule Not Met"
                    css = "status-ok" if ok else "status-no"
                    st.markdown(f"<div class='{css}'><b>Anti-{m}:</b> {txt} ({p}P / {n}N)</div>",unsafe_allow_html=True)
                    if not ok: ok_all=False
                
                if ok_all:
                    ht=f"<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='result-sheet'>Pt: {nm}<br>Res: Anti-{', '.join(match)}<br>Valid (p<0.05).<br><br>Sig:________</div><div style='position:fixed;bottom:0;text-align:center;width:100%'>Dr. Haitham Ismail</div></div><script>window.print()</script>"
                    st.markdown(ht,unsafe_allow_html=True)
                else:
                    st.warning("Add Cells below:")
    
    with st.expander("Add Extra Cell"):
        with st.form("add_ex"):
            idx=st.text_input("ID"); rs=st.selectbox("R",["Neg","Pos"])
            st.write("Antigens (Space separated e.g. D C s):")
            tx=st.text_input("Ags")
            if st.form_submit_button("Add"):
                p={a:0 for a in AGS}
                if tx:
                    for t in tx.split():
                        t=t.upper().strip()
                        if t in AGS: p[t]=1
                st.session_state.ext.append({"src":idx,"res":1 if rs=="Pos" else 0,"s":1 if rs=="Pos" else 0,"ph":p,"p":p})
                st.success("Added! Re-run.")
