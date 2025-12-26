import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. SETUP & CONFIG
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
    
    .signature-badge {
        position: fixed; bottom: 10px; right: 15px;
        font-family: 'Georgia', serif; font-size: 12px; color: #8B0000;
        background: rgba(255,255,255,0.95); padding: 5px 10px; border: 1px solid #eecaca; border-radius: 5px; z-index:99;
    }
    
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    .status-pass { background-color: #d1e7dd; padding: 10px; border-radius: 5px; color: #0f5132; border-left: 5px solid #198754; margin-bottom:5px; }
    .status-fail { background-color: #f8d7da; padding: 10px; border-radius: 5px; color: #842029; border-left: 5px solid #dc3545; margin-bottom:5px; }
</style>
""", unsafe_allow_html=True)

# Footer
st.markdown("<div class='signature-badge no-print'><b>Dr. Haitham Ismail</b><br>Clinical Hematology/Transfusion Consultant</div>", unsafe_allow_html=True)

# Antigen Logic
antigens_order = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
allele_pairs = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S'}
STRICT_DOSAGE = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]

# Initial State
if 'panel_11' not in st.session_state:
    st.session_state.panel_11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in antigens_order}} for i in range(11)])
if 'panel_3' not in st.session_state:
    st.session_state.panel_3 = pd.DataFrame([{"ID": f"Scn {i}", **{ag: 0 for ag in antigens_order}} for i in ["I","II","III"]])
if 'inputs' not in st.session_state: st.session_state.inputs = {f"c{i}": "Neg" for i in range(1,12)}
if 'inputs_s' not in st.session_state: st.session_state.inputs_s = {f"s{i}": "Neg" for i in ["I","II","III"]}
if 'extra' not in st.session_state: st.session_state.extra = []
if 'admin_mode' not in st.session_state: st.session_state.admin_mode = False

# ==========================================
# 2. THE INTELLIGENT PARSER (MAGIC FIX)
# ==========================================
def smart_parse_excel(file_upload):
    """
    يبحث عن السطر الذي يحتوي على العناوين الصحيحة
    ثم يستخرج البيانات التي تليه
    """
    # 1. Read file as is (headerless initially to scan)
    df_scan = pd.read_excel(file_upload, header=None)
    
    start_row_index = -1
    header_row = []
    
    # 2. SCAN loop: Look for a row that contains 'D' AND 'C' AND 'c'
    # عادة في ملفك هو الصف رقم 2 (index 1)
    for i in range(min(5, len(df_scan))):
        row_values = [str(x).strip() for x in df_scan.iloc[i].values]
        # Check intersection with our targets
        matches = 0
        if "D" in row_values: matches += 1
        if "C" in row_values: matches += 1
        if "e" in row_values: matches += 1
        
        if matches >= 3: # Found the header!
            start_row_index = i
            header_row = row_values
            break
            
    if start_row_index == -1:
        raise ValueError("Couldn't find the header row (D, C, e...). Try removing the top rows.")

    # 3. Reload dataframe using the correct header row
    # Skip rows before the header, then take next 11 rows
    df_clean = pd.read_excel(file_upload, header=start_row_index)
    
    # 4. MAP COLUMNS
    final_data = []
    # Loop over next 11 rows
    count = 0
    for idx, row in df_clean.iterrows():
        if count >= 11: break
        
        cell_dict = {"ID": f"Cell {count+1}"}
        
        for ag in antigens_order:
            val = 0
            # Try finding column
            found_col = None
            if ag in row: 
                found_col = ag
            else:
                # Fuzzy Search in columns
                for c in df_clean.columns:
                    if str(c).strip() == ag: found_col = c; break
            
            if found_col:
                raw_val = str(row[found_col]).lower().strip()
                # ---------------- CRITICAL FIX FOR YOUR FILE ----------------
                # Handles: "+", "+w", "1" -> 1
                # Handles: "0", "nt", "nan" -> 0
                if '+' in raw_val or '1' in raw_val: val = 1
                elif 'w' in raw_val and '+' in raw_val: val = 1 # Case: +w
                else: val = 0
                # -----------------------------------------------------------
            
            cell_dict[ag] = int(val)
        
        final_data.append(cell_dict)
        count += 1
        
    return pd.DataFrame(final_data)

# Logic Helpers
def can_rule_out(ag, pheno):
    if pheno.get(ag,0)==0: return False
    if ag in STRICT_DOSAGE:
        p = allele_pairs.get(ag)
        if p and pheno.get(p,0)==1: return False
    return True

def bulk(v):
    for i in range(1,12): st.session_state.inputs[f"c{i}"]=v

def check_r3(cand, rows, inpts, r3, in3, ex):
    pr, nr = 0, 0
    # Panel
    for i in range(1,12):
        s = 1 if inpts[i]!="Neg" else 0
        h = rows[i-1].get(cand,0)
        if h==1 and s==1: pr+=1
        if h==0 and s==0: nr+=1
    # Screen
    scrs=["I","II","III"]
    for i, sid in enumerate(scrs):
        s = 1 if in3[f"s{sid}"]!="Neg" else 0
        h = r3[i].get(cand,0)
        if h==1 and s==1: pr+=1
        if h==0 and s==0: nr+=1
    # Extra
    for c in ex:
        if c['s']==1 and c['p'].get(cand,0)==1: pr+=1
        if c['s']==0 and c['p'].get(cand,0)==0: nr+=1
    
    pas = (pr>=3 and nr>=3) or (pr>=2 and nr>=3)
    mt = "Standard (3/3)" if (pr>=3 and nr>=3) else ("Modified (2/3)" if pas else "Failed")
    return pas, pr, nr, mt

# ==========================================
# 3. SIDEBAR
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    st.caption("V23.0 Smart Row Search")
    app_mode = st.radio("Navigation", ["User Workstation", "Supervisor Config"])
    st.write("--
