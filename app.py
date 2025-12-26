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
        valid_row = False
        
        # We fill values based on mapped columns
        for ag in antigens_order:
            val = 0
            if ag in ag_col_map:
                c_idx = ag_col_map[ag]
                cell_content = str(df.iloc[curr, c_idx]).lower().strip()
                
                # Intelligent Value Parser
                if cell_content in ['+', '1', 'pos', 'yes']: val = 1
                elif '+w' in cell_content: val = 1  # YOUR FILE CASE
                elif 'w' in cell_content: val = 1
                
                # Check if this row actually has data (not empty line)
                if cell_content not in ['nan', '', 'none']: valid_row = True
                
            row_dict[ag] = val
            
        if valid_row:
            final_data.append(row_dict)
            count += 1
            
        curr += 1
        
    # If successful, return new DF
    if len(final_data) > 0:
        return pd.DataFrame(final_data), None
    else:
        return None, "Found headers but no data rows underneath."

# Helper Logic
def can_rule_out(ag, pheno):
    if pheno.get(ag,0)==0: return False
    if ag in STRICT_DOSAGE:
        p=allele_pairs.get(ag)
        if p and pheno.get(p,0)==1: return False
    return True

def bulk(v): 
    for i in range(1,12): st.session_state.inputs[f"c{i}"]=v

def check_r3(cand, rows, inpts, r3, in3, ex):
    pr,nr=0,0
    for i in range(1,12):
        s=1 if inpts[i]!="Neg" else 0
        h=rows[i-1].get(cand,0)
        if h==1 and s==1: pr+=1
        if h==0 and s==0: nr+=1
    for i,s in enumerate(["I","II","III"]):
        sc=1 if in3[f"s{s}"]!="Neg" else 0
        h=r3[i].get(cand,0)
        if h==1 and sc==1: pr+=1
        if h==0 and sc==0: nr+=1
    for c in ex:
        if c['s']==1 and c['p'].get(cand,0)==1: pr+=1
        if c['s']==0 and c['p'].get(cand,0)==0: nr+=1
    res = (pr>=3 and nr>=3) or (pr>=2 and nr>=3)
    mt="Standard" if (pr>=3 and nr>=3) else ("Modified" if res else "Fail")
    return res,pr,nr,mt

# ==========================================
# 3. SIDEBAR & MENU
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    st.caption("V25.0 Matrix Mapper")
    menu = st.radio("Navigation", ["User Workstation", "Supervisor Config"])
    st.write("---")
    if st.button("Reset All Extra Cells"):
        st.session_state.extra = []
        st.rerun()

# ---------------- ADMIN ----------------
if menu == "Supervisor Config":
    st.title("🛠️ Master Configuration (Matrix Engine)")
    pwd = st.text_input("Enter Admin Password", type="password")
    
    if pwd == "admin123":
        t1, t2 = st.tabs(["Panel 11 Setup", "Screening Setup"])
        
        with t1:
            st.info("ℹ️ Upload the PDF-converted Excel directly. The Matrix Mapper will find data even if columns are merged or shifted.")
            up = st.file_uploader("Upload Excel File", type=["xlsx", "xls"])
            
            if up:
                try:
                    bytes_data = up.getvalue()
                    
                    # RUN MATRIX MAPPER
                    df_new, err = matrix_parser(io.BytesIO(bytes_data))
                    
                    if df_new is not None:
                        count = df_new.shape[1] - 1
                        st.success(f"✅ Success! Extracted {count} Antigens.")
                        st.session_state.panel_11 = df_new
                        st.caption("Data loaded. Check grid below. If something is 0 but should be 1, edit it manually.")
                        if st.button("🔄 Refresh Grid"): st.rerun()
                    else:
                        st.error(f"⚠️ Detection Error: {err}")
                        with st.expander("Debug Raw File"):
                            st.write("Python sees this raw data:")
                            st.dataframe(pd.read_excel(io.BytesIO(bytes_data), header=None).head(15))
                            
                except Exception as e:
                    st.error(f"Fatal Error: {e}")

            st.write("#### Master Data Grid (Live Edit):")
            safe_df = st.session_state.panel_11.fillna(0)
            
            edited = st.data_editor(
                safe_df, 
                height=450, 
                use_container_width=True, 
                hide_index=True
            )
            if st.button("Save Manual Edits"):
                st.session_state.panel_11 = edited
                st.success("Saved.")

        with t2:
            st.write("Configure Screening Cells:")
            st.session_state.panel_3 = st.data_editor(st.session_state.panel_3, hide_index=True)
            
    elif pwd: st.error("Wrong Password")

# ---------------- USER ----------------
else:
    st.markdown("""<div class='hospital-header'><h1>Maternity & Children Hospital - Tabuk</h1><h4>Serology Workstation</h4></div>""", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mrn=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    L,R=st.columns([1,2])
    with L:
        st.subheader("1. Screen/Control")
        ac=st.radio("AC", ["Negative","Positive"])
        if ac=="Positive": st.error("DAT Required."); st.stop()
        for x in ["I","II","III"]:
            k=f"s{x}"
            st.session_state.inputs_s[k]=st.selectbox(x,["Neg","w+","1+","2+"],key=f"u_{x}")
        if st.button("Set Neg"): bulk("Neg")
        if st.button("Set Pos"): bulk("2+")
    
    with R:
        st.subheader("2. Panel")
        mp={}
        cols=st.columns(6)
        for i in range(1,12):
            k=f"c{i}"
            v=cols[(i-1)%6].selectbox(f"C{i}",["Neg","w+","1+","2+","3+"],key=f"p_{i}",index=["Neg","w+","1+","2+","3+"].index(st.session_state.inputs[k]))
            st.session_state.inputs[k]=v
            mp[i]=0 if v=="Neg" else 1
            
    st.divider()
    if st.checkbox("🔍 Analyze"):
        r11=[st.session_state.panel_11.iloc[i].to_dict() for i in range(11)]
        r3=[st.session_state.panel_3.iloc[i].to_dict() for i in range(3)]
        ruled=set()
        
        # Exclusion
        for ag in antigens_order:
            for idx,sc in mp.items():
                if sc==0 and
