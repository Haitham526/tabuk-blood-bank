import streamlit as st
import pandas as pd
import io
from datetime import date

# ==========================================
# 1. SETUP
# ==========================================
st.set_page_config(page_title="MCH Tabuk Serology", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .block-container { padding: 0 !important; } .print-only { display: block !important; } .results-box { border: 2px solid #333; padding: 20px; font-family: 'Times New Roman'; } .footer-sig { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #aaa; } }
    .print-only { display: none; }
    
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    
    .status-box { padding: 10px; border-radius: 5px; color: #fff; margin: 5px 0; }
    .hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: sans-serif; color: #003366; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='no-print' style='position:fixed; bottom:5px; right:10px; border:1px solid #ccc; background:#fff; padding:5px; border-radius:5px;'>Dr. Haitham Ismail | Consultant</div>", unsafe_allow_html=True)

# ----------------- DATA DEFINITIONS -----------------
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# Case Sensitive Watchlist (These MUST match exactly)
CASE_SENSITIVE = ["C", "c", "E", "e", "K", "k", "S", "s"]

if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a: 0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a: 0 for a in AGS}} for i in ["I","II","III"]])
if 'res' not in st.session_state: st.session_state.res = {f"c{i}": "Neg" for i in range(1, 12)}
if 'scr' not in st.session_state: st.session_state.scr = {f"s{i}": "Neg" for i in ["I", "II", "III"]}
if 'ext' not in st.session_state: st.session_state.ext = []

# ==========================================
# 2. SURGICAL PARSER (The Fixer)
# ==========================================
def clean_val(val):
    # Keep original case for sensitive letters
    return str(val).strip().replace(" ","").replace("\n","").replace("(","").replace(")","")

def get_value_from_cell(cell_val):
    # Translate Excel content to 0/1
    s = str(cell_val).lower().strip()
    # Handles: "+", "+w", "1", "pos", "w+"
    if '+' in s or '1' in s or 'pos' in s or 'w' in s: return 1
    return 0

def surgical_parse(file_bytes, row_limit):
    try:
        xls = pd.ExcelFile(file_bytes)
        
        # Loop Sheets
        for sheet in xls.sheet_names:
            df = pd.read_excel(file_bytes, sheet_name=sheet, header=None)
            
            # 1. MAP COLUMNS PRECISELY
            col_map = {}
            header_row = -1
            
            # Scan top 30 rows
            for r in range(min(30, len(df))):
                temp_map = {}
                count = 0
                for c in range(len(df.columns)):
                    val = clean_val(df.iloc[r, c])
                    
                    found_ag = None
                    
                    # A. Strict Case Check
                    if val in CASE_SENSITIVE:
                        found_ag = val 
                    
                    # B. Normal Check (Upper is fine)
                    else:
                        v_up = val.upper()
                        # Direct match for non-sensitive (e.g., Fya, Jka)
                        if v_up in [x.upper() for x in AGS if x not in CASE_SENSITIVE]:
                            # Map back to official case (FYA -> Fya)
                            for ref in AGS:
                                if ref.upper() == v_up: found_ag = ref
                        # Common aliases
                        elif v_up in ["RHD","D"]: found_ag = "D"
                    
                    if found_ag and found_ag not in temp_map:
                        temp_map[found_ag] = c
                        count += 1
                
                # Check Header Quality
                # We need D and (C or c) to be sure
                if "D" in temp_map and count >= 4:
                    header_row = r
                    col_map = temp_map
                    break
            
            if header_row == -1: continue # Try next sheet
            
            # 2. EXTRACT DATA ROWS (Guided by Column D)
            # Find the row where data starts by checking Col D
            # Start checking 1 row below header
            final_data = []
            curr = header_row + 1
            got = 0
            
            d_idx = col_map["D"]
            
            while got < row_limit and curr < len(df):
                d_cell = str(df.iloc[curr, d_idx]).lower()
                
                # Check if this row looks like data
                # Does column D contain: 0, +, 1, or w ?
                if any(x in d_cell for x in ['0', '+', '1', 'w']):
                    
                    lbl = f"Cell {got+1}" if row_limit==11 else f"Scn {['I','II','III'][got]}"
                    r_dic = {"ID": lbl}
                    
                    for ag in AGS:
                        v = 0
                        if ag in col_map:
                            raw = df.iloc[curr, col_map[ag]]
                            v = get_value_from_cell(raw)
                        r_dic[ag] = int(v)
                    
                    final_data.append(r_dic)
                    got += 1
                
                curr += 1
                
            if got >= 1:
                return pd.DataFrame(final_data), f"Matched {len(col_map)} Cols from '{sheet}'."
                
        return None, "Format not recognized."
    except Exception as e: return None, str(e)

