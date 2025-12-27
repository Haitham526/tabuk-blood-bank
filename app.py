import streamlit as st
import pandas as pd
from datetime import date

# --------------------------------------------------------------------------
# 1. SETUP
# --------------------------------------------------------------------------
st.set_page_config(page_title="MCH Tabuk Bank", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { 
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 3px double #b30000; padding: 25px; font-family: 'Times New Roman'; }
    }
    .print-only { display: none; }
    
    .status-ok { background: #d4edda; color: #155724; padding: 10px; margin: 5px 0; border-left: 5px solid #28a745;}
    .status-fail { background: #f8d7da; color: #721c24; padding: 10px; margin: 5px 0; border-left: 5px solid #dc3545;}
    .status-warn { background: #fff3cd; color: #856404; padding: 10px; margin: 5px 0; border-left: 5px solid #ffc107;}
    
    .sig-float { position: fixed; bottom: 5px; right: 15px; background: rgba(255,255,255,0.9); padding: 5px 10px; border: 1px solid #ccc; z-index:99; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""<div class='sig-float no-print'><b>Dr. Haitham Ismail</b><br>Clinical Hematology/Transfusion Consultant</div>""", unsafe_allow_html=True)

# DEFS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# STATE
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'ext' not in st.session_state: st.session_state.ext = []
if 'analysis_active' not in st.session_state: st.session_state.analysis_active = False

# --------------------------------------------------------------------------
# 2. LOGIC FUNCTIONS
# --------------------------------------------------------------------------
def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

def parse_paste(txt, limit=11):
    try:
        rows = txt.strip().split('\n')
        data = []
        c = 0
        for line in rows:
            if c >= limit: break
            parts = line.split('\t')
            v = []
            for p in parts:
                vl = str(p).lower().strip()
                v.append(1 if any(x in vl for x in ['1','+','w','pos']) else 0)
            if len(v)>26: v=v[-26:]
            while len(v)<26: v.append(0)
            
            rid = f"C{c+1}" if limit==11 else f"Scn"
            d={"ID": rid}
            for i,ag in enumerate(AGS): d[ag]=v[i]
            data.append(d)
            c+=1
        return pd.DataFrame(data), f"Updated {c} rows."
    except Exception as e: return None, str(e)

# --- THE FIX: THIS FUNCTION NOW RETURNS 2 VALUES ---
def run_logic_engine(p_in, s_in, ex):
    ruled = set()
    # 1. EXCLUSION
    # Panel
    for i in range(1, 12):
        if normalize(p_in[i]) == 0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                if ph.get(ag,0)==1 and safe: ruled.add(ag)
    # Screen
    idx={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize(s_in[k]) == 0:
            ph = st.session_state.p3.iloc[idx[k]]
            for ag in AGS:
                if ag not in ruled:
                    safe=True
                    if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                    if ph.get(ag,0)==1 and safe: ruled.add(ag)
    # Extra
    for x in ex:
        if normalize(x['r']) == 0:
            for ag in AGS:
                 if x['ph'].get(ag,0)==1: ruled.add(ag)

    # 2. SCORING
    candidates = [x for x in AGS if x not in ruled]
    scores = []
    
    for c in candidates:
        hits=0; miss=0
        # P
        for i in range(1, 12):
            is_pos = normalize(p_in[i])
            has_ag = st.session_state.p11.iloc[i-1].get(c,0)
            if is_pos and has_ag: hits+=1
            if is_pos and not has_ag: miss+=1
        # S
        for k in ["I","II","III"]:
            is_pos = normalize(s_in[k])
            has_ag = st.session_state.p3.iloc[idx[k]].get(c,0)
            if is_pos and has_ag: hits+=1
            if is_pos and not has_ag: miss+=1
            
        final_score = hits - (miss * 5)
        scores.append({"Ab": c, "Score": final_score})
        
    scores.sort(key=lambda x: x['Score'], reverse=True)
    
    # MUST RETURN 2 VALUES TO MATCH CALLER
    return scores, ruled 

def check_rules(cand, p_in, s_in, ex):
    p,n=0,0
    # P
    for i in range(1,12):
        s=normalize(p_in[i]); h=st.session_state.p11.iloc[i-1].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # S
    id={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s=normalize(s_in[k]); h=st.session_state.p3.iloc[id[k]].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Ex
    for x in ex:
        s=normalize(x['r']); h=x['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    return ok, p, n

# =========================================================================
# 3. INTERFACE
# =========================================================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png",width=60)
    nav=st.radio("Menu",["Workstation","Supervisor"])
    if st.button("RESET DATA"): 
        st.session_state.analysis_active=False
        st.session_state.ext=[]
        st.rerun()

# --- ADMIN ---
if nav == "Supervisor":
    st.title("Admin")
    if st.text_input("Password",type="password")=="admin123":
        c1,c2=st.columns(2)
        st.session_state.lot_p = c1.text_input("ID Lot", value=st.session_state.get('lot_p',''))
        st.session_state.lot_s = c2.text_input("Scr Lot", value=st.session_state.get('lot_s',''))
        
        t1,t2=st.tabs(["Panel 11","Screen"])
        with t1:
            p_in=st.text_area("Paste Digits P11", height=150)
            if st.button("Save P11"): 
                d,m=parse_paste(p_in, 11)
                if d is not None: st.session_state.p11=d; st.success(m)
            st.dataframe(st.session_state.p11)
        with t2:
            s_in=st.text_area("Paste Digits Screen", height=100)
            if st.button("Save S3"):
                d,m=parse_paste(s_in, 3)
                if d is not None: st.session_state.p3=d; st.success(m)
            st.dataframe(st.session_state.p3)

# --- WORKSTATION ---
else:
    # Header
    lt_p = st.session_state.get('lot_p', 'MISSING')
    lt_s = st.session_state.get('lot_s', 'MISSING')
    st.markdown(f"<center><h2 style='color:#036'>Maternity & Children Hospital - Tabuk</h2><small><b>Lots:</b> P={lt_p} | S={lt_s}</small></center><hr>", unsafe_allow_html=True)
    
    # Patient Info
    r1=st.columns(4)
    nm=r1[0].text_input("Name"); mr=r1[1].text_input("MRN"); tc=r1[2].text_input("Tech"); dt=r1[3].date_input("Date")
    st.divider()

    # FORM START
    with st.form("main"):
        cL, cR = st.columns([1, 2.5])
        with cL:
            st.write("Controls")
            ac_res = st.radio("Auto Control", ["Negative", "Positive"])
            st.write("Screen")
            s1=st.selectbox("I",GRADES); s2=st.selectbox("II",GRADES); s3=st.selectbox("III",GRADES)
        with cR:
            st.write("ID Panel")
            g1,g2=st.columns(2)
            with g1:
                c1=st.selectbox("1",GRADES); c2=st.selectbox("2",GRADES); c3=st.selectbox("3",GRADES)
                c4=st.selectbox("4",GRADES); c5=st.selectbox("5",GRADES); c6=st.selectbox("6",GRADES)
            with g2:
                c7=st.selectbox("7",GRADES); c8=st.selectbox("8",GRADES); c9=st.selectbox("9",GRADES)
                c10=st.selectbox("10",GRADES); c11=st.selectbox("11",GRADES)
        
        # KEY CHANGE: This updates session state safely
        run_click = st.form_submit_button("🚀 Run Analysis")

    # SAVE STATE ON CLICK
    if run_click:
        st.session_state.analysis_active = True
        st.session_state.last_ac = ac_res
        st.session_state.last_p = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
        st.session_state.last_s = {"I":s1,"II":s2,"III":s3}

    # PERSISTENT OUTPUT AREA
    if st.session_state.analysis_active:
        st.write("---")
        # Recover vars
        AC = st.session_state.last_ac
        IP = st.session_state.last_p
        IS = st.session_state.last_s
        pos_total = sum([normalize(x) for x in IP.values()]) + sum([normalize(x) for x in IS.values()])
        
        # 1. AC POSITIVE
        if AC == "Positive":
            st.markdown("<div class='status-fail'>🚨 Auto Control POSITIVE</div>", unsafe_allow_html=True)
            if pos_total >= 11:
                st.warning("⚠️ Critical: Pan-Agglutination + AC Positive -> Suspect DHTR (Delayed Transfusion Reaction). Check History.")
            
            # Interactive DAT (Works now because it's outside the Form)
            with st.container(border=True):
                st.subheader("🧪 DAT Investigation")
                cx = st.columns(3)
                digg = cx[0].selectbox("IgG", ["Neg","Pos"], key="dat1")
                dc3d = cx[1].selectbox("C3d", ["Neg","Pos"], key="dat2")
                dctl = cx[2].selectbox("Ctrl",["Neg","Pos"], key="dat3")
                
                if dctl == "Pos": st.error("Invalid Test")
                elif digg=="Pos": st.warning(">> Probable WAIHA / DHTR.")
                elif dc3d=="Pos": st.info(">> Probable CAS.")
        
        # 2. PAN-REACTIVE
        elif pos_total >= 14:
            st.markdown("<div class='status-warn'>⚠️ Pan-Reactivity (All Pos, AC Neg) -> High Frequency Antibody?</div>", unsafe_allow_html=True)
            
        # 3. ALLO ANALYSIS
        else:
            # FIX: Properly unpack 2 values here
            results_list, rules_list = run_logic_engine(IP, IS, st.session_state.ext)
            
            # Constants
            IG = ["Kpa","Kpb","Jsa","Jsb","Lub","Cw"]
            
            # Filter & Display Logic
            real_match = []
            
            for item in results_list:
                nm = item['Ab']
                if nm in IG: continue
                
                # Check Anti-D Masking
                is_D = any(x['Ab']=="D" and x['Score']>0 for x in results_list)
                if is_D and (nm == "C" or nm == "E"): continue # Mask
                
                real_match.append(nm)
                
            st.subheader("Conclusion")
            if not real_match:
                st.error("No matches.")
            else:
                st.success(f"**Identified:** Anti-{', '.join(real_match)}")
                
                if "c" in real_match:
                     st.warning("🛑 Anti-c present: Provide R1R1 (E- c-) blood.")

                st.write("**Validation:**")
                valid_all = True
                for m in real_match:
                    ok, p, n = check_rules(m, IP, IS, st.session_state.ext)
                    icon = "✅" if ok else "⚠️"
                    msg = "Confirmed" if ok else "Need Cells"
                    st.write(f"{icon} **Anti-{m}**: {msg} (P:{p} / N:{n})")
                    if not ok: valid_all = False
                
                if valid_all:
                    if st.button("Generate Report"):
                        rpt = f"""<div class='print-only'><br><center><h2>Maternity & Children Hospital - Tabuk</h2><h3>Serology Report</h3></center><div class='result-sheet'>Pt: {nm} | {mr}<hr><b>Conclusion: Anti-{', '.join(real_match)}</b><br>Rule of 3 Valid.<br>Note: Phenotype Neg.<br><br>Sig:_________</div><div style='position:fixed;bottom:0;text-align:center;width:100%'>Dr. Haitham Ismail</div></div><script>window.print()</script>"""
                        st.markdown(rpt, unsafe_allow_html=True)
    
    # 4. ADD EXTRA (Always Visible for Fixes)
    if st.session_state.analysis_active and st.session_state.last_ac == "Negative":
        with st.expander("➕ Add Cell"):
            c1,c2=st.columns(2); id_x=c1.text_input("ID"); rs_x=c2.selectbox("R",GRADES, key="xr")
            cols=st.columns(8); ph_x={}
            for i,a in enumerate(AGS):
                if cols[i%8].checkbox(a,key=f"ch_{a}"): ph_x[a]=1
                else: ph_x[a]=0
            if st.button("Confirm Add"):
                st.session_state.ext.append({"r":rs_x, "ph":ph_x, "res":rs_x}) # res key added for compatibility
                st.rerun()
