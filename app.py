import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. SETUP (Medical Standard Styling)
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology Expert", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { 
        .stApp > header, .sidebar, footer, .no-print { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 3px solid #b30000; padding: 25px; font-family: 'Times New Roman'; }
        .footer-sig { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 2px solid #ccc; padding: 10px; font-weight:bold;}
    }
    .print-only { display: none; }
    
    .hospital-logo { color: #b30000; text-align: center; border-bottom: 5px solid #b30000; padding-bottom: 5px; font-family: sans-serif; }
    
    .alert-high-freq { background-color: #fff3cd; color: #856404; padding: 15px; border-radius: 5px; border-left: 10px solid #ffeeba; font-weight: bold;}
    .alert-auto { background-color: #f8d7da; color: #721c24; padding: 15px; border-radius: 5px; border-left: 10px solid #f5c6cb; }
    
    /* Input Styling */
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    .result-badge { background: #e3f2fd; color: #0d47a1; padding: 10px; border-radius: 5px; border-left: 5px solid #1976d2; margin-top: 10px; }
    .strategy-box { background: #fbe9e7; color: #d84315; padding: 10px; border-radius: 5px; border: 1px dashed #ffab91; margin-top: 5px;}
    
    .signature-badge { 
        position: fixed; bottom: 10px; right: 15px; background: rgba(255,255,255,0.95); 
        padding: 8px 15px; border: 2px solid #e0e0e0; border-radius: 10px; z-index:99; 
        font-family: serif; color: #8B0000; box-shadow: 2px 2px 10px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# THE CONSULTANT SIGNATURE
st.markdown("""
<div class='signature-badge no-print'>
    <b>Dr. Haitham Ismail</b><br>
    Clinical Hematology/Oncology &<br>BM Transplantation & Transfusion Consultant
</div>
""", unsafe_allow_html=True)

# 2. CONSTANTS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
# Antibodies showing dosage (Homozygous Rule applied)
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}
# Correct Grades
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# 3. STATE
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'lot' not in st.session_state: st.session_state.lot = "Not Defined"

# 4. LOGIC
def normalize_grade(val):
    s = str(val).lower().strip()
    # Any reaction (>0) is Positive for Exclusion logic
    if s == "0" or s == "neg": return 0
    return 1 # Positive (+1 to +4 or Hemolysis)

def parse_paste(txt, limit=11):
    # Reliable Paste Logic
    try:
        rows = txt.strip().split('\n')
        data = []
        c = 0
        for row in rows:
            if c >= limit: break
            parts = row.split('\t')
            row_dict = {}
            vals = []
            for p in parts:
                v_clean = str(p).lower().strip()
                v = 1 if any(x in v_clean for x in ['+', '1', 'pos', 'w']) else 0
                vals.append(v)
            # Ensure 26 cols
            if len(vals)>26: vals=vals[-26:]
            while len(vals)<26: vals.append(0)
            
            rid = f"C{c+1}" if limit==11 else f"S{c}"
            row_dict = {"ID":rid}
            for i, ag in enumerate(AGS): row_dict[ag] = vals[i]
            data.append(row_dict)
            c+=1
        return pd.DataFrame(data), f"Updated {c} rows successfully."
    except Exception as e: return None, str(e)

def get_ruled_out(panel, inputs, screen, inputs_screen):
    out = set()
    # Panel Check
    for i in range(1, 12):
        score = normalize_grade(inputs[i])
        if score == 0: # Negative reaction
            ph = panel.iloc[i-1]
            for ag in AGS:
                # Rule: Exclude if Ag Present
                if ph.get(ag, 0) == 1:
                    # Dosage Protection
                    is_safe = True
                    if ag in DOSAGE:
                        partner = PAIRS.get(ag)
                        if partner and ph.get(partner, 0) == 1: 
                            is_safe = False # Heterozygous -> Do Not Exclude
                    
                    if is_safe: out.add(ag)
    
    # Screen Check
    idx_map = {"I":0, "II":1, "III":2}
    for k in ["I", "II", "III"]:
        score = normalize_grade(inputs_screen[k])
        if score == 0:
            ph = screen.iloc[idx_map[k]]
            for ag in AGS:
                if ag not in out:
                    if ph.get(ag, 0) == 1:
                        # Dosage Protection
                        is_safe = True
                        if ag in DOSAGE:
                            partner = PAIRS.get(ag)
                            if partner and ph.get(partner, 0) == 1: is_safe=False
                        if is_safe: out.add(ag)
    return out

# 5. UI
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Supervisor"])
    if st.button("RESET All"): st.rerun()

# --- ADMIN ---
if nav == "Supervisor":
    st.title("System Configuration")
    if st.text_input("Supervisor Password", type="password") == "admin123":
        st.info(f"Current Lot: {st.session_state.lot}")
        new_l = st.text_input("Update Lot Number:")
        if st.button("Save Lot"): st.session_state.lot = new_l; st.success("Saved")
        
        st.write("---")
        t1, t2 = st.tabs(["Panel Data", "Screen Data"])
        with t1:
            st.warning("Paste ONLY the number grid from Excel (No Headers).")
            p_txt = st.text_area("Paste Panel 11", height=150)
            if st.button("Update Panel"):
                df, m = parse_paste(p_txt, 11)
                if df is not None: st.session_state.p11=df; st.success(m)
            st.dataframe(st.session_state.p11)
        with t2:
            s_txt = st.text_area("Paste Screen 3", height=100)
            if st.button("Update Screen"):
                df, m = parse_paste(s_txt, 3)
                if df is not None: st.session_state.p3=df; st.success(m)
            st.dataframe(st.session_state.p3)

# --- USER ---
else:
    # HOSPITAL HEADER
    st.markdown(f"""
    <div class='hospital-logo'>
        <h2>Maternity & Children Hospital - Tabuk</h2>
        <h4 style='color:grey'>Serology Unit | Workstation</h4>
        <small style='color:red'>Active Panel Lot: {st.session_state.lot}</small>
    </div>
    """, unsafe_allow_html=True)
    
    # INFO
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Patient Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    # SAFE INPUT FORM
    with st.form("main_input"):
        colA, colB = st.columns([1, 2.5])
        with colA:
            st.write("<b>Screening & Auto Control</b>", unsafe_allow_html=True)
            ac_res = st.radio("Auto Control (AC)", ["Negative", "Positive"])
            st.write("---")
            si = st.selectbox("Scn Cell I", GRADES)
            sii = st.selectbox("Scn Cell II", GRADES)
            siii = st.selectbox("Scn Cell III", GRADES)
            
        with colB:
            st.write("<b>Identification Panel (11 Cells)</b>", unsafe_allow_html=True)
            g1, g2 = st.columns(2)
            with g1:
                c1=st.selectbox("1", GRADES, key="c1")
                c2=st.selectbox("2", GRADES, key="c2")
                c3=st.selectbox("3", GRADES, key="c3")
                c4=st.selectbox("4", GRADES, key="c4")
                c5=st.selectbox("5", GRADES, key="c5")
                c6=st.selectbox("6", GRADES, key="c6")
            with g2:
                c7=st.selectbox("7", GRADES, key="c7")
                c8=st.selectbox("8", GRADES, key="c8")
                c9=st.selectbox("9", GRADES, key="c9")
                c10=st.selectbox("10", GRADES, key="c10")
                c11=st.selectbox("11", GRADES, key="c11")
        
        calc = st.form_submit_button("🔎 Analyze & Interpret")

    # LOGIC PROCESSING
    if calc:
        inputs_p = {1:c1, 2:c2, 3:c3, 4:c4, 5:c5, 6:c6, 7:c7, 8:c8, 9:c9, 10:c10, 11:c11}
        inputs_s = {"I":si, "II":sii, "III":siii}
        
        # 1. CHECK POSITIVITY COUNT
        # Convert all panel inputs to 0/1 for counting
        count_pos = sum([normalize_grade(x) for x in inputs_p.values()])
        
        # --- SCENARIO 1: High Frequency Antigen (11 Pos + AC Neg) ---
        if count_pos == 11 and ac_res == "Negative":
            st.markdown("""
            <div class='alert-high-freq'>
                <h3>⚠️ CRITICAL: Pan-Agglutination with Negative Auto-Control</h3>
                <b>Interpretation:</b> Highly suggestive of Antibody to High-Frequency Antigen.<br>
                <hr>
                <b>Protocol & Guidance:</b><br>
                1. <b>Phenotype the Patient:</b> Patient must be negative for the suspected high-frequency antigen.<br>
                2. <b>Select Cells:</b> You need rare negative cells to confirm.<br>
                3. <b>Family Study:</b> Screen first-degree relatives (Siblings) for compatible blood.<br>
                4. <i>Refer sample to Reference Laboratory for further identification.</i>
            </div>
            """, unsafe_allow_html=True)
            
        # --- SCENARIO 2: Auto Antibody (AC Pos) ---
        elif ac_res == "Positive":
            st.markdown("""
            <div class='alert-auto'>
                <h3>🚨 ALERT: Auto-Control is POSITIVE</h3>
                Allo-antibody identification is halted.<br>
                <hr>
                <b>Workup Required:</b><br>
                1. <b>Perform Monospecific DAT</b> (Anti-IgG vs Anti-C3d).<br>
                2. <b>If IgG+:</b> Suspect WAIHA. Perform Adsorption (Auto/Allo).<br>
                3. <b>If C3d+:</b> Suspect Cold Agglutinin. Use Pre-warm technique.<br>
                4. Check history for <b>Delayed Hemolytic Transfusion Reaction (DHTR)</b>.
            </div>
            """, unsafe_allow_html=True)
        
        # --- SCENARIO 3: Allo-Antibody (Normal Case) ---
        else:
            ruled_out = get_ruled_out(st.session_state.p11, inputs_p, st.session_state.p3, inputs_s)
            
            # THE CORRECT LOGIC: LIST ALL THAT ARE NOT RULED OUT
            # (Don't try to find a perfect pattern match, just list candidates)
            candidates = [ag for ag in AGS if ag not in ruled_out]
            
            if not candidates:
                st.error("❌ No common alloantibodies match (Inconclusive). Possible low-frequency antibody or technical issue.")
            
            else:
                # SUCCESS
                st.subheader("📝 Investigation Result")
                
                # Single Ab
                if len(candidates) == 1:
                    res_txt = f"Anti-{candidates[0]}"
                    st.success(f"✅ Identity: {res_txt}")
                
                # Multiple Abs
                else:
                    res_txt = f"Multiple: {', '.join(['Anti-'+x for x in candidates])}"
                    st.warning(f"⚠️ {res_txt}")
                    st.markdown("**Mixture Suspected:** The reaction pattern corresponds to a combination of these antibodies (or one is present and others could not be excluded).")

                # Strategy for Separation (Selected Cells Advice)
                if len(candidates) > 1:
                    st.markdown("#### 🧪 Separation Strategy (Selected Cells)")
                    advice = analyze_strategy(candidates)
                    for a in advice: st.markdown(f"<div class='strategy-box'>{a}</div>", unsafe_allow_html=True)

                # PHENOTYPE REMINDER FOR ALL
                st.info("🧬 **Next Step:** Patient must be phenotyped for these antigens (Expected Result: Negative).")
                
                # PRINT BUTTON
                if st.button("Generate Official Report"):
                    rpt = f"""
                    <div class='print-only'>
                        <center><h2 style='color:#b30000'>Maternity & Children Hospital - Tabuk</h2><h3>Serology Lab</h3></center>
                        <div class='result-sheet'>
                            <table width='100%'>
                                <tr><td><b>Pt:</b> {nm}</td><td><b>MRN:</b> {mr}</td></tr>
                                <tr><td><b>Date:</b> {dt}</td><td><b>Tech:</b> {tc}</td></tr>
                                <tr><td><b>Lot No:</b> {st.session_state.lot}</td></tr>
                            </table>
                            <hr>
                            <h4>Conclusion: {res_txt}</h4>
                            <p><b>Clinical Note:</b> Patient phenotype required (Negative).</p>
                            <ul>
                                {''.join([f'<li>Rule out Anti-{x} by Selected Cells' for x in candidates]) if len(candidates)>1 else '<li>Rule of Three Met.'}
                            </ul>
                            <br><br><br>
                            <table width='100%'><tr><td><b>Technologist:</b> ______________</td><td><b>Consultant Verified:</b> ______________</td></tr></table>
                        </div>
                        <div style='text-align:center; position:fixed; bottom:0; width:100%'>
                            Dr. Haitham Ismail<br>Clinical Hematology/Oncology & BMT & Transfusion Medicine Consultant
                        </div>
                    </div>
                    <script>window.print()</script>
                    """
                    st.markdown(rpt, unsafe_allow_html=True)
