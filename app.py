import streamlit as st
import pandas as pd
import io

# ==========================================
# 1. SETUP
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🩸")

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
def normalize_val(val):
    s = str(val).lower().strip()
    if '+' in s or '1' in s or 'pos' in s: return 1
    return 0

# --- THE SMART HUNTER PARSER ---
def hunter_parser(file_bytes):
    # 1. Read file as is (header=None allows us to see everything)
    df = pd.read_excel(file_bytes, header=None)
    
    # Store where we found each antigen (Row Index, Col Index)
    # Example: 'D': (2, 5) -> Row 2, Col 5
    antigen_coords = {}
    
    # Scan the first 20 rows
    max_scan_row = min(20, len(df))
    
    for r_idx in range(max_scan_row):
        for c_idx in range(len(df.columns)):
            cell_val = str(df.iloc[r_idx, c_idx]).strip()
            # Cleanup text (remove parenthesis, spaces, newlines)
            clean_val = cell_val.replace("(", "").replace(")", "").replace("\n", "").replace(" ", "")
            
            # Special Checks based on Bio-Rad PDF output style
            detected_ag = None
            
            # Check Exact Match or Close Match
            if clean_val in antigens_order:
                detected_ag = clean_val
            elif clean_val == "RhD": detected_ag = "D"
            elif clean_val == "Fyab": continue # Avoid titles
            elif clean_val.upper() == "KELL": continue
            
            # If found an antigen name, SAVE ITS LOCATION
            if detected_ag:
                # We overwrite if found again? No, take the first valid header occurrence
                if detected_ag not in antigen_coords:
                    antigen_coords[detected_ag] = (r_idx, c_idx)

    # Validate findings
    if len(antigen_coords) < 5:
        return None, f"Found only {len(antigen_coords)} antigen headers. File format unreadable."

    # 2. Determine where data starts
    # Usually data starts 1 row AFTER the header
    # But headers might be on different rows? Let's assume most frequent row is the main header row
    rows_found = [pos[0] for pos in antigen_coords.values()]
    # Mode of rows
    header_row_consensus = max(set(rows_found), key=rows_found.count)
    data_start_row = header_row_consensus + 1
    
    # 3. EXTRACT DATA
    final_data = []
    current_row = data_start_row
    cells_extracted = 0
    
    # We want 11 cells. We will loop until we get 11 or run out of rows
    while cells_extracted < 11 and current_row < len(df):
        
        # Determine if this row is valid data (look for numbers/+/0)
        # Check 'D' column value
        if "D" in antigen_coords:
            d_col = antigen_coords["D"][1]
            test_val = str(df.iloc[current_row, d_col])
            # If empty row, skip
            if test_val.strip() == "" or test_val.lower() == "nan": 
                current_row += 1
                continue
                
        cell_dict = {"ID": f"Cell {cells_extracted+1}"}
        
        for ag in antigens_order:
