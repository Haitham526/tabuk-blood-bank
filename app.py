import streamlit as st
import pandas as pd
import io
import json
import base64
import requests
from datetime import date

# ==========================================
# 0. GITHUB ENGINE (RESTORED)
# ==========================================
# يقوم بتحميل البيانات وحفظها سحابياً عشان متضعش
def _gh_get_cfg():
    # يبحث عن التوكن في Secrets
    # تأكد من وضع GITHUB_TOKEN و GITHUB_REPO في إعدادات Streamlit Secrets
    try:
        token = st.secrets["GITHUB_TOKEN"]
        repo  = st.secrets["GITHUB_REPO"]
        branch = "main"
        return token, repo, branch
    except:
        return None, None, None

def github_upsert_file(filename, content, msg):
    token, repo, branch = _gh_get_cfg()
    if not token: return "Error: No GitHub Secrets Found!"
    
    url = f"https://api.github.com/repos/{repo}/contents/data/{filename}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    
    # Check exists
    sha = None
    r = requests.get(url, headers=headers)
    if r.status_code == 200: sha = r.json().get("sha")
    
    # Convert content to Base64
    b64_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    
    data = {"message": msg, "content": b64_content, "branch": branch}
    if sha: data["sha"] = sha
    
    resp = requests.put(url, headers=headers, json=data)
    if resp.status_code in [200, 201]: return "Saved to GitHub ✅"
    else: return f"GitHub Error: {resp.status_code}"

