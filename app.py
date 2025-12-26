import streamlit as st
import pandas as pd
import io

# ==========================================
# 1. SETUP
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
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    
    .signature-badge {
        position: fixed; bottom: 10px; right: 15px; font-family: 'Georgia', serif; font-size: 12px; color: #8B0000;
        background: rgba(255,255,255,0.95); padding: 5px 10px; border: 1px solid #eecaca; border-radius: 5px; z-index:99;
    }
</style>
""", unsafe_allow_html=True)

# Footer
st.markdown("<div class='signature-badge no-print'><b>Dr. Haitham Ismail</b><br>Clinical Hematology/Transfusion Consultant</div>", unsafe_allow_html=True)

# DEFINITIONS
antigens_order = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
allele_pairs = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S'}
STRICT_DOSAGE = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]

# STATES
if 'panel_11' not in st.session_state:
    st.session_state.panel_11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in antigens_order}} for i in range(11)])
if 'inputs' not in st.session_state: st.session_state.inputs = {f"c{i}": "Neg" for i in range(1, 12)}
if 'inputs_s' not in st.session_state: st.session_state.inputs_s = {f"s{i}": "Neg" for i in ["I","II","III"]}
if 'extra' not in st.session_state: st.session_state.extra = []
if 'admin_mode' not in st.session_state: st.session_state.admin_mode = False

# ==========================================
# 2. LOGIC FUNCTIONS
# ==========================================
def normalize_cell_value(val):
    s = str(val).lower().strip()
    # Logic: 1, +, +w, pos, yes -> 1
    # Logic: 0, nt, -, neg -> 0
    if '+' in s or '1' in s or 'pos' in s: return 1
    return 0

def deep_search_parser(file_bytes):
    # 1. Read entire file without header assumption
    df = pd.read_excel(file_bytes, header=None)
    
    header_idx = -1
    col_map = {} # {'D': 5, 'C': 6...} mapping antigen to column index
    
    # 2. Iterate first 20 rows to find a "signature"
    # We look for a row that contains multiple antigens
    for idx, row in df.iterrows():
        row_str = [str(x).strip() for x in row.values]
        
        # Clean checking
        matches = 0
        current_map = {}
        
        for col_i, cell_val in enumerate(row_str):
            c
