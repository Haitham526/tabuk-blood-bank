import streamlit as st
import pandas as pd
import io
from datetime import date

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
        .results-box { border: 2px solid #333; padding: 15px; margin-top: 20px; font-family: 'Times New Roman'; }
        .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; }
    }
    .hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    
    .signature-badge {
        position: fixed; bottom: 10px; right: 15px; font-family: 'Georgia', serif; font-size: 12px; color: #8B0000;
        background: rgba(255,255,255,0.95); padding: 5px 10px; border: 1px solid #eecaca; border-radius: 5px; z-index:99;
    }
    .status-pass { background-color: #d1e7dd; padding: 8px; border-radius: 5px; color: #0f5132; border: 1px solid #a3cfbb; }
    .status-fail { background-color: #f8d7da; padding: 8px; border-radius: 5px; color: #842029; border: 1px solid #f1aeb5; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='signature-badge no-print'><b>Dr. Haitham Ismail</b><br>Clinical Hematology/Transfusion Consultant</div>", unsafe_allow_html=True)

# Data Structure
antigens_order = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
allele_pairs = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S'}
STRICT_DOSAGE = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]

# State
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
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

def parse_excel_strict_case(file_bytes, limit_rows):
    xls = pd.ExcelFile(file_bytes)
    
    for sheet in xls.sheet_names:
        df = pd.read_excel(file_bytes, sheet_name=sheet, header=None)
        
        best_row_idx = -1
        best_row_matches = 0
        col_map = {}
        
        # 1. SCAN FOR HEADERS (FIXED VARIABLE NAME HERE)
        for r in range(min(30, len(df))):
            temp_map = {}
            current_matches_count = 0  # Fixed Variable Name
            
            for c in range(min(60, len(df.columns))):
                val_raw = str(df.iloc[r, c]).strip().replace(" ","")
                val_upper = val_raw.upper()
                
                det = None
                # Case Sensitive Check
                if val_raw in ["C","c","E","e","S","s","K","k"]: det = val_raw
                # Upper checks
                elif val_upper in ["D","RHD"]: det = "D"
                elif val_upper in [x.upper() for x in antigens_order if x not in ["C","c","E","e","S","s","K","k"]]:
                    for real_ag in antigens_order:
                        if real_ag.upper() == val_upper: det = real_ag; break
                
                if det and det not in temp_map:
                    temp_map[det] = c
                    current_matches_count += 1
            
            # Confidence Threshold (using corrected variable)
            if current_matches_count > best_row_matches:
                best_row_matches = current_matches_count
                best_row_idx = r
                col_map = temp_map
        
        # 2. EXTRACT DATA
        if best_row_matches >= 3:
            final_data = []
            curr = best_row_idx + 1
            cnt = 0
            
            while cnt < limit_rows and curr < len(df):
                has_data = False
                # Try finding D or C to confirm row
                d_idx = col_map.get("D") or col_map.get("C")
                
                if d_idx is not None:
                    check_val = str(df.iloc[curr, d_idx]).lower()
                    if any(x in check_val for x in ['+', '0', '1', 'w']): has_data = True
                
                if has_data:
                    cid = f"Cell {cnt+1}" if limit_rows==11 else f"Scn {['I','II','III'][cnt]}"
                    row_d = {"ID": cid}
                    for ag in antigens_order:
                        v = 0
                        if ag in col_map:
                            v = normalize_val(df.iloc[curr, col_map[ag]])
                        row_d[ag] = int(v)
                    final_data.append(row_d)
                    cnt += 1
                curr += 1
            
            if cnt >= 1:
                return pd.DataFrame(final_data), f"Success from '{sheet}'"

    return None, "Structure not found. Please Edit Manually."

def can_rule_out(ag, pheno):
    if pheno.get(ag, 0) == 0: return False
    if ag in STRICT_DOSAGE:
        partner = allele_pairs.get(ag)
        if partner and pheno.get(partner, 0) == 1: return False
    return True

def bulk_set(val):
    for i in range(1, 12): st.session_state.inputs[f"c{i}"] = val

def check_r3(cand, rows, ip, rows_s, inp_s, ex):
    p,n=0,0
    # Panel
    for i in range(1,12):
        s=1 if ip[i]!="Neg" else 0
        h=rows[i-1].get(cand,0)
        if h==1 and s==1: p+=1
        if h==0 and s==0: n+=1
    # Screen
    for i,l in enumerate(["I","II","III"]):
        s=1 if inp_s[f"s{l}"]!="Neg" else 0
        h=rows_s[i].get(cand,0)
        if h==1 and s==1: p+=1
        if h==0 and s==0: n+=1
    # Ext
    for c in ex:
        if c['score']==1 and c['pheno'].get(cand,0)==1: p+=1
        if c['score']==0 and c['pheno'].get(cand,0)==0: n+=1
    ok=(p>=3 and n>=3) or (p>=2 and n>=3)
    mt="Standard (3/3)" if (p>=3 and n>=3) else ("Modified" if ok else "Not Met")
    return ok,p,n,mt

# ==========================================
# 3. UI SIDEBAR
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Admin Config"])
    st.divider()
    if st.button("Reset All"): st.session_state.extra_cells=[]; st.rerun()

# ----------------- ADMIN -----------------
if nav == "Admin Config":
    st.title("🛠️ Master Configuration")
    if st.text_input("Password", type="password") == "admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening"])
        with t1:
            st.info("Upload Excel (Fix: Case Sensitive Matching)")
            up1 = st.file_uploader("Upload P11", type=["xlsx"])
            if up1:
                df1, m1 = parse_excel_strict_case(io.BytesIO(up1.getvalue()), 11)
                if df1 is not None:
                    st.success(m1); st.session_state.panel_11 = df1; st.rerun()
                else: st.error(m1)
            
            st.write("Edit Grid:")
            ed1 = st.data_editor(st.session_state.panel_11.fillna(0), hide_index=True)
            if st.button("Save P11"): st.session_state.panel_11=ed1; st.success("Saved")
            
        with t2:
            st.info("Upload Screening")
            up2 = st.file_uploader("Upload Screen", type=["xlsx"])
            if up2:
                df2, m2 = parse_excel_strict_case(io.BytesIO(up2.getvalue()), 3)
                if df2 is not None:
                    st.success(m2); st.session_state.panel_3 = df2; st.rerun()
            ed2 = st.data_editor(st.session_state.panel_3.fillna(0), hide_index=True)
            if st.button("Save Scr"): st.session_state.panel_3=ed2; st.success("Saved")

