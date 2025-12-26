import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. SETUP
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🏥")

st.markdown("""
<style>
    /* Print & Header */
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .block-container { padding: 0 !important; }
        .print-only { display: block !important; }
        .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; }
        .results-box { border: 2px solid #333; padding: 15px; font-family: 'Times New Roman'; margin-top: 20px; }
    }
    .hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    
    /* Footer */
    .signature-badge {
        position: fixed; bottom: 10px; right: 15px; text-align: right;
        font-family: 'Georgia', serif; font-size: 12px; color: #8B0000;
        background-color: rgba(255, 255, 255, 0.95); padding: 8px 15px;
        border-radius: 8px; border: 1px solid #eecaca; z-index: 9999;
    }
    .dr-name { font-weight: bold; font-size: 15px; display: block; margin-bottom: 3px;}
    
    /* Colors */
    .status-pass { background-color: #d1e7dd; padding: 10px; border-radius: 5px; color: #0f5132; border-left: 5px solid #198754; margin-bottom:5px; }
    .status-fail { background-color: #f8d7da; padding: 10px; border-radius: 5px; color: #842029; border-left: 5px solid #dc3545; margin-bottom:5px; }
</style>
""", unsafe_allow_html=True)

# Footer
st.markdown("""<div class='signature-badge no-print'><span class='dr-name'>Dr. Haitham Ismail</span>Clinical Hematology/Oncology & Transfusion Medicine Consultant</div>""", unsafe_allow_html=True)

# Defs
antigens_order = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
ANTIGEN_ALIASES = { "D": ["D", "Rh(D)", "RH1"], "C": ["C", "rh'", "RH2"], "E": ["E", "rh''", "RH3"], "c": ["c", "hr'", "RH4"], "e": ["e", "hr''", "RH5"], "Fya": ["Fya", "Fy(a)"], "Fyb": ["Fyb", "Fy(b)"], "Jka": ["Jka", "Jk(a)"], "Jkb": ["Jkb", "Jk(b)"], "Lea": ["Lea", "Le(a)"], "Leb": ["Leb", "Le(b)"], "P1": ["P1", "P"], "M": ["M", "MN"], "N": ["N"], "S": ["S"], "s": ["s"] }
allele_pairs = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Kpa':'Kpb', 'Kpb':'Kpa', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S', 'Lea':'Leb', 'Leb':'Lea'}
STRICT_DOSAGE_SYSTEMS = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]

# --- INITIAL STATE ---
if 'panel_11' not in st.session_state:
    st.session_state.panel_11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in antigens_order}} for i in range(11)])
if 'panel_3' not in st.session_state:
    st.session_state.panel_3 = pd.DataFrame([{"ID": f"Scn {i}", **{ag: 0 for ag in antigens_order}} for i in ["I", "II", "III"]])
if 'inputs' not in st.session_state: st.session_state.inputs = {f"c{i}": "Neg" for i in range(1, 12)}
if 'inputs_screen' not in st.session_state: st.session_state.inputs_screen = {f"s{i}": "Neg" for i in ["I", "II", "III"]}
if 'extra_cells' not in st.session_state: st.session_state.extra_cells = []

# ==========================================
# 2. LOGIC
# ==========================================
def find_column_in_df(df, target_ag):
    for col in df.columns:
        if str(col).strip() == target_ag: return col
    aliases = ANTIGEN_ALIASES.get(target_ag, [])
    for alias in aliases:
        for col in df.columns:
            clean_c = str(col).replace("(","").replace(")","").replace(" ","").upper()
            clean_a = alias.upper().replace("(","").replace(")","").replace(" ","")
            if clean_c == clean_a: return col
    return None

def normalize_val(val):
    s = str(val).lower().strip()
    return 1 if s in ['+','1','pos','yes','1.0'] else 0

def can_rule_out(ag, pheno):
    if pheno.get(ag,0)==0: return False
    if ag in STRICT_DOSAGE_SYSTEMS:
        pair = allele_pairs.get(ag)
        if pair and pheno.get(pair,0)==1: return False
    return True

def bulk_set(val):
    for i in range(1, 12): st.session_state.inputs[f"c{i}"] = val

