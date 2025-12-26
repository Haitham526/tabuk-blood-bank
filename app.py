import streamlit as st
import pandas as pd
import io
from datetime import date

# ==========================================
# 1. SETUP & STYLING
# ==========================================
st.set_page_config(page_title="MCH Tabuk Serology", layout="wide", page_icon="🏥")

st.markdown("""
<style>
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .block-container { padding: 0 !important; }
        .print-only { display: block !important; }
        .results-box { border: 2px solid #333; padding: 15px; margin-top: 10px; font-family: 'Times New Roman'; }
        .footer-print { position: fixed; bottom: 0; width: 100%; text-align: center; font-size: 10px; border-top: 1px solid #ccc; }
    }
    
    .hospital-header { 
        text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 15px; margin-bottom: 20px; 
        font-family: 'Arial'; color: #003366; 
    }
    
    .status-pass { background-color: #d1e7dd; padding: 8px; border-radius: 5px; color: #0f5132; border-left: 5px solid #198754; margin-bottom:5px; }
    .status-fail { background-color: #f8d7da; padding: 8px; border-radius: 5px; color: #842029; border-left: 5px solid #dc3545; margin-bottom:5px; }
    
    .dr-signature {
        position: fixed; bottom: 10px; right: 15px;
        font-family: 'Georgia', serif; font-size: 12px; color: #8B0000;
        background: rgba(255,255,255,0.95); padding: 5px 10px; border: 1px solid #eecaca; z-index: 99;
    }
    
    /* Grid Fixes */
    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

# Footer
st.markdown("<div class='dr-signature no-print'><b>Dr. Haitham Ismail</b><br>Clinical Hematology & Transfusion Consultant</div>", unsafe_allow_html=True)

# Definitions
antigens_order = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
allele_pairs = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S'}
STRICT_DOSAGE = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]

# Initial State
if 'panel_11' not in st.session_state:
    st.session_state.panel_11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in antigens_order}} for i in range(11)])
if 'panel_3' not in st.session_state:
    st.session_state.panel_3 = pd.DataFrame([{"ID": f"Scn {i}", **{ag: 0 for ag in antigens_order}} for i in ["I", "II", "III"]])
if 'inputs' not in st.session_state:
    st.session_state.inputs = {f"c{i}": "Neg" for i in range(1, 12)}
if 'inputs_s' not in st.session_state:
    st.session_state.inputs_s = {f"s{i}": "Neg" for i in ["I", "II", "III"]}
if 'extra_cells' not in st.session_state:
    st.session_state.extra_cells = []

# ==========================================
# 2. LOGIC FUNCTIONS
# ==========================================
def normalize_val(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

# --- THE SMART HUNTER PARSER ---
def parse_excel_smart(file_bytes, limit_rows):
    try:
        xls = pd.ExcelFile(file_bytes)
        for sheet in xls.sheet_names:
            df = pd.read_excel(file_bytes, sheet_name=sheet, header=None)
            
            # Map columns
            col_map = {}
            for r in range(min(25, len(df))):
                for c in range(min(50, len(df.columns))):
                    val = str(df.iloc[r, c]).strip().upper().replace(" ", "")
                    
                    found = None
                    if val in antigens_order: found = val
                    elif val in ["RHD", "D"]: found = "D"
                    elif val in ["RHC", "C"]: found = "C"
                    elif val in ["RHE", "E"]: found = "E"
                    
                    if found and found not in col_map:
                        col_map[found] = {"r": r, "c": c}
            
            # Check finding
            if len(col_map) >= 3:
                # Assuming data is below the lowest header row
                max_header_row = max(x['r'] for x in col_map.values())
                start_row = max_header_row + 1
                
                rows_data = []
                extracted = 0
                curr = start_row
                
                while extracted < limit_rows and curr < len(df):
                    # Check Row Validity (Check D column)
                    is_valid_row = False
                    if "D" in col_map:
                        chk_val = str(df.iloc[curr, col_map["D"]['c']]).lower()
                        if any(x in chk_val for x in ['0', '1', '+', 'w']): is_valid_row = True
                    elif "K" in col_map: # Backup check
                        chk_val = str(df.iloc[curr, col_map["K"]['c']]).lower()
                        if any(x in chk_val for x in ['0', '1', '+', 'w']): is_valid_row = True
                        
                    if is_valid_row:
                        r_dict = {"ID": f"C{extracted+1}"}
                        for ag in antigens_order:
                            v = 0
                            if ag in col_map:
                                v = normalize_val(df.iloc[curr, col_map[ag]['c']])
                            r_dict[ag] = int(v)
                        rows_data.append(r_dict)
                        extracted += 1
                    
                    curr += 1
                
                if extracted >= limit_rows:
                    return pd.DataFrame(rows_data), f"Successfully loaded from {sheet}"
                    
        return None, "Structure not found. Try Manual Entry."
    except Exception as e:
        return None, f"Error: {e}"

def can_rule_out(ag, pheno):
    if pheno.get(ag, 0) == 0: return False
    if ag in STRICT_DOSAGE:
        pair = allele_pairs.get(ag)
        if pair and pheno.get(pair, 0) == 1: return False
    return True

def bulk_set(val):
    for i in range(1, 12): st.session_state.inputs[f"c{i}"] = val

def calc_probability(cand, rows, in_p, rs, in_s, ex):
    p, n = 0, 0
    # Panel
    for i in range(1, 12):
        s = 1 if in_p[i] != "Neg" else 0
        h = rows[i-1].get(cand, 0)
        if h==1 and s==1: p+=1
        if h==0 and s==0: n+=1
    # Screen
    scs = ["I","II","III"]
    for i, label in enumerate(scs):
        s = 1 if in_s[f"s{label}"] != "Neg" else 0
        h = rs[i].get(cand, 0)
        if h==1 and s==1: p+=1
        if h==0 and s==0: n+=1
    # Extra
    for c in ex:
        if c['res']==1 and c['ph'].get(cand,0)==1: p+=1
        if c['res']==0 and c['ph'].get(cand,0)==0: n+=1
        
    pass_rule = (p>=3 and n>=3) or (p>=2 and n>=3)
    txt = "Standard (3/3)" if (p>=3 and n>=3) else ("Modified" if pass_rule else "Rule Failed")
    return pass_rule, p, n, txt

# ==========================================
# 3. SIDEBAR MENU
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    st.title("Main Menu")
    nav = st.radio("Go To:", ["User Workstation", "Admin Configuration"])
    
    st.markdown("---")
    if st.button("🗑️ Reset Selected Cells"):
        st.session_state.extra_cells = []
        st.rerun()

# ==========================================
# 4. ADMIN PANEL (CONFIGURATION)
# ==========================================
if nav == "Admin Configuration":
    st.title("🛠️ Master Data Configuration")
    pwd = st.text_input("Admin Password", type="password")
    
    if pwd == "admin123":
        st.success("Unlocked.")
        
        tab1, tab2 = st.tabs(["Panel 11 (ID)", "Panel 3 (Screening)"])
        
        # TAB 1: Panel
        with tab1:
            st.info("Upload PDF-converted Excel (The system will find the grid).")
            up = st.file_uploader("Upload Panel 11", type=["xlsx"], key="u1")
            
            if up:
                df, msg = parse_excel_smart(io.BytesIO(up.getvalue()), 11)
                if df is not None:
                    st.success(f"✅ {msg}")
                    st.session_state.panel_11 = df
                    if st.button("Update View", key="btn1"): st.rerun()
                else:
                    st.error(f"❌ {msg}")
            
            st.write("#### Live Grid (Manual Edit Supported):")
            # Always ensure integers
            safe_df = st.session_state.panel_11.fillna(0)
            edited = st.data_editor(safe_df, height=450, use_container_width=True, hide_index=True)
            if st.button("Save Grid"):
                st.session_state.panel_11 = edited
                st.success("Changes Saved.")

        # TAB 2: Screen
        with tab2:
            st.info("Upload Screening Cells (Optional)")
            up2 = st.file_uploader("Upload Screen 3", type=["xlsx"], key="u2")
            if up2:
                df2, msg2 = parse_excel_smart(io.BytesIO(up2.getvalue()), 3)
                if df2 is not None:
                    st.success(msg2)
                    st.session_state.panel_3 = df2
                    st.rerun()
            st.session_state.panel_3 = st.data_editor(st.session_state.panel_3, hide_index=True)
            
    elif pwd:
        st.error("Access Denied.")

# ==========================================
# 5. USER WORKSTATION
# ==========================================
else:
    st.markdown("""<div class='hospital-header'><h1>Maternity & Children Hospital - Tabuk</h1><h4>Serology Workstation</h4></div>""", unsafe_allow_html=True)
    
    # --- A. Patient Info ---
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mrn=c2.text_input("MRN"); tc=c3.text_input("Technician"); dt=c4.date_input("Date")
    
    st.divider()
    
    # --- B. Reactions Input ---
    colL, colR = st.columns([1, 2.5])
    
    with colL:
        st.subheader("1. Screen/Control")
        ac_val = st.radio("Auto Control (AC)", ["Negative", "Positive"])
        
        st.write("---")
        # Screen Inputs
        for s in ["I", "II", "III"]:
            key = f"s{s}"
            st.session_state.inputs_s[key] = st.selectbox(f"Scn {s}", ["Neg","w+","1+","2+","3+","4+"], key=f"inp_{s}")
            
        st.write("---")
        # Bulk Buttons
        b1, b2 = st.columns(2)
        if b1.button("Set Neg"): bulk_set("Neg")
        if b2.button("Set Pos"): bulk_set("2+")

    with colR:
        st.subheader("2. Panel Reactions (11 Cells)")
        # Grid Layout 6x2
        grid_cols = st.columns(6)
        in_p_map = {}
        for i in range(1, 12):
            k = f"c{i}"
            col_idx = (i-1) % 6
            # Accessing list carefully
            with grid_cols[col_idx]:
                v = st.selectbox(f"Cell {i}", ["Neg","w+","1+","2+","3+","4+"], key=f"main_{i}", index=["Neg","w+","1+","2+","3+","4+"].index(st.session_state.inputs[k]))
                st.session_state.inputs[k] = v
                in_p_map[i] = 0 if v == "Neg" else 1

    # --- C. Logic Analysis ---
    st.divider()
    
    if ac_val == "Positive":
        st.error("🚨 AUTO CONTROL POSITIVE")
        st.info("Protocol: Perform DAT (Polyspecific & Monospecific). Check for WAIHA/DHTR.")
    
    else:
        if st.checkbox("🚀 Run Analysis Engine"):
            # Prepare Lists
            r11 = [st.session_state.panel_11.iloc[i].to_dict() for i in range(11)]
            r3  = [st.session_state.panel_3.iloc[i].to_dict() for i in range(3)]
            
            # 1. Exclusion (Panel)
            ruled_out = set()
            for ag in antigens_order:
                for idx, sc in in_p_map.items():
                    if sc == 0:
                        if can_rule_out(ag, r11[idx-1]):
                            ruled_out.add(ag); break
            
            # 2. Exclusion (Screen)
            sm = {"I":0, "II":1, "III":2}
            for k, v in st.session_state.inputs_s.items():
                if v == "Neg":
                    ph = r3[sm[k.replace("s","")]]
                    for ag in antigens_order:
                        if ag not in ruled_out and can_rule_out(ag, ph):
                            ruled_out.add(ag)
                            
            candidates = [x for x in antigens_order if x not in ruled_out]
            
            # 3. Inclusion (Matching)
            matches = []
            for cand in candidates:
                mismatch = False
                # Must be positive where panel is positive
                for idx, sc in in_p_map.items():
                    if sc > 0 and r11[idx-1].get(cand,0)==0: mismatch = True
                if not mismatch: matches.append(cand)
            
            if not matches:
                st.error("❌ Inconclusive (Pattern mismatch).")
            else:
                allow = True
                st.subheader("3. Investigation Result")
                
                for m in matches:
                    ok, p, n, msg = calc_probability(m, r11, st.session_state.inputs, r3, st.session_state.inputs_s, st.session_state.extra_cells)
                    st.markdown(f"""
                    <div class='{'status-pass' if ok else 'status-fail'}'>
                        <b>Anti-{m}:</b> {msg}<br>
                        Matched: {p} Positive Cells / {n} Negative Cells
                    </div>
                    """, unsafe_allow_html=True)
                    if not ok: allow = False
                
                if allow:
                    if st.button("🖨️ Print Final Report"):
                        rpt = f"""<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'><b>Pt:</b> {nm} ({mrn})<br><b>Tech:</b> {tc}<hr><b>Conclusion:</b> Anti-{', '.join(matches)} Identified.<br>Validation: Probability p<0.05 met.<br>Note: Transfuse Ag-negative units.<br><br>Sign: _________</div><div class='footer-print'>Dr. Haitham Ismail</div></div><script>window.print()</script>"""
                        st.markdown(rpt, unsafe_allow_html=True)
                else:
                    st.warning("⚠️ Probability Rule NOT Met.")
                    st.write("Add selected cells below:")
                    with st.expander("➕ Add Cell"):
                        xc1,xc2 = st.columns(2)
                        nid = xc1.text_input("Cell Lot ID")
                        nres = xc2.selectbox("Reaction", ["Neg","Pos"])
                        cols_add = st.columns(len(matches))
                        t_ph = {}
                        for i, mt in enumerate(matches):
                            val = cols_add[i].radio(mt, ["+","0"], key=f"ex_{mt}")
                            t_ph[mt] = 1 if val=="+" else 0
                        if st.button("Add To Calculation"):
                            st.session_state.extra_cells.append({"src":nid, "res":1 if nres=="Pos" else 0, "ph":t_ph, "score":1 if nres=="Pos" else 0})
                            st.rerun()
