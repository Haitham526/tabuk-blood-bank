import streamlit as st
import pandas as pd
import io

# ------------------------------------------------------------------
# 1. SETUP & CLEANUP (تنظيف الذاكرة لمنع الاخطاء القديمة)
# ------------------------------------------------------------------
st.set_page_config(page_title="Tabuk Bank", layout="wide", page_icon="🩸")

# Style
st.markdown("""
<style>
    @media print { 
        .stApp > header, .sidebar, footer, .no-print { display: none !important; } 
        .print-only { display: block !important; }
        .result-paper { border: 2px solid #333; padding: 30px; font-family: 'Times New Roman'; }
    }
    .print-only { display: none; }
    .hospital-head { text-align: center; border-bottom: 5px solid #004466; padding-bottom: 10px; color: #003366; }
    .status-ok { background: #d4edda; padding: 10px; border-left: 5px solid green; margin: 5px 0; }
    .status-no { background: #f8d7da; padding: 10px; border-left: 5px solid red; margin: 5px 0; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div style='position:fixed;bottom:10px;right:10px;z-index:99;' class='no-print'><small>Dr. Haitham Ismail</small></div>", unsafe_allow_html=True)

# Defs
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# Initial Data (Reset-Proof)
if 'panel' not in st.session_state:
    st.session_state.panel = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'screen' not in st.session_state:
    st.session_state.screen = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'extra' not in st.session_state:
    st.session_state.extra = []

# ------------------------------------------------------------------
# 2. LOGIC FUNCTIONS
# ------------------------------------------------------------------
def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+','1','pos','yes','w']) else 0

def clean_read(file):
    # The Nuclear Parser
    try:
        xls = pd.ExcelFile(file)
        for sheet in xls.sheet_names:
            df = pd.read_excel(file, sheet_name=sheet, header=None)
            
            col_map = {}
            head_row = -1
            
            # Scan first 40 rows
            for r in range(min(40, len(df))):
                temp = {}
                count = 0
                for c in range(min(60, len(df.columns))):
                    val = str(df.iloc[r,c]).strip().replace(" ","")
                    
                    det = None
                    if val in ["c","C","e","E","k","K","s","S"]: det = val # Strict
                    elif val.upper() in ["D","RHD"]: det = "D"
                    elif val.upper() in AGS: det = val.upper()
                    
                    if det: 
                        temp[det] = c; count += 1
                
                if count >= 4:
                    head_row = r; col_map = temp; break
            
            if head_row != -1:
                # Extract
                data = []; cnt = 0; curr = head_row + 1
                while cnt < 11 and curr < len(df):
                    is_val = False
                    d_col = col_map.get("D") or col_map.get("C")
                    if d_col is not None:
                        chk = str(df.iloc[curr, d_col]).lower()
                        # Wide check
                        for off in [0, 1, -1]:
                            if 0 <= d_col+off < len(df.columns):
                                v2 = str(df.iloc[curr, d_col+off]).lower()
                                if any(x in v2 for x in ['+','0','1','w']): is_val=True
                    
                    if is_val:
                        rd = {"ID": f"Cell {cnt+1}"}
                        for ag in AGS:
                            v = 0
                            if ag in col_map:
                                cent = col_map[ag]
                                # Scan neighbors
                                found = 0
                                for off in [0, 1, -1]:
                                    if 0 <= cent+off < len(df.columns):
                                        if normalize(df.iloc[curr, cent+off])==1: found=1
                                rd[ag] = found
                        data.append(rd)
                        cnt += 1
                    curr += 1
                
                if cnt >= 1: return pd.DataFrame(data), f"OK: {sheet}"
        
        return None, "Not Found"
    except Exception as e: return None, str(e)

def can_rule_out(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr=PAIRS.get(ag)
        if pr and ph.get(pr,0)==1: return False
    return True

def calc_r3(cand, inputs):
    # Logic implementation
    pos_match = 0; neg_match = 0
    
    # 1. Panel
    p_df = st.session_state.panel
    for i in range(11):
        s = inputs["p"][i] # 0 or 1
        h = p_df.iloc[i].get(cand,0)
        if s==1 and h==1: pos_match+=1
        if s==0 and h==0: neg_match+=1
        
    # 2. Screen
    s_df = st.session_state.screen
    for i in range(3):
        s = inputs["s"][i]
        h = s_df.iloc[i].get(cand,0)
        if s==1 and h==1: pos_match+=1
        if s==0 and h==0: neg_match+=1
        
    # 3. Extra
    for x in st.session_state.extra:
        s = x['s']
        h = x['ph'].get(cand,0)
        if s==1 and h==1: pos_match+=1
        if s==0 and h==0: neg_match+=1
        
    pass_ok = (pos_match>=3 and neg_match>=3) or (pos_match>=2 and neg_match>=3)
    return pass_ok, pos_match, neg_match

# ==================================================================
# 3. UI - SIMPLEST POSSIBLE FORM (NO CRASH)
# ==================================================================
with st.sidebar:
    nav = st.radio("System Mode", ["Workstation", "Supervisor"])
    st.write("---")
    if st.button("Factory Reset"):
        for key in st.session_state.keys():
            del st.session_state[key]
        st.rerun()

# ------- ADMIN -------
if nav == "Supervisor":
    st.title("Admin Configuration")
    if st.text_input("Password", type="password") == "admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening"])
        with t1:
            f = st.file_uploader("Upload Panel 11", type=["xlsx"])
            if f:
                d, m = clean_read(io.BytesIO(f.getvalue()))
                if d is not None: 
                    st.success(m); st.session_state.panel = d
                else: st.error(m)
            e1 = st.data_editor(st.session_state.panel, hide_index=True)
            if st.button("Save P11"): st.session_state.panel=e1; st.success("Saved")
        
        with t2:
            st.write("Screening")
            e2 = st.data_editor(st.session_state.screen, hide_index=True)
            if st.button("Save Scr"): st.session_state.screen=e2; st.success("Saved")

# ------- USER (THE SAFE FORM) -------
else:
    st.markdown("<div class='hospital-head'><h2>Maternity & Children Hospital - Tabuk</h2></div>", unsafe_allow_html=True)
    
    # 1. INFO
    c1, c2, c3, c4 = st.columns(4)
    nm = c1.text_input("Name")
    mr = c2.text_input("MRN")
    tc = c3.text_input("Tech")
    dt = c4.date_input("Date")
    
    st.divider()
    
    # 2. INPUT FORM (NO AUTO-REFRESH ERRORS)
    with st.form("main_form"):
        colA, colB = st.columns([1, 2])
        
        with colA:
            st.subheader("Control")
            ac_res = st.radio("Auto Control", ["Negative", "Positive"])
            st.subheader("Screen")
            s1 = st.selectbox("S-I", ["Neg","Pos","w+"])
            s2 = st.selectbox("S-II", ["Neg","Pos","w+"])
            s3 = st.selectbox("S-III", ["Neg","Pos","w+"])
            
        with colB:
            st.subheader("Panel Reactions")
            bc1, bc2 = st.columns(2)
            with bc1:
                c1_in = st.selectbox("Cell 1", ["Neg","Pos","w+","2+","3+"])
                c2_in = st.selectbox("Cell 2", ["Neg","Pos","w+","2+","3+"])
                c3_in = st.selectbox("Cell 3", ["Neg","Pos","w+","2+","3+"])
                c4_in = st.selectbox("Cell 4", ["Neg","Pos","w+","2+","3+"])
                c5_in = st.selectbox("Cell 5", ["Neg","Pos","w+","2+","3+"])
                c6_in = st.selectbox("Cell 6", ["Neg","Pos","w+","2+","3+"])
            with bc2:
                c7_in = st.selectbox("Cell 7", ["Neg","Pos","w+","2+","3+"])
                c8_in = st.selectbox("Cell 8", ["Neg","Pos","w+","2+","3+"])
                c9_in = st.selectbox("Cell 9", ["Neg","Pos","w+","2+","3+"])
                c10_in = st.selectbox("Cell 10", ["Neg","Pos","w+","2+","3+"])
                c11_in = st.selectbox("Cell 11", ["Neg","Pos","w+","2+","3+"])
                
        sub = st.form_submit_button("🚀 RUN ANALYSIS")
        
    # 3. ANALYSIS OUTPUT
    if sub:
        if ac_res == "Positive":
            st.error("🚨 STOP: Positive Auto Control. Perform DAT.")
        else:
            # Map Inputs
            def get_s(v): return 0 if v=="Neg" else 1
            inputs_p = [get_s(x) for x in [c1_in,c2_in,c3_in,c4_in,c5_in,c6_in,c7_in,c8_in,c9_in,c10_in,c11_in]]
            inputs_s = [get_s(x) for x in [s1, s2, s3]]
            
            # Exclude
            ruled = set()
            p11 = st.session_state.panel
            p3  = st.session_state.screen
            
            for ag in AGS:
                # Panel
                for i in range(11):
                    if inputs_p[i] == 0:
                        if can_rule_out(ag, p11.iloc[i]): ruled.add(ag); break
                # Screen
                for i in range(3):
                    if inputs_s[i] == 0:
                        if ag not in ruled and can_rule_out(ag, p3.iloc[i]): ruled.add(ag)
                        
            # Include
            candidates = [x for x in AGS if x not in ruled]
            match = []
            for c in candidates:
                miss = False
                for i in range(11):
                    if inputs_p[i]==1 and p11.iloc[i].get(c,0)==0: miss = True
                if not miss: match.append(c)
                
            if not match:
                st.error("Inconclusive.")
            else:
                final_ok = True
                st.subheader("Result")
                for m in match:
                    ok, p, n = calc_r3(m, {"p":inputs_p, "s":inputs_s})
                    msg = "Valid (p<0.05)" if ok else "Rule Not Met"
                    css = "status-ok" if ok else "status-no"
                    st.markdown(f"<div class='{css}'><b>Anti-{m}:</b> {msg} ({p} Pos/{n} Neg)</div>", unsafe_allow_html=True)
                    if not ok: final_ok = False
                
                if final_ok:
                    st.success("Analysis Complete.")
                    html_rpt = f"""
                    <div class='print-only'>
                    <center><h2>Maternity & Children Hospital - Tabuk</h2><h3>Serology Report</h3></center>
                    <div class='result-paper'>
                    <b>Pt Name:</b> {nm} | <b>MRN:</b> {mr} <br> <b>Date:</b> {dt} | <b>Tech:</b> {tc}
                    <hr>
                    <h4>Antibodies Identified: Anti-{', '.join(match)}</h4>
                    <p><b>Verification:</b> Rule of three met. Probability p<=0.05</p>
                    <p><b>Clinical:</b> Phenotype patient negative. Crossmatch compatible units.</p>
                    <br><br><br>
                    <b>Signature:</b> ___________________
                    </div>
                    <div style='text-align:center;font-size:10px;margin-top:10px'>Dr. Haitham Ismail | Consultant</div>
                    </div>
                    """
                    st.markdown(html_rpt, unsafe_allow_html=True)
                    st.warning("Press Ctrl+P to Print Report")
                else:
                    st.warning("⚠️ Add Extra Cells (Rule Not Met). Use section below.")

    # 4. EXTRA CELLS (OUTSIDE FORM TO PREVENT RESET)
    with st.expander("➕ Add Selected Cell (External)"):
        with st.form("ext_cell"):
            idx = st.text_input("Cell ID")
            rs = st.selectbox("Res", ["Neg", "Pos"])
            st.write("Antigens Present:")
            ag_str = st.text_input("Type Antigens separated by space (e.g. D C K Fya)")
            add_sub = st.form_submit_button("Add Cell")
            if add_sub:
                ph_dic = {a:0 for a in AGS}
                if ag_str:
                    for item in ag_str.split():
                        # fuzzy match
                        cl = item.strip().upper()
                        if cl in AGS: ph_dic[cl]=1
                        # basic map
                        elif cl=="D": ph_dic["D"]=1
                        # and so on..
                        
                st.session_state.extra.append({"s":1 if rs=="Pos" else 0, "ph":ph_dic})
                st.success(f"Added {idx}. Please click 'Run Analysis' again.")
    
    if st.session_state.extra:
        st.write(f"Added {len(st.session_state.extra)} extra cells.")
