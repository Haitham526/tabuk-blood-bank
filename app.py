import streamlit as st
import pandas as pd
import io
from datetime import date

# ==========================================
# 1. SETUP
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🏥")

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
    
    .signature-badge {
        position: fixed; bottom: 10px; right: 15px; font-family: 'Georgia', serif; font-size: 12px; color: #8B0000;
        background: rgba(255,255,255,0.95); padding: 5px 10px; border: 1px solid #eecaca; border-radius: 5px; z-index:99;
    }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    .status-pass { background-color: #d1e7dd; padding: 8px; color: #0f5132; }
    .status-fail { background-color: #f8d7da; padding: 8px; color: #842029; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='signature-badge no-print'><b>Dr. Haitham Ismail</b><br>Clinical Consultant</div>", unsafe_allow_html=True)

# CONFIG
ANTIGENS = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
STRICT_DOSAGE = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]
ALLELE_PAIRS = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S'}

# STATE
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a: 0 for a in ANTIGENS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a: 0 for a in ANTIGENS}} for i in ["I","II","III"]])
if 'res' not in st.session_state: st.session_state.res = {f"c{i}": "Neg" for i in range(1, 12)}
if 'scr' not in st.session_state: st.session_state.scr = {f"s{i}": "Neg" for i in ["I","II","III"]}
if 'ext' not in st.session_state: st.session_state.ext = []
if 'admin' not in st.session_state: st.session_state.admin = False

# ==========================================
# 2. LOGIC (MATRIX SCANNER RESTORED + C/c Fix)
# ==========================================
def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

def matrix_scan_final(file_bytes, limit_rows=11):
    try:
        # Load ALL Sheets
        xls = pd.ExcelFile(file_bytes)
        for sheet in xls.sheet_names:
            df = pd.read_excel(file_bytes, sheet_name=sheet, header=None)
            
            # --- 1. SEARCH FOR COLUMN COORDINATES ---
            # Search entire top section (first 25 rows, 60 cols)
            col_coords = {}
            header_row_candidate = -1
            
            # We assume header is where we find > 3 antigens
            for r in range(min(25, len(df))):
                row_matches = 0
                temp_map = {}
                for c in range(min(60, len(df.columns))):
                    val = str(df.iloc[r, c]).strip().replace(" ","").replace("(","").replace(")","")
                    
                    detected = None
                    
                    # ---- STRICT MATCHING HERE (CASE SENSITIVE FOR c, C, e, E...) ----
                    if val in ["c", "C", "e", "E", "s", "S", "k", "K"]:
                        detected = val # Keep the case (Small is small, Big is big)
                    
                    # For others, use Upper
                    else:
                        val_up = val.upper()
                        if val_up in [x.upper() for x in ANTIGENS if x not in ["c","C","e","E","s","S","k","K"]]:
                            # Map back to official case
                            for off in ANTIGENS:
                                if off.upper() == val_up: detected = off; break
                        # Aliases
                        elif val_up in ["RHD","D"]: detected = "D"
                        
                    if detected:
                        temp_map[detected] = c
                        row_matches += 1
                        
                if row_matches >= 3:
                    header_row_candidate = r
                    # Merge temp_map into main map (overwriting works)
                    col_coords.update(temp_map)
            
            # If headers not found, continue next sheet
            if len(col_coords) < 3: continue
            
            # --- 2. EXTRACT DATA BELOW HEADER ---
            # Assuming data is somewhere below the lowest detected header
            start_search = header_row_candidate + 1
            final_data = []
            extracted_cnt = 0
            
            # We look for rows that have data in D column
            d_idx = col_coords.get("D") or col_coords.get("C") # Fallback to C
            
            curr = start_search
            while extracted_cnt < limit_rows and curr < len(df):
                is_valid = False
                if d_idx is not None:
                    check_v = str(df.iloc[curr, d_idx]).lower()
                    if any(x in check_v for x in ['+', '0', '1', 'w']): is_valid = True
                
                if is_valid:
                    lbl = f"C-{extracted_cnt+1}" if limit_rows==11 else f"Scn-{['I','II','III'][extracted_cnt]}"
                    row_dict = {"ID": lbl}
                    for ag in ANTIGENS:
                        v = 0
                        if ag in col_coords:
                            v = normalize(df.iloc[curr, col_coords[ag]])
                        row_dict[ag] = int(v)
                    final_data.append(row_dict)
                    extracted_cnt += 1
                curr += 1
            
            if extracted_cnt >= 1:
                return pd.DataFrame(final_data), f"Read from {sheet} OK"
                
        return None, "Structure not found. Headers were missing."
    except Exception as e: return None, str(e)

# Logic Stubs
def can_out(ag, pheno):
    if pheno.get(ag, 0) == 0: return False
    if ag in STRICT_DOSAGE:
        pr = ALLELE_PAIRS.get(ag)
        if pr and pheno.get(pr, 0) == 1: return False
    return True

def chk_rule(cand, r11, res11, r3, res3, extra):
    pos_cnt, neg_cnt = 0, 0
    # Panel
    for i in range(1, 12):
        s = 1 if res11[f"c{i}"] != "Neg" else 0
        h = r11.iloc[i-1].get(cand, 0)
        if s==1 and h==1: pos_cnt += 1
        if s==0 and h==0: neg_cnt += 1
    # Screen
    for i, lbl in enumerate(["I","II","III"]):
        s = 1 if res3[f"s{lbl}"] != "Neg" else 0
        h = r3.iloc[i].get(cand, 0)
        if s==1 and h==1: pos_cnt += 1
        if s==0 and h==0: neg_cnt += 1
    # Extra
    for c in extra:
        if c['s']==1 and c['p'].get(cand,0)==1: pos_cnt+=1
        if c['s']==0 and c['p'].get(cand,0)==0: neg_cnt+=1
        
    pass_r = (pos_cnt>=3 and neg_cnt>=3) or (pos_cnt>=2 and neg_cnt>=3)
    method = "Standard Rule" if (pos_cnt>=3 and neg_cnt>=3) else ("Modified" if pass_r else "Failed")
    return pass_r, pos_cnt, neg_cnt, method

