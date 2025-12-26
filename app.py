import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. إعدادات الصفحة (STYLE FIXES)
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🏥")

st.markdown("""
<style>
    /* Printing Cleanup */
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .block-container { padding: 0 !important; }
        .print-only { display: block !important; }
        .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; }
        .results-box { border: 2px solid #333; padding: 15px; font-family: 'Times New Roman'; margin-top: 20px; }
    }
    
    .hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    
    /* Signature Style */
    .signature-badge {
        position: fixed; bottom: 10px; right: 15px; text-align: right;
        font-family: 'Georgia', serif; font-size: 12px; color: #8B0000;
        background-color: rgba(255, 255, 255, 0.95); padding: 8px 15px;
        border-radius: 8px; border: 1px solid #eecaca;
        z-index: 9999;
    }
    .dr-name { font-weight: bold; font-size: 15px; display: block; margin-bottom: 3px;}
    
    /* Table Fixes */
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    
    /* Colors */
    .status-pass { background-color: #d1e7dd; padding: 10px; border-radius: 5px; color: #0f5132; border-left: 5px solid #198754; margin-bottom:5px; }
    .status-fail { background-color: #f8d7da; padding: 10px; border-radius: 5px; color: #842029; border-left: 5px solid #dc3545; margin-bottom:5px; }
</style>
""", unsafe_allow_html=True)

# Footer
st.markdown("""
<div class='signature-badge no-print'>
    <span class='dr-name'>Dr. Haitham Ismail</span>
    Clinical Hematology/Oncology & Transfusion Medicine Consultant
</div>
""", unsafe_allow_html=True)

# Data Structures
antigens_order = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
ANTIGEN_ALIASES = { "D": ["D", "Rh(D)", "RH1"], "C": ["C", "rh'", "RH2"], "E": ["E", "rh''", "RH3"], "c": ["c", "hr'", "RH4"], "e": ["e", "hr''", "RH5"], "Fya": ["Fya", "Fy(a)"], "Fyb": ["Fyb", "Fy(b)"], "Jka": ["Jka", "Jk(a)"], "Jkb": ["Jkb", "Jk(b)"], "Lea": ["Lea", "Le(a)"], "Leb": ["Leb", "Le(b)"], "P1": ["P1", "P"], "M": ["M", "MN"], "N": ["N"], "S": ["S"], "s": ["s"] }
allele_pairs = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Kpa':'Kpb', 'Kpb':'Kpa', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S', 'Lea':'Leb', 'Leb':'Lea'}
STRICT_DOSAGE_SYSTEMS = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]

# --- INITIAL STATE SAFETY ---
if 'panel_11' not in st.session_state:
    # Initialize with Integers 0 (Critical for display)
    df_init = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in antigens_order}} for i in range(11)])
    st.session_state.panel_11 = df_init.infer_objects()
    
if 'panel_3' not in st.session_state:
    st.session_state.panel_3 = pd.DataFrame([{"ID": f"Scn {i}", **{ag: 0 for ag in antigens_order}} for i in ["I", "II", "III"]])
if 'inputs' not in st.session_state: st.session_state.inputs = {f"c{i}": "Neg" for i in range(1, 12)}
if 'inputs_screen' not in st.session_state: st.session_state.inputs_screen = {f"s{i}": "Neg" for i in ["I", "II", "III"]}
if 'extra_cells' not in st.session_state: st.session_state.extra_cells = []

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def find_column_in_df(df, target_ag):
    # Try exact match first
    for col in df.columns:
        if str(col).strip() == target_ag: return col
    # Fuzzy match
    for col in df.columns:
        clean_c = str(col).upper().replace("(","").replace(")","").replace(" ","")
        clean_t = target_ag.upper().replace("(","").replace(")","").replace(" ","")
        if clean_c == clean_t: return col
        # Check aliases
        aliases = ANTIGEN_ALIASES.get(target_ag, [])
        for alias in aliases:
            clean_a = alias.upper().replace("(","").replace(")","").replace(" ","")
            if clean_c == clean_a: return col
    return None

