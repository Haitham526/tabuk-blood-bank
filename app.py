import streamlit as st
import pandas as pd
import io
from datetime import date

# ==========================================
# 1. SETUP (STABLE)
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { 
        .stApp > header, .sidebar, footer, .no-print { display: none !important; } 
        .print-only { display: block !important; }
        .results-box { border: 2px solid #000; padding: 15px; margin-top: 15px; }
        .footer-sig { position: fixed; bottom: 0; width: 100%; text-align: center; font-size: 12px; }
    }
    .print-only { display: none; }
    
    .status-ok { background:#d4edda; padding:10px; margin:5px 0; border-left: 5px solid green; }
    .status-no { background:#f8d7da; padding:10px; margin:5px 0; border-left: 5px solid red; }
    
    /* Force Grid Width */
    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div style='position:fixed;bottom:10px;right:10px;background:white;padding:5px;border:1px solid #ccc;z-index:999' class='no-print'>Dr. Haitham Ismail</div>", unsafe_allow_html=True)

# CONSTANTS
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
# 2. LOGIC FUNCTIONS
# ==========================================
def clean_val(v):
    # Translator: +w, 1, + -> 1
    s = str(v).lower().strip()
    return 1 if any(x in s for x in ['+','1','pos','w']) else 0

def robust_parser(file):
    try:
        xls = pd.ExcelFile(file)
        # Scan ALL Sheets
        for sheet in xls.sheet_names:
            df = pd.read_excel(file, sheet_name=sheet, header=None)
            
            # 1. MAP COLUMNS
            # Looking for Header Row
            head_idx = -1
            col_map = {} 
            
            # Scan first 40 rows
            for r in range(min(40, len(df))):
                temp_map = {}
                matches = 0
                for c in range(min(60, len(df.columns))):
                    val = str(df.iloc[r, c]).strip().replace(" ","").replace("\n","")
                    det = None
                    # Strict Case Match
                    if val in ["c","C","e","E","k","K","s","S"]: det = val
                    elif val.upper() in ["D","RHD"]: det = "D"
                    else:
                        if val.upper() in AGS: det = val.upper()
                    
                    if det:
                        temp_map[det] = c
                        matches += 1
                
                if matches >= 3:
                    head_idx = r
                    col_map = temp_map
                    break
            
            if head_idx == -1: continue 
            
            # 2. EXTRACT ROWS
            final_data = []
            count = 0
            curr = head_idx + 1
            
            while count < 11 and curr < len(df):
                is_valid = False
                # Check for Data in 'D' or 'C' column (Look Right/Left also for shifted cells)
                search_cols = []
                if "D" in col_map: search_cols = [col_map["D"], col_map["D"]-1, col_map["D"]+1]
                elif "C" in col_map: search_cols = [col_map["C"], col_map["C"]-1, col_map["C"]+1]
                
                for sc in search_cols:
                    if sc >= 0 and sc < len(df.columns):
                        chk = str(df.iloc[curr, sc]).lower()
                        if any(x in chk for x in ['+','0','1','w']): 
                            is_valid = True
                            break
                
                if is_valid:
                    rd = {"ID": f"C{count+1}"}
                    for ag in AGS:
                        v = 0
                        if ag in col_map:
                            center = col_map[ag]
                            # Wide Scan for Value
                            zones = [center, center-1, center+1]
                            for z in zones:
                                if z >=0 and z < len(df.columns):
                                    if clean_val(df.iloc[curr, z]) == 1:
                                        v = 1; break
                        rd[ag] = int(v)
                    final_data.append(rd)
                    count += 1
                curr += 1
                
            if count >= 1:
                return pd.DataFrame(final_data), f"Loaded {count} rows from '{sheet}'"
                
        return None, "Columns Not Found."
    except Exception as e: return None, str(e)

def can_rule_out(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr=PAIRS.get(ag)
        if pr and ph.get(pr,0)==1: return False
    return True

def calc_stats(cand, p11_inputs, s3_inputs):
    # Calculate using direct lists
    p, n = 0, 0
    
    # Panel
    p_df = st.session_state.panel
    for i in range(11):
        s = 1 if p11_inputs[i] != "Neg" else 0
        h = p_df.iloc[i].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
        
    # Screen
    s_df = st.session_state.screen
    for i in range(3):
        s = 1 if s3_inputs[i] != "Neg" else 0
        h = s_df.iloc[i].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    
    # Extra
    for x in st.session_state.extra:
        s = x['s']
        h = x['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
        
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    return ok, p, n

# ==========================================
# 3. INTERFACE (HARDCODED = NO ERRORS)
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    mode = st.radio("Menu", ["Workstation", "Supervisor"])
    if st.button("RESET ALL"):
        st.session_state.extra = []
        st.rerun()

# ----------- ADMIN -----------
if mode == "Supervisor":
    st.title("Admin Panel")
    if st.text_input("Password",type="password")=="admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening"])
        with t1:
            up = st.file_uploader("Upload P11", type=["xlsx"])
            if up:
                df, m = robust_parser(io.BytesIO(up.getvalue()))
                if df is not None:
                    st.success(m)
                    st.session_state.panel = df
                else: st.error(m)
            e1 = st.data_editor(st.session_state.panel, hide_index=True)
            if st.button("Save P11"): st.session_state.panel = e1; st.success("Saved")
        
        with t2:
            st.info("Edit Screening Manually (Faster)")
            e2 = st.data_editor(st.session_state.screen, hide_index=True)
            if st.button("Save Scr"): st.session_state.screen = e2; st.success("Saved")

# ----------- USER -----------
else:
    st.markdown("<center><h2>Maternity & Children Hospital - Tabuk</h2><h4>Serology Workstation</h4></center><hr>", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Pt"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    
    # 🔴 THE FAIL-SAFE FORM 🔴
    with st.form("entry_grid"):
        st.write("### Reactions")
        L, R = st.columns([1, 2])
        
        with L:
            st.write("**Controls**")
            ac_res = st.radio("AC", ["Negative","Positive"])
            st.write("**Screening**")
            # HARDCODED (NO LOOPS)
            s1 = st.selectbox("Scn I", ["Neg","w+","1+","2+"])
            s2 = st.selectbox("Scn II", ["Neg","w+","1+","2+"])
            s3 = st.selectbox("Scn III", ["Neg","w+","1+","2+"])
            
        with R:
            st.write("**Identification Panel**")
            # HARDCODED GRID (Cannot Fail)
            rc1, rc2 = st.columns(2)
            with rc1:
                c1_in = st.selectbox("Cell 1", ["Neg","w+","1+","2+","3+"])
                c2_in = st.selectbox("Cell 2", ["Neg","w+","1+","2+","3+"])
                c3_in = st.selectbox("Cell 3", ["Neg","w+","1+","2+","3+"])
                c4_in = st.selectbox("Cell 4", ["Neg","w+","1+","2+","3+"])
                c5_in = st.selectbox("Cell 5", ["Neg","w+","1+","2+","3+"])
                c6_in = st.selectbox("Cell 6", ["Neg","w+","1+","2+","3+"])
            with rc2:
                c7_in = st.selectbox("Cell 7", ["Neg","w+","1+","2+","3+"])
                c8_in = st.selectbox("Cell 8", ["Neg","w+","1+","2+","3+"])
                c9_in = st.selectbox("Cell 9", ["Neg","w+","1+","2+","3+"])
                c10_in = st.selectbox("Cell 10", ["Neg","w+","1+","2+","3+"])
                c11_in = st.selectbox("Cell 11", ["Neg","w+","1+","2+","3+"])
                
        submit = st.form_submit_button("🚀 RUN ANALYSIS")
        
    # --- ANALYSIS LOGIC ---
    if submit:
        if ac_res == "Positive":
            st.error("🚨 STOP: Auto Control Positive. Perform DAT/Elution.")
        else:
            # Collections
            p_inputs = [c1_in, c2_in, c3_in, c4_in, c5_in, c6_in, c7_in, c8_in, c9_in, c10_in, c11_in]
            s_inputs = [s1, s2, s3]
            
            # 1. EXCLUSION
            ruled_out = set()
            p_rows = [st.session_state.panel.iloc[i].to_dict() for i in range(11)]
            s_rows = [st.session_state.screen.iloc[i].to_dict() for i in range(3)]
            
            # Panel Ex
            for i, val in enumerate(p_inputs):
                if val == "Neg":
                    for ag in AGS:
                        if can_rule_out(ag, p_rows[i]): ruled_out.add(ag)
            # Screen Ex
            for i, val in enumerate(s_inputs):
                if val == "Neg":
                    for ag in AGS:
                        if ag not in ruled_out and can_rule_out(ag, s_rows[i]): ruled_out.add(ag)
            
            candidates = [x for x in AGS if x not in ruled_out]
            
            # 2. MATCHING
            matches = []
            for c in candidates:
                mis = False
                for i, val in enumerate(p_inputs):
                    if val != "Neg" and p_rows[i].get(c,0)==0: mis = True
                if not mis: matches.append(c)
            
            # 3. REPORT
            st.markdown("---")
            if not matches: st.error("No consistent pattern found / All excluded.")
            else:
                valid_all = True
                for m in matches:
                    ok, p, n = calc_stats(m, p_inputs, s_inputs)
                    cls = "status-ok" if ok else "status-no"
                    txt = "Valid Rule of 3" if ok else "Rule Not Met (Need Cells)"
                    st.markdown(f"<div class='{cls}'><b>Anti-{m}:</b> {txt} ({p} Pos / {n} Neg)</div>", unsafe_allow_html=True)
                    if not ok: valid_all = False
                
                if valid_all:
                    ht = f"""<div class='print-only'><br><center><h2>Maternity & Children Hospital - Tabuk</h2><h3>Serology Lab</h3></center><div class='results-box'>Pt Name: {nm} ({mr}) | Tech: {tc} | Date: {dt}<hr><h4>Antibodies Detected: Anti-{', '.join(matches)}</h4><p><b>Verification:</b> Probability Rule Met (p <= 0.05)</p><p><b>Action:</b> Phenotype patient negative. Transfuse Ag-negative blood.</p><br><br>Signature: ____________________</div><div style='position:fixed;bottom:0;text-align:center;width:100%'>Dr. Haitham Ismail | Consultant</div></div><script>window.print()</script>"""
                    st.markdown(ht, unsafe_allow_html=True)
                    st.balloons()
                else:
                    st.warning("⚠️ Add Extra Cells to confirm.")

    # EXTRA CELLS (OUT OF FORM)
    with st.expander("Add Extra Cells"):
        with st.form("ext"):
            eid=st.text_input("ID"); eres=st.selectbox("R",["Neg","Pos"]); eag=st.text_input("Antigens (e.g. D C)")
            if st.form_submit_button("Add"):
                ph = {a:0 for a in AGS}
                for x in eag.split(): 
                    if x.upper() in AGS: ph[x.upper()]=1
                st.session_state.extra.append({"s":1 if eres=="Pos" else 0,"ph":ph})
                st.success("Added! Re-Run Analysis.")
