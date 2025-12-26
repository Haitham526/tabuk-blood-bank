import streamlit as st
import pandas as pd
import io
from datetime import date

# 1. SETUP
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🏥")

st.markdown("""
<style>
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .block-container { padding: 0 !important; }
        .print-only { display: block !important; }
        .results-box { border: 2px solid #333; padding: 15px; font-family: 'Times New Roman'; font-size:14px;}
        .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; }
    }
    .hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    .signature-badge { position: fixed; bottom: 10px; right: 15px; font-family: 'Georgia', serif; font-size: 12px; color: #8B0000; background: rgba(255,255,255,0.95); padding: 5px 10px; border: 1px solid #eecaca; border-radius: 5px; z-index:99; } 
    div[data-testid="stDataEditor"] table { width: 100% !important; } 
    .status-pass { background-color: #d1e7dd; padding: 10px; border-radius: 5px; color: #0f5132; margin-bottom:5px; } 
    .status-fail { background-color: #f8d7da; padding: 10px; border-radius: 5px; color: #842029; margin-bottom:5px; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='signature-badge no-print'><b>Dr. Haitham Ismail</b><br>Clinical Hematology/Transfusion Consultant</div>", unsafe_allow_html=True)

antigens_order = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
allele_pairs = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Kpa':'Kpb', 'Kpb':'Kpa', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S', 'Lea':'Leb', 'Leb':'Lea'}
STRICT_DOSAGE = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]

# STATE
if 'panel_11' not in st.session_state:
    st.session_state.panel_11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in antigens_order}} for i in range(11)])
if 'panel_3' not in st.session_state:
    st.session_state.panel_3 = pd.DataFrame([{"ID": f"Scn {i}", **{ag: 0 for ag in antigens_order}} for i in ["I", "II", "III"]])
if 'inputs' not in st.session_state: st.session_state.inputs = {f"c{i}": "Neg" for i in range(1, 12)}
if 'inputs_s' not in st.session_state: st.session_state.inputs_s = {f"s{i}": "Neg" for i in ["I", "II", "III"]}
if 'extra_cells' not in st.session_state: st.session_state.extra_cells = []
if 'admin_mode' not in st.session_state: st.session_state.admin_mode = False

# 2. STRICT ROW PARSER (The Logic Fix)
def clean_header(val):
    # ينظف النص عشان يطابق اسماء الانتيجينات
    return str(val).strip().replace("\n","").replace(" ","").replace("(","").replace(")","")

def normalize_val(val):
    # تنظيف قيم الداتا (+ و 0)
    s = str(val).lower().strip()
    # لو الخلية فيها +w أو + او 1 أو Pos
    if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']): return 1
    return 0

def strict_scan(file_bytes):
    xls = pd.ExcelFile(file_bytes)
    
    # هنبحث في كل الصفحات
    for sheet in xls.sheet_names:
        df = pd.read_excel(file_bytes, sheet_name=sheet, header=None)
        
        # 1. البحث عن "السطر الذهبي" (سطر العناوين)
        # هذا السطر يجب أن يحتوي على أكبر عدد من الانتيجينات الصحيحة
        best_row_idx = -1
        best_row_matches = 0
        best_col_map = {}
        
        for r in range(min(20, len(df))): # نفحص اول 20 سطر فقط
            row_map = {}
            match_count = 0
            
            for c in range(len(df.columns)):
                cell_val = clean_header(df.iloc[r, c])
                
                # Check Match
                # Exact match?
                real_name = None
                if cell_val in antigens_order: real_name = cell_val
                # Common Variants in PDF conversion
                elif cell_val.upper() in ["RHD","D"]: real_name = "D"
                elif cell_val.upper() in ["RHC","C"]: real_name = "C"
                elif cell_val.upper() in ["RHE","E"]: real_name = "E"
                elif cell_val.upper() in ["RHC","HR'","c"]: real_name = "c" # Case sensitivity might fail, depend on context
                
                # C vs c distinction issue: BioRad uses capital letters clearly in header
                # We assume if the parser finds "C" and "c", it maps them correctly
                # based on case sensitivity of clean_header() result.
                
                if real_name:
                    row_map[real_name] = c
                    match_count += 1
            
            if match_count > best_row_matches:
                best_row_matches = match_count
                best_row_idx = r
                best_col_map = row_map
        
        # 2. EXTRACT DATA if we found a good header row (at least 5 antigens)
        if best_row_matches >= 5:
            # We trust 'best_row_idx' is the header
            # Data starts immediately after header usually
            start_data = best_row_idx + 1
            
            final_data = []
            valid_cnt = 0
            curr = start_data
            
            while valid_cnt < 11 and curr < len(df):
                # Is this a valid row? Look at D value
                is_valid = False
                d_val = ""
                # Try to check columns D or C to confirm it's a data row
                check_cols = [best_col_map.get("D"), best_col_map.get("C")]
                check_cols = [x for x in check_cols if x is not None]
                
                for cc in check_cols:
                    val_check = str(df.iloc[curr, cc]).lower()
                    if any(x in val_check for x in ['+', '0', '1', 'w']):
                        is_valid = True; break
                
                if is_valid:
                    row_dict = {"ID": f"Cell {valid_cnt+1}"}
                    for ag in antigens_order:
                        # Default 0
                        v = 0
                        if ag in best_col_map:
                            col_idx = best_col_map[ag]
                            raw_val = df.iloc[curr, col_idx]
                            v = normalize_val(raw_val)
                        row_dict[ag] = int(v)
                    
                    final_data.append(row_dict)
                    valid_cnt += 1
                curr += 1
            
            if valid_cnt >= 11:
                return pd.DataFrame(final_data), f"Success: Found {best_row_matches} antigens on Row {best_row_idx+1}"

    return None, "Parser failed to align columns."

# Logic
def can_rule_out(ag, pheno):
    if pheno.get(ag,0)==0: return False
    if ag in STRICT_DOSAGE:
        p=allele_pairs.get(ag)
        if p and pheno.get(p,0)==1: return False
    return True

def bulk_set(val): 
    for i in range(1,12): st.session_state.inputs[f"c{i}"]=val

def check_r3(cand, r, inp, rs, iscn, ex):
    pr,nr=0,0
    for i in range(1,12):
        s=1 if inp[i]!="Neg" else 0
        h=r[i-1].get(cand,0)
        if h==1 and s==1: pr+=1
        if h==0 and s==0: nr+=1
    for i,l in enumerate(["I","II","III"]):
        s=1 if iscn[f"s{l}"]!="Neg" else 0
        h=rs[i].get(cand,0)
        if h==1 and s==1: pr+=1
        if h==0 and s==0: nr+=1
    for c in ex:
        if c['s']==1 and c['p'].get(cand,0)==1: pr+=1
        if c['s']==0 and c['p'].get(cand,0)==0: nr+=1
    res=(pr>=3 and nr>=3) or (pr>=2 and nr>=3)
    mt="Standard" if (pr>=3 and nr>=3) else "Modified"
    return res,pr,nr,mt

# 3. SIDEBAR
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png",width=60)
    nav=st.radio("Go To", ["Workstation", "Supervisor"])
    st.write("---")
    if st.button("Reset Extras"): st.session_state.extra_cells=[]; st.rerun()

# 4. SUPERVISOR
if nav == "Supervisor":
    st.title("🛠️ Master Config (Row-Lock Tech)")
    if st.text_input("Password", type="password")=="admin123":
        t1, t2 = st.tabs(["Panel 11", "Screen"])
        with t1:
            st.info("Upload PDF-Converted Excel")
            up=st.file_uploader("Upload",type=['xlsx'])
            if up:
                df,msg=strict_scan(io.BytesIO(up.getvalue()))
                if df is not None:
                    st.success(msg)
                    st.session_state.panel_11=df
                    if st.button("Refresh View"): st.rerun()
                else: st.error(msg)
            st.write("### Data Grid:")
            edt=st.data_editor(st.session_state.panel_11.fillna(0), hide_index=True, use_container_width=True, height=450)
            if st.button("Save Grid"): st.session_state.panel_11=edt; st.success("Saved")
        with t2:
            st.session_state.panel_3=st.data_editor(st.session_state.panel_3, hide_index=True)

# 5. USER
else:
    st.markdown("""<div class='hospital-header'><h1>Maternity & Children Hospital - Tabuk</h1><h4>Serology Workstation</h4></div>""", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mrn=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    L,R=st.columns([1,2])
    with L:
        ac=st.radio("AC",["Negative","Positive"]); 
        if ac=="Positive": st.error("STOP: Check DAT"); st.stop()
        for x in ["I","II","III"]: st.session_state.inputs_s[f"s{x}"]=st.selectbox(x,["Neg","Pos"],key=f"su_{x}")
        if st.button("Neg"): bulk_set("Neg")
    with R:
        cols=st.columns(6)
        in_map={}
        for i in range(1,12):
            k=f"c{i}"
            v=cols[(i-1)%6].selectbox(f"C{i}",["Neg","Pos"],key=f"pu_{i}",index=["Neg","Pos"].index(st.session_state.inputs[k]))
            st.session_state.inputs[k]=v
            in_map[i]=0 if v=="Neg" else 1
    
    st.divider()
    if st.checkbox("Run Analysis"):
        r11=[st.session_state.panel_11.iloc[i].to_dict() for i in range(11)]
        r3=[st.session_state.panel_3.iloc[i].to_dict() for i in range(3)]
        ruled=set()
        for ag in antigens_order:
            for idx,sc in in_map.items():
                if sc==0 and can_rule_out(ag, r11[idx-1]): ruled.add(ag); break
        scrm={"I":0,"II":1,"III":2}
        for k,v in st.session_state.inputs_s.items():
            if v=="Neg":
                for ag in antigens_order:
                    if ag not in ruled and can_rule_out(ag, r3[scrm[k[1:]]]): ruled.add(ag)
        
        matches=[]
        for c in [x for x in antigens_order if x not in ruled]:
            mis=False
            for i,s in in_map.items():
                if s>0 and r11[i-1].get(c,0)==0: mis=True
            if not mis: matches.append(c)
            
        if not matches: st.error("Inconclusive.")
        else:
            ok_all=True
            for m in matches:
                pas,p,n,met = check_r3(m,r11,st.session_state.inputs,r3,st.session_state.inputs_s,st.session_state.extra_cells)
                st.markdown(f"<div class='status-{'pass' if pas else 'fail'}'><b>Anti-{m}:</b> {met} ({p} P/{n} N)</div>", unsafe_allow_html=True)
                if not pas: ok_all=False
            if ok_all:
                if st.button("Print"):
                    h=f"<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'>Pt: {nm}<hr>Res: Anti-{', '.join(matches)}<br>Verified.<br><br>Sig: ________</div><div class='consultant-footer'><span style='color:darkred;font-weight:bold'>Dr. Haitham Ismail</span></div></div><script>window.print()</script>"
                    st.markdown(h, unsafe_allow_html=True)
            else:
                with st.expander("Add Extra Cell"):
                    i1,i2=st.columns(2); id=i1.text_input("ID"); rs=i2.selectbox("R",["Neg","Pos"])
                    ph={}; cs=st.columns(len(matches))
                    for i,m in enumerate(matches):
                        rx=cs[i].radio(m,["+","0"],key=f"exx_{m}")
                        ph[m]=1 if rx=="+" else 0
                    if st.button("Confirm"):
                        st.session_state.extra_cells.append({"src":id,"score":1 if rs=="Pos" else 0,"pheno":ph,"s":1 if rs=="Pos" else 0}); st.rerun()
