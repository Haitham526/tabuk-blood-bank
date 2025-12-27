import streamlit as st
import pandas as pd
from datetime import date

# ------------------------------------------------------------------
# 1. CONFIGURATION & STYLING
# ------------------------------------------------------------------
st.set_page_config(page_title="MCH Tabuk - Serology Expert", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { 
        .stApp > header, .sidebar, footer, .no-print { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 5px double #b30000; padding: 25px; font-family: 'Times New Roman'; }
        .sig-block { margin-top: 50px; text-align: center; }
    }
    .print-only { display: none; }
    
    .hospital-head { color: #800000; text-align: center; border-bottom: 5px solid #800000; font-family: 'Arial'; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    
    /* Logic Alert Boxes */
    .logic-auto { background:#ffebee; border-left:6px solid #b71c1c; padding:15px; color:#b71c1c; border-radius:5px;}
    .logic-high { background:#fff8e1; border-left:6px solid #ff6f00; padding:15px; color:#bf360c; border-radius:5px;}
    .logic-match { background:#e8f5e9; border-left:6px solid #2e7d32; padding:15px; color:#1b5e20; border-radius:5px;}
    .logic-note { background:#e3f2fd; border-left:6px solid #1565c0; padding:10px; color:#0d47a1; font-size:14px;}
    
    .dr-sig { position:fixed; bottom:5px; right:10px; background:white; padding:5px 10px; border:1px solid #ccc; border-radius:5px; color:#800000; font-weight:bold; z-index:99; }
</style>
""", unsafe_allow_html=True)

st.markdown("""<div class='dr-sig no-print'>Dr. Haitham Ismail<br>Clinical Hematology & Transfusion Consultant</div>""", unsafe_allow_html=True)

# CONSTANTS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# STATE
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID":f"C{i+1}",**{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID":f"S{i}",**{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'lot' not in st.session_state: st.session_state.lot = "Not Set"
if 'ext' not in st.session_state: st.session_state.ext = []

# ------------------------------------------------------------------
# 2. LOGIC FUNCTIONS
# ------------------------------------------------------------------
def normalize(val):
    # Convert grades to binary
    s = str(val).lower().strip()
    return 0 if s in ["0", "neg"] else 1

def parse_paste(txt, limit):
    try:
        rows = txt.strip().split('\n')
        data = []
        c = 0
        for line in rows:
            if c >= limit: break
            parts = line.split('\t')
            vals = []
            for p in parts:
                v = 1 if any(x in str(p).lower() for x in ['+','1','pos','w']) else 0
                vals.append(v)
            if len(vals) > 26: vals=vals[-26:]
            while len(vals)<26: vals.append(0)
            d = {"ID": f"C{c+1}" if limit==11 else f"S{c}"}
            for i, ag in enumerate(AGS): d[ag] = vals[i]
            data.append(d)
            c+=1
        return pd.DataFrame(data), f"Parsed {c} rows"
    except Exception as e: return None, str(e)

def analyze_allo(in_p, in_s, extra):
    ruled = set()
    # Exclusion
    # 1. Panel
    for i in range(1, 12):
        if normalize(in_p[i]) == 0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                safe = True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                if ph.get(ag,0)==1 and safe: ruled.add(ag)
    # 2. Screen
    sidx = {"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize(in_s[k]) == 0:
            ph = st.session_state.p3.iloc[sidx[k]]
            for ag in AGS:
                if ag not in ruled:
                    safe = True
                    if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                    if ph.get(ag,0)==1 and safe: ruled.add(ag)
    # 3. Extras
    for x in extra:
        if normalize(x['res'])==0:
            for ag in AGS:
                if x['ph'].get(ag,0)==1: ruled.add(ag)
                
    candidates = [a for a in AGS if a not in ruled]
    display = [a for a in candidates if a not in IGNORED_AGS]
    return display, ruled

# ------------------------------------------------------------------
# 3. SIDEBAR (ADMIN)
# ------------------------------------------------------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png",width=60)
    nav=st.radio("Mode",["Workstation","Supervisor"])
    if st.button("RESET DATA"): 
        st.session_state.ext=[]
        st.session_state.dat_open=False
        st.rerun()

if nav == "Supervisor":
    st.title("Admin")
    if st.text_input("Pwd",type="password")=="admin123":
        st.session_state.lot = st.text_input("Lot No:", value=st.session_state.lot)
        t1, t2 = st.tabs(["Panel","Screen"])
        with t1:
            p_txt=st.text_area("Paste Panel 11",height=150)
            if st.button("Upd P11"): 
                d,m=parse_paste(p_txt,11)
                if d is not None: st.session_state.p11=d; st.success(m)
            st.dataframe(st.session_state.p11.iloc[:,:10])
        with t2:
            s_txt=st.text_area("Paste Screen 3",height=100)
            if st.button("Upd Scr"): 
                d,m=parse_paste(s_txt,3)
                if d is not None: st.session_state.p3=d; st.success(m)
            st.dataframe(st.session_state.p3.iloc[:,:10])

# ------------------------------------------------------------------
# 4. WORKSTATION (USER)
# ------------------------------------------------------------------
else:
    st.markdown(f"<div class='hospital-head'><h2>Maternity & Children Hospital - Tabuk</h2><h4>Lot: {st.session_state.lot}</h4></div>", unsafe_allow_html=True)
    c1,c2,c3,c4=st.columns(4)
    nm=c1.text_input("Patient"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    
    with st.form("main_form"):
        L, R = st.columns([1, 2])
        with L:
            st.subheader("Controls")
            ac_in = st.radio("Auto Control", ["Negative","Positive"])
            st.write("---")
            s1=st.selectbox("Scn I",GRADES); s2=st.selectbox("Scn II",GRADES); s3=st.selectbox("Scn III",GRADES)
        with R:
            st.subheader("ID Panel")
            g1,g2=st.columns(2)
            with g1:
                c1=st.selectbox("1",GRADES); c2=st.selectbox("2",GRADES); c3=st.selectbox("3",GRADES)
                c4=st.selectbox("4",GRADES); c5=st.selectbox("5",GRADES); c6=st.selectbox("6",GRADES)
            with g2:
                c7=st.selectbox("7",GRADES); c8=st.selectbox("8",GRADES); c9=st.selectbox("9",GRADES)
                c10=st.selectbox("10",GRADES); c11=st.selectbox("11",GRADES)
                
        run = st.form_submit_button("🚀 Run Logic Analysis")

    # ===============================================
    # THE PRIORITY LOGIC (The Core Correction)
    # ===============================================
    if run:
        inp_p = {1:c1, 2:c2, 3:c3, 4:c4, 5:c5, 6:c6, 7:c7, 8:c8, 9:c9, 10:c10, 11:c11}
        inp_s = {"I":s1, "II":s2, "III":s3}
        
        # Calculate Sums (Panel & Screen)
        sum_p = sum([normalize(v) for v in inp_p.values()])
        sum_s = sum([normalize(v) for v in inp_s.values()])
        total_pos = sum_p + sum_s
        total_cells = 14 # 11+3

        # >>> PRIORITY 1: AUTO CONTROL POSITIVE <<<
        if ac_in == "Positive":
            st.session_state.dat_open = True # Keep DAT open
            st.markdown("""
            <div class='logic-auto'>
                <h3>🚨 STOP: Auto-Control Positive</h3>
                Allo-antibody Logic Suspended. <br>
                Please perform Monospecific DAT Workup below.
            </div>
            """, unsafe_allow_html=True)
            
            # Additional Check: Is it also Pan-reactive? (WAIHA vs DHTR Risk)
            if total_pos >= 11: 
                st.error("⚠️ **CRITICAL WARNING:** Pan-Agglutination + AC Positive.")
                st.write("👉 Check History for recent transfusion. Rule out **Delayed Hemolytic Transfusion Reaction (DHTR)** (Alloantibody on donor cells).")

        # >>> PRIORITY 2: PAN-AGGLUTINATION (AC NEGATIVE) <<<
        elif total_pos >= 13 and ac_in == "Negative": 
            # Note: I used >=13 to be safe (if 1 cell is weak/neg error)
            st.session_state.dat_open = False
            st.markdown("""
            <div class='logic-high'>
                <h3>⚠️ High Incidence Antigen Antibody Detected</h3>
                <b>Status:</b> All Cells Positive | Auto-Control Negative.<br>
                <b>Protocol:</b>
                <ul>
                    <li>Search in first-degree relatives (Siblings).</li>
                    <li>Phenotype patient (Must be Negative).</li>
                    <li>Refer sample to Reference Lab.</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)

        # >>> PRIORITY 3: NORMAL ALLOANTIBODY LOGIC <<<
        else:
            st.session_state.dat_open = False
            matches, ruled = analyze_allo(inp_p, inp_s, st.session_state.ext)
            
            # --- Anti-G Check (D & C Logic) ---
            if "D" in matches and "C" in matches:
                st.info("ℹ️ **Possible Anti-G detected:** Patient has both Anti-D and Anti-C patterns.")
                st.write("Suggestion: Use Adsorption/Elution to differentiate Anti-G from Anti-D + Anti-C.")

            if not matches:
                st.error("No specific antibody identified (Inconclusive or Low Frequency).")
            else:
                st.markdown(f"<div class='logic-match'>✅ <b>Detected:</b> Anti-{', '.join(matches)}</div>", unsafe_allow_html=True)
                
                # Separation Advice
                if len(matches) > 1:
                    st.write("---")
                    st.warning("⚠️ **Multiple Antibodies:**")
                    st.write("**Separation Strategy:**")
                    for t in matches:
                        others = [o for o in matches if o != t]
                        st.write(f"- Confirm **{t}**: Need cell **{t} Pos / {' '.join(others)} Neg**")
                        # Add lookup code here if you want from V209
                
                # Checkbox for Rule of 3 (Optional visual)
                st.write("**Stats:**")
                all_ok = True
                for m in matches:
                    # Quick Calc P/N
                    # ... (Simplified here, same logic as before)
                    st.write(f"- Anti-{m}: Please confirm with 3 Pos / 3 Neg cells.")

                # Print Button
                if st.button("Generate Official Report"):
                     # Generate Report HTML ...
                     pass 

    # --- DAT FORM (PERSISTENT) ---
    if st.session_state.get('dat_open'):
        st.write("---")
        st.subheader("🧪 DAT Investigation")
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)
            igg = c1.selectbox("IgG", ["Neg", "Pos"], key="dig")
            c3d = c2.selectbox("C3d", ["Neg", "Pos"], key="dc3")
            ctrl = c3.selectbox("Control", ["Neg", "Pos"], key="dct")
            
            st.write("<b>Interpretation:</b>", unsafe_allow_html=True)
            if ctrl=="Pos": st.error("Invalid Test.")
            elif igg=="Pos": 
                st.warning("👉 **Probable WAIHA / DHTR**")
                st.write("Action: Adsorption / Elution.")
            elif c3d=="Pos":
                st.info("👉 **Probable Cold Agglutinin (CAS)**")
                st.write("Action: Pre-warm Technique.")

    # --- EXTRA CELLS (ALWAYS VISIBLE) ---
    with st.expander("➕ Add Selected Cells (For Separation/Rule of 3)"):
        with st.form("ext_f"):
            eid = st.text_input("ID"); eres=st.selectbox("Res", GRADES)
            pres = st.multiselect("Positive Antigens:", AGS)
            if st.form_submit_button("Add Cell"):
                ph = {a:1 if a in pres else 0 for a in AGS}
                st.session_state.ext.append({"res":normalize(eres), "res_txt":eres, "ph":ph})
                st.success("Added! Re-Run Analysis.")