def check_rule(cand, r11, in11, r3, in3, extra):
    pos_r, neg_r = 0, 0
    # Panel
    for i in range(1,12):
        score = 1 if in11[i]!="Neg" else 0
        has = r11[i-1].get(cand,0)
        if has==1 and score==1: pos_r+=1
        if has==0 and score==0: neg_r+=1
    # Screen
    scrs = ["I", "II", "III"]
    for i, s in enumerate(scrs):
        score = 1 if in3[f"s{s}"]!="Neg" else 0
        has = r3[i].get(cand,0)
        if has==1 and score==1: pos_r+=1
        if has==0 and score==0: neg_r+=1
    # Extra
    for c in extra:
        if c['score']==1 and c['pheno'].get(cand,0)==1: pos_r+=1
        if c['score']==0 and c['pheno'].get(cand,0)==0: neg_r+=1
    
    passed = (pos_r>=3 and neg_r>=3) or (pos_r>=2 and neg_r>=3)
    method = "Standard (3/3)" if (pos_r>=3 and neg_r>=3) else "Modified (2/3)" if passed else "Fail"
    return passed, pos_r, neg_r, method

# ==========================================
# 3. SIDEBAR NAV
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    st.caption("V21.1 Fixed")
    
    st.write("### Menu")
    app_mode = st.radio("Go to:", ["🔵 User Workstation", "🔴 Supervisor Config"])
    
    st.write("---")
    if st.button("Reset / Clear Extra Cells"):
        st.session_state.extra_cells = []
        st.rerun()

# ==========================================
# 4. SUPERVISOR
# ==========================================
if app_mode == "🔴 Supervisor Config":
    st.title("🛠️ Master Configuration")
    pwd = st.text_input("Enter Password", type="password")
    
    if pwd == "admin123":
        st.success("Access Granted")
        
        tab_p11, tab_scr = st.tabs(["Panel 11", "Screening 3"])
        
        with tab_p11:
            st.info("Upload Excel or Edit Grid")
            c_up, c_ed = st.columns([1, 2])
            
            with c_up:
                # ---------------- CRITICAL FIX AREA ----------------
                up_file = st.file_uploader("Upload Excel", type=["xlsx","xls"])
                
                if up_file:
                    try:
                        raw = pd.read_excel(up_file)
                        clean_data = []
                        for i in range(min(11, len(raw))):
                            r = {"ID": f"Cell {i+1}"}
                            for ag in antigens_order:
                                cn = find_column_in_df(raw, ag)
                                val = normalize_val(raw.iloc[i][cn]) if cn else 0
                                r[ag] = int(val) # Force Integer
                            clean_data.append(r)
                        
                        # UPDATE AND RERUN
                        st.session_state.panel_11 = pd.DataFrame(clean_data)
                        st.success("File Processed! Refreshing view...")
                        st.rerun() # <<< THIS MAGIC COMMAND FIXES THE EMPTY TABLE >>>
                        
                    except Exception as e: st.error(f"Error: {e}")
                # ---------------------------------------------------

            with c_ed:
                st.write("**Current Data (Editable):**")
                edited = st.data_editor(st.session_state.panel_11, height=450, hide_index=True, use_container_width=True, column_config={"ID": st.column_config.TextColumn(disabled=True)})
                
                if st.button("Save Changes to Memory"):
                    st.session_state.panel_11 = edited
                    st.success("Saved.")

        with tab_scr:
            st.write("Screen Cells I, II, III")
            st.session_state.panel_3 = st.data_editor(st.session_state.panel_3, hide_index=True)
            
    elif pwd: st.error("Wrong Password")

