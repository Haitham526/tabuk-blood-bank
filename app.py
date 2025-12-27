import streamlit as st
import pandas as pd
from datetime import date

# 1. SETUP
st.set_page_config(page_title="Tabuk Blood Bank", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    /* Styling adjustments */
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .print-only { display: block !important; } .result-sheet { border: 4px double #8B0000; padding: 25px; font-family: 'Times New Roman'; } }
    .print-only { display: none; }
    
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    .hospital-logo { color: #8B0000; text-align: center; border-bottom: 5px solid #8B0000; padding-bottom: 5px; font-family: sans-serif; font-weight: bold;}
    
    /* Logic Badges */
    .best-match { background-color: #d1e7dd; padding: 12px; border-left: 6px solid #198754; color: #0f5132; margin-bottom: 10px; }
    .possible-match { background-color: #fff3cd; padding: 12px; border-left: 6px solid #ffc107; color: #856404; margin-bottom: 10px; }
    .strategy-box { background-color: #e2e3e5; padding: 10px; border: 1px dashed #6c757d; margin: 5px 0; border-radius: 5px; color: #383d41; }
    .available-tag { background: #198754; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }
    
    .dr-signature { position: fixed; bottom: 0; right: 0; width: 100%; text-align: center; background: white; border-top: 1px solid #ccc; z-index:99; font-size: 11px; padding: 5px; color: #800; font-weight:bold;}
</style>
""", unsafe_allow_html=True)

st.markdown("""<div class='dr-signature no-print'>Dr. Haitham Ismail<br>Clinical Hematology/Oncology & BM Transplantation Consultant</div>""", unsafe_allow_html=True)

# 2. CONSTANTS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"] 
INSIGNIFICANT_AGS = ["Lea", "Lua", "Leb"] # P1 & M Removed from here to allow Primary Detection logic
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# 3. STATE
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'lot' not in st.session_state: st.session_state.lot = "Not Set"
if 'ext' not in st.session_state: st.session_state.ext = []

# 4. ENGINE
def normalize(val):
    return 0 if str(val) in ["0", "neg", "Neg"] else 1

def parse_paste(txt, limit=11):
    try:
        rows = txt.strip().split('\n')
        data = []
        c=0
        for line in rows:
            if c>=limit: break
            # Tab separated paste
            cells = line.split('\t')
            vals = []
            for cell in cells:
                # Accept: 1, +, w, pos
                if any(x in str(cell).lower() for x in ['1','+','w','pos']): vals.append(1)
                else: vals.append(0)
            
            # Trim/Fill
            if len(vals)>26: vals=vals[-26:]
            while len(vals)<26: vals.append(0)
            
            rd = {"ID": f"C{c+1}" if limit==11 else f"Scn"}
            for i,a in enumerate(AGS): rd[a]=vals[i]
            data.append(rd)
            c+=1
        return pd.DataFrame(data), f"Updated {c} rows."
    except Exception as e: return None, str(e)

# SMART STRATEGY FUNCTION
def suggest_strategy(matches):
    suggestions = []
    
    # We have list of candidates (e.g. ['C', 'P1'])
    # Need to find cells to Separate them
    for target in matches:
        others = [x for x in matches if x != target]
        if not others: continue
        
        # Criteria: Target(+), Others(-)
        
        # Scan Inventory (P11 + S3)
        found_in_stock = []
        
        # Panel 11 scan
        for i in range(11):
            row = st.session_state.p11.iloc[i]
            if row.get(target,0)==1:
                clean=True
                for o in others:
                    if row.get(o,0)==1: clean=False; break
                if clean: found_in_stock.append(f"Cell {i+1}")
                
        # Screen scan
        scns=["I","II","III"]
        for i,s in enumerate(scns):
            row = st.session_state.p3.iloc[i]
            if row.get(target,0)==1:
                clean=True
                for o in others:
                    if row.get(o,0)==1: clean=False; break
                if clean: found_in_stock.append(f"Scn {s}")
                
        neg_profile = " & ".join([f"{o}⁻" for o in others])
        
        # Build Message
        av_tag = f"<br><span class='available-tag'>✅ Available in Stock: {', '.join(found_in_stock)}</span>" if found_in_stock else "<br><span style='color:red'>(Not found in panel/screen. Search library)</span>"
        
        msg = f"To Confirm <b>Anti-{target}</b> (and rule out others):<br>Need Cell: <b>{target}+</b> and <b>{neg_profile}</b>{av_tag}"
        suggestions.append(msg)
        
    return suggestions

def analyze_logic_smart(p_in, s_in, ex):
    # 1. EXCLUSION
    ruled = set()
    
    # Loop ALL inputs (Panel, Screen, Extra)
    all_rows = []
    all_res = []
    
    # Aggregating
    for i in range(1,12): 
        all_rows.append(st.session_state.p11.iloc[i-1].to_dict())
        all_res.append(normalize(p_in[i]))
        
    s_idx = {"I":0, "II":1, "III":2}
    for k in ["I","II","III"]:
        all_rows.append(st.session_state.p3.iloc[s_idx[k]].to_dict())
        all_res.append(normalize(s_in[k]))
        
    for x in ex:
        all_rows.append(x['ph'])
        all_res.append(normalize(x['res']))
        
    # Logic
    total_pos_reactions = sum(all_res)
    
    for i, res in enumerate(all_res):
        if res == 0: # Neg result
            ph = all_rows[i]
            for ag in AGS:
                safe = True
                # Dosage
                if ag in DOSAGE:
                    pr = PAIRS.get(ag)
                    if pr and ph.get(pr,0)==1: safe=False
                
                if ph.get(ag,0)==1 and safe: ruled.add(ag)
                
    # 2. PATTERN RANKING
    candidates = [x for x in AGS if x not in ruled]
    display = [x for x in candidates if x not in IGNORED_AGS]
    
    scored_results = [] # [(Name, Score), ...]
    
    for cand in display:
        # Score = How many POS reactions does this Ag explain?
        explained = 0
        missed = 0
        
        for i, res in enumerate(all_res):
            if res == 1:
                has_ag = all_rows[i].get(cand, 0)
                if has_ag == 1: explained += 1
                else: missed += 1
                
        # Only keep candidates that explain AT LEAST ONE positive reaction (Basic Inclusion)
        # OR candidates that we couldn't rule out but didn't have chance to react
        # BUT for sorting: Prefer "Highest Explained / Lowest Missed"
        
        score_metric = explained - (missed * 2) # Penalize misses heavily
        
        scored_results.append({
            "Ab": cand,
            "Score": score_metric,
            "Explained": explained,
            "Missed": missed
        })
    
    # Sort: Highest Score first
    scored_results.sort(key=lambda x: x['Score'], reverse=True)
    
    # Categorize
    # "Probable" = Positive Score (Explains more than it misses)
    # "Possible/Residual" = Low Score
    
    return scored_results, ruled, total_pos_reactions

def check_stats(cand, p_in, s_in, ex):
    p, n = 0, 0
    # Panel
    for i in range(1,12):
        s = normalize(p_in[i]); h = st.session_state.p11.iloc[i-1].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    sm={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s = normalize(s_in[k]); h = st.session_state.p3.iloc[sm[k]].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extra
    for x in ex:
        s = normalize(x['res']); h = x['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
        
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    return ok, p, n

# ==========================================
# 5. UI
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    mode = st.radio("System Mode", ["Workstation", "Supervisor"])
    if st.button("RESET DATA"): 
        st.session_state.ext=[]
        st.rerun()

# ADMIN
if mode == "Supervisor":
    st.title("Config")
    if st.text_input("Pwd",type="password")=="admin123":
        st.session_state.lot = st.text_input("Lot:",value=st.session_state.lot)
        t1, t2 = st.tabs(["Panel","Screen"])
        with t1:
            t1v = st.text_area("Paste 11 Rows (Digits)", height=150)
            if st.button("Update P11"): 
                d,m = parse_paste(t1v, 11)
                if d is not None: st.session_state.p11=d; st.success(m)
            st.dataframe(st.session_state.p11)
        with t2:
            t2v = st.text_area("Paste 3 Rows (Digits)", height=100)
            if st.button("Update Scr"): 
                d,m = parse_paste(t2v, 3)
                if d is not None: st.session_state.p3=d; st.success(m)
            st.dataframe(st.session_state.p3)

# USER
else:
    st.markdown(f"<center><h2 style='color:#8B0000'>Maternity & Children Hospital - Tabuk</h2><p><b>Lot: {st.session_state.lot}</b></p></center>", unsafe_allow_html=True)
    c1,c2,c3,c4=st.columns(4)
    nm=c1.text_input("Pt Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    with st.form("inputs"):
        L,R = st.columns([1,2])
        with L:
            ac=st.radio("Auto",["Negative","Positive"])
            s1=st.selectbox("Scn I",GRADES); s2=st.selectbox("Scn II",GRADES); s3=st.selectbox("Scn III",GRADES)
        with R:
            g1,g2=st.columns(2)
            with g1:
                c1=st.selectbox("1",GRADES,key="k1"); c2=st.selectbox("2",GRADES,key="k2"); c3=st.selectbox("3",GRADES,key="k3"); c4=st.selectbox("4",GRADES,key="k4"); c5=st.selectbox("5",GRADES,key="k5"); c6=st.selectbox("6",GRADES,key="k6")
            with g2:
                c7=st.selectbox("7",GRADES,key="k7"); c8=st.selectbox("8",GRADES,key="k8"); c9=st.selectbox("9",GRADES,key="k9"); c10=st.selectbox("10",GRADES,key="k10"); c11=st.selectbox("11",GRADES,key="k11")
        go = st.form_submit_button("🚀 Run Smart Analysis")
        
    if go:
        inp_p={1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
        inp_s={"I":s1,"II":s2,"III":s3}
        
        # DAT ALERT
        if ac == "Positive":
            st.error("🚨 Auto-Control POSITIVE. Check DAT/History.")
        else:
            res_list, ruled, pos_sum = analyze_logic_smart(inp_p, inp_s, st.session_state.ext)
            
            # Pan Reactivity
            if pos_sum == 14: # 11+3
                 st.warning("⚠️ Pan-Reactivity: Check High Frequency Antibody.")
            
            elif not res_list:
                st.error("No Match Found / All ruled out.")
                
            else:
                st.subheader("Conclusion")
                
                # Logic: We have 'Best Fits' (score > 0) and 'Residuals'
                best_fits = [x for x in res_list if x['Score'] > 0]
                residuals = [x for x in res_list if x['Score'] <= 0]
                
                final_printable_list = []
                
                # SHOW BEST FITS
                if best_fits:
                    for obj in best_fits:
                        ab = obj['Ab']
                        st.markdown(f"<div class='best-match'>✅ <b>Anti-{ab}</b> (Most Likely Match)<br>Explains {obj['Explained']} positive cells. Missed {obj['Missed']}.</div>", unsafe_allow_html=True)
                        final_printable_list.append(ab)
                
                # SHOW RESIDUALS (Warning)
                if residuals:
                    txt = ", ".join([r['Ab'] for r in residuals])
                    st.markdown(f"<div class='possible-match'>⚠️ <b>Unable to Exclude:</b> Anti-{txt}<br>(Matches very few positives or masked by main antibody)</div>", unsafe_allow_html=True)
                    # Don't print residuals as "Identified" unless tech confirms, but add to strategies
                    final_printable_list.extend([r['Ab'] for r in residuals])

                st.write("---")
                st.write("<b>Validation & Strategy:</b>")
                
                # GENERATE STRATEGY FOR ALL REMAINING
                strategies = suggest_strategy(final_printable_list)
                for s in strategies: st.markdown(f"<div class='strategy-box'>{s}</div>", unsafe_allow_html=True)
                
                # VALIDATE ALL
                all_validated = True
                for ab in final_printable_list:
                    ok, p, n = check_stats(ab, inp_p, inp_s, st.session_state.ext)
                    icn = "✅" if ok else "❌"
                    st.caption(f"{icn} **Anti-{ab}**: Rule of 3 {'MET' if ok else 'FAIL'} (Pos:{p}/Neg:{n})")
                    if not ok: all_validated = False
                
                if all_validated:
                    if st.button("🖨️ Report"):
                        rpt = f"<div class='print-only'><br><center><h2>Maternity & Children Hospital - Tabuk</h2><h3>Serology Report</h3></center><div class='result-sheet'><b>Pt:</b> {nm}<br><b>Result:</b> Anti-{', '.join([x['Ab'] for x in best_fits])}<br><b>Note:</b> {', '.join([x['Ab'] for x in residuals])} also considered.<br><br><b>Sig:</b> ___________</div></div><script>window.print()</script>"
                        st.markdown(rpt, unsafe_allow_html=True)

    # Add Cell Tool
    with st.expander("➕ Add Cell (For Separation/Confirm)"):
        with st.form("ad"):
            i=st.text_input("ID"); r=st.selectbox("R",GRADES); 
            ags=st.multiselect("Pos Ags", AGS)
            if st.form_submit_button("Add"):
                p={a:0 for a in AGS}
                for x in ags: p[x]=1
                st.session_state.ext.append({"res":r,"ph":p})
                st.success("Added! Run Again.")
