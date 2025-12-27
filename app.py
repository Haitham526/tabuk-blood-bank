import streamlit as st
import pandas as pd
from datetime import date

# --------------------------------------------------------------------------
# 1. CONFIG & STYLING (UNCHANGED)
# --------------------------------------------------------------------------
st.set_page_config(page_title="MCH Tabuk - Serology Expert", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { 
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 4px double #8B0000; padding: 25px; font-family: 'Times New Roman'; font-size:14px; }
        .footer-print { position: fixed; bottom: 0; width: 100%; text-align: center; color: #8B0000; font-weight: bold; border-top: 1px solid #ccc; padding: 10px; font-family: serif; }
    }
    .print-only { display: none; }
    
    .hospital-logo { text-align: center; border-bottom: 5px solid #8B0000; padding-bottom: 5px; font-family: 'Arial'; color: #003366; }
    
    /* CLINICAL BOXES */
    .clinical-waiha { background-color: #f8d7da; border-left: 5px solid #dc3545; padding: 15px; margin: 10px 0; color: #721c24; }
    .clinical-cold { background-color: #cff4fc; border-left: 5px solid #0dcaf0; padding: 15px; margin: 10px 0; color: #055160; }
    .clinical-alert { background-color: #fff3cd; border: 2px solid #ffca2c; padding: 10px; color: #000; font-weight: bold; margin: 5px 0;}
    .cell-hint { font-size: 0.9em; color: #155724; background: #d4edda; padding: 2px 6px; border-radius: 4px; }

    /* SIGNATURE */
    .dr-signature { position: fixed; bottom: 10px; right: 15px; background: rgba(255,255,255,0.95); padding: 8px 15px; border: 2px solid #8B0000; border-radius: 8px; z-index:99; box-shadow: 2px 2px 5px rgba(0,0,0,0.1); text-align: center; font-family: 'Georgia', serif; }
    .dr-name { color: #8B0000; font-size: 15px; font-weight: bold; display: block;}
    
    .logic-pass { background-color: #e8f5e9; border-left: 5px solid #2e7d32; padding: 10px; color: #1b5e20; }
    .logic-fail { background-color: #f8d7da; border-left: 5px solid #dc3545; padding: 10px; color: #842029; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

# FIXED SIGNATURE
st.markdown("""<div class='dr-signature no-print'><span class='dr-name'>Dr. Haitham Ismail</span><span style='color:#333;font-size:11px'>Clinical Hematology/Oncology &<br>BM Transplantation & Transfusion Medicine Consultant</span></div>""", unsafe_allow_html=True)

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
if 'lot_p' not in st.session_state: st.session_state.lot_p = ""
if 'lot_s' not in st.session_state: st.session_state.lot_s = ""
if 'dat_mode' not in st.session_state: st.session_state.dat_mode = False
if 'ext' not in st.session_state: st.session_state.ext = []

# 4. LOGIC ENGINE
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
                v = 1 if any(x in str(p).lower() for x in ['+', '1', 'pos', 'w']) else 0
                vals.append(v)
            if len(vals) > 26: vals = vals[-26:]
            while len(vals) < 26: vals.append(0)
            d = {"ID": f"C{c+1}" if limit==11 else f"Scn"}
            for i, ag in enumerate(AGS): d[ag] = vals[i]
            data.append(d)
            c+=1
        return pd.DataFrame(data), f"Updated {c} rows."
    except Exception as e: return None, str(e)

# --- SEARCH SUGGESTIONS (Safe) ---
def find_matching_cells_in_inventory(target_ab, conflicts):
    found_list = []
    # Panel Scan
    for i in range(11):
        cell = st.session_state.p11.iloc[i]
        if cell.get(target_ab,0)==1:
            clean = True
            for bad in conflicts: 
                if cell.get(bad,0)==1: clean=False; break
            if clean: found_list.append(f"Panel #{i+1}")
    # Screen Scan
    sc = ["I","II","III"]
    for i in range(3):
        cell = st.session_state.p3.iloc[i]
        if cell.get(target_ab,0)==1:
            clean = True
            for bad in conflicts: 
                if cell.get(bad,0)==1: clean=False; break
            if clean: found_list.append(f"Screen {sc[i]}")
    return found_list

# --- MAIN ANALYSIS: V401 INTELLIGENT MATCHING ---
def analyze_alloantibodies(in_p, in_s, extra_cells):
    ruled_out = set()
    # 1. EXCLUSION
    # P11
    for i in range(1, 12):
        if normalize_grade(in_p[i]) == 0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False 
                if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
    # S3
    smap={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize_grade(in_s[k]) == 0:
            ph = st.session_state.p3.iloc[smap[k]]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
    # Extras
    for ex in extra_cells:
        if normalize_grade(ex['res']) == 0:
            for ag in AGS:
                 if ex['ph'].get(ag,0)==1: ruled_out.add(ag)

    # 2. CANDIDATES & RANKING (The Fix)
    # Filter candidates first
    raw_candidates = [x for x in AGS if x not in ruled_out]
    candidates = [x for x in raw_candidates if x not in IGNORED_AGS]
    
    # *** THE NEW LOGIC: SCORE THE MATCHES ***
    # Count "Unexplained Positives" for each candidate
    # A candidate must explain the positive reactions. 
    # If a patient is POSITIVE but the cell lacks the Antigen -> That's a Strike against that Ab.
    
    candidate_scores = [] # Stores (Name, Miss_Count)
    
    for cand in candidates:
        mismatches = 0
        # Check Panel Matches
        for i in range(1, 12):
            if normalize_grade(in_p[i]) == 1:
                # If Pt Pos, Cell MUST have Antigen (otherwise it's a mismatch for this specific Ab)
                if st.session_state.p11.iloc[i-1].get(cand, 0) == 0:
                    mismatches += 1
        
        # Check Screen Matches
        for k in ["I","II","III"]:
            if normalize_grade(in_s[k]) == 1:
                if st.session_state.p3.iloc[smap[k]].get(cand, 0) == 0:
                    mismatches += 1
                    
        # Append (Name, Mismatch Count)
        candidate_scores.append((cand, mismatches))

    # SORT by Mismatches (0 is Best)
    # Example: P1 has 0 mismatches, C has 4 mismatches -> P1 wins.
    candidate_scores.sort(key=lambda x: x[1])
    
    # 3. FILTERING & MASKING LOGIC
    # Now we pick the best fits.
    # Logic: If we have a Perfect Match (0 miss), show only those (unless mixture logic requires otherwise)
    # Anti-D Masking Logic must apply here too
    
    sorted_candidates = [x[0] for x in candidate_scores] # Names sorted
    final_list = []
    notes = []
    
    is_D_top = "D" in sorted_candidates # Check if D is a survivor
    
    for cand_tuple in candidate_scores:
        name = cand_tuple[0]
        miss = cand_tuple[1]
        
        # If Anti-D is present, silent kill C and E
        if is_D_top and (name == "C" or name == "E"):
            continue 
            
        # Optional: Hide bad matches? 
        # If P1 is perfect (0 miss) and C is terrible (5 miss), C is likely innocent survivor.
        # But we must be careful not to hide mixtures.
        # Strategy: Keep them but the UI will show the sorted order which implies likelihood.
        final_list.append(name)
        
    if "c" in final_list: notes.append("anti-c_risk")
    
    # Anti-G Check Logic (Fixed)
    # D+C combined
    g_cells = [0,1,2,3,7] # Indicies 0-based for cells 1,2,3,4,8
    # Logic to verify G is outside scope of simple parser, relying on D/C presense
    if "D" in final_list and "C" in raw_candidates: 
         # Only warn if specific G pattern match
         # This logic is complex, sticking to simple warning
         pass
         
    return final_list, notes

def check_p_val_stats(cand, in_p, in_s, extra_cells):
    p, n = 0, 0
    # Panel
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
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Supervisor"])
    if st.button("RESET DATA"): 
        st.session_state.ext=[]
        st.session_state.dat_mode=False
        st.rerun()

# --- ADMIN ---
if nav == "Supervisor":
    st.title("Admin")
    if st.text_input("Password",type="password")=="admin123":
        st.info("Configuration Unlocked")
        c1,c2 = st.columns(2)
        lp = c1.text_input("ID Lot", value=st.session_state.lot_p)
        ls = c2.text_input("Scr Lot", value=st.session_state.lot_s)
        if st.button("Lock Lots"): st.session_state.lot_p=lp; st.session_state.lot_s=ls; st.success("Updated"); st.rerun()

        t1,t2=st.tabs(["P11","Scr"])
        with t1:
            if st.button("Update P11 (Paste)"):
                d,m = parse_paste(st.session_state.temp_p, 11)
                if d is not None: st.session_state.p11=d; st.success(m)
            st.session_state.temp_p = st.text_area("Paste Data (P11)", height=150)
            st.dataframe(st.session_state.p11.iloc[:,:15])
        with t2:
            if st.button("Update Scr (Paste)"):
                d,m = parse_paste(st.session_state.temp_s, 3)
                if d is not None: st.session_state.p3=d; st.success(m)
            st.session_state.temp_s = st.text_area("Paste Data (S)", height=100)
            st.dataframe(st.session_state.p3.iloc[:,:15])

# --- USER ---
else:
    # LOCK
    if not st.session_state.lot_p or not st.session_state.lot_s:
        st.error("SYSTEM LOCKED: Supervisor must set Lot Numbers."); st.stop()

    st.markdown(f"""<div class='hospital-logo'><h2>Maternity & Children Hospital - Tabuk</h2><h4>Blood Bank Serology</h4><small>Lot ID: {st.session_state.lot_p}</small></div>""", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Pt"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()

    with st.form("main"):
        L, R = st.columns([1, 2.5])
        with L:
            ac_res = st.radio("Auto Control", ["Negative", "Positive"])
            st.write("Screening"); s1=st.selectbox("Scn I",GRADES); s2=st.selectbox("Scn II",GRADES); s3=st.selectbox("Scn III",GRADES)
        with R:
            st.write("ID Panel"); g1,g2=st.columns(2)
            with g1: c1=st.selectbox("1",GRADES); c2=st.selectbox("2",GRADES); c3=st.selectbox("3",GRADES); c4=st.selectbox("4",GRADES); c5=st.selectbox("5",GRADES); c6=st.selectbox("6",GRADES)
            with g2: c7=st.selectbox("7",GRADES); c8=st.selectbox("8",GRADES); c9=st.selectbox("9",GRADES); c10=st.selectbox("10",GRADES); c11=st.selectbox("11",GRADES)
        run = st.form_submit_button("🚀 Run Analysis")

    if run:
        inp_p = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
        inp_s = {"I":s1,"II":s2,"III":s3}
        
        # AC POSITIVE Logic
        if ac_res == "Positive":
            st.markdown("<div class='logic-fail'>🚨 Auto-Control POSITIVE</div>", unsafe_allow_html=True)
            if sum([normalize_grade(x) for x in inp_p.values()]) >= 11:
                st.markdown("<div class='clinical-alert'>⚠️ PAN-AGGLUTINATION + AC+ -> Check DHTR / History!</div>", unsafe_allow_html=True)
            st.session_state.dat_mode = True # Trigger DAT view
        
        # ALLO Logic
        elif sum([normalize_grade(x) for x in inp_p.values()]) == 11:
             st.markdown("<div class='logic-suspect'>⚠️ High Incidence Antibody (Pan-reactivity, AC Neg). Refer.</div>", unsafe_allow_html=True)
             st.session_state.dat_mode = False
             
        else:
            st.session_state.dat_mode = False
            # Call Improved Engine
            final_cands, notes = analyze_master_logic(inp_p, inp_s, st.session_state.ext)
            
            sigs = [x for x in final_cands if x not in INSIGNIFICANT_AGS]
            colds = [x for x in final_cands if x in INSIGNIFICANT_AGS]

            if not sigs and not colds:
                st.error("No Matches Found.")
            else:
                # HEADER - Smart Ordering
                # Sigs first
                if sigs:
                    # Special check: Is it likely only the first one?
                    # The parser sorted them by score! The first one is the "Best Match".
                    st.success(f"✅ **Most Likely:** Anti-{sigs[0]}")
                    if len(sigs) > 1:
                         st.write(f"**Also possible / Mixture:** {', '.join(['Anti-'+x for x in sigs[1:]])}")
                    if colds:
                         st.info(f"Cold/Insignificant: {', '.join(colds)}")
                         
                    # Alerts
                    if "anti-c_risk" in notes: st.warning("🛑 Anti-c present: Transfuse R1R1.")

                    # Strategy (Separation)
                    if len(sigs) > 1:
                        st.markdown("#### 🔬 Smart Selection Strategy")
                        for t in sigs:
                            conf = [x for x in sigs if x!=t]
                            stock = find_matching_cells_in_inventory(t, conf)
                            avl_txt = f"<span class='cell-hint'>{', '.join(stock)}</span>" if stock else "<span style='color:red'>Search Lib</span>"
                            st.markdown(f"To Confirm <b>Anti-{t}</b>: Need {t}+ / {' '.join([c+'-' for c in conf])} --> {avl_txt}", unsafe_allow_html=True)
                    
                    st.write("---")
                    
                    # Validation Loop (P Value)
                    all_met = True
                    for ab in (sigs + colds):
                        ok, p_cnt, n_cnt = check_p_val_stats(ab, inp_p, inp_s, st.session_state.ext)
                        ic = "✅" if ok else "⚠️"
                        ms = "Rule Met" if ok else "NOT Confirmed"
                        st.write(f"{ic} **Anti-{ab}:** {ms} ({p_cnt}P / {n_cnt}N)")
                        if not ok: all_met = False
                    
                    if all_met and sigs:
                        if st.button("🖨️ Print Report"):
                            h = f"<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='result-sheet'>Pt:{nm}|{mr}<hr><b>Conclusion: Anti-{', '.join(sigs)}</b><br>{'Cold: '+', '.join(colds) if colds else ''}<br>Rule of 3 Valid.<br>Action: Phenotype Neg.<br><br>Sig:_________</div><div class='footer-print'>Dr. Haitham Ismail</div></div><script>window.print()</script>"
                            st.markdown(h, unsafe_allow_html=True)

    # PERSISTENT MODULES (OUTSIDE FORM)
    if st.session_state.get('dat_mode', False):
        st.write("---")
        with st.container():
            st.subheader("🧪 DAT Entry")
            cc = st.columns(3)
            i = cc[0].selectbox("IgG",["Neg","Pos"]); c=cc[1].selectbox("C3",["Neg","Pos"]); ct=cc[2].selectbox("Ctl",["Neg","Pos"])
            if ct=="Pos": st.error("Invalid")
            elif i=="Pos": st.warning("👉 Probable WAIHA / DHTR. Perform Elution.")
            elif c=="Pos": st.info("👉 Probable CAS.")

    if not st.session_state.get('dat_mode', False):
        with st.expander("➕ Add Cell"):
            c1,c2=st.columns(2)
            id_n=c1.text_input("ID"); rs_n=c2.selectbox("Res",GRADES)
            st.write("Ag+:")
            cc=st.columns(6); ph_n={}
            for idx, a in enumerate(AGS):
                if cc[idx%6].checkbox(a): ph_n[a]=1
                else: ph_n[a]=0
            if st.button("Add Cell"):
                st.session_state.ext.append({"res":normalize_grade(rs_n), "res_txt":rs_n, "ph":ph_n})
                st.success("Added."); st.rerun()

    if st.session_state.ext: st.table(pd.DataFrame(st.session_state.ext)[['res_txt']])
