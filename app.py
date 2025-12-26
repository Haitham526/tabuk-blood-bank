import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. SETUP & STYLING
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🏥")

st.markdown("""
<style>
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .block-container { padding: 0 !important; }
        .print-only { display: block !important; }
        .results-box { border: 2px solid #333; padding: 15px; font-family: 'Times New Roman'; margin-top: 20px; }
        .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; }
    }
    .hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    
    /* Consultant Signature */
    .signature-badge {
        position: fixed; bottom: 10px; right: 15px; text-align: right;
        font-family: 'Georgia', serif; font-size: 12px; color: #8B0000;
        background-color: rgba(255, 255, 255, 0.95); padding: 8px 15px;
        border-radius: 8px; border: 1px solid #eecaca; box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        z-index: 9999;
    }
    .dr-name { font-weight: bold; font-size: 15px; display: block; margin-bottom: 3px;}
    
    /* Fix for Table Visibility */
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    .status-pass { background-color: #d1e7dd; padding: 10px; border-radius: 5px; color: #0f5132; border-left: 5px solid #198754; margin-bottom:5px; }
    .status-fail { background-color: #f8d7da; padding: 10px; border-radius: 5px; color: #842029; border-left: 5px solid #dc3545; margin-bottom:5px; }
</style>
""", unsafe_allow_html=True)

# Footer Signature
st.markdown("""
<div class='signature-badge no-print'>
    <span class='dr-name'>Dr. Haitham Ismail</span>
    Clinical Hematology/Oncology & Transfusion Medicine Consultant
</div>
""", unsafe_allow_html=True)

# --- DEFINITIONS ---
antigens_order = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
ANTIGEN_ALIASES = { "D": ["D", "Rh(D)", "RH1"], "C": ["C", "rh'", "RH2"], "E": ["E", "rh''", "RH3"], "c": ["c", "hr'", "RH4"], "e": ["e", "hr''", "RH5"], "Fya": ["Fya", "Fy(a)"], "Fyb": ["Fyb", "Fy(b)"], "Jka": ["Jka", "Jk(a)"], "Jkb": ["Jkb", "Jk(b)"], "Lea": ["Lea", "Le(a)"], "Leb": ["Leb", "Le(b)"], "P1": ["P1", "P"], "M": ["M", "MN"], "N": ["N"], "S": ["S"], "s": ["s"] }
allele_pairs = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Kpa':'Kpb', 'Kpb':'Kpa', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S', 'Lea':'Leb', 'Leb':'Lea'}
STRICT_DOSAGE_SYSTEMS = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]

# --- INITIAL STATE ---
if 'panel_11' not in st.session_state:
    st.session_state.panel_11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in antigens_order}} for i in range(11)])
if 'panel_3' not in st.session_state:
    st.session_state.panel_3 = pd.DataFrame([{"ID": f"Scn {i}", **{ag: 0 for ag in antigens_order}} for i in ["I", "II", "III"]])
if 'inputs' not in st.session_state: st.session_state.inputs = {f"c{i}": "Neg" for i in range(1, 12)}
if 'inputs_screen' not in st.session_state: st.session_state.inputs_screen = {f"s{i}": "Neg" for i in ["I", "II", "III"]}
if 'extra_cells' not in st.session_state: st.session_state.extra_cells = []
if 'admin_mode' not in st.session_state: st.session_state.admin_mode = False

# ==========================================
# 2. LOGIC HELPERS
# ==========================================
def find_column_in_df(df, target_ag):
    for col in df.columns:
        if str(col).strip().upper() == target_ag.upper(): return col
    aliases = ANTIGEN_ALIASES.get(target_ag, [])
    for alias in aliases:
        for col in df.columns:
            # Flexible Match (remove parenthesis and spaces)
            clean_col = str(col).replace("(","").replace(")","").replace(" ","").upper()
            clean_alias = str(alias).replace("(","").replace(")","").replace(" ","").upper()
            if clean_col == clean_alias: return col
    return None

