import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. SETUP & BRANDING (Final Polish)
# ==========================================
st.set_page_config(page_title="Tabuk Serology Expert", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    /* Print Layout */
    @media print { 
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 5px double #8B0000; padding: 30px; font-family: 'Times New Roman'; }
        .page-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 2px solid #ccc; padding: 10px; font-weight: bold; }
    }
    .print-only { display: none; }
    
    .hospital-logo { color: #8B0000; text-align: center; border-bottom: 6px solid #8B0000; padding-bottom: 10px; font-family: sans-serif; font-weight: 800;}
    .lot-badge { background-color: #f1f8e9; color: #2e7d32; border: 1px solid #c8e6c9; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 0.9em; margin-bottom: 15px;}
    
    /* Logic Cards */
    .card-confirmed { background-color: #d1e7dd; padding: 15px; border-radius: 8px; border-left: 6px solid #198754; color: #0f5132; margin-bottom: 8px; }
    .card-warning { background-color: #fff3cd; padding: 15px; border-radius: 8px; border-left: 6px solid #ffc107; color: #856404; margin-bottom: 8px; }
    .card-critical { background-color: #f8d7da; padding: 15px; border-radius: 8px; border-left: 6px solid #dc3545; color: #842029; font-weight: bold; }
    
    /* Strategy Section */
    .strategy-block { border: 1px dashed #004085; background-color: #cce5ff; padding: 10px; border-radius: 5px; color: #004085; margin: 5px 0;}
    .found-cell { background: #198754; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.9em; margin-left: 5px; }
    
    /* Sticky Footer for Screen */
    .dr-float { position: fixed; bottom: 10px; right: 20px; background: rgba(255,255,255,0.95); padding: 10px; border: 1px solid #bbb; border-radius: 8px; box-shadow: 2px 2px 8px rgba(0,0,0,0.15); text-align: right; z-index: 9999; }
    .dr-name { color: #8B0000; font-family: serif; font-size: 14px; font-weight: bold; display: block; margin-bottom: 2px;}
    .dr-title { font-size: 11px; color: #333; }
    
    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class='dr-float no-print'>
    <span class='dr-name'>Dr. Haitham Ismail</span>
    <span class='dr-title'>Clinical Hematology/Oncology &<br>BM Transplantation & Transfusion Medicine Consultant</span>
</div>
""", unsafe_allow_html=True)

# 2. DEFINITIONS (ALL CONSTANTS)
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
# Anti-M kept as significant. P1/Lea/Lua as Cold/Insignificant
INSIGNIFICANT_AGS = ["Lea", "Lua", "Leb", "P1"] 
GRADES = ["Negative", "+1", "+2", "+3", "+4", "Hemolysis"] # Explicit Grades

# 3. STATE
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
# Locking mechanism
if 'lot_p' not in st.session_state: st.session_state.lot_p = ""
if 'lot_s' not in st.session_state: st.session_state.lot_s = ""
# App Logic
if 'dat_mode' not in st.session_state: st.session_state.dat_mode = False
if 'ext' not in st.session_state: st.session_state.ext = []

# ==========================================
# 4. LOGIC ENGINE (V1000 Verified)
# ==========================================
def normalize_grade(val):
    s = str(val).lower().strip()
    # Anything other than these specific negs is Positive
    return 0 if s in ["0", "negative", "neg", "nan", ""] else 1

def parse_paste(txt, limit=11):
    try:
        # Splits lines
        raw_rows = [r for r in txt.strip().split('\n') if r.strip()]
        data = []
        c = 0
        for line in raw_rows:
            if c >= limit: break
            parts = line.split('\t')
            vals = []
            for p in parts:
                v_clean = str(p).lower().strip()
                # Accept diverse inputs
                v = 1 if any(x in v_clean for x in ['+', '1', 'pos', 'w', 'yes']) else 0
                vals.append(v)
            
            # Trim/Pad to 26
            if len(vals) > 26: vals = vals[-26:]
            while len(vals) < 26: vals.append(0)
            
            # Create Row
            lbl = f"Cell {c+1}" if limit==11 else f"Scn"
            d = {"ID": lbl}
            for i, ag in enumerate(AGS): d[ag] = vals[i]
            data.append(d)
            c+=1
        
        return pd.DataFrame(data), f"Successfully mapped {c} rows."
    except Exception as e: return None, str(e)

# --- 1. Find cells for Strategy ---
def find_matching_cells_in_inventory(target_ab, conflicts):
    matches = []
    # Panel
    for i in range(11):
        cell = st.session_state.p11.iloc[i]
        if cell.get(target_ab,0)==1:
            clean = True
            for bad in conflicts: 
                if cell.get(bad,0)==1: clean=False; break
            if clean: matches.append(f"Panel #{i+1}")
    # Screen
    sc = ["I","II","III"]
    for i in range(3):
        cell = st.session_state.p3.iloc[i]
        if cell.get(target_ab,0)==1:
            clean = True
            for bad in conflicts: 
                if cell.get(bad,0)==1: clean=False; break
            if clean: matches.append(f"Screen {sc[i]}")
    return matches

# --- 2. Master Analysis ---
def run_serology_logic(inputs_p, inputs_s, extras):
    ruled_out = set()
    
    # 1. EXCLUSION PHASE (Panel + Screen + Extra)
    # Check Panel Negs
    for i in range(1, 12):
        if normalize_grade(inputs_p[i]) == 0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False 
                if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
    
    # Check Screen Negs
    s_idx = {"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize_grade(inputs_s[k]) == 0:
            ph = st.session_state.p3.iloc[s_idx[k]]
            for ag in AGS:
                if ag not in ruled_out: # Optim
                    safe=True
                    if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                    if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
                    
    # Check Extra Cells Negs
    for ex in extras:
        if normalize_grade(ex['res']) == 0:
            for ag in AGS:
                # Assume extra cells entered by tech don't have dosage ambiguity or rule strictly
                 if ex['ph'].get(ag,0)==1: ruled_out.add(ag)

    # 2. SURVIVORS & MASKING
    candidates = [x for x in AGS if x not in ruled_out]
    display_cands = [x for x in candidates if x not in IGNORED_AGS]
    
    # Anti-D Silent Masking Logic
    final_list = []
    notes = []
    
    # Check D Presence
    has_D = "D" in display_cands
    
    # Check G Pattern (1,2,3,4,8 Pos?) - Only relevant if D and C are present
    is_G_suspect = False
    if has_D and "C" in display_cands:
         # Check reactions of cells 1,2,3,4,8 (indicies 1..8)
         # Using Safe Get
         g_cells_reacting = all(normalize_grade(inputs_p.get(i,0))==1 for i in [1,2,3,4,8])
         if g_cells_reacting: is_G_suspect = True
    
    for c in display_cands:
        if has_D:
            if c in ["C", "E"]:
                # If G suspect is active and c is C, keep it and warn
                if c == "C" and is_G_suspect:
                    notes.append("suspect_G")
                else:
                    continue # Mask
        final_list.append(c)
        
    if "c" in final_list: notes.append("anti-c_risk")
    
    return final_list, notes

# --- 3. Rule of Three Calc ---
def check_p_values(cand, in_p, in_s, extras):
    p, n = 0, 0
    # Panel
    for i in range(1, 12):
        s=normalize_grade(in_p[i]); h=st.session_state.p11.iloc[i-1].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    sidx = {"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s=normalize_grade(in_s[k]); h=st.session_state.p3.iloc[sidx[k]].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extras
    for c in extras:
        s=normalize_grade(c['res']); h=c['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
        
    passed = (p>=3 and n>=3) or (p>=2 and n>=3) # Std or Mod
    return passed, p, n

# ==========================================
# 5. UI CONSTRUCTION
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Supervisor"])
    if st.button("RESET"): st.session_state.ext=[]; st.rerun()

# --- ADMIN VIEW ---
if nav == "Supervisor":
    st.title("Admin Configuration")
    if st.text_input("Password",type="password")=="admin123":
        c1, c2 = st.columns(2)
        lp = c1.text_input("ID Panel Lot", value=st.session_state.lot_p)
        ls = c2.text_input("Screen Lot", value=st.session_state.lot_s)
        if st.button("Save & Lock System"):
            st.session_state.lot_p = lp; st.session_state.lot_s = ls
            st.success("System Updated!"); st.rerun()

        t1,t2 = st.tabs(["Panel (Copy/Paste)", "Screen (Copy/Paste)"])
        with t1:
            pt = st.text_area("Paste Excel Digits (11 Rows)", height=150)
            if st.button("Update Panel"):
                df, m = parse_paste(pt, 11)
                if df is not None: st.session_state.p11=df; st.success(m)
            st.dataframe(st.session_state.p11.iloc[:,:15])
        with t2:
            st2 = st.text_area("Paste Excel Digits (3 Rows)", height=100)
            if st.button("Update Screen"):
                df2, m2 = parse_paste(st2, 3)
                if df2 is not None: st.session_state.p3=df2; st.success(m2)
            st.dataframe(st.session_state.p3.iloc[:,:15])

# --- USER VIEW ---
else:
    # 1. HEADER (Check Locks)
    if not st.session_state.lot_p or not st.session_state.lot_s:
        st.error("⛔ SYSTEM LOCKED: Lots not configured."); st.stop()

    st.markdown(f"""
    <div class='hospital-logo'>
        <h2>Maternity & Children Hospital - Tabuk</h2>
        <h4 style='color:#555'>Blood Bank Serology</h4>
        <span class='lot-badge'>ID Panel: {st.session_state.lot_p}</span> 
        <span class='lot-badge'>Screen: {st.session_state.lot_s}</span>
    </div>""", unsafe_allow_html=True)
    
    # 2. PATIENT
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()

    # 3. FORM INPUTS (Safety Form)
    with st.form("entry_grid"):
        colL, colR = st.columns([1, 2])
        with colL:
            st.write("<b>Control & Screen</b>", unsafe_allow_html=True)
            ac_in = st.radio("Auto Control", ["Negative", "Positive"])
            s1=st.selectbox("Scn I",GRADES); s2=st.selectbox("Scn II",GRADES); s3=st.selectbox("Scn III",GRADES)
        with colR:
            st.write("<b>Panel (11 Cells)</b>", unsafe_allow_html=True)
            g1,g2=st.columns(2)
            with g1:
                c1=st.selectbox("1",GRADES,key="k1"); c2=st.selectbox("2",GRADES,key="k2"); c3=st.selectbox("3",GRADES,key="k3")
                c4=st.selectbox("4",GRADES,key="k4"); c5=st.selectbox("5",GRADES,key="k5"); c6=st.selectbox("6",GRADES,key="k6")
            with g2:
                c7=st.selectbox("7",GRADES,key="k7"); c8=st.selectbox("8",GRADES,key="k8"); c9=st.selectbox("9",GRADES,key="k9")
                c10=st.selectbox("10",GRADES,key="k10"); c11=st.selectbox("11",GRADES,key="k11")
        run = st.form_submit_button("🚀 Run Analysis")

    if run:
        inp_p = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
        inp_s = {"I":s1,"II":s2,"III":s3}
        pos_sum = sum([normalize_grade(x) for x in inp_p.values()]) + sum([normalize_grade(x) for x in inp_s.values()])

        # LOGIC 1: AC POSITIVE
        if ac_in == "Positive":
            st.session_state.dat_mode = True # Unlock DAT
            st.markdown("<div class='status-critical'>🚨 Auto-Control POSITIVE</div>", unsafe_allow_html=True)
            if pos_sum >= 11:
                st.warning("⚠️ Critical: Pan-agglutination + Pos AC. Suspect **DHTR** vs WAIHA.")
            st.info("Allo-antibody Logic Suspended. Please complete DAT below.")
            
        # LOGIC 2: HIGH FREQ
        elif pos_sum >= 13: # (Panel all pos + screen mostly pos)
             st.session_state.dat_mode = False
             st.markdown("<div class='status-warning'>⚠️ <b>High Incidence Antibody</b><br>Pan-reactivity with Negative Auto-Control.</div>", unsafe_allow_html=True)

        # LOGIC 3: ALLOANTIBODY
        else:
            st.session_state.dat_mode = False
            cands, notes = analyze_master_logic(inp_p, inp_s, st.session_state.ext)
            
            # Separation
            real = [x for x in cands if x not in INSIGNIFICANT_AGS]
            cold = [x for x in cands if x in INSIGNIFICANT_AGS]
            
            st.subheader("Conclusion")
            
            if not real and not cold:
                st.error("No Match / Inconclusive.")
            else:
                # -- ALERTS --
                if "suspect_G" in notes: st.warning("⚠️ Suspect Anti-G pattern (D+C). Differentiate.")
                if "anti-c_risk" in notes: st.markdown("<div class='status-critical'>🛑 Anti-c: Give R1R1 (E- c-) Units.</div>", unsafe_allow_html=True)

                if real: st.success(f"**Identified:** Anti-{', '.join(real)}")
                if cold: st.info(f"**Insignificant:** Anti-{', '.join(cold)}")
                
                # -- STRATEGY --
                if len(real) > 1:
                     st.write("---")
                     st.markdown("#### 🔬 Separation Strategy (Inventory Check)")
                     for t in real:
                         others = [o for o in real if o!=t]
                         # Call Inventory Search Function
                         hits = find_matching_cells_in_inventory(t, others)
                         hit_txt = f"<span class='cell-hint'>{', '.join(hits)}</span>" if hits else "<span style='color:red'>Search Library</span>"
                         st.markdown(f"<div class='strategy-box'>Confirm <b>{t}</b> (Select {t}+ / {' '.join(others)} neg) -> {hit_txt}</div>", unsafe_allow_html=True)
                
                st.write("---")
                # -- VALIDATION --
                valid_all = True
                for ab in (real+cold):
                    ok, p, n = check_p_val_stats(ab, inp_p, inp_s, st.session_state.ext)
                    icon = "✅" if ok else "⚠️"
                    msg = "Confirmed (Rule of 3)" if ok else "Unconfirmed"
                    cls = "status-confirmed" if ok else "status-warning"
                    st.markdown(f"<div class='{cls}'>{icon} <b>Anti-{ab}:</b> {msg} (Pos:{p} | Neg:{n})</div>", unsafe_allow_html=True)
                    if not ok: valid_all = False
                
                if valid_all and real:
                    if st.button("🖨️ Official Report"):
                         t=f"""<div class='print-only'><center><h2>Maternity & Children Hospital - Tabuk</h2><h3>Serology Report</h3></center><br>Pt: {nm} ({mr}) | Tech: {tc} | Date: {dt}<hr><h4>Results: Anti-{', '.join(real)}</h4>Validation: Confirmed.<br>Note: Phenotype Neg.<br><br>Sig:___________<div class='page-footer'>Dr. Haitham Ismail</div></div><script>window.print()</script>"""
                         st.markdown(t, unsafe_allow_html=True)
    
    # 4. DAT SECTION (PERSISTENT)
    if st.session_state.dat_mode:
        st.write("---")
        st.subheader("🧪 Monospecific DAT Workup")
        with st.container(border=True):
             d1,d2,d3 = st.columns(3)
             i=d1.selectbox("IgG",["Neg","Pos"], key="di"); c=d2.selectbox("C3d",["Neg","Pos"], key="dc"); t=d3.selectbox("Ctl",["Neg","Pos"], key="dt")
             if t=="Pos": st.error("Invalid")
             elif i=="Pos": st.warning("Probable WAIHA. Rule out DHTR if transfused.")
             elif c=="Pos": st.info("Probable CAS (Cold Agglutinin).")
             
    # 5. EXTRA CELLS
    if not st.session_state.dat_mode:
        with st.expander("➕ Add Selected Cell (Validation)"):
            ex_id=st.text_input("Cell Lot"); ex_r=st.selectbox("Result",GRADES,key="ex_r")
            st.write("Phenotype:")
            cg=st.columns(8); new_ph={}
            for idx, a in enumerate(AGS):
                if cg[idx%8].checkbox(a): new_ph[a]=1 
                else: new_ph[a]=0
            if st.button("Add"):
                st.session_state.ext.append({"res":ex_r,"ph":new_ph})
                st.success("Added! Re-run."); st.rerun()

    if st.session_state.ext: st.table(pd.DataFrame(st.session_state.ext))
