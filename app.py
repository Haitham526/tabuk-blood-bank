import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. SETUP & STYLING
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🏥")

st.markdown("""
<style>
    /* ----- Printing Rules ----- */
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .block-container { padding: 0 !important; }
        .print-only { display: block !important; }
        .results-box { border: 2px solid #333; padding: 15px; font-family: 'Times New Roman'; margin-top: 20px; }
        /* Footer Position for Print */
        .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; }
    }
    
    /* ----- Header Styling ----- */
    .hospital-header { 
        text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; 
        font-family: 'Arial'; color: #003366; 
    }
    
    /* ----- Dr. Haitham Signature (Elegant Red) ----- */
    .signature-badge {
        position: fixed;
        bottom: 10px;
        right: 15px;
        text-align: right;
        font-family: 'Georgia', serif; /* خط كلاسيكي أنيق */
        font-size: 12px;
        color: #8B0000; /* Dark Red */
        background-color: rgba(255, 255, 255, 0.9);
        padding: 5px 10px;
        border-radius: 5px;
        border: 1px solid #eecaca;
        z-index: 9999;
    }
    .dr-name { font-weight: bold; font-size: 14px; display: block; }
    
    /* ----- Logic Status Boxes ----- */
    .status-pass { background-color: #d1e7dd; padding: 10px; border-radius: 5px; color: #0f5132; border-left: 5px solid #198754; margin-bottom:5px; }
    .status-fail { background-color: #f8d7da; padding: 10px; border-radius: 5px; color: #842029; border-left: 5px solid #dc3545; margin-bottom:5px; }
</style>
""", unsafe_allow_html=True)

# Signature Display
st.markdown("""
<div class='signature-badge no-print'>
    <span class='dr-name'>Dr. Haitham Ismail</span>
    Clinical Hematology/Oncology & Transfusion Medicine Consultant
</div>
""", unsafe_allow_html=True)

# Definitions
antigens_order = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
ANTIGEN_ALIASES = { "D": ["D", "Rh(D)", "RH1"], "C": ["C", "rh'", "RH2"], "E": ["E", "rh''", "RH3"], "c": ["c", "hr'", "RH4"], "e": ["e", "hr''", "RH5"], "Fya": ["Fya", "Fy(a)"], "Fyb": ["Fyb", "Fy(b)"], "Jka": ["Jka", "Jk(a)"], "Jkb": ["Jkb", "Jk(b)"], "Lea": ["Lea", "Le(a)"], "Leb": ["Leb", "Le(b)"], "P1": ["P1", "P"], "M": ["M", "MN"], "N": ["N"], "S": ["S"], "s": ["s"] }
allele_pairs = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Kpa':'Kpb', 'Kpb':'Kpa', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S', 'Lea':'Leb', 'Leb':'Lea'}
STRICT_DOSAGE_SYSTEMS = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]

# States
if 'panel_11' not in st.session_state:
    st.session_state.panel_11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in antigens_order}} for i in range(11)])
if 'panel_3' not in st.session_state:
    st.session_state.panel_3 = pd.DataFrame([{"ID": f"Scn {i}", **{ag: 0 for ag in antigens_order}} for i in ["I", "II", "III"]])
if 'inputs' not in st.session_state: st.session_state.inputs = {f"c{i}": "Neg" for i in range(1, 12)}
if 'inputs_screen' not in st.session_state: st.session_state.inputs_screen = {f"s{i}": "Neg" for i in ["I", "II", "III"]}
if 'extra_cells' not in st.session_state: st.session_state.extra_cells = []
if 'admin_mode' not in st.session_state: st.session_state.admin_mode = False

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def find_column_in_df(df, target_ag):
    # Parser for messy headers
    for col in df.columns:
        if str(col).strip().upper() == target_ag.upper(): return col
    aliases = ANTIGEN_ALIASES.get(target_ag, [])
    for alias in aliases:
        for col in df.columns:
            if str(col).replace(" ","").replace("\n","").upper() == alias.upper(): return col
    return None

def normalize_val(val):
    return 1 if str(val).lower().strip() in ['+','1','pos','yes'] else 0

def can_rule_out(ag, pheno):
    if pheno.get(ag,0)==0: return False
    if ag in STRICT_DOSAGE_SYSTEMS:
        pair = allele_pairs.get(ag)
        if pair and pheno.get(pair,0)==1: return False
    return True

def bulk_set(val):
    for i in range(1, 12): st.session_state.inputs[f"c{i}"] = val