# ----------------- LOGIC -----------------
def can_out(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr=PAIRS.get(ag)
        if pr and ph.get(pr,0)==1: return False
    return True

def chk_rule(c, rp, ip, rs, iscr, ex):
    p, n = 0, 0
    # Panel
    for i in range(1, 12):
        s = 1 if ip[f"c{i}"]!="Neg" else 0
        h = rp.iloc[i-1].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    for i, x in enumerate(["I","II","III"]):
        s = 1 if iscr[f"s{x}"]!="Neg" else 0
        h = rs.iloc[i].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extra
    for x in ex:
        if x['s']==1 and x['ph'].get(c,0)==1: p+=1
        if x['s']==0 and x['ph'].get(c,0)==0: n+=1
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    t = "Standard" if (p>=3 and n>=3) else "Modified"
    return ok, p, n, t

def bulk(v): 
    for i in range(1,12): st.session_state.res[f"c{i}"]=v

# ==========================================
# 3. SIDEBAR & INTERFACE
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png",width=50)
    nav = st.radio("Menu", ["Workstation", "Supervisor Config"])
    if st.button("Reset All"): 
        st.session_state.ext=[]; st.rerun()

# --- ADMIN ---
if nav == "Supervisor Config":
    st.title("🛠️ Master Configuration")
    if st.text_input("Password",type="password")=="admin123":
        t1,t2=st.tabs(["Panel 11","Screen"])
        
        with t1:
            st.info("Upload PDF-Converted Excel")
            u1=st.file_uploader("Upload Panel 11",type=["xlsx"])
            if u1:
                df,m = surgical_parse(io.BytesIO(u1.getvalue()), 11)
                if df is not None:
                    st.success(f"✅ {m}")
                    st.session_state.p11 = df.fillna(0).astype(object) # object types prevent visual bugs
                    st.rerun()
                else: st.error(m)
            
            st.write("#### Grid Preview:")
            # Display without editing key errors
            save1 = st.data_editor(st.session_state.p11, hide_index=True)
            if st.button("Save Changes"): st.session_state.p11=save1; st.success("Saved")
            
        with t2:
            st.info("Upload Screen")
            u2=st.file_uploader("Upload Screen 3",type=["xlsx"])
            if u2:
                df2,m2 = surgical_parse(io.BytesIO(u2.getvalue()), 3)
                if df2 is not None:
                    st.success(m2)
                    st.session_state.p3 = df2.fillna(0).astype(object)
                    st.rerun()
            save2 = st.data_editor(st.session_state.p3, hide_index=True)
            if st.button("Save Scr"): st.session_state.p3=save2; st.success("Saved")

# --- USER ---
else:
    st.markdown("<h2 class='hospital-header'>Maternity & Children Hospital - Tabuk</h2>", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mrn=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    L, R = st.columns([1, 2])
    with L:
        ac = st.radio("Auto Control", ["Negative","Positive"], horizontal=True)
        if ac=="Positive": st.error("STOP: DAT Required"); st.stop()
        st.write("---")
        for x in ["I","II","III"]: st.session_state.scr[f"s{x}"]=st.selectbox(f"Scn {x}",["Neg","w+","1+","2+"], key=f"s_{x}")
        if st.button("Set Neg"): bulk("Neg")
    with R:
        cols=st.columns(6)
        in_map={}
        for i in range(1,12):
            v=cols[(i-1)%6].selectbox(f"C{i}",["Neg","w+","1+","2+"],key=f"p_{i}",index=0 if st.session_state.res[f"c{i}"]=="Neg" else 1)
            st.session_state.res[f"c{i}"]=v
            in_map[i] = 0 if v=="Neg" else 1
            
    st.divider()
    if st.checkbox("🔍 Analyze"):
        p11_ls = [st.session_state.p11.iloc[i].to_dict() for i in range(11)]
        p3_ls  = [st.session_state.p3.iloc[i].to_dict() for i in range(3)]
        ruled=set()
        
        # Ruleout Panel
        for ag in AGS:
            for i,s in in_map.items():
                if s==0 and can_out(ag, p11_ls[i-1]): ruled.add(ag); break
        # Ruleout Screen
        s_idx={"I":0,"II":1,"III":2}
        for k,v in st.session_state.scr.items():
            if v=="Neg":
                idx=s_idx[k.replace("s","")]
                for ag in AGS:
                    if ag not in ruled and can_out(ag, p3_ls[idx]): ruled.add(ag)
        
        matches=[]
        for c in [x for x in AGS if x not in ruled]:
            mis=False
            for i,s in in_map.items():
                if s>0 and p11_ls[i-1].get(c,0)==0: mis=True
            if not mis: matches.append(c)
            
        if not matches: st.error("Inconclusive.")
        else:
            allow=True
            st.subheader("Result")
            for m in matches:
                ok,p,n,txt=chk_rule(m,st.session_state.p11,st.session_state.res,st.session_state.p3,st.session_state.scr,st.session_state.ext)
                bg="#d4edda" if ok else "#f8d7da"
                st.markdown(f"<div style='background:{bg};padding:10px;margin:5px;border-radius:5px'><b>Anti-{m}:</b> {txt} ({p} P / {n} N)</div>",unsafe_allow_html=True)
                if not ok: allow=False
            
            if allow:
                if st.button("🖨️ Print Report"):
                    ht=f"<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'>Pt: {nm}<br>Res: Anti-{', '.join(matches)}<br>Valid (Rule of 3)<br><br>Sig: _______</div><div class='footer-sig'>Dr. Haitham Ismail</div></div><script>window.print()</script>"
                    st.markdown(ht,unsafe_allow_html=True)
            else:
                with st.expander("➕ Add Cell"):
                    id=st.text_input("ID"); rs=st.selectbox("R",["Neg","Pos"]); ph={}
                    cx=st.columns(len(matches))
                    for i,m in enumerate(matches):
                        if cx[i].checkbox(m): ph[m]=1
                        else: ph[m]=0
                    if st.button("Add"):
                        st.session_state.ext.append({"src":id,"res":1 if rs=="Pos" else 0,"s":1 if rs=="Pos" else 0,"ph":ph,"pheno":ph})
                        st.rerun()
