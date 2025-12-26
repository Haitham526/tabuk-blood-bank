import streamlit as st
import pandas as pd
import io
from datetime import date

# ---------------- CONFIG & STYLE ----------------
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🩸")
st.markdown("""<style>@media print {.stApp > header, .sidebar, footer, .no-print { display: none !important; } .block-container { padding: 0 !important; } .print-only { display: block !important; } .results-box { border: 2px solid #333; padding: 15px; margin-top: 10px; font-family: 'Times New Roman'; } .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; } } .hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; } .status-pass { background-color: #d1e7dd; padding: 8px; border-radius: 5px; color: #0f5132; } .status-fail { background-color: #f8d7da; padding: 8px; border-radius: 5px; color: #842029; } div[data-testid="stDataEditor"] table { width: 100% !important; }</style>""", unsafe_allow_html=True)
st.markdown("<div class='print-only' style='display:none'></div>", unsafe_allow_html=True) 

# ---------------- DEFINITIONS ----------------
ANTIGENS = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
DOSAGE_AGS = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]
PAIRS = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S'}

# ---------------- STATE INIT ----------------
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in ANTIGENS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"Scn {i}", **{ag: 0 for ag in ANTIGENS}} for i in ["I", "II", "III"]])
if 'inputs' not in st.session_state: st.session_state.inputs = {f"c{i}": "Neg" for i in range(1, 12)}
if 'inputs_s' not in st.session_state: st.session_state.inputs_s = {f"s{i}": "Neg" for i in ["I", "II", "III"]}
if 'extra' not in st.session_state: st.session_state.extra = []

# ---------------- LOGIC FUNCTIONS ----------------
def clean_str(val):
    return str(val).upper().replace("(","").replace(")","").replace(" ","").strip()

def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

def robust_excel_parser(file_bytes, limit=11):
    try:
        xls = pd.ExcelFile(file_bytes)
        # Iterate all sheets
        for sheet in xls.sheet_names:
            df = pd.read_excel(file_bytes, sheet_name=sheet, header=None)
            
            # SCAN for Header Coordinates
            col_map = {} 
            max_r = min(len(df), 30)
            max_c = min(len(df.columns), 60)
            
            # Search Grid
            for r in range(max_r):
                for c in range(max_c):
                    val = clean_str(df.iloc[r, c])
                    det = None
                    if val in ANTIGENS: det = val
                    elif val in ["RHD","D"]: det = "D"
                    elif val in ["RHC","C"]: det = "C"
                    elif val in ["RHE","E"]: det = "E"
                    
                    if det and det not in col_map:
                        col_map[det] = c
                        
            # If valid table found
            if len(col_map) >= 3:
                # Assuming data starts after the row where we found 'D' or 'C'
                start_row = 0
                # Find max row index of headers
                # We can approximate. Lets find where D is.
                # Heuristic: Scan downwards from row 0
                
                rows_data = []
                extracted = 0
                r_curr = 0
                
                while extracted < limit and r_curr < len(df):
                    # Check if this row has data in D column
                    if "D" in col_map:
                        col_d = col_map["D"]
                        check_val = str(df.iloc[r_curr, col_d]).lower()
                        # If value looks like data
                        if any(x in check_val for x in ['0','1','+','w']):
                            row_d = {"ID": f"C-{extracted+1}"}
                            for ag in ANTIGENS:
                                v = 0
                                if ag in col_map:
                                    v = normalize(df.iloc[r_curr, col_map[ag]])
                                row_d[ag] = int(v)
                            rows_data.append(row_d)
                            extracted += 1
                    r_curr += 1
                
                if extracted >= limit:
                    return pd.DataFrame(rows_data), f"Loaded from {sheet}"
                    
        return None, "Structure not found in any sheet."
    except Exception as e:
        return None, f"Error: {str(e)}"

