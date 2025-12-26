import streamlit as st
import pandas as pd
import io
from datetime import date

# 1. SETUP & STYLE
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .block-container { padding: 0 !important; }
        .print-only { display: block !important; }
        .results-box { border: 2px solid #333; padding: 15px; margin-top: 10px; font-family: 'Times New Roman'; }
        .watermark-print { position: fixed; bottom: 0; width: 100%; text-align: center; font-size: 10px; color: #555; }
    }
    .hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    .signature-badge {
        position: fixed; bottom: 10px; right: 15px; font-family: 'Georgia', serif; font-size: 12px; color: #8B0000;
        background: rgba(255,255,255,0.95); padding: 5px 10px; border: 1px solid #eecaca; border-radius: 5px; z-index:99;
    }
    .status-pass { background-color: #d1e7dd; padding: 8px; border-radius: 5px; color: #0f5132; margin-bottom:5px; border-left: 5px solid #198754; }
    .status-fail { background-color: #f8d7da; padding: 8px; border-radius: 5px; color: #842029; margin-bottom:5px; border-left: 5px solid #dc3545; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='signature-badge no-print'><b>Dr. Haitham Ismail</b><br>Clinical Hematology/Transfusion Consultant</div>", unsafe_allow_html=True)

antigens_order = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
allele_pairs = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S', 'Lea':'Leb', 'Leb':'Lea'}
STRICT_DOSAGE = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]

# STATES
if 'panel_11' not in st.session_state:
    st.session_state.panel_11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in antigens_order}} for i in range(11)])
if 'panel_3' not in st.session_state:
    st.session_state.panel_3 = pd.DataFrame([{"ID": f"Scn {i}", **{ag: 0 for ag in antigens_order}} for i in ["I", "II", "III"]])
if 'inputs' not in st.session_state: st.session_state.inputs = {f"c{i}": "Neg" for i in range(1, 12)}
if 'inputs_s' not in st.session_state: st.session_state.inputs_s = {f"s{i}": "Neg" for i in ["I", "II", "III"]}
if 'extra' not in st.session_state: st.session_state.extra = []
if 'admin_mode' not in st.session_state: st.session_state.admin_mode = False

