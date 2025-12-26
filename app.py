import streamlit as st
import pandas as pd
import io
from datetime import date

# 1. BASE CONFIG
st.set_page_config(page_title="Tabuk Blood Bank", layout="wide")

# CSS لإصلاح عرض الجدول
st.markdown("""
<style>
    .stApp > header {display:none;}
    .block-container {padding-top: 1rem;}
    div[data-testid="stDataEditor"] table {width: 100% !important;}
    @media print {.no-print, .sidebar {display:none;}}
</style>
""", unsafe_allow_html=True)

# definitions
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# STATE initialization
if 'p11' not in st.session_state:
    # Initialize with clean Integers (0) not float/object
    st.session_state.p11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{a:0 for a in AGS}} for i in range(11)]).astype(object)
    
if 'inputs' not in st.session_state: st.session_state.inputs = {i:"Neg" for i in range(1,12)}
if 'extra' not in st.session_state: st.session_state.extra = []

# --- PARSER ENGINE (The One that Worked) ---
def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+','1','pos','w']) else 0

def extract_excel_matrix(file):
    try:
        xls = pd.ExcelFile(file)
        # Search all sheets
        for sheet in xls.sheet_names:
            df = pd.read_excel(file, sheet_name=sheet, header=None)
            
            # Search Grid for Headers
            col_map = {}
            found_header = -1
            
            for r in range(min(30, len(df))):
                row_matches = 0
                temp_map = {}
                for c in range(min(60, len(df.columns))):
                    # Clean Cell Value
                    val = str(df.iloc[r, c]).strip().replace(" ","")
                    det = None
                    
                    # Logic to catch antigens (Case sensitive mostly kept, or Upper map)
                    # Checking common ones
                    v_up = val.upper()
                    if v_up in AGS: 
                        det = v_up # Map back to case if needed? For now lets grab index
                    elif v_up == "RHD" or v_up=="D": det="D"
                    elif val == "c": det="c"
                    elif val == "C": det="C"
                    
                    if det:
                        # Fix Case back to Standard AGS list
                        for standard_ag in AGS:
                            if standard_ag.upper() == det: det = standard_ag; break
                        
                        temp_map[det] = c
                        row_matches += 1
                        
                if row_matches >= 3:
                    found_header = r
                    col_map = temp_map
                    break # Header found
            
            # If Header Found -> Extract Data
            if found_header != -1:
                final_data = []
                extracted_count = 0
                curr_row = found_header + 1
                
                while extracted_count < 11 and curr_row < len(df):
                    # Validate Row by checking D column for data presence
                    is_valid = False
                    d_col = col_map.get("D") or col_map.get("C")
                    if d_col is not None:
                        chk = str(df.iloc[curr_row, d_col]).lower()
                        if any(k in chk for k in ['0','1','+','w']): is_valid=True
                        
                    if is_valid:
                        row_dic = {"ID": f"Cell {extracted_count+1}"}
                        for ag in AGS:
                            v = 0
                            if ag in col_map:
                                v = normalize(df.iloc[curr_row, col_map[ag]])
                            row_dic[ag] = int(v) # FORCE INT
                        final_data.append(row_dic)
                        extracted_count += 1
                    curr_row += 1
                
                if extracted_count >= 1:
                    return pd.DataFrame(final_data), f"Read OK from {sheet}"
                    
        return None, "Structure Not Found"
        
    except Exception as e: return None, str(e)

# Logic helpers
def rule_out(ph, negs):
    out = set()
    for ag in AGS:
        # Loop Negative Cells
        for i in negs:
            # i is 1-based index
            cell_p = ph[i-1]
            if cell_p.get(ag,0)==1:
                # Dosage check
                safe_to_rule = True
                if ag in DOSAGE:
                    pr = PAIRS.get(ag)
                    if pr and cell_p.get(pr,0)==1: safe_to_rule=False
                if safe_to_rule: out.add(ag)
    return out

# UI
with st.sidebar:
    st.header("Control")
    mode = st.radio("Menu", ["Workstation", "Supervisor"])
    if st.button("Reset All"): 
        st.session_state.p11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{a:0 for a in AGS}} for i in range(11)])
        st.session_state.extra = []
        st.rerun()

# ----------------- ADMIN -----------------
if mode == "Supervisor":
    st.title("Admin Panel Configuration")
    if st.text_input("Password", type="password")=="admin123":
        
        st.info("Upload File (PDF Converted)")
        up = st.file_uploader("Upload XLSX", type=["xlsx"])
        
        # LOGIC SEPARATION: UPLOAD vs DISPLAY
        if up:
            new_df, msg = extract_excel_matrix(io.BytesIO(up.getvalue()))
            if new_df is not None:
                st.session_state.p11 = new_df
                st.success(msg)
            else:
                st.error(msg)
                
        st.write("---")
        st.write("### Current Active Grid:")
        # This grid reads from Session State DIRECTLY
        # Editing here saves automatically to the "experimental_data_editor" state
        edited_df = st.data_editor(st.session_state.p11, hide_index=True, height=450)
        
        if st.button("Save Grid State"):
            st.session_state.p11 = edited_df
            st.success("Saved!")

# ----------------- USER -----------------
else:
    st.title("MCH Tabuk Workstation")
    
    # Simple Layout
    col_input, col_action = st.columns([2, 1])
    
    with col_input:
        st.write("#### Panel Reactions")
        g = st.columns(6)
        pmap = {}
        for i in range(1, 12):
            k = i
            v = g[(i-1)%6].selectbox(f"C{i}", ["Neg","w+","1+","2+","3+"], key=f"user_{i}", index=0 if st.session_state.inputs.get(i)=="Neg" else 1)
            st.session_state.inputs[i] = v
            pmap[i] = 0 if v=="Neg" else 1
            
    with col_action:
        st.write("#### Control")
        if st.button("All Neg"):
            for i in range(1,12): st.session_state.inputs[i]="Neg"
            st.rerun()
        if st.button("Analyze Now", type="primary"):
            st.session_state.run_analysis = True

    st.divider()
    
    # Analysis Logic Triggered
    if st.session_state.get('run_analysis'):
        # 1. Get Rows
        rows = [st.session_state.p11.iloc[i].to_dict() for i in range(11)]
        neg_cells = [k for k,v in pmap.items() if v==0]
        pos_cells = [k for k,v in pmap.items() if v==1]
        
        # 2. Exclude
        excluded = rule_out(rows, neg_cells)
        
        # 3. Match
        candidates = [a for a in AGS if a not in excluded]
        matches = []
        for c in candidates:
            # Verify positive pattern (Inclusion)
            valid = True
            for pidx in pos_cells:
                if rows[pidx-1].get(c,0)==0: valid=False
            if valid: matches.append(c)
            
        if not matches:
            st.error("No matches found / Inconclusive.")
        else:
            st.success(f"Possibilities: {', '.join(matches)}")
            
            # Simple Rule check for display
            for m in matches:
                p_cnt = sum([1 for p in pos_cells if rows[p-1].get(m,0)==1])
                n_cnt = sum([1 for n in neg_cells if rows[n-1].get(m,0)==0])
                st.write(f"**Anti-{m}:** {p_cnt} Positive Cells / {n_cnt} Negative Cells.")