# ----------------- USER -----------------
else:
    st.markdown("<div class='hospital-header'><h1>Maternity & Children Hospital - Tabuk</h1><h4>Serology Workstation</h4></div>", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    colL, colR = st.columns([1, 2])
    with colL:
        ac_val = st.radio("Auto Control (AC)", ["Negative","Positive"])
        if ac_val=="Positive": st.error("STOP: DAT Required"); st.stop()
        st.write("---")
        for x in ["I","II","III"]: st.session_state.inputs_s[f"s{x}"]=st.selectbox(f"Scn {x}",["Neg","w+","1+","2+"], key=f"bx{x}")
        if st.button("Set All Neg"): bulk_set("Neg")
    
    with colR:
        g = st.columns(6)
        in_map = {}
        for i in range(1, 12):
            v = g[(i-1)%6].selectbox(f"C{i}", ["Neg","w+","1+","2+"], key=f"cx{i}")
            st.session_state.inputs[f"c{i}"]=v
            in_map[i]=0 if v=="Neg" else 1
            
    st.divider()
    if st.checkbox("🔍 Analyze"):
        r11=[st.session_state.panel_11.iloc[i].to_dict() for i in range(11)]
        r3=[st.session_state.panel_3.iloc[i].to_dict() for i in range(3)]
        ruled=set()
        
        for ag in antigens_order:
            for idx, sc in in_map.items():
                if sc==0 and can_rule_out(ag, r11[idx-1]): ruled.add(ag); break
        smap={"I":0,"II":1,"III":2}
        for k,v in st.session_state.inputs_s.items():
            if v=="Neg":
                for ag in antigens_order:
                    if ag not in ruled and can_rule_out(ag, r3[smap[k[1:]]]): ruled.add(ag)
        
        matches = []
        for cand in [x for x in antigens_order if x not in ruled]:
            mis = False
            for idx, sc in in_map.items():
                if sc>0 and r11[idx-1].get(cand,0)==0: mis=True
            if not mis: matches.append(cand)
            
        if not matches: st.error("Inconclusive.")
        else:
            final_allow = True
            st.subheader("3. Result")
            for m in matches:
                pas,p,n,met = check_r3(m,r11,st.session_state.inputs,r3,st.session_state.inputs_s,st.session_state.extra_cells)
                st.markdown(f"<div class='status-{'pass' if pas else 'fail'}'><b>Anti-{m}:</b> {met} ({p} Pos, {n} Neg)</div>", unsafe_allow_html=True)
                if not pas: final_allow=False
                
            if final_allow:
                if st.button("🖨️ Report"):
                    rpt=f"<div class='print-only'><center><h2>MCH Tabuk</h2></center><div class='results-box'>Pt: {nm} ({mr})<hr>Res: Anti-{', '.join(matches)}<br>Valid Rule of 3.<br><br>Sig: _______</div></div><script>window.print()</script>"
                    st.markdown(rpt, unsafe_allow_html=True)
            else:
                st.warning("Confirmation needed:")
                with st.expander("Add Cell"):
                    id=st.text_input("ID"); rs=st.selectbox("R",["Neg","Pos"]); ph={}
                    cx=st.columns(len(matches))
                    for i,m in enumerate(matches): ph[m]=1 if cx[i].checkbox(m) else 0
                    if st.button("Add"):
                        st.session_state.extra_cells.append({"src":id,"score":1 if rs=="Pos" else 0,"pheno":ph,"res":1 if rs=="Pos" else 0}); st.rerun()