# ==========================================
# 2. THE MULTI-SHEET PARSER (THE SOLUTION)
# ==========================================
def normalize_val(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes']) else 0

def scan_all_sheets(file_bytes):
    # Load workbook metadata
    xls_file = pd.ExcelFile(file_bytes)
    all_sheet_names = xls_file.sheet_names
    
    # Iterate through ALL sheets (Table 1, Table 2, Table 3...)
    for sheet in all_sheet_names:
        
        # Read the sheet
        try:
            df = pd.read_excel(file_bytes, sheet_name=sheet, header=None)
        except:
            continue
            
        # SCAN 1: FIND HEADER ROW
        # Look for a row containing specific keywords like "Rh-hr" or specific antigens
        header_row_index = -1
        col_mapping = {} # {'D': 5, 'C': 6}
        
        max_rows = min(len(df), 20)
        
        for r in range(max_rows):
            # Convert row to list of strings
            row_vals = [str(x).upper().strip().replace(" ","") for x in df.iloc[r].values]
            
            # Check signatures
            matches = 0
            temp_map = {}
            for c_idx, val in enumerate(row_vals):
                found = None
                if val in antigens_order: found = val
                elif val == "RHD" or val == "D": found = "D"
                elif val == "RHC" or val == "C": found = "C"
                elif val == "RHE" or val == "E": found = "E"
                
                if found:
                    matches += 1
                    temp_map[found] = c_idx
            
            # Sensitivity Threshold: If found 4+ antigens, this is the Header Row!
            if matches >= 4:
                header_row_index = r
                col_mapping = temp_map
                # Additional: Search wider in this row for missing antigens
                for c_scan in range(len(df.columns)):
                    v_clean = str(df.iloc[r, c_scan]).strip().replace(" ","")
                    # Try fuzzy
                    if v_clean in antigens_order and v_clean not in col_mapping:
                        col_mapping[v_clean] = c_scan
                break
        
        # If we found headers in this sheet
        if header_row_index != -1 and len(col_mapping) > 3:
            
            # EXTRACT 11 ROWS
            final_data = []
            row_pointer = header_row_index + 1
            extracted_count = 0
            
            while extracted_count < 11 and row_pointer < len(df):
                
                # Check Row Validity (Look at D column)
                d_val = ""
                if "D" in col_mapping:
                    d_col = col_mapping["D"]
                    d_val = str(df.iloc[row_pointer, d_col]).lower()
                elif "C" in col_mapping: # Fallback
                    c_col = col_mapping["C"]
                    d_val = str(df.iloc[row_pointer, c_col]).lower()
                
                # Logic: Is it data? (+, 0, w)
                is_data_row = any(char in d_val for char in ['+', '0', '1', 'w'])
                
                if is_data_row:
                    cell_d = {"ID": f"Cell {extracted_count+1}"}
                    for ag in antigens_order:
                        v = 0
                        if ag in col_mapping:
                            raw = df.iloc[row_pointer, col_mapping[ag]]
                            v = normalize_val(raw)
                        cell_d[ag] = int(v)
                    final_data.append(cell_d)
                    extracted_count += 1
                
                row_pointer += 1
            
            # IF WE EXTRACTED 11 CELLS, RETURN SUCCESS
            if extracted_count >= 11:
                return pd.DataFrame(final_data), f"Success from Sheet: '{sheet}'"

    return None, "Scanned all sheets (Tables), but count not find antigen grid."

# Helpers
def can_rule_out(ag, pheno):
    if pheno.get(ag, 0) == 0: return False
    if ag in STRICT_DOSAGE:
        pair = allele_pairs.get(ag)
        if pair and pheno.get(pair, 0) == 1: return False
    return True

def bulk_set(val):
    for i in range(1, 12): st.session_state.inputs[f"c{i}"] = val

def check_r3(cand, rows, inputs, rows_s, inputs_s, extra):
    pr, nr = 0, 0
    # Panel
    for i in range(1,12):
        s=1 if inputs[i]!="Neg" else 0
        h=rows[i-1].get(cand,0)
        if h==1 and s==1: pr+=1
        if h==0 and s==0: nr+=1
    # Screen
    scs=["I","II","III"]
    for i, s in enumerate(scs):
        sval=1 if inputs_s[f"s{s}"]!="Neg" else 0
        h=rows_s[i].get(cand,0)
        if h==1 and sval==1: pr+=1
        if h==0 and sval==0: nr+=1
    # Extra
    for c in extra:
        s=c['score']
        h=c['pheno'].get(cand,0)
        if h==1 and s==1: pr+=1
        if h==0 and s==0: nr+=1
    
    passed=(pr>=3 and nr>=3) or (pr>=2 and nr>=3)
    method = "Standard (3/3)" if (pr>=3 and nr>=3) else ("Modified (2/3)" if passed else "Fail")
    return passed, pr, nr, method

# ==========================================
# 3. SIDEBAR
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Navigation", ["User Workstation", "Supervisor Config"])
    st.write("---")
    if st.button("Reset Extras"):
        st.session_state.extra=[]
        st.rerun()

# ADMIN
if nav == "Supervisor Config":
    st.title("🛠️ Master Configuration (Multi-Sheet)")
    if st.text_input("Password", type="password") == "admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening"])
        with t1:
            st.info("Upload Excel File (System will scan ALL sheets/tables)")
            up = st.file_uploader("Upload", type=['xlsx'])
            if up:
                new_df, msg = scan_all_sheets(io.BytesIO(up.getvalue()))
                if new_df is not None:
                    st.success(f"✅ Found! {msg}")
                    st.session_state.panel_11 = new_df
                    if st.button("Update Table View"): st.rerun()
                else:
                    st.error(f"❌ Error: {msg}")
            
            st.write("### Grid (Live):")
            edit = st.data_editor(st.session_state.panel_11.fillna(0), height=450, hide_index=True, use_container_width=True)
            if st.button("Save Grid"):
                st.session_state.panel_11=edit
                st.success("Saved.")
        
        with t2:
            st.session_state.panel_3=st.data_editor(st.session_state.panel_3, hide_index=True)

