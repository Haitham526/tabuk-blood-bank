import streamlit as st
import pandas as pd
import io

# ==========================================
# 1. إعدادات الصفحة
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .block-container { padding: 0 !important; }
        .print-only { display: block !important; }
        .results-box { border: 2px solid #333; padding: 15px; margin-top: 20px; font-family: 'Times New Roman'; }
        .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; }
    }
    .hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    .signature-badge {
        position: fixed; bottom: 10px; right: 15px; font-family: 'Georgia', serif; font-size: 12px; color: #8B0000;
        background: rgba(255,255,255,0.95); padding: 5px 10px; border: 1px solid #eecaca; border-radius: 5px; z-index:99;
    }
    
    /* Styling Logic */
    .status-pass { background-color: #d1e7dd; padding: 10px; border-radius: 5px; color: #0f5132; border-left: 5px solid #198754; margin-bottom:5px; }
    .status-fail { background-color: #f8d7da; padding: 10px; border-radius: 5px; color: #842029; border-left: 5px solid #dc3545; margin-bottom:5px; }
</style>
""", unsafe_allow_html=True)

# Footer
st.markdown("<div class='signature-badge no-print'><b>Dr. Haitham Ismail</b><br>Clinical Hematology/Transfusion Consultant</div>", unsafe_allow_html=True)

# Defs
antigens_order = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
allele_pairs = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S'}
STRICT_DOSAGE = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]

# STATES
if 'panel_11' not in st.session_state:
    st.session_state.panel_11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in antigens_order}} for i in range(11)])
if 'panel_3' not in st.session_state:
    st.session_state.panel_3 = pd.DataFrame([{"ID": f"Scn {i}", **{ag: 0 for ag in antigens_order}} for i in ["I", "II", "III"]])
if 'inputs' not in st.session_state: st.session_state.inputs = {f"c{i}": "Neg" for i in range(1,12)}
if 'inputs_s' not in st.session_state: st.session_state.inputs_s = {f"s{i}": "Neg" for i in ["I","II","III"]}
if 'extra' not in st.session_state: st.session_state.extra = []
if 'admin_mode' not in st.session_state: st.session_state.admin_mode = False

# ==========================================
# 2. THE MATRIX PARSER (THE FINAL FIX)
# ==========================================
def matrix_parser(file_obj):
    # Read WITHOUT header (Raw Matrix)
    df = pd.read_excel(file_obj, header=None)
    
    # 1. MAP ANTIGEN COORDINATES
    # We will search for every antigen name in the first 20 rows and 50 cols
    ag_col_map = {} # {'D': 5, 'C': 8, ...} column index
    header_row_index = -1
    
    max_rows = min(len(df), 20)
    max_cols = min(len(df.columns), 50)
    
    # Cleaning helper
    def clean(tx): 
        return str(tx).replace("(","").replace(")","").replace(" ","").replace("\n","").strip().upper()

    found_count = 0
    
    # SCANNING GRID
    for r in range(max_rows):
        row_found = 0
        for c in range(max_cols):
            val = clean(df.iloc[r, c])
            
            # Map common labels
            detected = None
            if val == "RH1" or val == "RHD" or val == "D": detected = "D"
            elif val == "RH2" or val == "RH'" or val == "C": detected = "C"
            elif val == "RH3" or val == "RH''" or val == "E": detected = "E"
            elif val == "RH4" or val == "HR'" or val == "C": detected = "c" # Note lowercase issue handled by list check usually
            elif val in [x.upper() for x in antigens_order]:
                # Map back to original casing
                idx = [x.upper() for x in antigens_order].index(val)
                detected = antigens_order[idx]
            
            if detected and detected not in ag_col_map:
                ag_col_map[detected] = c
                row_found += 1
        
        if row_found > 3: # If we found more than 3 antigens in this row, it's likely the header row
            if header_row_index == -1: header_row_index = r
            
    if not ag_col_map:
        return None, "No antigens found. File format completely unrecognizable."

    # 2. EXTRACT DATA
    # Data starts after header row
    start_row = header_row_index + 1 if header_row_index != -1 else 0
    
    final_data = []
    # Try to grab 11 valid rows
    count = 0
    curr = start_row
    
    while count < 11 and curr < len(df):
        row_dict = {"ID": f"Cell {count+1}"}
        
        # Check validity of row (look for 'D' value)
        valid_row = Fa
