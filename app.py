import streamlit as st
import pandas as pd
import io
from datetime import date

# =========================================================
# 1. BASE CONFIGURATION
# =========================================================
st.set_page_config(page_title="Tabuk Blood Bank", layout="wide", page_icon="🏥")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .print-only { display: block !important; } .results-box { border: 2px solid #333; padding: 20px; font-family: 'Times New Roman'; } .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; } }
    .print-only { display: none; }
    .header-box { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    .status-pass { background-color: #d1e7dd; padding: 10px; border-radius: 5px; color: #0f5132; margin-bottom: 5px; border-left: 5px solid #198754; } 
    .status-fail { background-color: #f8d7da; padding: 10px; border-radius: 5px; color: #842029; margin-bottom: 5px; border-left: 5px solid #dc3545; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    .sig-badge { position: fixed; bottom: 10px; right: 15px; background: white; padding: 5px; border: 1px solid #ccc; border-radius: 5px; font-size: 11px; z-index:99; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='sig-badge no-print'>Dr. Haitham Ismail | Consultant</div>", unsafe_allow_html=True)

# DATA
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# --- FAIL-SAFE INITIALIZATION ---
# نضمن وجود الجداول بقيم صفرية صحيحة
if 'p11' not in st.session_state: 
    st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: 
    st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'ext' not in st.session_state: 
    st.session_state.ext = []

# =========================================================
# 2. THE WORKING PARSER (V47) - اللي قرأ ملفك صح
# =========================================================
def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

def final_parser(file):
    try:
        xls = pd.ExcelFile(file)
        # Scan all sheets
        for sheet in xls.sheet_names:
            df = pd.read_excel(file, sheet_name=sheet, header=None)
            
            # Map Header
            col_map = {}
            header_row = -1
            
            for r in range(min(40, len(df))):
                cnt = 0
                temp = {}
                for c in range(min(60, len(df.columns))):
                    v = str(df.iloc[r, c]).strip().replace(" ","").replace("\n","")
                    det = None
                    if v in ["c","C","e","E","k","K","s","S"]: det = v
                    elif v.upper() in ["D","RHD"]: det = "D"
                    else:
                        if v.upper() in AGS: det = v.upper()
                    
                    if det:
                        temp[det] = c
                        cnt += 1
                if cnt >= 4:
                    header_row = r
                    col_map = temp
                    break
            
            if header_row != -1:
                final = []
                count = 0
                curr = header_row + 1
                while count < 11 and curr < len(df):
                    is_val = False
                    check_cols = [col_map.get("D"), col_map.get("C")]
                    for cc in [x for x in check_cols if x is not None]:
                        raw = str(df.iloc[curr, cc]).lower()
                        if any(x in raw for x in ['+','0','1','w']): is_val = True; break
                    
                    if is_val:
                        rid = f"Cell {count+1}"
                        rd = {"ID": rid}
                        for ag in AGS:
                            v = 0
                            if ag in col_map: v = normalize(df.iloc[curr, col_map[ag]])
                            rd[ag] = int(v)
                        final.append(rd)
                        count += 1
                    curr += 1
                if count >= 1: return pd.DataFrame(final), f"Read from {sheet} OK"
                
        return None, "Columns Not Found"
    except Exception as e: return None, str(e)

def can_out(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr=PAIRS.get(ag)
        if pr and ph.get(pr,0)==1: return False
    return True

def rule_check(c, p11, r11, p3, r3, ex):
    p, n = 0, 0
    # Panel
    for i in range(1, 12):
        s = 1 if r11[i]!="Neg" else 0
        h = p11.iloc[i-1].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    for i, x in enumerate(["I","II","III"]):
        s = 1 if r3[x]!="Neg" else 0
        h = p3.iloc[i].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extra
    for x in ex:
        if x['s']==1 and x['ph'].get(c,0)==1: p+=1
        if x['s']==0 and x['ph'].get(c,0)==0: n+=1
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    msg = "Standard Rule" if (p>=3 and n>=3) else ("Modified Rule" if ok else "Fail")
    return ok, p, n, msg

# =========================================================
# 3. INTERFACE (MANUAL & SAFE)
# =========================================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Admin Config"])
    if st.button("Reset"):
        st.session_state.ext = []
        st.rerun()

# --------- ADMIN ---------
if nav == "Admin Config":
    st.title("Admin Panel")
    if st.text_input("Pwd", type="password")=="admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening"])
        with t1:
            u1=st.file_uploader("Upload Panel 11", type=["xlsx"])
            if u1:
                d1,m1 = final_parser(io.BytesIO(u1.getvalue()))
                if d1 is not None:
                    st.success(m1); st.session_state.p11=d1
                else: st.error(m1)
            e1 = st.data_editor(st.session_state.p11, hide_index=True)
            if st.button("Save P11"): st.session_state.p11=e1; st.success("Saved")
        with t2:
            u2=st.file_uploader("Upload Screen 3", type=["xlsx"])
            if u2:
                d2,m2 = final_parser(io.BytesIO(u2.getvalue()))
                if d2 is not None:
                    st.success(m2); st.session_state.p3=d2
                else: st.error(m2)
            e2 = st.data_editor(st.session_state.p3, hide_index=True)
            if st.button("Save Scr"): st.session_state.p3=e2; st.success("Saved")

# --------- USER (NO LOOP UI) ---------
else:
    st.markdown("<div class='header-box'><h2>Maternity & Children Hospital - Tabuk</h2></div>", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    L, R = st.columns([1, 2])
    with L:
        st.subheader("1. Screen/Control")
        ac = st.radio("AC", ["Negative","Positive"])
        if ac=="Positive": st.error("DAT Required"); st.stop()
        
        # --- SAFE MANUAL INPUTS ---
        si = st.selectbox("Scn I", ["Neg","w+","1+","2+"], key="box_s1")
        sii = st.selectbox("Scn II", ["Neg","w+","1+","2+"], key="box_s2")
        siii = st.selectbox("Scn III", ["Neg","w+","1+","2+"], key="box_s3")
        screen_results = {"I": si, "II": sii, "III": siii}
        
    with R:
        st.subheader("2. Panel Reactions")
        # --- SAFE MANUAL INPUTS (No Loop = No Crash) ---
        colA, colB = st.columns(2)
        with colA:
            c1_v = st.selectbox("C1", ["Neg","w+","1+","2+","3+"], key="c1")
            c2_v = st.selectbox("C2", ["Neg","w+","1+","2+","3+"], key="c2")
            c3_v = st.selectbox("C3", ["Neg","w+","1+","2+","3+"], key="c3")
            c4_v = st.selectbox("C4", ["Neg","w+","1+","2+","3+"], key="c4")
            c5_v = st.selectbox("C5", ["Neg","w+","1+","2+","3+"], key="c5")
            c6_v = st.selectbox("C6", ["Neg","w+","1+","2+","3+"], key="c6")
        with colB:
            c7_v = st.selectbox("C7", ["Neg","w+","1+","2+","3+"], key="c7")
            c8_v = st.selectbox("C8", ["Neg","w+","1+","2+","3+"], key="c8")
            c9_v = st.selectbox("C9", ["Neg","w+","1+","2+","3+"], key="c9")
            c10_v = st.selectbox("C10", ["Neg","w+","1+","2+","3+"], key="c10")
            c11_v = st.selectbox("C11", ["Neg","w+","1+","2+","3+"], key="c11")
            
        panel_results = {1:c1_v, 2:c2_v, 3:c3_v, 4:c4_v, 5:c5_v, 6:c6_v, 7:c7_v, 8:c8_v, 9:c9_v, 10:c10_v, 11:c11_v}

    st.write("---")
    
    if st.button("🚀 Run Analysis"):
        r11 = [st.session_state.p11.iloc[i].to_dict() for i in range(11)]
        r3  = [st.session_state.p3.iloc[i].to_dict() for i in range(3)]
        ruled = set()
        
        # Ruleout P11
        for ag in AGS:
            for i, val in panel_results.items():
                if val=="Neg" and can_out(ag, r11[i-1]): ruled.add(ag); break
        # Ruleout Screen
        idx_map={"I":0,"II":1,"III":2}
        for k, v in screen_results.items():
            if v=="Neg":
                for ag in AGS:
                    if ag not in ruled and can_out(ag, r3[idx_map[k]]): ruled.add(ag)
        
        matches = []
        for cand in [x for x in AGS if x not in ruled]:
            mis = False
            for i, val in panel_results.items():
                if val!="Neg" and r11[i-1].get(cand,0)==0: mis = True
            if not mis: matches.append(cand)
            
        st.subheader("Result")
        if not matches: st.error("Inconclusive.")
        else:
            allow_f = True
            for m in matches:
                ok,p,n,msg = rule_check(m, st.session_state.p11, panel_results, st.session_state.p3, screen_results, st.session_state.ext)
                st.markdown(f"<div class='status-{'pass' if ok else 'fail'}'><b>Anti-{m}:</b> {msg} ({p} P / {n} N)</div>", unsafe_allow_html=True)
                if not ok: allow_f = False
            
            if allow_f:
                if st.button("Print"):
                    h=f"<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'>Pt: {nm} | {mr}<hr>Res: Anti-{', '.join(matches)}<br>Valid.<br><br>Sig: ___________</div></div><script>window.print()</script>"
                    st.markdown(h, unsafe_allow_html=True)
            else:
                with st.expander("➕ Add Cell"):
                    idx=st.text_input("ID"); rs=st.selectbox("R",["Neg","Pos"]); ph={}
                    cols=st.columns(len(matches))
                    for i,mm in enumerate(matches):
                        if cols[i].checkbox(mm): ph[mm]=1
                        else: ph[mm]=0
                    if st.button("Add"):
                        st.session_state.ext.append({"src":idx,"s":1 if rs=="Pos" else 0,"ph":ph,"res":1 if rs=="Pos" else 0})
                        st.rerun()
