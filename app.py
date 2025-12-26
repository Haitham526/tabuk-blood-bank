import streamlit as st
import pandas as pd
import io
from datetime import date

# 1. SETUP
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🩸")

st.markdown("""<style>@media print {.stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }.block-container { padding: 0 !important; }.print-only { display: block !important; }.results-box { border: 2px solid #333; padding: 15px; margin-top: 20px; font-family: 'Times New Roman'; }.consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; }}.hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }.signature-badge { position: fixed; bottom: 10px; right: 15px; font-family: 'Georgia', serif; font-size: 12px; color: #8B0000; background: rgba(255,255,255,0.95); padding: 5px 10px; border: 1px solid #eecaca; border-radius: 5px; z-index:99; } div[data-testid="stDataEditor"] table { width: 100% !important; } .status-pass { background-color: #d1e7dd; padding: 10px; border-radius: 5px; color: #0f5132; border-left: 5px solid #198754; margin-bottom: 5px; } .status-fail { background-color: #f8d7da; padding: 10px; border-radius: 5px; color: #842029; border-left: 5px solid #dc3545; margin-bottom: 5px; }</style>""", unsafe_allow_html=True)

st.markdown("<div class='signature-badge no-print'><b>Dr. Haitham Ismail</b><br>Clinical Hematology/Transfusion Consultant</div>", unsafe_allow_html=True)

antigens_order = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
allele_pairs = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Kpa':'Kpb', 'Kpb':'Kpa', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S', 'Lea':'Leb', 'Leb':'Lea'}
STRICT_DOSAGE = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]

if 'panel_11' not in st.session_state:
    st.session_state.panel_11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in antigens_order}} for i in range(11)])
if 'panel_3' not in st.session_state:
    st.session_state.panel_3 = pd.DataFrame([{"ID": f"Scn {i}", **{ag: 0 for ag in antigens_order}} for i in ["I", "II", "III"]])
if 'inputs' not in st.session_state: st.session_state.inputs = {f"c{i}": "Neg" for i in range(1, 12)}
if 'inputs_s' not in st.session_state: st.session_state.inputs_s = {f"s{i}": "Neg" for i in ["I", "II", "III"]}
if 'extra_cells' not in st.session_state: st.session_state.extra_cells = []
if 'admin_mode' not in st.session_state: st.session_state.admin_mode = False

# ==========================================
# 2. LOGIC: THE X-RAY PARSER
# ==========================================
def clean_str(val):
    # Aggressive cleaning
    return str(val).upper().replace("(","").replace(")","").replace(" ","").replace(".","").strip()

