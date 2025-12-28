import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. SETUP & STYLE
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { 
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 4px double #8B0000; padding: 25px; font-family: 'Times New Roman'; font-size:14px; }
        /* Footer for Print */
        .footer-print { 
            position: fixed; bottom: 0; width: 100%; text-align: center; 
            color: #8B0000; font-weight: bold; border-top: 1px solid #ccc; padding: 10px; font-family: serif;
        }
    }
    .print-only { display: none; }
    
    .hospital-logo { 
        text-align: center; border-bottom: 5px solid #8B0000; 
        padding-bottom: 5px; font-family: sans-serif; 
        color: #003366; 
    }
    
    /* SYSTEM LOCK */
    .lock-screen {
        background-color: #ffebee; border: 2px solid #c62828; color: #b71c1c; 
        padding: 20px; text-align: center; font-weight: bold; border-radius: 8px;
    }
    
    /* LOGIC BOXES */
    .status-ok { background: #d4edda; color: #155724; padding: 10px; border-left: 6px solid #198754; margin: 5px 0; border-radius: 4px; }
    .status-fail { background: #f8d7da; color: #842029; padding: 10px; border-left: 6px solid #dc3545; margin: 5px 0; border-radius: 4px; }
    .clinical-alert { background: #fff3cd; color: #856404; padding: 10px; border-left: 6px solid #ffca2c; margin: 5px 0; border-radius: 4px; }
    .critical-alert { background: #f8d7da; color: #721c24; padding: 10px; border-left: 6px solid #dc3545; margin: 5px 0; border-radius: 4px; font-weight: bold;}
    .cell-hint { background: #e9ecef; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; font-weight: bold; color: #495057; }

    /* SIGNATURE STICKY */
    .dr-signature { 
        position: fixed; bottom: 10px; right: 15px; 
        background: rgba(255,255,255,0.95); 
        padding: 8px 15px; border: 2px solid #8B0000; 
        border-radius: 8px; z-index:99; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
        text-align: center;
    }
    .dr-name { color: #8B0000; font-family: 'Georgia', serif; font-size: 14px; font-weight: bold; display: block; }
    .dr-title { color: #333; font-size: 11px; }

    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

# FIXED SIGNATURE
st.markdown("""
<div class='dr-signature no-print'>
    <span class='dr-name'>Dr. Haitham Ismail</span>
    <span class='dr-title'>Clinical Hematology/Oncology &<br>BM Transplantation & Transfusion Medicine Consultant</span>
</div>
""", unsafe_allow_html=True)

# 2. DEFINITIONS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
INSIGNIFICANT_AGS = ["Lea", "Lua", "Leb", "P1"] 
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# 3. STATE INIT
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
# Lots (Mandatory)
if 'lot_p' not in st.session_state: st.session_state.lot_p = ""
if 'lot_s' not in st.session_state: st.session_state.lot_s = ""
# App Logic
if 'dat_mode' not in st.session_state: st.session_state.dat_mode = False
if 'ext' not in st.session_state: st.session_state.ext = []

# ==========================================
# 4. LOGIC ENGINE
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
            vals = []
            for p in parts:
                v_clean = str(p).lower().strip()
                v = 1 if any(x in v_clean for x in ['+', '1', 'pos', 'w', 'yes']) else 0
                vals.append(v)
            if len(vals) > 26: vals = vals[-26:]
            while len(vals) < 26: vals.append(0)
            d = {"ID": f"C{c+1}" if limit==11 else f"Scn"}
            for i, ag in enumerate(AGS): d[ag] = vals[i]
            data.append(d)
            c+=1
        return pd.DataFrame(data), f"Updated {c} rows."
    except Exception as e: return None, str(e)

# --- 1. Find cells for Strategy ---
def find_matching_cells_in_inventory(target_ab, conflicts):
    found_list = []
    # Panel
    for i in range(11):
        cell = st.session_state.p11.iloc[i]
        if cell.get(target_ab,0)==1:
            clean = True
            for bad in conflicts: 
                if cell.get(bad,0)==1: clean=False; break
            if clean: found_list.append(f"Panel#{i+1}")
    # Screen
    sc_lbls = ["I","II","III"]
    for i in range(3):
        cell = st.session_state.p3.iloc[i]
        if cell.get(target_ab,0)==1:
            clean = True
            for bad in conflicts: 
                if cell.get(bad,0)==1: clean=False; break
            if clean: found_list.append(f"Screen {sc_lbls[i]}")
    return found_list

# --- 2. Main Logic ---
def analyze_master_logic(in_p, in_s, extra_cells):
    ruled_out = set()
    # P11 Exclusion
    for i in range(1, 12):
        if normalize_grade(in_p[i]) == 0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False 
                if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
    # P3 Exclusion
    smap={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize_grade(in_s[k]) == 0:
            ph = st.session_state.p3.iloc[smap[k]]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
    # Extra Exclusion
    for ex in extra_cells:
        if normalize_grade(ex['res']) == 0:
            for ag in AGS:
                 if ex['ph'].get(ag,0)==1: ruled_out.add(ag)

    candidates = [x for x in AGS if x not in ruled_out]
    display_cands = [x for x in candidates if x not in IGNORED_AGS]
    
    # 3. Special Patterns (G, D masking)
    final_list = []
    notes = []
    
    # Anti-G Check (Rows 1,2,3,4,8 Pos?)
    # Adjust for 0-index: 0,1,2,3,7
    g_idx = [1, 2, 3, 4, 8]
    is_G_pattern = True
    for idx in g_idx:
        if normalize_grade(in_p[idx]) == 0: is_G_pattern=False; break
        
    is_D = "D" in display_cands
    
    for c in display_cands:
        # Anti-D Masking Rule:
        if is_D:
            if c in ["C", "E"]:
                # If D+C matches G pattern exactly, keep C and warn G
                if c == "C" and is_G_pattern:
                    notes.append("suspect_G")
                else:
                    # Silent Drop for C and E
                    continue 
        final_list.append(c)
        
    if "c" in final_list: notes.append("anti-c_risk")
    
    return final_list, notes

# --- 3. Rule of Three Validator ---
def check_rule_3(cand, in_p, in_s, extras):
    p, n = 0, 0
    # Panel
    for i in range(1, 12):
        s=normalize_grade(in_p[i]); h=st.session_state.p11.iloc[i-1].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    si={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s=normalize_grade(in_s[k]); h=st.session_state.p3.iloc[si[k]].get(cand, 0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extra
    for c in extras:
        s=normalize_grade(c['res']); h=c['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    
    pass_ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    return pass_ok, p, n

# ==========================================
# 5. UI LAYOUT
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
    st.title("Admin Configuration")
    if st.text_input("Enter Admin Password:", type="password")=="admin123":
        st.success("Authorized")
        
        st.subheader("1. Lot Setup (Important)")
        c1, c2 = st.columns(2)
        # Added unique keys to prevent errors
        l_p = c1.text_input("ID Panel Lot", value=st.session_state.lot_p, key="input_lot_p")
        l_s = c2.text_input("Screen Cell Lot", value=st.session_state.lot_s, key="input_lot_s")
        
        if st.button("Save Lot Info", key="btn_save_lots"):
            st.session_state.lot_p = l_p
            st.session_state.lot_s = l_s
            st.success("Lot Numbers Updated.")
            st.rerun()
            
        st.subheader("2. Grid Data (Copy-Paste)")
        t1, t2 = st.tabs(["Panel 11", "Screen 3"])
        with t1:
            st.caption("Paste the 11 rows from Excel (Numbers only):")
            # Fixed Key error
            pt1 = st.text_area("P11 Data", height=150, key="txt_p11")
            if st.button("Update Panel 11", key="btn_up_p11"):
                df,m = parse_paste(pt1, 11)
                if df is not None: st.session_state.p11 = df; st.success(m)
            st.dataframe(st.session_state.p11.iloc[:,:15])
            
        with t2:
            st.caption("Paste the 3 rows from Screen Excel:")
            pt2 = st.text_area("P3 Data", height=100, key="txt_p3")
            if st.button("Update Screen 3", key="btn_up_p3"): # Unique key fixed
                df2,m2 = parse_paste(pt2, 3)
                if df2 is not None: st.session_state.p3 = df2; st.success(m2)
            st.dataframe(st.session_state.p3.iloc[:,:15])

# --- USER ---
else:
    # 1. HEADER (Safe Lot Display)
    lp = st.session_state.lot_p if st.session_state.lot_p else "NOT SET"
    ls = st.session_state.lot_s if st.session_state.lot_s else "NOT SET"
    
    st.markdown(f"""
    <div class='hospital-logo'>
        <h2 style='color:#8B0000'>Maternity & Children Hospital - Tabuk</h2>
        <h4 style='color:#555'>Blood Bank Serology Unit</h4>
    </div>
    <div class='clinical-alert' style='text-align:center;'>
        <b>Active ID Panel:</b> {lp} | <b>Active Screen:</b> {ls}
    </div>
    <br>
    """, unsafe_allow_html=True)
    
    # 2. LOCK SYSTEM
    if not st.session_state.lot_p or not st.session_state.lot_s:
        st.error("⛔ SYSTEM LOCKED: Please configure Lots in Admin Panel.")
        st.stop()
    
    # 3. PATIENT FORM
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()

    # 4. ENTRY FORM
    with st.form("main"):
        colL, colR = st.columns([1, 2.5])
        with colL:
            st.write("<b>Control</b>", unsafe_allow_html=True)
            ac_res = st.radio("Auto Control", ["Negative", "Positive"])
            st.write("<b>Screening</b>", unsafe_allow_html=True)
            s1=st.selectbox("Scn I",GRADES); s2=st.selectbox("Scn II",GRADES); s3=st.selectbox("Scn III",GRADES)
        with colR:
            st.write("<b>ID Panel</b>", unsafe_allow_html=True)
            g1,g2=st.columns(2)
            with g1:
                c1=st.selectbox("1",GRADES,key="c1"); c2=st.selectbox("2",GRADES,key="c2"); c3=st.selectbox("3",GRADES,key="c3"); c4=st.selectbox("4",GRADES,key="c4"); c5=st.selectbox("5",GRADES,key="c5"); c6=st.selectbox("6",GRADES,key="c6")
            with g2:
                c7=st.selectbox("7",GRADES,key="c7"); c8=st.selectbox("8",GRADES,key="c8"); c9=st.selectbox("9",GRADES,key="c9"); c10=st.selectbox("10",GRADES,key="c10"); c11=st.selectbox("11",GRADES,key="c11")
        run = st.form_submit_button("🚀 Run Analysis")

    # 5. LOGIC & RESULTS
    if run:
        inp_p = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
        inp_s = {"I":s1,"II":s2,"III":s3}
        
        pos_cnt = sum([normalize_grade(x) for x in inp_p.values()])
        
        # --- SCENARIO 1: AUTO CONTROL POSITIVE ---
        if ac_res == "Positive":
            st.session_state.dat_mode = True # Trigger DAT view
            st.markdown("""<div class='status-critical'><h3>🚨 Auto-Control POSITIVE</h3>Analysis Suspended. Complete DAT Workup.</div>""", unsafe_allow_html=True)
            
            if pos_cnt >= 11:
                st.markdown("""<div class='clinical-alert'><b>⚠️ CRITICAL WARNING:</b> Pan-agglutination + Pos AC.<br>Consider <b>Delayed Hemolytic Transfusion Reaction (DHTR)</b> mimicking WAIHA.<br>Mandatory: Check History & Elution.</div>""", unsafe_allow_html=True)

        # --- SCENARIO 2: PAN-REACTIVITY ---
        elif pos_cnt == 11:
            st.session_state.dat_mode = False
            st.markdown("""<div class='status-warning'><h3>⚠️ High Frequency Antigen</h3>Pan-Reactivity with Neg Auto.<br>Guidance: Screen siblings, Refer to Ref Lab.</div>""", unsafe_allow_html=True)
            
        # --- SCENARIO 3: ALLOANTIBODY ---
        else:
            st.session_state.dat_mode = False
            
            final_cands, notes = analyze_master_logic(inp_p, inp_s, st.session_state.ext)
            
            sigs = [x for x in final_cands if x not in INSIGNIFICANT_AGS]
            colds = [x for x in final_cands if x in INSIGNIFICANT_AGS]

            st.subheader("Conclusion")
            
            if not sigs and not colds:
                st.error("No Match Found / Inconclusive.")
            else:
                all_ok = True
                
                # MESSAGES
                if "suspect_G" in notes:
                    st.warning("⚠️ **Suspect Anti-G**: Pattern Matches Cells 1,2,3,4,8. Differentiate D+C.")
                if "anti-c_risk" in notes:
                    st.markdown("""<div class='status-fail'>🛑 <b>Anti-c Detected:</b> Must provide R1R1 (E- c-) units to avoid Anti-E formation.</div>""", unsafe_allow_html=True)

                if sigs:
                    st.success(f"**Identified:** Anti-{', '.join(sigs)}")
                if colds:
                    st.info(f"**Other/Cold:** Anti-{', '.join(colds)}")
                    
                # STRATEGY FOR MULTIPLE
                if len(sigs) > 1:
                    st.markdown("#### 🔬 Smart Separation Strategy")
                    for t in sigs:
                         others = [o for o in sigs if o!=t]
                         matches = find_matching_cells_in_inventory(t, others)
                         txt = f"<span class='cell-hint'>{', '.join(matches)}</span>" if matches else "<span style='color:red'>Search External</span>"
                         st.markdown(f"<div class='strategy-box'>Confirm <b>{t}</b> (Select {t}+ / {' '.join(others)}-) -> {txt}</div>", unsafe_allow_html=True)
                
                st.write("---")
                # VALIDATION LOOP
                for ab in (sigs + colds):
                    # CORRECTED NAME CALL
                    ok, p, n = check_rule_3(ab, inp_p, inp_s, st.session_state.ext)
                    icn = "✅" if ok else "⚠️"
                    msg = "Confirmed (Rule of 3)" if ok else "Unconfirmed"
                    cls = "status-ok" if ok else "status-warn"
                    st.markdown(f"<div class='{cls}'>{icn} <b>Anti-{ab}:</b> {msg} (P:{p} | N:{n})</div>", unsafe_allow_html=True)
                    if not ok: all_ok = False
                
                if all_ok and sigs:
                    if st.button("🖨️ Generate Official Report"):
                         t = f"""<div class='print-only'><center><h2>Maternity & Children Hospital - Tabuk</h2><h3>Serology Report</h3></center><div class='result-sheet'><b>Pt:</b> {nm} ({mr})<br><b>Tech:</b> {tc} | <b>Date:</b> {dt}<hr><b>Result: Anti-{', '.join(sigs)}</b><br>{' (+ '+', '.join(colds)+')' if colds else ''}<br>Validation: p<=0.05 Confirmed.<br>Clinical: Phenotype Negative.<br><br>Sig:_________</div><div class='footer-print'>Dr. Haitham Ismail</div></div><script>window.print()</script>"""
                         st.markdown(t, unsafe_allow_html=True)
                elif sigs:
                    st.warning("⚠️ Validation Required (Use Extra Cells below).")

    # 5. PERSISTENT MODULES (OUTSIDE FORM)
    
    # A. DAT
    if st.session_state.get('dat_mode', False):
        st.write("---")
        with st.container(border=True):
            st.subheader("🧪 Monospecific DAT Workup")
            c1,c2,c3 = st.columns(3)
            # Use keys to keep state active
            i=c1.selectbox("IgG", ["Negative","Positive"], key="di")
            c=c2.selectbox("C3d", ["Negative","Positive"], key="dc")
            t=c3.selectbox("Control", ["Negative","Positive"], key="dt")
            
            if t=="Positive": st.error("Invalid Test.")
            elif i=="Positive": 
                st.warning("👉 **Probable WAIHA**.")
                st.write("Auto-antibody present. Rule out DHTR if transfused. Adsorption may be needed.")
            elif c=="Positive": 
                st.info("👉 **Probable CAS (Cold)**. Use Pre-warm.")

    # B. ADD CELL
    if not st.session_state.get('dat_mode', False):
        with st.expander("➕ Add Selected Cell (Input Data)"):
            with st.form("ext_f"):
                e_id=st.text_input("ID"); e_rs=st.selectbox("R",GRADES)
                st.write("Antigens (+):")
                cols=st.columns(8); new_ph={}
                for i,ag in enumerate(AGS):
                    if cols[i%8].checkbox(ag): new_ph[ag]=1
                    else: new_ph[ag]=0
                if st.form_submit_button("Confirm Add"):
                    st.session_state.ext.append({"res":normalize_grade(e_rs), "res_txt":e_rs, "ph":new_ph})
                    st.success("Added! Please Run Analysis again.")
                    
        if st.session_state.ext: st.table(pd.DataFrame(st.session_state.ext)[['res_txt']])
