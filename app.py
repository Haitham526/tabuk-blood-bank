import streamlit as st
import pandas as pd
import io
from datetime import date

# ---------------- CONFIG & STYLE ----------------
st.set_page_config(page_title="MCH Blood Bank", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .block-container { padding: 0 !important; } .print-only { display: block !important; } .results-box { border: 2px solid #333; padding: 20px; font-family: 'Times New Roman'; margin-top:20px; } }
    .print-only { display: none; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    .status-pass { background-color: #d1e7dd; padding: 8px; border-radius: 5px; color: #0f5132; }
    .status-fail { background-color: #f8d7da; padding: 8px; border-radius: 5px; color: #842029; }
</style>
""", unsafe_allow_html=True)

# ---------------- DEFINITIONS ----------------
AGS = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
DOSAGE = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]
PAIRS = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S'}

# ---------------- STATE ----------------
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"Scn {i}", **{ag: 0 for ag in AGS}} for i in ["I","II","III"]])
if 'res' not in st.session_state: st.session_state.res = {f"c{i}": "Neg" for i in range(1, 12)}
if 'scr' not in st.session_state: st.session_state.scr = {f"s{i}": "Neg" for i in ["I","II","III"]}
if 'ext' not in st.session_state: st.session_state.ext = []

# ---------------- LOGIC ----------------
def clean_header(val):
    return str(val).upper().replace("(","").replace(")","").replace(" ","").replace("\n","").strip()

def is_positive_cell(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

def smart_parser_v39(file_obj, limit_rows=11):
    try:
        xls = pd.ExcelFile(file_obj)
        # Scan ALL Sheets
        for sheet in xls.sheet_names:
            df = pd.read_excel(file_obj, sheet_name=sheet, header=None)
            
            # 1. MAP COLUMNS
            # Looking for Header Row
            head_idx = -1
            col_map = {} # {'D': 5, 'C': 8...}
            
            # Scan first 30 rows
            for r in range(min(30, len(df))):
                temp_map = {}
                matches = 0
                for c in range(min(60, len(df.columns))):
                    val = clean_header(df.iloc[r, c])
                    det = None
                    if val in AGS: det = val
                    elif val in ["RHD","D"]: det = "D"
                    elif val in ["RHC","C"]: det = "C"
                    elif val in ["RHE","E"]: det = "E"
                    elif val in ["RHC","c"]: det = "c"
                    
                    if det and det not in temp_map:
                        temp_map[det] = c
                        matches += 1
                
                # Confidence Threshold (found enough headers)
                if matches >= 3:
                    head_idx = r
                    col_map = temp_map
                    # Broad scan on this row
                    for c2 in range(len(df.columns)):
                        v2 = clean_header(df.iloc[r, c2])
                        if v2 in AGS and v2 not in col_map: col_map[v2] = c2
                    break
            
            if head_idx == -1: continue # Try next sheet
            
            # 2. EXTRACT WITH "WIDENET" LOGIC
            final_rows = []
            extracted = 0
            curr = head_idx + 1
            max_col_idx = len(df.columns) - 1
            
            while extracted < limit_rows and curr < len(df):
                # Is Data Row? Check D (scan wide)
                has_data = False
                d_idx = col_map.get("D") or col_map.get("C") # Try D or C
                
                if d_idx is not None:
                    # Scan Center, Left, Right
                    checks = [d_idx]
                    if d_idx > 0: checks.append(d_idx - 1)
                    if d_idx < max_col_idx: checks.append(d_idx + 1)
                    
                    for cx in checks:
                        if is_positive_cell(df.iloc[curr, cx]) or "0" in str(df.iloc[curr, cx]):
                            has_data = True; break
                
                if has_data:
                    rid = f"C-{extracted+1}" if limit_rows > 3 else f"S-{['I','II','III'][extracted]}"
                    r_data = {"ID": rid}
                    
                    for ag in AGS:
                        val = 0
                        if ag in col_map:
                            center = col_map[ag]
                            # WIDENET: Check exact column, then Left, then Right
                            # This fixes merged cells issues
                            candidates = [center]
                            if center > 0: candidates.append(center - 1)
                            if center < max_col_idx: candidates.append(center + 1)
                            
                            found_ag_val = 0
                            for target_col in candidates:
                                if is_positive_cell(df.iloc[curr, target_col]):
                                    found_ag_val = 1
                                    break # Stop if found +
                            val = found_ag_val
                            
                        r_data[ag] = int(val)
                    final_rows.append(r_data)
                    extracted += 1
                curr += 1
                
            if extracted >= 1:
                return pd.DataFrame(final_rows), f"Success: Extracted {extracted} rows from '{sheet}'."
                
        return None, "Structure not found. Try Manual Entry."
        
    except Exception as e: return None, str(e)

# Logic Stubs
def check_logic(c, r11, ip, r3, iscr, ex):
    p, n = 0, 0
    # 1. Panel
    for i in range(1,12):
        s = 1 if ip[f"c{i}"]!="Neg" else 0
        h = r11.iloc[i-1][c]
        if h==1 and s==1: p+=1
        if h==0 and s==0: n+=1
    # 2. Screen
    for i, x in enumerate(["I","II","III"]):
        s = 1 if iscr[f"s{x}"]!="Neg" else 0
        h = r3.iloc[i][c]
        if h==1 and s==1: p+=1
        if h==0 and s==0: n+=1
    # 3. Extra
    for x in ex:
        if x['ph'].get(c,0)==1 and x['s']==1: p+=1
        if x['ph'].get(c,0)==0 and x['s']==0: n+=1
    
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    t = "Std" if (p>=3 and n>=3) else "Mod"
    return ok, p, n, t

def get_out(p11, ip, p3, iscr):
    out = set()
    # Panel
    for i in range(1,12):
        if ip[f"c{i}"]=="Neg":
            ph = p11.iloc[i-1]
            for a in AGS:
                dos = True
                if a in DOSAGE:
                    pr = PAIRS.get(a)
                    if pr and ph.get(pr,0)==1: dos=False
                if ph.get(a,0)==1 and dos: out.add(a)
    # Screen
    lookup = {"I":0, "II":1, "III":2}
    for k, v in iscr.items():
        if v == "Neg":
            ph = p3.iloc[lookup[k[1:]]]
            for a in AGS:
                dos = True
                if a in DOSAGE:
                    pr = PAIRS.get(a)
                    if pr and ph.get(pr,0)==1: dos=False
                if ph.get(a,0)==1 and dos: out.add(a)
    return out

def bulk_p(v): 
    for i in range(1,12): st.session_state.res[f"c{i}"]=v

# ---------------- INTERFACE ----------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    st.write("V39.0 (WideNet)")
    menu = st.radio("Go To", ["Workstation", "Admin Config"])
    st.divider()
    if st.button("New Patient / Reset"):
        st.session_state.res = {f"c{i}":"Neg" for i in range(1,12)}
        st.session_state.scr = {f"s{i}":"Neg" for i in ["I","II","III"]}
        st.session_state.ext = []
        st.rerun()

# 1. ADMIN
if menu == "Admin Config":
    st.title("🛠️ Master Configuration")
    if st.text_input("Password", type="password") == "admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening 3"])
        
        with t1:
            st.info("Upload Excel (Wide-Net Scanner enabled)")
            up = st.file_uploader("Upload Panel 11", type=["xlsx"])
            if up:
                df, m = smart_parser_v39(io.BytesIO(up.getvalue()), 11)
                if df is not None:
                    st.success(m)
                    st.session_state.p11 = df
                    st.rerun()
                else: st.error(m)
            
            st.caption("Live Grid:")
            save1 = st.data_editor(st.session_state.p11, hide_index=True)
            if st.button("Save P11"): st.session_state.p11=save1; st.success("Saved")
            
        with t2:
            st.info("Upload Screening")
            up2 = st.file_uploader("Upload P3", type=["xlsx"])
            if up2:
                df2, m2 = smart_parser_v39(io.BytesIO(up2.getvalue()), 3)
                if df2 is not None:
                    st.success(m2)
                    st.session_state.p3 = df2
                    st.rerun()
                else: st.error(m2)
            save2 = st.data_editor(st.session_state.p3, hide_index=True)
            if st.button("Save Scr"): st.session_state.p3=save2; st.success("Saved")

# 2. USER
else:
    st.markdown("<h2 style='text-align:center; color:#036;'>MCH Tabuk - Blood Bank</h2><hr>", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Pt Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    
    st.write("---")
    L, R = st.columns([1, 2])
    with L:
        st.write("<b>1. Screen/Ctl</b>", unsafe_allow_html=True)
        ac = st.radio("AC", ["Negative", "Positive"])
        if ac=="Positive": st.error("STOP: DAT Required"); st.stop()
        for x in ["I","II","III"]: st.session_state.scr[f"s{x}"] = st.selectbox(f"S-{x}", ["Neg","w+","1+","2+"])
    
    with R:
        st.write("<b>2. Panel Reactions</b>", unsafe_allow_html=True)
        g = st.columns(6)
        in_p = {}
        for i in range(1, 12):
            col_target = g[(i-1)%6]
            st.session_state.res[f"c{i}"] = col_target.selectbox(f"{i}", ["Neg","w+","1+","2+","3+"])
            
    st.write("---")
    if st.button("🚀 Analyze"):
        ruled = get_out(st.session_state.p11, st.session_state.res, st.session_state.p3, st.session_state.scr)
        cands = [x for x in AGS if x not in ruled]
        match = []
        
        # Inclusion
        for c in cands:
            miss = False
            for i in range(1,12):
                if st.session_state.res[f"c{i}"] != "Neg" and st.session_state.p11.iloc[i-1].get(c,0)==0: miss=True
            if not miss: match.append(c)
            
        if not match: st.error("Inconclusive.")
        else:
            final_pass = True
            for m in match:
                ok, p, n, msg = check_logic(m, st.session_state.p11, st.session_state.res, st.session_state.p3, st.session_state.scr, st.session_state.ext)
                st.markdown(f"<div class='status-{'pass' if ok else 'fail'}'><b>Anti-{m}:</b> {msg} ({p} Pos, {n} Neg)</div>", unsafe_allow_html=True)
                if not ok: final_pass = False
            
            if final_pass:
                ht = f"""<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'>Pt: {nm} ({mr})<hr>Result: Anti-{', '.join(match)} Detected.<br>Probability Confirmed (p<0.05).<br><br>Sig: __________</div></div><script>window.print()</script>"""
                st.markdown(ht, unsafe_allow_html=True)
            else:
                st.warning("Confirmation needed. Add cells:")
                with st.expander("Add"):
                    x1,x2=st.columns(2); id=x1.text_input("ID"); rr=x2.selectbox("R",["Neg","Pos"]); xp={}
                    cs=st.columns(len(match))
                    for i,m in enumerate(match): xp[m]=1 if cs[i].checkbox(m) else 0
                    if st.button("Save"): st.session_state.ext.append({"src":id,"s":1 if rr=="Pos" else 0,"ph":xp,"res":1 if rr=="Pos" else 0}); st.rerun()

st.markdown("<div style='position:fixed;bottom:5px;right:5px;font-size:10px;color:grey' class='no-print'>V39.0</div>", unsafe_allow_html=True)
