import streamlit as st
import pandas as pd
import io

# 1. SETUP
st.set_page_config(page_title="Tabuk Serology", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .print-only { display: block !important; } .result-box { border: 2px solid #000; padding: 20px; } }
    .print-only { display: none; }
    
    .status-alert { background: #ffebee; border-left: 5px solid #c62828; padding: 15px; color: #b71c1c; margin-bottom: 10px;}
    .status-warn { background: #fff3cd; border-left: 5px solid #ffc107; padding: 15px; color: #856404; margin-bottom: 10px;}
    .status-ok { background: #d4edda; border-left: 5px solid #198754; padding: 15px; color: #155724; margin-bottom: 10px;}
    
    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div style='position:fixed;bottom:5px;right:5px;background:white;z-index:99;padding:5px;border:1px solid #ccc' class='no-print'><b>Dr. Haitham Ismail</b> | Consultant</div>", unsafe_allow_html=True)

# 2. STATE & DEFS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}
IGNORED = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
COLD = ["Lea", "Leb", "Lua", "P1"]

# Initialize Persistent State
if 'setup_done' not in st.session_state:
    st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
    st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
    st.session_state.lot_p = ""
    st.session_state.lot_s = ""
    st.session_state.ext = []
    # THIS IS THE FIX: A flag to keep analysis open
    st.session_state.analysis_active = False 
    st.session_state.inputs_p = {}
    st.session_state.inputs_s = {}
    st.session_state.ac = "Negative"
    st.session_state.setup_done = True

# 3. LOGIC
def normalize(val):
    return 1 if any(x in str(val).lower() for x in ['+','1','pos','w']) else 0

def parse_paste(txt, limit):
    try:
        rows = txt.strip().split('\n')
        data = []
        c = 0
        for line in rows:
            if c>=limit: break
            parts = line.split('\t')
            row = []
            for p in parts:
                v = 1 if any(x in str(p).lower() for x in ['+','1','pos','w']) else 0
                row.append(v)
            if len(row)>26: row=row[-26:]
            while len(row)<26: row.append(0)
            d={"ID": f"C{c+1}" if limit==11 else f"Scn"}
            for i, a in enumerate(AGS): d[a]=row[i]
            data.append(d); c+=1
        return pd.DataFrame(data), f"Updated {c} rows."
    except: return None, "Error"

def solve_logic(ip, iscr, ext):
    ruled = set()
    # Exclude
    for i in range(1,12):
        if normalize(ip[i])==0:
            ph=st.session_state.p11.iloc[i-1]
            for a in AGS:
                safe=True
                if a in DOSAGE and ph.get(PAIRS[a],0)==1: safe=False
                if ph.get(a,0)==1 and safe: ruled.add(a)
    for i,k in enumerate(["I","II","III"]):
        if normalize(iscr[k])==0:
            ph=st.session_state.p3.iloc[i]
            for a in AGS:
                if a not in ruled:
                    safe=True
                    if a in DOSAGE and ph.get(PAIRS[a],0)==1: safe=False
                    if ph.get(a,0)==1 and safe: ruled.add(a)
    for x in ext:
        if normalize(x['r'])==0:
            for a in AGS: 
                if x['ph'].get(a,0)==1: ruled.add(a)
    
    # Match & Score
    cands = [x for x in AGS if x not in ruled and x not in IGNORED]
    scores = []
    for c in cands:
        hits = 0; miss = 0
        # P11
        for i in range(1,12):
            s=normalize(ip[i]); h=st.session_state.p11.iloc[i-1].get(c,0)
            if s==1 and h==1: hits+=1
            if s==1 and h==0: miss+=1
        # S3
        for i,k in enumerate(["I","II","III"]):
            s=normalize(iscr[k]); h=st.session_state.p3.iloc[i].get(c,0)
            if s==1 and h==1: hits+=1
            if s==1 and h==0: miss+=1
        
        # Rank by Least Mismatches (Solves P1 vs C)
        score = hits - (miss * 5)
        scores.append({"Ab":c, "S":score, "M":miss, "H":hits})
    
    scores.sort(key=lambda x: x['S'], reverse=True)
    return scores

# 4. UI
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png",width=60)
    nav=st.radio("Menu",["Workstation","Admin"])
    if st.button("RESET / NEW"): 
        st.session_state.analysis_active = False
        st.session_state.ext = []
        st.rerun()

# --- ADMIN ---
if nav=="Admin":
    st.title("Admin")
    if st.text_input("Password",type="password")=="admin123":
        c1,c2=st.columns(2)
        lp=c1.text_input("Panel Lot", value=st.session_state.lot_p)
        ls=c2.text_input("Screen Lot", value=st.session_state.lot_s)
        if st.button("Save Lots"): st.session_state.lot_p=lp; st.session_state.lot_s=ls; st.success("OK"); st.rerun()
        
        t1,t2=st.tabs(["P11","S3"])
        with t1:
            tx=st.text_area("Paste P11 Data", height=150)
            if st.button("Upd P11"):
                d,m=parse_paste(tx,11)
                if d is not None: st.session_state.p11=d; st.success(m)
            st.dataframe(st.session_state.p11)
        with t2:
            tx2=st.text_area("Paste S3", height=100)
            if st.button("Upd Scr"):
                d,m=parse_paste(tx2,3)
                if d is not None: st.session_state.p3=d; st.success(m)
            st.dataframe(st.session_state.p3)

# --- USER ---
else:
    # Header
    st.markdown(f"<div style='text-align:center;border-bottom:5px solid #800;color:#003366'><h2>Maternity & Children Hospital - Tabuk</h2><h4>Lot P: {st.session_state.lot_p} | S: {st.session_state.lot_s}</h4></div>",unsafe_allow_html=True)
    if not st.session_state.lot_p or not st.session_state.lot_s: st.error("Locked. Ask Admin."); st.stop()
    
    # 1. FORM (Data Entry Only)
    with st.form("entry"):
        st.subheader("Data Entry")
        L,R=st.columns([1,2])
        with L:
            ac_res=st.radio("AC", ["Negative","Positive"])
            s1=st.selectbox("Scn I", ["Neg","Pos","w+","2+"]); s2=st.selectbox("Scn II", ["Neg","Pos","w+","2+"]); s3=st.selectbox("Scn III", ["Neg","Pos","w+","2+"])
        with R:
            g1,g2=st.columns(2)
            p_res = {}
            for i in range(1,7): p_res[i]=g1.selectbox(f"{i}",["Neg","Pos","w+","2+"])
            for i in range(7,12): p_res[i]=g2.selectbox(f"{i}",["Neg","Pos","w+","2+"])
        
        run = st.form_submit_button("🚀 ANALYZE")
        
    if run:
        st.session_state.analysis_active = True
        st.session_state.inputs_p = p_res
        st.session_state.inputs_s = {"I":s1,"II":s2,"III":s3}
        st.session_state.ac = ac_res
    
    # 2. ANALYSIS RESULTS (OUTSIDE FORM -> DOES NOT VANISH ON UPDATE)
    if st.session_state.analysis_active:
        st.write("---")
        st.subheader("Interpretation Phase")
        
        in_p = st.session_state.inputs_p
        in_s = st.session_state.inputs_s
        pos_cnt = sum([normalize(v) for v in in_p.values()]) + sum([normalize(v) for v in in_s.values()])
        
        # A. AUTO CONTROL POSITIVE
        if st.session_state.ac == "Positive":
            st.markdown("<div class='status-alert'><h3>🚨 Auto Control POSITIVE</h3>Logic Suspended. Please complete DAT Workup below.</div>", unsafe_allow_html=True)
            if pos_cnt >= 13: # Pan-reactive
                st.warning("⚠️ Critical: Pan-Agglutination + AC Positive. Suspect **DHTR** if recently transfused.")
            
            # --- INTERACTIVE DAT (WILL NOT DISAPPEAR NOW) ---
            with st.container(border=True):
                c1,c2,c3 = st.columns(3)
                ig = c1.selectbox("IgG Result", ["Neg", "Pos"], key="dat_igg") # Key is vital
                c3 = c2.selectbox("C3d Result", ["Neg", "Pos"], key="dat_c3d")
                ct = c3.selectbox("Control", ["Neg", "Pos"], key="dat_ctrl")
                
                st.write("**Analysis:**")
                if ct=="Pos": st.error("Invalid Test.")
                elif ig=="Pos": st.error("👉 Probable **WAIHA**. If transfused, **DHTR** possible. Do Elution.")
                elif c3=="Pos": st.info("👉 Probable **CAS** (Cold Agglutinin). Use Pre-warm.")

        # B. HIGH FREQ
        elif pos_cnt >= 13:
             st.markdown("<div class='status-warn'><h3>⚠️ High Incidence Antigen</h3>Pan-reactivity with Neg Auto.</div>",unsafe_allow_html=True)
             
        # C. ALLO LOGIC
        else:
            final_data, ruled = solve_logic(in_p, in_s, st.session_state.ext)
            
            # Filters
            # Anti-D Silent Mask
            final = []
            is_D_top = (len(final_data)>0 and final_data[0]['Ab'] == "D" and final_data[0]['M'] == 0)
            
            # Anti-G Check (1,2,3,4,8 Pos)
            g_check_idx = [1,2,3,4,8]
            g_pos_count = sum([1 for i in g_check_idx if normalize(in_p[i])==1])
            is_G_likely = (g_pos_count == 5)
            
            for res in final_data:
                nm = res['Ab']
                if res['S'] < 0: continue # Skip bad matches
                
                # If D is confirmed
                if is_D_top:
                    if nm in ["C","E"]: 
                        if nm=="C" and is_G_likely: pass # Keep C if G suspect
                        else: continue # Mask
                final.append(nm)

            real = [x for x in final if x not in COLD]
            cold = [x for x in final if x in COLD]

            if not real and not cold:
                st.error("No clear match found.")
            else:
                if is_G_likely and "D" in real and "C" in real:
                    st.warning("⚠️ **Suspect Anti-G (or D+C).** Pattern matches.")
                
                if real: st.success(f"**Identified:** Anti-{', '.join(real)}")
                if cold: st.info(f"Cold/Insig: Anti-{', '.join(cold)}")
                if "c" in real: st.error("🛑 **Anti-c Warning:** Transfuse R1R1 Units.")
                
                st.write("**Validation (Rule of 3):**")
                valid_all = True
                
                for ab in (real+cold):
                    # Recalc P/N for display
                    p, n = 0, 0
                    for i in range(1,12):
                        s=normalize(in_p[i]); h=st.session_state.p11.iloc[i-1].get(ab,0)
                        if s==1 and h==1: p+=1; 
                        if s==0 and h==0: n+=1
                    # Extras logic
                    for x in st.session_state.ext:
                        if x['s']==1 and x['ph'].get(ab,0)==1: p+=1
                        if x['s']==0 and x['ph'].get(ab,0)==0: n+=1
                    
                    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
                    msg = "Met" if ok else "Unconfirmed"
                    icon = "✅" if ok else "⚠️"
                    st.write(f"{icon} Anti-{ab}: {msg} (P:{p}/N:{n})")
                    if not ok: valid_all = False
                
                if not valid_all:
                    st.warning("Need Confirmation. Use Cell Search Below:")
                    # Helper for Finding Cells
                    for t in real:
                        others = [o for o in real if o!=t]
                        # Scan Panel
                        fnd=[]
                        for i in range(11):
                            cl=st.session_state.p11.iloc[i]
                            if cl.get(t)==1 and all(cl.get(o)==0 for o in others): fnd.append(f"C{i+1}")
                        st.caption(f"- To confirm **{t}** (and rule out {others}): Found {fnd if fnd else 'None (Check Library)'}")

    # EXTRA CELL TOOL (PERSISTENT)
    if st.session_state.analysis_active and st.session_state.ac == "Negative":
        st.write("---")
        with st.expander("➕ Add Selected Cell (From Library)"):
            c1,c2=st.columns(2)
            eid=c1.text_input("ID")
            ers=c2.selectbox("Res", ["Neg","Pos"], key="ext_res")
            st.write("Antigens Pos:")
            cc=st.columns(8); new_ph={}
            for i,ag in enumerate(AGS): 
                if cc[i%8].checkbox(ag, key=f"x_{ag}"): new_ph[ag]=1 
                else: new_ph[ag]=0
            if st.button("Add Cell"):
                st.session_state.ext.append({"id":eid,"s":1 if ers=="Pos" else 0,"ph":new_ph, "res":ers})
                st.success("Added! Please click Run Analysis again."); st.rerun()

        if st.session_state.ext: st.table(pd.DataFrame(st.session_state.ext)[['id','res']])
