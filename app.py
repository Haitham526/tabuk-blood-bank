import streamlit as st
import pandas as pd
import io
from datetime import date

# ==========================================
# 1. SETUP & STYLE
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .block-container { padding: 0 !important; }
        .print-only { display: block !important; }
        .results-box { border: 2px solid #333; padding: 15px; font-family: 'Times New Roman'; }
        .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; }
    }
    .hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    .signature-badge { position: fixed; bottom: 10px; right: 15px; font-family: 'Georgia', serif; font-size: 12px; color: #8B0000; background: rgba(255,255,255,0.95); padding: 5px 10px; border: 1px solid #eecaca; border-radius: 5px; z-index:99; }
    div[data-testid="stDataEditor"] table { width: 100% !important; } 
    .status-pass { background-color: #d1e7dd; padding: 8px; border-radius: 5px; color: #0f5132; margin-bottom:5px; border-left: 5px solid #198754; }
    .status-fail { background-color: #f8d7da; padding: 8px; border-radius: 5px; color: #842029; margin-bottom:5px; border-left: 5px solid #dc3545; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='signature-badge no-print'><b>Dr. Haitham Ismail</b><br>Clinical Hematology/Transfusion Consultant</div>", unsafe_allow_html=True)

antigens_order = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
allele_pairs = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Kpa':'Kpb', 'Kpb':'Kpa', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S', 'Lea':'Leb', 'Leb':'Lea'}
STRICT_DOSAGE = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]

# --- CORRECTED SESSION STATE ---
if 'panel_11' not in st.session_state:
    st.session_state.panel_11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in antigens_order}} for i in range(11)])
if 'panel_3' not in st.session_state:
    st.session_state.panel_3 = pd.DataFrame([{"ID": f"Scn {i}", **{ag: 0 for ag in antigens_order}} for i in ["I", "II", "III"]])
if 'inputs' not in st.session_state: st.session_state.inputs = {f"c{i}": "Neg" for i in range(1, 12)}
if 'inputs_s' not in st.session_state: st.session_state.inputs_s = {f"s{i}": "Neg" for i in ["I", "II", "III"]}
if 'extra_cells' not in st.session_state: st.session_state.extra_cells = []
if 'admin_mode' not in st.session_state: st.session_state.admin_mode = False