def normalize_val(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes']) else 0

def matrix_parser_v3(file_bytes):
    # Read without header
    try:
        df = pd.read_excel(file_bytes, header=None)
    except:
        return None, "File Corrupted or Not Excel", None

    ag_map = {} 
    
    # 1. SCAN UNLIMITED (No Limits)
    # Search whole dataframe for anchors
    for r in range(len(df)):
        # Speed Optimization: Only scan rows that look like headers (contain strings)
        row_values = [str(x) for x in df.iloc[r].values]
        row_str = "".join(row_values)
        if len(row_str) < 5: continue # Skip empty rows
        
        for c in range(len(df.columns)):
            val_clean = clean_str(df.iloc[r, c])
            
            detected = None
            # Direct Check
            if val_clean in antigens_order: detected = val_clean
            # Fuzzy Map
            elif val_clean in ["RHD","RH1","D"]: detected = "D"
            elif val_clean in ["RHC","RH2","C","RH'"]: detected = "C"
            elif val_clean in ["RHE","RH3","E","RH''"]: detected = "E"
            elif val_clean in ["RHC","RH4","C","HR'"]: detected = "c"
            
            if detected:
                # Always take the first valid occurrence?
                # Sometimes PDF puts "Rh-hr" system names above. 
                # We overwrite to find the *lowest* row before data starts usually? 
                # Let's trust first find.
                if detected not in ag_map:
                    ag_map[detected] = {"c": c, "r": r} # Save Col and Row index
    
    # Check what we found
    if len(ag_map) < 3: 
        return None, f"Only found {list(ag_map.keys())}. Is the PDF converted as Image?", df

    # 2. EXTRACT
    # We assume data starts 1 row below the FOUND antigens. 
    # NOTE: Different antigens might be found on different rows in merged headers.
    # We take the Maximum Row Index found as the "Header Line".
    header_row_idx = max(x['r'] for x in ag_map.values())
    start_row = header_row_idx + 1
    
    final_rows = []
    collected = 0
    curr = start_row
    
    while collected < 11 and curr < len(df):
        # Validate Row: Does 'D' or 'C' column have valid data?
        is_data = False
        test_keys = [k for k in ['D','C','E','c','e'] if k in ag_map]
        
        for k in test_keys:
            col = ag_map[k]['c']
            val = str(df.iloc[curr, col]).lower()
            if any(x in val for x in ['0','1','+','w']): 
                is_data = True; break
        
        if is_data:
            rd = {"ID": f"Cell {collected+1}"}
            for ag in antigens_order:
                v = 0
                if ag in ag_map:
                    col = ag_map[ag]['c']
                    v = normalize_val(df.iloc[curr, col])
                rd[ag] = int(v)
            final_rows.append(rd)
            collected += 1
        
        curr += 1
    
    if not final_rows:
        return None, "Headers found but no data rows underneath (0 or + symbols).", df
        
    return pd.DataFrame(final_rows), "Success", df

# Helper Logic (Same as before)
def can_rule_out(ag, pheno):
    if pheno.get(ag, 0) == 0: return False
    if ag in STRICT_DOSAGE:
        partner = allele_pairs.get(ag)
        if partner and pheno.get(partner, 0) == 1: return False
    return True

def bulk_set(val):
    for i in range(1, 12): st.session_state.inputs[f"c{i}"] = val

def check_r3(cand, rows, inputs, rows_s, inputs_s, extra):
    pr, nr = 0, 0
    for i in range(1,12):
        s=1 if inputs[i]!="Neg" else 0
        h=rows[i-1].get(cand,0)
        if h==1 and s==1: pr+=1
        if h==0 and s==0: nr+=1
    scrs=["I","II","III"]
    for i, sc in enumerate(scrs):
        s=1 if inputs_s[f"s{sc}"]!="Neg" else 0
        h=rows_s[i].get(cand,0)
        if h==1 and s==1: pr+=1
        if h==0 and s==0: nr+=1
    for c in extra:
        if c['score']==1 and c['pheno'].get(cand,0)==1: pr+=1
        if c['score']==0 and c['pheno'].get(cand,0)==0: nr+=1
    passed = (pr>=3 and nr>=3) or (pr>=2 and nr>=3)
    method = "Standard (3/3)" if (pr>=3 and nr>=3) else ("Modified" if passed else "Fail")
    return passed, pr, nr, method

# ==========================================
# 3. SIDEBAR
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Navigation", ["User Workstation", "Supervisor Config"])
    st.write("---")
    if st.button("🗑️ Reset All"):
        st.session_state.extra_cells = []
        st.rerun()

# ==========================================
# 4. SUPERVISOR CONFIG (X-RAY MODE)
# ==========================================
if nav == "Supervisor Config":
    st.title("🛠️ Admin Config (X-Ray Mode)")
    if st.text_input("Password", type="password") == "admin123":
        t1, t2 = st.tabs(["Panel 11", "Screen"])
        with t1:
            st.info("Upload PDF-converted Excel.")
            up = st.file_uploader("Upload Excel", type=['xlsx'])
            if up:
                new_df, msg, debug_df = matrix_parser_v3(io.BytesIO(up.getvalue()))
                if new_df is not None:
                    count_cols = new_df.shape[1] - 1
                    st.success(f"✅ Extracted {count_cols} Antigens.")
                    st.session_state.panel_11 = new_df
                    if st.button("Update"): st.rerun()
                else:
                    st.error(f"❌ Error: {msg}")
                    # --- X-RAY VISION ---
                    with st.expander("👀 DEBUG: See what Python sees (X-RAY)", expanded=True):
                        st.write("If this table looks empty or messed up, your file converter is the problem.")
                        st.dataframe(debug_df.head(25) if debug_df is not None else "No Data")
            
            st.write("#### Live Grid:")
            edited_panel = st.data_editor(st.session_state.panel_11.fillna(0), height=450, use_container_width=True, hide_index=True)
            if st.button("Save Changes"):
                st.session_state.panel_11 = edited_panel; st.success("Saved.")
        
        with t2:
            st.session_state.panel_3 = st.data_editor(st.session_state.panel_3, hide_index=True)

# ==========================================
# 5. USER WORKSTATION
# ==========================================
else:
    st.markdown("<div class='hospital-header'><h1>Maternity & Children Hospital - Tabuk</h1><h4>Serology Workstation</h4></div>", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mrn=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    L, R = st.columns([1, 2.5])
    with L:
        st.subheader("1. Control")
        ac_val = st.radio("AC", ["Negative","Positive"], horizontal=True)
        if ac_val == "Positive": st.error("STOP: DAT Required."); st.stop()
        st.write("---")
        for s in ["I", "II", "III"]: st.session_state.inputs_s[f"s{s}"] = st.selectbox(f"Scn {s}", ["Neg", "w+", "1+", "2+", "3+"], key=f"k_{s}")
        if st.button("Set Neg"): bulk_set("Neg")
    with R:
        st.subheader("2. Panel")
        grd = st.columns(6)
        in_map = {}
        for i in range(1, 12):
            k=f"c{i}"
            v=grd[(i-1)%6].selectbox(f"C{i}",["Neg","w+","1+","2+"],key=f"u_{i}",index=["Neg","w+","1+","2+"].index(st.session_state.inputs[k]))
            st.session_state.inputs[k]=v
            in_map[i]=0 if v=="Neg" else 1
    
    st.divider()
    if st.checkbox("🔍 Analyze"):
        r11 = [st.session_state.panel_11.iloc[i].to_dict() for i in range(11)]
        r3 = [st.session_state.panel_3.iloc[i].to_dict() for i in range(3)]
        ruled = set()
        for ag in antigens_order:
            for idx, s in in_map.items():
                if s==0 and can_rule_out(ag, r11[idx-1]): ruled.add(ag); break
        s_m = {"I":0,"II":1,"III":2}
        for k,v in st.session_state.inputs_s.items():
            if v=="Neg":
                for ag in antigens_order:
                    if ag not in ruled and can_rule_out(ag, r3[s_m[k[1:]]]): ruled.add(ag)
        
        mtch = []
        for c in [x for x in antigens_order if x not in ruled]:
            mis=False
            for i,s in in_map.items():
                if s>0 and r11[i-1].get(c,0)==0: mis=True
            if not mis: mtch.append(c)
            
        if not mtch: st.error("Inconclusive.")
        else:
            allow=True
            for m in mtch:
                ps, p, n, met = check_r3(m, r11, st.session_state.inputs, r3, st.session_state.inputs_s, st.session_state.extra_cells)
                st.markdown(f"<div class='status-{'pass' if ps else 'fail'}'><b>Anti-{m}:</b> {met} ({p} P/{n} N)</div>", unsafe_allow_html=True)
                if not ps: allow=False
            if allow:
                if st.button("Print Report"):
                    rpt = f"<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'>Pt: {nm} ({mrn})<hr>Res: Anti-{', '.join(mtch)}<br>Valid Rule of 3.<br><br>Sig: ______</div><div class='consultant-footer'><span style='color:#800;font-weight:bold'>Dr. Haitham Ismail</span></div></div><script>window.print()</script>"
                    st.markdown(rpt, unsafe_allow_html=True)
            else:
                with st.expander("Add Cell"):
                    id=st.text_input("ID"); rs=st.selectbox("R",["Neg","Pos"]); ph={}
                    cols=st.columns(len(mtch))
                    for i,mm in enumerate(mtch):
                        r=cols[i].radio(mm,["+","0"],key=f"ex_{mm}")
                        ph[mm]=1 if r=="+" else 0
                    if st.button("Add"):
                        st.session_state.extra_cells.append({"src":id,"score":1 if rs=="Pos" else 0,"pheno":ph,"s":1 if rs=="Pos" else 0}); st.rerun()
