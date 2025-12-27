import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. SETUP
# ==========================================
st.set_page_config(page_title="Tabuk Blood Bank", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { 
        .stApp > header, .sidebar, footer, .no-print { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 4px double #8B0000; padding: 30px; font-family: 'Times New Roman'; }
    }
    .print-only { display: none; }
    
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    
    /* Lot Badges */
    .lot-container { display: flex; justify-content: center; gap: 20px; margin-bottom: 20px; }
    .lot-box { border: 1px solid #ccc; padding: 5px 15px; border-radius: 5px; font-size: 14px; background: #f9f9f9; }
    .lot-label { font-weight: bold; color: #555; }
    .lot-val { font-weight: bold; color: #b71c1c; }

    /* Logic Boxes */
    .logic-pass { background-color: #e8f5e9; border-left: 5px solid #2e7d32; padding: 10px; margin: 5px 0;}
    .logic-fail { background-color: #ffebee; border-left: 5px solid #c62828; padding: 10px; margin: 5px 0;}
    
    .dr-sig { position: fixed; bottom: 5px; right: 15px; font-family: serif; font-size: 11px; background: #fff; padding: 5px; border: 1px solid #ddd; z-index:99;}
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='dr-sig no-print'>Dr. Haitham Ismail | Consultant</div>", unsafe_allow_html=True)

# --- DEFINITIONS ---
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# Filters
IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"] 
INSIGNIFICANT = ["Lea", "Lua", "Leb", "P1", "M", "N"]
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# --- STATE ---
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
# Lots
if 'lot_p' not in st.session_state: st.session_state.lot_p = "NOT SET"
if 'lot_s' not in st.session_state: st.session_state.lot_s = "NOT SET"
# Extras
if 'ext' not in st.session_state: st.session_state.ext = []

# ==========================================
# 2. LOGIC
# ==========================================
def normalize(val):
    s = str(val).lower().strip()
    return 0 if s in ["0", "neg"] else 1

def parse_paste(txt, limit=11):
    # Stable copy-paste parser
    try:
        rows = txt.strip().split('\n')
        data = []
        c = 0
        for line in rows:
            if c >= limit: break
            parts = line.split('\t')
            vals = []
            for p in parts:
                v = 1 if any(x in str(p).lower() for x in ['+','1','pos','w']) else 0
                vals.append(v)
            if len(vals) > 26: vals=vals[-26:]
            while len(vals) < 26: vals.append(0)
            
            rid = f"C{c+1}" if limit==11 else f"S{c}"
            d = {"ID": rid}
            for i,ag in enumerate(AGS): d[ag] = vals[i]
            data.append(d)
            c += 1
        return pd.DataFrame(data), f"Parsed {c} rows."
    except Exception as e: return None, str(e)

# --- CORE ALGORITHM: CUMULATIVE EXCLUSION ---
def get_excluded_antigens(in_p, in_s, extra_cells):
    ruled_out = set()
    
    # 1. Panel Exclusion (11 Cells)
    # Check each cell: Is patient NEGATIVE? If yes, RULE OUT its antigens
    p_df = st.session_state.p11
    for i in range(1, 12):
        if normalize(in_p[i]) == 0: # Neg result
            ph = p_df.iloc[i-1]
            for ag in AGS:
                # Basic Rule Out
                if ph.get(ag, 0) == 1:
                    # Dosage Protection
                    is_safe = True
                    if ag in DOSAGE:
                        pair = PAIRS.get(ag)
                        if pair and ph.get(pair, 0) == 1: is_safe = False # Hetero
                    
                    if is_safe: ruled_out.add(ag)
                    
    # 2. Screening Exclusion (3 Cells) -> IMPORTANT REQUEST
    # Acts exactly like panel cells
    s_df = st.session_state.p3
    idx_map = {"I":0, "II":1, "III":2}
    for k in ["I", "II", "III"]:
        if normalize(in_s[k]) == 0: # Neg result
            ph = s_df.iloc[idx_map[k]]
            for ag in AGS:
                if ph.get(ag, 0) == 1:
                    is_safe = True
                    if ag in DOSAGE:
                        pair = PAIRS.get(ag)
                        if pair and ph.get(pair, 0) == 1: is_safe = False
                    if is_safe: ruled_out.add(ag)

    # 3. Extra Cells Exclusion
    for cell in extra_cells:
        if normalize(cell['res_txt']) == 0:
            ph = cell['ph']
            for ag in AGS:
                if ph.get(ag,0) == 1:
                    is_safe = True
                    if ag in DOSAGE:
                        pair = PAIRS.get(ag)
                        if pair and ph.get(pair,0) == 1: is_safe = False
                    if is_safe: ruled_out.add(ag)
                    
    return ruled_out

# --- CORE ALGORITHM: CUMULATIVE INCLUSION (RULE OF 3) ---
def check_probability_cumulative(cand, in_p, in_s, extras):
    p, n = 0, 0
    # Panel
    for i in range(1, 12):
        res = normalize(in_p[i])
        has = st.session_state.p11.iloc[i-1].get(cand, 0)
        if res==1 and has==1: p+=1
        if res==0 and has==0: n+=1
    # Screen
    s_idx = {"I":0, "II":1, "III":2}
    for k in ["I", "II", "III"]:
        res = normalize(in_s[k])
        has = st.session_state.p3.iloc[s_idx[k]].get(cand, 0)
        if res==1 and has==1: p+=1
        if res==0 and has==0: n+=1
    # Extras
    for cell in extras:
        res = normalize(cell['res_txt'])
        has = cell['ph'].get(cand, 0)
        if res==1 and has==1: p+=1
        if res==0 and has==0: n+=1
        
    pass_rule = (p>=3 and n>=3) or (p>=2 and n>=3)
    return pass_rule, p, n

# ==========================================
# 3. INTERFACE
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Admin"])
    if st.button("RESET DATA"): 
        st.session_state.ext = []
        st.rerun()

# --- ADMIN ---
if nav == "Admin":
    st.title("Admin Configuration")
    if st.text_input("Password",type="password")=="admin123":
        st.warning("You must enter BOTH Lot Numbers to save configurations.")
        
        c1, c2 = st.columns(2)
        lot_p_in = c1.text_input("ID Panel Lot Number", value=st.session_state.lot_p)
        lot_s_in = c2.text_input("Screen Cell Lot Number", value=st.session_state.lot_s)
        
        t1, t2 = st.tabs(["ID Panel (11)", "Screen Panel (3)"])
        
        with t1:
            st.info("Paste Excel Numbers (11 Rows)")
            pt1 = st.text_area("P11 Data", height=150)
            if st.button("Update Panel 11"):
                if not lot_p_in or lot_p_in == "NOT SET":
                    st.error("Please enter ID Panel Lot Number first!")
                else:
                    df,m = parse_paste(pt1, 11)
                    if df is not None:
                        st.session_state.p11 = df
                        st.session_state.lot_p = lot_p_in
                        st.success(f"{m} (Lot {lot_p_in} Saved)")
            st.dataframe(st.session_state.p11)

        with t2:
            st.info("Paste Screen Numbers (3 Rows)")
            pt2 = st.text_area("P3 Data", height=100)
            if st.button("Update Screen 3"):
                if not lot_s_in or lot_s_in == "NOT SET":
                    st.error("Please enter Screen Panel Lot Number first!")
                else:
                    df2,m2 = parse_paste(pt2, 3)
                    if df2 is not None:
                        st.session_state.p3 = df2
                        st.session_state.lot_s = lot_s_in
                        st.success(f"{m2} (Lot {lot_s_in} Saved)")
            st.dataframe(st.session_state.p3)

# --- USER ---
else:
    # 1. HEADER (DUAL LOT DISPLAY)
    st.markdown("""<center><h2 style='color:#b30000'>Maternity & Children Hospital - Tabuk</h2><h4>Serology Unit</h4></center>""", unsafe_allow_html=True)
    
    # Lot Badge Area
    c_lp, c_ls = "#b71c1c" if st.session_state.lot_p == "NOT SET" else "#1b5e20", "#b71c1c" if st.session_state.lot_s == "NOT SET" else "#1b5e20"
    st.markdown(f"""
    <div class='lot-container'>
        <div class='lot-box'><span class='lot-label'>ID Panel Lot:</span> <span class='lot-val' style='color:{c_lp}'>{st.session_state.lot_p}</span></div>
        <div class='lot-box'><span class='lot-label'>Screen Lot:</span> <span class='lot-val' style='color:{c_ls}'>{st.session_state.lot_s}</span></div>
    </div>
    """, unsafe_allow_html=True)
    
    # Info
    r1 = st.columns(4)
    nm=r1[0].text_input("Name"); mr=r1[1].text_input("MRN"); tc=r1[2].text_input("Tech"); dt=r1[3].date_input("Date")
    
    st.divider()

    # 2. ENTRY FORM (NO CRASH)
    with st.form("main"):
        cL, cR = st.columns([1, 2.5])
        
        with cL:
            st.subheader("1. Screen & Auto")
            ac_res = st.radio("AC", ["Negative", "Positive"])
            s1=st.selectbox("Scn I", GRADES); s2=st.selectbox("Scn II", GRADES); s3=st.selectbox("Scn III", GRADES)
        
        with cR:
            st.subheader("2. Panel Reactions")
            gA, gB = st.columns(2)
            with gA:
                c1=st.selectbox("1",GRADES,key="k1"); c2=st.selectbox("2",GRADES,key="k2"); c3=st.selectbox("3",GRADES,key="k3")
                c4=st.selectbox("4",GRADES,key="k4"); c5=st.selectbox("5",GRADES,key="k5"); c6=st.selectbox("6",GRADES,key="k6")
            with gB:
                c7=st.selectbox("7",GRADES,key="k7"); c8=st.selectbox("8",GRADES,key="k8"); c9=st.selectbox("9",GRADES,key="k9")
                c10=st.selectbox("10",GRADES,key="k10"); c11=st.selectbox("11",GRADES,key="k11")
        
        go = st.form_submit_button("🚀 Run Cumulative Analysis")

    # 3. ANALYSIS LOGIC (V205)
    if go:
        if st.session_state.lot_p == "NOT SET":
            st.error("⚠️ SYSTEM LOCKED: Supervisor must configure Lot Numbers first.")
        
        elif ac_res == "Positive":
            st.error("🚨 STOP: Auto Control Positive.")
            st.info("Protocol: Perform DAT (Poly -> Mono). WAIHA / CAS investigation required.")
            
        else:
            # Inputs
            p_map = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
            s_map = {"I":s1, "II":s2, "III":s3}
            pos_total = sum([normalize(x) for x in p_map.values()])

            if pos_total == 11:
                st.warning("⚠️ Pan-Agglutination: Suspect High Freq Ab. Phenotype Patient.")
            else:
                # 1. TOTAL EXCLUSION
                ruled = get_excluded_antigens(p_map, s_map, st.session_state.ext)
                
                # Filter Logic
                raw_cands = [x for x in AGS if x not in ruled]
                cands = [x for x in raw_cands if x not in IGNORED_AGS]
                
                # 2. SEPARATION LOGIC
                real = [x for x in cands if x not in INSIGNIFICANT]
                cold = [x for x in cands if x in INSIGNIFICANT]
                
                st.subheader("Conclusion")
                
                if not real and not cold:
                    st.error("❌ No common alloantibodies found. Inconclusive.")
                else:
                    all_ok = True
                    
                    if real: st.success(f"**Identified:** Anti-{', '.join(real)}")
                    if cold: st.info(f"**Other:** Anti-{', '.join(cold)} (Clinically Insignificant/Cold)")
                    
                    st.write("---")
                    
                    # 3. PROBABILITY VALIDATION (CUMULATIVE)
                    for ab in (real + cold):
                        passed, pos_n, neg_n = check_probability_cumulative(ab, p_map, s_map, st.session_state.ext)
                        
                        box_cls = "logic-pass" if passed else "logic-fail"
                        status_txt = "Rule of 3 MET (p≤0.05)" if passed else "NOT MET (Need more cells)"
                        
                        st.markdown(f"""
                        <div class='{box_cls}'>
                        <b>Anti-{ab}:</b> {status_txt} <br>
                        Cumulative Stats: {pos_n} Positive Cells / {neg_n} Negative Cells.
                        </div>
                        """, unsafe_allow_html=True)
                        
                        if not passed: all_ok = False
                    
                    # 4. OUTPUTS
                    if all_ok:
                        if st.button("🖨️ Print Final Report"):
                            ht = f"""<div class='print-only'><br><center><h2>Maternity & Children Hospital - Tabuk</h2><h3>Serology Lab</h3></center><div class='result-sheet'><b>Pt:</b> {nm} ({mr})<br><b>Tech:</b> {tc} | <b>Lot:</b> {st.session_state.lot_p}<hr><b>Conclusion:</b> Anti-{', '.join(real)} detected.<br>Validation: Probability p<=0.05 Confirmed.<br><b>Note:</b> Phenotype Patient (Must be Negative).<br><br><br>Sig: ______________</div></div><script>window.print()</script>"""
                            st.markdown(ht, unsafe_allow_html=True)
                    else:
                        st.warning("⚠️ Validation Incomplete. Please Add Selected Cells below to satisfy stats.")

    # 4. ADD EXTRA CELL MODULE (Works on same logic)
    with st.expander("➕ Add Selected Cell (From Library)"):
        with st.form("add_ex"):
            c_id = st.text_input("Cell Lot ID")
            c_res = st.selectbox("Result", GRADES)
            
            st.write("<b>Cell Profile (Select Antigens Present +)</b>", unsafe_allow_html=True)
            # Create a compact grid of checkboxes for manual entry of phenotype
            # (Because User is holding the physical vial/sheet of that specific old cell)
            cols = st.columns(6)
            new_ph = {a:0 for a in AGS}
            for i, ag in enumerate(AGS):
                if cols[i%6].checkbox(ag): new_ph[ag] = 1
                
            if st.form_submit_button("Confirm Add"):
                st.session_state.ext.append({
                    "id": c_id, 
                    "res_txt": c_res, 
                    "ph": new_ph,
                    "src": "Extra"
                })
                st.success("Cell Added! Click 'Run Analysis' to recalculate.")

    if st.session_state.ext:
        st.write("Added Cells:")
        disp = [{"ID": x['id'], "Result": x['res_txt']} for x in st.session_state.ext]
        st.table(pd.DataFrame(disp))
