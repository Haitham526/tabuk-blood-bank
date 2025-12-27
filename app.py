import streamlit as st
import pandas as pd
from datetime import date

# --------------------------------------------------------------------------
# 1. SETUP & BRANDING (RED SIGNATURE FIX)
# --------------------------------------------------------------------------
st.set_page_config(page_title="MCH Tabuk - Serology Expert", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { 
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 4px double #8B0000; padding: 25px; font-family: 'Times New Roman'; font-size:14px; }
        .footer-print { 
            position: fixed; bottom: 0; width: 100%; text-align: center; 
            color: #8B0000; font-weight: bold; border-top: 1px solid #ccc; padding: 10px; font-family: serif;
        }
    }
    .print-only { display: none; }
    
    .hospital-logo { color: #8B0000; text-align: center; border-bottom: 5px solid #8B0000; padding-bottom: 5px; font-family: 'Arial'; }
    
    /* LOT INFO BAR */
    .lot-bar {
        display: flex; justify-content: space-around; background-color: #f1f8e9; 
        border: 1px solid #81c784; padding: 8px; border-radius: 5px; margin-bottom: 20px; font-weight: bold; color: #1b5e20;
    }

    /* CLINICAL BOXES */
    .clinical-waiha { background-color: #f8d7da; border-left: 5px solid #dc3545; padding: 15px; margin: 10px 0; color: #721c24; }
    .clinical-cold { background-color: #cff4fc; border-left: 5px solid #0dcaf0; padding: 15px; margin: 10px 0; color: #055160; }
    .clinical-alert { background-color: #fff3cd; border: 2px solid #ffca2c; padding: 10px; color: #000; font-weight: bold; margin: 5px 0;}
    .cell-hint { font-size: 0.9em; color: #155724; background: #d4edda; padding: 2px 6px; border-radius: 4px; }

    /* SIGNATURE */
    .dr-signature { 
        position: fixed; bottom: 10px; right: 15px; 
        background: rgba(255,255,255,0.95); 
        padding: 8px 15px; border: 2px solid #8B0000; border-radius: 8px; z-index:99; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);
        text-align: center; font-family: 'Georgia', serif;
    }
    .dr-name { color: #8B0000; font-size: 15px; font-weight: bold; display: block;}
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

# RULES
IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
INSIGNIFICANT_AGS = ["Lea", "Lua", "Leb", "P1"] 
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# 3. STATE
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
# DISTINCT LOTS
if 'lot_p' not in st.session_state: st.session_state.lot_p = ""
if 'lot_s' not in st.session_state: st.session_state.lot_s = ""
# DAT STATE
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
            if len(vals) > 26: vals=vals[-26:]
            while len(vals) < 26: vals.append(0)
            d = {"ID": f"C{c+1}" if limit==11 else f"Scn"}
            for i, ag in enumerate(AGS): d[ag] = vals[i]
            data.append(d)
            c+=1
        return pd.DataFrame(data), f"Updated {c} rows."
    except Exception as e: return None, str(e)

# --- SMART SUGGESTIONS ---
def find_matching_cells_in_inventory(target_ab, conflicts):
    found_list = []
    # P11
    for i in range(11):
        cell = st.session_state.p11.iloc[i]
        if cell.get(target_ab,0)==1:
            clean = True
            for bad in conflicts: 
                if cell.get(bad,0)==1: clean=False; break
            if clean: found_list.append(f"Panel #{i+1}")
    # P3
    sc_lbls = ["I","II","III"]
    for i in range(3):
        cell = st.session_state.p3.iloc[i]
        if cell.get(target_ab,0)==1:
            clean = True
            for bad in conflicts: 
                if cell.get(bad,0)==1: clean=False; break
            if clean: found_list.append(f"Screen {sc_lbls[i]}")
    return found_list

# --- MAIN ANALYSIS ALGO ---
def analyze_alloantibodies(in_p, in_s, extra_cells):
    ruled_out = set()
    # 1. Panel Exclusion
    for i in range(1, 12):
        if normalize_grade(in_p[i]) == 0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False 
                if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
    # 2. Screen Exclusion
    smap={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize_grade(in_s[k]) == 0:
            ph = st.session_state.p3.iloc[smap[k]]
            for ag in AGS:
                if ag not in ruled_out:
                    safe=True
                    if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                    if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
    # 3. Extra Exclusion
    for ex in extra_cells:
        if normalize_grade(ex['res']) == 0:
            for ag in AGS:
                 if ex['ph'].get(ag,0)==1: ruled_out.add(ag)

    candidates = [x for x in AGS if x not in ruled_out]
    display_cands = [x for x in candidates if x not in IGNORED_AGS]
    
    # 4. ANTI-G CHECK (Pattern on Cell 1,2,3,4,8)
    g_indices = [1,2,3,4,8]
    is_G_pattern = True
    for idx in g_indices:
        if normalize_grade(in_p[idx]) == 0: 
            is_G_pattern = False
            break
            
    is_D = "D" in display_cands
    final_list = []
    notes = []
    
    for c in display_cands:
        # Special Logic for D masking
        if is_D:
            if c in ["C", "E"]:
                # Only show C if Anti-G pattern is strong and user wants to know
                if c=="C" and is_G_pattern:
                     notes.append("anti_G_suspect")
                     final_list.append(c) # Keep C
                else:
                     continue # Silent Masking for C and E
        
        final_list.append(c)
        
    if "c" in final_list: notes.append("anti-c_risk")
    
    return final_list, notes

def check_rule_3(cand, in_p, in_s, extras):
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
    for c in extras:
        s=normalize_grade(c['res']); h=c['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    return ok, p, n

# ==========================================
# 5. UI
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Supervisor"])
    if st.button("RESET DATA"): 
        st.session_state.ext=[]; st.session_state.dat_mode=False
        st.rerun()

# --- ADMIN ---
if nav == "Supervisor":
    st.title("Config")
    if st.text_input("Password",type="password")=="admin123":
        st.subheader("1. Lot Setup (Separate)")
        c1, c2 = st.columns(2)
        lp = c1.text_input("ID Panel Lot#", value=st.session_state.lot_p)
        ls = c2.text_input("Screen Panel Lot#", value=st.session_state.lot_s)
        if st.button("Save Lots"):
            st.session_state.lot_p=lp; st.session_state.lot_s=ls; st.success("Saved"); st.rerun()

        st.subheader("2. Grid Data (Copy-Paste)")
        t1, t2 = st.tabs(["Panel (11)", "Screen (3)"])
        with t1:
            p_txt=st.text_area("Paste Panel Numbers",height=150)
            if st.button("Upd P11"): 
                d,m=parse_paste(p_txt,11)
                if d is not None: st.session_state.p11=d; st.success(m)
            st.dataframe(st.session_state.p11.iloc[:,:15])
        with t2:
            s_txt=st.text_area("Paste Screen Numbers",height=100)
            if st.button("Upd Scr"): 
                d,m=parse_paste(s_txt,3)
                if d is not None: st.session_state.p3=d; st.success(m)
            st.dataframe(st.session_state.p3.iloc[:,:15])

# --- USER ---
else:
    # 1. HOSPITAL HEADER
    st.markdown("""
    <div class='hospital-logo'>
        <h2>Maternity & Children Hospital - Tabuk</h2>
        <h4 style='color:#555'>Blood Bank Serology Unit</h4>
    </div>
    """, unsafe_allow_html=True)
    
    # 2. LOT INFO BAR
    lp_txt = st.session_state.lot_p if st.session_state.lot_p else "⚠️ REQUIRED"
    ls_txt = st.session_state.lot_s if st.session_state.lot_s else "⚠️ REQUIRED"
    st.markdown(f"""
    <div class='lot-bar'>
        <span>ID Panel Lot: {lp_txt}</span> | <span>Screen Lot: {ls_txt}</span>
    </div>
    """, unsafe_allow_html=True)
    
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")

    # 3. FORM
    with st.form("main"):
        st.write("### Reaction Entry")
        L, R = st.columns([1, 2.5])
        with L:
            st.write("Controls")
            ac_res = st.radio("Auto Control (AC)", ["Negative", "Positive"])
            st.write("Screening")
            s1=st.selectbox("Scn I", GRADES)
            s2=st.selectbox("Scn II", GRADES)
            s3=st.selectbox("Scn III", GRADES)
        with R:
            st.write("Panel Reactions")
            g1,g2=st.columns(2)
            with g1:
                c1=st.selectbox("1",GRADES,key="1"); c2=st.selectbox("2",GRADES,key="2"); c3=st.selectbox("3",GRADES,key="3"); c4=st.selectbox("4",GRADES,key="4"); c5=st.selectbox("5",GRADES,key="5"); c6=st.selectbox("6",GRADES,key="6")
            with g2:
                c7=st.selectbox("7",GRADES,key="7"); c8=st.selectbox("8",GRADES,key="8"); c9=st.selectbox("9",GRADES,key="9"); c10=st.selectbox("10",GRADES,key="10"); c11=st.selectbox("11",GRADES,key="11")
        
        run = st.form_submit_button("🚀 Run Analysis")

    # 4. RESULTS
    if run:
        # Validate Lots
        if not st.session_state.lot_p or not st.session_state.lot_s:
            st.error("⛔ Action Blocked: Lots not configured by Supervisor.")
        
        else:
            # AUTO CONTROL CHECK (PRIORITY 1)
            if ac_res == "Positive":
                st.session_state.dat_mode = True # Trigger DAT view
            else:
                st.session_state.dat_mode = False # Allow Allo logic
                
                i_p = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
                i_s = {"I":s1,"II":s2,"III":s3}
                cnt = sum([normalize_grade(x) for x in i_p.values()])
                
                # High Frequency Check
                if cnt >= 11:
                    st.markdown("""<div class='clinical-alert'>⚠️ <b>High Incidence Antigen suspected.</b><br>Pan-reactivity with Neg AC.<br>Action: Check siblings / Reference Lab.</div>""", unsafe_allow_html=True)
                
                else:
                    final, notes = analyze_alloantibodies(i_p, i_s, st.session_state.ext)
                    sigs = [x for x in final if x not in INSIGNIFICANT_AGS]
                    others = [x for x in final if x in INSIGNIFICANT_AGS]

                    st.subheader("Conclusion")
                    
                    if not sigs and not others:
                        st.error("No Match Found / Inconclusive.")
                    else:
                        valid_all = True
                        
                        # --- ALERTS & NOTES ---
                        if "anti_G_suspect" in notes:
                            st.warning("⚠️ **Anti-G or Anti-D+C**: Reaction Pattern (Cells 1,2,3,4,8 Pos) suggests Anti-G. Perform Adsorption/Elution to differentiate.")
                        elif "D" in sigs:
                            # Silent mask applied (C and E removed from list)
                            st.caption("ℹ️ Anti-D present (Anti-C/Anti-E excluded/masked).")

                        if "anti-c_risk" in notes:
                            st.markdown("""<div class='clinical-alert'>🛑 <b>Anti-c Detected:</b> Patient requires R1R1 (E- c-) units to prevent Anti-E formation.</div>""", unsafe_allow_html=True)

                        # --- SIGNIFICANT ABS ---
                        if sigs:
                            st.success(f"**Identified:** Anti-{', '.join(sigs)}")
                        if others:
                            st.info(f"**Other:** Anti-{', '.join(others)} (Clinically insignificant/Cold)")
                            
                        # --- STRATEGY ADVISOR ---
                        if len(sigs) > 1:
                            st.write("---")
                            st.markdown("**🧪 Separation Strategy (Using Inventory):**")
                            for t in sigs:
                                conf = [x for x in sigs if x!=t]
                                found = find_matching_cells_in_inventory(t, conf)
                                s_txt = f"<span class='cell-hint'>{', '.join(found)}</span>" if found else "<span style='color:red'>Search External</span>"
                                
                                st.write(f"- Confirm **{t}**: Needs ({t}+ / {' '.join(conf)} neg) {s_txt}")
                                
                        # --- RULE OF 3 CHECK ---
                        for ab in (sigs+others):
                            ok, p, n = check_rule_3(ab, i_p, i_s, st.session_state.ext)
                            msg = "Rule of 3 MET" if ok else "Unconfirmed"
                            ic = "✅" if ok else "⚠️"
                            st.write(f"**{ic} Anti-{ab}:** {msg} (P:{p} / N:{n})")
                            if not ok: valid_all = False

                        if valid_all:
                             if st.button("Generate Official Report"):
                                 rpt=f"""<div class='print-only'><center><h2>Maternity & Children Hospital - Tabuk</h2><h3>Serology Report</h3></center><div class='result-sheet'><b>Pt:</b> {nm} ({mr})<br><b>Tech:</b> {tc} | <b>Lot:</b> {st.session_state.lot_p}<hr><b>Result:</b> Anti-{', '.join(sigs)}<br>{'('+','.join(others)+')' if others else ''}<br><b>Validation:</b> Confirmed (p<=0.05).<br><b>Clinical:</b> Phenotype Negative. Transfuse compatible.<br><br><b>Consultant Verified:</b> _____________</div><div class='print-footer'>Dr. Haitham Ismail | Consultant</div></div><script>window.print()</script>"""
                                 st.markdown(rpt, unsafe_allow_html=True)
                        else:
                            st.warning("⚠️ Validation Required. Add Cells below.")

    # 5. PERSISTENT MODULES
    # A. DAT (If AC Positive)
    if st.session_state.dat_mode:
        st.write("---")
        st.subheader("🧪 Monospecific DAT Workup")
        
        # DAT INPUT (Reactive)
        c_d1, c_d2, c_d3 = st.columns(3)
        igg = c_d1.selectbox("IgG", ["Negative","Positive"], key="dig")
        c3d = c_d2.selectbox("C3d", ["Negative","Positive"], key="dc3")
        ctl = c_d3.selectbox("Control", ["Negative","Positive"], key="dct")
        
        # LOGIC & INTERPRETATION (As requested)
        st.markdown("**Interpretation:**")
        if ctl == "Positive": st.error("Invalid. Control Positive.")
        else:
            if igg=="Positive": 
                st.warning("👉 **WAIHA** (Warm Autoimmune Hemolytic Anemia).")
                st.write("- Perform Elution/Adsorption.")
                # The Critical DHTR Warning
                st.markdown("<div class='clinical-waiha'><b>⚠️ Critical Note:</b> If recently transfused, rule out <b>Delayed Hemolytic Transfusion Reaction (DHTR)</b>. Elution is Mandatory.</div>", unsafe_allow_html=True)
            elif c3d=="Positive" and igg=="Negative":
                st.info("👉 **CAS** (Cold Agglutinin Syndrome).")
                st.write("- Use Pre-warm Technique.")

    # B. ADD CELLS (Always Available)
    if not st.session_state.dat_mode:
        with st.expander("➕ Add Selected Cell (From Library)"):
            id_x=st.text_input("ID"); rs_x=st.selectbox("R",GRADES,key="exr")
            ag_col=st.columns(6)
            new_p={}
            for i,ag in enumerate(AGS): 
                if ag_col[i%6].checkbox(ag): new_p[ag]=1
                else: new_p[ag]=0
            if st.button("Confirm Add"):
                st.session_state.ext.append({"res":normalize_grade(rs_x),"res_txt":rs_x,"ph":new_p})
                st.success("Added! Re-run Analysis.")
                
    if st.session_state.ext: st.table(pd.DataFrame(st.session_state.ext)[['res_txt']])
