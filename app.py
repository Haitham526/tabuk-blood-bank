import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. SETUP & STYLE
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology Expert", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .block-container { padding: 0 !important; }
        .print-only { display: block !important; }
        .results-box { border: 2px solid #333; padding: 15px; margin-top: 10px; font-family: 'Times New Roman'; font-size: 14px; }
        .watermark-print { position: fixed; bottom: 0; width: 100%; text-align: center; font-size: 10px; color: #555; }
    }
    
    .hospital-header { 
        text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; margin-bottom: 15px; 
        font-family: 'Arial'; color: #003366;
    }
    
    .status-pass { background-color: #d1e7dd; padding: 8px; border-radius: 5px; color: #0f5132; border: 1px solid #badbcc; }
    .status-fail { background-color: #f8d7da; padding: 8px; border-radius: 5px; color: #842029; border: 1px solid #f5c2c7; }
</style>
""", unsafe_allow_html=True)

# Data
antigens_order = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
allele_pairs = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Kpa':'Kpb', 'Kpb':'Kpa', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S', 'Lea':'Leb', 'Leb':'Lea'}
STRICT_DOSAGE_SYSTEMS = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]

# State
if 'panel_11' not in st.session_state:
    st.session_state.panel_11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in antigens_order}} for i in range(11)])
if 'inputs' not in st.session_state:
    st.session_state.inputs = {f"c{i}": "Neg" for i in range(1, 12)}
if 'extra_cells' not in st.session_state:
    st.session_state.extra_cells = [] 

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def can_rule_out(ag, pheno):
    if pheno.get(ag,0) == 0: return False
    if ag in STRICT_DOSAGE_SYSTEMS:
        pair = allele_pairs.get(ag)
        if pair and pheno.get(pair,0) == 1: return False
    return True

def bulk_set(val):
    for i in range(1, 12): st.session_state.inputs[f"c{i}"] = val

def check_rule_of_three(candidate, main_panel_rows, inputs_map, extra_cells_list):
    pos_reactions = 0
    neg_reactions = 0
    # Main Panel
    for i in range(1, 12):
        row = main_panel_rows[i-1]
        res_score = inputs_map[i]
        has_antigen = row.get(candidate, 0) == 1
        if has_antigen and res_score > 0: pos_reactions += 1
        if not has_antigen and res_score == 0: neg_reactions += 1
    # Extra Cells
    for cell in extra_cells_list:
        has_antigen = cell['pheno'].get(candidate, 0) == 1
        res_score = cell['score']
        if has_antigen and res_score > 0: pos_reactions += 1
        if not has_antigen and res_score == 0: neg_reactions += 1

    is_standard = (pos_reactions >= 3 and neg_reactions >= 3)
    is_modified = (pos_reactions >= 2 and neg_reactions >= 3)
    passed = is_standard or is_modified
    return passed, pos_reactions, neg_reactions, "Standard" if is_standard else ("Modified" if is_modified else "Failed")

# ==========================================
# 3. SIDEBAR & ADMIN (WITH EXCEL UPLOAD)
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=50)
    st.write("V18.1 Pro")
    if st.checkbox("Supervisor Login"):
        if st.text_input("Pwd", type="password") == "admin123":
            st.info("Configuration Mode")
            
            # --- UPLOAD SECTION ---
            uploaded_file = st.file_uploader("📂 Upload Excel (Optional)", type=['xlsx'])
            if uploaded_file:
                try:
                    df = pd.read_excel(uploaded_file)
                    new_data = []
                    for i in range(min(11, len(df))):
                        row_data = {"ID": f"Cell {i+1}"}
                        for ag in antigens_order:
                            found = 0
                            for col in df.columns:
                                if str(col).strip() == ag:
                                    val = df.iloc[i][col]
                                    if val==1 or val=='+' or str(val).lower()=='pos': found=1
                            row_data[ag] = found
                        new_data.append(row_data)
                    st.session_state.panel_11 = pd.DataFrame(new_data)
                    st.success("Excel Loaded!")
                except Exception as e:
                    st.error("Error reading file.")
            
            # --- MANUAL EDITOR ---
            st.caption("Or Edit Manually:")
            st.session_state.panel_11 = st.data_editor(st.session_state.panel_11, hide_index=True)

    st.markdown("---")
    if st.button("🗑️ Clear Extra Cells"):
        st.session_state.extra_cells = []
        st.rerun()

# ==========================================
# 4. MAIN INTERFACE
# ==========================================
st.markdown("""
<div class='hospital-header'>
    <h1>Maternity & Children Hospital - Tabuk</h1>
    <h4>Blood Bank Serology | Advanced Workstation</h4>
</div>
""", unsafe_allow_html=True)

# Patient
c1, c2, c3, c4 = st.columns(4)
p_name = c1.text_input("Patient Name")
p_mrn = c2.text_input("MRN / ID")
p_tech = c3.text_input("Performed By")
p_date = c4.date_input("Date", value=date.today())
st.divider()

# Inputs
c_L, c_R = st.columns([1, 2])
with c_L:
    st.subheader("1. Control")
    ac_val = st.radio("Auto Control (AC)", ["Negative", "Positive"], horizontal=True)
    if ac_val == "Positive":
        st.error("🚨 STOP. AC Positive.")
        st.info("Possible WAIHA, CAS or Delayed Reaction.")
        st.stop()
    st.write("---")
    st.caption("Quick Tools:")
    b1, b2 = st.columns(2)
    if b1.button("All Neg"): bulk_set("Neg")
    if b2.button("All Pos"): bulk_set("2+")

with c_R:
    st.subheader("2. Panel Reactions")
    grid = st.columns(6)
    input_scores_map = {}
    for i in range(1, 12):
        key = f"c{i}"
        val = grid[(i-1)%6].selectbox(f"Cell {i}", ["Neg","w+","1+","2+","3+","4+"], key=key, index=["Neg","w+","1+","2+","3+","4+"].index(st.session_state.inputs[key]))
        st.session_state.inputs[key] = val
        score = 0 if val=="Neg" else int(val[0]) if val[0].isdigit() else 0.5
        input_scores_map[i] = score

# ==========================================
# 5. LIVE ANALYSIS
# ==========================================
st.divider()
if st.checkbox("🔴 Run Analysis"):
    
    # Logic: Exclusion
    p_rows = [st.session_state.panel_11.iloc[i].to_dict() for i in range(11)]
    ruled_out = set()
    for ag in antigens_order:
        for idx, score in input_scores_map.items():
            if score == 0:
                if can_rule_out(ag, p_rows[idx-1]): ruled_out.add(ag)
                
    candidates = [a for a in antigens_order if a not in ruled_out]
    
    # Inclusion
    matches = []
    for cand in candidates:
        mismatch = False
        for idx, score in input_scores_map.items():
            if score > 0 and p_rows[idx-1].get(cand,0) == 0: mismatch = True
        if not mismatch: matches.append(cand)

    # Status & Probability
    st.subheader("3. Investigation Status")
    if not matches:
        st.error("❌ Inconclusive Pattern.")
        allow_print = False
    else:
        allow_print = True
        for ab in matches:
            passed, p_pos, p_neg, method = check_rule_of_three(ab, p_rows, input_scores_map, st.session_state.extra_cells)
            
            if passed:
                st.markdown(f"<div class='status-pass'>✅ <b>Anti-{ab}: Confirmed ({method}).</b> Stats: {p_pos} Pos / {p_neg} Neg. (p ≤ 0.05)</div>", unsafe_allow_html=True)
            else:
                allow_print = False
                st.markdown(f"<div class='status-fail'>🛑 <b>Anti-{ab}: RULE NOT MET!</b> Need <b>{3-p_pos if 3-p_pos>0 else 0} Pos</b> / <b>{3-p_neg if 3-p_neg>0 else 0} Neg</b> cells more.</div>", unsafe_allow_html=True)

        # Helper
        if not allow_print:
            st.markdown("### ➕ Add Selected Cells")
            with st.container(border=True):
                c_n1, c_n2, c_n3, c_n4 = st.columns(4)
                new_id = c_n1.text_input("Cell ID")
                new_res = c_n2.selectbox("Result", ["Neg","1+","2+"])
                # Smart Checkbox for detected antibodies only
                col3_t = c_n3.empty()
                temp_pheno = {}
                for m in matches:
                     val = col3_t.radio(f"{m} Antigen?", ["Pos", "Neg"], key=f"r_{m}")
                     temp_pheno[m] = 1 if val=="Pos" else 0
                
                if c_n4.button("Add Cell"):
                     if new_id:
                         st.session_state.extra_cells.append({"src": new_id, "pheno": temp_pheno, "score": 0 if new_res=="Neg" else int(new_res[0]), "res_str": new_res})
                         st.rerun()

            if st.session_state.extra_cells: st.write("Added:", [x['src'] for x in st.session_state.extra_cells])

    # Report
    st.divider()
    if allow_print:
        if st.button("🖨️ Generate Report"):
            xtra_txt = ""
            if st.session_state.extra_cells:
                xtra_txt = "<br><b>Extra Cells Used:</b> " + ", ".join([f"{x['src']}({x['res_str']})" for x in st.session_state.extra_cells])
            
            st.markdown(f"""
            <div class='print-only'>
                <br><div class='hospital-header'><h2>Maternity & Children Hospital - Tabuk</h2><h4>Blood Bank Serology</h4></div>
                <div class='results-box'>
                    <table width="100%"><tr><td><b>Patient:</b> {p_name}</td><td><b>MRN:</b> {p_mrn}</td></tr><tr><td><b>Tech:</b> {p_tech}</td><td><b>Date:</b> {p_date}</td></tr></table>
                    <hr>
                    <p><b>Conclusion:</b> Anti-{', '.join(matches)} Identified.</p>
                    <p><b>Validation:</b> Rule of Three Met (p ≤ 0.05). {xtra_txt}</p>
                    <div style="border:1px solid black; padding:5px;"><b>Note:</b> Phenotype patient for {', '.join(matches)} (Must be Negative).</div>
                    <hr><br><br>
                    <table width="100%"><tr><td><b>Tech Signature:</b> _________</td><td><b>Verified By:</b> _________</td></tr></table>
                    <div class='watermark-print'>V18.1 Pro | Haitham Ismail © 2025</div>
                </div>
            </div>
            <script>window.print();</script>
            """, unsafe_allow_html=True)
            st.balloons()