# USER
else:
    st.markdown("""<div class='hospital-header'><h1>Maternity & Children Hospital - Tabuk</h1><h4>Serology Workstation</h4></div>""", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mrn=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    L, R = st.columns([1, 2])
    with L:
        ac = st.radio("AC", ["Negative","Positive"], horizontal=True)
        if ac=="Positive": st.error("STOP: Check DAT."); st.stop()
        for x in ["I","II","III"]: st.session_state.inputs_s[f"s{x}"]=st.selectbox(x,["Neg","Pos"],key=f"u_{x}")
        if st.button("All Neg"): bulk_set("Neg")
    with R:
        cols=st.columns(6)
        in_map={}
        for i in range(1,12):
            k=f"c{i}"
            v=cols[(i-1)%6].selectbox(f"C{i}",["Neg","Pos"],key=f"p_{i}",index=["Neg","Pos"].index(st.session_state.inputs[k]))
            st.session_state.inputs[k]=v
            in_map[i]=0 if v=="Neg" else 1
            
    st.divider()
    if st.checkbox("Analyze"):
        r11=[st.session_state.panel_11.iloc[i].to_dict() for i in range(11)]
        r3=[st.session_state.panel_3.iloc[i].to_dict() for i in range(3)]
        ruled=set()
        for ag in antigens_order:
            for idx, sc in in_map.items():
                if sc==0 and can_rule_out(ag, r11[idx-1]): ruled.add(ag); break
        s_m = {"I":0,"II":1,"III":2}
        for k,v in st.session_state.inputs_s.items():
            if v=="Neg":
                for ag in antigens_order:
                    if ag not in ruled and can_rule_out(ag, r3[s_m[k[1:]]]): ruled.add(ag)
        
        matches=[]
        for cand in [x for x in antigens_order if x not in ruled]:
            mis=False
            for idx,sc in in_map.items():
                if sc>0 and r11[idx-1].get(cand,0)==0: mis=True
            if not mis: matches.append(cand)
            
        if not matches: st.error("Inconclusive")
        else:
            allow=True
            for m in matches:
                pas,p,n,met = check_r3(m,r11,st.session_state.inputs,r3,st.session_state.inputs_s,st.session_state.extra)
                st.markdown(f"<div class='status-{'pass' if pas else 'fail'}'><b>Anti-{m}:</b> {met} ({p} P / {n} N)</div>", unsafe_allow_html=True)
                if not pas: allow=False
            
            if allow:
                if st.button("Print"):
                    rpt=f"<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'>Pt:{nm} ({mrn})<hr>Res: Anti-{', '.join(matches)}<br>Valid Rule of 3.<br><br>Sig: ______</div><div class='consultant-footer'><span style='color:#800;font-weight:bold'>Dr. Haitham Ismail</span></div></div><script>window.print()</script>"
                    st.markdown(rpt, unsafe_allow_html=True)
            else:
                st.info("Rule Not Met. Add Cell:")
                with st.expander("Add Cell"):
                    xc1,xc2=st.columns(2); nid=xc1.text_input("ID"); nres=xc2.selectbox("R",["Neg","Pos"]); ph={}
                    cx=st.columns(len(matches))
                    for i,m in enumerate(matches):
                        r=cx[i].radio(m,["+","0"],key=f"xa_{m}")
                        ph[m]=1 if r=="+" else 0
                    if st.button("Confirm"):
                        st.session_state.extra.append({"src":nid,"score":1 if nres=="Pos" else 0,"pheno":ph,"s":1 if nres=="Pos" else 0}); st.rerun()
