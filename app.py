import streamlit as st
import pandas as pd
import io
from datetime import date

# 1. SETUP
st.set_page_config(page_title="Tabuk Blood Bank", layout="wide", page_icon="🏥")

st.markdown("""
<style>
    @media print {
        .stApp > header, .sidebar, footer, .no-print { display: none !important; }
        .block-container { padding: 0 !important; }
        .print-only { display: block !important; }
        .report-box { border: 2px solid #000; padding: 20px; font-family: serif; }
    }
    .print-only { display: none; }
    
    .status-ok { background: #d4edda; color: #155724; padding: 8px; border-radius: 4px; margin: 4px 0; border-left: 5px solid #28a745;}
    .status-no { background: #f8d7da; color: #721c24; padding: 8px; border-radius: 4px; margin: 4px 0; border-left: 5px solid #dc3545;}
    
    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

# 2. DEFINITIONS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# 3. STATE
if 'panel_data' not in st.session_state:
    st.session_state.panel_data = pd.DataFrame([{"ID":f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'screen_data' not in st.session_state:
    st.session_state.screen_data = pd.DataFrame([{"ID":f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'extra_cells' not in st.session_state:
    st.session_state.extra_cells = []

# 4. LOGIC FUNCTIONS
def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+','1','pos','yes','w']) else 0

def exact_parser(file):
    try:
        xls = pd.ExcelFile(file)
        for sheet in xls.sheet_names:
            df = pd.read_excel(file, sheet_name=sheet, header=None)
            
            # Map Cols
            col_map = {}
            head_row = -1
            
            for r in range(min(30, len(df))):
                cnt = 0
                temp = {}
                for c in range(min(60, len(df.columns))):
                    v = str(df.iloc[r,c]).strip().replace(" ","")
                    
                    det = None
                    # Strict Check
                    if v in ["c","C","e","E","k","K","s","S"]: det = v
                    elif v.upper() == "D" or v.upper() == "RHD": det = "D"
                    else:
                        vup = v.upper()
                        if vup in AGS: det = vup
                    
                    if det:
                        temp[det] = c
                        cnt += 1
                
                if cnt >= 3:
                    head_row = r
                    col_map = temp
                    break
            
            if head_row != -1:
                final = []
                count = 0
                curr = head_row + 1
                while count < 11 and curr < len(df):
                    is_val = False
                    if "D" in col_map:
                        check = str(df.iloc[curr, col_map["D"]]).lower()
                        if any(x in check for x in ['+','0','1','w']): is_val = True
                    
                    if is_val:
                        rd = {"ID": f"Cell {count+1}"}
                        for ag in AGS:
                            v = 0
                            if ag in col_map:
                                v = normalize(df.iloc[curr, col_map[ag]])
                            rd[ag] = int(v)
                        final.append(rd)
                        count += 1
                    curr += 1
                
                if count >= 1:
                    return pd.DataFrame(final), f"Found {count} rows in {sheet}"
                    
        return None, "Columns Not Found"
    except Exception as e: return None, str(e)

def rule_check(c, p11, r11, p3, r3, ext):
    p, n = 0, 0
    # Panel
    for i in range(1, 12):
        s = 1 if r11[i] != "Neg" else 0
        h = p11.iloc[i-1].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    for i, x in enumerate(["I","II","III"]):
        s = 1 if r3[f"s{x}"] != "Neg" else 0
        h = p3.iloc[i].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extra
    for x in ext:
        if x['s']==1 and x['p'].get(c,0)==1: p+=1
        if x['s']==0 and x['p'].get(c,0)==0: n+=1
        
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    t = "Standard" if (p>=3 and n>=3) else ("Modified" if ok else "Fail")
    return ok, p, n, t

def can_out(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE:
        pair = PAIRS.get(ag)
        if pair and ph.get(pair,0)==1: return False
    return True

# 5. UI NAVIGATION
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Supervisor"])
    st.write("---")
    if st.button("New Patient / Reset"):
        st.session_state.extra_cells = []
        st.rerun()

# --- ADMIN PAGE ---
if nav == "Supervisor":
    st.title("Admin Configuration")
    if st.text_input("Password", type="password") == "admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening"])
        with t1:
            up1 = st.file_uploader("Upload P11", type=["xlsx"])
            if up1:
                d1,m1 = exact_parser(io.BytesIO(up1.getvalue()))
                if d1 is not None:
                    st.session_state.panel_data = d1
                    st.success(m1)
                else: st.error(m1)
            e1 = st.data_editor(st.session_state.panel_data, hide_index=True)
            if st.button("Save Panel"): st.session_state.panel_data = e1; st.success("Saved")
            
        with t2:
            st.info("Edit Screening Grid Manually if needed")
            e2 = st.data_editor(st.session_state.screen_data, hide_index=True)
            if st.button("Save Screen"): st.session_state.screen_data = e2; st.success("Saved")

# --- USER WORKSTATION ---
else:
    st.markdown("<h2 style='text-align:center; color:#036'>MCH Tabuk Serology</h2><hr>", unsafe_allow_html=True)
    
    # *** FORM START *** (This stops the refreshing error)
    with st.form("entry_form"):
        c1,c2,c3,c4 = st.columns(4)
        nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
        
        st.write("### 1. Reactions")
        L, R = st.columns([1, 2])
        
        # Screen Inputs
        with L:
            st.write("<b>Screening</b>", unsafe_allow_html=True)
            ac = st.radio("Auto Control", ["Negative", "Positive"], horizontal=True)
            s_res = {}
            for x in ["I","II","III"]:
                s_res[f"s{x}"] = st.selectbox(f"Scn {x}", ["Neg","w+","1+","2+","3+"])
                
        # Panel Inputs (Safe 2 Cols)
        with R:
            st.write("<b>Identification Panel</b>", unsafe_allow_html=True)
            pc1, pc2 = st.columns(2)
            p_res = {}
            for i in range(1, 12):
                col = pc1 if i<=6 else pc2
                p_res[i] = col.selectbox(f"Cell {i}", ["Neg","w+","1+","2+","3+"])
        
        submitted = st.form_submit_button("🚀 Submit & Analyze")
    
    # --- ANALYSIS LOGIC ---
    if submitted:
        if ac == "Positive":
            st.error("🚨 STOP: Auto Control Positive. Perform DAT.")
        else:
            # Prepare Data
            rows11 = [st.session_state.panel_data.iloc[i].to_dict() for i in range(11)]
            rows3  = [st.session_state.screen_data.iloc[i].to_dict() for i in range(3)]
            
            # Logic: Exclusion
            ruled = set()
            # 1. From Panel
            for ag in AGS:
                for i in range(1, 12):
                    if p_res[i] == "Neg" and can_out(ag, rows11[i-1]):
                        ruled.add(ag); break
            
            # 2. From Screen
            sc_idx = {"I":0, "II":1, "III":2}
            for k, v in s_res.items():
                if v == "Neg":
                    # Check safe dict
                    sx = sc_idx[k.replace("s","")]
                    for ag in AGS:
                        if ag not in ruled and can_out(ag, rows3[sx]):
                            ruled.add(ag)
            
            # 3. Inclusion
            cands = [x for x in AGS if x not in ruled]
            match = []
            
            # P map for checking positives
            p_map = {i: 0 if p_res[i]=="Neg" else 1 for i in range(1,12)}
            
            for c in cands:
                mis = False
                for i, v in p_map.items():
                    if v==1 and rows11[i-1].get(c,0)==0: mis = True
                if not mis: match.append(c)
                
            # OUTPUT
            if not match:
                st.error("❌ Result Inconclusive / No Pattern Found.")
            else:
                st.success(f"✅ Identified: Anti-{', '.join(match)}")
                
                final_ok = True
                for m in match:
                    ok, p, n, txt = rule_check(m, st.session_state.panel_data, p_res, st.session_state.screen_data, s_res, st.session_state.extra_cells)
                    if not ok: final_ok = False
                    cls = "status-ok" if ok else "status-no"
                    st.markdown(f"<div class='{cls}'><b>Anti-{m}:</b> {txt} ({p} Pos, {n} Neg)</div>", unsafe_allow_html=True)
                
                if final_ok:
                    # Print logic is handled outside form for state persistence, 
                    # but simple display here is enough for now.
                    rpt = f"""<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='report-box'>Pt: {nm}<br>Res: Anti-{', '.join(match)}<br>Valid Rule of 3 (p<=0.05).<br><br>Sig: ___________</div><div style='position:fixed;bottom:0;text-align:center;width:100%'>Dr. Haitham Ismail</div></div>"""
                    st.markdown(rpt, unsafe_allow_html=True)
                    st.balloons()
                    st.info("Tip: Use Ctrl+P to Print")
                else:
                    st.warning("⚠️ Rule Not Met. Add Extra Cells below.")
    
    # --- EXTRA CELLS (Outside Form to allow addition) ---
    if st.session_state.get('extra_cells'):
        st.write("#### Added Extra Cells:")
        st.dataframe(pd.DataFrame([{ "ID":x['id'], "Res": "Pos" if x['s']==1 else "Neg", "Details": str([k for k,v in x['ph'].items() if v==1]) } for x in st.session_state.extra_cells]), hide_index=True)

    with st.expander("➕ Add Selected Cell (Validation)"):
        # This part must be separate from main form
        with st.form("extra_cell_form"):
            e1,e2 = st.columns(2)
            nid = e1.text_input("Cell Lot ID")
            nres = e2.selectbox("Result", ["Neg","Pos"])
            st.write("Select present antigens:")
            # Simple multiselect for ease
            present_ags = st.multiselect("Antigens on Cell", AGS)
            
            add_btn = st.form_submit_button("Add Cell")
            if add_btn:
                ph_map = {ag: 1 if ag in present_ags else 0 for ag in AGS}
                st.session_state.extra_cells.append({"id":nid, "s":1 if nres=="Pos" else 0, "res":1, "ph":ph_map, "p":ph_map})
                st.success(f"Cell {nid} Added. Re-Run Analysis above.")
                # We do not rerun immediately to avoid losing form data up top, 
                # user clicks Submit again up top.
