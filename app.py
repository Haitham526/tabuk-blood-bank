import streamlit as st
import pandas as pd
from datetime import date

# --------------------------------------------------------------------------
# 1. BASE CONFIGURATION & MEDICAL STYLING
# --------------------------------------------------------------------------
st.set_page_config(page_title="Tabuk Blood Bank Expert", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { 
        .stApp > header, .sidebar, footer, .no-print { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 4px double #8B0000; padding: 20px; font-family: 'Times New Roman'; }
    }
    .print-only { display: none; }
    
    .hospital-logo { color: #8B0000; text-align: center; border-bottom: 5px solid #8B0000; padding-bottom: 5px; font-family: sans-serif; font-weight: bold;}
    .lot-badge { background-color: #ffebee; color: #b71c1c; padding: 5px; border-radius: 4px; font-size: 14px; text-align:center; margin-bottom:10px; border:1px solid #ffcdd2;}

    /* CLINICAL BOXES */
    .clinical-high-freq { background-color: #fff3cd; border-left: 5px solid #ffc107; padding: 15px; margin: 10px 0; color: #856404; }
    .clinical-waiha { background-color: #f8d7da; border-left: 5px solid #dc3545; padding: 15px; margin: 10px 0; color: #721c24; }
    .clinical-cold { background-color: #cff4fc; border-left: 5px solid #0dcaf0; padding: 15px; margin: 10px 0; color: #055160; }
    .clinical-d-mask { background-color: #e2e3e5; border-left: 5px solid #383d41; padding: 10px; margin: 5px 0; color: #383d41; font-style: italic; }
    .clinical-c-risk { background-color: #fff3cd; border: 2px solid #ffca2c; padding: 10px; color: #000; font-weight: bold; margin: 5px 0;}
    
    .strategy-box { border: 1px dashed #004085; background: #cce5ff; padding: 10px; margin: 5px 0; border-radius: 5px; color: #004085; }

    .dr-sig { position: fixed; bottom: 5px; right: 10px; font-family: serif; font-size: 11px; background: rgba(255,255,255,0.9); padding: 5px; border: 1px solid #ccc; z-index:99; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class='dr-sig no-print'>
    <b>Dr. Haitham Ismail</b><br>
    Clinical Hematology/Oncology &<br>BM Transplantation & Transfusion Medicine Consultant
</div>
""", unsafe_allow_html=True)

# 2. DEFINITIONS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# ** MEDICAL FILTERS (The lists you asked for) **
IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"] # Totally silent
INSIGNIFICANT_AGS = ["Lea", "Leb", "Lua"] # Cold / Insignificant (Anti-M REMOVED from here)
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# 3. STATE
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'lot' not in st.session_state: st.session_state.lot = "NOT SET"
if 'ext' not in st.session_state: st.session_state.ext = [] # Extra/Selected Cells

# 4. PARSER (PASTE LOGIC - STABLE)
def normalize_grade(val):
    s = str(val).lower().strip()
    return 0 if s in ["0", "neg"] else 1

def parse_paste(txt, limit):
    try:
        rows = txt.strip().split('\n')
        data = []
        c = 0
        for line in rows:
            if c >= limit: break
            parts = line.split('\t')
            row_v = []
            for p in parts:
                v = 1 if any(x in str(p).lower() for x in ['+','1','pos','w']) else 0
                row_v.append(v)
            if len(row_v)>26: row_v=row_v[-26:]
            while len(row_v)<26: row_v.append(0)
            d = {"ID": f"C{c+1}" if limit==11 else f"S{c}"}
            for i, ag in enumerate(AGS): d[ag] = row_v[i]
            data.append(d)
            c+=1
        return pd.DataFrame(data), f"Parsed {c} rows."
    except: return None, "Parse Error"

# --- MAIN ALGORITHM (V206 LOGIC) ---
def analyze_master_logic(inputs_p, inputs_s, extras):
    ruled_out = set()
    # 1. EXCLUSION PHASE (ALL SOURCES)
    # Panel
    for i in range(1, 12):
        if normalize_grade(inputs_p[i]) == 0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False # Hetero
                if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
    # Screen
    s_idx={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize_grade(inputs_s[k]) == 0:
            ph = st.session_state.p3.iloc[s_idx[k]]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
    # Extras
    for cell in extras:
        if normalize_grade(cell['res']) == 0:
            for ag in AGS:
                # We assume extras are selected well. But applying rules logic:
                if cell['ph'].get(ag,0)==1: ruled_out.add(ag)

    # 2. FILTER & SPECIAL RULES
    candidates = [x for x in AGS if x not in ruled_out]
    
    # Hide Ignored
    display_cands = [x for x in candidates if x not in IGNORED_AGS]
    
    # RULE: Anti-D Masking
    is_D = "D" in display_cands
    final_list = []
    notes = []
    
    for c in display_cands:
        if is_D and (c=="C" or c=="E"):
            continue # Skip C/E if D exists
        final_list.append(c)
        
    if is_D: notes.append("anti-D_mask")
    if "c" in final_list: notes.append("anti-c_risk")
    
    return final_list, notes

# Rule of 3 (Cumulative)
def check_p_val(cand, inputs_p, inputs_s, extras):
    p, n = 0, 0
    # Panel
    for i in range(1, 12):
        s = normalize_grade(inputs_p[i])
        h = st.session_state.p11.iloc[i-1].get(cand, 0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    s_idx = {"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s = normalize_grade(inputs_s[k])
        h = st.session_state.p3.iloc[s_idx[k]].get(cand, 0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extras
    for c in extras:
        s = normalize_grade(c['res'])
        h = c['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    
    return (p>=3 and n>=3) or (p>=2 and n>=3), p, n

# 5. UI
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png",width=60)
    nav=st.radio("Mode",["Workstation","Supervisor"])
    if st.button("RESET DATA"): 
        st.session_state.ext=[]
        st.rerun()

# ADMIN
if nav == "Supervisor":
    st.title("Admin Panel")
    if st.text_input("Pwd",type="password")=="admin123":
        st.session_state.lot = st.text_input("Panel/Screen Lot:", value=st.session_state.lot)
        t1,t2=st.tabs(["Panel","Screen"])
        with t1:
            if st.button("Save P11 from Paste Area below"): pass 
            txt1=st.text_area("Paste P11", height=150)
            if txt1: 
                df,m = parse_paste(txt1,11)
                st.session_state.p11=df; st.success(m)
            st.dataframe(st.session_state.p11)
        with t2:
            txt2=st.text_area("Paste S3")
            if txt2:
                df2,m2=parse_paste(txt2,3)
                st.session_state.p3=df2
            st.dataframe(st.session_state.p3)

# USER
else:
    st.markdown(f"""
    <div class='hospital-logo'>
        <h2>Maternity & Children Hospital - Tabuk</h2>
        <h4>Immunohematology Workstation</h4>
        <div class='lot-badge'>Active Lot: {st.session_state.lot}</div>
    </div>
    """, unsafe_allow_html=True)
    
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Pt Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()

    with st.form("main_logic"):
        st.subheader("1. Reactions Input")
        L, R = st.columns([1, 2])
        with L:
            ac_res = st.radio("Auto Control (AC)", ["Negative", "Positive"])
            st.write("---")
            s1=st.selectbox("Scn I",GRADES)
            s2=st.selectbox("Scn II",GRADES)
            s3=st.selectbox("Scn III",GRADES)
        with R:
            g1, g2 = st.columns(2)
            with g1:
                c1=st.selectbox("1",GRADES); c2=st.selectbox("2",GRADES); c3=st.selectbox("3",GRADES); c4=st.selectbox("4",GRADES); c5=st.selectbox("5",GRADES); c6=st.selectbox("6",GRADES)
            with g2:
                c7=st.selectbox("7",GRADES); c8=st.selectbox("8",GRADES); c9=st.selectbox("9",GRADES); c10=st.selectbox("10",GRADES); c11=st.selectbox("11",GRADES)
        
        # DAT WORKUP (IF NEEDED)
        st.write("---")
        st.caption("Only if AC is Positive (Select results here for guidance):")
        d_cols = st.columns(3)
        dat_igg = d_cols[0].selectbox("Mono-IgG", ["Negative","Positive","Weak"], index=0)
        dat_c3d = d_cols[1].selectbox("Mono-C3d", ["Negative","Positive"], index=0)
        dat_ctrl= d_cols[2].selectbox("DAT-Ctrl", ["Negative","Positive"], index=0)
        
        run = st.form_submit_button("🚀 Run Expert Interpretation")
    
    if run:
        inp_p = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
        inp_s = {"I":s1, "II":s2, "III":s3}
        pos_cnt = sum([normalize_grade(x) for x in inp_p.values()])
        
        st.subheader("2. Interpretation")

        # SCENARIO A: AC POSITIVE (DAT GUIDE)
        if ac_res == "Positive":
            st.markdown(f"<div class='logic-critical'>🚨 <b>Auto Control Positive.</b><br>Allo-antibody rules suspended. Proceed with DAT Interpretation below.</div>", unsafe_allow_html=True)
            
            # Critical Alert for High Frequency Masking
            if pos_cnt == 11:
                st.markdown("<div class='clinical-waiha'><b>⚠️ Critical:</b> Pan-agglutination + Pos AC + Recent Transfusion? -> Suspect <b>Delayed Hemolytic Transfusion Reaction (DHTR)</b> mimicking WAIHA. Elution is MANDATORY.</div>", unsafe_allow_html=True)

            # DAT Logic Tree
            if dat_ctrl == "Positive": st.error("Invalid DAT. Control Positive.")
            elif normalize_grade(dat_igg)==1 and normalize_grade(dat_c3d)==0:
                st.markdown("<div class='clinical-waiha'><b>Diagnostic: WAIHA (Warm Auto)</b><br>• IgG only detected.<br>• Perform Adsorption/Elution to rule out masked Alloantibodies.<br>👉 <b>Refer to Physician.</b></div>", unsafe_allow_html=True)
            elif normalize_grade(dat_igg)==0 and normalize_grade(dat_c3d)==1:
                st.markdown("<div class='clinical-cold'><b>Diagnostic: CAS (Cold Agglutinin)</b><br>• C3d only detected.<br>• Perform ID using Pre-warm Technique.<br>👉 <b>Refer to Physician.</b></div>", unsafe_allow_html=True)
            elif normalize_grade(dat_igg)==1 and normalize_grade(dat_c3d)==1:
                st.info("**Mixed Type AIHA suspected.** Check history.")

        # SCENARIO B: ALLOANTIBODY
        else:
            # 1. High Freq?
            if pos_cnt == 11:
                 st.markdown("""<div class='clinical-high-freq'><b>⚠️ High Incidence Antibody</b><br>Pan-reactivity with Negative Auto-Control.<br>Action: Phenotype patient (must be Neg), Screen Siblings.</div>""", unsafe_allow_html=True)
            
            else:
                cands, notes = analyze_master_logic(inp_p, inp_s, st.session_state.ext)
                
                # SEPARATE SIGNIFICANT vs COLD
                sigs = [x for x in cands if x not in INSIGNIFICANT_AGS]
                colds = [x for x in cands if x in INSIGNIFICANT_AGS]

                if not sigs and not colds:
                    st.error("❌ No Match. Inconclusive or Low Frequency.")
                
                else:
                    # STRATEGY & CONFIRMATION
                    st.markdown("### 🧬 Identification Analysis")
                    
                    # 1. Special Rules Output
                    if "anti-D_mask" in notes: st.info("ℹ️ Anti-D Masking Active: Anti-C & Anti-E hidden from list.")
                    if "anti-c_risk" in notes: st.markdown("<div class='clinical-c-risk'>⚠️ CRITICAL: Anti-c Detected.<br>Anti-E is hard to exclude. TRANSFUSE R1R1 (E- c-) UNITS.</div>", unsafe_allow_html=True)
                    
                    all_validated = True
                    
                    # 2. Main Antibodies Display
                    if sigs:
                        st.write("#### Significant Antibodies:")
                        for ab in sigs:
                            valid, p, n = check_p_val(ab, inp_p, inp_s, st.session_state.ext)
                            css = "logic-pass" if valid else "logic-fail"
                            msg = "Confirmed (Rule of 3 Met)" if valid else "Unconfirmed (Add Selected Cells)"
                            
                            st.markdown(f"<div class='{css}'><b>Anti-{ab}:</b> {msg} <br><small>Stats: {p} Pos / {n} Neg cells</small></div>", unsafe_allow_html=True)
                            
                            if not valid: all_validated = False
                            
                            # Phenotype Reminder
                            st.caption(f"👉 MUST Phenotype Patient for {ab} -> Expect NEGATIVE.")

                    # 3. Separation Strategy (If Multiple Significant)
                    if len(sigs) > 1:
                        st.markdown("#### 🔬 Smart Separation Strategy")
                        st.caption("To separate mixtures, test Selected Cells with:")
                        for target in sigs:
                             others = [o for o in sigs if o != target]
                             st.markdown(f"<div class='strategy-box'>To Confirm <b>Anti-{target}</b>: Select Cell <b>{target} Positive</b> / <b>{' & '.join(others)} Negative</b>.</div>", unsafe_allow_html=True)

                    # 4. Cold Antibodies
                    if colds:
                        st.write("#### Cold / Insignificant:")
                        st.markdown(f"<div class='clinical-cold'><b>{', '.join(['Anti-'+x for x in colds])}</b>: Likely not clinically significant unless reactive at 37/AHG.</div>", unsafe_allow_html=True)

                    # 5. FINAL REPORT ACTION
                    if all_validated and sigs:
                        if st.button("🖨️ Generate Official Report"):
                            h=f"""<div class='print-only'><center><h2>MCH Tabuk - Blood Bank</h2></center><div class='result-sheet'><b>Pt:</b> {nm} ({mr})<br><b>Tech:</b> {tc} | <b>Date:</b> {dt}<hr><h3>Conclusion</h3><b>Identified:</b> Anti-{', '.join(sigs)}<br>{' + '.join(colds) + ' (Cold)' if colds else ''}<br><br><b>Verification:</b> Probability p<=0.05 Met.<br><b>Clinical Action:</b> Phenotype patient (Negative). Transfuse compatible units.<br><br><br>Sig: ______________</div><div style='position:fixed;bottom:0;width:100%;text-align:center'>Dr. Haitham Ismail</div></div><script>window.print()</script>"""
                            st.markdown(h, unsafe_allow_html=True)
                    elif sigs:
                        st.warning("⚠️ Cannot print report until antibodies are confirmed by Rule of 3. Use 'Add Extra Cells' below.")

    # EXTRA CELLS MODULE
    with st.expander("➕ Add Selected Cells (To Resolve Mixtures / Confirm Rules)"):
        c1, c2 = st.columns(2)
        eid = c1.text_input("Cell Lot#")
        eres = c2.selectbox("Result", GRADES)
        
        st.write("Phenotype (Select Present):")
        # Multiselect is cleaner inside expander
        pres = st.multiselect("Antigens on this cell", AGS)
        
        if st.button("Add Cell to Analysis"):
            ph = {a:0 for a in AGS}
            for p in pres: ph[p]=1
            st.session_state.ext.append({"res": eres, "res_txt":eres, "ph":ph})
            st.success("Added! Please click 'Run Analysis' again to update stats.")

    if st.session_state.ext:
        st.write(f"Loaded {len(st.session_state.ext)} Extra Cells.")
