import streamlit as st
import pandas as pd
import io
from datetime import date

# 1. SETUP
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🏥")

# STYLE
st.markdown("""<style>@media print {.stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }.block-container { padding: 0 !important; }.print-only { display: block !important; }.results-box { border: 2px solid #333; padding: 15px; margin-top: 20px; font-family: 'Times New Roman'; }.consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; }}.hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }.signature-badge { position: fixed; bottom: 10px; right: 15px; font-family: 'Georgia', serif; font-size: 12px; color: #8B0000; background: rgba(255,255,255,0.95); padding: 5px 10px; border: 1px solid #eecaca; border-radius: 5px; z-index:99; } div[data-testid="stDataEditor"] table { width: 100% !important; } .status-pass { background-color: #d1e7dd; padding: 10px; border-radius: 5px; color: #0f5132; border-left: 5px solid #198754; margin-bottom: 5px; } .status-fail { background-color: #f8d7da; padding: 10px; border-radius: 5px; color: #842029; border-left: 5px solid #dc3545; margin-bottom: 5px; }</style>""", unsafe_allow_html=True)

# FOOTER
st.markdown("<div class='signature-badge no-print'><b>Dr. Haitham Ismail</b><br>Clinical Hematology/Transfusion Consultant</div>", unsafe_allow_html=True)

# --- DEFINITIONS (SINGLE LINE TO PREVENT SYNTAX ERRORS) ---
antigens_order = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
allele_pairs = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Kpa':'Kpb', 'Kpb':'Kpa', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S', 'Lea':'Leb', 'Leb':'Lea'}
STRICT_DOSAGE = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]

# --- STATE INIT ---
if 'panel_11' not in st.session_state:
    st.session_state.panel_11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in antigens_order}} for i in range(11)])
if 'panel_3' not in st.session_state:
    st.session_state.panel_3 = pd.DataFrame([{"ID": f"Scn {i}", **{ag: 0 for ag in antigens_order}} for i in ["I", "II", "III"]])
if 'inputs' not in st.session_state: st.session_state.inputs = {f"c{i}": "Neg" for i in range(1, 12)}
if 'inputs_s' not in st.session_state: st.session_state.inputs_s = {f"s{i}": "Neg" for i in ["I", "II", "III"]}
if 'extra_cells' not in st.session_state: st.session_state.extra_cells = []
if 'admin_mode' not in st.session_state: st.session_state.admin_mode = False

# ==========================================
# 2. LOGIC FUNCTIONS (MATRIX SCANNER V3)
# ==========================================
def clean_str(val):
    return str(val).upper().replace("(","").replace(")","").replace(" ","").strip()

