import streamlit as st
import pandas as pd
import io
from datetime import date

# ==========================================
# 1. SETUP
# ==========================================
st.set_page_config(page_title="MCH Blood Bank", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .block-container { padding: 0 !important; } .print-only { display: block !important; } .results-box { border: 2px solid #333; padding: 20px; margin-top:20px; font-family: 'Times New Roman'; font-size:14px; } }
    .print-only { display: none; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    .status-pass { background-color: #d1e7dd; padding: 8px; border-radius: 5px; color: #0f5132; margin-bottom: 5px; }
    .status-fail { background-color: #f8d7da; padding: 8px; border-radius: 5px; color: #842029; margin-bottom: 5px; }
    .dr-sign { position: fixed; bottom: 5px; right: 10px; font-size: 11px; background: white; padding: 5px; border: 1px solid #ccc; z-index:99; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='dr-sign no-print'>Dr. Haitham Ismail | Consultant</div>", unsafe_allow_html=True)

# --- DEFINITIONS ---
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# --- STATE ---
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"Scn {i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'res' not in st.session_state: st.session_state.res = {f"c{i}":"Neg" for i in range(1,12)}
if 'scr' not in st.session_state: st.session_state.scr = {f"s{i}":"Neg" for i in ["I","II","III"]}
if 'ext' not in st.session_state: st.session_state.ext = []

# ==========================================
# 2. LOGIC (SAME PARSER THAT WORKED + VISUAL FIX)
# ==========================================
def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+','1','pos','yes','w']) else 0

def matrix_scan_final(file_bytes, limit_rows=11):
    try:
        xls = pd.ExcelFile(file_bytes)
        for sheet in xls.sheet_names:
            df = pd.read_excel(file_bytes, sheet_name=sheet, header=None)
            
            # 1. MAP COLUMNS
            col_coords = {}
            header_row = -1
            
            for r in range(min(30, len(df))):
                matches = 0
                temp = {}
                for c in range(min(60, len(df.columns))):
                    val = str(df.iloc[r, c]).strip().replace(" ","")
                    
                    # CASE SENSITIVE DETECT
                    det = None
                    if val in ["c","C","e","E","k","K","s","S"]: det = val
                    elif val.upper() == "D" or val.upper() == "RHD": det = "D"
                    else:
                        vup = val.upper()
                        if vup in AGS: det = vup
                    
                    if det: 
                        temp[det] = c
                        matches += 1
                
                if matches >= 3:
                    header_row = r
                    col_coords = temp
            
            if len(col_coords) < 3: continue
            
            # 2. EXTRACT ROWS
            start = header_row + 1
            data = []
            extracted = 0
            curr = start
            
            while extracted < limit_rows and curr < len(df):
                # Valid check using D or C
                d_idx = col_coords.get("D") or col_coords.get("C")
                is_valid = False
                if d_idx is not None:
                    check = str(df.iloc[curr, d_idx]).lower()
                    if any(x in check for x in ['+','0','1','w']): is_valid=True
                
                if is_valid:
                    lbl = f"Cell {extracted+1}" if limit_rows==11 else f"Scn {['I','II','III'][extracted]}"
                    r_d = {"ID": lbl}
                    for ag in AGS:
                        v = 0
                        if ag in col_coords:
                            v = normalize(df.iloc[curr, col_coords[ag]])
                        r_d[ag] = int(v)
                    data.append(r_d)
                    extracted += 1
                curr += 1
                
            if extracted >= 1:
                return pd.DataFrame(data), f"Success from '{sheet}' OK"
                
        return None, "Structure not found"
    except Exception as e: return None, str(e)

# Calculation Logic
def check_logic(c, r11, ip, r3, iscr, ex):
    p,n = 0,0
    # Panel
    for i in range(1,12):
        s = 1 if ip[f"c{i}"]!="Neg" else 0
        h = r11.iloc[i-1].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    for i, x in enumerate(["I","II","III"]):
        s = 1 if iscr[f"s{x}"]!="Neg" else 0
        h = r3.iloc[i].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extra
    for x in ex:
        if x['ph'].get(c,0)==1 and x['s']==1: p+=1
        if x['ph'].get(c,0)==0 and x['s']==0: n+=1
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    t = "Standard" if (p>=3 and n>=3) else ("Modified" if ok else "Fail")
    return ok, p, n, t

def get_ruled(r11, ip, r3, iscr):
    out = set()
    for ag in AGS:
        # P
        for i in range(1,12):
            if ip[f"c{i}"]=="Neg" and r11.iloc[i-1].get(ag,0)==1:
                if ag in DOSAGE:
                    pr = PAIRS.get(ag)
                    if pr and r11.iloc[i-1].get(pr,0)==1: continue
                out.add(ag)
        # S
        lk = {"I":0,"II":1,"III":2}
        for k,v in iscr.items():
            if v=="Neg":
                ph = r3.iloc[lk[k.replace("s","")]]
                if ph.get(ag,0)==1:
                    if ag in DOSAGE:
                        pr = PAIRS.get(ag)
                        if pr and ph.get(pr,0)==1: continue
                    out.add(ag)
    return out

def set_bulk(v):
    for i in range(1,12): st.session_state.res[f"c{i}"]=v

# ==========================================
# 3. INTERFACE
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png",width=60)
    nav = st.radio("Mode", ["Workstation", "Admin Config"])
    st.divider()
    if st.button("Reset All"): st.session_state.ext=[]; st.rerun()

# --- ADMIN ---
if nav == "Admin Config":
    st.title("🛠️ Master Configuration")
    if st.text_input("Password",type="password")=="admin123":
        t1,t2=st.tabs(["Panel 11", "Screening"])
        with t1:
            up=st.file_uploader("Upload Panel", type=["xlsx"])
            if up:
                df, m = matrix_scan_final(io.BytesIO(up.getvalue()), 11)
                if df is not None:
                    st.success(m)
                    # ---- FORCE CLEAN TYPES BEFORE SAVE ----
                    st.session_state.p11 = df.fillna(0).astype(int, errors='ignore') 
                    st.rerun()
                else: st.error(m)
            
            # --- SAFE DISPLAY ---
            safe_df = st.session_state.p11.copy()
            # Ensure ID is string and rest are numbers
            for c in safe_df.columns:
                if c != "ID": safe_df[c] = pd.to_numeric(safe_df[c], errors='coerce').fillna(0).astype(int)
            
            st.caption("Live Editor (Changes Saved automatically via Save button)")
            edit1 = st.data_editor(safe_df, height=450, hide_index=True, use_container_width=True)
            if st.button("Save Panel"): st.session_state.p11=edit1; st.success("Saved")
            
        with t2:
            st.info("Upload Screen")
            ups=st.file_uploader("Upload Scr", type=["xlsx"])
            if ups:
                df2,m2=matrix_scan_final(io.BytesIO(ups.getvalue()),3)
                if df2 is not None:
                    st.success(m2)
                    st.session_state.p3=df2.fillna(0).astype(int, errors='ignore')
                    st.rerun()
                else: st.error(m2)
            safe_p3 = st.session_state.p3.copy()
            for c in safe_p3.columns:
                if c != "ID": safe_p3[c] = pd.to_numeric(safe_p3[c], errors='coerce').fillna(0).astype(int)
            edit2=st.data_editor(safe_p3, hide_index=True)
            if st.button("Save Screen"): st.session_state.p3=edit2; st.success("Saved")

# --- USER ---
else:
    st.markdown("<h2 style='color:#036;text-align:center;'>Maternity & Children Hospital - Tabuk</h2>",unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Pt"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    L,R=st.columns([1,2])
    with L:
        ac=st.radio("AC",["Negative","Positive"]); 
        if ac=="Positive": st.error("DAT REQ"); st.stop()
        st.write("---")
        for x in ["I","II","III"]: st.session_state.scr[f"s{x}"]=st.selectbox(f"S-{x}",["Neg","w+","1+","2+"], key=f"s_{x}")
    with R:
        cols=st.columns(6)
        in_map={}
        for i in range(1,12):
            v=cols[(i-1)%6].selectbox(f"C{i}",["Neg","w+","1+","2+"],key=f"p_{i}")
            st.session_state.res[f"c{i}"]=v
            in_map[i]=0 if v=="Neg" else 1
            
    st.divider()
    if st.checkbox("Analyze"):
        ruled=get_out(st.session_state.p11, st.session_state.res, st.session_state.p3, st.session_state.scr)
        cands=[x for x in AGS if x not in ruled]
        match=[]
        for c in cands:
            miss=False
            for i,s in in_map.items():
                if s>0 and st.session_state.p11.iloc[i-1].get(c,0)==0: miss=True
            if not miss: match.append(c)
            
        if not match: st.error("Inconclusive.")
        else:
            allow=True
            st.subheader("Result")
            for m in match:
                ok,p,n,txt=check_logic(m,st.session_state.p11,st.session_state.res,st.session_state.p3,st.session_state.scr,st.session_state.ext)
                st.markdown(f"<div class='status-{'pass' if ok else 'fail'}'><b>Anti-{m}</b>: {txt} ({p} P/{n} N)</div>",unsafe_allow_html=True)
                if not ok: allow=False
            
            if allow:
                if st.button("Print"):
                    h=f"<div class='print-only'><center><h2>MCH Tabuk</h2></center><div class='results-box'>Pt: {nm}<br>Res: Anti-{', '.join(match)}<br>Valid Rule of 3.<br>Sig: ________</div></div><script>window.print()</script>"
                    st.markdown(h,unsafe_allow_html=True)
            else:
                with st.expander("Add Cell"):
                    idx=st.text_input("ID"); rs=st.selectbox("Res",["Neg","Pos"]); ph={}
                    cols=st.columns(len(match))
                    for i,m in enumerate(match):
                        ph[m]=1 if cols[i].checkbox(m) else 0
                    if st.button("Add"):
                        st.session_state.ext.append({"src":idx,"s":1 if rs=="Pos" else 0,"ph":ph,"res":1 if rs=="Pos" else 0}); st.rerun()
