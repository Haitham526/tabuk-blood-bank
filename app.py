import streamlit as st
import pandas as pd
import io
import json
import base64
import requests
from datetime import date

# --------------------------------------------------------------------------
# 0) GITHUB CONNECTOR (SAFE MODE)
# --------------------------------------------------------------------------
def _gh_get_cfg():
    try:
        # يقرأ من Secrets
        t = st.secrets["GITHUB_TOKEN"]; r = st.secrets["GITHUB_REPO"]
        return t, r, "main"
    except: return None, None, None

def load_from_gh(fname):
    t, r, b = _gh_get_cfg()
    if not t: return None
    url = f"https://api.github.com/repos/{r}/contents/data/{fname}"
    headers = {"Authorization": f"token {t}", "Accept": "application/vnd.github.v3.raw"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200: return resp.text
    return None

def save_to_gh(fname, content, msg):
    t, r, b = _gh_get_cfg()
    if not t: return "No Token"
    
    url = f"https://api.github.com/repos/{r}/contents/data/{fname}"
    headers = {"Authorization": f"token {t}", "Accept": "application/vnd.github+json"}
    
    # Check SHA for update
    sha = None
    get_r = requests.get(url, headers=headers)
    if get_r.status_code == 200: sha = get_r.json().get("sha")
    
    # Encode
    b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    payload = {"message": msg, "content": b64, "branch": b}
    if sha: payload["sha"] = sha
    
    put_r = requests.put(url, headers=headers, json=payload)
    return "Saved ✅" if put_r.status_code in [200, 201] else f"Err {put_r.status_code}"

# --------------------------------------------------------------------------
# 1. PAGE CONFIG
# --------------------------------------------------------------------------
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .print-only { display: block !important; } .res-box { border: 4px double #8B0000; padding: 25px; font-family: 'Times New Roman'; } }
    .print-only { display: none; }
    
    .status-ok { background: #d4edda; padding: 10px; border-left: 5px solid #198754; color: #155724; margin: 5px 0;}
    .status-warn { background: #fff3cd; padding: 10px; border-left: 5px solid #ffc107; color: #856404; margin: 5px 0;}
    .status-fail { background: #f8d7da; padding: 10px; border-left: 5px solid #dc3545; color: #842029; margin: 5px 0;}
    
    .strat-box { border: 1px dashed #004085; background: #cfe2ff; padding: 8px; margin-top:5px; border-radius:4px; color:#084298;}
    
    .sig-float { position: fixed; bottom: 10px; right: 15px; background: rgba(255,255,255,0.95); padding: 8px 15px; border: 2px solid #8B0000; border-radius: 8px; box-shadow: 2px 2px 8px #ddd; text-align: center; z-index:99; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class='sig-float no-print'>
    <span style='color:#8B0000;font-weight:bold'>Dr. Haitham Ismail</span><br>
    <small>Clinical Hematology & Transfusion Consultant</small>
</div>
""", unsafe_allow_html=True)

# 2. CONSTANTS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"] 
INSIG = ["Lea", "Lua", "Leb", "P1"]
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# 3. STATE LOADING (SAFE MODE)
# Panel
if 'p11' not in st.session_state:
    raw_p11 = load_from_gh("p11.csv")
    if raw_p11: 
        st.session_state.p11 = pd.read_csv(io.StringIO(raw_p11))
    else:
        st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])

# Screen
if 'p3' not in st.session_state:
    raw_p3 = load_from_gh("p3.csv")
    if raw_p3:
        st.session_state.p3 = pd.read_csv(io.StringIO(raw_p3))
    else:
        st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])

# Lots
if 'lot_p' not in st.session_state:
    # Try Load
    j = load_from_gh("lots.json")
    if j:
        d = json.loads(j)
        st.session_state.lot_p = d.get("lot_p", "NOT SET")
        st.session_state.lot_s = d.get("lot_s", "NOT SET")
    else:
        st.session_state.lot_p = "NOT SET"
        st.session_state.lot_s = "NOT SET"

if 'ext' not in st.session_state: st.session_state.ext = []

# 4. LOGIC ENGINE
def normalize(v): 
    return 0 if str(v).lower() in ["0", "neg"] else 1

def parse_paste(txt, limit):
    # Tab Separated parser
    try:
        rows = txt.strip().split('\n')
        data = []
        c=0
        for line in rows:
            if c>=limit: break
            parts = line.split('\t')
            vals = []
            for p in parts:
                vl = str(p).lower().strip()
                v = 1 if any(x in vl for x in ['+','1','pos','w']) else 0
                vals.append(v)
            if len(vals)>26: vals=vals[-26:]
            while len(vals)<26: vals.append(0)
            rid = f"C{c+1}" if limit==11 else f"Scn"
            d={"ID": rid}
            for i, a in enumerate(AGS): d[a]=vals[i]
            data.append(d); c+=1
        return pd.DataFrame(data), f"Updated {c} rows."
    except Exception as e: return None, str(e)

# SMART SEARCH INVENTORY
def find_cell(target, avoid):
    res = []
    # P11
    for i in range(11):
        r = st.session_state.p11.iloc[i]
        if r.get(target,0)==1:
            clean=True
            for b in avoid: 
                if r.get(b,0)==1: clean=False; break
            if clean: res.append(f"Panel#{i+1}")
    # P3
    scs=["I","II","III"]
    for i,s in enumerate(scs):
        r = st.session_state.p3.iloc[i]
        if r.get(target,0)==1:
            clean=True
            for b in avoid:
                if r.get(b,0)==1: clean=False; break
            if clean: res.append(f"Scn-{s}")
    return res

def analyze_logic(ip, iscr, ex):
    ruled = set()
    # Exclude P11
    for i in range(1,12):
        if normalize(ip[i])==0:
            ph=st.session_state.p11.iloc[i-1]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                if ph.get(ag,0)==1 and safe: ruled.add(ag)
    # Exclude S3
    sim={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize(iscr[k])==0:
            ph=st.session_state.p3.iloc[sim[k]]
            for ag in AGS:
                if ag not in ruled:
                    safe=True
                    if ag in DOSAGE and ph.get(PAIRS.get(ag),0)==1: safe=False
                    if ph.get(ag,0)==1 and safe: ruled.add(ag)
    # Exclude Extra
    for x in ex:
        if normalize(x['res'])==0:
            for ag in AGS: 
                if x['ph'].get(ag,0)==1: ruled.add(ag)
    
    # Matching Score
    cands = [x for x in AGS if x not in ruled and x not in IGNORED_AGS]
    scores = []
    
    for c in cands:
        hits=0; miss=0
        # Count Matches
        for i in range(1,12):
            s=normalize(ip[i]); h=st.session_state.p11.iloc[i-1].get(c,0)
            if s and h: hits+=1
            if s and not h: miss+=1
        for k in ["I","II","III"]:
            s=normalize(iscr[k]); h=st.session_state.p3.iloc[sim[k]].get(c,0)
            if s and h: hits+=1
            if s and not h: miss+=1
        
        final_sc = hits - (miss*3) # Penalty
        scores.append({"Ab":c, "S":final_sc})
        
    scores.sort(key=lambda x: x['S'], reverse=True)
    
    # D-Masking Filter
    res_list = []
    notes = []
    
    is_D = any(x['Ab']=="D" and x['S']>0 for x in scores)
    
    # Check G Pattern (Cells 1,2,3,4,8 Pos?)
    # Adjust to 0-based: 0,1,2,3,7
    g_cells_idx = [0,1,2,3,7] 
    is_G_likely = all(normalize(ip[idx+1])==1 for idx in g_cells_idx)
    
    if is_D and is_G_likely and "C" in cands: 
        notes.append("G_SUSPECT")

    for itm in scores:
        ab = itm['Ab']
        if itm['S'] <= -5: continue 
        # Silent mask C/E if D confirmed
        if is_D and ab in ["C","E"]:
             # If G suspected, Keep C
             if ab=="C" and is_G_likely: pass 
             else: continue 
             
        res_list.append(ab)
        
    if "c" in res_list: notes.append("c_RISK")
    return res_list, notes

def check_r3(cand, ip, iscr, ex):
    p, n = 0, 0
    # Count...
    for i in range(1,12):
        s=normalize(ip[i]); h=st.session_state.p11.iloc[i-1].get(cand,0)
        if s and h: p+=1; 
        if not s and not h: n+=1
    si={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s=normalize(iscr[k]); h=st.session_state.p3.iloc[si[k]].get(cand,0)
        if s and h: p+=1; 
        if not s and not h: n+=1
    for x in ex:
        s=normalize(x['res']); h=x['ph'].get(cand,0)
        if s and h: p+=1; 
        if not s and not h: n+=1
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    return ok, p, n

# ========================================================
# 5. UI LAYOUT
# ========================================================
with st.sidebar:
    st.title("Menu")
    nav = st.radio("Go To", ["Workstation", "Admin Config"])
    if st.button("RESET DATA"): 
        st.session_state.ext=[]
        st.session_state.dat=False
        st.rerun()

# --------- ADMIN ---------
if nav == "Admin Config":
    st.header("Admin Configuration")
    if st.text_input("Password",type="password")=="admin123":
        st.info("Set Lots")
        c1, c2 = st.columns(2)
        lp = c1.text_input("Lot P11", value=st.session_state.lot_p)
        ls = c2.text_input("Lot Scr", value=st.session_state.lot_s)
        
        t1, t2 = st.tabs(["Panel (Copy-Paste)", "Screen (Copy-Paste)"])
        
        with t1:
            tp = st.text_area("Paste Digits (11 Rows)", height=150)
            if st.button("Update P11"):
                df, m = parse_paste(tp, 11)
                if df is not None: st.session_state.p11 = df; st.success(m)
            st.dataframe(st.session_state.p11.iloc[:,:15])
            
        with t2:
            ts = st.text_area("Paste Screen", height=100)
            if st.button("Update Scr"):
                df, m = parse_paste(ts, 3)
                if df is not None: st.session_state.p3 = df; st.success(m)
            st.dataframe(st.session_state.p3.iloc[:,:15])

        st.write("---")
        if st.button("☁️ SAVE CHANGES TO CLOUD"):
            # Prepare JSON
            l_data = json.dumps({"lot_p": lp, "lot_s": ls})
            # 1. Update State
            st.session_state.lot_p = lp; st.session_state.lot_s = ls
            # 2. Push GitHub
            r1 = github_upsert("p11.csv", st.session_state.p11.to_csv(index=False), "P11 upd")
            r2 = github_upsert("p3.csv", st.session_state.p3.to_csv(index=False), "P3 upd")
            r3 = github_upsert("lots.json", l_data, "Lots upd")
            st.success(f"Cloud Update: {r1}")

# --------- WORKSTATION ---------
else:
    lt_p = st.session_state.lot_p
    lt_s = st.session_state.lot_s
    
    st.markdown(f"<center><h2 style='color:#800'>Maternity & Children Hospital - Tabuk</h2><small>Panel: {lt_p} | Screen: {lt_s}</small></center><hr>", unsafe_allow_html=True)
    
    if "NOT SET" in lt_p or "NOT SET" in lt_s:
        st.error("System Locked. Please set Lot Numbers in Admin."); st.stop()
        
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    
    with st.form("main"):
        L, R = st.columns([1, 2])
        with L:
            ac_res = st.radio("Auto Control", ["Negative", "Positive"])
            s1=st.selectbox("Scn I",GRADES); s2=st.selectbox("Scn II",GRADES); s3=st.selectbox("Scn III",GRADES)
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
        inp_p = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
        inp_s = {"I":s1,"II":s2,"III":s3}
        
        tot = sum([normalize(x) for x in inp_p.values()]) + sum([normalize(x) for x in inp_s.values()])
        
        # 1. AC POS
        if ac_res == "Positive":
            st.session_state.dat = True
            st.markdown("<div class='status-fail'>🚨 Auto Control Positive</div>", unsafe_allow_html=True)
            if tot >= 12: st.error("⚠️ Critical: Pan-agglutination + AC+. Check DHTR History.")
            
        # 2. HIGH FREQ
        elif tot >= 13:
             st.session_state.dat = False
             st.markdown("<div class='status-warn'>⚠️ High Frequency Antibody (Pan-reactive).</div>", unsafe_allow_html=True)
             
        # 3. ALLO
        else:
             st.session_state.dat = False
             mat, note = analyze_logic(inp_p, inp_s, st.session_state.ext)
             
             real = [x for x in mat if x not in INSIG]
             cold = [x for x in mat if x in INSIG]
             
             st.subheader("Conclusion")
             
             if not real and not cold: st.error("No Matches Found.")
             else:
                 valid_all = True
                 if "c_RISK" in note: st.error("🛑 Anti-c: Provide R1R1 (E- c-) blood.")
                 if "G_SUSPECT" in note: st.warning("⚠️ Suspect Anti-G pattern.")
                 
                 if real: st.success(f"**Identified:** Anti-{', '.join(real)}")
                 if cold: st.info(f"Cold/Insignificant: Anti-{', '.join(cold)}")
                 
                 st.write("---")
                 
                 # Separation Strategy
                 if len(real) > 1:
                     st.markdown("#### 🔬 Smart Strategy (Separation):")
                     for t in real:
                         oth = [x for x in real if x!=t]
                         hits = find_stock_match(t, oth)
                         loc = f"<b style='color:green'>{', '.join(hits)}</b>" if hits else "<span style='color:red'>Search External</span>"
                         st.markdown(f"<div class='strat-box'>To Confirm <b>{t}</b>: Select {t}+ / {' '.join(oth)} Neg -> {loc}</div>", unsafe_allow_html=True)
                 
                 # Rule 3
                 for ab in (real+cold):
                     ok, p, n = check_r3(ab, inp_p, inp_s, st.session_state.ext)
                     ic = "✅" if ok else "🛑"
                     txt = "Confirmed" if ok else "Need Cells"
                     cls = "status-ok" if ok else "status-warn"
                     st.markdown(f"<div class='{cls}'>{ic} <b>Anti-{ab}:</b> {txt} (Pos:{p} | Neg:{n})</div>", unsafe_allow_html=True)
                     if not ok: valid_all = False
                 
                 if valid_all and real:
                     if st.button("🖨️ Report"):
                         t=f"<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='res-box'>Pt: {nm} ({mr})<hr><h3>Result: Anti-{', '.join(real)}</h3>Verified (p<0.05).<br>Note: Phenotype Neg.<br><br>Sig:_________</div><div class='sig-float'>Dr. Haitham Ismail</div></div><script>window.print()</script>"
                         st.markdown(t,unsafe_allow_html=True)

    # Persistent Extras
    if st.session_state.get('dat', False):
        st.write("---")
        with st.container():
            c1,c2,c3=st.columns(3)
            i=c1.selectbox("IgG",["Neg","Pos"]); c=c2.selectbox("C3",["Neg","Pos"]); ct=c3.selectbox("Ctl",["Neg","Pos"])
            if ct=="Pos": st.error("Invalid")
            elif i=="Pos": st.warning(">> WAIHA / DHTR")
            elif c=="Pos": st.info(">> CAS")

    if not st.session_state.get('dat', False):
        with st.expander("➕ Add Cell"):
            idx=st.text_input("ID"); rs=st.selectbox("Res",GRADES); ph={}
            c=st.columns(8)
            for i,ag in enumerate(AGS):
                if c[i%8].checkbox(ag): ph[ag]=1
                else: ph[ag]=0
            if st.button("Add"):
                st.session_state.ext.append({"res":normalize_grade(rs),"ph":ph})
                st.rerun()

    if st.session_state.ext: st.write("External Cells Added:", len(st.session_state.ext))