# ==========================================
# 5. USER WORKSTATION
# ==========================================
elif app_mode == "🔵 User Workstation":
    st.markdown("""<div class='hospital-header'><h1>Maternity & Children Hospital - Tabuk</h1><h4>Blood Bank Serology</h4></div>""", unsafe_allow_html=True)
    
    # Inputs
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mrn=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    # Entry
    L, R = st.columns([1, 2.5])
    with L:
        st.subheader("1. Screen/AC")
        for x in ["I","II","III"]:
            k=f"s{x}"
            st.session_state.inputs_screen[k]=st.selectbox(f"Scn {x}",["Neg","w+","1+","2+","3+","4+"], key=f"us_{x}")
        st.write("---")
        ac=st.radio("AC", ["Negative","Positive"], horizontal=True)
        if st.button("All Neg"): bulk_set("Neg")
        if st.button("All Pos"): bulk_set("2+")
    
    with R:
        st.subheader("2. Panel")
        colss = st.columns(6)
        in11 = {}
        cnt=0
        for i in range(1,12):
            k=f"c{i}"
            v=colss[(i-1)%6].selectbox(f"C{i}",["Neg","w+","1+","2+","3+","4+"], key=f"up_{i}", index=["Neg","w+","1+","2+","3+","4+"].index(st.session_state.inputs[k]))
            st.session_state.inputs[k]=v
            sc=0 if v=="Neg" else 1
            in11[i]=sc
            if sc: cnt+=1
            
    # Logic
    st.divider()
    
    if ac == "Positive":
        st.error("🚨 Auto Control POSITIVE. DAT Investigation Required.")
        st.info("Suspect: WAIHA, CAS, or Delayed Transfusion Reaction. Refer to Physician.")
    else:
        if st.checkbox("🔍 Analyze"):
            # Prepare Logic Rows
            rows11 = [st.session_state.panel_11.iloc[i].to_dict() for i in range(11)]
            rows3 = [st.session_state.panel_3.iloc[i].to_dict() for i in range(3)]
            
            if cnt==11: st.warning("⚠️ Pan-Agglutination: Suspect High Frequency Antibody.")
            
            # Exclusion (Panel)
            ruled = set()
            for ag in antigens_order:
                for idx, sc in in11.items():
                    if sc==0 and can_rule_out(ag, rows11[idx-1]):
                        ruled.add(ag); break
            
            # Exclusion (Screen)
            sm = {"I":0, "II":1, "III":2}
            for k,v in st.session_state.inputs_screen.items():
                if v=="Neg":
                    p3 = rows3[sm[k[1:]]]
                    for ag in antigens_order:
                        if ag not in ruled and can_rule_out(ag, p3): ruled.add(ag)
                        
            cands = [x for x in antigens_order if x not in ruled]
            match = []
            
            # Inclusion
            for c in cands:
                mis = False
                for idx, sc in in11.items():
                    if sc>0 and rows11[idx-1].get(c,0)==0: mis=True
                if not mis: match.append(c)
                
            if not match: st.error("Inconclusive / All Ruled Out.")
            else:
                allow = True
                for m in match:
                    ok, p, n, mt = check_rule(m, rows11, st.session_state.inputs, rows3, st.session_state.inputs_screen, st.session_state.extra_cells)
                    st.markdown(f"<div class='status-{'pass' if ok else 'fail'}'><b>Anti-{m}:</b> {mt} ({p}/{n})</div>", unsafe_allow_html=True)
                    if not ok: allow=False
                
                if allow:
                    if st.button("🖨️ Report"):
                        ht = f"<div class='print-only'><br><center><h2>Maternity & Children Hospital - Tabuk</h2></center><div class='results-box'>Pt: {nm} | MRN: {mrn}<br>Tech: {tc} | Date: {dt}<hr><b>Conclusion:</b> Anti-{', '.join(match)} Detected.<br>Probability met.<br>Note: Phenotype Patient (Negative).<br><br><br>Signature: ___________</div><div class='consultant-footer'><span style='color:darkred;font-weight:bold'>Dr. Haitham Ismail</span><br>Consultant</div></div><script>window.print()</script>"
                        st.markdown(ht, unsafe_allow_html=True)
                else:
                    st.info("Validation needed (Rule not met). Add Extra Cells.")
                    with st.expander("➕ Add Cell"):
                        xc1,xc2,xc3=st.columns([1,1,2])
                        nid=xc1.text_input("ID"); nres=xc2.selectbox("Res",["Neg","Pos"])
                        tp={}
                        cols=xc3.columns(len(match))
                        for idx,m in enumerate(match):
                            rr=cols[idx].radio(m,["+","0"],key=f"xa_{m}")
                            tp[m]=1 if rr=="+" else 0
                        if st.button("Add"):
                            st.session_state.extra_cells.append({"src":nid, "score":1 if nres=="Pos" else 0, "pheno":tp})
                            st.rerun()
