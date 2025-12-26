import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. SETUP
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🏥")

st.markdown("""
<style>
    /* Print & Header */
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .block-container { padding: 0 !important; }
        .print-only { display: block !important; }
        .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; }
        .results-box { border: 2px solid #333; padding: 15px; font-family: 'Times New Roman'; margin-top: 20px; }
    }
    .hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    
    /* Footer */
    .signature-badge {
        position: fixed; bottom: 10px; right: 15px; text-align: right;
        font-family: 'Georgia', serif; font-size: 12px; color: #8B0000;
        background-color: rgba(255, 255, 255, 0.95); padding: 8px 15px;
        border-radius: 8px; border: 1px solid #eecaca; z-index: 9999;
    }
    .dr-name { font-weight: bold; font-size: 15px; display: block; margin-bottom: 3px;}
    
    /* Colors */
    .status-pass { background-color: #d1e7dd; padding: 10px; border-radius: 5px; color: #0f5132; border-left: 5px solid #198754; margin-bottom:5px; }
    .status-fail { background-color: #f8d7da; padding: 10px; border-radius: 5px; color: #842029; border-left: 5px solid #dc3545; margin-bottom:5px; }
</style>
""", unsafe_allow_html=True)

# Footer
st.markdown("""<div class='signature-badge no-print'><span class='dr-name'>Dr. Haitham Ismail</span>Clinical Hematology/Oncology & Transfusion Medicine Consultant</div>""", unsafe_allow_html=True)

# Defs
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

# ==========================================
# 2. LOGIC
# ==========================================
def find_column_in_df(df, target_ag):
    for col in df.columns:
        if str(col).strip() == target_ag: return col
    aliases = ANTIGEN_ALIASES.get(target_ag, [])
    for alias in aliases:
        for col in df.columns:
            clean_c = str(col).replace("(","").replace(")","").replace(" ","").upper()
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