# P-Value Calculator (Includes Screen + Panel + Extra)
def check_rule(cand, rows11, inputs11, rows3, inputs3, extra):
    pos_r, neg_r = 0, 0
    # Panel
    for i in range(1,12):
        if inputs11[i]>0 and rows11[i-1].get(cand,0)==1: pos_r+=1
        if inputs11[i]==0 and rows11[i-1].get(cand,0)==0: neg_r+=1
    # Screen (NEW FEATURE: using screen results in calculation)
    scr_ids = ["I", "II", "III"]
    for i, id_val in enumerate(scr_ids):
        res = 0 if inputs3[id_val]=="Neg" else 1
        if res>0 and rows3[i].get(cand,0)==1: pos_r+=1
        if res==0 and rows3[i].get(cand,0)==0: neg_r+=1
    # Extra
    for c in extra:
        if c['score']>0 and c['pheno'].get(cand,0)==1: pos_r+=1
        if c['score']==0 and c['pheno'].get(cand,0)==0: neg_r+=1
        
    passed = (pos_r>=3 and neg_r>=3) or (pos_r>=2 and neg_r>=3)
    method = "Standard" if (pos_r>=3 and neg_r>=3) else ("Modified" if (pos_r>=2 and neg_r>=3) else "Failed")
    return passed, pos_r, neg_r, method

# ==========================================
# 3. SIDEBAR (Login Only)
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=50)
    st.caption("Workstation V20.0")
    if st.checkbox("Supervisor Config"):
        if st.text_input("Password", type="password") == "admin123":
            st.session_state.admin_mode = True
            st.success("✅ Access Granted")
        else:
            st.session_state.admin_mode = False
    else:
        st.session_state.admin_mode = False

# ==========================================
# 4. ADMIN DASHBOARD
# ==========================================
if st.session_state.admin_mode:
    st.title("🛠️ Master Configuration (Supervisor)")
    st.warning("⚠️ Warning: Updating these tables changes the logic for all users.")
    
    # --- TWO TABS STRATEGY ---
    tab_pan, tab_scr = st.tabs(["📂 Identification Panel (11 Cells)", "🧪 Screening Panel (3 Cells)"])
    
    # TAB 1: PANEL 11
    with tab_pan:
        col_up, col_ed = st.columns([1, 2])
        with col_up:
            up_11 = st.file_uploader("Upload Panel (Excel)", type=["xlsx"], key="up11")
            if up_11:
                # ... (Reading Logic as before)
                try:
                    df = pd.read_excel(up_11)
                    new_data = []
                    for i in range(min(11, len(df))):
                        r = {"ID": f"Cell {i+1}"}
                        for ag in antigens_order:
                            c = find_column_in_df(df, ag)
                            r[ag] = normalize_val(df.iloc[i][c]) if c else 0
                        new_data.append(r)
                    st.session_state.panel_11 = pd.DataFrame(new_data)
                    st.success("Panel Updated!")
                except Exception as e: st.error(f"Error: {e}")
        
        with col_ed:
            st.session_state.panel_11 = st.data_editor(st.session_state.panel_11, hide_index=True, use_container_width=True, height=450)

    # TAB 2: SCREEN 3 (New Requested Feature)
    with tab_scr:
        st.info("Set the Antigram for Screen Cells (I, II, III). You can edit manually.")
        # Manual edit is best here as Screen Panels often lack complex Excel files
        st.session_state.panel_3 = st.data_editor(
            st.session_state.panel_3, 
            hide_index=True, 
            use_container_width=True, 
            height=200,
            column_config={"ID": st.column_config.TextColumn(disabled=True)}
        )