def normalize_val(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes']) else 0

def matrix_parser(file_obj):
    # This parser ignores rows and scans everywhere
    df = pd.read_excel(file_obj, header=None)
    
    ag_map = {} # {'D': col_index, 'C': col_index}
    
    # 1. SCAN HEADERS (First 20 rows, 50 cols)
    for r in range(min(20, len(df))):
        for c in range(min(50, len(df.columns))):
            val = clean_str(df.iloc[r, c])
            detected = None
            if val in antigens_order: detected = val
            elif val in ["RHD","RH1","D"]: detected = "D"
            elif val in ["RHC","RH2","C"]: detected = "C"
            elif val in ["RHE","RH3","E"]: detected = "E"
            
            if detected and detected not in ag_map:
                ag_map[detected] = c # Capture Column Index
    
    if len(ag_map) < 3: return None, "No antigens found. Check Excel format."

    # 2. EXTRACT DATA (Find the 1s and 0s)
    # We scan starting from where we found headers
    final_data = []
    collected_count = 0
    row_cursor = 0
    
    while collected_count < 11 and row_cursor < len(df):
        row_idx = row_cursor
        # Validate if this is a data row (look for D column data)
        is_valid = False
        if "D" in ag_map:
            d_col = ag_map["D"]
            d_val = str(df.iloc[row_idx, d_col]).lower()
            if any(x in d_val for x in ['0','+','1','w','neg','pos']): is_valid = True
        elif "K" in ag_map: # Backup
            k_col = ag_map["K"]
            k_val = str(df.iloc[row_idx, k_col]).lower()
            if any(x in k_val for x in ['0','+','1','w','neg','pos']): is_valid = True
            
        if is_valid:
            r_data = {"ID": f"Cell {collected_count+1}"}
            for ag in antigens_order:
                val = 0
                if ag in ag_map:
                    col = ag_map[ag]
                    val = normalize_val(df.iloc[row_idx, col])
                r_data[ag] = val
            final_data.append(r_data)
            collected_count += 1
            
        row_cursor += 1
        
    return pd.DataFrame(final_data), None

def can_rule_out(ag, pheno):
    if pheno.get(ag, 0) == 0: return False
    if ag in STRICT_DOSAGE:
        partner = allele_pairs.get(ag)
        if partner and pheno.get(partner, 0) == 1: return False
    return True

def bulk_set(val):
    for i in range(1, 12): st.session_state.inputs[f"c{i}"] = val

def check_r3(cand, rows, inputs, rows_s, inputs_s, extra):
    pos_r, neg_r = 0, 0
    # Panel
    for i in range(1,12):
        s=1 if inputs[i]!="Neg" else 0
        h=rows[i-1].get(cand,0)
        if h==1 and s==1: pos_r+=1
        if h==0 and s==0: neg_r+=1
    # Screen
    scrs=["I","II","III"]
    for i, sc in enumerate(scrs):
        s=1 if inputs_s[f"s{sc}"]!="Neg" else 0
        h=rows_s[i].get(cand,0)
        if h==1 and s==1: pos_r+=1
        if h==0 and s==0: neg_r+=1
    # Extra
    for c in extra:
        if c['score']==1 and c['pheno'].get(cand,0)==1: pos_r+=1
        if c['score']==0 and c['pheno'].get(cand,0)==0: neg_r+=1
    
    passed = (pos_r>=3 and neg_r>=3) or (pos_r>=2 and neg_r>=3)
    method = "Standard (3/3)" if (pos_r>=3 and neg_r>=3) else ("Modified" if passed else "Fail")
    return passed, pos_r, neg_r, method

# ==========================================
# 3. SIDEBAR NAVIGATION
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    st.write("V27.0 Stable")
    app_mode = st.radio("Navigation", ["User Workstation", "Supervisor Config"])
    st.write("---")
    if st.button("🗑️ Reset All"):
        st.session_state.extra_cells = []
        st.rerun()

# ==========================================
# 4. SUPERVISOR CONFIG
# ==========================================
if app_mode == "Supervisor Config":
    st.title("🛠️ Master Configuration (Matrix Engine)")
    if st.text_input("Password", type="password") == "admin123":
        t1, t2 = st.tabs(["Panel 11", "Screen"])
        with t1:
            st.info("Smart Upload: Upload PDF-converted Excel here.")
            up = st.file_uploader("Upload Excel", type=['xlsx'])
            if up:
                new_df, msg = matrix_parser(up)
                if new_df is not None:
                    count = new_df.shape[1] - 1
                    st.success(f"✅ Success! Extracted {count} Antigens.")
                    st.session_state.panel_11 = new_df
                    if st.button("Update View"): st.rerun()
                else:
                    st.error(f"Failed: {msg}")
            
            st.write("### Grid Editor:")
            edited = st.data_editor(st.session_state.panel_11, height=450, hide_index=True, use_container_width=True)
            if st.button("Save Manual Changes"):
                st.session_state.panel_11 = edited
                st.success("Saved.")
        
        with t2:
            st.session_state.panel_3 = st.data_editor(st.session_state.panel_3, hide_index=True)

# ==========================================
# 5. USER WORKSTATION
# ==========================================
else:
    st.markdown("""<div class='hospital-header'><h1>Maternity & Children Hospital - Tabuk</h1><h4>Serology Workstation</h4></div>""", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mrn=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    L, R = st.columns([1, 2.5])
    with L:
        st.subheader("1. Control")
        ac = st.radio("AC", ["Negative","Positive"], horizontal=True)
        if ac == "Positive": st.error("🚨 STOP: Auto Control Positive."); st.stop()
        st.write("---")
        for x in ["I","II","III"]: st.session_state.inputs_s[f"s{x}"] = st.selectbox(f"Scn {x}",["Neg","w+","1+","2+"], key=f"k_{x}")
        st.write("---")
        if st.button("All Neg"): bulk_set("Neg")
        if st.button("All Pos"): bulk_set("2+")
    
    with R:
        st.subheader("2. Panel")
        grd = st.columns(6)
        in_map = {}
        for i in range(1, 12):
            k=f"c{i}"
            val = grd[(i-1)%6].selectbox(f"C{i}",["Neg","w+","1+","2+"], key=f"u_{i}", index=["Neg","w+","1+","2+"].index(st.session_state.inputs[k]))
            st.session_state.inputs[k] = val
            in_map[i] = 0 if val == "Neg" else 1
    
    st.divider()
    if st.checkbox("🔍 Analyze"):
        r11 = [st.session_state.panel_11.iloc[i].to_dict() for i in range(11)]
        r3  = [st.session_state.panel_3.iloc[i].to_dict() for i in range(3)]
        ruled_out = set()
        
        # Rule out
        for ag in antigens_order:
            for i,sc in in_map.items():
                if sc==0 and can_rule_out(ag, r11[i-1]): ruled_out.add(ag); break
        scr_m={"I":0,"II":1,"III":2}
        for k,v in st.session_state.inputs_s.items():
            if v=="Neg":
                for ag in antigens_order:
                    if ag not in ruled_out and can_rule_out(ag, r3[scr_m[k[1:]]]): ruled_out.add(ag)
        
        matches = []
        for cand in [x for x in antigens_order if x not in ruled_out]:
            mis = False
            for i, sc in in_map.items():
                if sc>0 and r11[i-1].get(cand,0)==0: mis=True
            if not mis: matches.append(cand)
            
        if not matches: st.error("Inconclusive.")
        else:
            allow = True
            for m in matches:
                pas,p,n,met = check_r3(m,r11,st.session_state.inputs,r3,st.session_state.inputs_s,st.session_state.extra_cells)
                st.markdown(f"<div class='status-{'pass' if pas else 'fail'}'><b>Anti-{m}:</b> {met} ({p} Pos/{n} Neg)</div>", unsafe_allow_html=True)
                if not pas: allow=False
            
            if allow:
                if st.button("🖨️ Report"):
                    ht=f"<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'>Pt:{nm} ({mrn})<hr>Result: Anti-{', '.join(matches)}<br>Valid Rule of 3.<br><br>Sig: _________</div><div class='consultant-footer'><span style='color:darkred;font-weight:bold'>Dr. Haitham Ismail</span></div></div><script>window.print()</script>"
                    st.markdown(ht, unsafe_allow_html=True)
            else:
                st.info("Rule Not Met. Add Cell:")
                with st.expander("Add Cell"):
                    xc1,xc2=st.columns(2); nid=xc1.text_input("ID"); nres=xc2.selectbox("R",["Neg","Pos"])
                    tph={}
                    cols=st.columns(len(matches))
                    for i,m in enumerate(matches):
                        r=cols[i].radio(m,["+","0"],key=f"ex_{m}")
                        tph[m]=1 if r=="+" else 0
                    if st.button("Add"):
                        st.session_state.extra_cells.append({"src":nid,"score":1 if nres=="Pos" else 0,"pheno":tph})
                        st.rerun()
