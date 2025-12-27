import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. SETUP & BRANDING (The Consultant Look)
# ==========================================
st.set_page_config(page_title="MCH Tabuk Serology", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    /* HIDE STREAMLIT ELEMENTS */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stAppDeployButton {display:none;}
    [data-testid="stToolbar"] {display:none;}
    
    /* PRINTING */
    @media print { 
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 5px double #8B0000; padding: 30px; font-family: 'Times New Roman'; }
    }
    .print-only { display: none; }
    
    /* ALERTS STYLING */
    .hospital-header { text-align: center; border-bottom: 6px solid #8B0000; padding-bottom: 10px; margin-bottom: 20px; font-family: 'Arial'; color: #003366; }
    
    .logic-pass { background-color: #e8f5e9; border-left: 8px solid #2e7d32; padding: 15px; border-radius: 5px; color: #1b5e20; }
    .logic-suspect { background-color: #fff3e0; border-left: 8px solid #ef6c00; padding: 15px; border-radius: 5px; color: #e65100; font-weight: bold;}
    .logic-fail { background-color: #f8d7da; border-left: 8px solid #dc3545; padding: 15px; border-radius: 5px; color: #842029; }
    
    /* DETAILED CLINICAL NOTES STYLES */
    .note-waiha { background:#ffebee; color:#b71c1c; padding:10px; border:1px solid #ffcdd2; margin:5px 0;}
    .note-risk { background:#fff3cd; color:#856404; padding:10px; border-left:5px solid #ffc107; font-weight:bold; }
    
    /* DR SIGNATURE STICKY FOOTER */
    .dr-signature {
        position: fixed; bottom: 0px; width: 100%; right: 0px;
        background: rgba(255,255,255,0.95); 
        text-align: center; padding: 8px; border-top: 3px solid #8B0000;
        z-index: 99999;
    }
    .dr-name { color: #8B0000; font-family: 'Georgia', serif; font-size: 16px; font-weight: bold; text-shadow: 1px 1px 1px #eee; }
    .dr-title { color: #333; font-size: 12px; font-family: sans-serif; font-weight: bold;}
    
    /* Strategy Table */
    .cell-suggest { font-weight: bold; color: #155724; background: #d4edda; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }
    
    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

# FIXED SIGNATURE FOOTER
st.markdown("""
<div class='dr-signature no-print'>
    <span class='dr-name'>Dr. Haitham Ismail</span><br>
    <span class='dr-title'>Clinical Hematology/Oncology & BMT & Transfusion Medicine Consultant</span>
</div>
""", unsafe_allow_html=True)

# 2. DEFINITIONS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
INSIGNIFICANT_AGS = ["Lea", "Leb", "Lua"] 
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# 3. STATE
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID":f"C{i+1}",**{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID":f"S{i}",**{a:0 for a in AGS}} for i in ["I","II","III"]])
# Mandatory Lot Numbers
if 'lot_p' not in st.session_state: st.session_state.lot_p = ""
if 'lot_s' not in st.session_state: st.session_state.lot_s = ""
if 'ext' not in st.session_state: st.session_state.ext = []

# 4. LOGIC ENGINE
def normalize_grade(val):
    return 0 if str(val) in ["0", "Neg"] else 1

def parse_paste(txt, limit=11):
    try:
        rows = txt.strip().split('\n')
        data = []
        c=0
        for line in rows:
            if c >= limit: break
            parts = line.split('\t')
            row_v = []
            for p in parts:
                v_clean = str(p).lower().strip()
                val = 1 if any(x in v_clean for x in ['+', '1', 'pos', 'w']) else 0
                row_v.append(val)
            if len(row_v)>26: row_v=row_v[-26:]
            while len(row_v)<26: row_v.append(0)
            
            d = {"ID": f"C{c+1}" if limit==11 else f"S{c}"}
            for i, ag in enumerate(AGS): d[ag] = row_v[i]
            data.append(d)
            c+=1
        return pd.DataFrame(data), f"Successfully mapped {c} rows."
    except Exception as e: return None, str(e)

# Smart Suggestions
def find_matching_cells_in_inventory(target_ab, conflicts):
    found_list = []
    # P11
    for i in range(11):
        cell = st.session_state.p11.iloc[i]
        if cell.get(target_ab,0)==1:
            clean = True
            for bad in conflicts:
                if cell.get(bad,0)==1: clean=False; break
            if clean: found_list.append(f"Panel-C{i+1}")
    # P3
    scrs = ["I","II","III"]
    for i, s in enumerate(scrs):
        cell = st.session_state.p3.iloc[i]
        if cell.get(target_ab,0)==1:
            clean = True
            for bad in conflicts:
                if cell.get(bad,0)==1: clean=False; break
            if clean: found_list.append(f"Screen-{s}")
    return found_list

# Master Algorithm
def analyze_master_logic(inputs_p, inputs_s, extras):
    ruled_out = set()
    # Exclusion (Cumulative)
    # Panel
    for i in range(1, 12):
        if normalize_grade(inputs_p[i]) == 0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False 
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
    # Extra
    for ex in extras:
        if normalize_grade(ex['res']) == 0:
             for ag in AGS:
                if ex['ph'].get(ag,0)==1: ruled_out.add(ag) # Assume Homozygous check done by tech for extras

    candidates = [x for x in AGS if x not in ruled_out]
    display_cands = [x for x in candidates if x not in IGNORED_AGS]
    
    # Masking Rules
    is_D = "D" in display_cands
    final_list = []
    notes = []
    for c in display_cands:
        if is_D and (c=="C" or c=="E"): continue 
        final_list.append(c)
        
    if is_D: notes.append("anti-D_mask")
    if "c" in final_list: notes.append("anti-c_risk")
    
    return final_list, notes

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

# 5. UI & LOCKING MECHANISM
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Access Level", ["Workstation", "Admin/Supervisor"])
    if st.button("Factory Reset"): st.session_state.ext=[]; st.rerun()

# --- ADMIN VIEW ---
if nav == "Admin/Supervisor":
    st.title("Supervisor Configuration")
    if st.text_input("Enter Admin Password:", type="password")=="admin123":
        st.success("Authorized")
        
        # MANDATORY LOT NUMBERS
        st.subheader("1. Monthly Lot Setup (Mandatory)")
        c1, c2 = st.columns(2)
        l_p = c1.text_input("Identification Panel Lot #", value=st.session_state.lot_p)
        l_s = c2.text_input("Screening Cells Lot #", value=st.session_state.lot_s)
        
        if st.button("Save Lot Numbers"):
            st.session_state.lot_p = l_p
            st.session_state.lot_s = l_s
            st.rerun()
            
        st.subheader("2. Grid Data (Copy-Paste)")
        t1, t2 = st.tabs(["Panel 11", "Screen 3"])
        with t1:
            st.caption("Paste the 11 rows of 1s and 0s from Excel here:")
            txt = st.text_area("P11 Data", height=150)
            if st.button("Update P11"):
                df, m = parse_paste(txt, 11)
                if df is not None: st.session_state.p11 = df; st.success(m)
            st.dataframe(st.session_state.p11.iloc[:,:15])
            
        with t2:
            st.caption("Paste the 3 rows:")
            txts = st.text_area("S3 Data", height=100)
            if st.button("Update S3"):
                df2, m2 = parse_paste(txts, 3)
                if df2 is not None: st.session_state.p3 = df2; st.success(m2)
            st.dataframe(st.session_state.p3.iloc[:,:15])

# --- USER VIEW ---
else:
    st.markdown("""<div class='hospital-header'><center><h1 style='color:#8B0000; font-family:sans-serif'>Maternity & Children Hospital - Tabuk</h1><h3>Blood Bank & Serology Unit</h3></center></div>""", unsafe_allow_html=True)
    
    # 🔴 BLOCKER: Check if Lot is set
    if not st.session_state.lot_p or not st.session_state.lot_s:
        st.error("⛔ SYSTEM LOCKED: Identification Panel or Screening Panel Lot Numbers are missing.")
        st.info("Please contact the Laboratory Supervisor to configure the current Lots.")
        st.stop()
        
    # Valid Interface
    st.info(f"📅 **Active Session:** Panel Lot `{st.session_state.lot_p}` | Screen Lot `{st.session_state.lot_s}`")
    
    c1,c2,c3,c4=st.columns(4)
    nm=c1.text_input("Patient"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()

    with st.form("main"):
        colL, colR = st.columns([1, 2.5])
        with colL:
            st.write("<b>Screening</b>", unsafe_allow_html=True)
            ac_res = st.radio("Auto Control (AC)", ["Negative","Positive"])
            st.write("---")
            s1=st.selectbox("Scn I", GRADES); s2=st.selectbox("Scn II", GRADES); s3=st.selectbox("Scn III", GRADES)
        with colR:
            st.write("<b>Identification Panel</b>", unsafe_allow_html=True)
            g1,g2=st.columns(2)
            with g1:
                c1=st.selectbox("1",GRADES,key="c1"); c2=st.selectbox("2",GRADES,key="c2"); c3=st.selectbox("3",GRADES,key="c3")
                c4=st.selectbox("4",GRADES,key="c4"); c5=st.selectbox("5",GRADES,key="c5"); c6=st.selectbox("6",GRADES,key="c6")
            with g2:
                c7=st.selectbox("7",GRADES,key="c7"); c8=st.selectbox("8",GRADES,key="c8"); c9=st.selectbox("9",GRADES,key="c9")
                c10=st.selectbox("10",GRADES,key="c10"); c11=st.selectbox("11",GRADES,key="c11")
                
        run = st.form_submit_button("🚀 Run Comprehensive Analysis")

    if run:
        st.write("---")
        inp_p = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
        inp_s = {"I":s1,"II":s2,"III":s3}
        
        pos_cnt = sum([normalize_grade(x) for x in inp_p.values()])

        # --- SCENARIO 1: AUTO CONTROL POSITIVE ---
        if ac_res == "Positive":
            st.markdown("""<div class='logic-fail'><h3>🚨 Auto-Control POSITIVE</h3><b>Action Stopped. Allo-antibody Logic suspended.</b></div>""", unsafe_allow_html=True)
            
            # WAIHA/DHTR Warning
            if pos_cnt == 11:
                st.markdown("""
                <div class='note-risk'>
                ⚠️ CRITICAL: Pan-Agglutination + Pos AC + Recent Transfusion? <br>
                High Risk of <b>Delayed Hemolytic Transfusion Reaction (DHTR)</b> mimicking WAIHA. <br>
                Check history! Elution is Mandatory to find hidden Alloantibodies.
                </div>
                """, unsafe_allow_html=True)
            
            # DAT FORM (Inline)
            st.write("#### 🧪 Monospecific DAT Investigation:")
            with st.container(border=True):
                cd1, cd2, cd3 = st.columns(3)
                igg = cd1.selectbox("Anti-IgG", ["Negative","Positive"])
                c3d = cd2.selectbox("Anti-C3d", ["Negative","Positive"])
                ctrl= cd3.selectbox("Control", ["Negative","Positive"])
                
                if ctrl == "Positive": st.error("Invalid Test.")
                elif igg=="Positive": st.warning("Result: **Probable WAIHA**. \nRecommended: Adsorption/Elution studies.")
                elif c3d=="Positive" and igg=="Negative": st.info("Result: **Probable Cold Agglutinin (CAS)**. \nRecommended: Pre-warm Technique.")
        
        # --- SCENARIO 2: PAN-REACTIVITY ---
        elif pos_cnt == 11:
            st.markdown("""
            <div class='logic-suspect'>
            <h3>⚠️ High Frequency Antigen Suspected</h3>
            Auto Control is Negative, but All Cells are Positive.<br>
            <b>Protocol:</b> Phenotype patient. Screen siblings.
            </div>
            """, unsafe_allow_html=True)

        # --- SCENARIO 3: ALLOANTIBODY ---
        else:
            final_cands, notes = analyze_master_logic(inp_p, inp_s, st.session_state.ext)
            
            sigs = [x for x in final_cands if x not in INSIGNIFICANT_AGS]
            colds = [x for x in final_cands if x in INSIGNIFICANT_AGS]

            if not sigs and not colds:
                st.error("No Match Found / All Ruled Out.")
            
            else:
                # SPECIAL ALERTS
                if "anti-D_mask" in notes: st.info("ℹ️ Anti-D Detected: C/E antigens masked.")
                if "anti-c_risk" in notes: 
                    st.markdown("""
                    <div class='note-risk'>
                    🛑 Anti-c IDENTIFIED.<br>
                    Anti-E cannot be excluded easily. Patient needs R1R1 (CDe/CDe) Blood Units.
                    </div>""", unsafe_allow_html=True)
                
                # --- [FIX]: LOGIC FOR MIXTURES VS SINGLE ---
                all_valid = True
                
                # If Multiple significant antibodies -> SHOW WARNING (Orange)
                if len(sigs) > 1:
                    st.markdown(f"""
                    <div class='logic-suspect'>
                    <h3>⚠️ Suspected Complex Mixture: Anti-{', '.join(sigs)}</h3>
                    Multiple candidates remain after exclusion. <b>Differentiation Required.</b><br>
                    Use Selected Cells below to confirm each specificity.
                    </div>
                    """, unsafe_allow_html=True)
                    
                    st.write("**Separation Strategy:**")
                    for t in sigs:
                        conf = [x for x in sigs if x!=t]
                        stock_matches = find_matching_cells_in_inventory(t, conf)
                        
                        stock_txt = f"<span class='cell-suggest'>Available: {', '.join(stock_matches)}</span>" if stock_matches else "<span style='color:red'>Not in current lot.</span>"
                        
                        st.markdown(f"""
                        <div style='border:1px dashed #444; padding:10px; margin:5px 0'>
                        Target: <b>Anti-{t}</b><br>
                        Require Cell: <b>{t} POSITIVE</b> and <b>{' & '.join([c+' Neg' for c in conf])}</b><br>
                        {stock_txt}
                        </div>
                        """, unsafe_allow_html=True)
                
                # Loop for Validation
                valid_list = []
                for ab in (sigs + colds):
                    ok, p, n = check_probability(ab, inp_p, inp_s, st.session_state.ext)
                    if ok:
                        valid_list.append(ab)
                    else:
                        all_valid = False
                        short_p = max(0, 3-p)
                        short_n = max(0, 3-n)
                        st.warning(f"❌ Anti-{ab}: Rule of Three NOT MET. Need {short_p} Pos / {short_n} Neg more.")

                # If ALL VALID -> Show Green Final Result & Print
                if all_valid and len(sigs) >= 1:
                     st.success(f"✅ **FINAL CONFIRMED IDENTIFICATION: Anti-{', '.join(sigs)}**")
                     st.caption("Statistical p-value <= 0.05 achieved.")
                     
                     if st.button("🖨️ Issue Official Report"):
                         r_html = f"""
                         <div class='print-only'>
                            <center><h2 style='color:#8B0000'>Maternity & Children Hospital - Tabuk</h2><h3>Serology Report</h3></center>
                            <div class='result-sheet'>
                                <b>Patient:</b> {nm} ({mr})<br><b>Date:</b> {dt}
                                <hr>
                                <h4>Conclusion: Anti-{', '.join(sigs)} Detected</h4>
                                <p>Validation: Probability confirmed.</p>
                                <p><b>Clinical:</b> Phenotype patient (Negative). Transfuse Compatible.</p>
                                <br><br><b>Consultant Verified:</b> ________________
                            </div>
                            <div style='position:fixed;bottom:0;width:100%;text-align:center'>Dr. Haitham Ismail</div>
                         </div>
                         <script>window.print()</script>
                         """
                         st.markdown(r_html, unsafe_allow_html=True)

    # ADD CELLS
    with st.expander("➕ Add Selected Cell (Input Data)"):
        with st.form("extra"):
            id_x=st.text_input("Cell Lot"); res_x=st.selectbox("Result",GRADES)
            st.write("Phenotype (+):")
            c = st.columns(6)
            ph={}
            for i,a in enumerate(AGS):
                if c[i%6].checkbox(a): ph[a]=1 
                else: ph[a]=0
            if st.form_submit_button("Add Cell"):
                st.session_state.ext.append({"id":id_x, "res":res_x, "res_txt":res_x, "ph":ph})
                st.success("Added! Re-Run.")
