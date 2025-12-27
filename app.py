import streamlit as st
import pandas as pd
import io
from datetime import date

# -----------------------------------------------------------------------------
# 1. SETUP (STABLE)
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Tabuk Blood Bank", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .print-only { display: block !important; } .results-box { border: 2px solid #333; padding: 20px; font-family: 'Times New Roman'; } .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; } }
    .print-only { display: none; }
    .header-box { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    .status-pass { background-color: #d1e7dd; padding: 10px; border-radius: 5px; color: #0f5132; margin-bottom: 5px; border-left: 5px solid #198754; } 
    .status-fail { background-color: #f8d7da; padding: 10px; border-radius: 5px; color: #842029; margin-bottom: 5px; border-left: 5px solid #dc3545; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    .sig-badge { position: fixed; bottom: 10px; right: 15px; background: white; padding: 5px 10px; border: 1px solid #ccc; border-radius: 5px; z-index:99; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='sig-badge no-print'>Dr. Haitham Ismail | Consultant</div>", unsafe_allow_html=True)

# ANTIGENS LIST
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# --- FAIL-SAFE INIT ---
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
keys_safe = ["s_I", "s_II", "s_III", "c_1", "c_2", "c_3", "c_4", "c_5", "c_6", "c_7", "c_8", "c_9", "c_10", "c_11"]
for k in keys_safe:
    if k not in st.session_state: st.session_state[k] = "Neg"
if 'ext' not in st.session_state: st.session_state.ext = []

# =========================================================
# 2. MAGNETIC PARSER (The FIX for Shifted Columns)
# =========================================================
def magnetic_check(df, r_idx, c_idx):
    """Checks the target cell AND neighbors (left/right) for + symbols"""
    # Define search window: Center, Left, Right
    scan_cols = [c_idx, c_idx-1, c_idx+1]
    
    for c in scan_cols:
        # Boundary check
        if 0 <= c < len(df.columns):
            val = str(df.iloc[r_idx, c]).lower().strip()
            # If ANY positive sign found nearby -> Return 1
            if any(x in val for x in ['+', '1', 'pos', 'yes', 'w']):
                return 1
    return 0

def final_parser(file):
    try:
        xls = pd.ExcelFile(file)
        for sheet in xls.sheet_names:
            df = pd.read_excel(file, sheet_name=sheet, header=None)
            
            # 1. FIND HEADER
            col_map = {}
            header_row = -1
            
            for r in range(min(40, len(df))):
                temp = {}
                matches = 0
                for c in range(min(60, len(df.columns))):
                    v = str(df.iloc[r, c]).strip().replace(" ","").replace("\n","")
                    det = None
                    # Strict Case
                    if v in ["c","C","e","E","k","K","s","S"]: det = v
                    elif v.upper() in ["D","RHD"]: det = "D"
                    else:
                        if v.upper() in AGS: det = v.upper()
                    
                    if det:
                        temp[det] = c
                        matches += 1
                
                # Check confidence (Found enough headers)
                if matches >= 4:
                    header_row = r
                    col_map = temp
                    break
            
            # 2. EXTRACT ROWS
            if header_row != -1:
                final = []
                count = 0
                curr = header_row + 1
                
                while count < 11 and curr < len(df):
                    is_valid = False
                    
                    # Validate Row by checking D column (with Magnetic Search)
                    if "D" in col_map:
                        is_valid = magnetic_check(df, curr, col_map["D"])
                    
                    if is_valid:
                        rid = f"Cell {count+1}"
                        rd = {"ID": rid}
                        
                        for ag in AGS:
                            if ag in col_map:
                                # USE MAGNETIC SEARCH HERE
                                val = magnetic_check(df, curr, col_map[ag])
                                rd[ag] = int(val)
                            else:
                                rd[ag] = 0
                        
                        final.append(rd)
                        count += 1
                    
                    curr += 1
                
                if count >= 1:
                    return pd.DataFrame(final), f"Success from '{sheet}'"
        
        return None, "Structure Not Found"
    except Exception as e: return None, str(e)

# Helpers
def can_out(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr=PAIRS.get(ag)
        if pr and ph.get(pr,0)==1: return False
    return True

def rule_check(c, p11, r11, p3, r3, ex):
    p, n = 0, 0
    # Panel
    for i in range(1,12):
        s = 1 if r11[f"c_{i}"]!="Neg" else 0
        h = p11.iloc[i-1].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    for i, s_lbl in enumerate(["I","II","III"]):
        sc = 1 if r3[f"s_{s_lbl}"]!="Neg" else 0
        h = p3.iloc[i].get(c,0)
        if sc==1 and h==1: p+=1
        if sc==0 and h==0: n+=1
    # Extra
    for x in ex:
        if x['s']==1 and x['ph'].get(c,0)==1: p+=1
        if x['s']==0 and x['ph'].get(c,0)==0: n+=1
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    msg = "Standard Rule" if (p>=3 and n>=3) else ("Modified Rule" if ok else "Fail")
    return ok, p, n, msg

# =========================================================
# 3. INTERFACE (STABLE)
# =========================================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png",width=60)
    nav=st.radio("Menu",["Workstation","Supervisor"])
    if st.button("Reset"):
        st.session_state.ext = []
        for i in range(1,12): st.session_state[f"c_{i}"] = "Neg"
        st.rerun()

# --- ADMIN ---
if nav == "Supervisor":
    st.title("Admin Panel")
    if st.text_input("Password",type="password")=="admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening"])
        with t1:
            st.info("Upload uses Magnetic Search (Left/Right Tolerance)")
            up1=st.file_uploader("Upload P11", type=["xlsx"])
            if up1:
                d1,m1 = final_parser(io.BytesIO(up1.getvalue()))
                if d1 is not None:
                    st.success(m1)
                    st.session_state.p11 = d1
                else: st.error(m1)
            
            # EDIT & SAVE
            e1 = st.data_editor(st.session_state.p11, hide_index=True)
            if st.button("Save P11"): 
                st.session_state.p11 = e1
                st.success("✅ Panel 11 Saved!")
        
        with t2:
            st.info("Upload Screening")
            up2=st.file_uploader("Upload Scr", type=["xlsx"])
            if up2:
                d2,m2 = final_parser(io.BytesIO(up2.getvalue()))
                if d2 is not None:
                    st.success(m2)
                    st.session_state.p3 = d2
            # EDIT & SAVE
            e2 = st.data_editor(st.session_state.p3, hide_index=True)
            if st.button("Save Scr"): 
                st.session_state.p3 = e2
                st.success("✅ Screening Saved!")

# --- USER ---
else:
    st.markdown("<div class='header-box'><h2>Maternity & Children Hospital - Tabuk</h2></div>", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    L, R = st.columns([1, 1.5])
    with L:
        st.subheader("1. Screen/Ctl")
        ac = st.radio("AC", ["Negative","Positive"])
        if ac=="Positive": st.error("STOP: DAT Req"); st.stop()
        st.write("---")
        # SAFE UI
        st.session_state["s_I"] = st.selectbox("S-I", ["Neg","w+","1+","2+"], key="si")
        st.session_state["s_II"] = st.selectbox("S-II", ["Neg","w+","1+","2+"], key="sii")
        st.session_state["s_III"] = st.selectbox("S-III", ["Neg","w+","1+","2+"], key="siii")
        
    with R:
        st.subheader("2. Panel")
        c1, c2 = st.columns(2)
        # SAFE UI (Hardcoded Keys)
        with c1:
            st.session_state["c_1"] = st.selectbox("1", ["Neg","w+","1+","2+","3+"], key="p1")
            st.session_state["c_2"] = st.selectbox("2", ["Neg","w+","1+","2+","3+"], key="p2")
            st.session_state["c_3"] = st.selectbox("3", ["Neg","w+","1+","2+","3+"], key="p3")
            st.session_state["c_4"] = st.selectbox("4", ["Neg","w+","1+","2+","3+"], key="p4")
            st.session_state["c_5"] = st.selectbox("5", ["Neg","w+","1+","2+","3+"], key="p5")
            st.session_state["c_6"] = st.selectbox("6", ["Neg","w+","1+","2+","3+"], key="p6")
        with c2:
            st.session_state["c_7"] = st.selectbox("7", ["Neg","w+","1+","2+","3+"], key="p7")
            st.session_state["c_8"] = st.selectbox("8", ["Neg","w+","1+","2+","3+"], key="p8")
            st.session_state["c_9"] = st.selectbox("9", ["Neg","w+","1+","2+","3+"], key="p9")
            st.session_state["c_10"] = st.selectbox("10", ["Neg","w+","1+","2+","3+"], key="p10")
            st.session_state["c_11"] = st.selectbox("11", ["Neg","w+","1+","2+","3+"], key="p11")

    st.write("---")
    if st.button("🚀 Analyze", type="primary"):
        # Logic Calc
        r11 = [st.session_state.p11.iloc[i].to_dict() for i in range(11)]
        r3  = [st.session_state.p3.iloc[i].to_dict() for i in range(3)]
        
        ruled = set()
        # 1. Ruleout P
        for ag in AGS:
            for i in range(1, 12):
                if st.session_state[f"c_{i}"] == "Neg" and can_out(ag, r11[i-1]):
                    ruled.add(ag); break
        # 2. Ruleout S
        idx={"I":0,"II":1,"III":2}
        for k in ["I","II","III"]:
            if st.session_state[f"s_{k}"] == "Neg":
                for ag in AGS:
                    if ag not in ruled and can_out(ag, r3[idx[k]]): ruled.add(ag)
        
        # 3. Match
        match = []
        for c in [x for x in AGS if x not in ruled]:
            mis = False
            for i in range(1, 12):
                if st.session_state[f"c_{i}"] != "Neg" and r11[i-1].get(c,0)==0: mis = True
            if not mis: match.append(c)
            
        st.subheader("Results")
        if not match: st.error("Inconclusive.")
        else:
            final_ok = True
            for m in match:
                ok, p, n, msg = rule_check(m, st.session_state.p11, st.session_state.res, st.session_state.p3, st.session_state.scr, st.session_state.ext)
                st.markdown(f"<div class='status-{'pass' if ok else 'fail'}'><b>Anti-{m}:</b> {msg} ({p}P / {n}N)</div>", unsafe_allow_html=True)
                if not ok: final_ok = False
            
            if final_ok:
                if st.button("Print"):
                    h = f"<div class='print-only'><center><h2>MCH Tabuk</h2></center><br>Pt:{nm}<hr>Anti-{', '.join(match)} Confirmed.<br>Sig:_________</div><script>window.print()</script>"
                    st.markdown(h, unsafe_allow_html=True)
            else:
                with st.expander("Add Cell"):
                    id=st.text_input("ID"); rs=st.selectbox("R",["Neg","Pos"]); ph={}
                    cols=st.columns(len(match))
                    for i,m in enumerate(match):
                        if cols[i].checkbox(m): ph[m]=1
                        else: ph[m]=0
                    if st.button("Add"):
                        st.session_state.ext.append({"src":id,"s":1 if rs=="Pos" else 0,"ph":ph,"res":1}); st.rerun()
