import streamlit as st
import pandas as pd
from datetime import date
import io

# -----------------------------------------------------------------------------
# 1. BASE CONFIG & INITIALIZATION (HARD RESET)
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Tabuk Blood Bank", layout="wide", page_icon="🩸")

# Custom Styling to fix Table Visibility & Printing
st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .print-only { display: block !important; } .results-box { border: 2px solid #333; padding: 20px; font-family: 'Times New Roman'; } .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; } }
    .print-only { display: none; }
    .hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    
    /* Force Tables to Show */
    div[data-testid="stDataEditor"] table { width: 100% !important; min-width: 100% !important; }
    
    .status-pass { background-color: #d1e7dd; padding: 10px; border-radius: 5px; color: #0f5132; margin-bottom: 5px; }
    .status-fail { background-color: #f8d7da; padding: 10px; border-radius: 5px; color: #842029; margin-bottom: 5px; }
    .sig-badge { position: fixed; bottom: 10px; right: 15px; background: white; padding: 5px 10px; border: 1px solid #ccc; border-radius: 5px; z-index:99; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='sig-badge no-print'>Dr. Haitham Ismail | Consultant</div>", unsafe_allow_html=True)

# ANTIGEN LIST
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# Initialize Session State (Manual Init to prevent errors)
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
# User Input State
keys_to_init = ["s_I", "s_II", "s_III", "c_1", "c_2", "c_3", "c_4", "c_5", "c_6", "c_7", "c_8", "c_9", "c_10", "c_11"]
for k in keys_to_init:
    if k not in st.session_state: st.session_state[k] = "Neg"
if 'ext' not in st.session_state: st.session_state.ext = []

# -----------------------------------------------------------------------------
# 2. THE WORKING PARSER (V47 ENGINE - TABLE 3 SOLVER)
# -----------------------------------------------------------------------------
def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

def parser(file_bytes, limit=11):
    try:
        xls = pd.ExcelFile(file_bytes)
        for sheet in xls.sheet_names:
            df = pd.read_excel(file_bytes, sheet_name=sheet, header=None)
            
            # Map Header
            col_map = {}
            header_row = -1
            
            for r in range(min(40, len(df))):
                matches = 0
                temp = {}
                for c in range(min(60, len(df.columns))):
                    val = str(df.iloc[r, c]).strip().replace(" ","").replace("\n","")
                    det = None
                    # Strict Case Logic
                    if val in ["c","C","e","E","k","K","s","S"]: det = val
                    elif val.upper() in ["D","RHD"]: det = "D"
                    else:
                        if val.upper() in AGS: det = val.upper()
                    
                    if det:
                        temp[det] = c
                        matches += 1
                
                # If row has enough matches (e.g. Table 3 header)
                if matches >= 4:
                    header_row = r
                    col_map = temp
                    break
            
            # Extract
            if header_row != -1:
                final = []
                count = 0
                curr = header_row + 1
                
                while count < limit and curr < len(df):
                    is_data = False
                    # Check key columns
                    if "D" in col_map:
                        raw = str(df.iloc[curr, col_map["D"]]).lower()
                        if any(x in raw for x in ['+','0','1','w']): is_data = True
                    
                    if is_data:
                        cid = f"C-{count+1}" if limit==11 else f"S-{count+1}"
                        rd = {"ID": cid}
                        for ag in AGS:
                            v = 0
                            if ag in col_map:
                                v = normalize(df.iloc[curr, col_map[ag]])
                            rd[ag] = int(v) # Ensure Int
                        final.append(rd)
                        count += 1
                    curr += 1
                
                if count >= 1:
                    return pd.DataFrame(final), f"Success: Loaded from {sheet}"
                    
        return None, "Data Not Found"
    except Exception as e: return None, str(e)

# Logic Helpers
def can_out(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr=PAIRS.get(ag)
        if pr and ph.get(pr,0)==1: return False
    return True

def chk_rule(c, p11, r11, p3, r3, ex):
    p, n = 0, 0
    # Panel
    for i in range(1,12):
        s=1 if r11[f"c_{i}"]!="Neg" else 0
        h=p11.iloc[i-1].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    for i, s in enumerate(["I","II","III"]):
        sc=1 if r3[f"s_{s}"]!="Neg" else 0
        h=p3.iloc[i].get(c,0)
        if sc==1 and h==1: p+=1
        if sc==0 and h==0: n+=1
    # Extra
    for x in ex:
        if x['s']==1 and x['ph'].get(c,0)==1: p+=1
        if x['s']==0 and x['ph'].get(c,0)==0: n+=1
        
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    txt = "Std Rule" if (p>=3 and n>=3) else ("Mod Rule" if ok else "Not Met")
    return ok, p, n, txt

# -----------------------------------------------------------------------------
# 3. INTERFACE (STATIC NO-LOOP UI) -> THE FIX FOR TYPEERROR
# -----------------------------------------------------------------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png",width=60)
    nav = st.radio("MENU", ["Workstation", "Admin Config"])
    if st.button("RESET"): st.session_state.ext=[]; st.rerun()

# --------- ADMIN ---------
if nav == "Admin Config":
    st.title("🛠️ Config")
    if st.text_input("Password",type="password")=="admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening"])
        with t1:
            up1=st.file_uploader("Upload Panel 11",type=["xlsx"])
            if up1:
                df1, m1 = parser(io.BytesIO(up1.getvalue()), 11)
                if df1 is not None:
                    st.success(m1)
                    st.session_state.p11 = df1
                else: st.error(m1)
            e1 = st.data_editor(st.session_state.p11, hide_index=True)
            if st.button("Save P11"): st.session_state.p11=e1; st.success("OK")
            
        with t2:
            up2=st.file_uploader("Upload Screen",type=["xlsx"])
            if up2:
                df2, m2 = parser(io.BytesIO(up2.getvalue()), 3)
                if df2 is not None:
                    st.success(m2); st.session_state.p3 = df2
            e2 = st.data_editor(st.session_state.p3, hide_index=True)
            if st.button("Save Scr"): st.session_state.p3=e2; st.success("OK")

# --------- USER WORKSTATION (NO LOOPS = NO ERROR) ---------
else:
    st.markdown("""<div class='hospital-header'><h1>Maternity & Children Hospital - Tabuk</h1><h4>Serology Workstation</h4></div>""", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    L, R = st.columns([1, 1.5])
    
    with L:
        st.subheader("1. Screen/AC")
        ac = st.radio("AC", ["Negative","Positive"], horizontal=True)
        if ac=="Positive": st.error("STOP: DAT Required"); st.stop()
        st.write("---")
        # Explicit inputs
        st.session_state["s_I"] = st.selectbox("Scn I", ["Neg","w+","1+","2+"], key="box_s1")
        st.session_state["s_II"] = st.selectbox("Scn II", ["Neg","w+","1+","2+"], key="box_s2")
        st.session_state["s_III"] = st.selectbox("Scn III", ["Neg","w+","1+","2+"], key="box_s3")
        
    with R:
        st.subheader("2. Identification Panel (11 Cells)")
        # Explicit Grid (Safety)
        c_a, c_b = st.columns(2)
        with c_a:
            st.session_state["c_1"] = st.selectbox("Cell 1", ["Neg","w+","1+","2+","3+"], key="box_c1")
            st.session_state["c_2"] = st.selectbox("Cell 2", ["Neg","w+","1+","2+","3+"], key="box_c2")
            st.session_state["c_3"] = st.selectbox("Cell 3", ["Neg","w+","1+","2+","3+"], key="box_c3")
            st.session_state["c_4"] = st.selectbox("Cell 4", ["Neg","w+","1+","2+","3+"], key="box_c4")
            st.session_state["c_5"] = st.selectbox("Cell 5", ["Neg","w+","1+","2+","3+"], key="box_c5")
            st.session_state["c_6"] = st.selectbox("Cell 6", ["Neg","w+","1+","2+","3+"], key="box_c6")
        with c_b:
            st.session_state["c_7"] = st.selectbox("Cell 7", ["Neg","w+","1+","2+","3+"], key="box_c7")
            st.session_state["c_8"] = st.selectbox("Cell 8", ["Neg","w+","1+","2+","3+"], key="box_c8")
            st.session_state["c_9"] = st.selectbox("Cell 9", ["Neg","w+","1+","2+","3+"], key="box_c9")
            st.session_state["c_10"] = st.selectbox("Cell 10", ["Neg","w+","1+","2+","3+"], key="box_c10")
            st.session_state["c_11"] = st.selectbox("Cell 11", ["Neg","w+","1+","2+","3+"], key="box_c11")

    # ACTION
    st.write("---")
    
    if st.checkbox("🔍 Analyze Results"):
        # Map Inputs
        inputs_p = st.session_state  # Direct access via keys defined above
        inputs_s = st.session_state 
        
        ruled = set()
        p11_rows = [st.session_state.p11.iloc[i].to_dict() for i in range(11)]
        p3_rows = [st.session_state.p3.iloc[i].to_dict() for i in range(3)]
        
        # Exclude Panel
        for ag in AGS:
            for i in range(1, 12):
                if inputs_p[f"c_{i}"] == "Neg" and can_out(ag, p11_rows[i-1]):
                    ruled.add(ag); break
        # Exclude Screen
        sm = {"I":0,"II":1,"III":2}
        for s in ["I","II","III"]:
            if inputs_s[f"s_{s}"] == "Neg":
                for ag in AGS:
                    if ag not in ruled and can_out(ag, p3_rows[sm[s]]): ruled.add(ag)
        
        match = []
        for c in [x for x in AGS if x not in ruled]:
            miss = False
            for i in range(1, 12):
                if inputs_p[f"c_{i}"] != "Neg" and p11_rows[i-1].get(c,0)==0: miss=True
            if not miss: match.append(c)
            
        st.subheader("Interpretation")
        if not match: st.error("Inconclusive.")
        else:
            allow = True
            for m in match:
                ok, p, n, txt = chk_rule(m, st.session_state.p11, inputs_p, st.session_state.p3, inputs_s, st.session_state.ext)
                st.markdown(f"<div class='status-{'pass' if ok else 'fail'}'><b>Anti-{m}:</b> {txt} ({p} P / {n} N)</div>", unsafe_allow_html=True)
                if not ok: allow=False
            
            if allow:
                if st.button("🖨️ Print Report"):
                    rpt=f"""<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'>Pt:{nm} | {mr}<hr>Res: Anti-{', '.join(match)}<br>Valid (Rule of 3)<br><br>Sig:_________</div><div class='consultant-footer'><span style='color:darkred;font-weight:bold'>Dr. Haitham Ismail</span></div></div><script>window.print()</script>"""
                    st.markdown(rpt,unsafe_allow_html=True)
            else:
                with st.expander("➕ Add Cell"):
                    idx=st.text_input("ID"); rs=st.selectbox("R",["Neg","Pos"]); ph={}
                    cl=st.columns(len(match))
                    for i,mm in enumerate(match): 
                        ph[mm]=1 if cl[i].checkbox(mm) else 0
                    if st.button("Add"):
                        st.session_state.ext.append({"src":idx,"s":1 if rs=="Pos" else 0,"ph":ph}); st.rerun()
