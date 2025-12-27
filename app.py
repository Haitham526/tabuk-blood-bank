import streamlit as st
import pandas as pd
import io
from datetime import date

# ==========================================
# 1. SETUP (CONFIGURATION)
# ==========================================
st.set_page_config(page_title="MCH Blood Bank", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .block-container { padding: 0 !important; } .print-only { display: block !important; } .results-box { border: 2px solid #333; padding: 20px; font-family: 'Times New Roman'; font-size:14px;} .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; } }
    .print-only { display: none; }
    .header-box { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    .status-pass { background-color: #d1e7dd; padding: 10px; border-radius: 5px; color: #0f5132; margin-bottom:5px; border-left: 5px solid #198754; } 
    .status-fail { background-color: #f8d7da; padding: 10px; border-radius: 5px; color: #842029; margin-bottom:5px; border-left: 5px solid #dc3545; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div style='position:fixed;bottom:10px;right:10px;background:white;padding:5px;border:1px solid #ccc;z-index:99' class='no-print'>Dr. Haitham Ismail | Consultant</div>", unsafe_allow_html=True)

# DATA CONSTANTS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]

# SESSION STATE (MEMORY)
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
# User inputs stored directly here to prevent key errors
if 'r_1' not in st.session_state: 
    for i in range(1, 12): st.session_state[f"r_{i}"] = "Neg"
    for s in ["I","II","III"]: st.session_state[f"s_{s}"] = "Neg"
if 'ext' not in st.session_state: st.session_state.ext = []

# ==========================================
# 2. LOGIC FUNCTIONS
# ==========================================
def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

# --- THE PARSER THAT WORKED (For Table 3) ---
def final_parser(file):
    try:
        xls = pd.ExcelFile(file)
        for sheet in xls.sheet_names:
            df = pd.read_excel(file, sheet_name=sheet, header=None)
            
            # Map Cols
            col_map = {}
            head_row = -1
            
            # Scan top 30 rows
            for r in range(min(30, len(df))):
                cnt = 0
                temp = {}
                for c in range(min(60, len(df.columns))):
                    v = str(df.iloc[r, c]).strip().replace(" ","")
                    
                    det = None
                    if v in ["c","C","e","E","k","K","s","S"]: det = v
                    elif v.upper() == "D" or v.upper() == "RHD": det = "D"
                    else:
                        vup = v.upper()
                        if vup in AGS: det = vup
                    
                    if det:
                        temp[det] = c
                        cnt += 1
                
                if cnt >= 4:
                    head_row = r
                    col_map = temp
                    break
            
            if head_row != -1:
                # Extract
                data = []
                extracted = 0
                curr = head_row + 1
                
                while extracted < 11 and curr < len(df):
                    is_val = False
                    # Check D column
                    if "D" in col_map:
                        raw = str(df.iloc[curr, col_map["D"]]).lower()
                        if any(x in raw for x in ['+','0','1','w']): is_val = True
                    
                    if is_val:
                        rid = f"Cell {extracted+1}"
                        rd = {"ID": rid}
                        for ag in AGS:
                            v = 0
                            if ag in col_map:
                                v = normalize(df.iloc[curr, col_map[ag]])
                            rd[ag] = int(v)
                        data.append(rd)
                        extracted += 1
                    curr += 1
                
                if extracted >= 1:
                    return pd.DataFrame(data), f"Success: Read from '{sheet}'"
        
        return None, "Columns Not Found"
    except Exception as e: return None, str(e)

def can_out(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr=PAIRS.get(ag)
        if pr and ph.get(pr,0)==1: return False
    return True

def rule_check(cand):
    p, n = 0, 0
    # Panel
    for i in range(1, 12):
        s = 1 if st.session_state[f"r_{i}"] != "Neg" else 0
        h = st.session_state.p11.iloc[i-1].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    for i, x in enumerate(["I","II","III"]):
        s = 1 if st.session_state[f"s_{x}"] != "Neg" else 0
        h = st.session_state.p3.iloc[i].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Ext
    for c in st.session_state.ext:
        if c['s']==1 and c['p'].get(cand,0)==1: p+=1
        if c['s']==0 and c['p'].get(cand,0)==0: n+=1
    
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    msg = "Standard (3/3)" if (p>=3 and n>=3) else ("Modified" if ok else "Fail")
    return ok, p, n, msg

# ==========================================
# 3. LAYOUT & NAVIGATION
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("MAIN MENU", ["WORKSTATION", "ADMIN CONFIG"])
    st.divider()
    if st.button("RESET"):
        st.session_state.ext = []
        for i in range(1,12): st.session_state[f"r_{i}"] = "Neg"
        st.rerun()

# ----------------- ADMIN -----------------
if nav == "ADMIN CONFIG":
    st.title("Admin Panel Setup")
    if st.text_input("Password", type="password") == "admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening"])
        with t1:
            up1 = st.file_uploader("Upload Panel 11", type=["xlsx"])
            if up1:
                d1, m1 = final_parser(io.BytesIO(up1.getvalue()))
                if d1 is not None:
                    st.success(m1)
                    st.session_state.p11 = d1
                else: st.error(m1)
            e1 = st.data_editor(st.session_state.p11, hide_index=True)
            if st.button("Save P11"): st.session_state.p11 = e1; st.success("Saved")
        
        with t2:
            st.write("Edit Screening Cells (I, II, III)")
            e2 = st.data_editor(st.session_state.p3, hide_index=True)
            if st.button("Save Scr"): st.session_state.p3 = e2; st.success("Saved")

# ----------------- WORKSTATION (FIXED UI) -----------------
else:
    st.markdown("<div class='header-box'><h2>Maternity & Children Hospital - Tabuk</h2><h4>Serology Workstation</h4></div>", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Pt Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    
    st.divider()
    L, R = st.columns([1, 1.5])
    
    with L:
        st.subheader("1. Screen & Auto")
        ac = st.radio("AC", ["Negative","Positive"])
        if ac=="Positive": st.error("STOP: DAT REQUIRED"); st.stop()
        st.write("---")
        # MANUAL SELECTBOXES (NO LOOPS = NO ERROR)
        st.session_state["s_I"] = st.selectbox("Scn I", ["Neg","w+","1+","2+"], key="box_s1")
        st.session_state["s_II"] = st.selectbox("Scn II", ["Neg","w+","1+","2+"], key="box_s2")
        st.session_state["s_III"] = st.selectbox("Scn III", ["Neg","w+","1+","2+"], key="box_s3")
        
    with R:
        st.subheader("2. Panel Reactions")
        # STATIC GRID (SAFE)
        sc1, sc2 = st.columns(2)
        with sc1:
            st.session_state["r_1"] = st.selectbox("C1", ["Neg","w+","1+","2+","3+"], key="b1")
            st.session_state["r_2"] = st.selectbox("C2", ["Neg","w+","1+","2+","3+"], key="b2")
            st.session_state["r_3"] = st.selectbox("C3", ["Neg","w+","1+","2+","3+"], key="b3")
            st.session_state["r_4"] = st.selectbox("C4", ["Neg","w+","1+","2+","3+"], key="b4")
            st.session_state["r_5"] = st.selectbox("C5", ["Neg","w+","1+","2+","3+"], key="b5")
            st.session_state["r_6"] = st.selectbox("C6", ["Neg","w+","1+","2+","3+"], key="b6")
        with sc2:
            st.session_state["r_7"] = st.selectbox("C7", ["Neg","w+","1+","2+","3+"], key="b7")
            st.session_state["r_8"] = st.selectbox("C8", ["Neg","w+","1+","2+","3+"], key="b8")
            st.session_state["r_9"] = st.selectbox("C9", ["Neg","w+","1+","2+","3+"], key="b9")
            st.session_state["r_10"] = st.selectbox("C10", ["Neg","w+","1+","2+","3+"], key="b10")
            st.session_state["r_11"] = st.selectbox("C11", ["Neg","w+","1+","2+","3+"], key="b11")

    # ACTION BUTTONS
    st.write("---")
    c_btn1, c_btn2 = st.columns(2)
    if c_btn1.button("Set All Negative"):
        for i in range(1,12): st.session_state[f"r_{i}"] = "Neg"
        st.rerun()
    
    if st.checkbox("🔍 Analyze"):
        # Logic Exec
        r11 = [st.session_state.p11.iloc[i].to_dict() for i in range(11)]
        r3  = [st.session_state.p3.iloc[i].to_dict() for i in range(3)]
        
        ruled = set()
        # Panel Exclude
        for ag in AGS:
            for i in range(1,12):
                if st.session_state[f"r_{i}"] == "Neg":
                    if can_out(ag, r11[i-1]): ruled.add(ag); break
        
        # Screen Exclude
        si = {"I":0,"II":1,"III":2}
        for k in ["I","II","III"]:
            if st.session_state[f"s_{k}"] == "Neg":
                for ag in AGS:
                    if ag not in ruled and can_out(ag, r3[si[k]]): ruled.add(ag)
        
        matches = []
        for cand in [x for x in AGS if x not in ruled]:
            mis = False
            for i in range(1,12):
                scr = 1 if st.session_state[f"r_{i}"]!="Neg" else 0
                if scr==1 and r11[i-1].get(cand,0)==0: mis = True
            if not mis: matches.append(cand)
            
        if not matches: st.error("No Match Found.")
        else:
            final_ok = True
            st.subheader("Result Validation")
            for m in matches:
                ok, p, n, msg = rule_check(m)
                st.markdown(f"<div class='status-{'pass' if ok else 'fail'}'><b>Anti-{m}:</b> {msg} ({p}P / {n}N)</div>", unsafe_allow_html=True)
                if not ok: final_ok = False
            
            if final_ok:
                if st.button("🖨️ Print Report"):
                    rpt = f"""<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'><b>Pt:</b> {nm}<br><b>Result:</b> Anti-{', '.join(matches)} Detected.<br>Probability Confirmed (p<0.05).<br><br>Sig: ______________</div></div><script>window.print()</script>"""
                    st.markdown(rpt, unsafe_allow_html=True)
            else:
                st.warning("Rule Not Met.")
                with st.expander("Add Extra Cell"):
                    idx=st.text_input("ID"); rs=st.selectbox("R",["Neg","Pos"]); ph={}
                    cols=st.columns(len(matches))
                    for i,m in enumerate(matches): 
                        ph[m]=1 if cols[i].checkbox(m) else 0
                    if st.button("Confirm Add"):
                        st.session_state.ext.append({"src":idx,"res":1 if rs=="Pos" else 0,"s":1 if rs=="Pos" else 0,"p":ph,"ph":ph})
                        st.rerun()