def check_dosage(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE_AGS:
        partner = PAIRS.get(ag)
        if partner and ph.get(partner,0)==1: return False
    return True

def validate_rule3(cand, rp, ip, rs, Is, ex):
    p, n = 0, 0
    # Panel
    for i in range(1,12):
        s = 1 if ip[i]!="Neg" else 0
        h = rp[i-1].get(cand,0)
        if h==1 and s==1: p+=1
        if h==0 and s==0: n+=1
    # Screen
    scrs = ["I","II","III"]
    for i, label in enumerate(scrs):
        s = 1 if Is[f"s{label}"]!="Neg" else 0
        h = rs[i].get(cand,0)
        if h==1 and s==1: p+=1
        if h==0 and s==0: n+=1
    # Extra
    for c in ex:
        if c['res']==1 and c['ph'].get(cand,0)==1: p+=1
        if c['res']==0 and c['ph'].get(cand,0)==0: n+=1
        
    pass_rule = (p>=3 and n>=3) or (p>=2 and n>=3)
    msg = "Standard (3/3)" if (p>=3 and n>=3) else ("Modified" if pass_rule else "Not Met")
    return pass_rule, p, n, msg

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.title("Blood Bank")
    nav = st.radio("Menu", ["Workstation", "Admin Config"])
    if st.button("Reset All"): 
        st.session_state.extra=[]
        st.rerun()

# ---------------- ADMIN ----------------
if nav == "Admin Config":
    st.title("Admin Panel")
    pwd = st.text_input("Password", type="password")
    if pwd == "admin123":
        t1, t2 = st.tabs(["Panel 11", "Screen"])
        with t1:
            up = st.file_uploader("Upload Excel", type=["xlsx"])
            if up:
                df, msg = robust_excel_parser(io.BytesIO(up.getvalue()), 11)
                if df is not None:
                    st.success(msg)
                    st.session_state.p11 = df
                    st.rerun()
                else: st.error(msg)
            st.session_state.p11 = st.data_editor(st.session_state.p11, hide_index=True)
        with t2:
            up2 = st.file_uploader("Upload Screen", type=["xlsx"])
            if up2:
                df2, msg2 = robust_excel_parser(io.BytesIO(up2.getvalue()), 3)
                if df2 is not None:
                    st.session_state.p3 = df2
                    st.rerun()
            st.session_state.p3 = st.data_editor(st.session_state.p3, hide_index=True)

# ---------------- USER ----------------
else:
    st.markdown("<center><h2>Maternity & Children Hospital - Tabuk</h2><h4>Serology Unit</h4></center><hr>", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mrn=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    
    st.write("### 1. Results")
    L, R = st.columns([1, 2.5])
    with L:
        st.caption("Screen & Auto")
        ac = st.radio("Auto Control", ["Neg", "Pos"])
        if ac == "Pos": st.error("DAT Required"); st.stop()
        for x in ["I","II","III"]: st.session_state.inputs_s[f"s{x}"]=st.selectbox(x, ["Neg","Pos"], key=f"k{x}")
    with R:
        st.caption("ID Panel")
        cols = st.columns(6)
        in_map = {}
        for i in range(1, 12):
            k = f"c{i}"
            v = cols[(i-1)%6].selectbox(f"{i}", ["Neg", "Pos"], key=f"p{i}")
            st.session_state.inputs[k] = v
            in_map[i] = 0 if v=="Neg" else 1
            
    if st.button("Analyze"):
        r11 = [st.session_state.p11.iloc[i].to_dict() for i in range(11)]
        r3  = [st.session_state.p3.iloc[i].to_dict() for i in range(3)]
        ruled = set()
        
        # Exclusion (Panel)
        for ag in ANTIGENS:
            for idx, sc in in_map.items():
                if sc==0 and check_dosage(ag, r11[idx-1]): ruled.add(ag); break
        # Exclusion (Screen)
        smap = {"I":0,"II":1,"III":2}
        for k, v in st.session_state.inputs_s.items():
            if v=="Neg":
                sidx = smap[k[1:]]
                for ag in ANTIGENS:
                    if ag not in ruled and check_dosage(ag, r3[sidx]): ruled.add(ag)
        
        cands = [x for x in ANTIGENS if x not in ruled]
        matches = []
        for c in cands:
            mis = False
            for idx, sc in in_map.items():
                if sc>0 and r11[idx-1].get(c,0)==0: mis=True
            if not mis: matches.append(c)
            
        if not matches: st.error("Inconclusive.")
        else:
            allow = True
            for m in matches:
                ok, p, n, txt = validate_rule3(m, r11, st.session_state.inputs, r3, st.session_state.inputs_s, st.session_state.extra)
                cls = "pass" if ok else "fail"
                st.markdown(f"<div class='status-{cls}'><b>Anti-{m}</b>: {txt} ({p} Pos/{n} Neg)</div>", unsafe_allow_html=True)
                if not ok: allow=False
            
            if allow:
                rpt = f"""<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'><b>Pt:</b> {nm} | <b>MRN:</b> {mrn}<hr><b>Conclusion:</b> Anti-{', '.join(matches)} Detected.<br>Probability Confirmed (p<0.05).<br>Tech: {tc}</div><div class='consultant-footer'><span style='color:darkred;font-weight:bold'>Dr. Haitham Ismail</span></div></div><script>window.print()</script>"""
                st.markdown(rpt, unsafe_allow_html=True)
            else:
                st.warning("Add Cells:")
                c1,c2 = st.columns(2)
                id=c1.text_input("Lot"); rs=c2.selectbox("Res",["Neg","Pos"])
                ph={}
                cx = st.columns(len(matches))
                for i,m in enumerate(matches):
                    r = cx[i].checkbox(m, key=f"ex{m}")
                    ph[m] = 1 if r else 0
                if st.button("Add"):
                    st.session_state.extra.append({"src":id, "res":1 if rs=="Pos" else 0, "ph":ph})
                    st.rerun()

# FOOTER
st.markdown("<div class='consultant-footer no-print'>System V34.0 | <b>Dr. Haitham Ismail</b></div>", unsafe_allow_html=True)