def set_all(v):
    for i in range(1, 12): st.session_state.res[f"c{i}"] = v

# ==========================================
# 3. SIDEBAR
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Navigation", ["User Workstation", "Supervisor Config"])
    if st.button("Reset Extras"): st.session_state.ext=[]; st.rerun()

# --- ADMIN ---
if nav == "Supervisor Config":
    st.title("🛠️ Master Config (Matrix Restored)")
    if st.text_input("Password", type="password") == "admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening"])
        with t1:
            up1 = st.file_uploader("Upload Panel 11", type=["xlsx"])
            if up1:
                df1, m1 = matrix_scan_final(io.BytesIO(up1.getvalue()), 11)
                if df1 is not None:
                    st.success(m1); st.session_state.p11 = df1; st.rerun()
                else: st.error(m1)
            e1 = st.data_editor(st.session_state.p11, hide_index=True)
            if st.button("Save P11"): st.session_state.p11 = e1; st.success("Saved")
        
        with t2:
            up2 = st.file_uploader("Upload Screen 3", type=["xlsx"])
            if up2:
                df2, m2 = matrix_scan_final(io.BytesIO(up2.getvalue()), 3)
                if df2 is not None:
                    st.success(m2); st.session_state.p3 = df2; st.rerun()
                else: st.error(m2)
            e2 = st.data_editor(st.session_state.p3, hide_index=True)
            if st.button("Save Scr"): st.session_state.p3 = e2; st.success("Saved")

# --- USER ---
else:
    st.markdown("""<div class='hospital-header'><h1>Maternity & Children Hospital - Tabuk</h1><h4>Serology Workstation</h4></div>""", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    # 2 Col Layout
    L, R = st.columns([1, 2])
    with L:
        ac = st.radio("Auto Control", ["Negative", "Positive"])
        if ac == "Positive": st.error("STOP: DAT Required."); st.stop()
        st.write("---")
        for x in ["I","II","III"]: st.session_state.scr[f"s{x}"]=st.selectbox(x, ["Neg","w+","1+","2+"], key=f"bx{x}")
        if st.button("Set Neg"): set_all("Neg")
    
    with R:
        cols = st.columns(6)
        in_map = {}
        for i in range(1, 12):
            val = cols[(i-1)%6].selectbox(f"{i}", ["Neg","w+","1+","2+","3+"], key=f"cx{i}")
            st.session_state.res[f"c{i}"] = val
            in_map[i] = 0 if val=="Neg" else 1
            
    st.divider()
    if st.checkbox("🔍 Analyze"):
        # Calc
        p11_list = [st.session_state.p11.iloc[i].to_dict() for i in range(11)]
        p3_list = [st.session_state.p3.iloc[i].to_dict() for i in range(3)]
        ruled = set()
        
        # Rule Out
        for ag in ANTIGENS:
            for i, score in in_map.items():
                if score == 0 and can_out(ag, p11_list[i-1]): ruled.add(ag); break
        scr_map = {"I":0,"II":1,"III":2}
        for k, v in st.session_state.scr.items():
            if v == "Neg" and k.startswith("s"):
                for ag in ANTIGENS:
                    if ag not in ruled and can_out(ag, p3_list[scr_map[k[1:]]]): ruled.add(ag)
        
        matches = []
        for cand in [x for x in ANTIGENS if x not in ruled]:
            miss = False
            for i, score in in_map.items():
                if score > 0 and p11_list[i-1].get(cand, 0) == 0: miss = True
            if not miss: matches.append(cand)
            
        if not matches: st.error("Inconclusive.")
        else:
            allow_final = True
            for m in matches:
                ok, p, n, msg = chk_rule(m, st.session_state.p11, st.session_state.res, st.session_state.p3, st.session_state.scr, st.session_state.ext)
                st.markdown(f"<div class='status-{'pass' if ok else 'fail'}'><b>Anti-{m}:</b> {msg} ({p}/{n})</div>", unsafe_allow_html=True)
                if not ok: allow_final = False
            
            if allow_final:
                if st.button("🖨️ Print"):
                    ht=f"<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'>Pt:{nm}|{mr}<hr>Res: Anti-{', '.join(matches)}<br>Valid (Rule of 3).<br><br>Sign: _________</div><div class='consultant-footer'><span style='color:darkred;font-weight:bold'>Dr. Haitham Ismail</span></div></div><script>window.print()</script>"
                    st.markdown(ht, unsafe_allow_html=True)
            else:
                with st.expander("Add Cell"):
                    idx=st.text_input("ID"); rs=st.selectbox("R",["Neg","Pos"]); ph={}
                    cols=st.columns(len(matches))
                    for i,mm in enumerate(matches):
                        if cols[i].checkbox(mm): ph[mm]=1
                        else: ph[mm]=0
                    if st.button("Confirm"):
                        st.session_state.ext.append({"src":idx,"score":1 if rs=="Pos" else 0,"ph":ph,"s":1 if rs=="Pos" else 0}); st.rerun()
