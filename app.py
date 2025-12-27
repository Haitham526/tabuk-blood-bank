import streamlit as st
import pandas as pd
import io
from datetime import date

# --------------------------------------------------------
# 1. SETUP
# --------------------------------------------------------
st.set_page_config(page_title="MCH Tabuk Bank", layout="wide", page_icon="🏥")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .print-only { display: block !important; } .results-box { border: 2px solid #333; padding: 20px; font-family: 'Times New Roman'; } .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; } }
    .print-only { display: none; }
    .header-box { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    .status-ok { background:#d4edda; color:#155724; padding:8px; margin:2px; border-radius:4px;}
    .status-no { background:#f8d7da; color:#721c24; padding:8px; margin:2px; border-radius:4px;}
    .sig-badge { position: fixed; bottom: 10px; right: 15px; background: white; border: 1px solid #ccc; padding: 5px; z-index: 99; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='sig-badge no-print'>Dr. Haitham Ismail</div>", unsafe_allow_html=True)

# CONSTANTS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# STATE
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'ext' not in st.session_state: st.session_state.ext = []

# --------------------------------------------------------
# 2. LOGIC
# --------------------------------------------------------
def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

def smart_parse(file):
    try:
        xls = pd.ExcelFile(file)
        for sheet in xls.sheet_names:
            df = pd.read_excel(file, sheet_name=sheet, header=None)
            
            # Map Cols
            col_map = {}
            head_row = -1
            
            for r in range(min(30, len(df))):
                temp = {}
                matches = 0
                for c in range(min(60, len(df.columns))):
                    val = str(df.iloc[r, c]).strip().replace(" ","")
                    
                    det = None
                    if val in ["c","C","e","E","k","K","s","S"]: det = val
                    elif val.upper() in ["D","RHD"]: det = "D"
                    else:
                        vup = val.upper()
                        if vup in AGS: det = vup
                    
                    if det:
                        temp[det] = c
                        matches += 1
                
                if matches >= 4:
                    head_row = r
                    col_map = temp
                    break
            
            # Extract
            if head_row != -1:
                data = []
                found = 0
                curr = head_row + 1
                while found < 11 and curr < len(df):
                    is_val = False
                    # Check near D column for data
                    chk_cols = []
                    if "D" in col_map: chk_cols.extend([col_map["D"], col_map["D"]-1, col_map["D"]+1])
                    
                    for cx in chk_cols:
                        if cx >=0 and cx < len(df.columns):
                            raw = str(df.iloc[curr, cx]).lower()
                            if any(x in raw for x in ['+','0','1','w']): is_val = True; break
                    
                    if is_val:
                        row = {"ID": f"C{found+1}"}
                        for ag in AGS:
                            v = 0
                            if ag in col_map:
                                center = col_map[ag]
                                # Scan neighbors too (Magnetic)
                                neighbors = [center, center-1, center+1]
                                for nc in neighbors:
                                    if nc >=0 and nc < len(df.columns):
                                        if normalize(df.iloc[curr, nc]) == 1:
                                            v = 1; break
                            row[ag] = int(v)
                        data.append(row)
                        found += 1
                    curr += 1
                
                if found >= 1: return pd.DataFrame(data), f"Read from {sheet} OK"
                
        return None, "No data found."
    except Exception as e: return None, str(e)

def can_out(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr=PAIRS.get(ag)
        if pr and ph.get(pr,0)==1: return False
    return True

def rule_check(c, p11, in_p, p3, in_s, ex):
    p, n = 0, 0
    # Panel
    for i in range(1,12):
        s = 1 if in_p[i]!="Neg" else 0
        h = p11.iloc[i-1].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    for i, s in enumerate(["I","II","III"]):
        sc = 1 if in_s[s]!="Neg" else 0
        h = p3.iloc[i].get(c,0)
        if sc==1 and h==1: p+=1
        if sc==0 and h==0: n+=1
    # Ext
    for x in ex:
        if x['s']==1 and x['ph'].get(c,0)==1: p+=1
        if x['s']==0 and x['ph'].get(c,0)==0: n+=1
    
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    t = "Std Rule" if (p>=3 and n>=3) else ("Modified" if ok else "Fail")
    return ok, p, n, t

# =========================================================
# 3. INTERFACE (FORM BASED - ERROR PROOF)
# =========================================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png",width=50)
    nav = st.radio("Menu", ["Workstation", "Admin Config"])
    st.divider()
    if st.button("New Patient"):
        st.session_state.ext = []
        st.rerun()

# ----------------- ADMIN -----------------
if nav == "Admin Config":
    st.title("System Configuration")
    if st.text_input("Password",type="password")=="admin123":
        
        st.info("💡 Tip: Upload PDF-Excel or Copy/Paste 0 and 1 here manually.")
        
        tab1, tab2 = st.tabs(["Panel 11", "Screen 3"])
        with tab1:
            u1=st.file_uploader("Upload Panel", type=["xlsx"])
            if u1:
                d1,m1 = smart_parse(io.BytesIO(u1.getvalue()))
                if d1 is not None:
                    st.success(m1)
                    st.session_state.p11=d1
                else: st.error(m1)
            
            st.caption("Live Editor:")
            e1 = st.data_editor(st.session_state.p11, hide_index=True)
            if st.button("Save P11"): st.session_state.p11=e1; st.success("OK")
            
        with tab2:
            st.caption("Edit Screen:")
            e2 = st.data_editor(st.session_state.p3, hide_index=True)
            if st.button("Save Screen"): st.session_state.p3=e2; st.success("OK")

# ----------------- USER WORKSTATION -----------------
else:
    st.markdown("<div class='header-box'><h2>Maternity & Children Hospital - Tabuk</h2></div>", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    # 🔴 START OF FORM (THIS STOPS THE CRASHES)
    with st.form("analysis_form"):
        colL, colR = st.columns([1, 2])
        
        with colL:
            st.subheader("1. Controls")
            ac_res = st.radio("Auto Control", ["Negative","Positive"])
            st.write("---")
            si = st.selectbox("Scn I", ["Neg","w+","1+","2+"])
            sii = st.selectbox("Scn II", ["Neg","w+","1+","2+"])
            siii = st.selectbox("Scn III", ["Neg","w+","1+","2+"])
            
        with colR:
            st.subheader("2. Panel Reactions")
            # HARDCODED INPUTS INSIDE FORM
            ca, cb = st.columns(2)
            with ca:
                c1 = st.selectbox("Cell 1", ["Neg","w+","1+","2+"])
                c2 = st.selectbox("Cell 2", ["Neg","w+","1+","2+"])
                c3 = st.selectbox("Cell 3", ["Neg","w+","1+","2+"])
                c4 = st.selectbox("Cell 4", ["Neg","w+","1+","2+"])
                c5 = st.selectbox("Cell 5", ["Neg","w+","1+","2+"])
                c6 = st.selectbox("Cell 6", ["Neg","w+","1+","2+"])
            with cb:
                c7 = st.selectbox("Cell 7", ["Neg","w+","1+","2+"])
                c8 = st.selectbox("Cell 8", ["Neg","w+","1+","2+"])
                c9 = st.selectbox("Cell 9", ["Neg","w+","1+","2+"])
                c10 = st.selectbox("Cell 10", ["Neg","w+","1+","2+"])
                c11 = st.selectbox("Cell 11", ["Neg","w+","1+","2+"])
        
        st.write("---")
        # SUBMIT BUTTON TRIGGER
        submit = st.form_submit_button("🚀 Submit & Analyze")
    
    # 🟢 LOGIC RUNS ONLY AFTER SUBMIT
    if submit:
        if ac_res == "Positive":
            st.error("🚨 Auto Control Positive: Perform DAT (Polyspecific -> Mono).")
        else:
            # Gather inputs into map
            inp_p = {1:c1, 2:c2, 3:c3, 4:c4, 5:c5, 6:c6, 7:c7, 8:c8, 9:c9, 10:c10, 11:c11}
            inp_s = {"I":si, "II":sii, "III":siii}
            
            # Logic Vars
            r11 = [st.session_state.p11.iloc[i].to_dict() for i in range(11)]
            r3  = [st.session_state.p3.iloc[i].to_dict() for i in range(3)]
            ruled = set()
            
            # Exclusion
            for ag in AGS:
                for i in range(1, 12):
                    if inp_p[i]=="Neg" and can_out(ag, r11[i-1]): ruled.add(ag); break
            sm={"I":0,"II":1,"III":2}
            for k in ["I","II","III"]:
                if inp_s[k]=="Neg":
                    for ag in AGS: 
                        if ag not in ruled and can_out(ag, r3[sm[k]]): ruled.add(ag)
            
            # Inclusion
            match = []
            for c in [x for x in AGS if x not in ruled]:
                mis=False
                for i in range(1,12):
                    if inp_p[i]!="Neg" and r11[i-1].get(c,0)==0: mis=True
                if not mis: match.append(c)
            
            # Output
            if not match: st.error("No pattern matched.")
            else:
                allow_final = True
                for m in match:
                    ok, p, n, msg = rule_check(m, st.session_state.p11, inp_p, st.session_state.p3, inp_s, st.session_state.ext)
                    cls = "status-ok" if ok else "status-no"
                    st.markdown(f"<div class='{cls}'><b>Anti-{m}:</b> {msg} ({p}P / {n}N)</div>",unsafe_allow_html=True)
                    if not ok: allow_final = False
                
                if allow_final:
                    h=f"<div class='print-only'><center><h2>MCH Tabuk</h2></center><br>Pt:{nm}<hr>Res: Anti-{', '.join(match)}<br>Valid Rule 3.<br><br>Sig:_________<div class='consultant-footer'>Dr. Haitham Ismail</div></div><script>window.print()</script>"
                    st.markdown(h, unsafe_allow_html=True)
                    st.info("Analysis Validated. Ready to print.")
                else:
                    st.warning("⚠️ Validation failed (Rule of 3). Add Extra Cells below.")

    # EXTRA CELLS (OUTSIDE FORM TO ALLOW DYNAMIC ADDITION)
    if st.session_state.ext:
        st.write("Added Cells:")
        st.table(pd.DataFrame(st.session_state.ext))

    with st.expander("➕ Add External Cell"):
        with st.form("add_cell"):
            idx=st.text_input("ID")
            res=st.selectbox("Res",["Neg","Pos"])
            st.write("Phenotype:")
            # Use simple text area for ease inside form or hardcode commons
            # For simplicity: Hardcode matches if known, else let user select
            # Simplest approach for stable UI:
            ag_txt = st.multiselect("Select Present Antigens:", AGS)
            if st.form_submit_button("Add Cell"):
                ph = {a:1 if a in ag_txt else 0 for a in AGS}
                st.session_state.ext.append({"src":idx, "s":1 if res=="Pos" else 0, "res":1 if res=="Pos" else 0, "ph":ph, "p":ph})
                st.rerun()