def load_data_from_github(filename):
    token, repo, branch = _gh_get_cfg()
    if not token: return None
    
    url = f"https://api.github.com/repos/{repo}/contents/data/{filename}"
    r = requests.get(url, headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3.raw"})
    if r.status_code == 200: return r.text
    return None

# ==========================================
# 1. SETUP & STYLE
# ==========================================
st.set_page_config(page_title="MCH Tabuk Bank", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .print-only { display: block !important; } .result-box { border: 2px solid #333; padding: 20px; font-family: 'Times New Roman'; } }
    .print-only { display: none; }
    
    .status-ok { background: #d4edda; color: #155724; padding: 10px; margin: 5px 0; border-left: 5px solid green; border-radius: 4px; }
    .status-warn { background: #fff3cd; color: #856404; padding: 10px; margin: 5px 0; border-left: 5px solid #ffc107; border-radius: 4px; }
    .status-fail { background: #f8d7da; color: #842029; padding: 10px; margin: 5px 0; border-left: 5px solid #dc3545; border-radius: 4px; }
    .status-info { background: #e2e3e5; padding: 10px; margin: 5px 0; border-left: 5px solid #0d6efd; border-radius: 4px; color: #004085; }
    
    .sig-float { position: fixed; bottom: 10px; right: 15px; background: white; padding: 5px; border: 1px solid #ccc; z-index:99; box-shadow: 2px 2px 5px #ccc;}
    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='sig-float no-print'><b>Dr. Haitham Ismail</b><br>Clinical Consultant</div>", unsafe_allow_html=True)

# 2. CONSTANTS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

IGNORED_AGS = ["Kpa", "Kpb", "Jsa", "Jsb", "Lub", "Cw"]
INSIGNIFICANT_AGS = ["Lea", "Leb", "Lua", "P1"] # Clinical decision: Cold/Nuissance
GRADES = ["0", "+1", "+2", "+3", "+4", "Hemolysis"]

# 3. STATE INITIALIZATION (Load from Cloud if available)
if 'p11' not in st.session_state:
    csv_txt = load_data_from_github("p11.csv")
    if csv_txt: 
        st.session_state.p11 = pd.read_csv(io.StringIO(csv_txt))
    else:
        st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])

if 'p3' not in st.session_state:
    csv_txt = load_data_from_github("p3.csv")
    if csv_txt: 
        st.session_state.p3 = pd.read_csv(io.StringIO(csv_txt))
    else:
        st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])

if 'ext' not in st.session_state: st.session_state.ext = []
if 'lots' not in st.session_state:
    j = load_data_from_github("lots.json")
    if j: st.session_state.lots = json.loads(j)
    else: st.session_state.lots = {"p":"Not Set", "s":"Not Set"}

# 4. LOGIC ENGINE
def normalize_grade(val):
    s = str(val).lower().strip()
    return 0 if s in ["0", "neg"] else 1

def parse_paste(txt, limit):
    try:
        rows = [r for r in txt.strip().split('\n') if r.strip()]
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
        return pd.DataFrame(data), f"Parsed {c} rows"
    except Exception as e: return None, str(e)

def find_stock_match(target, avoid_list):
    matches = []
    # Panel
    for i in range(11):
        c = st.session_state.p11.iloc[i]
        if c.get(target,0)==1:
            clean=True
            for bad in avoid_list: 
                if c.get(bad,0)==1: clean=False; break
            if clean: matches.append(f"P-C{i+1}")
    # Screen
    scns = ["I","II","III"]
    for i, s in enumerate(scns):
        c = st.session_state.p3.iloc[i]
        if c.get(target,0)==1:
            clean=True
            for bad in avoid_list: 
                if c.get(bad,0)==1: clean=False; break
            if clean: matches.append(f"Scn-{s}")
    return matches

# *** THIS IS THE MASTER LOGIC (NAME FIXED) ***
def analyze_master_logic(in_p, in_s, extra):
    ruled_out = set()
    
    # 1. Exclusion (Panel)
    for i in range(1, 12):
        if normalize_grade(in_p[i]) == 0:
            ph = st.session_state.p11.iloc[i-1]
            for ag in AGS:
                safe=True
                if ag in DOSAGE and ph.get(PAIRS[ag],0)==1: safe=False
                if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
                
    # 2. Exclusion (Screen)
    idx={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        if normalize_grade(in_s[k]) == 0:
            ph = st.session_state.p3.iloc[idx[k]]
            for ag in AGS:
                if ag not in ruled_out:
                    safe=True
                    if ag in DOSAGE and ph.get(PAIRS[ag],0)==1: safe=False
                    if ph.get(ag,0)==1 and safe: ruled_out.add(ag)
    
    # 3. Extra
    for ex in extra:
        if normalize_grade(ex['r']) == 0:
             for ag in AGS:
                 if ex['ph'].get(ag,0)==1: ruled_out.add(ag)
                 
    # 4. Candidates & Scoring
    survivors = [x for x in AGS if x not in ruled_out and x not in IGNORED_AGS]
    scored = []
    
    for cand in survivors:
        hits = 0; miss = 0
        # P
        for i in range(1,12):
            is_pos = normalize_grade(in_p[i])
            has_ag = st.session_state.p11.iloc[i-1].get(cand,0)
            if is_pos and has_ag: hits+=1
            if is_pos and not has_ag: miss+=1
        # S
        for k in ["I","II","III"]:
            is_pos = normalize_grade(in_s[k])
            has_ag = st.session_state.p3.iloc[idx[k]].get(cand,0)
            if is_pos and has_ag: hits+=1
            if is_pos and not has_ag: miss+=1
        # E
        for x in extra:
            is_pos = normalize_grade(x['r'])
            has_ag = x['ph'].get(cand,0)
            if is_pos and has_ag: hits+=1
            if is_pos and not has_ag: miss+=1
            
        score = hits - (miss * 5)
        scored.append({"Ab": cand, "Score": score})
        
    scored.sort(key=lambda x: x['Score'], reverse=True)
    
    final = []
    # Filter D masking
    is_D = any(x['Ab']=="D" and x['Score']>0 for x in scored)
    for x in scored:
        ab = x['Ab']
        if x['Score'] < -2: continue 
        if is_D and (ab=="C" or ab=="E"): continue
        final.append(ab)
        
    notes = []
    if "c" in final: notes.append("R1R1")
    return final, notes

def check_r3(cand, in_p, in_s, extra):
    p, n = 0, 0
    # P
    for i in range(1,12):
        s=normalize_grade(in_p[i]); h=st.session_state.p11.iloc[i-1].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # S
    id={"I":0,"II":1,"III":2}
    for k in ["I","II","III"]:
        s=normalize_grade(in_s[k]); h=st.session_state.p3.iloc[id[k]].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Ex
    for x in extra:
        s=normalize_grade(x['r']); h=x['ph'].get(cand,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
        
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    return ok, p, n

# ========================================================
# 5. UI
# ========================================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Admin Config"])
    if st.button("RESET LOCAL"):
        st.session_state.ext=[]
        st.rerun()

# --- ADMIN ---
if nav == "Admin Config":
    st.title("System Admin (Cloud Connected)")
    pwd = st.text_input("Admin Password", type="password")
    
    if pwd == "admin123":
        c1, c2 = st.columns(2)
        lp = c1.text_input("Lot P11", value=st.session_state.lots['p'])
        ls = c2.text_input("Lot Scr", value=st.session_state.lots['s'])
        
        t1, t2 = st.tabs(["Panel Data", "Screen Data"])
        with t1:
            pt = st.text_area("Paste Digits (11 Rows)", height=150)
            if st.button("Load P11"):
                df,m = parse_paste(pt, 11)
                if df is not None: st.session_state.p11 = df; st.success(m)
            st.dataframe(st.session_state.p11)
            
        with t2:
            st = st.text_area("Paste Digits (Screen)", height=100)
            if st.button("Load Scr"):
                df,m = parse_paste(st, 3)
                if df is not None: st.session_state.p3 = df; st.success(m)
            st.dataframe(st.session_state.p3)
            
        st.write("---")
        if st.button("☁️ SAVE CHANGES TO GITHUB (Live)"):
            st.session_state.lots['p'] = lp
            st.session_state.lots['s'] = ls
            
            res1 = github_upsert_file("p11.csv", st.session_state.p11.to_csv(index=False), "Update P11")
            res2 = github_upsert_file("p3.csv", st.session_state.p3.to_csv(index=False), "Update P3")
            l_json = json.dumps({"p": lp, "s": ls})
            res3 = github_upsert_file("lots.json", l_json, "Update Lots")
            
            st.info(f"Status: P11:{res1} | P3:{res2} | Lots:{res3}")

# --- USER ---
else:
    # 1. INFO HEADER
    lt_p = st.session_state.lots.get('p','N/A')
    lt_s = st.session_state.lots.get('s','N/A')
    st.markdown(f"<center><h2 style='color:#800'>Maternity & Children Hospital - Tabuk</h2><small>Panel: {lt_p} | Screen: {lt_s}</small></center><hr>", unsafe_allow_html=True)
    
    # Check Lock
    if lt_p == "N/A" or lt_s == "N/A":
        st.error("System Locked: Update Lots in Admin."); st.stop()
    
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    
    # 2. ENTRY FORM (STABLE)
    with st.form("main_form"):
        colL, colR = st.columns([1, 2])
        with colL:
            st.write("<b>Control</b>", unsafe_allow_html=True)
            ac_in = st.radio("AC", ["Negative", "Positive"])
            s1=st.selectbox("Scn I",GRADES); s2=st.selectbox("Scn II",GRADES); s3=st.selectbox("Scn III",GRADES)
        with colR:
            st.write("<b>ID Panel</b>", unsafe_allow_html=True)
            g1,g2 = st.columns(2)
            with g1:
                c1=st.selectbox("1",GRADES,key="k1"); c2=st.selectbox("2",GRADES,key="k2"); c3=st.selectbox("3",GRADES,key="k3"); c4=st.selectbox("4",GRADES,key="k4"); c5=st.selectbox("5",GRADES,key="k5"); c6=st.selectbox("6",GRADES,key="k6")
            with g2:
                c7=st.selectbox("7",GRADES,key="k7"); c8=st.selectbox("8",GRADES,key="k8"); c9=st.selectbox("9",GRADES,key="k9"); c10=st.selectbox("10",GRADES,key="k10"); c11=st.selectbox("11",GRADES,key="k11")
        
        run = st.form_submit_button("🚀 Run Analysis")

    # 3. ANALYSIS OUTPUT
    if run:
        st.write("---")
        # Collect Data
        i_p = {1:c1,2:c2,3:c3,4:c4,5:c5,6:c6,7:c7,8:c8,9:c9,10:c10,11:c11}
        i_s = {"I":s1, "II":s2, "III":s3}
        
        cnt = sum([normalize_grade(x) for x in i_p.values()]) + sum([normalize_grade(x) for x in i_s.values()])

        if ac_in == "Positive":
            st.markdown("<div class='status-fail'>🚨 Auto Control POSITIVE</div>", unsafe_allow_html=True)
            if cnt >= 12: st.error("⚠️ Critical: Pan-agglutination. Suspect DHTR (History check required).")
            
            # Persist this session part? We are in form submission flow.
            # Inline DAT Table (Won't persist perfectly on re-click of other things, but fine for result view)
            st.write("### 🧪 DAT Interpretation")
            with st.container(border=True):
                 cl1,cl2,cl3=st.columns(3)
                 st.caption("(For documentation, please record manually)")
                 st.write("Protocol: 1. IgG+ (WAIHA/DHTR) 2. C3d+ (CAS)")
        
        elif cnt >= 13:
            st.markdown("<div class='status-warn'>⚠️ High Incidence Antigen Suspected (Pan-reactivity).</div>", unsafe_allow_html=True)

        else:
            # ALLO
            final_res, notes = analyze_master_logic(i_p, i_s, st.session_state.ext)
            
            sigs = [x for x in final_res if x not in INSIGNIFICANT_AGS]
            colds = [x for x in final_res if x in INSIGNIFICANT_AGS]
            
            if not sigs and not colds:
                st.error("No Match.")
            else:
                if sigs: st.success(f"**Identified:** Anti-{', '.join(sigs)}")
                if colds: st.markdown(f"<div class='status-info'>Insignificant: Anti-{', '.join(colds)}</div>",unsafe_allow_html=True)
                if "R1R1" in notes: st.error("🛑 Anti-c present: Transfuse R1R1 (E- c-) units.")

                valid_all = True
                
                # Rule of 3 + Strategy
                for ab in (sigs+colds):
                    ok, p_n, n_n = check_rule_3(ab, i_p, i_s, st.session_state.ext)
                    ic = "✅" if ok else "⚠️"
                    msg = "Rule Met" if ok else "Need Cells"
                    
                    st.write(f"**{ic} Anti-{ab}:** {msg} (P:{p_n} | N:{n_n})")
                    if not ok: valid_all=False
                
                if len(sigs) > 1:
                     st.write("---")
                     st.write("**Separation Strategy:**")
                     for t in sigs:
                         conflicts = [x for x in sigs if x!=t]
                         matches = find_stock_match(t, conflicts)
                         found = f"<span style='color:green;font-weight:bold'>{', '.join(matches)}</span>" if matches else "<span style='color:red'>External</span>"
                         st.markdown(f"- Confirm <b>{t}</b> ({t}+ / {' '.join(conflicts)}- ) using: {found}", unsafe_allow_html=True)

                if valid_all:
                     if st.button("🖨️ Print Report"):
                         t=f"<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='result-sheet'>Pt: {nm}<br><b>Result: Anti-{', '.join(sigs)}</b><br>{'+ '.join(colds)}<br>Valid Rule 3.<br><br>Sig:_________</div><div class='footer-print'>Dr. Haitham</div></div><script>window.print()</script>"
                         st.markdown(t,unsafe_allow_html=True)
                         
    # Extra (Always Visible)
    with st.expander("Add External Cell"):
        with st.form("ext_f"):
            e_id=st.text_input("ID"); e_rs=st.selectbox("R",GRADES)
            st.write("Phenotype (+):")
            cg=st.columns(8); np={}
            for i,ag in enumerate(AGS):
                if cg[i%8].checkbox(ag): np[ag]=1 
            if st.form_submit_button("Add"):
                st.session_state.ext.append({"res":e_rs,"ph":np})
                st.success("Added! Re-run."); st.rerun()

    if st.session_state.ext: st.table(pd.DataFrame(st.session_state.ext)[['res']])
