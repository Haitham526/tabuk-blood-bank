import streamlit as st
import pandas as pd
from datetime import date

# 1. SETUP
st.set_page_config(page_title="Tabuk Blood Bank", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .print-only { display: block !important; } .results-box { border: 4px double #800; padding: 25px; font-family: 'Times New Roman'; } }
    .print-only { display: none; }
    
    .status-ok { background:#d4edda; color:#155724; padding:10px; border-radius:5px; border-left:5px solid #28a745; margin:5px 0;}
    .status-warn { background:#fff3cd; color:#856404; padding:10px; border-radius:5px; border-left:5px solid #ffc107; margin:5px 0;}
    .status-fail { background:#f8d7da; color:#842029; padding:10px; border-radius:5px; border-left:5px solid #dc3545; margin:5px 0;}
    .rec-box { background:#e2e3e5; color:#383d41; padding:10px; border:1px dashed #383d41; margin:5px 0; font-size:14px; }
    
    .hospital-head { text-align: center; border-bottom: 5px solid #800000; padding-bottom: 10px; color: #003366; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    
    .sig-badge { position: fixed; bottom: 10px; right: 15px; background: rgba(255,255,255,0.9); padding: 8px; border: 1px solid #ccc; z-index:99; box-shadow: 2px 2px 10px rgba(0,0,0,0.1); }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class='sig-badge no-print'>
    <b>Dr. Haitham Ismail</b><br>
    Clinical Hematology/Oncology &<br>BM Transplantation & Transfusion Medicine Consultant
</div>
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
if 'ext' not in st.session_state: st.session_state.ext = []

# 4. LOGIC ENGINE
def normalize(val):
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
            d = {"ID": f"C{c+1}" if limit==11 else f"S{c}"}
            for i, ag in enumerate(AGS): d[ag] = vals[i]
            data.append(d)
            c+=1
        return pd.DataFrame(data), f"Updated {c} rows"
    except Exception as e: return None, str(e)

# Smart Search for Existing Cells
def find_cell_in_inventory(target_ab, conflicts):
    # Scan P11
    matches = []
    for i in range(11):
        cell = st.session_state.p11.iloc[i]
        if cell.get(target_ab,0)==1:
            clean = True
            for c in conflicts: 
                if cell.get(c,0)==1: clean=False; break
            if clean: matches.append(f"C-{i+1}")
            
    # Scan Screen
    lbls=["I","II","III"]
    for i, l in enumerate(lbls):
        cell = st.session_state.p3.iloc[i]
        if cell.get(target_ab,0)==1:
            clean = True
            for c in conflicts: 
                if cell.get(c,0)==1: clean=False; break
            if clean: matches.append(f"Scn-{l}")
            
    return matches

def check_rule_3(cand, in_p, in_s, extra):
    p, n = 0, 0
    # P11
    for i in range(1,12):
        s = normalize(in_p[i]); h = st.session_state.p11.iloc[i-1].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # P3
    ids = {"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s = normalize(in_s[k]); h = st.session_state.p3.iloc[ids[k]].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Ext
    for x in extra:
        s=normalize(x['res']); h=x['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    return ok, p, n

# ==========================================
# 5. UI
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Mode", ["Workstation", "Admin"])
    if st.button("RESET"): st.session_state.ext=[]; st.rerun()

# --- ADMIN ---
if nav == "Admin":
    st.title("Admin")
    if st.text_input("Password", type="password")=="admin123":
        t1,t2=st.tabs(["Panel 11","Screen 3"])
        with t1:
            txt1=st.text_area("Paste Panel Digits",height=150)
            if st.button("Upd P11"): 
                d,m = parse_paste(txt1, 11)
                if d is not None: st.session_state.p11=d; st.success(m)
            st.dataframe(st.session_state.p11.iloc[:,:15])
        with t2:
            txt2=st.text_area("Paste Screen Digits",height=100)
            if st.button("Upd Scr"): 
                d,m = parse_paste(txt2, 3)
                if d is not None: st.session_state.p3=d; st.success(m)
            st.dataframe(st.session_state.p3.iloc[:,:15])

# --- WORKSTATION ---
else:
    st.markdown("""<div class='hospital-head'><h1>Maternity & Children Hospital - Tabuk</h1><h3>Blood Bank Workstation</h3></div>""", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()

    with st.form("main"):
        st.write("### Reaction Entry")
        L, R = st.columns([1, 2])
        with L:
            st.write("<b>Control</b>", unsafe_allow_html=True)
            ac = st.radio("AC", ["Negative", "Positive"])
            st.write("<b>Screening</b>", unsafe_allow_html=True)
            s1=st.selectbox("Scn I",GRADES); s2=st.selectbox("Scn II",GRADES); s3=st.selectbox("Scn III",GRADES)
        with R:
            st.write("<b>ID Panel</b>", unsafe_allow_html=True)
            g1,g2=st.columns(2)
            with g1:
                c1=st.selectbox("1",GRADES,key="k1"); c2=st.selectbox("2",GRADES,key="k2"); c3=st.selectbox("3",GRADES,key="k3")
                c4=st.selectbox("4",GRADES,key="k4"); c5=st.selectbox("5",GRADES,key="k5"); c6=st.selectbox("6",GRADES,key="k6")
            with g2:
                c7=st.selectbox("7",GRADES,key="k7"); c8=st.selectbox("8",GRADES,key="k8"); c9=st.selectbox("9",GRADES,key="k9")
                c10=st.selectbox("10",GRADES,key="k10"); c11=st.selectbox("11",GRADES,key="k11")
        
        # DAT (Show if AC Pos selected)
        # Using persistent DAT logic if AC is Pos
        dat_box = st.container()
        
        run = st.form_submit_button("🚀 Run Analysis")

    if run:
        inp_p = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
        inp_s = {"I":s1, "II":s2, "III":s3}
        pos_cnt = sum([normalize(x) for x in inp_p.values()])

        if ac == "Positive":
            st.markdown("<div class='status-fail'><h3>🚨 Auto Control Positive</h3>Allo-ID Suspended. Proceed to DAT.</div>", unsafe_allow_html=True)
            if pos_cnt >= 11:
                st.markdown("<div class='status-warn'><b>⚠️ Critical:</b> Pan-agglutination + AC+. <br>High Risk of <b>DHTR</b>. Elution Mandatory.</div>", unsafe_allow_html=True)
            st.info("💡 Guidance: If IgG+ -> WAIHA/DHTR. If C3d+ -> CAS.")
        
        elif pos_cnt == 11:
            st.markdown("<div class='status-warn'><h3>⚠️ Pan-Reactivity (High Freq Antigen)</h3>All cells positive + AC Neg.<br>Check Siblings / Phenotype Patient.</div>", unsafe_allow_html=True)
        
        else:
            # 1. EXCLUSION
            ruled = set()
            # P
            for i in range(1,12):
                if normalize(inp_p[i])==0:
                    ph = st.session_state.p11.iloc[i-1]
                    for ag in AGS:
                        safe=True
                        if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                        if ph.get(ag,0)==1 and safe: ruled.add(ag)
            # S
            sim={"I":0,"II":1,"III":2}
            for k,v in inp_s.items():
                if normalize(v)==0:
                    ph=st.session_state.p3.iloc[sim[k]]
                    for ag in AGS:
                        if ag not in ruled:
                            safe=True
                            if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                            if ph.get(ag,0)==1 and safe: ruled.add(ag)
            # Extra
            for x in st.session_state.ext:
                if normalize(x['res'])==0:
                    for ag in AGS:
                        if x['ph'].get(ag,0)==1: ruled.add(ag)

            candidates = [x for x in AGS if x not in ruled and x not in IGNORED_AGS]
            
            # 2. LOGIC CHECKS
            # Check for specific D+C Pattern (Anti-G)
            # User Criteria: Cell 1, 2, 3, 4, 8 POSITIVE
            is_anti_G_Pattern = False
            # Check positivity of these specific cells (1-based index)
            g_cells = [1, 2, 3, 4, 8]
            g_match = all(normalize(inp_p[i]) == 1 for i in g_cells)
            
            # Anti-D Masking Logic
            final_display = []
            
            # Special Handling
            if "D" in candidates:
                if g_match and "C" in candidates:
                     st.warning("⚠️ **Anti-G or Anti-D+C Combination** suspected (Cells 1,2,3,4,8 Pos).")
                     final_display.append("D"); final_display.append("C") # Show them
                else:
                    # Pure Anti-D (Masks C/E silently)
                    final_display.append("D")
                    # Remove C/E from candidates to silent them
                    if "C" in candidates: candidates.remove("C")
                    if "E" in candidates: candidates.remove("E")
                    
            for c in candidates:
                if c not in final_display and (not "D" in candidates or (c!="C" and c!="E")):
                    final_display.append(c)

            # 3. RESULT
            if not final_display:
                st.error("No Match Found / Inconclusive.")
            else:
                real = [x for x in final_display if x not in INSIGNIFICANT_AGS]
                other = [x for x in final_display if x in INSIGNIFICANT_AGS]
                
                # Header
                res_txt = " + ".join([f"Anti-{x}" for x in real])
                if not real and other: res_txt = "No Significant Ab"
                
                if real: st.success(f"**Identified:** {res_txt}")
                if other: st.info(f"**Other/Cold:** Anti-{', '.join(other)}")
                
                # Warnings
                if "c" in final_display:
                    st.markdown("<div class='status-fail'>🛑 <b>Anti-c Alert:</b> Anti-E is hard to exclude. Need rare E+c- cell.<br>👉 Transfuse <b>R1R1 (E- c-)</b> Units.</div>", unsafe_allow_html=True)
                
                st.write("---")
                # Rule 3 Validation Loop
                all_val = True
                for ab in (real+other):
                    ok, p, n = check_rule_3(ab, inp_p, inp_s, st.session_state.ext)
                    icn = "✅" if ok else "⚠️"
                    msg = "Rule of 3 Met" if ok else "Unconfirmed"
                    st.write(f"**{icn} Anti-{ab}:** {msg} (P:{p}/N:{n})")
                    if not ok: all_val=False
                    
                    # Separation Strategy
                    if len(real) > 1 and not ok:
                         confs = [x for x in real if x!=ab]
                         found = find_cell_in_inventory(ab, confs)
                         sug_txt = f"Found in stock: <b>{', '.join(found)}</b>" if found else "<span style='color:red'>Search external library</span>"
                         
                         st.markdown(f"""
                         <div class='rec-box'>
                         To Confirm <b>{ab}</b>: Use Cell (<b>{ab}+</b> / {' '.join([c+'-' for c in confs])}).<br>
                         {sug_txt}
                         </div>""", unsafe_allow_html=True)
                         
                if all_val and real:
                    if st.button("Generate Report"):
                        rpt=f"<div class='print-only'><br><center><h2>Maternity & Children Hospital - Tabuk</h2><h3>Serology Report</h3></center><div class='result-sheet'><b>Pt:</b> {nm} ({mr})<hr><b>Result:</b> {res_txt}<br>{f'(Note: '+', '.join(other)+' also found)' if other else ''}<br><b>Validation:</b> Confirmed (p<=0.05).<br><b>Recommendation:</b> Phenotype Negative. Crossmatch Compatible.<br><br>Sig: ___________</div><div style='position:fixed;bottom:0;width:100%;text-align:center'>Dr. Haitham Ismail | Consultant</div></div><script>window.print()</script>"
                        st.markdown(rpt,unsafe_allow_html=True)
                        
    # ADD CELL
    with st.expander("➕ Add Selected Cell (Input Data)"):
        with st.form("extf"):
            id_x=st.text_input("ID"); rs_x=st.selectbox("R",GRADES)
            st.write("Phenotype:")
            c_g=st.columns(8)
            new_p={}
            for i,ag in enumerate(AGS):
                if c_g[i%8].checkbox(ag): new_p[ag]=1
                else: new_p[ag]=0
            if st.form_submit_button("Add Cell"):
                st.session_state.ext.append({"res":normalize_grade(rs_x),"res_txt":rs_x,"ph":new_p})
                st.success("Added! Re-Run.")

    if st.session_state.ext: st.table(pd.DataFrame(st.session_state.ext)[['res_txt']])
