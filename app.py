import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. SETUP
# ==========================================
st.set_page_config(page_title="MCH Serology", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    /* Printing & Header */
    @media print { 
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 4px double #8B0000; padding: 25px; font-family: 'Times New Roman'; }
    }
    .print-only { display: none; }
    
    .hospital-logo { color: #8B0000; text-align: center; border-bottom: 5px solid #8B0000; padding-bottom: 5px; font-family: sans-serif; font-weight: bold;}
    .lot-badge { background-color: #ffebee; color: #b71c1c; padding: 5px 10px; border-radius: 5px; font-weight: bold; margin-bottom: 20px;}
    
    /* Logic Status Boxes */
    .logic-pass { background-color: #e8f5e9; border-left: 5px solid #2e7d32; padding: 10px; color: #1b5e20; }
    .logic-suspect { background-color: #fff3cd; border-left: 5px solid #ffc107; padding: 10px; color: #856404; }
    .logic-fail { background-color: #f8d7da; border-left: 5px solid #dc3545; padding: 10px; color: #721c24; }
    .logic-info { background-color: #e3f2fd; border-left: 5px solid #1976d2; padding: 10px; color: #0d47a1; }

    /* Signatures */
    .dr-signature { 
        position: fixed; bottom: 0; width: 100%; right: 0; background: white; 
        text-align: center; padding: 5px; border-top: 2px solid #8B0000; z-index:99;
    }
    
    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class='dr-signature no-print'>
    <b>Dr. Haitham Ismail</b><br>
    <small>Clinical Hematology/Oncology & Transfusion Medicine Consultant</small>
</div>
""", unsafe_allow_html=True)

# DEFINITIONS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# FILTER LISTS
IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"] 
INSIGNIFICANT_AGS = ["Lea", "Lua", "Leb", "P1"] # M Removed from here to show as Significant
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# STATE
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'lot' not in st.session_state: st.session_state.lot = "Not Set"
if 'ext' not in st.session_state: st.session_state.ext = []

# Persistent DAT State
if 'dat_mode' not in st.session_state: st.session_state.dat_mode = False

# ==========================================
# 2. LOGIC FUNCTIONS
# ==========================================
def normalize_grade(val):
    s = str(val).lower().strip()
    return 0 if s in ["0", "neg"] else 1

def parse_paste(txt, limit=11):
    try:
        rows = txt.strip().split('\n')
        data = []
        c = 0
        for line in rows:
            if c >= limit: break
            parts = line.split('\t')
            row_v = []
            for p in parts:
                v_clean = str(p).lower().strip()
                val = 1 if any(x in v_clean for x in ['+', '1', 'pos', 'w']) else 0
                row_v.append(val)
            if len(row_v)>26: row_v=row_v[-26:]
            while len(row_v)<26: row_v.append(0)
            
            d_row = {"ID": f"C{c+1}" if limit==11 else f"S{c}"}
            for i, ag in enumerate(AGS): d_row[ag] = row_v[i]
            data.append(d_row)
            c+=1
        return pd.DataFrame(data), f"Updated {c} rows."
    except Exception as e: return None, str(e)

# --- [NOTE] Name Fixed: check_p_val ---
def check_p_val(cand, inputs_p, inputs_s, extras):
    p, n = 0, 0
    # Panel
    for i in range(1, 12):
        s = normalize_grade(inputs_p[i])
        h = st.session_state.p11.iloc[i-1].get(cand, 0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    s_idx = {"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s = normalize_grade(inputs_s[k])
        h = st.session_state.p3.iloc[s_idx[k]].get(cand, 0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extras
    for c in extras:
        s = normalize_grade(c['res'])
        h = c['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    
    return (p>=3 and n>=3) or (p>=2 and n>=3), p, n

# ==========================================
# 3. INTERFACE
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Supervisor"])
    if st.button("RESET DATA"): 
        st.session_state.ext=[]
        st.session_state.dat_mode=False
        st.rerun()

# --- ADMIN ---
if nav == "Supervisor":
    st.title("Config")
    if st.text_input("Pwd", type="password") == "admin123":
        st.session_state.lot = st.text_input("Lot No:", value=st.session_state.lot)
        t1, t2 = st.tabs(["Panel Copy-Paste", "Screen Copy-Paste"])
        with t1:
            p_in = st.text_area("Paste 11 Rows (Digits only)", height=200)
            if st.button("Save P11"):
                df, m = parse_paste(p_in, 11)
                if df is not None: st.session_state.p11=df; st.success(m)
            st.dataframe(st.session_state.p11)
        with t2:
            s_in = st.text_area("Paste 3 Rows", height=100)
            if st.button("Save Scr"):
                df, m = parse_paste(s_in, 3)
                if df is not None: st.session_state.p3=df; st.success(m)
            st.dataframe(st.session_state.p3)

# --- WORKSTATION ---
else:
    st.markdown(f"""
    <div class='hospital-logo'>
        <h2>Maternity & Children Hospital - Tabuk</h2>
        <div class='lot-badge'>Active Lot: {st.session_state.lot}</div>
    </div>
    """, unsafe_allow_html=True)
    
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()

    # FORM (STOPS CRASH)
    with st.form("main_form"):
        colL, colR = st.columns([1, 2.5])
        with colL:
            st.write("**Controls**")
            ac_res = st.radio("Auto Control", ["Negative", "Positive"])
            s1=st.selectbox("Scn I", GRADES)
            s2=st.selectbox("Scn II", GRADES)
            s3=st.selectbox("Scn III", GRADES)
        with colR:
            st.write("**Panel**")
            g1,g2=st.columns(2)
            with g1:
                c1=st.selectbox("1",GRADES,key="1"); c2=st.selectbox("2",GRADES,key="2"); c3=st.selectbox("3",GRADES,key="3")
                c4=st.selectbox("4",GRADES,key="4"); c5=st.selectbox("5",GRADES,key="5"); c6=st.selectbox("6",GRADES,key="6")
            with g2:
                c7=st.selectbox("7",GRADES,key="7"); c8=st.selectbox("8",GRADES,key="8"); c9=st.selectbox("9",GRADES,key="9")
                c10=st.selectbox("10",GRADES,key="10"); c11=st.selectbox("11",GRADES,key="11")
        
        submitted = st.form_submit_button("🚀 Run Analysis")

    # LOGIC HANDLING
    if submitted:
        # 1. Capture State
        st.session_state.ac_res = ac_res
        st.session_state.in_p = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
        st.session_state.in_s = {"I":s1,"II":s2,"III":s3}
        st.session_state.pos_cnt = sum([normalize_grade(x) for x in st.session_state.in_p.values()])
        
        if ac_res == "Positive":
            st.session_state.dat_mode = True # ENABLE DAT MODE
        else:
            st.session_state.dat_mode = False # DISABLE DAT MODE

    # ------------------ OUTPUT SECTION (PERSISTENT) ------------------
    if 'ac_res' in st.session_state:
        
        # SCENARIO A: AUTO CONTROL POSITIVE
        if st.session_state.dat_mode:
            st.markdown(f"""<div class='logic-fail'><h3>🚨 Auto-Control POSITIVE</h3>Process Stopped. Allo-antibody Logic Suspended.</div>""", unsafe_allow_html=True)
            
            # 1. Critical High Freq Check
            if st.session_state.pos_cnt == 11:
                st.markdown("""<div class='logic-suspect'><b>⚠️ CRITICAL WARNING: Pan-Agglutination + AC Positive.</b><br>Possible <b>Delayed Hemolytic Transfusion Reaction (DHTR)</b>.<br>Elution Mandatory. Do not result as simple WAIHA without checking history.</div>""", unsafe_allow_html=True)
            
            # 2. Interactive DAT (Persist outside Form)
            st.write("#### 🧪 Monospecific DAT Guide:")
            
            d_cont = st.container(border=True)
            c1, c2, c3 = d_cont.columns(3)
            # Use distinct keys
            dat_igg = c1.selectbox("Anti-IgG", ["Negative","Positive"], key="d_igg")
            dat_c3d = c2.selectbox("Anti-C3d", ["Negative","Positive"], key="d_c3d")
            dat_ctl = c3.selectbox("Control", ["Negative","Positive"], key="d_ctl")
            
            # Immediate Interpretation
            st.write("---")
            if dat_ctl == "Positive": st.error("Invalid Test (Control Pos).")
            elif dat_igg == "Positive" and dat_c3d == "Negative":
                 st.warning("**Interpretation: Probable WAIHA** (Warm Auto).\n* Alloantibodies may be masked.")
            elif dat_igg == "Negative" and dat_c3d == "Positive":
                 st.info("**Interpretation: Probable CAS** (Cold Agglutinin).\n* Use Pre-warm technique.")
            elif dat_igg == "Positive" and dat_c3d == "Positive":
                 st.warning("**Interpretation: Mixed AIHA.**")
                 
            st.caption("👉 Action: Refer to Blood Bank Physician.")

        # SCENARIO B: ALLO (AC NEG)
        elif st.session_state.get('pos_cnt', 0) == 11:
            st.markdown("<div class='logic-suspect'><b>⚠️ High Frequency Antibody.</b><br>All cells Positive, AC Negative.<br>Screen Siblings. Phenotype Patient.</div>", unsafe_allow_html=True)

        else:
            # 1. EXCLUSION
            ruled = set()
            p11 = st.session_state.p11
            p3  = st.session_state.p3
            # Panel
            for i in range(1,12):
                if normalize_grade(st.session_state.in_p[i])==0:
                    ph = p11.iloc[i-1]
                    for ag in AGS:
                        safe=True
                        if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                        if ph.get(ag,0)==1 and safe: ruled.add(ag)
            # Screen
            lookup={"I":0,"II":1,"III":2}
            for k in ["I","II","III"]:
                if normalize_grade(st.session_state.in_s[k])==0:
                    ph = p3.iloc[lookup[k]]
                    for ag in AGS:
                        if ag not in ruled:
                            safe=True
                            if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                            if ph.get(ag,0)==1 and safe: ruled.add(ag)
            # Extra
            for x in st.session_state.ext:
                 if normalize_grade(x['res'])==0:
                     for ag in AGS:
                         if x['ph'].get(ag,0)==1: ruled.add(ag)

            # 2. FILTER & SILENCE
            initial = [x for x in AGS if x not in ruled]
            # Remove Ignored
            active = [x for x in initial if x not in IGNORED_AGS]
            
            # --- SILENT D MASKING (The Request) ---
            final_cands = []
            is_D_found = "D" in active
            for c in active:
                if is_D and (c == "C" or c == "E"):
                    continue # Silently drop C and E, don't list them
                final_cands.append(c)
                
            st.subheader("Conclusion")
            
            sigs = [x for x in final_cands if x not in INSIGNIFICANT_AGS]
            colds = [x for x in final_cands if x in INSIGNIFICANT_AGS]
            
            if not sigs and not colds:
                st.error("No Match. Inconclusive.")
            else:
                if len(sigs) > 1:
                    st.warning(f"⚠️ Mixture: **Anti-{', '.join(sigs)}**")
                    st.write("**Strategy:**")
                    for t in sigs:
                         oth = [o for o in sigs if o!=t]
                         st.info(f"To Confirm {t}: Need Cell {t}+ / {' '.join(oth)} neg")
                elif len(sigs) == 1:
                    st.success(f"✅ Identity: **Anti-{sigs[0]}**")
                    st.write(f"*Phenotype patient for {sigs[0]} (Must be Negative)*")
                    if sigs[0] == "c": st.error("Give R1R1 Units.")
                
                if colds: st.caption(f"Insignificant: {', '.join(colds)}")
                
                # VALIDATION
                valid_all = True
                for ab in (sigs+colds):
                    # CORRECTED NAME FUNCTION CALL
                    ok, p, n = check_p_val(ab, st.session_state.in_p, st.session_state.in_s, st.session_state.ext)
                    icon = "✅" if ok else "❌"
                    st.markdown(f"**{ab}**: {icon} Rule of 3 {'Met' if ok else 'Fail'} ({p} Pos/{n} Neg)")
                    if not ok: valid_all = False
                
                if valid_all:
                    if st.button("🖨️ Official Report"):
                        ht = f"<div class='print-only'><br><center><h2>Maternity & Children Hospital - Tabuk</h2></center><div class='result-sheet'>Pt:{nm}<br><b>Conclusion: Anti-{', '.join(sigs)}</b><br>{'('.join(colds)+')' if colds else ''}<br>Verified p<=0.05.<br><br>Sig:________</div></div><script>window.print()</script>"
                        st.markdown(ht, unsafe_allow_html=True)
                else:
                    st.warning("Validation Required (See below)")
    
    # 4. EXTRA CELL ADDITION
    if st.session_state.dat_mode == False:
        with st.expander("➕ Add Selected Cell"):
            with st.form("exx"):
                i=st.text_input("ID"); r=st.selectbox("R",GRADES)
                st.write("Antigens:")
                cols = st.columns(6)
                new_ph = {a:0 for a in AGS}
                for idx, a in enumerate(AGS):
                    if cols[idx%6].checkbox(a): new_ph[a]=1
                if st.form_submit_button("Add"):
                    st.session_state.ext.append({"res":r, "ph":new_ph})
                    st.rerun()

    if st.session_state.ext: st.table(pd.DataFrame(st.session_state.ext))