def normalize_val(val):
    s = str(val).lower().strip()
    return 1 if s in ['+','1','pos','yes','1.0'] else 0

def can_rule_out(ag, pheno):
    if pheno.get(ag,0)==0: return False
    if ag in STRICT_DOSAGE_SYSTEMS:
        pair = allele_pairs.get(ag)
        if pair and pheno.get(pair,0)==1: return False
    return True

def bulk_set(val):
    for i in range(1, 12): st.session_state.inputs[f"c{i}"] = val

def check_rule(cand, rows11, inputs11, rows3, inputs3, extra):
    pos_r, neg_r = 0, 0
    # Panel
    for i in range(1,12):
        res = 1 if inputs11[i]!="Neg" else 0
        if res==1 and rows11[i-1].get(cand,0)==1: pos_r+=1
        if res==0 and rows11[i-1].get(cand,0)==0: neg_r+=1
    # Screen
    scr_ids = ["I", "II", "III"]
    for i, sid in enumerate(scr_ids):
        res = 1 if inputs3[f"s{sid}"]!="Neg" else 0
        if res==1 and rows3[i].get(cand,0)==1: pos_r+=1
        if res==0 and rows3[i].get(cand,0)==0: neg_r+=1
    # Extra
    for c in extra:
        res = c['score']
        if res==1 and c['pheno'].get(cand,0)==1: pos_r+=1
        if res==0 and c['pheno'].get(cand,0)==0: neg_r+=1
    
    passed = (pos_r>=3 and neg_r>=3) or (pos_r>=2 and neg_r>=3)
    method = "Standard Rule Met (3/3)" if (pos_r>=3 and neg_r>=3) else ("Modified Rule Met (2/3)" if passed else "Rule NOT Met")
    return passed, pos_r, neg_r, method

# ==========================================
# 3. SIDEBAR NAVIGATION (CLEAR NAVIGATION)
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=70)
    st.write("System V21.0 (Stable)")
    
    st.write("---")
    st.write("## 📍 Menu")
    # This is the clear Navigation you requested
    app_mode = st.radio("Go to:", ["🔵 User Workstation", "🔴 Supervisor Config"])
    
    st.write("---")
    if st.button("🔄 Reset / Clear Extra Cells"):
        st.session_state.extra_cells = []
        st.rerun()

# ==========================================
# 4. SUPERVISOR CONFIG (ADMIN PAGE)
# ==========================================
if app_mode == "🔴 Supervisor Config":
    st.title("🛠️ Master Configuration (Admin)")
    
    # Password check
    pwd = st.text_input("Enter Supervisor Password:", type="password")
    
    if pwd == "admin123":
        st.success("✅ Logged In")
        
        tab_p11, tab_scr = st.tabs(["Panel 11 Setup", "Screening Cells"])
        
        # --- TAB 1: 11 Cells ---
        with tab_p11:
            st.info("Upload Excel or Edit Grid Below")
            col_load, col_view = st.columns([1, 2])
            
            with col_load:
                up_file = st.file_uploader("Upload Excel Sheet", type=["xlsx", "xls"])
                
                if up_file:
                    try:
                        raw = pd.read_excel(up_file)
                        clean_data = []
                        
                        # Loop limited to 11 cells max
                        for i in range(min(11, len(raw))):
                            row = {"ID": f"Cell {i+1}"}
                            for ag in antigens_order:
                                col_match = find_column_in_df(raw, ag)
                                val = 0
                                if col_match:
                                    val = normalize_val(raw.iloc[i][col_match])
                                row[ag] = int(val) # Force Integer
                            clean_data.append(row)
                        
                        # FORCE UPDATE STATE AND REFRESH
                        df_new = pd.DataFrame(clean_data)
                        st.session_state.panel_11 = df_new
                        st.success("File processed! Refreshing...")
                        # Important: Do not rerun immediately inside loop, wait for interaction
                        # or display success message
                        
                    except Exception as e:
                        st.error(f"Error parsing file: {e}")

            with col_view:
                st.write("**Current Master Data (Editable):**")
                # Ensuring data is integer to prevent "Empty Table" glitch
                df_display = st.session_state.panel_11.fillna(0) # No NaNs allowed
                
                edited_df = st.data_editor(
                    df_display, 
                    use_container_width=True, 
                    height=450,
                    hide_index=True,
                    column_config={"ID": st.column_config.TextColumn(disabled=True)}
                )
                
                if st.button("💾 Save Changes"):
                    st.session_state.panel_11 = edited_df
                    st.success("Changes Saved to Memory.")

        # --- TAB 2: Screen Cells ---
        with tab_scr:
            st.write("Edit Screening Cells (I, II, III):")
            st.session_state.panel_3 = st.data_editor(st.session_state.panel_3, hide_index=True, use_container_width=True)

    else:
        if pwd: st.error("Wrong Password")
        st.stop()

