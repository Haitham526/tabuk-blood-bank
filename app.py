import streamlit as st
import pandas as pd
from datetime import date

# ==========================================
# 1. SETUP & STYLE
# ==========================================
st.set_page_config(page_title="Tabuk Blood Bank", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { 
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 4px double #8B0000; padding: 30px; font-family: 'Times New Roman'; font-size:14px;}
        .footer-sig { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; font-weight:bold;}
    }
    .print-only { display: none; }
    
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    .hospital-logo { color: #800000; text-align: center; border-bottom: 5px solid #800000; font-family: 'Arial'; padding-bottom: 5px; }
    
    /* Logic Status Boxes */
    .status-confirmed { background-color: #d1e7dd; padding: 12px; border-radius: 5px; border-left: 6px solid #198754; color: #0f5132; margin-bottom: 5px; }
    .status-warning { background-color: #fff3cd; padding: 12px; border-radius: 5px; border-left: 6px solid #ffc107; color: #856404; margin-bottom: 5px; }
    .status-critical { background-color: #f8d7da; padding: 12px; border-radius: 5px; border-left: 6px solid #dc3545; color: #842029; margin-bottom: 5px; }
    .status-info { background-color: #e2e3e5; padding: 10px; border-radius: 5px; border-left: 6px solid #6c757d; color: #383d41; font-style: italic; }

    .dr-float { position: fixed; bottom: 10px; right: 15px; background: rgba(255,255,255,0.9); padding: 5px 10px; border: 1px solid #ccc; z-index:99; box-shadow: 2px 2px 5px #ccc;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class='dr-float no-print'>
    <b>Dr. Haitham Ismail</b><br>
    <small>Clinical Hematology & Transfusion Consultant</small>
</div>
""", unsafe_allow_html=True)

# 2. DEFINITIONS (MISSING PART FIXED)
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# ** FIXED: Grades Definition Added **
GRADES = ["Negative", "w+", "+1", "+2", "+3", "+4", "Hemolysis"]

IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
INSIGNIFICANT_AGS = ["Lea", "Leb", "Lua", "P1"]

# 3. STATE
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'ext' not in st.session_state: st.session_state.ext = []
# DAT & Input State Persistence
if 'run_analysis' not in st.session_state: st.session_state.run_analysis = False
if 'last_inputs_p' not in st.session_state: st.session_state.last_inputs_p = {}
if 'last_inputs_s' not in st.session_state: st.session_state.last_inputs_s = {}
if 'last_ac' not in st.session_state: st.session_state.last_ac = "Negative"
if 'lot_p' not in st.session_state: st.session_state.lot_p = ""
if 'lot_s' not in st.session_state: st.session_state.lot_s = ""


# 4. LOGIC ENGINE
def normalize(val):
    s = str(val).lower().strip()
    return 0 if s in ["0", "negative", "neg"] else 1

def parse_paste(txt, limit):
    try:
        rows = txt.strip().split('\n')
        data = []
        c=0
        for line in rows:
            if c >= limit: break
            parts = line.split('\t')
            vals = []
            for p in parts:
                v_clean = str(p).lower().strip()
                v = 1 if any(x in v_clean for x in ['+', '1', 'pos', 'w']) else 0
                vals.append(v)
            # Fix len
            if len(vals) > 26: vals=vals[-26:]
            while len(vals) < 26: vals.append(0)
            
            d={"ID": f"C{c+1}" if limit==11 else f"Scn"}
            for i,ag in enumerate(AGS): d[ag]=vals[i]
            data.append(d); c+=1
        return pd.DataFrame(data), f"Updated {c} rows."
    except Exception as e: return None, str(e)

def analyze_logic(p_in, s_in, extra):
    # Exclusion
    ruled = set()
    # Panel
    for i in range(1, 12):
        if normalize(p_in[i]) == 0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False 
                if ph.get(ag,0)==1 and safe: ruled.add(ag)
    # Screen
    s_idx={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize(s_in[k]) == 0:
            ph = st.session_state.p3.iloc[s_idx[k]]
            for ag in AGS:
                if ag not in ruled:
                    safe=True
                    if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                    if ph.get(ag,0)==1 and safe: ruled.add(ag)
    # Extra
    for ex in extra:
        if normalize(ex['res']) == 0:
            for ag in AGS:
                 if ex['ph'].get(ag,0)==1: ruled.add(ag)

    candidates = [x for x in AGS if x not in ruled]
    display_cands = [x for x in candidates if x not in IGNORED_AGS]
    
    # RANKING LOGIC (Points system to prioritize P1 over C in mismatch)
    scored = []
    for cand in display_cands:
        hits = 0
        miss = 0
        # Check P
        for i in range(1,12):
            is_pos = normalize(p_in[i])
            has_ag = st.session_state.p11.iloc[i-1].get(cand,0)
            if is_pos and has_ag: hits+=1
            if is_pos and not has_ag: miss+=1
        # Check S
        for k in ["I","II","III"]:
            is_pos = normalize(s_in[k])
            has_ag = st.session_state.p3.iloc[s_idx[k]].get(cand,0)
            if is_pos and has_ag: hits+=1
            if is_pos and not has_ag: miss+=1
            
        score = hits - (miss * 5)
        scored.append({"Ab": cand, "Score": score})
        
    scored.sort(key=lambda x: x['Score'], reverse=True)
    
    # Filter Anti-D masking silently
    final_list = []
    is_D = any(x['Ab']=="D" and x['Score']>0 for x in scored)
    
    for item in scored:
        cand = item['Ab']
        if item['Score'] < -5: continue # Remove impossible matches
        
        # Silent Masking Rule
        if is_D and (cand == "C" or cand == "E"):
            continue 
            
        final_list.append(cand)
        
    notes = []
    if "c" in final_list: notes.append("anti-c_risk")
    
    return final_list, notes

def check_r3(cand, in_p, in_s, extras):
    p, n = 0, 0
    # Panel
    for i in range(1, 12):
        s=normalize(in_p[i]); h=st.session_state.p11.iloc[i-1].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    s_idx = {"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s=normalize(in_s[k]); h=st.session_state.p3.iloc[s_idx[k]].get(cand, 0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extras
    for c in extras:
        s=normalize(c['res']); h=c['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    return ok, p, n

# Suggested Cells from Inventory
def get_suggestions(targets):
    msgs = []
    if len(targets) < 2: return msgs
    for t in targets:
        conflicts = [x for x in targets if x != t]
        # Find cell: T+ and Conflict-
        matches = []
        # P11
        for i in range(11):
            cl = st.session_state.p11.iloc[i]
            if cl.get(t)==1 and all(cl.get(x)==0 for x in conflicts): matches.append(f"Cell {i+1}")
        # S3
        for i, s in enumerate(["I","II","III"]):
            cl = st.session_state.p3.iloc[i]
            if cl.get(t)==1 and all(cl.get(x)==0 for x in conflicts): matches.append(f"Scn {s}")
            
        loc_txt = f"<b style='color:green'>{', '.join(matches)}</b>" if matches else "<b style='color:red'>None in stock (Search External)</b>"
        msgs.append(f"To Confirm <b>Anti-{t}</b>: Select cell ({t}+ / {' '.join(conflicts)}-) -> {loc_txt}")
    return msgs

# ==========================================
# 5. UI
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png",width=60)
    nav=st.radio("Mode",["Workstation","Supervisor"])
    if st.button("RESET DATA"): 
        st.session_state.ext=[]
        st.session_state.run_analysis=False
        st.rerun()

# --- ADMIN ---
if nav == "Supervisor":
    st.title("Admin")
    if st.text_input("Pwd",type="password")=="admin123":
        c1,c2=st.columns(2)
        st.session_state.lot_p = c1.text_input("Panel Lot", value=st.session_state.lot_p)
        st.session_state.lot_s = c2.text_input("Screen Lot", value=st.session_state.lot_s)
        
        t1,t2=st.tabs(["P11","S3"])
        with t1:
            if st.button("Save P11 from Text Area"):
                 d,m=parse_paste(st.session_state.txt_p11,11)
                 if d is not None: st.session_state.p11=d; st.success(m)
            st.session_state.txt_p11 = st.text_area("Paste Data P11", height=150)
            st.dataframe(st.session_state.p11.iloc[:,:15])
        with t2:
            if st.button("Save S3 from Text Area"):
                 d,m=parse_paste(st.session_state.txt_s3,3)
                 if d is not None: st.session_state.p3=d; st.success(m)
            st.session_state.txt_s3 = st.text_area("Paste Data Screen", height=100)
            st.dataframe(st.session_state.p3.iloc[:,:15])

# --- USER ---
else:
    st.markdown(f"""<div class='hospital-logo'><h2>Maternity & Children Hospital - Tabuk</h2><h4>Blood Bank Serology</h4><small>Lot ID: {st.session_state.lot_p}</small></div>""",unsafe_allow_html=True)
    
    # 1. INPUT FORM
    with st.form("main_form"):
        # Header Info
        c1,c2,c3,c4 = st.columns(4)
        nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
        st.divider()
        
        colL, colR = st.columns([1, 2])
        with colL:
            st.write("Controls")
            ac_res = st.radio("Auto Control", ["Negative","Positive"])
            st.write("Screening")
            s1=st.selectbox("Scn I",GRADES); s2=st.selectbox("Scn II",GRADES); s3=st.selectbox("Scn III",GRADES)
        with colR:
            st.write("Panel")
            g1,g2=st.columns(2)
            with g1:
                c1=st.selectbox("1",GRADES); c2=st.selectbox("2",GRADES); c3=st.selectbox("3",GRADES); c4=st.selectbox("4",GRADES); c5=st.selectbox("5",GRADES); c6=st.selectbox("6",GRADES)
            with g2:
                c7=st.selectbox("7",GRADES); c8=st.selectbox("8",GRADES); c9=st.selectbox("9",GRADES); c10=st.selectbox("10",GRADES); c11=st.selectbox("11",GRADES)
        
        run_btn = st.form_submit_button("🚀 Run Analysis")

    if run_btn:
        st.session_state.run_analysis = True
        st.session_state.last_ac = ac_res
        st.session_state.last_p = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
        st.session_state.last_s = {"I":s1,"II":s2,"III":s3}

    # 2. RESULT RENDERER (Persistent)
    if st.session_state.run_analysis:
        inp_p = st.session_state.last_p
        inp_s = st.session_state.last_s
        ac_val = st.session_state.last_ac
        pos_sum = sum([normalize(x) for x in inp_p.values()]) + sum([normalize(x) for x in inp_s.values()])
        
        # --- SCENARIO 1: AUTO POS ---
        if ac_val == "Positive":
            st.markdown("<div class='status-critical'>🚨 Auto Control POSITIVE</div>", unsafe_allow_html=True)
            if pos_sum >= 12:
                st.markdown("<div class='status-warning'>⚠️ Pan-agglutination + AC(+) -> Check <b>DHTR</b>. Perform Elution.</div>", unsafe_allow_html=True)
            
            st.subheader("🧪 Monospecific DAT Workup")
            with st.container(border=True):
                d1,d2,d3 = st.columns(3)
                ig=d1.selectbox("IgG", ["Negative","Positive"]); c3=d2.selectbox("C3d", ["Negative","Positive"]); ct=d3.selectbox("Control", ["Negative","Positive"])
                
                if ct=="Positive": st.error("Invalid Test")
                elif ig=="Positive": st.warning(">> Probable WAIHA / DHTR")
                elif c3=="Positive": st.info(">> Probable CAS (Pre-warm)")
        
        # --- SCENARIO 2: PAN (High Freq) ---
        elif pos_sum >= 13:
             st.markdown("<div class='status-warning'>⚠️ Pan-Reactivity (AC Neg) -> Suspect High Frequency Antibody.</div>", unsafe_allow_html=True)
             
        # --- SCENARIO 3: ALLO ---
        else:
             final_list, notes = calculate_expert_logic(inp_p, inp_s, st.session_state.ext)
             
             real = [x for x in final_list if x not in INSIGNIFICANT_AGS]
             cold = [x for x in final_list if x in INSIGNIFICANT_AGS]
             
             if not real and not cold:
                 st.error("Inconclusive.")
             else:
                 st.subheader("Interpretation")
                 
                 if "anti-c_risk" in notes:
                      st.markdown("<div class='status-critical'>🛑 Anti-c: Provide R1R1 (E- c-) Units.</div>", unsafe_allow_html=True)
                 
                 if real: st.success(f"**Identified:** Anti-{', '.join(real)}")
                 if cold: st.markdown(f"<div class='status-info'>Cold/Other: Anti-{', '.join(cold)}</div>", unsafe_allow_html=True)
                 
                 st.write("---")
                 
                 # VALIDATION & SUGGESTIONS
                 valid_all = True
                 
                 # Suggestions if multiple
                 if len(real) > 1:
                     sugs = get_suggestions(real)
                     for s in sugs: st.markdown(f"<div class='strategy-box'>{s}</div>", unsafe_allow_html=True)
                 
                 # P-Values
                 for ab in (real+cold):
                     ok, p, n = check_r3(ab, inp_p, inp_s, st.session_state.ext)
                     sty = "status-confirmed" if ok else "status-critical"
                     txt = "Rule Met (p≤0.05)" if ok else "NOT Confirmed"
                     st.markdown(f"<div class='{sty}'><b>Anti-{ab}:</b> {txt} ({p}P / {n}N)</div>", unsafe_allow_html=True)
                     if not ok: valid_all = False
                 
                 if valid_all and real:
                     if st.button("🖨️ Official Report"):
                         t = f"""<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='result-sheet'><b>Pt:</b> {nm}<hr><b>Conclusion: Anti-{', '.join(real)}</b><br>Rule of 3 Confirmed.<br>Phenotype Neg.<br><br>Sig:_________</div><div class='page-footer'>Dr. Haitham Ismail</div></div><script>window.print()</script>"""
                         st.markdown(t, unsafe_allow_html=True)
                         
    # EXTRA CELL TOOL (Only show if needed)
    if ac_val == "Negative":
        with st.expander("➕ Add Selected Cell (Input)"):
             i1, i2 = st.columns(2)
             idx = i1.text_input("Cell Lot")
             res = i2.selectbox("Res", GRADES, key="exr")
             st.write("Phenotype (+):")
             cols = st.columns(6); ph_x={}
             for i,a in enumerate(AGS):
                 if cols[i%6].checkbox(a): ph_x[a]=1
             if st.button("Add Cell"):
                 st.session_state.ext.append({"res":res, "ph":ph_x})
                 st.rerun()
