import streamlit as st
import pandas as pd
from datetime import date

# 1. BASE CONFIGURATION & STYLING
st.set_page_config(page_title="Tabuk Blood Bank Workstation", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    /* Printing & Header Styles */
    @media print { 
        .stApp > header, .sidebar, footer, .no-print { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 3px solid #b30000; padding: 20px; font-family: 'Times New Roman'; }
    }
    .print-only { display: none; }
    
    .hospital-logo { color: #b30000; text-align: center; border-bottom: 5px solid #b30000; margin-bottom: 10px; font-family: sans-serif; font-weight: bold; }
    
    .lot-badge { background-color: #ffebee; color: #b71c1c; padding: 5px 10px; border-radius: 5px; border: 1px solid #ffcdd2; font-weight: bold; text-align: center; margin-bottom: 20px;}
    
    /* Logic Status Boxes */
    .logic-pass { background-color: #e8f5e9; border-left: 5px solid #2e7d32; padding: 10px; color: #1b5e20; }
    .logic-multi { background-color: #fff3e0; border-left: 5px solid #ef6c00; padding: 10px; color: #e65100; }
    .logic-critical { background-color: #ffebee; border-left: 5px solid #c62828; padding: 10px; color: #b71c1c; font-weight: bold;}
    
    /* Signature Footer */
    .dr-signature {
        position: fixed; bottom: 0px; width: 100%; 
        background: linear-gradient(to top, white 80%, transparent); 
        text-align: center; font-size: 11px; padding: 10px; color: #8B0000; z-index: 999;
        font-family: 'Georgia', serif; font-weight: bold; border-top: 1px solid #f0f0f0;
    }
</style>
""", unsafe_allow_html=True)

# THE SIGNATURE
st.markdown("""
<div class='dr-signature no-print'>
    Dr. Haitham Ismail<br>
    Clinical Hematology/Oncology & BMT & Transfusion Medicine Consultant
</div>
""", unsafe_allow_html=True)

# 2. DEFINITIONS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# 3. STATE (Memory)
if 'panel' not in st.session_state: st.session_state.panel = pd.DataFrame([{"ID":f"C{i+1}",**{a:0 for a in AGS}} for i in range(11)])
if 'screen' not in st.session_state: st.session_state.screen = pd.DataFrame([{"ID":f"S{i}",**{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'active_lot' not in st.session_state: st.session_state.active_lot = "Not Set"

# 4. LOGIC ENGINE
def parse_paste(txt, limit):
    # Same reliable parser from before
    try:
        lines = txt.strip().split('\n')
        data = []
        c=0
        for line in lines:
            if c >= limit: break
            parts = line.split('\t')
            row_v = []
            for p in parts:
                v_clean = str(p).lower().strip()
                val = 1 if any(x in v_clean for x in ['+', '1', 'pos', 'w']) else 0
                row_v.append(val)
            # Ensure 26 cols
            if len(row_v)>26: row_v=row_v[-26:]
            while len(row_v)<26: row_v.append(0)
            
            d_row = {"ID": f"C{c+1}" if limit==11 else f"S{c}"}
            for i, ag in enumerate(AGS): d_row[ag] = row_v[i]
            data.append(d_row)
            c+=1
        return pd.DataFrame(data), f"Updated {c} rows."
    except Exception as e: return None, str(e)

def can_exclude_ag(ag, pheno):
    # Rule of Exclusion with Dosage
    if pheno.get(ag, 0) == 0: return False # Cannot exclude if cell is Ag Negative
    if ag in DOSAGE:
        # Check Homozygous (Ag+, Partner-) -> Rule Out OK
        partner = PAIRS.get(ag)
        if partner and pheno.get(partner, 0) == 1:
            return False # Heterozygous -> Dosage Effect -> Do Not Exclude
    return True

def analyze_strategy(matches):
    advice = []
    # If we have 2 candidates e.g. D, K
    if len(matches) > 1:
        advice.append("⚠️ **Separation Required:** Use Selected Cells with the following profiles:")
        for target in matches:
            # We need a cell that is Target+ and Others-
            others = [x for x in matches if x != target]
            neg_cond = " & ".join([f"{o}-" for o in others])
            advice.append(f"- To confirm **Anti-{target}**: Find a cell **{target}+ / {neg_cond}**")
    return advice

# 5. UI SIDEBAR
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    mode = st.radio("System Mode", ["Workstation", "Supervisor"])
    st.divider()
    if st.button("Refresh / Reset"): st.session_state.temp=[] ; st.rerun()

# --- ADMIN PANEL ---
if mode == "Supervisor":
    st.title("Admin Configuration")
    if st.text_input("Passcode", type="password") == "admin123":
        st.success("Access Granted")
        
        # 1. Set Lot Number
        st.subheader("1. Active Panel Details")
        new_lot = st.text_input("Enter Current Lot Number:", value=st.session_state.active_lot)
        if st.button("Update Lot Info"):
            st.session_state.active_lot = new_lot
            st.success("Lot Updated")

        # 2. Paste Data
        st.subheader("2. Panel Data Entry (Copy/Paste)")
        t1, t2 = st.tabs(["Panel 11", "Screen 3"])
        
        with t1:
            txt_p = st.text_area("Paste Excel Numbers (11 rows)", height=150)
            if st.button("Update Panel Data"):
                df, m = parse_paste(txt_p, 11)
                if df is not None: st.session_state.panel = df; st.success(m)
            st.dataframe(st.session_state.panel.iloc[:, :10]) # Show preview

        with t2:
            txt_s = st.text_area("Paste Screen Numbers (3 rows)", height=100)
            if st.button("Update Screen Data"):
                df, m = parse_paste(txt_s, 3)
                if df is not None: st.session_state.screen = df; st.success(m)
            st.dataframe(st.session_state.screen.iloc[:, :10])

# --- USER WORKSTATION ---
else:
    # HOSPITAL HEADER
    st.markdown("""
    <div class='hospital-logo'>
        <h1>Maternity & Children Hospital - Tabuk</h1>
        <h4>Immunohematology Reference Lab</h4>
    </div>
    """, unsafe_allow_html=True)
    
    # ALERT FOR LOT NUMBER
    lot_color = "#b71c1c" if st.session_state.active_lot == "Not Set" else "#2e7d32"
    st.markdown(f"""
    <div class='lot-badge' style='color:{lot_color}; border-color:{lot_color}'>
        Active Panel Lot Number: {st.session_state.active_lot}
    </div>
    """, unsafe_allow_html=True)

    # PATIENT INFO
    c1,c2,c3,c4 = st.columns(4)
    p_name = c1.text_input("Patient Name")
    p_id = c2.text_input("MRN / File")
    p_tech = c3.text_input("Technician")
    p_date = c4.date_input("Date", value=date.today())
    
    st.divider()
    
    # === INPUT FORM ===
    with st.form("results_form"):
        # Custom Grades list
        GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]
        
        col_L, col_R = st.columns([1, 2])
        
        with col_L:
            st.write("#### Control / Screen")
            ac_res = st.radio("Auto Control (AC)", ["Negative", "Positive"])
            
            s1 = st.selectbox("Screen Cell I", GRADES)
            s2 = st.selectbox("Screen Cell II", GRADES)
            s3 = st.selectbox("Screen Cell III", GRADES)
            
        with col_R:
            st.write("#### Identification Panel (11 Cells)")
            g1, g2 = st.columns(2)
            # Safe hardcoded inputs
            with g1:
                c1 = st.selectbox("Cell 1", GRADES, key="c1")
                c2 = st.selectbox("Cell 2", GRADES, key="c2")
                c3 = st.selectbox("Cell 3", GRADES, key="c3")
                c4 = st.selectbox("Cell 4", GRADES, key="c4")
                c5 = st.selectbox("Cell 5", GRADES, key="c5")
                c6 = st.selectbox("Cell 6", GRADES, key="c6")
            with g2:
                c7 = st.selectbox("Cell 7", GRADES, key="c7")
                c8 = st.selectbox("Cell 8", GRADES, key="c8")
                c9 = st.selectbox("Cell 9", GRADES, key="c9")
                c10 = st.selectbox("Cell 10", GRADES, key="c10")
                c11 = st.selectbox("Cell 11", GRADES, key="c11")
                
        submit_btn = st.form_submit_button("🚀 Run Expert Analysis")
    
    # === ANALYSIS ENGINE V106 ===
    if submit_btn:
        
        # 1. Map Inputs to Binary (Pos/Neg)
        def to_bin(val): return 0 if val == "0" else 1
        
        inp_panel = [to_bin(x) for x in [c1,c2,c3,c4,c5,c6,c7,c8,c9,c10,c11]]
        inp_screen = [to_bin(x) for x in [s1,s2,s3]]
        
        # 2. Logic Check: AC & Pan-Reactivity
        total_pos_panel = sum(inp_panel)
        is_ac_pos = (ac_res == "Positive")
        
        st.subheader("Diagnostics & Interpretation")
        
        # CASE A: High Frequency (All Panel Pos + AC Neg)
        if total_pos_panel == 11 and not is_ac_pos:
            st.markdown("""
            <div class='logic-critical'>
                <h3>🚨 High Probability: Antibody to High-Prevalence Antigen</h3>
                All panel cells are positive while Auto-Control is Negative.<br>
                <b>Guidance:</b><br>
                1. Most likely an antibody against a high incidence antigen (e.g. Anti-k, Anti-Kp(b), Anti-Lub).<br>
                2. <b>Family Study Required:</b> Search in first-degree relatives (siblings) for compatible blood.<br>
                3. Phenotype the patient (Must be Antigen Negative).
            </div>
            """, unsafe_allow_html=True)
            
        # CASE B: Auto Antibody
        elif is_ac_pos:
             st.markdown("""
            <div class='logic-critical'>
                <h3>🚨 Auto-Control is POSITIVE</h3>
                Interpretation is halted.
                <hr>
                <b>Guidance:</b><br>
                1. Perform <b>Monospecific DAT</b> (IgG vs C3d).<br>
                2. If IgG+ (Pan-agglutination): Suspect <b>WAIHA</b>. Perform Adsorption/Elution.<br>
                3. If C3d+: Suspect Cold Agglutinins (Pre-warm technique).<br>
                4. Check for Delayed Hemolytic Transfusion Reaction if recently transfused.
            </div>
            """, unsafe_allow_html=True)
             
        # CASE C: Alloantibody (Normal Logic)
        else:
            # 1. Exclusion Phase
            ruled_out = set()
            r_pan = [st.session_state.panel.iloc[i].to_dict() for i in range(11)]
            r_scr = [st.session_state.screen.iloc[i].to_dict() for i in range(3)]
            
            # Check Panel Negatives
            for i, val in enumerate(inp_panel):
                if val == 0:
                    for ag in AGS:
                        if can_exclude_ag(ag, r_pan[i]): ruled_out.add(ag)
                        
            # Check Screen Negatives
            for i, val in enumerate(inp_screen):
                if val == 0:
                    for ag in AGS:
                        if can_exclude_ag(ag, r_scr[i]): ruled_out.add(ag)
                        
            # 2. Candidates
            candidates = [a for a in AGS if a not in ruled_out]
            
            if not candidates:
                st.error("❌ No common allo-antibody matches. Possible low-frequency antibody or Technical Error.")
            
            else:
                # SINGLE MATCH
                if len(candidates) == 1:
                    ab = candidates[0]
                    st.success(f"✅ **Single Allo-antibody Detected: Anti-{ab}**")
                    st.markdown(f"<div class='logic-pass'>Matches Exclusion Logic & Pattern.</div>", unsafe_allow_html=True)
                    st.info(f"👉 **Action:** Phenotype patient for {ab} antigen (Expected: Negative).")
                    
                # MULTIPLE MATCHES
                else:
                    st.warning(f"⚠️ **Multiple Antibodies Suspected:** {', '.join(candidates)}")
                    
                    st.markdown("<div class='logic-multi'><b>👩‍🔬 Smart Guide for Separation (Selected Cells):</b></div>", unsafe_allow_html=True)
                    
                    advice = analyze_strategy(candidates)
                    for line in advice:
                        st.write(line)
                
                # Report Print
                report = f"""
                <div class='print-only'>
                    <center>
                        <h2 style='color:#800000'>Maternity & Children Hospital - Tabuk</h2>
                        <h4>Immunohematology Laboratory</h4>
                    </center>
                    <br>
                    <table width='100%' style='border:1px solid #333'>
                        <tr><td style='padding:5px'><b>Pt:</b> {p_name}</td><td><b>ID:</b> {p_id}</td></tr>
                        <tr><td style='padding:5px'><b>Tech:</b> {p_tech}</td><td><b>Date:</b> {p_date}</td></tr>
                        <tr><td colspan='2' style='padding:5px'><b>Panel Lot:</b> {st.session_state.active_lot}</td></tr>
                    </table>
                    <hr>
                    <h3>Interpretation Result</h3>
                    <p style='font-size:18px; font-weight:bold'>Conclusion: Possible Anti-{', '.join(candidates)}</p>
                    <p><b>Notes:</b> Clinical correlation & phenotyping required.</p>
                    <br><br><br>
                    <table width='100%'><tr><td><b>Technologist:</b> ______________</td><td><b>Supervisor:</b> ______________</td></tr></table>
                    <div style='position:fixed;bottom:0;width:100%;text-align:center;border-top:1px solid #ccc;padding:5px'>
                        Dr. Haitham Ismail | Clinical Hematology/Oncology Consultant
                    </div>
                </div>
                <script>window.print();</script>
                """
                st.markdown(report, unsafe_allow_html=True)
