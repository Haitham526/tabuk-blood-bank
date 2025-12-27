import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. SETUP & STYLE
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
    
    /* Lot Warning */
    .lot-warning { background-color: #fff3e0; color: #e65100; padding: 5px; text-align: center; border-bottom: 1px solid #ffb74d;}

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
# Lots
if 'lot_p' not in st.session_state: st.session_state.lot_p = "NOT SET"
if 'lot_s' not in st.session_state: st.session_state.lot_s = "NOT SET"
# Persistence
if 'ext' not in st.session_state: st.session_state.ext = []

# ==========================================
# 4. LOGIC ENGINE (Stable Copy)
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
                # Accept: +, 1, pos, w.  REJECT: nt, 0, neg
                v = 1 if any(x in v_clean for x in ['+', '1', 'pos', 'w']) else 0
                vals.append(v)
            if len(vals) > 26: vals = vals[-26:]
            while len(vals) < 26: vals.append(0)
            d = {"ID": f"C{c+1}" if limit==11 else f"Scn"}
            for i, ag in enumerate(AGS): d[ag] = vals[i]
            data.append(d)
            c+=1
        return pd.DataFrame(data), f"Updated {c} rows."
    except Exception as e: return None, str(e)

def analyze_alloantibodies(in_p, in_s, extra_cells):
    ruled_out = set()
    # Panel Exclusion
    for i in range(1, 12):
        if normalize_grade(in_p[i]) == 0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False 
                if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
    # Screen Exclusion
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
    
    # Masking Rules (Silent for D)
    is_D = "D" in display_cands
    final_list = []
    notes = []
    for c in display_cands:
        if is_D and (c=="C" or c=="E"): continue 
        final_list.append(c)
        
    # No Blue Note for D
    if "c" in final_list: notes.append("anti-c_risk")
    
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
# FOOTER BADGE
st.markdown("""
<div class='dr-signature no-print'>
    <span class='dr-name'>Dr. Haitham Ismail</span><br>
    <span class='dr-title'>Clinical Hematology/Oncology & BM Transplantation & Transfusion Medicine Consultant</span>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Access Level", ["Workstation", "Admin/Supervisor"])
    if st.button("Factory Reset"): st.session_state.ext=[]; st.rerun()

# --- ADMIN VIEW ---
if nav == "Admin/Supervisor":
    st.title("Supervisor Configuration")
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

# --- USER VIEW (UNLOCKED) ---
else:
    # 1. HEADER (Safe Lot Display)
    lp = st.session_state.lot_p if st.session_state.lot_p else "NOT SET"
    ls = st.session_state.lot_s if st.session_state.lot_s else "NOT SET"
    
    st.markdown(f"""
    <div class='hospital-logo'>
        <h2 style='color:#8B0000'>Maternity & Children Hospital - Tabuk</h2>
        <h4 style='color:#555'>Blood Bank Serology Unit</h4>
    </div>
    <div class='lot-warning'>
        <b>Active ID Panel:</b> {lp} | <b>Active Screen:</b> {ls}
    </div>
    <br>
    """, unsafe_allow_html=True)
    
    # 2. PATIENT FORM
    c1,c2,c3,c4=st.columns(4)
    nm=c1.text_input("Patient"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()

    # 3. ENTRY FORM
    with st.form("main"):
        colL, colR = st.columns([1, 2.5])
        with colL:
            st.write("<b>Screening</b>", unsafe_allow_html=True)
            ac_res = st.radio("Auto Control", ["Negative", "Positive"])
            st.write("---")
            s1=st.selectbox("Scn I", GRADES); s2=st.selectbox("Scn II", GRADES); s3=st.selectbox("Scn III", GRADES)
        with colR:
            st.write("<b>Identification Panel</b>", unsafe_allow_html=True)
            g1,g2=st.columns(2)
            with g1:
                c1=st.selectbox("1",GRADES,key="c1"); c2=st.selectbox("2",GRADES,key="c2"); c3=st.selectbox("3",GRADES,key="c3")
                c4=st.selectbox("4",GRADES,key="c4"); c5=st.selectbox("5",GRADES,key="c5"); c6=st.selectbox("6",GRADES,key="c6")
            with g2:
                c7=st.selectbox("7",GRADES,key="c7"); c8=st.selectbox("8",GRADES,key="c8"); c9=st.selectbox("9",GRADES,key="c9")
                c10=st.selectbox("10",GRADES,key="c10"); c11=st.selectbox("11",GRADES,key="c11")
                
        run = st.form_submit_button("🚀 Run Comprehensive Analysis")

    if run:
        st.write("---")
        inp_p = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
        inp_s = {"I":s1,"II":s2,"III":s3}
        pos_cnt = sum([normalize_grade(x) for x in inp_p.values()])
        
        # --- SCENARIO 1: AUTO POS ---
        if ac_res == "Positive":
            st.markdown("""<div class='logic-critical'><h3>🚨 Auto-Control POSITIVE</h3>Analysis Halted. See DAT Guide below.</div>""", unsafe_allow_html=True)
            
            if pos_cnt == 11:
                st.markdown("""<div class='logic-alert'>⚠️ <b>High Risk of DHTR (Delayed Transfusion Reaction).</b> Check history. Elution mandatory.</div>""", unsafe_allow_html=True)
            
            # Interactive DAT
            st.session_state.dat_mode = True 
        
        # --- SCENARIO 2: ALLO ---
        else:
            st.session_state.dat_mode = False
            
            if pos_cnt == 11:
                st.markdown("""<div class='logic-alert'>⚠️ <b>High Incidence Antibody</b> suspected (Pan-reactivity).</div>""", unsafe_allow_html=True)
            else:
                # Exclusion & Logic
                final_cands, notes = analyze_alloantibodies(inp_p, inp_s, st.session_state.ext)
                
                sigs = [x for x in final_cands if x not in INSIGNIFICANT_AGS]
                colds = [x for x in final_cands if x in INSIGNIFICANT_AGS]

                st.subheader("Result Conclusion")
                
                if not sigs and not colds:
                    st.error("No Match Found.")
                else:
                    all_ok = True
                    # --- SIGNIFICANT ANTIBODIES ---
                    if sigs:
                        st.success(f"**Identified:** Anti-{', '.join(sigs)}")
                    if colds:
                        st.markdown(f"<div class='note-gray'>Insignificant Detected: Anti-{', '.join(colds)}</div>", unsafe_allow_html=True)
                    
                    if "anti-c_risk" in notes:
                        st.markdown("<div class='logic-alert'>🛑 <b>Anti-c Detected.</b> Must provide R1R1 (E- c-) Units.</div>", unsafe_allow_html=True)
                    
                    st.write("---")
                    
                    # Validation Loop
                    for ab in (sigs+colds):
                        ok, p_n, n_n = check_p_val_stats(ab, inp_p, inp_s, st.session_state.ext)
                        if ok:
                            st.markdown(f"<div class='logic-pass'>✅ <b>Anti-{ab}:</b> Confirmed (P={p_n} / N={n_n}).</div>", unsafe_allow_html=True)
                        else:
                            all_ok = False
                            st.markdown(f"<div class='logic-fail'>🛑 <b>Anti-{ab}:</b> Rule of 3 NOT MET (P={p_n} / N={n_n}).</div>", unsafe_allow_html=True)

                    if len(sigs) > 1:
                         st.info("💡 <b>Multiple Abs?</b> Use 'Selected Cells' below to separate/confirm.")
                         for t in sigs:
                             conflicts = [x for x in sigs if x!=t]
                             st.write(f"- <b>Anti-{t}</b>: Need cell ({t}+ / {' '.join(conflicts)}- )")

                    if all_ok and sigs:
                        if st.button("🖨️ Print Official Report"):
                            h=f"""<div class='print-only'><br><center><h2>Maternity & Children Hospital - Tabuk</h2><h3>Serology Lab</h3></center><div class='result-sheet'><b>Patient:</b> {nm} ({mr})<br><b>Tech:</b> {tc} | <b>Date:</b> {dt} | <b>Lot:</b> {lp}<hr><h3>Conclusion: Anti-{', '.join(sigs)}</h3>{' + '.join(colds)+' (Cold)' if colds else ''}<br><b>Status:</b> Confirmed (p<=0.05).<br><b>Clinical:</b> Phenotype Patient Negative. Crossmatch compatible units.<br><br><br><b>Signature:</b> ____________________</div><div class='print-footer'>Dr. Haitham Ismail | Consultant</div></div><script>window.print()</script>"""
                            st.markdown(h, unsafe_allow_html=True)

    # PERSISTENT DAT FORM
    if st.session_state.get('dat_mode', False):
        st.write("---")
        with st.container(border=True):
            st.subheader("🧪 DAT Investigation")
            d1,d2,d3=st.columns(3)
            r_igg=d1.selectbox("IgG",["Negative","Positive"]); r_c3=d2.selectbox("C3d",["Negative","Positive"]); r_ct=d3.selectbox("Ctrl",["Negative","Positive"])
            if r_ct=="Positive": st.error("Invalid")
            elif r_igg=="Positive": st.warning("Probable WAIHA / DHTR.")
            elif r_c3=="Positive": st.info("Probable CAS (Cold).")

    # ADD EXTRA CELLS
    with st.expander("➕ Add Selected Cells (To confirm rules)"):
        with st.form("exx"):
            id_x=st.text_input("Cell Lot"); res_x=st.selectbox("Result",GRADES)
            st.write("Antigens (+):")
            cg=st.columns(8)
            new_p={}
            for i,ag in enumerate(AGS): 
                if cg[i%8].checkbox(ag): new_p[ag]=1 
                else: new_p[ag]=0
            if st.form_submit_button("Add Cell"):
                st.session_state.ext.append({"res":normalize_grade(res_x), "res_txt":res_x, "ph":new_p})
                st.success("Added! Run Analysis Again.")
    
    if st.session_state.ext:
        st.caption(f"External Cells added: {len(st.session_state.ext)}")
