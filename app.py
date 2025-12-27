import streamlit as st
import pandas as pd
import io
from datetime import date

# 1. SETUP
st.set_page_config(page_title="Tabuk Blood Bank", layout="wide", page_icon="🏥")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .block-container { padding: 0 !important; } .print-only { display: block !important; } .results-box { border: 2px solid #333; padding: 20px; font-family: 'Times New Roman'; } .footer-sig { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; } }
    .print-only { display: none; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    .status-ok { background:#d4edda; color:#155724; padding:10px; border-radius:5px; margin:5px 0; border-left: 5px solid #28a745; }
    .status-no { background:#f8d7da; color:#721c24; padding:10px; border-radius:5px; margin:5px 0; border-left: 5px solid #dc3545; }
    .dr-badge { position: fixed; bottom: 10px; right: 15px; background: white; padding: 5px; border: 1px solid #ccc; z-index:99; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='dr-badge no-print'>Dr. Haitham Ismail | Consultant</div>", unsafe_allow_html=True)

# DATA Definitions
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# INITIALIZE STATE (Safe Method)
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'ext' not in st.session_state: st.session_state.ext = []

# Manual Init of Input Keys to avoid KeyError
keys = ["c_1","c_2","c_3","c_4","c_5","c_6","c_7","c_8","c_9","c_10","c_11", "s_I","s_II","s_III"]
for k in keys:
    if k not in st.session_state: st.session_state[k] = "Neg"

# ==========================================
# 2. LOGIC: MAGNETIC PARSER (V47 Engine)
# ==========================================
def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

def magnetic_parser(file):
    try:
        xls = pd.ExcelFile(file)
        for sheet in xls.sheet_names:
            df = pd.read_excel(file, sheet_name=sheet, header=None)
            
            # Map Headers
            col_map = {}
            head_row = -1
            
            for r in range(min(40, len(df))):
                cnt = 0
                temp = {}
                for c in range(min(60, len(df.columns))):
                    val = str(df.iloc[r, c]).strip().replace(" ","").replace("\n","")
                    det = None
                    if val in ["c","C","e","E","k","K","s","S"]: det = val
                    elif val.upper() in ["D","RHD"]: det = "D"
                    else:
                        if val.upper() in AGS: det = val.upper()
                    
                    if det:
                        temp[det] = c
                        cnt += 1
                
                if cnt >= 4:
                    head_row = r
                    col_map = temp
                    break
            
            # Extract Rows with Magnetic Search (Left/Center/Right)
            if head_row != -1:
                data = []
                found = 0
                curr = head_row + 1
                while found < 11 and curr < len(df):
                    is_val = False
                    # Check Data Existence nearby D or C column
                    chk_cols = []
                    if "D" in col_map: chk_cols.extend([col_map["D"], col_map["D"]-1, col_map["D"]+1])
                    if "C" in col_map: chk_cols.extend([col_map["C"], col_map["C"]-1, col_map["C"]+1])
                    
                    for cx in chk_cols:
                        if cx >= 0 and cx < len(df.columns):
                            raw = str(df.iloc[curr, cx]).lower()
                            if any(x in raw for x in ['+','0','1','w']): is_val = True; break
                    
                    if is_val:
                        rid = f"Cell {found+1}"
                        rd = {"ID": rid}
                        for ag in AGS:
                            v = 0
                            if ag in col_map:
                                center = col_map[ag]
                                # Scan neighbors
                                scan_zone = [center]
                                if center > 0: scan_zone.append(center-1)
                                if center < len(df.columns)-1: scan_zone.append(center+1)
                                
                                for sz in scan_zone:
                                    v_raw = df.iloc[curr, sz]
                                    if normalize(v_raw) == 1:
                                        v = 1
                                        break
                            rd[ag] = int(v)
                        data.append(rd)
                        found += 1
                    curr += 1
                
                if found >= 1:
                    return pd.DataFrame(data), f"Read Success from {sheet}"
        
        return None, "Data Not Found"
    except Exception as e: return None, str(e)

def can_out(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr=PAIRS.get(ag)
        if pr and ph.get(pr,0)==1: return False
    return True

def rule_check(cand):
    p, n = 0, 0
    # Collect Inputs manually to avoid loop errors
    inputs_p = {i: st.session_state[f"c_{i}"] for i in range(1,12)}
    inputs_s = {k: st.session_state[f"s_{k}"] for k in ["I","II","III"]}
    
    # P
    for i in range(1, 12):
        s = 1 if inputs_p[i]!="Neg" else 0
        h = st.session_state.p11.iloc[i-1].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # S
    for i, label in enumerate(["I","II","III"]):
        s = 1 if inputs_s[label]!="Neg" else 0
        h = st.session_state.p3.iloc[i].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # E
    for x in st.session_state.ext:
        if x['s']==1 and x['p'].get(cand,0)==1: p+=1
        if x['s']==0 and x['p'].get(cand,0)==0: n+=1
        
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    t = "Std Rule" if (p>=3 and n>=3) else ("Mod Rule" if ok else "Not Met")
    return ok, p, n, t

def set_neg():
    for k in keys: st.session_state[k] = "Neg"

# =========================================================
# 3. INTERFACE - MANUAL & HARDCODED (NO LOOPS)
# =========================================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Mode", ["Workstation", "Admin"])
    if st.button("RESET"):
        st.session_state.ext = []
        set_neg()
        st.rerun()

# --- ADMIN ---
if nav == "Admin":
    st.title("Admin Configuration")
    if st.text_input("Password", type="password")=="admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening"])
        with t1:
            u1=st.file_uploader("Upload Panel", type=["xlsx"])
            if u1:
                d,m = magnetic_parser(io.BytesIO(u1.getvalue()))
                if d is not None:
                    st.success(m); st.session_state.p11=d
                else: st.error(m)
            e1 = st.data_editor(st.session_state.p11, hide_index=True)
            if st.button("Save Panel"): st.session_state.p11=e1; st.success("Saved")
        
        with t2:
            u2=st.file_uploader("Upload Scr", type=["xlsx"])
            if u2:
                d2,m2 = magnetic_parser(io.BytesIO(u2.getvalue()))
                if d2 is not None:
                    st.success(m2); st.session_state.p3=d2
            e2 = st.data_editor(st.session_state.p3, hide_index=True)
            if st.button("Save Screen"): st.session_state.p3=e2; st.success("Saved")

# --- USER (HARDCODED INPUTS = NO CRASH) ---
else:
    st.markdown("<h2 style='text-align:center; color:#036'>MCH Tabuk</h2><hr>", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Pt"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    
    colL, colR = st.columns([1, 2])
    with colL:
        st.subheader("1. Screen / AC")
        ac = st.radio("Auto Control", ["Negative","Positive"])
        if ac=="Positive": st.error("DAT REQ"); st.stop()
        st.write("---")
        # MANUAL WIDGETS
        st.selectbox("Scn I", ["Neg","w+","1+","2+"], key="s_I")
        st.selectbox("Scn II", ["Neg","w+","1+","2+"], key="s_II")
        st.selectbox("Scn III", ["Neg","w+","1+","2+"], key="s_III")
        
        if st.button("Set Neg"): set_neg(); st.rerun()

    with colR:
        st.subheader("2. Panel (11 Cells)")
        # MANUAL LAYOUT
        rc1, rc2 = st.columns(2)
        with rc1:
            st.selectbox("1", ["Neg","w+","1+","2+","3+"], key="c_1")
            st.selectbox("2", ["Neg","w+","1+","2+","3+"], key="c_2")
            st.selectbox("3", ["Neg","w+","1+","2+","3+"], key="c_3")
            st.selectbox("4", ["Neg","w+","1+","2+","3+"], key="c_4")
            st.selectbox("5", ["Neg","w+","1+","2+","3+"], key="c_5")
            st.selectbox("6", ["Neg","w+","1+","2+","3+"], key="c_6")
        with rc2:
            st.selectbox("7", ["Neg","w+","1+","2+","3+"], key="c_7")
            st.selectbox("8", ["Neg","w+","1+","2+","3+"], key="c_8")
            st.selectbox("9", ["Neg","w+","1+","2+","3+"], key="c_9")
            st.selectbox("10", ["Neg","w+","1+","2+","3+"], key="c_10")
            st.selectbox("11", ["Neg","w+","1+","2+","3+"], key="c_11")

    st.write("---")
    if st.button("🚀 Run Analysis"):
        # Logic
        ruled = set()
        p_in = {i: st.session_state[f"c_{i}"] for i in range(1,12)}
        s_in = {k: st.session_state[f"s_{k}"] for k in ["I","II","III"]}
        r11 = [st.session_state.p11.iloc[i].to_dict() for i in range(11)]
        r3  = [st.session_state.p3.iloc[i].to_dict() for i in range(3)]
        
        # Rule out
        for ag in AGS:
            for i in range(1,12):
                if p_in[i]=="Neg" and can_out(ag, r11[i-1]): ruled.add(ag); break
        smap = {"I":0,"II":1,"III":2}
        for k, v in s_in.items():
            if v=="Neg":
                for ag in AGS: 
                    if ag not in ruled and can_out(ag, r3[smap[k]]): ruled.add(ag)
        
        match = []
        for c in [x for x in AGS if x not in ruled]:
            mis = False
            for i in range(1,12):
                if p_in[i]!="Neg" and r11[i-1].get(c,0)==0: mis = True
            if not mis: match.append(c)
            
        if not match: st.error("Inconclusive.")
        else:
            allow = True
            st.subheader("Results:")
            for m in match:
                ok, p, n, msg = rule_check(m)
                st.markdown(f"<div class='{'status-ok' if ok else 'status-no'}'><b>Anti-{m}:</b> {msg} ({p} P/{n} N)</div>", unsafe_allow_html=True)
                if not ok: allow = False
            
            if allow:
                if st.button("Print"):
                    h=f"<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'>Pt:{nm}<hr>Res: Anti-{', '.join(match)}<br>Valid (Rule of 3).<br><br>Sig: ___________</div></div><script>window.print()</script>"
                    st.markdown(h, unsafe_allow_html=True)
            else:
                with st.expander("Add Cell"):
                    idx=st.text_input("ID"); rs=st.selectbox("R",["Neg","Pos"]); ph={}
                    cols=st.columns(len(match))
                    for i,m in enumerate(match):
                        ph[m]=1 if cols[i].checkbox(m) else 0
                    if st.button("Confirm"):
                        st.session_state.ext.append({"src":idx,"s":1 if rs=="Pos" else 0,"ph":ph,"res":1 if rs=="Pos" else 0}); st.rerun()