# ==========================================
# 2. LOGIC FUNCTIONS
# ==========================================
def normalize_val(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes']) else 0

def multi_sheet_parser(file_bytes, num_cells=11):
    xls = pd.ExcelFile(file_bytes)
    for sheet in xls.sheet_names:
        df = pd.read_excel(file_bytes, sheet_name=sheet, header=None)
        
        # Search Headers
        header_row_idx, col_map = -1, {}
        best_matches = 0
        
        for r in range(min(15, len(df))):
            matches, temp_map = 0, {}
            for c, val in enumerate(df.iloc[r]):
                v_clean = str(val).strip().replace(" ", "")
                if v_clean in antigens_order and v_clean not in temp_map:
                    matches += 1; temp_map[v_clean] = c
            
            if matches > best_matches:
                best_matches, header_row_idx, col_map = matches, r, temp_map
        
        # If headers found in sheet, extract data
        if best_matches >= 3:
            start = header_row_idx + 1
            data = []
            cnt = 0
            
            while cnt < num_cells and start < len(df):
                is_data_row = False
                test_cols = [col_map.get(k) for k in ['D', 'C'] if k in col_map]
                for tc in test_cols:
                    val = str(df.iloc[start, tc]).lower()
                    if any(x in val for x in ['+','0','1']): is_data_row=True; break
                
                if is_data_row:
                    row_dict = {}
                    if num_cells == 11: row_dict["ID"] = f"Cell {cnt+1}"
                    else: row_dict["ID"] = f"Scn {['I','II','III'][cnt]}"

                    for ag in antigens_order:
                        val = 0
                        if ag in col_map: val = normalize_val(df.iloc[start, col_map[ag]])
                        row_dict[ag] = int(val)
                    data.append(row_dict)
                    cnt += 1
                start += 1
            
            if len(data) >= num_cells: return pd.DataFrame(data), f"Data found on Sheet '{sheet}'"

    return None, "No valid grid found in any sheet."

# (Other logic functions can remain the same)
def can_rule_out(ag, pheno):
    if pheno.get(ag, 0) == 0: return False
    if ag in STRICT_DOSAGE:
        partner = allele_pairs.get(ag)
        if partner and pheno.get(partner, 0) == 1: return False
    return True

def check_r3(cand, r11, i11, r3, i3, ex):
    pr,nr=0,0
    # Panel
    for i in range(1,12):
        s=1 if i11[i]!="Neg" else 0
        h=r11[i-1].get(cand,0)
        if h==1 and s==1: pr+=1
        if h==0 and s==0: nr+=1
    # Screen
    for i,sid in enumerate(["I","II","III"]):
        s=1 if i3[f"s{sid}"]!="Neg" else 0
        h=r3[i].get(cand,0)
        if h==1 and s==1: pr+=1
        if h==0 and s==0: nr+=1
    # Extra
    for c in ex:
        s,h=c['s'],c['p'].get(cand,0)
        if h==1 and s==1: pr+=1
        if h==0 and s==0: nr+=1
    
    passed=(pr>=3 and nr>=3) or (pr>=2 and nr>=3)
    method="Standard" if (pr>=3 and nr>=3) else "Modified"
    return passed,pr,nr,method

def bulk(v): 
    for i in range(1,12): st.session_state.inputs[f"c{i}"]=v

# ==========================================
# 3. SIDEBAR & MENU
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    st.caption("V32.0 (Stable & Correct)")
    app_mode = st.radio("Navigation", ["User Workstation", "Supervisor Config"])
    st.write("---")
    if st.button("Reset Extras"):
        st.session_state.extra_cells=[]
        st.rerun()

# --- ADMIN VIEW ---
if app_mode == "Supervisor Config":
    st.title("🛠️ Master Configuration")
    if st.text_input("Password", type="password") == "admin123":
        tab1, tab2 = st.tabs(["Panel 11", "Screening 3"])
        
        with tab1:
            st.info("Upload the PDF-Converted Excel for the Main Panel.")
            up1 = st.file_uploader("Upload Panel (Excel)", type=['xlsx'], key='up1')
            if up1:
                df, msg = multi_sheet_parser(io.BytesIO(up1.getvalue()), 11)
                if df is not None:
                    st.success(msg)
                    st.session_state.panel_11 = df
                    st.rerun()
                else: st.error(msg)
            
            st.write("#### Master Data Grid (Live Edit):")
            edited1 = st.data_editor(st.session_state.panel_11.fillna(0), height=450, hide_index=True, use_container_width=True)
            if st.button("Save Grid 11", type='primary'):
                st.session_state.panel_11 = edited1; st.success("Saved.")
        
        with tab2:
            st.info("Upload a SEPARATE Excel for the 3 Screening Cells.")
            up2 = st.file_uploader("Upload Screen (Excel)", type=['xlsx'], key='up2')
            if up2:
                df3, msg3 = multi_sheet_parser(io.BytesIO(up2.getvalue()), 3)
                if df3 is not None:
                    st.success(msg3)
                    st.session_state.panel_3 = df3
                    st.rerun()
                else: st.error(msg3)
            
            st.write("#### Screen Cells Grid:")
            edited2 = st.data_editor(st.session_state.panel_3.fillna(0), hide_index=True, use_container_width=True)
            if st.button("Save Grid 3", type='primary'):
                st.session_state.panel_3 = edited2; st.success("Saved.")

    elif st.text_input: st.error("Wrong Password.")
# --- USER VIEW ---
else:
    st.markdown("""<div class='hospital-header'><h1>Maternity & Children Hospital - Tabuk</h1><h4>Serology Workstation</h4></div>""", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mrn=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    L, R = st.columns([1, 2.5])
    with L:
        st.subheader("1. Screen/Control")
        ac = st.radio("Auto Control (AC)", ["Negative", "Positive"])
        if ac=="Positive": st.error("DAT Required"); st.stop()
        for x in ["I","II","III"]: st.session_state.inputs_s[f"s{x}"]=st.selectbox(f"Scn {x}",["Neg","Pos"],key=f"u_{x}")
        if st.button("All Neg"): bulk_set("Neg")
    with R:
        st.subheader("2. Panel")
        cols=st.columns(6)
        in_map={}
        for i in range(1,12):
            k=f"c{i}"
            v=cols[(i-1)%6].selectbox(f"C{i}",["Neg","Pos"],key=f"p_{i}",index=["Neg","Pos"].index(st.session_state.inputs[k]))
            st.session_state.inputs[k]=v
            in_map[i]=0 if v=="Neg" else 1
            
    st.divider()
    if st.checkbox("🔍 Analyze"):
        r11=[st.session_state.panel_11.iloc[i].to_dict() for i in range(11)]
        r3=[st.session_state.panel_3.iloc[i].to_dict() for i in range(3)]
        ruled=set()
        
        # Exclusions
        for ag in antigens_order:
            for i,s in in_map.items():
                if s==0 and can_rule_out(ag, r11[i-1]): ruled.add(ag); break
        scr_m={"I":0,"II":1,"III":2}
        for k,v in st.session_state.inputs_s.items():
            if v=="Neg":
                for ag in antigens_order:
                    if ag not in ruled and can_rule_out(ag, r3[scr_m[k[1:]]]): ruled.add(ag)
        
        matches=[]
        for c in [x for x in antigens_order if x not in ruled]:
            mis=False
            for i,s in in_map.items():
                if s>0 and r11[i-1].get(c,0)==0: mis=True
            if not mis: matches.append(c)
            
        if not matches: st.error("Inconclusive")
        else:
            allow_print=True
            st.subheader("3. Identification")
            for m in matches:
                pas,p,n,met = check_r3(m,r11,st.session_state.inputs,r3,st.session_state.inputs_s,st.session_state.extra_cells)
                st.markdown(f"<div class='status-{'pass' if pas else 'fail'}'><b>Anti-{m}:</b> {met} ({p} Pos/{n} Neg)</div>", unsafe_allow_html=True)
                if not
