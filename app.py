import streamlit as st
import pandas as pd
from datetime import date

# --------------------------------------------------------------------------
# 1. BASE CONFIG & STYLE (UNCHANGED)
# --------------------------------------------------------------------------
st.set_page_config(page_title="MCH Tabuk - Serology Expert", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { 
        .stApp > header, .sidebar, footer, .no-print { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 4px double #8B0000; padding: 30px; font-family: 'Times New Roman'; }
    }
    .print-only { display: none; }
    
    .hospital-logo { color: #8B0000; text-align: center; border-bottom: 5px solid #8B0000; padding-bottom: 5px; font-family: sans-serif; font-weight: bold;}
    .lot-badge { background-color: #ffebee; color: #b71c1c; padding: 5px; border-radius: 4px; font-size: 14px; text-align:center; margin-bottom:10px; border:1px solid #ffcdd2;}

    .clinical-high-freq { background-color: #fff3cd; border-left: 5px solid #ffc107; padding: 15px; margin: 10px 0; color: #856404; }
    .clinical-waiha { background-color: #f8d7da; border-left: 5px solid #dc3545; padding: 15px; margin: 10px 0; color: #721c24; }
    .clinical-cold { background-color: #cff4fc; border-left: 5px solid #0dcaf0; padding: 15px; margin: 10px 0; color: #055160; }
    .clinical-d-mask { background-color: #e2e3e5; border-left: 5px solid #383d41; padding: 10px; margin: 5px 0; color: #383d41; font-style: italic; }
    .clinical-c-risk { background-color: #fff3cd; border: 2px solid #ffca2c; padding: 10px; color: #000; font-weight: bold; margin: 5px 0;}
    
    /* Strategy Box Improved */
    .strategy-box { border: 1px dashed #004085; background: #cce5ff; padding: 12px; margin: 5px 0; border-radius: 5px; color: #004085; }
    .cell-suggest { font-weight: bold; color: #155724; background: #d4edda; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; margin-left: 10px; }

    .dr-sig { position: fixed; bottom: 5px; right: 10px; font-family: serif; font-size: 11px; background: rgba(255,255,255,0.9); padding: 5px; border: 1px solid #ccc; z-index:99; }
</style>
""", unsafe_allow_html=True)

st.markdown("""<div class='dr-sig no-print'><b>Dr. Haitham Ismail</b><br>Clinical Hematology/Oncology &<br>BM Transplantation & Transfusion Consultant</div>""", unsafe_allow_html=True)

# 2. DEFINITIONS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
INSIGNIFICANT_AGS = ["Lea", "Leb", "Lua"]
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# 3. STATE
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'lot' not in st.session_state: st.session_state.lot = "NOT SET"
if 'ext' not in st.session_state: st.session_state.ext = []

# 4. HELPERS
def normalize_grade(val):
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
            row_v = []
            for p in parts:
                v = 1 if any(x in str(p).lower() for x in ['+','1','pos','w']) else 0
                row_v.append(v)
            if len(row_v)>26: row_v=row_v[-26:]
            while len(row_v)<26: row_v.append(0)
            
            d = {"ID": f"C{c+1}" if limit==11 else f"S{c}"}
            for i, ag in enumerate(AGS): d[ag] = row_v[i]
            data.append(d)
            c+=1
        return pd.DataFrame(data), f"Updated {c} rows."
    except Exception as e: return None, str(e)

# --- [NEW FUNCTION]: FIND CELL IN INVENTORY ---
def find_matching_cells_in_inventory(target_ab, conflicts):
    # This scans Panel (p11) and Screen (p3)
    found_list = []
    
    # Scan Panel
    for i in range(11):
        cell = st.session_state.p11.iloc[i]
        # Logic: Target Ag == 1 AND All Conflict Ags == 0
        is_target = cell.get(target_ab, 0) == 1
        is_clean = True
        for bad in conflicts:
            if cell.get(bad, 0) == 1:
                is_clean = False; break
        
        if is_target and is_clean:
            found_list.append(f"Panel Cell {i+1}")

    # Scan Screen
    screen_labels = ["I", "II", "III"]
    for i, lbl in enumerate(screen_labels):
        cell = st.session_state.p3.iloc[i]
        is_target = cell.get(target_ab, 0) == 1
        is_clean = True
        for bad in conflicts:
            if cell.get(bad, 0) == 1:
                is_clean = False; break
        
        if is_target and is_clean:
            found_list.append(f"Screen Cell {lbl}")
            
    return found_list

# Logic
def analyze_master_logic(inputs_p, inputs_s, extras):
    ruled_out = set()
    # Panel
    for i in range(1, 12):
        if normalize_grade(inputs_p[i]) == 0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False 
                if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
    # Screen
    s_idx={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize_grade(inputs_s[k]) == 0:
            ph = st.session_state.p3.iloc[s_idx[k]]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
    # Extras
    for cell in extras:
        if normalize_grade(cell['res']) == 0:
            for ag in AGS:
                if cell['ph'].get(ag,0)==1: ruled_out.add(ag)

    candidates = [x for x in AGS if x not in ruled_out]
    display_cands = [x for x in candidates if x not in IGNORED_AGS]
    
    is_D = "D" in display_cands
    final_list = []
    notes = []
    for c in display_cands:
        if is_D and (c=="C" or c=="E"): continue 
        final_list.append(c)
        
    if is_D: notes.append("anti-D_mask")
    if "c" in final_list: notes.append("anti-c_risk")
    
    return final_list, notes

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

# 5. UI SIDEBAR
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png",width=60)
    nav=st.radio("Mode",["Workstation","Supervisor"])
    if st.button("RESET DATA"): st.session_state.ext=[]; st.rerun()

# ADMIN
if nav == "Supervisor":
    st.title("Admin Panel")
    if st.text_input("Pwd",type="password")=="admin123":
        st.session_state.lot = st.text_input("Lot No:", value=st.session_state.lot)
        t1,t2=st.tabs(["Panel","Screen"])
        with t1:
            txt1=st.text_area("Paste P11", height=150)
            if st.button("Save P11"): 
                df,m = parse_paste(txt1,11)
                if df is not None: st.session_state.p11=df; st.success(m)
            st.dataframe(st.session_state.p11)
        with t2:
            txt2=st.text_area("Paste S3", height=100)
            if st.button("Save S3"):
                df,m = parse_paste(txt2,3)
                if df is not None: st.session_state.p3=df; st.success(m)
            st.dataframe(st.session_state.p3)

# USER
else:
    st.markdown(f"""<div class='hospital-logo'><h2>Maternity & Children Hospital - Tabuk</h2><div class='lot-badge'>Active Lot: {st.session_state.lot}</div></div>""", unsafe_allow_html=True)
    
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Pt Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()

    with st.form("main"):
        L, R = st.columns([1, 2])
        with L:
            st.write("Controls")
            ac_res = st.radio("Auto Control", ["Negative", "Positive"])
            s1=st.selectbox("Scn I",GRADES)
            s2=st.selectbox("Scn II",GRADES)
            s3=st.selectbox("Scn III",GRADES)
        with R:
            st.write("Panel Reactions")
            g1,g2=st.columns(2)
            with g1:
                c1=st.selectbox("1",GRADES,key="k1"); c2=st.selectbox("2",GRADES,key="k2"); c3=st.selectbox("3",GRADES,key="k3")
                c4=st.selectbox("4",GRADES,key="k4"); c5=st.selectbox("5",GRADES,key="k5"); c6=st.selectbox("6",GRADES,key="k6")
            with g2:
                c7=st.selectbox("7",GRADES,key="k7"); c8=st.selectbox("8",GRADES,key="k8"); c9=st.selectbox("9",GRADES,key="k9")
                c10=st.selectbox("10",GRADES,key="k10"); c11=st.selectbox("11",GRADES,key="k11")
        
        submit = st.form_submit_button("🚀 Run Analysis")
    
    if submit:
        if ac_res == "Positive":
             st.markdown("""<div class='logic-critical'>🚨 Auto-Control POSITIVE - Perform DAT Workup</div>""", unsafe_allow_html=True)
             st.session_state.show_dat = True
        else:
            st.session_state.show_dat = False
            ip = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
            IS = {"I":s1, "II":s2, "III":s3}
            pos = sum([normalize_grade(x) for x in ip.values()])
            
            if pos == 11:
                st.markdown("""<div class='clinical-high-freq'>⚠️ Pan-Reactivity (High Freq Antigen). Refer Sample.</div>""", unsafe_allow_html=True)
            else:
                final, notes = analyze_master_logic(ip, IS, st.session_state.ext)
                
                real = [x for x in final if x not in INSIGNIFICANT_AGS]
                cold = [x for x in final if x in INSIGNIFICANT_AGS]
                
                st.subheader("Results")
                if not real and not cold: st.error("No matches found.")
                else:
                    if real: st.success(f"**Identified:** Anti-{', '.join(real)}")
                    if cold: st.info(f"**Other:** Anti-{', '.join(cold)} (Insignificant)")
                    
                    if "anti-D_mask" in notes: st.caption("Note: Anti-C/E masked by Anti-D")
                    if "anti-c_risk" in notes: st.warning("⚠️ Give R1R1 Units (Anti-c present)")
                    
                    # ---------------- VALIDATION ----------------
                    valid = True
                    for ab in (real+cold):
                        ok, p, n = check_p_val(ab, ip, IS, st.session_state.ext)
                        sty = "logic-pass" if ok else "logic-critical"
                        msg = "Confirmed" if ok else "NOT Confirmed"
                        st.markdown(f"<div class='{sty}'><b>Anti-{ab}:</b> {msg} (P={p}/N={n})</div>", unsafe_allow_html=True)
                        if not ok: valid=False
                    
                    # ---------------- STRATEGY WITH SUGGESTIONS (V207 NEW) ----------------
                    if len(real) > 1:
                        st.markdown("#### 🔬 Smart Strategy")
                        for t in real:
                            conflicts = [x for x in real if x!=t]
                            
                            # SEARCH INVENTORY FOR MATCH
                            matches_in_stock = find_matching_cells_in_inventory(t, conflicts)
                            
                            if matches_in_stock:
                                sugg = f"<span class='cell-suggest'>✅ USE: {', '.join(matches_in_stock)}</span>"
                            else:
                                sugg = "<span style='color:#b71c1c; font-size:0.9em'>(Not found in current panel/screen - Search Library)</span>"
                                
                            st.markdown(f"""
                            <div class='strategy-box'>
                                To confirm <b>Anti-{t}</b>: Select Cell <b>{t}+</b> / <b>{'&'.join([x+'-' for x in conflicts])}</b><br>
                                {sugg}
                            </div>
                            """, unsafe_allow_html=True)
                            
                    if valid and real:
                        if st.button("🖨️ Report"):
                            h=f"""<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='result-sheet'><b>Pt:</b> {nm} ({mr})<br><b>Tech:</b> {tc}<hr><b>Conclusion:</b> Anti-{', '.join(real)} Detected.<br>Probability Confirmed.<br>Note: Phenotype Negative.<br><br>Sig: __________</div><div style='position:fixed;bottom:0;text-align:center'>Dr. Haitham Ismail</div></div><script>window.print()</script>"""
                            st.markdown(h, unsafe_allow_html=True)

    # DAT
    if st.session_state.get('show_dat', False):
        st.write("---")
        with st.container(border=True):
            d1,d2,d3=st.columns(3)
            ri=d1.selectbox("IgG",["Neg","Pos"]); rc=d2.selectbox("C3d",["Neg","Pos"]); rt=d3.selectbox("Ctrl",["Neg","Pos"])
            if rt=="Pos": st.error("Invalid")
            elif ri=="Pos": st.warning("WAIHA / DHTR (Adsorption Required)")
            elif rc=="Pos": st.info("CAS (Pre-warm)")
    
    # ADD CELLS
    with st.expander("➕ Add Selected Cell"):
        i1,i2=st.columns(2)
        cid=i1.text_input("Lot#"); crs=i2.selectbox("Res",GRADES)
        pres=st.multiselect("Pos Antigens:", AGS)
        if st.button("Add"):
            ph={a:1 if a in pres else 0 for a in AGS}
            st.session_state.ext.append({"id":cid,"res":normalize_grade(crs),"res_txt":crs,"ph":ph})
            st.success("Added! Run Analysis.")

    if st.session_state.ext: st.table(pd.DataFrame(st.session_state.ext)[['id','res_txt']])
