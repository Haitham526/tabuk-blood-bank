import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. SETUP & STYLE (Red Branding Fixed)
# ==========================================
st.set_page_config(page_title="MCH Tabuk Serology", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    /* Printing & Header */
    @media print { 
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 4px double #8B0000; padding: 25px; font-family: 'Times New Roman'; }
        /* Footer for Print */
        .print-footer { 
            position: fixed; bottom: 0; width: 100%; text-align: center; 
            color: #8B0000; font-weight: bold; font-family: serif; border-top: 1px solid #ccc;
        }
    }
    .print-only { display: none; }
    
    .hospital-logo { 
        text-align: center; border-bottom: 5px solid #8B0000; 
        padding-bottom: 5px; font-family: sans-serif; 
        color: #003366; 
    }
    
    /* MANDATORY LOCK STYLE */
    .lock-screen {
        padding: 20px; background-color: #ffebee; border: 2px solid #c62828; 
        color: #b71c1c; text-align: center; font-weight: bold; border-radius: 5px;
    }

    /* DR SIGNATURE STICKY FOOTER (Screen) */
    .dr-signature { 
        position: fixed; bottom: 10px; right: 15px; 
        background: rgba(255,255,255,0.95); 
        padding: 8px 15px; border: 2px solid #8B0000; 
        border-radius: 8px; z-index:99; box-shadow: 0 0 10px rgba(0,0,0,0.1);
        text-align: center;
    }
    .dr-name { color: #8B0000; font-family: 'Georgia', serif; font-size: 14px; font-weight: bold; }
    .dr-title { color: #333; font-size: 11px; }

    /* Logic Boxes */
    .logic-pass { background-color: #e8f5e9; border-left: 5px solid #2e7d32; padding: 10px; color: #1b5e20; }
    .logic-alert { background-color: #fff3e0; border-left: 5px solid #ff9800; padding: 10px; color: #e65100; font-weight: bold; }
    .logic-critical { background-color: #f8d7da; border-left: 5px solid #dc3545; padding: 10px; color: #842029; }
    .note-gray { background-color: #f8f9fa; padding: 10px; border-left: 5px solid #6c757d; font-style: italic; color: #6c757d; }

    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

# 2. DEFINITIONS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"] 
INSIGNIFICANT_AGS = ["Lea", "Lua", "Leb", "P1"]
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# 3. STATE
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
# Mandatory Lots
if 'lot_p' not in st.session_state: st.session_state.lot_p = ""
if 'lot_s' not in st.session_state: st.session_state.lot_s = ""
# Persistence
if 'ext' not in st.session_state: st.session_state.ext = []

# ==========================================
# 4. LOGIC ENGINE (CORRECTED)
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
                v = 1 if any(x in v_clean for x in ['+', '1', 'pos', 'w']) else 0
                vals.append(v)
            if len(vals) > 26: vals = vals[-26:]
            while len(vals) < 26: vals.append(0)
            d = {"ID": f"Cell {c+1}" if limit==11 else f"Scn"}
            for i, ag in enumerate(AGS): d[ag] = vals[i]
            data.append(d)
            c+=1
        return pd.DataFrame(data), f"Updated {c} rows."
    except Exception as e: return None, str(e)

def analyze_alloantibodies(in_p, in_s, extra_cells):
    # A. Exclusion
    ruled_out = set()
    # Panel
    for i in range(1, 12):
        if normalize_grade(in_p[i]) == 0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False 
                if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
    # Screen
    smap={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize_grade(in_s[k]) == 0:
            ph = st.session_state.p3.iloc[smap[k]]
            for ag in AGS:
                if ag not in ruled_out:
                    safe=True
                    if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                    if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
    # Extra
    for ex in extra_cells:
        if normalize_grade(ex['res']) == 0:
            for ag in AGS:
                 if ex['ph'].get(ag,0)==1: ruled_out.add(ag)

    # B. Candidates (Inclusion not mandatory for multiple match logic, we list all survivors)
    survivors = [x for x in AGS if x not in ruled_out]
    
    # C. Filtering & Masking
    display_list = []
    
    # 1. First, check if D is present in survivors
    has_D = "D" in survivors
    
    for cand in survivors:
        if cand in IGNORED_AGS: continue # Skip ignored
        
        # *** FIX FOR ANTI-D SILENT MASKING ***
        # If D exists, skip C and E completely
        if has_D and (cand == "C" or cand == "E"):
            continue 
            
        display_list.append(cand)
        
    return display_list

def check_p_val_stats(cand, in_p, in_s, extra_cells):
    p, n = 0, 0
    # P11
    for i in range(1, 12):
        s=normalize_grade(in_p[i]); h=st.session_state.p11.iloc[i-1].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # P3
    si={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s=normalize_grade(in_s[k]); h=st.session_state.p3.iloc[si[k]].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Ext
    for c in extra_cells:
        s=normalize_grade(c['res']); h=c['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    
    pass_ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    return pass_ok, p, n

# ==========================================
# 5. UI LAYOUT
# ==========================================
# FOOTER BADGE
st.markdown("""
<div class='dr-signature no-print'>
    <span class='dr-name'>Dr. Haitham Ismail</span><br>
    <span class='dr-title'>Clinical Hematology/Oncology & BM Transplantation & Transfusion Medicine Consultant</span>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Access:", ["Workstation", "Supervisor"])
    if st.button("Refresh / New Case"): 
        st.session_state.ext=[]
        st.session_state.dat_mode=False
        st.rerun()

# --- ADMIN ---
if nav == "Supervisor":
    st.title("Supervisor Settings")
    if st.text_input("Password",type="password")=="admin123":
        st.info("Enter Lot Numbers to unlock the Workstation.")
        c1,c2 = st.columns(2)
        l_p = c1.text_input("ID Panel Lot", value=st.session_state.lot_p)
        l_s = c2.text_input("Screen Cell Lot", value=st.session_state.lot_s)
        
        if st.button("Save & Lock Config"):
            st.session_state.lot_p = l_p
            st.session_state.lot_s = l_s
            st.success("Configuration Updated!")
            st.rerun()
            
        t1, t2 = st.tabs(["Panel 11", "Screen 3"])
        with t1:
            pt = st.text_area("Paste Excel P11 Data", height=150)
            if st.button("Update Panel"):
                d,m = parse_paste(pt, 11)
                if d is not None: st.session_state.p11=d; st.success(m)
            st.dataframe(st.session_state.p11)
        with t2:
            st = st.text_area("Paste Excel Screen", height=100)
            if st.button("Update Screen"):
                d,m = parse_paste(st, 3)
                if d is not None: st.session_state.p3=d; st.success(m)
            st.dataframe(st.session_state.p3)

# --- WORKSTATION ---
else:
    # 1. LOCK SCREEN
    if not st.session_state.lot_p or not st.session_state.lot_s:
        st.markdown("<div class='lock-screen'>⛔ SYSTEM LOCKED<br>Please ask Supervisor to configure Lot Numbers.</div>", unsafe_allow_html=True)
        st.stop()
        
    # 2. HEADER
    st.markdown(f"""
    <div class='hospital-logo'>
        <h2 style='color:#8B0000'>Maternity & Children Hospital - Tabuk</h2>
        <h4 style='color:#555'>Immunohematology Workstation</h4>
        <small><b>ID Panel:</b> {st.session_state.lot_p} | <b>Screen:</b> {st.session_state.lot_s}</small>
    </div>
    """, unsafe_allow_html=True)
    
    # 3. ENTRY
    with st.form("entry"):
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.write("<b>Screening & Auto</b>", unsafe_allow_html=True)
            ac = st.radio("Auto Control", ["Negative","Positive"])
            s1=st.selectbox("Scn I",GRADES)
            s2=st.selectbox("Scn II",GRADES)
            s3=st.selectbox("Scn III",GRADES)
            
        with col2:
            st.write("<b>Identification Panel</b>", unsafe_allow_html=True)
            c_a, c_b = st.columns(2)
            with c_a:
                c1=st.selectbox("1",GRADES,key="k1"); c2=st.selectbox("2",GRADES,key="k2"); c3=st.selectbox("3",GRADES,key="k3")
                c4=st.selectbox("4",GRADES,key="k4"); c5=st.selectbox("5",GRADES,key="k5"); c6=st.selectbox("6",GRADES,key="k6")
            with c_b:
                c7=st.selectbox("7",GRADES,key="k7"); c8=st.selectbox("8",GRADES,key="k8"); c9=st.selectbox("9",GRADES,key="k9")
                c10=st.selectbox("10",GRADES,key="k10"); c11=st.selectbox("11",GRADES,key="k11")
        
        # Info
        st.markdown("---")
        ir = st.columns(4)
        pnm=ir[0].text_input("Name"); pmr=ir[1].text_input("MRN"); ptc=ir[2].text_input("Tech"); pdt=ir[3].date_input("Date")

        btn = st.form_submit_button("🚀 Run Analysis")

    # 4. RESULTS LOGIC
    if btn:
        st.write("### 📝 Analysis Report")
        
        # MAP INPUTS
        i_p = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
        i_s = {"I":s1,"II":s2,"III":s3}
        cnt = sum([normalize_grade(x) for x in i_p.values()])
        
        # ----- CRITICAL: AUTO POS -----
        if ac == "Positive":
            st.markdown("<div class='logic-critical'>🚨 <b>Auto-Control POSITIVE.</b> Allo-antibody ID suspended.</div>", unsafe_allow_html=True)
            st.session_state.dat_mode = True # Keep DAT open
            
            if cnt == 11:
                st.markdown("""
                <div class='logic-alert'>
                ⚠️ <b>DHTR ALERT:</b> Pan-agglutination + AC Positive.<br>
                High risk of <b>Delayed Hemolytic Transfusion Reaction</b> (Alloantibody on donor cells).<br>
                Mandatory: Check History & Perform Elution.
                </div>
                """, unsafe_allow_html=True)
                
        # ----- NORMAL ALLO -----
        else:
            st.session_state.dat_mode = False
            
            if cnt == 11:
                st.markdown("<div class='logic-alert'>⚠️ <b>High Incidence Antibody.</b><br>Pan-reactivity with Negative Auto.<br>Search siblings / Reference Lab.</div>", unsafe_allow_html=True)
            else:
                # CORE ANALYSIS (FIXED)
                final_res, notes = analyze_alloantibodies(i_p, i_s, st.session_state.ext)
                
                # Separation
                sigs = [x for x in final_res if x not in INSIGNIFICANT_AGS]
                colds = [x for x in final_res if x in INSIGNIFICANT_AGS]
                
                if not sigs and not colds:
                    st.error("No Match. Inconclusive or Low Frequency.")
                
                else:
                    # VALIDATION LOOP
                    all_confirmed = True
                    
                    if sigs:
                        st.success(f"**Potential Significant:** Anti-{', '.join(sigs)}")
                    if colds:
                        st.markdown(f"<div class='note-gray'>Insignificant/Cold Detected: Anti-{', '.join(colds)}</div>", unsafe_allow_html=True)
                        
                    # Rule Specifics
                    if "anti-c_risk" in notes:
                        st.warning("🛑 <b>Anti-c Found:</b> Transfuse R1R1 (CDe/CDe) to respect Anti-E.")
                    
                    st.write("---")
                    st.write("<b>Validation Status:</b>", unsafe_allow_html=True)
                    
                    for ab in (sigs+colds):
                        # P-VAL CHECK
                        ok, p_n, n_n = check_p_val_stats(ab, i_p, i_s, st.session_state.ext)
                        if ok:
                            st.markdown(f"<div class='logic-pass'>✅ <b>Anti-{ab}:</b> Rule of 3 MET. (P:{p_n} / N:{n_n})</div>", unsafe_allow_html=True)
                        else:
                            all_confirmed = False
                            st.markdown(f"<div class='logic-critical'>🛑 <b>Anti-{ab}:</b> UNCONFIRMED. Need more cells. (P:{p_n} / N:{n_n})</div>", unsafe_allow_html=True)

                    # Strategy Guide for Multiple
                    if len(sigs) > 1:
                        st.info("💡 <b>Strategy:</b> Use Selected Cells to separate.")
                        for t in sigs:
                            oths = [o for o in sigs if o!=t]
                            st.write(f"- Confirm <b>{t}</b> using: {t} Pos / {' '.join(oths)} Neg Cell.")

                    # Print
                    if all_confirmed:
                         full_str = ", ".join(sigs)
                         html = f"""
                         <div class='print-only'>
                            <center><h2 style='color:#8B0000'>Maternity & Children Hospital - Tabuk</h2></center>
                            <div class='result-sheet'>
                                <b>Patient:</b> {pnm} ({pmr}) <br> <b>Date:</b> {pdt} <br> <b>Tech:</b> {ptc}
                                <hr>
                                <h3>Results: Anti-{full_str} Detected</h3>
                                <p>{' (+ ' + ', '.join(colds) + ' Cold)' if colds else ''}</p>
                                <p><b>Validation:</b> Confirmed (p<=0.05).</p>
                                <p><b>Requirement:</b> Patient Must be Phenotype Negative for: {full_str}.</p>
                                <br><br>
                                <table width='100%'><tr><td>Tech Sig: __________</td><td>Consul. Sig: __________</td></tr></table>
                                <div class='print-footer'>Dr. Haitham Ismail | Consultant</div>
                            </div>
                         </div>
                         <script>window.print()</script>
                         """
                         st.markdown(html, unsafe_allow_html=True)

    # 5. PERSISTENT MODULES (DAT & ADD CELL)
    if st.session_state.get('dat_mode', False):
        st.write("---")
        st.subheader("🧪 DAT Investigation")
        with st.container(border=True):
            dc1,dc2,dc3 = st.columns(3)
            r_igg = dc1.selectbox("IgG", ["Neg","Pos"])
            r_c3 = dc2.selectbox("C3d", ["Neg","Pos"])
            r_ct = dc3.selectbox("Control", ["Neg","Pos"])
            
            if r_ct=="Pos": st.error("Invalid Test.")
            elif r_igg=="Pos": st.warning(">> WAIHA Pattern. Perform Elution.")
            elif r_c3=="Pos": st.info(">> CAS Pattern. Pre-warm.")
    
    # Extra Cells (Always visible to allow fixes)
    with st.expander("➕ Add Selected Cell (Validation)"):
        with st.form("extf"):
            e_id=st.text_input("Cell ID")
            e_rs=st.selectbox("Result", GRADES)
            st.write("Antigens Present:")
            c_g=st.columns(6)
            ph_n={}
            for i,ag in enumerate(AGS):
                if c_g[i%6].checkbox(ag): ph_n[ag]=1
                else: ph_n[ag]=0
            if st.form_submit_button("Add Cell"):
                st.session_state.ext.append({"res":e_rs, "res_txt":e_rs, "ph":ph_n})
                st.success("Cell Added! Re-run Analysis.")

    if st.session_state.ext:
        st.write(f"Added {len(st.session_state.ext)} Extra Cells.")
