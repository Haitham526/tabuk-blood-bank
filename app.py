import streamlit as st
import pandas as pd
import io

# --------------------------------------------------------
# 1. BASE SETUP
# --------------------------------------------------------
st.set_page_config(page_title="Tabuk Blood Bank", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .print-only { display: block !important; } .results-box { border: 2px solid #000; padding: 20px; font-family: 'Times New Roman'; margin-top: 10px; } }
    .print-only { display: none; }
    .status-ok { background: #d4edda; color: #155724; padding: 10px; margin: 5px 0; border-radius: 5px; }
    .status-fail { background: #f8d7da; color: #721c24; padding: 10px; margin: 5px 0; border-radius: 5px; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

# definitions
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# INITIALIZATION (Reset-Proof)
if 'panel_11' not in st.session_state:
    st.session_state.panel_11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'panel_3' not in st.session_state:
    st.session_state.panel_3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'extras' not in st.session_state:
    st.session_state.extras = []

# --------------------------------------------------------
# 2. LOGIC FUNCTIONS
# --------------------------------------------------------
def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

def exact_parser(file):
    try:
        xls = pd.ExcelFile(file)
        for sheet in xls.sheet_names:
            df = pd.read_excel(file, sheet_name=sheet, header=None)
            
            # Map Header
            col_map = {}
            header_row = -1
            
            for r in range(min(40, len(df))):
                cnt = 0
                temp = {}
                for c in range(min(60, len(df.columns))):
                    v = str(df.iloc[r,c]).strip().replace(" ","").replace("\n","")
                    det = None
                    if v in ["c","C","e","E","k","K","s","S"]: det = v
                    elif v.upper() in ["D","RHD"]: det = "D"
                    else:
                        if v.upper() in AGS: det = v.upper()
                    
                    if det:
                        temp[det] = c
                        cnt += 1
                
                if cnt >= 3:
                    header_row = r
                    col_map = temp
                    break
            
            if header_row != -1:
                data = []
                extracted = 0
                curr = header_row + 1
                while extracted < 11 and curr < len(df):
                    is_val = False
                    # Search around D
                    chk_cols = []
                    if "D" in col_map: chk_cols = [col_map["D"], col_map["D"]-1, col_map["D"]+1]
                    
                    for cx in chk_cols:
                        if cx >=0 and cx < len(df.columns):
                            raw = str(df.iloc[curr, cx]).lower()
                            if any(x in raw for x in ['+','0','1','w']): is_val = True; break
                    
                    if is_val:
                        rid = f"Cell {extracted+1}"
                        rd = {"ID": rid}
                        for ag in AGS:
                            v = 0
                            if ag in col_map:
                                center = col_map[ag]
                                scans = [center, center-1, center+1]
                                for z in scans:
                                    if z>=0 and z<len(df.columns):
                                        if normalize(df.iloc[curr, z])==1: v=1
                            rd[ag] = int(v)
                        data.append(rd)
                        extracted += 1
                    curr += 1
                
                if extracted >= 1:
                    return pd.DataFrame(data), f"Read OK from {sheet}"
        return None, "Not Found"
    except Exception as e: return None, str(e)

def can_out(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr=PAIRS.get(ag)
        if pr and ph.get(pr,0)==1: return False
    return True

def rule_checker(cand, p11_ins, s3_ins, ex):
    p, n = 0, 0
    # Panel
    p_df = st.session_state.panel_11
    for i in range(1,12):
        s = 1 if p11_ins[i]!="Neg" else 0
        h = p_df.iloc[i-1].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    s_df = st.session_state.panel_3
    scrs=["I","II","III"]
    for i, lb in enumerate(scrs):
        s = 1 if s3_ins[lb]!="Neg" else 0
        h = s_df.iloc[i].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extra
    for x in ex:
        if x['s']==1 and x['ph'].get(cand,0)==1: p+=1
        if x['s']==0 and x['ph'].get(cand,0)==0: n+=1
    
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    t = "Standard Rule" if (p>=3 and n>=3) else ("Modified" if ok else "Rule Failed")
    return ok, p, n, t

# ========================================================
# 3. INTERFACE (The Safe Form)
# ========================================================
with st.sidebar:
    st.title("MCH Tabuk")
    nav = st.radio("Menu", ["Workstation", "Admin"])
    if st.button("RESET"):
        st.session_state.extras = []
        st.rerun()

# -------- ADMIN --------
if nav == "Admin":
    st.header("Admin Configuration")
    if st.text_input("Password", type="password") == "admin123":
        t1, t2 = st.tabs(["Panel", "Screen"])
        with t1:
            u1 = st.file_uploader("Upload Panel", type=["xlsx"])
            if u1:
                d1,m1 = exact_parser(io.BytesIO(u1.getvalue()))
                if d1 is not None:
                    st.success(m1)
                    st.session_state.panel_11 = d1
                else: st.error(m1)
            st.session_state.panel_11 = st.data_editor(st.session_state.panel_11, hide_index=True)
        with t2:
            st.write("Edit Screening")
            st.session_state.panel_3 = st.data_editor(st.session_state.panel_3, hide_index=True)

# -------- WORKSTATION (SAFE MODE) --------
else:
    st.markdown("<h2 style='text-align:center; color:#036'>Blood Bank Workstation</h2>", unsafe_allow_html=True)
    c1,c2,c3,c4=st.columns(4)
    nm=c1.text_input("Pt Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    # 🔴 FORM STARTS HERE (PREVENTS CRASHES)
    with st.form("entry_form"):
        colL, colR = st.columns([1, 2])
        
        with colL:
            st.write("#### Control/Screen")
            ac = st.radio("Auto Control", ["Negative", "Positive"])
            s_i = st.selectbox("Scn I", ["Neg","w+","1+","2+"])
            s_ii = st.selectbox("Scn II", ["Neg","w+","1+","2+"])
            s_iii = st.selectbox("Scn III", ["Neg","w+","1+","2+"])
            
        with colR:
            st.write("#### Panel (11 Cells)")
            # MANUAL LAYOUT (NO LOOP)
            ca, cb = st.columns(2)
            with ca:
                c1_v = st.selectbox("Cell 1", ["Neg","w+","1+","2+","3+"])
                c2_v = st.selectbox("Cell 2", ["Neg","w+","1+","2+","3+"])
                c3_v = st.selectbox("Cell 3", ["Neg","w+","1+","2+","3+"])
                c4_v = st.selectbox("Cell 4", ["Neg","w+","1+","2+","3+"])
                c5_v = st.selectbox("Cell 5", ["Neg","w+","1+","2+","3+"])
                c6_v = st.selectbox("Cell 6", ["Neg","w+","1+","2+","3+"])
            with cb:
                c7_v = st.selectbox("Cell 7", ["Neg","w+","1+","2+","3+"])
                c8_v = st.selectbox("Cell 8", ["Neg","w+","1+","2+","3+"])
                c9_v = st.selectbox("Cell 9", ["Neg","w+","1+","2+","3+"])
                c10_v = st.selectbox("Cell 10", ["Neg","w+","1+","2+","3+"])
                c11_v = st.selectbox("Cell 11", ["Neg","w+","1+","2+","3+"])
        
        sub = st.form_submit_button("🚀 RUN ANALYSIS")
        
    # LOGIC (Runs ONLY on Submit)
    if sub:
        try:
            if ac == "Positive":
                st.error("🚨 STOP: Auto Control Positive. Perform DAT.")
            else:
                # Prepare Inputs
                input_p = {1:c1_v, 2:c2_v, 3:c3_v, 4:c4_v, 5:c5_v, 6:c6_v, 7:c7_v, 8:c8_v, 9:c9_v, 10:c10_v, 11:c11_v}
                input_s = {"I":s_i, "II":s_ii, "III":s_iii}
                
                # Exclusion
                ruled = set()
                # P
                for ag in AGS:
                    for i in range(1,12):
                        if input_p[i]=="Neg" and can_out(ag, st.session_state.panel_11.iloc[i-1].to_dict()):
                            ruled.add(ag); break
                # S
                smap={"I":0,"II":1,"III":2}
                for k,v in input_s.items():
                    if v=="Neg":
                        idx = smap[k]
                        for ag in AGS:
                            if ag not in ruled and can_out(ag, st.session_state.panel_3.iloc[idx].to_dict()):
                                ruled.add(ag)
                                
                candidates = [x for x in AGS if x not in ruled]
                matches = []
                for c in candidates:
                    miss = False
                    for i in range(1,12):
                        if input_p[i]!="Neg" and st.session_state.panel_11.iloc[i-1].get(c,0)==0: miss = True
                    if not miss: matches.append(c)
                    
                st.write("---")
                if not matches: st.error("No Match Found.")
                else:
                    valid_all = True
                    for m in matches:
                        ok, p, n, msg = rule_checker(m, input_p, input_s, st.session_state.extras)
                        css = "status-ok" if ok else "status-fail"
                        st.markdown(f"<div class='{css}'><b>Anti-{m}:</b> {msg} ({p} Pos / {n} Neg)</div>", unsafe_allow_html=True)
                        if not ok: valid_all = False
                        
                    if valid_all:
                        st.balloons()
                        rpt = f"""<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'><b>Pt:</b> {nm} ({mr})<br><b>Tech:</b> {tc}<hr><b>Conclusion:</b> Anti-{', '.join(matches)} Detected.<br>Probability Valid.<br><br>Sig: ___________</div></div><script>window.print()</script>"""
                        st.markdown(rpt, unsafe_allow_html=True)
                        st.info("Validation OK. Print Report (Ctrl+P).")
                    else:
                        st.warning("⚠️ Validation Needed. Add Extra Cells below.")
                        
        except Exception as e:
            st.error(f"Logic Error: {e}")

    # EXTRA CELLS (OUTSIDE FORM)
    with st.expander("Add Extra Cells"):
        with st.form("extra_form"):
            e_id = st.text_input("ID")
            e_rs = st.selectbox("Res", ["Neg", "Pos"])
            st.write("Select Present Antigens:")
            # Simple selectbox
            ag_str = st.text_input("Type antigens (e.g. D C E)")
            if st.form_submit_button("Add Cell"):
                ph = {a:0 for a in AGS}
                for item in ag_str.split():
                    it = item.strip()
                    if it in AGS: ph[it]=1 # basic map
                    # Case fix
                    for std in AGS:
                        if std.upper() == it.upper(): ph[std]=1
                        
                st.session_state.extras.append({"src":e_id, "s":1 if e_rs=="Pos" else 0, "res":1 if e_rs=="Pos" else 0, "ph":ph, "p":ph})
                st.success("Cell Added! Please click RUN ANALYSIS again.")
                
    if st.session_state.extras:
        st.write("Extra Cells Added:")
        st.dataframe(pd.DataFrame([{"ID":x['src'], "Result":"Pos" if x['s']==1 else "Neg"} for x in st.session_state.extras]))
