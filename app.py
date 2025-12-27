import streamlit as st
import pandas as pd
import io

# 1. BASE CONFIG
st.set_page_config(page_title="Tabuk Serology Lab", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { 
        .stApp > header, .sidebar, footer, .no-print { display: none !important; } 
        .print-only { display: block !important; }
        .result-box { border: 3px double #800; padding: 25px; font-family: 'Times New Roman'; }
    }
    .print-only { display: none; }
    
    .status-ok { background: #d4edda; color: #155724; padding: 10px; border-left: 6px solid #198754; margin-bottom: 5px; }
    .status-warn { background: #fff3cd; color: #856404; padding: 10px; border-left: 6px solid #ffc107; margin-bottom: 5px; }
    .status-fail { background: #f8d7da; color: #842029; padding: 10px; border-left: 6px solid #dc3545; margin-bottom: 5px; }
    
    .best-match { border: 2px solid #28a745; background-color: #eaffea; padding: 10px; border-radius: 5px; margin: 10px 0; }
    
    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div style='position:fixed;bottom:10px;right:10px;z-index:99;' class='no-print'><b style='color:#800'>Dr. Haitham Ismail</b><br>Clinical Consultant</div>", unsafe_allow_html=True)

# 2. DEFINITIONS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

IGNORED = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
# IMPORTANT: M is significant here. P1, Lea, Leb, Lua are cold/insignificant logic
COLD_AGS = ["Lea", "Leb", "Lua", "P1"] 

# 3. STATE
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'lot_p' not in st.session_state: st.session_state.lot_p = "Unknown"
if 'lot_s' not in st.session_state: st.session_state.lot_s = "Unknown"
if 'ext' not in st.session_state: st.session_state.ext = []

# 4. LOGIC ENGINE
def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

def parse_paste(txt, limit):
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
                v = 1 if any(x in v_clean for x in ['+', '1', 'pos', 'w']) else 0
                vals.append(v)
            if len(vals) > 26: vals=vals[-26:]
            while len(vals) < 26: vals.append(0)
            
            lbl = f"C{c+1}" if limit==11 else f"Scn"
            d = {"ID": lbl}
            for i, ag in enumerate(AGS): d[ag] = vals[i]
            data.append(d)
            c+=1
        return pd.DataFrame(data), f"Saved {c} rows."
    except Exception as e: return None, str(e)

def analyze_and_score(inp_p, inp_s, extras):
    # A. Exclusion Phase
    ruled_out = set()
    # Panel
    for i in range(1, 12):
        if inp_p[i] == 0: # User said Neg
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False 
                if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
    # Screen
    s_idx = {"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if inp_s[k] == 0: # Neg
            ph = st.session_state.p3.iloc[s_idx[k]]
            for ag in AGS:
                if ag not in ruled_out:
                    safe=True
                    if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                    if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
    
    # Extras
    for ex in extras:
        if normalize(ex['res']) == 0:
            for ag in AGS:
                if ex['ph'].get(ag,0)==1: ruled_out.add(ag)

    # B. Candidates & Scoring
    survivors = [x for x in AGS if x not in ruled_out]
    display = [x for x in survivors if x not in IGNORED]
    
    scored_results = []
    
    for cand in display:
        # Score = Positive matches. Mismatch = Penalty.
        match_count = 0
        mismatch_count = 0
        
        # Panel Check
        for i in range(1, 12):
            if inp_p[i] == 1: # User Pos
                if st.session_state.p11.iloc[i-1].get(cand,0) == 1: match_count+=1
                else: mismatch_count += 1
                
        # Screen Check
        for k in ["I","II","III"]:
            if inp_s[k] == 1:
                if st.session_state.p3.iloc[s_idx[k]].get(cand,0) == 1: match_count+=1
                else: mismatch_count += 1
        
        # Determine sorting score
        # High match, Low mismatch is better
        # Penalty is heavy: An Antibody shouldn't miss reactions
        final_score = match_count - (mismatch_count * 5)
        
        scored_results.append({
            "Ab": cand, 
            "Score": final_score,
            "Matches": match_count,
            "Mismatches": mismatch_count
        })

    # Sort DESC
    scored_results.sort(key=lambda x: x['Score'], reverse=True)
    return scored_results, ruled_out

def check_rule_3(cand, in_p, in_s, extra):
    p, n = 0, 0
    # Panel
    for i in range(1, 12):
        s = in_p[i]; h = st.session_state.p11.iloc[i-1].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    s_idx = {"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s = in_s[k]; h = st.session_state.p3.iloc[s_idx[k]].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extra
    for c in extra:
        s = normalize(c['res']); h = c['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
        
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    return ok, p, n

# ========================================================
# 5. UI LAYOUT
# ========================================================
with st.sidebar:
    nav = st.radio("System Menu", ["Workstation", "Admin Config"])
    st.divider()
    if st.button("RESET ALL"): st.session_state.ext=[]; st.rerun()

# ------- ADMIN -------
if nav == "Admin Config":
    st.title("Settings")
    if st.text_input("Password",type="password")=="admin123":
        st.subheader("1. Lot Setup (Separate)")
        c1, c2 = st.columns(2)
        lp = c1.text_input("Panel 11 Lot #", value=st.session_state.lot_p)
        ls = c2.text_input("Screen Lot #", value=st.session_state.lot_s)
        if st.button("Save Lots"): 
            st.session_state.lot_p = lp
            st.session_state.lot_s = ls
            st.rerun()

        st.subheader("2. Grid Data (Copy Paste)")
        t1, t2 = st.tabs(["Panel", "Screen"])
        with t1:
            tp = st.text_area("Paste Panel Digits", height=150)
            if st.button("Update P11"): 
                d,m = parse_paste(tp, 11)
                if d is not None: st.session_state.p11=d; st.success(m)
            st.dataframe(st.session_state.p11)
        with t2:
            ts = st.text_area("Paste Screen Digits", height=100)
            if st.button("Update Scr"): 
                d,m = parse_paste(ts, 3)
                if d is not None: st.session_state.p3=d; st.success(m)
            st.dataframe(st.session_state.p3)

# ------- WORKSTATION -------
else:
    # Header with Both Lots
    st.markdown(f"""
    <div style='text-align:center; color:#800000; border-bottom:4px solid #003366;'>
        <h1>Maternity & Children Hospital - Tabuk</h1>
        <h4>Immunohematology Unit</h4>
        <small style='color:green; font-weight:bold;'>Panel Lot: {st.session_state.lot_p} | Screen Lot: {st.session_state.lot_s}</small>
    </div>
    """, unsafe_allow_html=True)
    
    c1,c2,c3,c4=st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()

    with st.form("main_entry"):
        colL, colR = st.columns([1, 2])
        with colL:
            st.write("Controls")
            ac_sel = st.radio("Auto Control", ["Negative","Positive"])
            s1=st.selectbox("S-I",["Neg","Pos"]); s2=st.selectbox("S-II",["Neg","Pos"]); s3=st.selectbox("S-III",["Neg","Pos"])
        with colR:
            st.write("Panel")
            g1,g2=st.columns(2)
            # Safe Hardcode
            with g1:
                c1=st.selectbox("1",["Neg","Pos"]); c2=st.selectbox("2",["Neg","Pos"]); c3=st.selectbox("3",["Neg","Pos"])
                c4=st.selectbox("4",["Neg","Pos"]); c5=st.selectbox("5",["Neg","Pos"]); c6=st.selectbox("6",["Neg","Pos"])
            with g2:
                c7=st.selectbox("7",["Neg","Pos"]); c8=st.selectbox("8",["Neg","Pos"]); c9=st.selectbox("9",["Neg","Pos"])
                c10=st.selectbox("10",["Neg","Pos"]); c11=st.selectbox("11",["Neg","Pos"])
        
        run_btn = st.form_submit_button("🚀 Run Analysis")

    # LOGIC
    if run_btn:
        st.session_state.ac_res = ac_sel # Persist for DAT
        
        inp_p = {i+1:normalize(v) for i,v in enumerate([c1,c2,c3,c4,c5,c6,c7,c8,c9,c10,c11])}
        inp_s = {"I":normalize(s1), "II":normalize(s2), "III":normalize(s3)}
        
        total_pos = sum(inp_p.values()) + sum(inp_s.values())

        if ac_sel == "Positive":
            st.error("🚨 STOP: Auto Control Positive.")
            st.warning("Suspect: Auto-Antibody. Check DAT Below.")
        
        elif total_pos >= 13: # Pan reactivity
             st.warning("⚠️ High Incidence Antibody (Pan-reactivity + Neg AC).")
             st.info("Guidance: Test Siblings / Reference Lab.")
             
        else:
            # 1. SMART ENGINE
            ranked_results, ruled_out = analyze_and_score(inp_p, inp_s, st.session_state.ext)
            
            # Anti-D Masking Logic (Applied on sorted results)
            final_display = []
            
            # Check if D is the top candidate or high score
            is_D_Likely = False
            for r in ranked_results:
                if r['Ab'] == "D" and r['Score'] > 0: is_D_Likely = True; break
            
            for item in ranked_results:
                cand = item['Ab']
                # Mask C/E only if D is strong match
                if is_D_Likely and (cand == "C" or cand == "E"): continue
                final_display.append(item)
            
            if not final_display:
                st.error("Inconclusive.")
            else:
                st.subheader("Conclusion")
                
                # Split Real vs Cold
                likely = []
                insig = []
                
                for res in final_display:
                    if res['Score'] < 0: continue # Hide total mismatches
                    
                    if res['Ab'] in COLD_AGS:
                        insig.append(res['Ab'])
                    else:
                        likely.append(res)
                        
                # DISPLAY SIGNIFICANT
                if likely:
                    top = likely[0]['Ab']
                    
                    # IF MATCH > 1 -> Show top one green, others yellow (Separation needed)
                    if len(likely) > 1:
                        names = [x['Ab'] for x in likely]
                        st.warning(f"⚠️ **Mixture Suspected:** {', '.join(names)}")
                        
                        st.markdown("**🔬 Separation Strategy:**")
                        for t in names:
                            oths = [o for o in names if o!=t]
                            st.write(f"- Confirm **{t}**: Need cell {t}+ / {' '.join([x+'-' for x in oths])}")
                    else:
                        st.success(f"✅ **Identified:** Anti-{top}")
                        st.caption("Matches Logic Pattern Best.")
                
                if insig:
                     st.info(f"Cold/Other: Anti-{', '.join(insig)} detected.")

                st.write("---")
                # VALIDATION STATS (Show for all active candidates)
                to_validate = [x['Ab'] for x in likely] + insig
                valid_ok = True
                
                for ab in to_validate:
                    ok, p, n = check_rule_3(ab, inp_p, inp_s, st.session_state.ext)
                    icon = "✅" if ok else "🛑"
                    txt = "Met" if ok else "Need Cells"
                    st.write(f"{icon} **Anti-{ab}**: {txt} (P:{p}/N:{n})")
                    if not ok: valid_ok = False
                
                if valid_ok and likely:
                     if st.button("Generate Report"):
                         t = ", ".join([x['Ab'] for x in likely])
                         h=f"<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='result-box'>Pt: {nm} ({mr})<hr>Res: Anti-{t}<br>Validated.<br>Note: Phenotype Negative.<br><br>Sig:___________</div></div><script>window.print()</script>"
                         st.markdown(h, unsafe_allow_html=True)
                elif likely:
                     st.warning("Please Add Extra Cells to meet Rule of 3.")
                     
    # DAT AREA
    if st.session_state.get('ac_res') == "Positive":
         st.write("---")
         with st.container():
             c1,c2,c3 = st.columns(3)
             i=c1.selectbox("IgG", ["Neg","Pos"]); c=c2.selectbox("C3", ["Neg","Pos"]); t=c3.selectbox("Ctrl",["Neg","Pos"])
             if t=="Pos": st.error("Invlaid")
             elif i=="Pos": st.error("Probable WAIHA / DHTR")
             elif c=="Pos": st.warning("Probable CAS")

    # EXTRA CELL
    with st.expander("➕ Add Cell"):
        c1,c2=st.columns(2); nid=c1.text_input("ID"); nrs=c2.selectbox("Res",["Neg","Pos"])
        ph={}
        g=st.columns(8)
        for i,a in enumerate(AGS):
            if g[i%8].checkbox(a): ph[a]=1
            else: ph[a]=0
        if st.button("Add Cell"):
            st.session_state.ext.append({"res":normalize(nrs),"ph":ph})
            st.success("OK"); st.rerun()
    
    if st.session_state.ext: st.table(pd.DataFrame(st.session_state.ext))