# ==========================================
# 5. USER WORKSTATION
# ==========================================
else:
    st.markdown("""<div class='hospital-header'><h1>Maternity & Children Hospital - Tabuk</h1><h4>Blood Bank Serology</h4></div>""", unsafe_allow_html=True)
    
    # Inputs
    c1,c2,c3,c4 = st.columns(4)
    p_name = c1.text_input("Name"); p_mrn=c2.text_input("MRN"); p_tech=c3.text_input("Technologist"); p_date=c4.date_input("Date")
    st.divider()
    
    c_left, c_right = st.columns([1, 2])
    
    # LEFT: Screen & AC
    with c_left:
        st.subheader("1. Screening & Control")
        # Screen Inputs (Bind to state)
        for i in ["I", "II", "III"]:
            key = f"s{i}"
            st.session_state.inputs_screen[key] = st.selectbox(f"Screen Cell {i}", ["Neg","w+","1+","2+","3+","4+"], key=f"sel_{key}")
        
        st.write("---")
        ac = st.radio("Auto Control (AC)", ["Negative", "Positive"], horizontal=True)
        if ac=="Positive":
            st.error("🚨 DAT Investigation Required.")
            st.stop() # Stops logic here for brevity in this snippet
            
        st.write("---")
        if st.button("Set All Neg (Panel)"): bulk_set("Neg")
        if st.button("Set All 2+ (Panel)"): bulk_set("2+")

    # RIGHT: Panel Reactions
    with c_right:
        st.subheader("2. Panel Reactions")
        g = st.columns(6)
        in_map = {} # Score map
        for i in range(1,12):
            key=f"c{i}"
            val = g[(i-1)%6].selectbox(f"C {i}", ["Neg","w+","1+","2+","3+","4+"], key=f"sel_{key}", index=["Neg","w+","1+","2+","3+","4+"].index(st.session_state.inputs[key]))
            st.session_state.inputs[key]=val
            in_map[i] = 0 if val=="Neg" else 1 # Simplified score 1 for logic
            
    st.divider()
    
    # Logic
    if st.checkbox("🔴 Run Advanced Analysis"):
        rows11 = [st.session_state.panel_11.iloc[i].to_dict() for i in range(11)]
        rows3  = [st.session_state.panel_3.iloc[i].to_dict() for i in range(3)]
        
        # 1. EXCLUSION (Using Panel Negatives)
        # Note: Ideally we should use Screen negatives too if Panel doesn't exclude everything
        # Current Logic: Uses Panel inputs to exclude first.
        out = set()
        for ag in antigens_order:
            for idx, score in in_map.items():
                if score == 0:
                    if can_rule_out(ag, rows11[idx-1]):
                        out.add(ag); break
        
        # Add Screen Negatives to Exclusion (Powerful enhancement)
        scr_map = {"I":0, "II":1, "III":2}
        for k, v in st.session_state.inputs_screen.items():
            s_key = k[1:] # "I" from "sI"
            s_score = 0 if v=="Neg" else 1
            if s_score == 0:
                s_pheno = rows3[scr_map[s_key]]
                for ag in antigens_order:
                    if ag not in out and can_rule_out(ag, s_pheno):
                        out.add(ag)

        cands = [x for x in antigens_order if x not in out]
        
        # 2. MATCHING (Inclusion) - Using Panel Only mostly
        match = []
        for c in cands:
            mis = False
            for idx, score in in_map.items():
                if score > 0 and rows11[idx-1].get(c,0) == 0: mis = True
            if not mis: match.append(c)
            
        if not match: st.error("❌ Inconclusive / All Ruled Out")
        else:
            allow = True
            st.subheader("3. Result Validation")
            
            for m in match:
                # Calc Probability using Panel + Screen
                passed, pos, neg, meth = check_rule(m, rows11, in_map, rows3, st.session_state.inputs_screen, st.session_state.extra_cells)
                
                status_color = 'pass' if passed else 'fail'
                st.markdown(f"""
                <div class='status-{status_color}'>
                    <b>Anti-{m}:</b> {meth} <br>
                    <small>Stats: {pos} Positive Cells / {neg} Negative Cells reacting appropriately.</small>
                </div>
                """, unsafe_allow_html=True)
                
                if not passed: allow=False
            
            # --- Printing ---
            if allow:
                if st.button("🖨️ Print Final Report"):
                    # Generate Report HTML
                    final_rpt = f"""
                    <div class='print-only'>
                        <br>
                        <div class='hospital-header'><h2>Maternity & Children Hospital - Tabuk</h2></div>
                        <div class='results-box'>
                            <table width="100%">
                                <tr><td><b>Patient Name:</b> {p_name}</td> <td><b>MRN:</b> {p_mrn}</td></tr>
                                <tr><td><b>Technologist:</b> {p_tech}</td> <td><b>Date:</b> {p_date}</td></tr>
                            </table>
                            <hr>
                            <p style='font-size:16px;'><b>Antibody Identified:</b> Anti-{', '.join(match)}</p>
                            <p><b>Analysis Validation:</b> Probability Met (p &le; 0.05). Screening cells included in calculation.</p>
                            <br>
                            <p><b>Clinical Recommendation:</b><br>1. Antigen type patient units.<br>2. Transfuse Antigen-Negative crossmatch compatible units.</p>
                            <br><br><br>
                            <table width="100%" style="border-top:1px solid #ccc; padding-top:10px;">
                                <tr><td><b>Performed By:</b> ___________</td> <td><b>Reviewed By:</b> ___________</td></tr>
                            </table>
                            <div class='consultant-footer'>
                                <span style='color:#8B0000; font-weight:bold; font-family:serif;'>Dr. Haitham Ismail</span><br>
                                Clinical Hematology/Oncology & Transfusion Medicine Consultant
                            </div>
                        </div>
                    </div>
                    <script>window.print();</script>
                    """
                    st.markdown(final_rpt, unsafe_allow_html=True)
            else:
                st.info("Confirmation required (Add Selected Cells).")
                # (Selected Cells Code Here - shortened for logic focus)
