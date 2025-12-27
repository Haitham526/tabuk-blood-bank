import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. SETUP (تصميم نظيف)
# ==========================================
st.set_page_config(page_title="MCH Tabuk Bank", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .print-only { display: block !important; } .results-box { border: 2px solid #333; padding: 20px; font-family: 'Times New Roman'; font-size:14px; margin-top:20px; } }
    .print-only { display: none; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    .status-box { padding: 10px; margin: 5px 0; border-radius: 5px; color: #fff; text-align: center; }
    .pass { background: #198754; } .fail { background: #dc3545; }
    .sig-badge { position: fixed; bottom: 10px; right: 15px; background: white; padding: 5px; border: 1px solid #ccc; z-index:99; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='sig-badge no-print'>Dr. Haitham Ismail | Consultant</div>", unsafe_allow_html=True)

# Definitions
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# STATE INITIALIZATION
if 'panel' not in st.session_state:
    st.session_state.panel = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'screen' not in st.session_state:
    st.session_state.screen = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'extra' not in st.session_state:
    st.session_state.extra = []

# ==========================================
# 2. LOGIC: THE PASTE ENGINE
# ==========================================
def parse_paste(text_data, limit_rows=11):
    # This takes the raw text from Excel copy and converts to Grid
    try:
        lines = text_data.strip().split('\n')
        data = []
        count = 0
        
        for line in lines:
            if count >= limit_rows: break
            # Split by Tab (Excel default copy)
            cells = line.split('\t')
            
            # Clean values
            clean_cells = []
            for c in cells:
                val = str(c).strip().lower()
                res = 1 if any(x in val for x in ['+', '1', 'pos', 'w', 'yes']) else 0
                clean_cells.append(res)
            
            # If line is valid (has at least 5 cols)
            if len(clean_cells) >= 5:
                # We expect 26 antigens. Take the first 26 columns found
                # Or try to fit them. Let's assume user copies only the DATA columns
                row_dict = {"ID": f"Cell {count+1}" if limit_rows==11 else f"S-{count}"}
                
                # Safety fill
                for idx, ag in enumerate(AGS):
                    if idx < len(clean_cells):
                        row_dict[ag] = clean_cells[idx]
                    else:
                        row_dict[ag] = 0
                
                data.append(row_dict)
                count += 1
                
        return pd.DataFrame(data), f"Successfully loaded {count} rows"
    except Exception as e:
        return None, str(e)

# Rule Logic
def can_out(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr=PAIRS.get(ag)
        if pr and ph.get(pr,0)==1: return False
    return True

def calc_res(c, r11, p, r3, s, ex):
    pos, neg = 0, 0
    # Panel
    for i in range(11):
        if p[i]==1 and r11.iloc[i].get(c,0)==1: pos+=1
        if p[i]==0 and r11.iloc[i].get(c,0)==0: neg+=1
    # Screen
    for i in range(3):
        if s[i]==1 and r3.iloc[i].get(c,0)==1: pos+=1
        if s[i]==0 and r3.iloc[i].get(c,0)==0: neg+=1
    # Ext
    for x in ex:
        if x['s']==1 and x['ph'].get(c,0)==1: pos+=1
        if x['s']==0 and x['ph'].get(c,0)==0: neg+=1
    ok = (pos>=3 and neg>=3) or (pos>=2 and neg>=3)
    return ok, pos, neg

# ==========================================
# 3. INTERFACE
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png",width=60)
    nav=st.radio("Menu",["Workstation","Supervisor"])
    if st.button("RESET SYSTEM"):
        st.session_state.extra=[]
        st.rerun()

# ------- ADMIN -------
if nav == "Supervisor":
    st.title("Admin Configuration (Copy/Paste Mode)")
    if st.text_input("Password",type="password")=="admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening"])
        
        with t1:
            st.info("طريقة الاستخدام: افتح الاكسيل -> ظلل الأرقام فقط (بدون عناوين) -> انسخ -> الصق هنا")
            txt = st.text_area("Paste Excel Data (Panel 11)", height=150)
            if st.button("Process Data (Panel)"):
                df, m = parse_paste(txt, 11)
                if df is not None:
                    st.success(m); st.session_state.panel = df
                else: st.error(m)
            st.write("Preview:")
            e1=st.data_editor(st.session_state.panel, hide_index=True)
            if st.button("Save P11"): st.session_state.panel=e1; st.success("Saved")

        with t2:
            st.info("Paste Screen Cells (3 Rows)")
            txt2 = st.text_area("Paste Excel Data (Screen)", height=100)
            if st.button("Process Data (Screen)"):
                df2, m2 = parse_paste(txt2, 3)
                if df2 is not None:
                    st.success(m2); st.session_state.screen = df2
            e2=st.data_editor(st.session_state.screen, hide_index=True)
            if st.button("Save Scr"): st.session_state.screen=e2; st.success("Saved")

# ------- USER -------
else:
    st.markdown("<center><h2 style='color:#036'>MCH Tabuk - Serology Workstation</h2></center><hr>", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Pt Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    # INPUT FORM
    with st.form("entry"):
        st.write("### 1. Reactions")
        L, R = st.columns([1, 2])
        
        with L:
            st.write("Controls")
            ac=st.radio("Auto Control",["Neg","Pos"])
            s1=st.selectbox("Scn I",["Neg","w+","1+","2+"])
            s2=st.selectbox("Scn II",["Neg","w+","1+","2+"])
            s3=st.selectbox("Scn III",["Neg","w+","1+","2+"])
        
        with R:
            st.write("Panel")
            rc1, rc2 = st.columns(2)
            c1_v = rc1.selectbox("Cell 1", ["Neg","w+","1+","2+"])
            c2_v = rc1.selectbox("Cell 2", ["Neg","w+","1+","2+"])
            c3_v = rc1.selectbox("Cell 3", ["Neg","w+","1+","2+"])
            c4_v = rc1.selectbox("Cell 4", ["Neg","w+","1+","2+"])
            c5_v = rc1.selectbox("Cell 5", ["Neg","w+","1+","2+"])
            c6_v = rc1.selectbox("Cell 6", ["Neg","w+","1+","2+"])
            
            c7_v = rc2.selectbox("Cell 7", ["Neg","w+","1+","2+"])
            c8_v = rc2.selectbox("Cell 8", ["Neg","w+","1+","2+"])
            c9_v = rc2.selectbox("Cell 9", ["Neg","w+","1+","2+"])
            c10_v = rc2.selectbox("Cell 10", ["Neg","w+","1+","2+"])
            c11_v = rc2.selectbox("Cell 11", ["Neg","w+","1+","2+"])

        sub = st.form_submit_button("🚀 Run Analysis")
    
    # ANALYZE
    if sub:
        if ac=="Pos": st.error("DAT REQ"); st.stop()
        
        # Maps
        in_p = [1 if x!="Neg" else 0 for x in [c1_v,c2_v,c3_v,c4_v,c5_v,c6_v,c7_v,c8_v,c9_v,c10_v,c11_v]]
        in_s = [1 if x!="Neg" else 0 for x in [s1,s2,s3]]
        
        ruled = set()
        for ag in AGS:
            # Panel
            for i, res in enumerate(in_p):
                if res==0 and can_out(ag, st.session_state.panel.iloc[i]): ruled.add(ag); break
            # Screen
            for i, res in enumerate(in_s):
                if res==0 and ag not in ruled and can_out(ag, st.session_state.screen.iloc[i]): ruled.add(ag)
        
        cands = [x for x in AGS if x not in ruled]
        match = []
        for c in cands:
            mis = False
            for i, res in enumerate(in_p):
                if res==1 and st.session_state.panel.iloc[i].get(c,0)==0: mis=True
            if not mis: match.append(c)
            
        st.subheader("Result")
        if not match: st.error("Inconclusive.")
        else:
            allow = True
            for m in match:
                ok, p, n = calc_res(m, st.session_state.panel, in_p, st.session_state.screen, in_s, st.session_state.extra)
                cls="pass" if ok else "fail"
                msg="Rule Met" if ok else "Need Cells"
                st.markdown(f"<div class='status-box {cls}'><b>Anti-{m}:</b> {msg} ({p} Pos/{n} Neg)</div>",unsafe_allow_html=True)
                if not ok: allow=False
            
            if allow:
                rpt=f"<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'>Pt: {nm}<br>Anti-{', '.join(match)} Confirmed.<br>Sign: ________</div></div><script>window.print()</script>"
                st.markdown(rpt,unsafe_allow_html=True)
                st.balloons()
            else:
                with st.expander("Add Extra Cell"):
                    with st.form("ex_f"):
                        id_x=st.text_input("ID"); rs_x=st.selectbox("R",["Neg","Pos"]); ph={}
                        st.write("Antigens (Separated by space):")
                        txt=st.text_input("Ag List")
                        if st.form_submit_button("Add"):
                            for t in txt.split(): ph[t.strip().upper()]=1
                            st.session_state.extra.append({"s":1 if rs_x=="Pos" else 0,"ph":ph})
                            st.success("Added! Re-Run.")

    if st.session_state.extra:
        st.write(f"Extra cells: {len(st.session_state.extra)}")
