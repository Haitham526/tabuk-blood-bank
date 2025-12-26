import streamlit as st
import pandas as pd
import io
from datetime import date

# 1. SETUP
st.set_page_config(page_title="Tabuk Blood Bank", layout="wide", page_icon="🏥")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .print-only { display: block !important; } }
    .print-only { display: none; }
    .header-hospital { text-align:center; color:#003366; border-bottom:4px solid #005f73; padding-bottom:10px; }
    .status-ok { background:#d4edda; color:#155724; padding:8px; border-radius:4px; margin:2px; }
    .status-no { background:#f8d7da; color:#721c24; padding:8px; border-radius:4px; margin:2px; }
    .footer-sig { position:fixed; bottom:0; width:100%; text-align:center; font-size:10px; border-top:1px solid #ddd; background:#fff; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='footer-sig no-print'>Dr. Haitham Ismail | Consultant</div>", unsafe_allow_html=True)

# DEFINITIONS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# STATE
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'user' not in st.session_state: st.session_state.user = {f"c{i}":"Neg" for i in range(1,12)}
if 'scr' not in st.session_state: st.session_state.scr = {f"s{i}":"Neg" for i in ["I","II","III"]}
if 'ext' not in st.session_state: st.session_state.ext = []

# --- 2. THE BRUTE FORCE PARSER ---
def get_val(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

def clean(txt):
    return str(txt).strip().replace("\n","").replace(" ","")

def brute_force_scan(file, rows_needed):
    xls = pd.ExcelFile(file)
    for sheet in xls.sheet_names:
        df = pd.read_excel(file, sheet_name=sheet, header=None)
        
        # 1. MAP COLUMNS (Case Sensitive Scan)
        col_indices = {}
        for r in range(min(30, len(df))):
            for c in range(len(df.columns)):
                raw = clean(df.iloc[r, c])
                
                det = None
                # Check Specific Case
                if raw in ["c","C","e","E","k","K","s","S"]: det = raw
                # Check Standard Upper
                elif raw.upper() in ["D","RHD","RH1"]: det = "D"
                elif raw.upper() in [x.upper() for x in AGS]:
                    # Normalize back
                    for a in AGS: 
                        if a.upper() == raw.upper(): det = a
                
                if det:
                    # Update (Latest finding overwrites earliest, closer to data?) 
                    # No, First finding usually Header.
                    if det not in col_indices: col_indices[det] = c
        
        # Check if D was found
        if "D" in col_indices or "K" in col_indices:
            # 2. FIND DATA START
            # Use 'D' column to find where '0' or '+' starts
            key_col = col_indices.get("D") if "D" in col_indices else col_indices.get("K")
            
            data_start_row = -1
            for r in range(min(40, len(df))):
                cell = str(df.iloc[r, key_col]).lower()
                if any(x in cell for x in ['+','0','1','w']) and "d" not in cell: # valid data
                    data_start_row = r
                    break
            
            if data_start_row != -1:
                # EXTRACT
                final = []
                curr = data_start_row
                extracted = 0
                while extracted < rows_needed and curr < len(df):
                    row_data = {"ID": f"C{extracted+1}"}
                    
                    # Double Check Row Validity
                    check_val = str(df.iloc[curr, key_col]).lower()
                    if not any(x in check_val for x in ['+','0','1','w']): 
                        curr += 1; continue # Skip empty lines
                    
                    for ag in AGS:
                        v = 0
                        if ag in col_indices:
                            v = get_val(df.iloc[curr, col_indices[ag]])
                        row_data[ag] = int(v)
                    
                    final.append(row_data)
                    extracted += 1
                    curr += 1
                
                if extracted >= 1:
                    return pd.DataFrame(final), f"Success from '{sheet}'"

    return None, "Parse failed."

# LOGIC
def can_out(ag, p):
    if p.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr=PAIRS.get(ag)
        if pr and p.get(pr,0)==1: return False
    return True

def chk(c, p11, u11, p3, u3, ex):
    p, n = 0, 0
    # P11
    for i in range(1, 12):
        s = 1 if u11[f"c{i}"]!="Neg" else 0
        h = p11.iloc[i-1].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # P3
    for i,l in enumerate(["I","II","III"]):
        s = 1 if u3[f"s{l}"]!="Neg" else 0
        h = p3.iloc[i].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # EX
    for x in ex:
        if x['s']==1 and x['p'].get(c,0)==1: p+=1
        if x['s']==0 and x['p'].get(c,0)==0: n+=1
    
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    t = "Std" if (p>=3 and n>=3) else "Mod"
    return ok, p, n, t

def set_b(v): 
    for i in range(1,12): st.session_state.user[f"c{i}"]=v

# UI SIDEBAR
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png",width=60)
    nav=st.radio("Menu",["Workstation","Supervisor"])
    if st.button("Reset All"): st.session_state.ext=[]; st.rerun()

# ----------------- ADMIN -----------------
if nav == "Supervisor":
    st.title("🛠️ Config")
    if st.text_input("Password",type="password")=="admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening"])
        with t1:
            up1=st.file_uploader("Upload Panel", type=["xlsx"])
            if up1:
                d1,m1=brute_force_scan(io.BytesIO(up1.getvalue()),11)
                if d1 is not None:
                    st.success(m1); st.session_state.p11=d1; st.rerun()
                else: st.error(m1)
            e1=st.data_editor(st.session_state.p11, hide_index=True)
            if st.button("Save P11"): st.session_state.p11=e1; st.success("Saved")
        
        with t2:
            up2=st.file_uploader("Upload Screen", type=["xlsx"])
            if up2:
                d2,m2=brute_force_scan(io.BytesIO(up2.getvalue()),3)
                if d2 is not None:
                    st.success(m2); st.session_state.p3=d2; st.rerun()
                else: st.error(m2)
            e2=st.data_editor(st.session_state.p3, hide_index=True)
            if st.button("Save Scr"): st.session_state.p3=e2; st.success("Saved")

# ----------------- USER -----------------
else:
    st.markdown("<div class='header-hospital'><h2>Maternity & Children Hospital - Tabuk</h2><h4>Serology Unit</h4></div>", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Pt Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    L,R=st.columns([1,2])
    with L:
        ac=st.radio("AC",["Negative","Positive"]); 
        if ac=="Positive": st.error("STOP: DAT Required"); st.stop()
        st.write("---")
        for x in ["I","II","III"]: st.session_state.scr[f"s{x}"]=st.selectbox(x,["Neg","Pos"],key=f"su_{x}")
        if st.button("Set All Neg"): set_b("Neg")
    with R:
        cols=st.columns(6)
        in_m={}
        for i in range(1,12):
            val=cols[(i-1)%6].selectbox(f"C{i}",["Neg","w+","1+","2+"],key=f"pu_{i}", index=0 if st.session_state.user[f"c{i}"]=="Neg" else 1)
            st.session_state.user[f"c{i}"]=val
            in_m[i]=0 if val=="Neg" else 1
            
    if st.button("Run Analysis"):
        r11=[st.session_state.p11.iloc[i].to_dict() for i in range(11)]
        r3=[st.session_state.p3.iloc[i].to_dict() for i in range(3)]
        ruled=set()
        
        for ag in AGS:
            for i,s in in_m.items():
                if s==0 and can_out(ag, r11[i-1]): ruled.add(ag); break
        scr_m={"I":0,"II":1,"III":2}
        for k,v in st.session_state.scr.items():
            if v=="Neg":
                for ag in AGS:
                    if ag not in ruled and can_out(ag, r3[scr_m[k[1:]]]): ruled.add(ag)
        
        match=[]
        for c in [x for x in AGS if x not in ruled]:
            miss=False
            for i,s in in_m.items():
                if s>0 and r11[i-1].get(c,0)==0: miss=True
            if not miss: match.append(c)
            
        st.divider()
        if not match: st.error("Inconclusive.")
        else:
            allow=True
            st.subheader("Result")
            for m in match:
                ok,p,n,t = chk(m, st.session_state.p11, st.session_state.user, st.session_state.p3, st.session_state.scr, st.session_state.ext)
                cls = "status-ok" if ok else "status-no"
                st.markdown(f"<div class='{cls}'><b>Anti-{m}:</b> {t} ({p}/{n})</div>",unsafe_allow_html=True)
                if not ok: allow=False
            
            if allow:
                rpt=f"""<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'>Pt:{nm} | MRN:{mr}<hr>Anti-{', '.join(match)} Detected.<br>Probability Confirmed.<br><br>Sig: __________</div><div class='footer-sig'>Dr. Haitham Ismail</div></div><script>window.print()</script>"""
                st.markdown(rpt,unsafe_allow_html=True)
            else:
                with st.expander("➕ Add Cell"):
                    id=st.text_input("ID"); rr=st.selectbox("R",["Neg","Pos"]); ph={}
                    cols=st.columns(len(match))
                    for i,mm in enumerate(match): ph[mm]=1 if cols[i].checkbox(mm) else 0
                    if st.button("Add"):
                        st.session_state.ext.append({"src":id,"s":1 if rr=="Pos" else 0,"ph":ph,"res":1}); st.rerun()