# ==========================================
# 5. USER WORKSTATION (DAILY USE)
# ==========================================
elif app_mode == "🔵 User Workstation":
    
    st.markdown("""<div class='hospital-header'><h1>Maternity & Children Hospital - Tabuk</h1><h4>Blood Bank Serology Workstation</h4></div>""", unsafe_allow_html=True)
    
    # 1. Info
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mrn=c2.text_input("MRN"); tech=c3.text_input("Tech"); dt=c4.date_input("Date")
    
    st.divider()
    
    # 2. Entry Grid
    L, R = st.columns([1, 2.5])
    
    with L:
        st.subheader("1. Screen/AC")
        for x in ["I","II","III"]:
            k = f"s{x}"
            st.session_state.inputs_screen[k] = st.selectbox(f"Scn {x}", ["Neg","w+","1+","2+","3+","4+"], key=f"user_{x}")
        st.write("---")
        ac = st.radio("AC", ["Negative","Positive"], horizontal=True)
        
        st.caption("Quick Fill:")
        if st.button("All Neg"): bulk_set("Neg")
        if st.button("All Pos"): bulk_set("2+")

    with R:
        st.subheader("2. Panel Reactions (11 Cells)")
        # Dense Grid Layout
        cols = st.columns(6)
        pan_sc = {}
        pos_cnt = 0
        
        for i in range(1, 12):
            k = f"c{i}"
            col_idx = (i-1) % 6
            v = cols[col_idx].selectbox(f"Cell {i}", ["Neg","w+","1+","2+","3+","4+"], key=f"u_{i}", index=["Neg","w+","1+","2+","3+","4+"].index(st.session_state.inputs[k]))
            st.session_state.inputs[k] = v
            sc = 0 if v=="Neg" else 1
            pan_sc[i] = sc
            if sc: pos_cnt+=1

    # 3. ANALYSIS
    st.divider()
    
    # Stop Logic for AC+
    if ac == "Positive":
        st.error("🚨 STOP: Auto Control is Positive.")
        st.info("Clinical Guideline: 1. Perform Monospecific DAT. 2. If IgG+, suspect WAIHA/DHTR. 3. If C3d+, suspect CAS.")
        st.stop()
        
    if st.checkbox("🔍 Start Investigation Logic"):
        
        # High Freq Check
        if pos_cnt == 11:
            st.warning("⚠️ Warning: Pan-Agglutination. Suspect Antibody to High Frequency Antigen.")
        
        else:
            # Prepare Dataframes (Safe Copy)
            r11 = [st.session_state.panel_11.iloc[i].to_dict() for i in range(11)]
            r3 = [st.session_state.panel_3.iloc[i].to_dict() for i in range(3)]
            
            # Exclusion (Panel + Screen Negatives)
            ruled_out = set()
            
            # From Panel Inputs
            for i, score in pan_sc.items():
                if score == 0:
                    for ag in antigens_order:
                        if can_rule_out(ag, r11[i-1]): ruled_out.add(ag)
            
            # From Screen Inputs (Added Value!)
            s_idx_map = {"I":0, "II":1, "III":2}
            for k,v in st.session_state.inputs_screen.items(): # k="sI"
                if v == "Neg":
                    ph = r3[s_idx_map[k[1:]]]
                    for ag in antigens_order:
                        if ag not in ruled_out:
                            if can_rule_out(ag, ph): ruled_out.add(ag)

            # Inclusion
            cands = [x for x in antigens_order if x not in ruled_out]
            match = []
            
            # Match Logic (Positive cells must contain Antigen)
            # Using Panel cells mostly for pattern matching
            for cand in cands:
                mis = False
                for i, score in pan_sc.items():
                    if score > 0 and r11[i-1].get(cand, 0) == 0: mis = True
                if not mis: match.append(cand)
            
            # Results
            if not match:
                st.error("❌ Inconclusive (Pattern mismatch or all excluded).")
            else:
                allow_print = True
                st.subheader("3. Identification Results")
                
                for m in match:
                    passed, p, n, method = check_rule(m, r11, st.session_state.inputs, r3, st.session_state.inputs_screen, st.session_state.extra_cells)
                    
                    st.markdown(f"""
                    <div class='{'status-pass' if passed else 'status-fail'}'>
                        <b>Anti-{m}:</b> {method}<br>
                        Pos Cells Reacting: {p} | Neg Cells Clean: {n}<br>
                        Probability p ≤ 0.05: {'YES' if passed else 'NO'}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if not passed: allow_print=False
                
                # --- Actions ---
                if allow_print:
                    if st.button("🖨️ Print Final Report"):
                        rpt = f"""
                        <div class='print-only'>
                            <br><div class='hospital-header'><h2>Maternity & Children Hospital - Tabuk</h2></div>
                            <div class='results-box'>
                                <table width='100%'><tr><td>Pt: {nm}</td><td>MRN: {mrn}</td></tr><tr><td>Tech: {tech}</td><td>Date: {dt}</td></tr></table>
                                <hr>
                                <h3>Interpretation Report</h3>
                                <p><b>Antibodies Detected:</b> Anti-{', '.join(match)}</p>
                                <p><b>Validation:</b> Confirmed by exclusion & Rule of Three (p≤0.05).</p>
                                <p><b>Note:</b> Phenotype patient for: {', '.join(match)} (Expected Negative).</p>
                                <hr><br><br>
                                <table width='100%'><tr><td>Signature: _____________</td><td>Verifier: _____________</td></tr></table>
                                <div class='consultant-footer'><span style='color:#8B0000; font-weight:bold;'>Dr. Haitham Ismail</span><br>Clinical Hematology/Oncology Consultant</div>
                            </div>
                        </div>
                        <script>window.print()</script>
                        """
                        st.markdown(rpt, unsafe_allow_html=True)
                else:
                    st.warning("⚠️ Confirmation Required: Use Extra Cells.")
                    with st.expander("➕ Add Selected Cell (From Library)"):
                        x1,x2,x3=st.columns([1,1,2])
                        nid = x1.text_input("Cell Lot#")
                        nres = x2.selectbox("Result", ["Neg","Pos"])
                        pcols = x3.columns(len(match))
                        tph = {}
                        for i,mm in enumerate(match):
                            r=pcols[i].radio(mm, ["+","0"], key=f"add_{mm}")
                            tph[mm]=1 if r=="+" else 0
                        if st.button("Add"):
                            st.session_state.extra_cells.append({"src":nid,"score":1 if nres=="Pos" else 0,"pheno":tph})
                            st.rerun()
