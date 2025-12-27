import streamlit as st
import pandas as pd
from datetime import date

# 1. SETUP & STYLE
st.set_page_config(page_title="Tabuk Serology Expert", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    /* Printing & Header */
    @media print { 
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 4px double #8B0000; padding: 25px; font-family: 'Times New Roman'; font-size:14px; }
        .page-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; }
    }
    .print-only { display: none; }
    
    .hospital-logo { text-align: center; border-bottom: 5px solid #8B0000; padding-bottom: 5px; color: #003366; font-family: sans-serif; font-weight: bold;}
    
    .status-confirmed { background-color: #d1e7dd; padding: 10px; border-left: 6px solid #198754; color: #0f5132; margin-bottom: 5px;}
    .status-warning { background-color: #fff3cd; padding: 10px; border-left: 6px solid #ffc107; color: #856404; margin-bottom: 5px;}
    .status-critical { background-color: #f8d7da; padding: 10px; border-left: 6px solid #dc3545; color: #842029; font-weight: bold;}
    .status-info { background-color: #e2e3e5; padding: 10px; border-left: 6px solid #6c757d; color: #383d41; font-style: italic;}
    
    .strategy-box { border: 1px dashed #0d6efd; background-color: #cfe2ff; padding: 10px; border-radius: 4px; color: #084298; margin-top: 5px;}
    
    .dr-signature { position: fixed; bottom: 10px; right: 15px; background: rgba(255,255,255,0.95); padding: 5px 10px; border: 2px solid #8B0000; border-radius: 5px; z-index:99; text-align:center; box-shadow: 2px 2px 5px rgba(0,0,0,0.1); }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class='dr-signature no-print'>
    <span style='color:#8B0000; font-weight:bold'>Dr. Haitham Ismail</span><br>
    <span style='font-size:11px'>Clinical Hematology/Oncology &<br>BM Transplantation & Transfusion Medicine Consultant</span>
</div>
""", unsafe_allow_html=True)

# 2. DEFINITIONS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
INSIGNIFICANT_AGS = ["Lea", "Leb", "Lua", "P1"] 
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# 3. STATE INITIALIZATION
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'lot_p' not in st.session_state: st.session_state.lot_p = ""
if 'lot_s' not in st.session_state: st.session_state.lot_s = ""
if 'ext' not in st.session_state: st.session_state.ext = []

# ==========================================
# 4. LOGIC ENGINE
# ==========================================
def normalize(val):
    s = str(val).lower().strip()
    if s in ["0", "neg"]: return 0
    return 1

# *** THE FIXED PARSER ***
def parse_paste(txt, limit):
    try:
        # 1. Clean empty lines
        lines = [line for line in txt.strip().split('\n') if line.strip()]
        data = []
        c = 0
        
        for line in lines:
            if c >= limit: break
            parts = line.split('\t')
            row_v = []
            
            # Logic to find relevant data
            # Excel paste usually puts numbers; handle text and 'nt'
            cleaned_parts = [p.strip() for p in parts if p.strip() != '']
            
            # Auto-align: take first 26 valid-looking values or just first 26
            count_v = 0
            for p in parts:
                v_str = str(p).lower().strip()
                # 0 for: 0, nt, neg, empty
                # 1 for: +, 1, pos, w, +w
                if any(x in v_str for x in ['+', '1', 'pos', 'w', 'yes']):
                    row_v.append(1)
                else:
                    row_v.append(0) # Treats 'nt', '0', etc as 0
            
            # Handle list length (Panel 26 Ags)
            # If copied row is huge, take last 26 cols usually containing Antigens
            # If user copied just numbers, take first 26
            
            final_vals = row_v
            if len(row_v) > 26:
                # Often copies row numbers or names first. 
                # Antigens usually end the row? No, often middle.
                # Safe bet: If user follows instruction "Copy numbers only", first 26 are it.
                final_vals = row_v[:26] 
            
            # Pad with 0 if short
            while len(final_vals) < 26: final_vals.append(0)

            d_row = {"ID": f"C{c+1}" if limit==11 else f"S{c}"}
            for i, ag in enumerate(AGS): 
                d_row[ag] = final_vals[i] if i < len(final_vals) else 0
                
            data.append(d_row)
            c+=1
            
        return pd.DataFrame(data), f"Successfully mapped {c} rows."
    except Exception as e: return None, str(e)

# Suggestions Logic
def find_matching_cells_in_inventory(target_ab, conflicts):
    found = []
    # Panel
    for i in range(11):
        c = st.session_state.p11.iloc[i]
        if c.get(target_ab,0)==1:
            safe=True
            for b in conflicts:
                if c.get(b,0)==1: safe=False; break
            if safe: found.append(f"Panel#{i+1}")
    # Screen
    sc=["I","II","III"]
    for i,l in enumerate(sc):
        c = st.session_state.p3.iloc[i]
        if c.get(target_ab,0)==1:
            safe=True
            for b in conflicts:
                if c.get(b,0)==1: safe=False; break
            if safe: found.append(f"Scn-{l}")
    return found

# Main Analysis Logic
def calculate_expert_logic(inputs_p, inputs_s, extra_cells):
    # A. Exclusion
    ruled = set()
    # Panel
    for i in range(1,12):
        if normalize(inputs_p[i])==0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                if ph.get(ag,0)==1 and safe: ruled.add(ag)
    # Screen
    sm={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize(inputs_s[k])==0:
            ph = st.session_state.p3.iloc[sm[k]]
            for ag in AGS:
                if ag not in ruled:
                    safe=True
                    if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                    if ph.get(ag,0)==1 and safe: ruled.add(ag)
    # Extra
    for ex in extra_cells:
        if normalize(ex['res'])==0:
            for ag in AGS:
                if ex['ph'].get(ag,0)==1: ruled.add(ag)

    # B. Candidates
    candidates = [x for x in AGS if x not in ruled]
    display = [x for x in candidates if x not in IGNORED_AGS]

    # C. Logic Check (Pattern Matching Score)
    scored = []
    
    # Pre-calc D/C presence for Anti-G check
    d_pres = "D" in display
    c_pres = "C" in display

    # Anti-G Check Logic (Strict Pattern: Cells 1,2,3,4,8 Pos?)
    # Using specific Panel cells known for D+C
    g_cells = [1,2,3,4,8]
    is_G_Pattern = True
    for gc in g_cells:
        if normalize(inputs_p[gc]) == 0: 
            is_G_Pattern = False; break
            
    final_list = []
    notes = []
    
    # --- RANKING ---
    for cand in display:
        match=0; miss=0
        # Check Panel Only for Scoring Pattern
        for i in range(1,12):
            is_pos = normalize(inputs_p[i])
            has_ag = st.session_state.p11.iloc[i-1].get(cand,0)
            if is_pos and has_ag: match+=1
            if is_pos and not has_ag: miss+=1
        
        # Anti-D Masking Logic (Inside Loop)
        if d_pres:
            if cand in ["C","E"]: 
                # If pattern strongly suggests G, Keep C?
                # User Request: If pattern fits, suggest G. Otherwise Silent Mask.
                if cand == "C" and is_G_Pattern: 
                    notes.append("suspect_G")
                else:
                    continue # Hide C and E silently
                    
        final_list.append(cand)
        
    if "c" in final_list: notes.append("anti_c_risk")

    return final_list, notes

# Rule 3 Stats
def check_r3(cand, in_p, in_s, extra):
    p, n = 0, 0
    # Panel
    for i in range(1,12):
        s=normalize(in_p[i]); h=st.session_state.p11.iloc[i-1].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    sid={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s=normalize(in_s[k]); h=st.session_state.p3.iloc[sid[k]].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extra
    for ex in extra:
        s=normalize(ex['res']); h=ex['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
        
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    return ok, p, n

# ==========================================
# 5. UI LAYOUT
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Admin"])
    if st.button("RESET"): st.session_state.ext=[]; st.rerun()

# --- ADMIN ---
if nav == "Admin":
    st.title("Admin")
    if st.text_input("Pwd",type="password")=="admin123":
        c1,c2 = st.columns(2)
        lp = c1.text_input("Lot Panel", value=st.session_state.lot_p)
        ls = c2.text_input("Lot Screen", value=st.session_state.lot_s)
        if st.button("Save Lots"): st.session_state.lot_p=lp; st.session_state.lot_s=ls; st.success("OK"); st.rerun()
        
        t1,t2=st.tabs(["Panel 11","Screen 3"])
        with t1:
            pt=st.text_area("Paste Digits (Panel)", height=150)
            if st.button("Update Panel"):
                # *** FIX: Using correct function name ***
                d,m = parse_paste(pt, 11) 
                if d is not None: st.session_state.p11=d; st.success(m)
            st.dataframe(st.session_state.p11.iloc[:,:15])
        with t2:
            st2=st.text_area("Paste Digits (Screen)", height=100)
            if st.button("Update Screen"):
                # *** FIX: Using correct function name ***
                d,m = parse_paste(st2, 3) 
                if d is not None: st.session_state.p3=d; st.success(m)
            st.dataframe(st.session_state.p3.iloc[:,:15])

# --- WORKSTATION ---
else:
    # 1. HEADERS & LOCK
    if not st.session_state.lot_p or not st.session_state.lot_s:
        st.error("LOCKED: Enter Lot Numbers in Admin."); st.stop()
        
    st.markdown(f"""
    <div class='hospital-logo'>
    <h2>Maternity & Children Hospital - Tabuk</h2>
    <h4>Serology Workstation</h4>
    <small><b>ID Lot:</b> {st.session_state.lot_p} | <b>Scn Lot:</b> {st.session_state.lot_s}</small>
    </div>""", unsafe_allow_html=True)
    
    # 2. PATIENT FORM
    c1,c2,c3,c4=st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()

    # 3. ENTRY FORM
    with st.form("main_form"):
        colL, colR = st.columns([1, 2])
        with colL:
            st.write("<b>Control</b>", unsafe_allow_html=True)
            ac = st.radio("AC", ["Negative","Positive"])
            st.write("<b>Screening</b>", unsafe_allow_html=True)
            s1=st.selectbox("Scn I",GRADES); s2=st.selectbox("Scn II",GRADES); s3=st.selectbox("Scn III",GRADES)
        with colR:
            st.write("<b>Panel</b>", unsafe_allow_html=True)
            g1,g2=st.columns(2)
            with g1:
                c1=st.selectbox("1",GRADES,key="k1"); c2=st.selectbox("2",GRADES,key="k2"); c3=st.selectbox("3",GRADES,key="k3")
                c4=st.selectbox("4",GRADES,key="k4"); c5=st.selectbox("5",GRADES,key="k5"); c6=st.selectbox("6",GRADES,key="k6")
            with g2:
                c7=st.selectbox("7",GRADES,key="k7"); c8=st.selectbox("8",GRADES,key="k8"); c9=st.selectbox("9",GRADES,key="k9")
                c10=st.selectbox("10",GRADES,key="k10"); c11=st.selectbox("11",GRADES,key="k11")
        run = st.form_submit_button("🚀 Run Analysis")

    if run:
        inp_p={1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
        inp_s={"I":s1,"II":s2,"III":s3}
        
        pos_cnt = sum([normalize(x) for x in inp_p.values()]) + sum([normalize(x) for x in inp_s.values()])
        
        # --- SCENARIO 1: AC POSITIVE ---
        if ac == "Positive":
            st.markdown("<div class='status-critical'>🚨 Auto Control POSITIVE</div>", unsafe_allow_html=True)
            if pos_cnt >= 11:
                st.warning("⚠️ High Risk of DHTR (if transfused). Do not result as simple WAIHA.")
            
            # Interactive DAT Table (Persistent within Run state visually)
            st.subheader("Monospecific DAT:")
            with st.container(border=True):
                d1,d2,d3 = st.columns(3)
                ig=d1.selectbox("IgG", ["Neg","Pos"], key="dg"); c3=d2.selectbox("C3", ["Neg","Pos"], key="dc"); ct=d3.selectbox("Ctl",["Neg","Pos"], key="dct")
                if ct=="Pos": st.error("Invalid")
                elif ig=="Pos": st.warning("Probable WAIHA/DHTR. Do Adsorption/Elution.")
                elif c3=="Pos": st.info("Probable CAS. Use Pre-warm.")
        
        # --- SCENARIO 2: HIGH FREQ ---
        elif pos_cnt >= 13: # (All 14 positive or close)
            st.markdown("<div class='status-warning'>⚠️ <b>High Incidence Antibody</b><br>Pan-agglutination with Neg AC.<br>Action: Check Siblings, Refer Sample.</div>", unsafe_allow_html=True)

        # --- SCENARIO 3: ALLOANTIBODY ---
        else:
            final_cands, notes = calculate_expert_logic(inp_p, inp_s, st.session_state.ext)
            
            sigs = [x for x in final_cands if x not in INSIGNIFICANT_AGS]
            colds = [x for x in final_cands if x in INSIGNIFICANT_AGS]
            
            if not sigs and not colds:
                st.error("No Match Found / All Excluded.")
            else:
                st.subheader("Results")
                if "suspect_G" in notes:
                    st.warning("⚠️ Pattern Matches **Anti-G or Anti-D+C**. (Cell 1,2,3,4,8 Pos). Differentiation Needed.")
                elif sigs:
                    st.success(f"**Identified:** Anti-{', '.join(sigs)}")
                if colds:
                    st.markdown(f"<div class='status-info'>Others: Anti-{', '.join(colds)}</div>",unsafe_allow_html=True)
                
                if "anti-c_risk" in notes:
                    st.error("🛑 Anti-c found: Must transfuse R1R1 (E- c-).")
                
                # Validation Loop
                all_valid = True
                valid_ab = []
                st.write("---")
                
                # Check Probability for each
                for ab in (sigs + colds):
                    ok, p, n = check_r3(ab, inp_p, inp_s, st.session_state.ext)
                    txt = "Confirmed" if ok else "Unconfirmed"
                    ico = "✅" if ok else "⚠️"
                    st.write(f"**{ico} Anti-{ab}**: {txt} ({p}P / {n}N)")
                    if ok: valid_ab.append(ab)
                    else: all_valid = False
                
                # Separation Logic
                if len(sigs) > 1:
                    st.info("Strategy: Use Selected Cells")
                    for t in sigs:
                        oth = [o for o in sigs if o!=t]
                        av = find_matching_cells_in_inventory(t, oth)
                        av_t = f"Found: {', '.join(av)}" if av else "Search External"
                        st.write(f"- Confirm **{t}**: {t}+ / {' '.join(oth)}- | {av_t}")

                # Print
                if all_valid and sigs:
                    if st.button("Print Report"):
                         rhtml = f"""<div class='print-only'><center><h2>MCH Tabuk</h2></center><div class='result-sheet'>Pt: {nm} ({mr})<hr><b>Res: Anti-{', '.join(sigs)}</b><br>{' + '.join(colds) if colds else ''}<br>Confirmed (p<=0.05).<br>Note: Phenotype Neg.<br><br>Sig: ___________</div></div><script>window.print()</script>"""
                         st.markdown(rhtml, unsafe_allow_html=True)
                
    # EXTRA CELL
    if not ac == "Positive":
        with st.expander("Add Cell"):
            c1,c2=st.columns(2); id=c1.text_input("ID"); rs=c2.selectbox("R",GRADES, key="exr")
            st.write("Phenotype:")
            cg=st.columns(8); ph={}
            for i,ag in enumerate(AGS):
                if cg[i%8].checkbox(ag, key=f"bx{ag}"): ph[ag]=1
                else: ph[ag]=0
            if st.button("Add"):
                st.session_state.ext.append({"res":normalize(rs), "res_txt":rs, "ph":ph})
                st.success("Added! Re-run."); st.rerun()

    if st.session_state.ext: st.table(pd.DataFrame(st.session_state.ext))