def normalize_val(val):
    v_str = str(val).lower().strip()
    return 1 if v_str in ['+','1','pos','yes', '1.0'] else 0

def can_rule_out(ag, pheno):
    if pheno.get(ag,0)==0: return False
    if ag in STRICT_DOSAGE_SYSTEMS:
        pair = allele_pairs.get(ag)
        if pair and pheno.get(pair,0)==1: return False
    return True

def check_rule(cand, rows11, inputs11, rows3, inputs3, extra):
    pos_r, neg_r = 0, 0
    # Panel
    for i in range(1,12):
        score = 1 if inputs11[i]!="Neg" else 0
        has = rows11[i-1].get(cand,0)
        if has==1 and score==1: pos_r+=1
        if has==0 and score==0: neg_r+=1
    # Screen
    scr_ids = ["I", "II", "III"]
    for i, sid in enumerate(scr_ids):
        score = 1 if inputs3[sid]!="Neg" else 0
        has = rows3[i].get(cand,0)
        if has==1 and score==1: pos_r+=1
        if has==0 and score==0: neg_r+=1
    # Extra
    for c in extra:
        score = c['score']
        has = c['pheno'].get(cand,0)
        if has==1 and score==1: pos_r+=1
        if has==0 and score==0: neg_r+=1
        
    passed = (pos_r>=3 and neg_r>=3) or (pos_r>=2 and neg_r>=3)
    method = "Standard" if (pos_r>=3 and neg_r>=3) else ("Modified" if passed else "Failed")
    return passed, pos_r, neg_r, method

def bulk_set(val):
    for i in range(1, 12): st.session_state.inputs[f"c{i}"] = val

# ==========================================
# 3. SIDEBAR (Login Only)
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=50)
    st.caption("Ver 20.1 Fixed")
    if st.checkbox("Supervisor Config"):
        if st.text_input("Password", type="password") == "admin123":
            st.session_state.admin_mode = True
            st.success("✅ Logged In")
        else:
            st.session_state.admin_mode = False
            st.error("Incorrect")
    else:
        st.session_state.admin_mode = False

# ==========================================
# 4. VIEW LOGIC (Admin vs User)
# ==========================================

if st.session_state.admin_mode:
    # --- ADMIN VIEW ---
    st.title("🛠️ Master Configuration (Admin)")
    st.warning("Ensure the Excel file headers match: D, C, E, c, e, K, k...")
    
    t_main, t_scr = st.tabs(["Main Panel (11)", "Screen Panel (3)"])
    
    with t_main:
        c_up, c_show = st.columns([1, 2])
        with c_up:
            up = st.file_uploader("Upload Panel (.xlsx)", type=["xlsx"])
            if up:
                try:
                    df_in = pd.read_excel(up)
                    # Show preview of columns found for debugging
                    st.caption(f"Columns Found: {list(df_in.columns)[:5]}...")
                    
                    mapped_data = []
                    found_count = 0
                    for i in range(min(11, len(df_in))):
                        row_dict = {"ID": f"Cell {i+1}"}
                        for ag in antigens_order:
                            c_name = find_column_in_df(df_in, ag)
                            val = 0
                            if c_name:
                                val = normalize_val(df_in.iloc[i][c_name])
                                if i==0: found_count+=1
                            row_dict[ag] = val
                        mapped_data.append(row_dict)
                    
                    st.session_state.panel_11 = pd.DataFrame(mapped_data)
                    st.success(f"Updated! Matched {found_count}/{len(antigens_order)} antigens.")
                    if found_count < 5: st.error("⚠️ Warning: Most columns not found. Check Excel headers.")
                    
                except Exception as e: st.error(f"Error: {e}")
                
        with c_show:
            st.write("### Review Panel Data")
            # Force Re-render using key
            st.session_state.panel_11 = st.data_editor(
                st.session_state.panel_11, 
                key="editor_11", 
                hide_index=True, 
                use_container_width=True, 
                height=450
            )

    with t_scr:
        st.write("Edit Screening Cells:")
        st.session_state.panel_3 = st.data_editor(
            st.session_state.panel_3, 
            key="editor_3",
            hide_index=True, 
            use_container_width=True
        )

