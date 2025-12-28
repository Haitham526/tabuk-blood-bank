import streamlit as st
import pandas as pd
import json
import base64
import requests
import io
from datetime import date
from pathlib import Path

# ==========================================
# 0. GITHUB ENGINE (RESTORED)
# ==========================================
def _gh_get_cfg():
    # Fetch from secrets
    try:
        token = st.secrets["GITHUB_TOKEN"]
        repo  = st.secrets["GITHUB_REPO"]
        branch = "main"
        return token, repo, branch
    except: return None, None, None

def github_upsert(filename, content, msg):
    token, repo, branch = _gh_get_cfg()
    if not token: return "Error: No Secrets Found"
    
    url = f"https://api.github.com/repos/{repo}/contents/data/{filename}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    
    sha = None
    r = requests.get(url, headers=headers)
    if r.status_code == 200: sha = r.json().get("sha")
    
    b64_c = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    data = {"message": msg, "content": b64_c, "branch": branch}
    if sha: data["sha"] = sha
    
    resp = requests.put(url, headers=headers, json=data)
    return "Saved to GitHub ✅" if resp.status_code in [200, 201] else f"Error {resp.status_code}"

def load_gh_data(filename):
    token, repo, branch = _gh_get_cfg()
    if not token: return None
    url = f"https://api.github.com/repos/{repo}/contents/data/{filename}"
    r = requests.get(url, headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3.raw"})
    if r.status_code == 200: return r.text
    return None

# ==========================================
# 1. SETUP
# ==========================================
st.set_page_config(page_title="Tabuk Blood Bank", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .print-only { display: block !important; } .res-box { border: 4px double #800; padding: 25px; font-family: Times New Roman; } .sig-foot { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; font-weight: bold; } }
    .print-only { display: none; }
    .head-logo { text-align: center; border-bottom: 5px solid #8B0000; padding-bottom: 5px; color: #003366; }
    
    .stat-ok { background: #d4edda; padding: 10px; border-left: 5px solid #198754; color: #155724; margin: 5px 0;}
    .stat-warn { background: #fff3cd; padding: 10px; border-left: 5px solid #ffc107; color: #856404; margin: 5px 0;}
    .stat-crit { background: #f8d7da; padding: 10px; border-left: 5px solid #dc3545; color: #721c24; margin: 5px 0;}
    .stat-info { background: #e2e3e5; padding: 10px; border-left: 5px solid #0d6efd; color: #004085; font-style: italic;}

    .strat-box { border: 1px dashed #004085; background-color: #cfe2ff; padding: 10px; margin: 5px 0; border-radius: 4px; color: #004085; }
    .avail-tag { font-weight: bold; color: white; background: #198754; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; margin-left: 5px; }
    
    .dr-badge { position: fixed; bottom: 10px; right: 15px; background: rgba(255,255,255,0.9); padding: 8px 15px; border: 2px solid #8B0000; border-radius: 8px; z-index:99; text-align: center; }
</style>
""", unsafe_allow_html=True)

st.markdown("""<div class='dr-badge no-print'><span style='color:#800;font-weight:bold'>Dr. Haitham Ismail</span><br><small>Clinical Hematology & Transfusion Consultant</small></div>""", unsafe_allow_html=True)

AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

IGNORED = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
INSIG = ["Lea", "Lua", "Leb", "P1"]
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# 3. STATE (Try load from GitHub first, else init blank)
if 'p11' not in st.session_state:
    csv = load_gh_data("p11.csv")
    if csv: st.session_state.p11 = pd.read_csv(io.StringIO(csv))
    else: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])

if 'p3' not in st.session_state:
    csv = load_gh_data("p3.csv")
    if csv: st.session_state.p3 = pd.read_csv(io.StringIO(csv))
    else: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])

if 'ext' not in st.session_state: st.session_state.ext = []

# Load Lots
if 'lots' not in st.session_state:
    j = load_gh_data("lots.json")
    st.session_state.lots = json.loads(j) if j else {"p": "", "s": ""}

# 4. LOGIC ENGINE
def norm(v): return 0 if str(v).lower() in ["0", "neg", "negative"] else 1

def parse_paste(txt, lim):
    try:
        lines = txt.strip().split('\n')
        d = []
        c = 0
        for l in lines:
            if c>=lim: break
            parts = l.split('\t')
            row = []
            for p in parts:
                v = 1 if any(x in str(p).lower() for x in ['+','1','pos','w']) else 0
                row.append(v)
            if len(row)>26: row=row[-26:]
            while len(row)<26: row.append(0)
            rec = {"ID": f"C{c+1}" if lim==11 else f"S{c}"}
            for i, a in enumerate(AGS): rec[a] = row[i]
            d.append(rec); c+=1
        return pd.DataFrame(d), f"Parsed {c} rows."
    except Exception as e: return None, str(e)

# Smart Suggestions (Look in Inventory)
def find_matching_cells_in_inventory(target_ab, conflicts):
    found_list = []
    # Panel
    for i in range(11):
        cell = st.session_state.p11.iloc[i]
        if cell.get(target_ab,0)==1:
            clean = True
            for bad in conflicts: 
                if cell.get(bad,0)==1: clean=False; break
            if clean: found_list.append(f"Panel#{i+1}")
    # Screen
    sc_lbls = ["I","II","III"]
    for i in range(3):
        cell = st.session_state.p3.iloc[i]
        if cell.get(target_ab,0)==1:
            clean = True
            for bad in conflicts: 
                if cell.get(bad,0)==1: clean=False; break
            if clean: found_list.append(f"Screen {sc_lbls[i]}")
    return found_list

def run_analysis_logic(ip, iscr, ext):
    # A. Exclusion
    ruled = set()
    # Panel
    for i in range(1,12):
        if norm(ip[i])==0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                if ph.get(ag,0)==1 and safe: ruled.add(ag)
    # Screen
    smap={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if norm(iscr[k])==0:
            ph = st.session_state.p3.iloc[smap[k]]
            for ag in AGS:
                if ag not in ruled:
                    safe=True
                    if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                    if ph.get(ag,0)==1 and safe: ruled.add(ag)
    # Extra
    for ex in ext:
        if norm(ex['res'])==0:
            for ag in AGS:
                 if ex['ph'].get(ag,0)==1: ruled.add(ag)

    # B. Ranking (Best Match)
    cands = [x for x in AGS if x not in ruled and x not in IGNORED]
    scores = []
    for c in cands:
        h=0; m=0
        # P
        for i in range(1,12):
            s=norm(ip[i]); val=st.session_state.p11.iloc[i-1].get(c,0)
            if s and val: h+=1
            if s and not val: m+=1
        # S
        for k in ["I","II","III"]:
            s=norm(iscr[k]); val=st.session_state.p3.iloc[smap[k]].get(c,0)
            if s and val: h+=1
            if s and not val: m+=1
        # E
        for x in ext:
            s=norm(x['res']); val=x['ph'].get(c,0)
            if s and val: h+=1
            if s and not val: m+=1
            
        scores.append({"Ab":c, "S": h - (m*5)}) # Penalty
        
    scores.sort(key=lambda x: x['S'], reverse=True)
    
    # Anti-D mask
    final = []
    notes = []
    is_D = any(x['Ab']=="D" and x['S']>0 for x in scores)
    
    for item in scores:
        ab = item['Ab']
        if item['S'] < -2: continue
        if is_D and ab in ["C","E"]: continue
        final.append(ab)
        
    if "c" in final: notes.append("anti-c")
    return final, notes

def check_r3(cand, ip, iscr, ex):
    p, n = 0, 0
    # Panel
    for i in range(1, 12):
        s=norm(ip[i]); h=st.session_state.p11.iloc[i-1].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    idx = {"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s=norm(iscr[k]); h=st.session_state.p3.iloc[idx[k]].get(cand, 0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extras
    for c in ex:
        s=norm(c['res']); h=c['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    return (p>=3 and n>=3) or (p>=2 and n>=3), p, n

# ==========================================
# 5. UI
# ==========================================
with st.sidebar:
    st.title("Menu")
    nav = st.radio("Go To:", ["Workstation", "Supervisor (Admin)"])
    st.divider()
    if st.button("RESET Local Data"):
        st.session_state.ext=[]; st.session_state.dat=False; st.rerun()

# --------- ADMIN (WITH GITHUB) ---------
if nav == "Supervisor (Admin)":
    st.title("Master Configuration")
    if st.text_input("Password",type="password")=="admin123":
        st.info("System Config")
        c1, c2 = st.columns(2)
        lp = c1.text_input("Lot P11", value=st.session_state.lots['p'])
        ls = c2.text_input("Lot Scr", value=st.session_state.lots['s'])
        
        t1, t2 = st.tabs(["Panel Copy", "Screen Copy"])
        with t1:
            pt = st.text_area("Paste Digits P11", height=150)
            if st.button("Apply P11"):
                d,m = parse_paste(pt,11)
                if d is not None: st.session_state.p11=d; st.success(m)
            st.dataframe(st.session_state.p11.iloc[:,:12])
        with t2:
            st2 = st.text_area("Paste Digits Scr", height=100)
            if st.button("Apply Scr"):
                d,m = parse_paste(st2,3)
                if d is not None: st.session_state.p3=d; st.success(m)
            st.dataframe(st.session_state.p3.iloc[:,:12])
            
        st.write("---")
        if st.button("☁️ SAVE TO GITHUB (Live Update)"):
            st.session_state.lots = {"p":lp, "s":ls}
            j = json.dumps(st.session_state.lots)
            r1 = github_upsert_file("p11.csv", st.session_state.p11.to_csv(index=False), "Upd P11")
            r2 = github_upsert_file("p3.csv", st.session_state.p3.to_csv(index=False), "Upd P3")
            r3 = github_upsert_file("lots.json", j, "Upd Lots")
            st.success(f"Status: {r1} | {r2} | {r3}")

# --------- WORKSTATION ---------
else:
    # 1. LOCK
    lt_p = st.session_state.lots['p']; lt_s = st.session_state.lots['s']
    if not lt_p or not lt_s: st.error("LOCKED. Contact Admin."); st.stop()
    
    st.markdown(f"<center><h2 style='color:#800'>Maternity & Children Hospital - Tabuk</h2><small>ID Lot: {lt_p} | Screen Lot: {lt_s}</small></center><hr>", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    
    with st.form("main"):
        L, R = st.columns([1, 2])
        with L:
            ac_res = st.radio("Auto Control", ["Negative", "Positive"])
            s1=st.selectbox("Scn I", GRADES); s2=st.selectbox("Scn II", GRADES); s3=st.selectbox("Scn III", GRADES)
        with R:
            g1,g2=st.columns(2)
            with g1:
                c1=st.selectbox("1",GRADES,key="k1"); c2=st.selectbox("2",GRADES,key="k2"); c3=st.selectbox("3",GRADES,key="k3")
                c4=st.selectbox("4",GRADES,key="k4"); c5=st.selectbox("5",GRADES,key="k5"); c6=st.selectbox("6",GRADES,key="k6")
            with g2:
                c7=st.selectbox("7",GRADES,key="k7"); c8=st.selectbox("8",GRADES,key="k8"); c9=st.selectbox("9",GRADES,key="k9")
                c10=st.selectbox("10",GRADES,key="k10"); c11=st.selectbox("11",GRADES,key="k11")
        run = st.form_submit_button("🚀 Run Analysis")

    if run:
        st.session_state.inp_p = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
        st.session_state.inp_s = {"I":s1,"II":s2,"III":s3}
        
        cnt = sum([norm(x) for x in st.session_state.inp_p.values()]) + sum([norm(x) for x in st.session_state.inp_s.values()])
        
        # SCENARIO: AUTO POSITIVE
        if ac_res == "Positive":
            st.session_state.dat = True
            st.markdown("<div class='stat-crit'>🚨 AC POSITIVE: Logic Suspended. See DAT.</div>", unsafe_allow_html=True)
            if cnt >= 12: st.warning("⚠️ Critical: Pan-Agglutination. Rule out DHTR/WAIHA.")
            
        # SCENARIO: HIGH FREQ
        elif cnt >= 13:
             st.session_state.dat = False
             st.markdown("<div class='stat-warn'>⚠️ High Incidence Ag Suspected. Refer Sample.</div>", unsafe_allow_html=True)
             
        # SCENARIO: ALLO
        else:
             st.session_state.dat = False
             matches, notes = analyze_master_logic(st.session_state.inp_p, st.session_state.inp_s, st.session_state.ext)
             
             real = [x for x in matches if x not in INSIG]
             cold = [x for x in matches if x in INSIG]
             
             st.subheader("Conclusion")
             if not real and not cold: st.error("No Match.")
             else:
                 valid_all = True
                 if real: st.success(f"**Identified:** Anti-{', '.join(real)}")
                 if cold: st.info(f"Insignificant: {', '.join(cold)}")
                 if "anti-c" in notes: st.error("Anti-c found. Use R1R1 (E-c-).")
                 
                 # Strategy for Multiple
                 if len(real) > 1:
                     st.markdown("**Separation Strategy:**")
                     for t in real:
                         others = [o for o in real if o!=t]
                         # Check Inventory
                         hits = find_matching_cells_in_inventory(t, others)
                         htxt = f"<span class='avail-tag'>{', '.join(hits)}</span>" if hits else "<b style='color:red'>Search Lib</b>"
                         st.markdown(f"<div class='strat-box'>To Confirm <b>{t}</b> (Select {t}+ / {' '.join(others)} neg) -> {htxt}</div>", unsafe_allow_html=True)
                         
                 # Validation Rule 3
                 for ab in (real+cold):
                     ok, p, n = check_rule_3(ab, st.session_state.inp_p, st.session_state.inp_s, st.session_state.ext)
                     icon = "✅" if ok else "🛑"
                     msg = "Met" if ok else "Unconfirmed"
                     st.write(f"**{icon} {ab}:** Rule of 3 {msg} (P:{p} | N:{n})")
                     if not ok: valid_all = False
                     
                 if valid_all and real:
                     if st.button("Generate Report"):
                         t = f"""<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='res-box'>Pt:{nm} ({mr})<br>Tech:{tc} | Date:{dt}<hr><h3>Anti-{', '.join(real)}</h3>Verified (p<0.05).<br>Note: Phenotype Neg.<br><br>Sig:________<div class='footer-print'>Dr. Haitham Ismail</div></div></div><script>window.print()</script>"""
                         st.markdown(t, unsafe_allow_html=True)

    # PERSISTENT DAT
    if st.session_state.get('dat', False):
        st.write("---")
        with st.container():
            c1,c2,c3 = st.columns(3)
            i=c1.selectbox("IgG",["Neg","Pos"]); c=c2.selectbox("C3",["Neg","Pos"]); ct=c3.selectbox("Ctl",["Neg","Pos"])
            if ct=="Pos": st.error("Invalid")
            elif i=="Pos": st.warning(">> WAIHA/DHTR. Do Elution.")
            elif c=="Pos": st.info(">> CAS. Pre-warm.")

    # PERSISTENT ADD CELL
    if not st.session_state.get('dat', False):
        with st.expander("➕ Add Selected Cell (Input Data)"):
            id_x=st.text_input("Lot#"); rs_x=st.selectbox("R", GRADES, key="xrr")
            ag_col=st.columns(8); new_ph={}
            for i,ag in enumerate(AGS):
                if ag_col[i%8].checkbox(ag): new_ph[ag]=1 
                else: new_ph[ag]=0
            if st.button("Add Cell"):
                st.session_state.ext.append({"res":normalize_grade(rs_x), "res_txt":rs_x, "ph":new_ph})
                st.success("Added!"); st.rerun()
                
    if st.session_state.ext:
         st.write("Extra Cells:"); st.table(pd.DataFrame(st.session_state.ext)[['res_txt']])
