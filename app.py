import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. إعدادات الصفحة والهوية
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology Expert", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    /* Printing & Header */
    @media print { 
        .stApp > header, .sidebar, footer, .no-print { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 4px double #8B0000; padding: 25px; font-family: 'Times New Roman'; }
        .page-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; }
    }
    .print-only { display: none; }
    
    .hospital-logo { text-align: center; border-bottom: 5px solid #8B0000; padding-bottom: 5px; color: #003366; font-family: sans-serif; font-weight: bold;}
    
    /* Logic Alerts & Boxes */
    .status-confirmed { background-color: #d1e7dd; padding: 12px; border-radius: 5px; border-left: 6px solid #198754; color: #0f5132; margin-bottom: 5px;}
    .status-warning { background-color: #fff3cd; padding: 12px; border-radius: 5px; border-left: 6px solid #ffc107; color: #856404; margin-bottom: 5px;}
    .status-critical { background-color: #f8d7da; padding: 12px; border-radius: 5px; border-left: 6px solid #dc3545; color: #842029; font-weight: bold;}
    .status-cold { background-color: #e2e3e5; padding: 10px; border-left: 6px solid #6c757d; color: #383d41; font-style: italic;}
    
    .strategy-box { border: 1px dashed #0d6efd; background-color: #cfe2ff; padding: 10px; border-radius: 4px; color: #084298; margin-top: 5px;}
    
    .dr-signature { position: fixed; bottom: 10px; right: 15px; background: rgba(255,255,255,0.95); padding: 5px 10px; border: 1px solid #8B0000; border-radius: 5px; z-index:99; text-align:center; box-shadow: 2px 2px 5px rgba(0,0,0,0.1); }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class='dr-signature no-print'>
    <span style='color:#8B0000; font-weight:bold'>Dr. Haitham Ismail</span><br>
    <span style='font-size:11px'>Clinical Hematology/Oncology &<br>BM Transplantation & Transfusion Medicine Consultant</span>
</div>
""", unsafe_allow_html=True)

# Definitions
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

IGNORED = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
# NOTE: Removed M from here, kept Lea/Lua/P1/Leb
INSIGNIFICANT = ["Lea", "Leb", "Lua", "P1"] 
FULL_GRADES = ["Negative", "+1", "+2", "+3", "+4", "Hemolysis"]

# 2. STATE
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'lot_p' not in st.session_state: st.session_state.lot_p = ""
if 'lot_s' not in st.session_state: st.session_state.lot_s = ""
if 'ext' not in st.session_state: st.session_state.ext = []

# ==========================================
# 3. LOGIC & INTELLIGENCE
# ==========================================
def normalize(val):
    s = str(val).lower().strip()
    # Anything other than "negative" or "0" is Positive
    if s in ["negative", "neg", "0"]: return 0
    return 1

def parse_text(txt, limit):
    # Safe Paste Parser
    try:
        rows = txt.strip().split('\n')
        data = []
        c=0
        for line in rows:
            if c>=limit: break
            parts = line.split('\t')
            vals = []
            for p in parts:
                v_clean = str(p).lower().strip()
                v = 1 if any(x in v_clean for x in ['+','1','pos','w']) else 0
                vals.append(v)
            if len(vals)>26: vals=vals[-26:]
            while len(vals)<26: vals.append(0)
            d={"ID": f"C{c+1}" if limit==11 else f"Scn"}
            for i,ag in enumerate(AGS): d[ag]=vals[i]
            data.append(d)
            c+=1
        return pd.DataFrame(data), f"Successfully mapped {c} rows."
    except Exception as e: return None, str(e)

# Smart Suggestions (Look in Inventory)
def find_stock_cell(target, avoid_list):
    # Scan Panel
    matches = []
    for i in range(11):
        c = st.session_state.p11.iloc[i]
        if c.get(target,0)==1:
            safe = True
            for bad in avoid_list:
                if c.get(bad,0)==1: safe=False; break
            if safe: matches.append(f"Panel #{i+1}")
    # Scan Screen
    lbls=["I","II","III"]
    for i, s in enumerate(lbls):
        c = st.session_state.p3.iloc[i]
        if c.get(target,0)==1:
            safe = True
            for bad in avoid_list:
                if c.get(bad,0)==1: safe=False; break
            if safe: matches.append(f"Screen {s}")
    return matches

def calculate_expert(p_in, s_in, extra_list):
    # 1. EXCLUSION
    ruled = set()
    # Panel
    for i in range(1,12):
        if normalize(p_in[i])==0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False # Hetero
                if ph.get(ag,0)==1 and safe: ruled.add(ag)
    # Screen
    s_idx={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize(s_in[k])==0:
            ph = st.session_state.p3.iloc[s_idx[k]]
            for ag in AGS:
                if ag not in ruled:
                    safe=True
                    if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                    if ph.get(ag,0)==1 and safe: ruled.add(ag)
    # Extra
    for x in extra_list:
        if normalize(x['res'])==0:
            for ag in AGS:
                if x['ph'].get(ag,0)==1: ruled.add(ag)
                
    # 2. CANDIDATES & RANKING (Correct Logic: Score = Hits - Misses)
    candidates = [x for x in AGS if x not in ruled]
    display = [x for x in candidates if x not in IGNORED]
    
    scored = []
    for cand in display:
        hits = 0
        misses = 0
        # Scan Panel hits
        for i in range(1,12):
            is_pt_pos = normalize(p_in[i])
            is_ag_pos = st.session_state.p11.iloc[i-1].get(cand,0)
            if is_pt_pos and is_ag_pos: hits+=1
            if is_pt_pos and not is_ag_pos: misses+=1 # Penalty!
        # Scan Screen hits
        for k in ["I","II","III"]:
            is_pt_pos = normalize(s_in[k])
            is_ag_pos = st.session_state.p3.iloc[s_idx[k]].get(cand,0)
            if is_pt_pos and is_ag_pos: hits+=1
            if is_pt_pos and not is_ag_pos: misses+=1
            
        score = hits - (misses * 2) # Weighted penalty
        scored.append({"Ab": cand, "Score": score, "Hits": hits, "Misses": misses})
    
    # Sort DESC
    scored.sort(key=lambda x: x['Score'], reverse=True)
    
    return scored, ruled

def check_prob(cand, p_in, s_in, ex):
    p, n = 0, 0
    # Panel
    for i in range(1,12):
        s=normalize(p_in[i]); h=st.session_state.p11.iloc[i-1].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    sid={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s=normalize(s_in[k]); h=st.session_state.p3.iloc[sid[k]].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Ex
    for c in ex:
        s=normalize(c['res']); h=c['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    ok=(p>=3 and n>=3) or (p>=2 and n>=3)
    return ok, p, n

# ==========================================
# 4. INTERFACE
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png",width=60)
    nav=st.radio("System Access",["Workstation","Supervisor"])
    if st.button("RESET DATA"): 
        st.session_state.ext=[]; st.session_state.dat_open=False; st.rerun()

# ------- ADMIN --------
if nav == "Supervisor":
    st.title("Admin Configuration")
    if st.text_input("Password",type="password")=="admin123":
        c1,c2=st.columns(2)
        lp = c1.text_input("ID Panel Lot", value=st.session_state.lot_p)
        ls = c2.text_input("Screen Lot", value=st.session_state.lot_s)
        if st.button("Save & Lock"):
            st.session_state.lot_p=lp; st.session_state.lot_s=ls; st.success("Updated!"); st.rerun()
        
        t1,t2=st.tabs(["Panel 11","Screen"])
        with t1:
            tp=st.text_area("Paste Data (P11)", height=150)
            if st.button("Update P11"):
                d,m=parse_paste(tp,11)
                if d is not None: st.session_state.p11=d; st.success(m)
            st.dataframe(st.session_state.p11)
        with t2:
            ts=st.text_area("Paste Data (S3)", height=100)
            if st.button("Update S3"):
                d,m=parse_paste(ts,3)
                if d is not None: st.session_state.p3=d; st.success(m)
            st.dataframe(st.session_state.p3)

# ------- WORKSTATION --------
else:
    # 1. HEADER & LOCK
    if not st.session_state.lot_p or not st.session_state.lot_s:
        st.markdown("<div class='status-critical'>⛔ SYSTEM LOCKED: Lot Numbers not configured.</div>", unsafe_allow_html=True)
        st.stop()
        
    st.markdown(f"""
    <div class='hospital-logo'>
        <h2>Maternity & Children Hospital - Tabuk</h2>
        <h4 style='color:#555'>Blood Bank & Serology Unit</h4>
        <small style='color:darkred;font-weight:bold;border:1px solid #ddd;padding:3px'>ID Panel: {st.session_state.lot_p} | Screen: {st.session_state.lot_s}</small>
    </div>
    """, unsafe_allow_html=True)
    
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Pt Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    # 2. FORM (STABLE INPUT)
    with st.form("entry_form"):
        colL, colR = st.columns([1, 2.5])
        
        with colL:
            st.write("<b>Controls</b>", unsafe_allow_html=True)
            ac = st.radio("Auto Control (AC)", ["Negative","Positive"])
            st.write("<b>Screening</b>", unsafe_allow_html=True)
            s1=st.selectbox("Scn I",GRADES); s2=st.selectbox("Scn II",GRADES); s3=st.selectbox("Scn III",GRADES)
            
        with colR:
            st.write("<b>Panel (11)</b>", unsafe_allow_html=True)
            g1,g2=st.columns(2)
            with g1:
                c1=st.selectbox("1",GRADES); c2=st.selectbox("2",GRADES); c3=st.selectbox("3",GRADES)
                c4=st.selectbox("4",GRADES); c5=st.selectbox("5",GRADES); c6=st.selectbox("6",GRADES)
            with g2:
                c7=st.selectbox("7",GRADES); c8=st.selectbox("8",GRADES); c9=st.selectbox("9",GRADES)
                c10=st.selectbox("10",GRADES); c11=st.selectbox("11",GRADES)
                
        run = st.form_submit_button("🚀 Run Comprehensive Analysis")
        
    # 3. ANALYSIS EXECUTION
    if run:
        # Save AC status for DAT
        st.session_state.dat_open = (ac == "Positive")
        
        inp_p = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
        inp_s = {"I":s1,"II":s2,"III":s3}
        pos_cnt = sum([normalize(x) for x in inp_p.values()])
        
        # --- LOGIC PATH A: AUTO CONTROL POSITIVE ---
        if ac == "Positive":
            st.markdown("<div class='status-critical'>🚨 Auto-Control POSITIVE</div>", unsafe_allow_html=True)
            
            if pos_cnt == 11:
                st.markdown("""<div class='clinical-waiha'><b>⚠️ Critical Warning:</b> Pan-agglutination + Positive AC.<br>
                High Risk of <b>DHTR (Delayed Hemolytic Transfusion Reaction)</b> if recently transfused.<br>
                <b>Elution is MANDATORY.</b> Don't assume WAIHA only.</div>""", unsafe_allow_html=True)
            
            # Note: DAT table is shown below

        # --- LOGIC PATH B: PAN REACTIVITY ---
        elif pos_cnt == 11:
             st.markdown("""<div class='clinical-alert'>⚠️ <b>High Frequency Antigen Suspected</b><br>All Cells Positive + AC Negative.<br>Protocol: Phenotype patient (must be Neg), Screen Siblings, Refer Sample.</div>""", unsafe_allow_html=True)
             st.session_state.dat_open = False
             
        # --- LOGIC PATH C: ALLOANTIBODY ---
        else:
            st.session_state.dat_open = False
            ranked_list, ruled = calculate_expert(inp_p, inp_s, st.session_state.ext)
            
            # --- MASKING LOGIC FOR D, G, C, E ---
            # 1. Anti-G check: Pos on 1,2,3,4,8? (Usually D+C cells)
            is_G_suspect = all(normalize(inp_p[k])==1 for k in [1,2,3,4,8])
            
            # 2. Filter D Masking
            final_display = []
            is_D_top = False
            
            # Check if D is the best match
            if ranked_list and ranked_list[0]['Ab'] == "D" and ranked_list[0]['Score']>0:
                is_D_top = True
                
            for item in ranked_list:
                ab = item['Ab']
                if item['Score'] <= 0: continue # Hide mismatches
                
                # Silent mask for C and E if D is confirmed
                if is_D_top and (ab=="C" or ab=="E") and not is_G_suspect:
                    continue 
                
                final_display.append(ab)
                
            # RESULTS
            if not final_display:
                st.error("No clear match found. All excluded or pattern mismatch.")
            else:
                real = [x for x in final_display if x not in INSIGNIFICANT_AGS]
                cold = [x for x in final_display if x in INSIGNIFICANT_AGS]
                
                # --- REPORT HEADER ---
                if real:
                    # Most Probable
                    if len(real) == 1:
                         st.success(f"✅ **Most Probable Identity:** Anti-{real[0]}")
                    else:
                         st.warning(f"⚠️ **Multiple Antibodies / Mixture:** Anti-{', '.join(real)}")
                         
                if cold:
                    st.info(f"❄️ Cold/Insignificant Detected: Anti-{', '.join(cold)}")
                
                # ALERTS
                if is_G_suspect and is_D_top and "C" in final_display:
                     st.warning("⚠️ **Note:** Pattern matches Anti-D+C or Anti-G. Perform Adsorption/Elution to differentiate.")
                
                if "c" in final_display:
                     st.markdown("<div class='clinical-alert'>🛑 <b>Anti-c Detected.</b> Anti-E is hard to exclude. Transfuse <b>R1R1</b> (E- c-) Units.</div>", unsafe_allow_html=True)

                st.write("---")
                
                # --- VALIDATION STATS ---
                all_confirmed = True
                valid_list = []
                for ab in (real+cold):
                    ok, p, n = check_prob(ab, inp_p, inp_s, st.session_state.ext)
                    txt = "Confirmed" if ok else "Unconfirmed"
                    ico = "✅" if ok else "🛑"
                    cls = "status-confirmed" if ok else "status-rejected"
                    st.markdown(f"<div class='{cls}'>{ico} <b>Anti-{ab}:</b> {txt} (Pos:{p} / Neg:{n})</div>", unsafe_allow_html=True)
                    if ok: valid_list.append(ab)
                    else: all_confirmed = False

                # --- SEPARATION STRATEGY ---
                if len(real) > 1:
                     st.markdown("#### 🧪 Separation Strategy")
                     for t in real:
                         others = [x for x in real if x!=t]
                         # Check inventory
                         avail = find_stock_cell(t, others)
                         av_tx = f"<span class='cell-hint'>{', '.join(avail)}</span>" if avail else "<span style='color:#c00'>Search External</span>"
                         st.markdown(f"<div class='strategy-box'>To Confirm <b>{t}</b>: Use Cell ({t}+ / {' '.join([o+'-' for o in others])}) - {av_tx}</div>", unsafe_allow_html=True)
                
                # --- PRINTING ---
                if all_confirmed and valid_list:
                    if st.button("🖨️ Generate Official Report"):
                         full_txt = ", ".join(real)
                         h=f"""
                         <div class='print-only'>
                            <center><h2 style='color:#800'>Maternity & Children Hospital - Tabuk</h2><h3>Serology Report</h3></center>
                            <div class='result-sheet'>
                                <b>Patient:</b> {nm} ({mr})<br><b>Tech:</b> {tc} | <b>Date:</b> {dt}
                                <hr>
                                <h4>Interpretation: Anti-{full_txt}</h4>
                                <small>Secondary/Cold: {', '.join(cold)}</small>
                                <p><b>Validation:</b> Statistical probability (p<=0.05) confirmed.</p>
                                <p><b>Recommendation:</b> Give Antigen Negative blood.</p>
                                <div style='margin-top:40px'><b>Signature:</b> ____________________</div>
                            </div>
                            <div style='position:fixed;bottom:0;text-align:center;width:100%'>Dr. Haitham Ismail | Consultant</div>
                         </div>
                         <script>window.print()</script>
                         """
                         st.markdown(h, unsafe_allow_html=True)
                else:
                    if not all_confirmed: st.warning("⚠️ Rules Not Met. Please add extra cells below.")
    
    # 5. DAT INTERACTIVE SECTION
    if st.session_state.get('dat_open', False):
        st.write("---")
        st.subheader("🧪 Monospecific DAT Entry")
        # Variables here for display, Logic is purely visual guide based on selection
        d_cont = st.container(border=True)
        colA, colB, colC = d_cont.columns(3)
        dig = colA.selectbox("Anti-IgG", ["Negative", "Positive"])
        dc3 = colB.selectbox("Anti-C3d", ["Negative", "Positive"])
        dct = colC.selectbox("Control", ["Negative", "Positive"])
        
        if dct == "Positive":
             st.error("Invalid DAT.")
        elif dig=="Positive":
             st.warning("👉 <b>Probable WAIHA / DHTR</b> (Perform Elution).")
        elif dc3=="Positive":
             st.info("👉 <b>Probable CAS</b> (Pre-warm).")
             
    # 6. ADD CELL MODULE
    if not st.session_state.get('dat_open', False):
        with st.expander("➕ Add Selected Cells (To fix Logic)"):
            cx1,cx2=st.columns(2)
            id_n=cx1.text_input("Lot#")
            res_n=cx2.selectbox("Result", GRADES)
            st.write("Select Positive Antigens on this cell:")
            cols=st.columns(8)
            new_ph = {a:0 for a in AGS}
            for i,ag in enumerate(AGS):
                if cols[i%8].checkbox(ag): new_ph[ag]=1
            if st.button("Add Cell"):
                st.session_state.ext.append({"res":normalize(res_n),"res_txt":res_n,"ph":new_ph})
                st.success("Added! Run Analysis Again."); st.rerun()

    if st.session_state.ext: st.table(pd.DataFrame(st.session_state.ext)[['res_txt']])