else:
    # --- USER WORKSTATION ---
    st.markdown("""<div class='hospital-header'><h1>Maternity & Children Hospital - Tabuk</h1><h4>Blood Bank Serology</h4></div>""", unsafe_allow_html=True)
    
    # 1. Info
    cc1, cc2, cc3, cc4 = st.columns(4)
    pname=cc1.text_input("Name"); pmrn=cc2.text_input("MRN"); ptech=cc3.text_input("Tech"); pdate=cc4.date_input("Date")
    st.divider()
    
    # 2. Entry
    col_A, col_B = st.columns([1, 2])
    with col_A:
        st.subheader("1. Screen/Ctl")
        for x in ["I","II","III"]:
            key=f"s{x}"
            st.session_state.inputs_screen[key] = st.selectbox(f"Scn {x}", ["Neg","w+","1+","2+","3+","4+"], key=f"k_{x}")
        st.write("---")
        ac_res = st.radio("AC", ["Negative","Positive"])
        if ac_res == "Positive": st.error("DAT Required."); st.stop()
        
        st.write("---")
        if st.button("Set Neg"): bulk_set("Neg")
        if st.button("Set Pos"): bulk_set("2+")

    with col_B:
        st.subheader("2. ID Panel")
        grd = st.columns(6)
        pan_scores = {}
        for i in range(1,12):
            k=f"c{i}"
            v=grd[(i-1)%6].selectbox(f"C{i}", ["Neg","w+","1+","2+","3+","4+"], key=f"kv_{i}", index=["Neg","w+","1+","2+","3+","4+"].index(st.session_state.inputs[k]))
            st.session_state.inputs[k] = v
            pan_scores[i] = 0 if v=="Neg" else 1 # Simplified for logic check
            
    # 3. Logic & Print
    st.divider()
    if st.checkbox("🔍 Analyze"):
        rows11 = [st.session_state.panel_11.iloc[i].to_dict() for i in range(11)]
        rows3  = [st.session_state.panel_3.iloc[i].to_dict() for i in range(3)]
        
        # Rule out
        ruled_out = set()
        
        # From Panel
        for ag in antigens_order:
            for idx, sc in pan_scores.items():
                if sc == 0:
                    if can_rule_out(ag, rows11[idx-1]):
                        ruled_out.add(ag); break
        
        # From Screen
        sc_map = {"I":0, "II":1, "III":2}
        for k, v in st.session_state.inputs_screen.items():
            sc_val = 0 if v=="Neg" else 1
            if sc_val == 0:
                s_idx = sc_map[k[1:]]
                for ag in antigens_order:
                    if ag not in ruled_out:
                        if can_rule_out(ag, rows3[s_idx]): ruled_out.add(ag)

        cands = [x for x in antigens_order if x not in ruled_out]
        
        # Match (Inclusive)
        final_match = []
        for c in cands:
            mis = False
            for idx, sc in pan_scores.items():
                if sc>0 and rows11[idx-1].get(c,0)==0: mis=True
            if not mis: final_match.append(c)
            
        if not final_match:
            st.error("Inconclusive.")
        else:
            allow = True
            for m in final_match:
                ok, p, n, meth = check_rule(m, rows11, st.session_state.inputs, rows3, st.session_state.inputs_screen, st.session_state.extra_cells)
                st.markdown(f"<div class='status-{'pass' if ok else 'fail'}'><b>Anti-{m}:</b> {meth} ({p}/{n})</div>", unsafe_allow_html=True)
                if not ok: allow=False
            
            if allow:
                if st.button("🖨️ Print Final Report"):
                    rpt_html = f"""
