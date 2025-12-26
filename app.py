import streamlit as st
import pandas as pd
import io
from datetime import date

# ==========================================
# 1. SETUP
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Blood Bank", layout="wide", page_icon="🏥")

# STYLE & PRINT FIXES
st.markdown("""
<style>
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .block-container { padding: 0 !important; }
        .print-only { display: block !important; }
        .results-box { border: 2px solid #333; padding: 15px; margin-top: 20px; font-family: 'Times New Roman'; font-size:14px;}
        .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; }
    }
    
    .hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    .signature-badge { position: fixed; bottom: 10px; right: 15px; background: rgba(255,255,255,0.9); padding: 5px 10px; border: 1px solid #eecaca; z-index:99; } 
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    
    .status-pass { background-color: #d1e7dd; padding: 8px; border-radius: 5px; color: #0f5132; margin-bottom:5px; border-left: 5px solid #198754; } 
    .status-fail { background-color: #f8d7da; padding: 8px; border-radius: 5px; color: #842029; margin-bottom:5px; border-left: 5px solid #dc3545; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='signature-badge no-print'><small><b>Dr. Haitham Ismail</b><br>Clinical Consultant</small></div>", unsafe_allow_html=True)

# DATA STRUCTS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]

# ALIASES DICT FOR PDF
ALIAS_MAP = {
    "RH(D)":"D", "RHD":"D", "RH1":"D",
    "RH'":"C", "RHC":"C", "RH2":"C",
    "RH''":"E", "RHE":"E", "RH3":"E",
    "HR'":"c", "RHC2":"c", "RH4":"c",
    "HR''":"e", "RHE2":"e", "RH5":"e",
    "K1":"K", "KEL1":"K", "KELL":"K",
    "K2":"k", "KEL2":"k", "CELLANO":"k",
    "FY(A)":"Fya", "FY1":"Fya",
    "FY(B)":"Fyb", "FY2":"Fyb",
    "JK(A)":"Jka", "JK1":"Jka",
    "JK(B)":"Jkb", "JK2":"Jkb",
    "LE(A)":"Lea", "LE1":"Lea",
    "LE(B)":"Leb", "LE2":"Leb",
    "MN":"M", "MNS1":"M",
    "MNS2":"N", "MNS3":"S", "MNS4":"s"
}

# STATES
if 'p11' not in st.session_state: st.session_state.p11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state: st.session_state.p3 = pd.DataFrame([{"ID": f"Scn {i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'res' not in st.session_state: st.session_state.res = {i:"Neg" for i in range(1,12)}
if 'scr' not in st.session_state: st.session_state.scr = {f"s{i}":"Neg" for i in ["I","II","III"]}
if 'ext' not in st.session_state: st.session_state.ext = []

# ==========================================
# 2. LOGIC: THE NUCLEAR PARSER
# ==========================================
def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

def clean_txt(t):
    return str(t).upper().replace("(","").replace(")","").replace(" ","").replace("\n","").strip()

def match_ag(val):
    val = clean_txt(val)
    if val in AGS: return val
    if val in ALIAS_MAP: return ALIAS_MAP[val]
    # Hard checks
    if val == "C": return "C"
    if val == "c": return "c" # Case issues usually handled by checking order or row context
    return None

def nuclear_parser(file, row_limit):
    try:
        # Load all sheets
        xls = pd.ExcelFile(file)
        
        # Iterate sheets to find data
        for sheet in xls.sheet_names:
            df = pd.read_excel(file, sheet_name=sheet, header=None)
            
            # A. FIND HEADER ROW
            head_idx = -1
            col_idx_map = {}
            
            # Scan first 30 rows
            for r in range(min(30, len(df))):
                temp_map = {}
                count = 0
                for c in range(min(60, len(df.columns))):
                    raw = df.iloc[r, c]
                    matched = match_ag(raw)
                    if matched and matched not in temp_map:
                        temp_map[matched] = c
                        count += 1
                
                # Confidence: If we found D, C, and E/e/c/K, it's the header
                required = ['D','C'] 
                has_req = sum(1 for x in required if x in temp_map)
                
                if count >= 3 and has_req >= 1:
                    head_idx = r
                    col_idx_map = temp_map
                    # Broad search in this row for missing antigens
                    for c2 in range(len(df.columns)):
                        raw2 = df.iloc[r, c2]
                        matched2 = match_ag(raw2)
                        if matched2 and matched2 not in col_idx_map:
                            col_idx_map[matched2] = c2
                    break
            
            if head_idx == -1: continue # Try next sheet
            
            # B. EXTRACT ROWS
            final = []
            extracted = 0
            curr = head_idx + 1
            
            while extracted < row_limit and curr < len(df):
                # Is valid row? Check column D
                d_idx = col_idx_map.get("D")
                valid_row = False
                
                if d_idx is not None:
                    check_val = str(df.iloc[curr, d_idx]).lower()
                    if any(c in check_val for c in ['+', '0', '1', 'w']): valid_row=True
                
                if valid_row:
                    if row_limit == 3: cid = f"Scn {['I','II','III'][extracted]}"
                    else: cid = f"Cell {extracted+1}"
                    
                    row_data = {"ID": cid}
                    for ag in AGS:
                        v = 0
                        if ag in col_idx_map:
                            raw_v = df.iloc[curr, col_idx_map[ag]]
                            v = normalize(raw_v)
                        row_data[ag] = int(v)
                    final.append(row_data)
                    extracted += 1
                
                curr += 1
                
            if extracted >= 1: # Found something
                # Fix length if not 11 (pad with empty?)
                return pd.DataFrame(final), f"Success from '{sheet}'! ({extracted} rows)"
                
        return None, "Structure not found in any sheet. Please edit manually."
        
    except Exception as e:
        return None, f"Parse Error: {e}"

# LOGIC FUNCTIONS
def get_pheno(df, idx):
    return df.iloc[idx].to_dict()

def can_out(ag, pheno):
    if pheno.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr = PAIRS.get(ag)
        if pr and pheno.get(pr,0)==1: return False
    return True

def chk_rule(c, rp, ip, rs, ins, ex):
    p, n = 0, 0
    # Panel
    for i in range(1,12):
        s = 1 if ip[i]!="Neg" else 0
        h = rp[i-1].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    for i,l in enumerate(["I","II","III"]):
        s = 1 if ins[f"s{l}"]!="Neg" else 0
        h = rs[i].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Ext
    for x in ex:
        if x['s']==1 and x['p'].get(c,0)==1: p+=1
        if x['s']==0 and x['p'].get(c,0)==0: n+=1
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    txt = "Std Rule" if (p>=3 and n>=3) else ("Mod Rule" if ok else "Fail")
    return ok, p, n, txt

# ==========================================
# 3. INTERFACE
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=60)
    nav = st.radio("Menu", ["Workstation", "Admin Setup"])
    if st.button("Reset All"): 
        st.session_state.ext = []
        st.rerun()

# ----------------- ADMIN -----------------
if nav == "Admin Setup":
    st.title("🛠️ Master Config")
    if st.text_input("Password", type="password") == "admin123":
        
        t1, t2 = st.tabs(["Panel 11 Setup", "Screening Setup"])
        
        with t1:
            st.info("Upload Panel (Excel from PDF)")
            u1 = st.file_uploader("Upload P11", type=["xlsx"])
            if u1:
                df1, m1 = nuclear_parser(io.BytesIO(u1.getvalue()), 11)
                if df1 is not None:
                    st.success(m1)
                    st.session_state.p11 = df1
                    st.rerun()
                else: st.error(m1)
            st.write("Edit:")
            ed1 = st.data_editor(st.session_state.p11, hide_index=True)
            if st.button("Save P11"): st.session_state.p11 = ed1; st.success("Saved")
            
        with t2:
            st.info("Upload Screen (Excel)")
            u2 = st.file_uploader("Upload P3", type=["xlsx"])
            if u2:
                df2, m2 = nuclear_parser(io.BytesIO(u2.getvalue()), 3)
                if df2 is not None:
                    st.success(m2)
                    st.session_state.p3 = df2
                    st.rerun()
                else: st.error(m2)
            st.write("Edit:")
            ed2 = st.data_editor(st.session_state.p3, hide_index=True)
            if st.button("Save Scr"): st.session_state.p3 = ed2; st.success("Saved")

# ----------------- USER -----------------
else:
    st.markdown("<div class='hospital-header'><h1>Maternity & Children Hospital - Tabuk</h1><h4>Serology Workstation</h4></div>", unsafe_allow_html=True)
    c1,c2,c3,c4=st.columns(4)
    nm=c1.text_input("Pt Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    L, R = st.columns([1, 2])
    with L:
        st.subheader("1. Screen")
        for x in ["I","II","III"]: st.session_state.scr[f"s{x}"]=st.selectbox(x,["Neg","w+","1+","2+"],key=f"u_{x}")
        st.write("---")
        if st.radio("Auto Control",["Negative","Positive"])=="Positive": st.error("DAT Required"); st.stop()
        if st.button("Set Neg"): 
            for i in range(1,12): st.session_state.res[i]="Neg"
            st.rerun()
            
    with R:
        st.subheader("2. Panel")
        cc = st.columns(6)
        in_map = {}
        for i in range(1,12):
            val = cc[(i-1)%6].selectbox(f"C{i}",["Neg","w+","1+","2+"],key=f"p_{i}",index=["Neg","w+","1+","2+"].index(st.session_state.res[i]))
            st.session_state.res[i] = val
            in_map[i] = 0 if val=="Neg" else 1
            
    st.divider()
    if st.checkbox("🔍 Analyze"):
        rp = [get_pheno(st.session_state.p11, i) for i in range(11)]
        rs = [get_pheno(st.session_state.p3, i) for i in range(3)]
        ruled = set()
        
        # Exclude Panel
        for ag in AGS:
            for i,s in in_map.items():
                if s==0 and can_out(ag, rp[i-1]): ruled.add(ag); break
        # Exclude Screen
        si = {"I":0,"II":1,"III":2}
        for k,v in st.session_state.scr.items():
            if v=="Neg":
                idx = si[k.replace("s","")]
                for ag in AGS: 
                    if ag not in ruled and can_out(ag, rs[idx]): ruled.add(ag)
        
        mt = []
        for c in [x for x in AGS if x not in ruled]:
            mis=False
            for i,s in in_map.items():
                if s>0 and rp[i-1].get(c,0)==0: mis=True
            if not mis: mt.append(c)
            
        if not mt: st.error("Inconclusive.")
        else:
            allow=True
            st.subheader("Results")
            for m in mt:
                ok,p,n,msg = chk_rule(m,rp,st.session_state.res,rs,st.session_state.scr,st.session_state.ext)
                st.markdown(f"<div class='status-{'pass' if ok else 'fail'}'><b>Anti-{m}:</b> {msg} ({p}/{n})</div>", unsafe_allow_html=True)
                if not ok: allow=False
            
            if allow:
                if st.button("🖨️ Print Report"):
                    ht=f"<div class='print-only'><center><h2>MCH Tabuk</h2></center><div class='results-box'>Pt: {nm} | MRN: {mr}<hr><b>Conclusion:</b> Anti-{', '.join(mt)} Detected.<br>Probability Valid.<br><br>Sig: ___________</div></div><script>window.print()</script>"
                    st.markdown(ht,unsafe_allow_html=True)
            else:
                with st.expander("Add Cell"):
                    xc1,xc2=st.columns(2); nid=xc1.text_input("ID"); nr=xc2.selectbox("R",["Neg","Pos"]); ph={}
                    cx=st.columns(len(mt))
                    for i,m in enumerate(mt):
                        ph[m]=1 if cx[i].checkbox(m) else 0
                    if st.button("Add"):
                        st.session_state.ext.append({"src":nid,"s":1 if nr=="Pos" else 0,"res":1 if nr=="Pos" else 0,"p":ph,"ph":ph}); st.rerun()
