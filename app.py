import streamlit as st
import pandas as pd
import io
from datetime import date

# ==========================================
# 1. SETUP
# ==========================================
st.set_page_config(page_title="Tabuk Blood Bank", layout="wide", page_icon="🏥")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .block-container { padding: 0 !important; } .print-only { display: block !important; } .results-box { border: 2px solid #333; padding: 20px; font-family: 'Times New Roman'; font-size:14px;} .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; } }
    .print-only { display: none; }
    .header-box { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    
    .status-pass { background-color: #d1e7dd; padding: 8px; border-radius: 5px; color: #0f5132; margin-bottom:5px; border-left: 5px solid #198754; } 
    .status-fail { background-color: #f8d7da; padding: 8px; border-radius: 5px; color: #842029; margin-bottom:5px; border-left: 5px solid #dc3545; }
    .sig-badge { position: fixed; bottom: 10px; right: 15px; background: #fff; padding: 5px; border: 1px solid #ccc; border-radius: 5px; font-size: 11px; z-index:99; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='sig-badge no-print'>Dr. Haitham Ismail | Consultant</div>", unsafe_allow_html=True)

# CONFIG
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
# --- SAFE INPUT INIT ---
for i in range(1,12): 
    if f"c{i}" not in st.session_state: st.session_state[f"c{i}"] = "Neg"
for s in ["I","II","III"]:
    if f"s{s}" not in st.session_state: st.session_state[f"s{s}"] = "Neg"
if 'ext' not in st.session_state: st.session_state.ext = []

# ==========================================
# 2. LOGIC (NUCLEAR PARSER)
# ==========================================
def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

def exact_parser(file):
    try:
        xls = pd.ExcelFile(file)
        for sheet in xls.sheet_names:
            df = pd.read_excel(file, sheet_name=sheet, header=None)
            
            # Map columns (Nuclear Scan)
            col_map = {}
            head_row = -1
            
            for r in range(min(30, len(df))):
                cnt = 0
                temp = {}
                for c in range(min(60, len(df.columns))):
                    v = str(df.iloc[r,c]).strip().replace(" ","").replace("(","").replace(")","")
                    det = None
                    # Strict Case check
                    if v in ["c","C","e","E","k","K","s","S"]: det = v
                    elif v.upper() == "D" or v.upper() == "RHD": det = "D"
                    else:
                        if v.upper() in AGS: det = v.upper()
                    
                    if det:
                        temp[det] = c
                        cnt += 1
                
                if cnt >= 4:
                    head_row = r
                    col_map = temp
                    break
            
            if head_row != -1:
                final = []
                extracted = 0
                curr = head_row + 1
                while extracted < 11 and curr < len(df):
                    is_val = False
                    # Check Data Existence in D or C
                    for check_col in [col_map.get("D"), col_map.get("C")]:
                        if check_col:
                            raw = str(df.iloc[curr, check_col]).lower()
                            if any(x in raw for x in ['+','0','1','w']): is_val=True; break
                    
                    if is_val:
                        rid = f"Cell {extracted+1}"
                        rd = {"ID": rid}
                        for ag in AGS:
                            v = 0
                            if ag in col_map: v = normalize(df.iloc[curr, col_map[ag]])
                            rd[ag] = int(v)
                        final.append(rd)
                        extracted += 1
                    curr += 1
                
                if extracted >= 1:
                    return pd.DataFrame(final), f"Read Success: {sheet}"
                    
        return None, "Columns Not Found"
    except Exception as e: return None, str(e)

def can_out(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr=PAIRS.get(ag)
        if pr and ph.get(pr,0)==1: return False
    return True

def rule_check(c, r11, p3, ex):
    p, n = 0, 0
    # Panel
    for i in range(1, 12):
        s = 1 if st.session_state[f"c{i}"] != "Neg" else 0
        h = r11.iloc[i-1].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    for i, x in enumerate(["I","II","III"]):
        s = 1 if st.session_state[f"s{x}"] != "Neg" else 0
        h = p3.iloc[i].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extra
    for x in ex:
        if x['s']==1 and x['ph'].get(c,0)==1: p+=1
        if x['s']==0 and x['ph'].get(c,0)==0: n+=1
    
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    t = "Standard Rule" if (p>=3 and n>=3) else ("Modified Rule" if ok else "Not Met")
    return ok, p, n, t

def set_neg():
    for i in range(1, 12): st.session_state[f"c{i}"] = "Neg"

# ==========================================
# 3. INTERFACE (SIMPLE & STABLE)
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=50)
    nav = st.radio("MENU", ["Workstation", "Supervisor"])
    st.write("---")
    if st.button("RESET"):
        st.session_state.ext = []
        set_neg()
        st.rerun()

# --------- ADMIN ---------
if nav == "Supervisor":
    st.title("Admin Configuration")
    if st.text_input("Password", type="password") == "admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening"])
        with t1:
            up1 = st.file_uploader("Upload Panel (Excel)", type=["xlsx"])
            if up1:
                d1,m1 = exact_parser(io.BytesIO(up1.getvalue()))
                if d1 is not None:
                    st.success(m1); st.session_state.p11=d1
                else: st.error(m1)
            e1 = st.data_editor(st.session_state.p11, hide_index=True)
            if st.button("Save P11"): st.session_state.p11=e1; st.success("Saved")
            
        with t2:
            st.info("Screening Cells Upload")
            up2 = st.file_uploader("Upload Screen (Excel)", type=["xlsx"])
            if up2:
                d2,m2 = exact_parser(io.BytesIO(up2.getvalue()))
                if d2 is not None:
                    st.success(m2); st.session_state.p3=d2
                else: st.error(m2)
            e2 = st.data_editor(st.session_state.p3, hide_index=True)
            if st.button("Save Scr"): st.session_state.p3=e2; st.success("Saved")

# --------- USER ---------
else:
    st.markdown("<div class='header-box'><h2>Maternity & Children Hospital - Tabuk</h2><h4>Serology Workstation</h4></div>", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Pt Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    # ------------------ ERROR PROOF UI (NO LOOPS FOR LAYOUT) ------------------
    L, R = st.columns([1, 1.5])
    with L:
        st.subheader("1. Screen/Control")
        ac = st.radio("AC", ["Negative","Positive"], horizontal=True)
        if ac == "Positive": st.error("STOP: DAT Required"); st.stop()
        
        st.write("---")
        for x in ["I","II","III"]:
            st.selectbox(f"Scn {x}", ["Neg","w+","1+","2+","3+"], key=f"s{x}")
            
    with R:
        st.subheader("2. Panel Reactions")
        # Direct layout (No Complex Grids)
        rc1, rc2 = st.columns(2)
        for i in range(1, 12):
            col = rc1 if i <= 6 else rc2
            col.selectbox(f"Cell {i}", ["Neg","w+","1+","2+","3+"], key=f"c{i}")
            
    # ACTION
    st.write("---")
    if st.button("🚀 Run Analysis", type="primary"):
        # Calc
        r11 = [st.session_state.p11.iloc[i].to_dict() for i in range(11)]
        p3_df = st.session_state.p3
        
        ruled = set()
        
        # Ruleout P11
        for ag in AGS:
            for i in range(1,12):
                res = st.session_state[f"c{i}"]
                if res == "Neg" and can_out(ag, r11[i-1]):
                    ruled.add(ag); break
                    
        # Ruleout Screen
        sm = {"I":0,"II":1,"III":2}
        for k in ["I","II","III"]:
            if st.session_state[f"s{k}"] == "Neg":
                ph = p3_df.iloc[sm[k]]
                for ag in AGS:
                    if ag not in ruled and can_out(ag, ph): ruled.add(ag)
                    
        matches = []
        for c in [x for x in AGS if x not in ruled]:
            miss = False
            for i in range(1,12):
                if st.session_state[f"c{i}"]!="Neg" and r11[i-1].get(c,0)==0: miss=True
            if not miss: matches.append(c)
            
        st.subheader("Result")
        if not matches: st.error("Inconclusive.")
        else:
            final_ok = True
            for m in matches:
                ok, p, n, msg = rule_check(m, st.session_state.p11, st.session_state.p3, st.session_state.ext)
                st.markdown(f"<div class='status-{'pass' if ok else 'fail'}'><b>Anti-{m}:</b> {msg} ({p} P / {n} N)</div>", unsafe_allow_html=True)
                if not ok: final_ok = False
                
            if final_ok:
                if st.button("🖨️ Print Report"):
                    rpt=f"""<div class='print-only'><center><h2>MCH Tabuk</h2></center><div class='results-box'><b>Pt:</b> {nm}<br><b>Res:</b> Anti-{', '.join(matches)}<br>Valid (Rule of 3)<br><br>Sig:___________</div><div style='position:fixed;bottom:0;width:100%;text-align:center'>Dr. Haitham Ismail</div></div><script>window.print()</script>"""
                    st.markdown(rpt, unsafe_allow_html=True)
            else:
                st.info("Validation needed:")
                with st.expander("Add Extra Cell"):
                    idx=st.text_input("ID"); rs=st.selectbox("R",["Neg","Pos"]); ph={}
                    cols=st.columns(len(matches))
                    for i,m in enumerate(matches):
                        if cols[i].checkbox(m): ph[m]=1
                        else: ph[m]=0
                    if st.button("Add"):
                        st.session_state.ext.append({"src":idx,"s":1 if rs=="Pos" else 0,"ph":ph,"res":1}); st.rerun()
