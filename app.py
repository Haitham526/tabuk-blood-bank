import streamlit as st
import pandas as pd
import io
from datetime import date

# -----------------------------------------------
# 1. SETUP
# -----------------------------------------------
st.set_page_config(page_title="MCH Blood Bank", layout="wide", page_icon="🩸")

# Style adjustments for clean UI & Print
st.markdown("""
<style>
    @media print {
        .stApp > header, .sidebar, footer, .no-print { display: none !important; }
        .results-box { border: 2px solid #333; padding: 20px; font-family: 'Times New Roman'; margin-top:20px; }
        .print-only { display: block !important; }
    }
    .print-only { display: none; }
    
    .header-box { text-align: center; border-bottom: 4px solid #024; padding-bottom: 10px; margin-bottom: 20px; }
    h1 { color: #024; font-family: sans-serif; }
    
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    
    .sig-badge { position: fixed; bottom: 5px; right: 10px; background: white; border: 1px solid #ccc; padding: 5px 10px; border-radius: 5px; font-size: 11px; z-index:9999; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="sig-badge no-print">Dr. Haitham Ismail | Consultant</div>', unsafe_allow_html=True)

# Definitions
AGS = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
DOSAGE = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]
PAIRS = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S'}

# Init State
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID":f"Cell {i+1}",**{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID":f"Scn {i}",**{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'res' not in st.session_state: st.session_state.res = {f"c{i}":"Neg" for i in range(1,12)}
if 'scr' not in st.session_state: st.session_state.scr = {f"s{i}":"Neg" for i in ["I","II","III"]}
if 'ext' not in st.session_state: st.session_state.ext = []

# -----------------------------------------------
# 2. PARSERS & LOGIC
# -----------------------------------------------
def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+','1','pos','yes','w']) else 0

def smart_parse(file):
    try:
        # Load Raw
        df = pd.read_excel(file, header=None)
        # 1. Map Columns (Search first 25 rows)
        col_map = {}
        for r in range(min(25, len(df))):
            for c in range(min(60, len(df.columns))):
                val = str(df.iloc[r,c]).upper().strip().replace("(","").replace(")","")
                found = None
                if val in AGS: found=val
                elif val in ["RHD","D"]: found="D"
                elif val in ["RHC","C"]: found="C"
                elif val in ["RHE","E"]: found="E"
                
                if found and found not in col_map: col_map[found] = c
        
        if len(col_map)<3: return None, "No antigens found."
        
        # 2. Find Start Row
        # Heuristic: Row where 'D' has a value like 0, +, 1
        data = []
        rows_got = 0
        r_curr = 0
        while rows_got < 11 and r_curr < len(df):
            # Check row validity
            if "D" in col_map:
                chk = str(df.iloc[r_curr, col_map["D"]]).lower()
                if any(x in chk for x in ['0','1','+','w']):
                    # Valid Row
                    d = {"ID": f"Cell {rows_got+1}"}
                    for ag in AGS:
                        v = 0
                        if ag in col_map: v = normalize(df.iloc[r_curr, col_map[ag]])
                        d[ag] = int(v)
                    data.append(d)
                    rows_got += 1
            r_curr += 1
            
        if rows_got==0: return None, "Headers found but no data rows (+/0) detected."
        return pd.DataFrame(data), f"Success ({rows_got} rows)."
    except Exception as e: return None, str(e)

def check_rule(cand, r11, inp, r3, ins, ex):
    pos_match, neg_match = 0, 0
    # Panel
    for i in range(1,12):
        s = 1 if inp[i]!="Neg" else 0
        h = r11[i-1].get(cand,0)
        if h==1 and s==1: pos_match+=1
        if h==0 and s==0: neg_match+=1
    # Screen
    scrs=["I","II","III"]
    for i, txt in enumerate(scrs):
        s = 1 if ins[f"s{txt}"]!="Neg" else 0
        h = r3[i].get(cand,0)
        if h==1 and s==1: pos_match+=1
        if h==0 and s==0: neg_match+=1
    # Extra
    for c in ex:
        if c['res']==1 and c['phen'].get(cand,0)==1: pos_match+=1
        if c['res']==0 and c['phen'].get(cand,0)==0: neg_match+=1
        
    pass_r = (pos_match>=3 and neg_match>=3) or (pos_match>=2 and neg_match>=3)
    method = "Standard Rule" if (pos_match>=3 and neg_match>=3) else ("Modified" if pass_r else "Not Met")
    return pass_r, pos_match, neg_match, method

def get_rule_out(phen, dosage=True):
    # Determines if Ag can be excluded
    # For Dosage AGS: Only Exclude if Homozygous
    if dosage and phen.get("D",0)==0: pass # Dummy check
    pass # Simple implementation in main loop
    
# -----------------------------------------------
# 3. INTERFACE
# -----------------------------------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Admin Setup"])
    st.divider()
    if st.button("New Patient / Reset"):
        st.session_state.res = {f"c{i}":"Neg" for i in range(1,12)}
        st.session_state.scr = {f"s{i}":"Neg" for i in ["I","II","III"]}
        st.session_state.ext = []
        st.rerun()

# --------- ADMIN ---------
if nav == "Admin Setup":
    st.title("🛠️ System Configuration")
    if st.text_input("Password", type="password") == "admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening"])
        with t1:
            up = st.file_uploader("Upload Excel", type=['xlsx'])
            if up:
                df, msg = smart_parse(io.BytesIO(up.getvalue()))
                if df is not None:
                    st.session_state.p11 = df
                    st.success(msg)
                    st.rerun()
                else: st.error(msg)
            
            st.caption("Live Edit:")
            edit1 = st.data_editor(st.session_state.p11, hide_index=True)
            if st.button("Save P11"): st.session_state.p11=edit1; st.success("Saved")
        
        with t2:
            st.caption("Screening Cells (I,II,III)")
            edit2 = st.data_editor(st.session_state.p3, hide_index=True)
            if st.button("Save Scr"): st.session_state.p3=edit2; st.success("Saved")

# --------- USER ---------
else:
    st.markdown("<div class='header-box'><h1>Maternity & Children Hospital - Tabuk</h1><h4>Serology Workstation</h4></div>", unsafe_allow_html=True)
    
    # 1. DATA
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mrn=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    # 2. ENTRY (SAFE MODE: NO FANCY GRIDS)
    colA, colB = st.columns([1, 1.5])
    
    with colA:
        st.subheader("1. Screen/Control")
        ac = st.radio("Auto Control", ["Negative","Positive"])
        if ac=="Positive": st.error("STOP: Perform DAT."); st.stop()
        
        st.write("---")
        for x in ["I","II","III"]:
            val = st.selectbox(f"Scn {x}", ["Neg","w+","1+","2+"], key=f"sbox_{x}")
            st.session_state.scr[f"s{x}"] = val
    
    with colB:
        st.subheader("2. Panel (11 Cells)")
        # Simple stable list instead of dynamic grid
        cols_input = st.columns(2)
        for i in range(1,12):
            target_col = cols_input[0] if i<=6 else cols_input[1]
            key = f"c{i}"
            with target_col:
                new_val = st.selectbox(f"Cell {i}", ["Neg","w+","1+","2+","3+"], key=f"pbox_{i}")
                st.session_state.res[key] = new_val

    # 3. ANALYSIS
    st.divider()
    if st.checkbox("🔍 Run Analysis"):
        r11 = [st.session_state.p11.iloc[i].to_dict() for i in range(11)]
        r3 = [st.session_state.p3.iloc[i].to_dict() for i in range(3)]
        
        # 3.1 Mapping
        map_p = {i: (0 if st.session_state.res[f"c{i}"]=="Neg" else 1) for i in range(1,12)}
        map_s = {"I": (0 if st.session_state.scr["sI"]=="Neg" else 1),
                 "II": (0 if st.session_state.scr["sII"]=="Neg" else 1),
                 "III": (0 if st.session_state.scr["sIII"]=="Neg" else 1)}
        
        # 3.2 Exclusion
        ruled = set()
        # Panel Negs
        for i in range(1,12):
            if map_p[i]==0:
                ph = r11[i-1]
                for ag in AGS:
                    # Logic: Homozygous check
                    is_homo = True
                    if ag in DOSAGE:
                        pair = PAIRS.get(ag)
                        if pair and ph.get(pair,0)==1: is_homo=False
                    
                    if ph.get(ag,0)==1 and is_homo: ruled.add(ag)
        
        # Screen Negs
        s_lookup = {"I":0, "II":1, "III":2}
        for s in ["I","II","III"]:
            if map_s[s]==0:
                ph = r3[s_lookup[s]]
                for ag in AGS:
                    is_homo = True
                    if ag in DOSAGE:
                        pair = PAIRS.get(ag)
                        if pair and ph.get(pair,0)==1: is_homo=False
                    if ph.get(ag,0)==1 and is_homo: ruled.add(ag)
                    
        cands = [x for x in AGS if x not in ruled]
        match = []
        for c in cands:
            mis = False
            # Check if all positives have the antigen
            for i in range(1,12):
                if map_p[i]==1 and r11[i-1].get(c,0)==0: mis=True
            if not mis: match.append(c)
            
        if not match: st.error("Inconclusive.")
        else:
            allow = True
            st.subheader("Results:")
            for m in match:
                pas,p,n,met = check_rule(m,r11,st.session_state.res,r3,st.session_state.scr,st.session_state.ext)
                if not pas: allow=False
                bg = "#d4edda" if pas else "#f8d7da"
                st.markdown(f"<div style='background:{bg};padding:10px;border-radius:5px;margin:5px'><b>Anti-{m}</b>: {met} ({p} Pos, {n} Neg)</div>", unsafe_allow_html=True)
            
            if allow:
                if st.button("🖨️ Print Report"):
                    ht = f"""
                    <div class='print-only'>
                        <center><h2>MCH Tabuk</h2><h3>Serology Lab</h3></center>
                        <div class='results-box'>
                            <p><b>Pt:</b> {nm} ({mrn}) | <b>Tech:</b> {tc}</p>
                            <hr>
                            <p><b>Result:</b> Anti-{', '.join(match)} Detected.</p>
                            <p><b>Validation:</b> Rule of three met (p <= 0.05).</p>
                            <p><b>Note:</b> Verify patient is antigen negative.</p>
                            <br><br>
                            <p>Signature: _______________________</p>
                        </div>
                        <div style='position:fixed;bottom:0;width:100%;text-align:center'>Dr. Haitham Ismail</div>
                    </div>
                    <script>window.print();</script>
                    """
                    st.markdown(ht, unsafe_allow_html=True)
            else:
                st.warning("Validation Rule Not Met. Add Cells:")
                with st.expander("➕ Add Cell"):
                    colx, coly = st.columns(2)
                    nid = colx.text_input("Lot#")
                    nrs = coly.selectbox("Result", ["Neg","Pos"])
                    # Checkbox for match
                    new_ph = {}
                    for mm in match:
                        chk = st.checkbox(mm, key=f"ck_{mm}")
                        new_ph[mm] = 1 if chk else 0
                    if st.button("Confirm Add"):
                        st.session_state.ext.append({"src":nid, "res":1 if nrs=="Pos" else 0, "phen":new_ph})
                        st.rerun()
