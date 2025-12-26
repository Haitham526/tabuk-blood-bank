import streamlit as st
import pandas as pd
import io

# ==========================================
# 1. SETUP
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🏥")

st.markdown("""
<style>
    @media print {
        .stApp > header, .sidebar, footer, .no-print, .element-container:has(button) { display: none !important; }
        .block-container { padding: 0 !important; }
        .print-only { display: block !important; }
        .results-box { border: 2px solid #333; padding: 15px; font-family: 'Times New Roman'; margin-top: 20px; }
        .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; }
    }
    .hospital-header { text-align: center; border-bottom: 5px solid #005f73; padding-bottom: 10px; font-family: 'Arial'; color: #003366; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
    
    .signature-badge {
        position: fixed; bottom: 10px; right: 15px; font-family: 'Georgia', serif; font-size: 12px; color: #8B0000;
        background: rgba(255,255,255,0.95); padding: 5px 10px; border: 1px solid #eecaca; border-radius: 5px; z-index:99;
    }
</style>
""", unsafe_allow_html=True)

# Footer
st.markdown("<div class='signature-badge no-print'><b>Dr. Haitham Ismail</b><br>Clinical Hematology/Transfusion Consultant</div>", unsafe_allow_html=True)

# DEFINITIONS
antigens_order = ["D", "C", "E", "c", "e", "Cw", "K", "k", "Kpa", "Kpb", "Jsa", "Jsb", "Fya", "Fyb", "Jka", "Jkb", "Lea", "Leb", "P1", "M", "N", "S", "s", "Lua", "Lub", "Xga"]
allele_pairs = {'C':'c', 'c':'C', 'E':'e', 'e':'E', 'K':'k', 'k':'K', 'Fya':'Fyb', 'Fyb':'Fya', 'Jka':'Jkb', 'Jkb':'Jka', 'M':'N', 'N':'M', 'S':'s', 's':'S'}
STRICT_DOSAGE = ["C", "c", "E", "e", "Fya", "Fyb", "Jka", "Jkb", "M", "N", "S", "s"]

# STATES
if 'panel_11' not in st.session_state:
    st.session_state.panel_11 = pd.DataFrame([{"ID": f"Cell {i+1}", **{ag: 0 for ag in antigens_order}} for i in range(11)])
if 'inputs' not in st.session_state: st.session_state.inputs = {f"c{i}": "Neg" for i in range(1, 12)}
if 'inputs_s' not in st.session_state: st.session_state.inputs_s = {f"s{i}": "Neg" for i in ["I","II","III"]}
if 'extra' not in st.session_state: st.session_state.extra = []
if 'admin_mode' not in st.session_state: st.session_state.admin_mode = False

# ==========================================
# 2. LOGIC FUNCTIONS
# ==========================================
def normalize_cell_value(val):
    s = str(val).lower().strip()
    # Logic: 1, +, +w, pos, yes -> 1
    # Logic: 0, nt, -, neg -> 0
    if '+' in s or '1' in s or 'pos' in s: return 1
    return 0

def deep_search_parser(file_bytes):
    # 1. Read entire file without header assumption
    df = pd.read_excel(file_bytes, header=None)
    
    header_idx = -1
    col_map = {} # {'D': 5, 'C': 6...} mapping antigen to column index
    
    # 2. Iterate first 20 rows to find a "signature"
    # We look for a row that contains multiple antigens
    for idx, row in df.iterrows():
        row_str = [str(x).strip() for x in row.values]
        
        # Clean checking
        matches = 0
        current_map = {}
        
        for col_i, cell_val in enumerate(row_str):
            clean_val = cell_val.replace("(","").replace(")","").strip()
            
            # Special check for 'c' and 'C' case sensitivity issues? 
            # BioRad uses "C" and "c" distinctly.
            if clean_val in antigens_order:
                matches += 1
                current_map[clean_val] = col_i
            elif clean_val == "Rh(D)": 
                matches += 1
                current_map["D"] = col_i
        
        # If this row has at least 4 antigens (confidence threshold)
        if matches >= 4:
            header_idx = idx
            col_map = current_map
            break
            
    if header_idx == -1:
        return None, "Header row not found (D, C, c, E...)"

    # 3. Extract Data starting from header_idx + 1
    extracted_data = []
    
    # Try to grab the next 11 rows
    start_data = header_idx + 1
    
    for i in range(11):
        actual_row_idx = start_data + i
        if actual_row_idx >= len(df): break
        
        row_values = df.iloc[actual_row_idx]
        
        cell_dict = {"ID": f"Cell {i+1}"}
        
        # For every expected antigen
        for ag in antigens_order:
            val = 0
            if ag in col_map:
                col_index = col_map[ag]
                raw_cell = row_values[col_index]
                val = normalize_cell_value(raw_cell)
            cell_dict[ag] = val
            
        extracted_data.append(cell_dict)
        
    return pd.DataFrame(extracted_data), None

# Common Helpers
def can_rule_out(ag, pheno):
    if pheno.get(ag,0)==0: return False
    if ag in STRICT_DOSAGE:
        p=allele_pairs.get(ag)
        if p and pheno.get(p,0)==1: return False
    return True

def check_r3(cand, rows, inpts, r3, in3, ex):
    pr,nr = 0,0
    for i in range(1,12):
        s=1 if inpts[i]!="Neg" else 0
        if rows[i-1].get(cand,0)==1 and s==1: pr+=1
        if rows[i-1].get(cand,0)==0 and s==0: nr+=1
    for i,s in enumerate(["I","II","III"]):
        sc=1 if in3[f"s{s}"]!="Neg" else 0
        if r3[i].get(cand,0)==1 and sc==1: pr+=1
        if r3[i].get(cand,0)==0 and sc==0: nr+=1
    for c in ex:
        if c['s']==1 and c['p'].get(cand,0)==1: pr+=1
        if c['s']==0 and c['p'].get(cand,0)==0: nr+=1
    ok=(pr>=3 and nr>=3) or (pr>=2 and nr>=3)
    mt="Standard" if (pr>=3 and nr>=3) else ("Modified" if ok else "Fail")
    return ok,pr,nr,mt

def bulk(v): 
    for i in range(1,12): st.session_state.inputs[f"c{i}"]=v

# ==========================================
# 3. SIDEBAR & LOGIC
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png",width=60)
    st.caption("V23.1 Deep Scan")
    app_mode = st.radio("Menu",["Workstation","Supervisor"])
    st.write("---")
    if st.button("Reset Extras"):
        st.session_state.extra=[]
        st.rerun()

# --------- ADMIN ---------
if app_mode == "Supervisor":
    st.title("🛠️ Master Config (Deep Scan)")
    pwd=st.text_input("Password",type="password")
    
    if pwd == "admin123":
        t1,t2=st.tabs(["Panel 11","Screen"])
        with t1:
            st.info("Upload ANY Excel file. The system will hunt for the grid.")
            up = st.file_uploader("Upload Excel", type=['xlsx'])
            
            if up:
                # Use IO buffer to prevent read errors
                bytes_data = up.getvalue()
                
                # CALL THE NEW PARSER
                new_df, error_msg = deep_search_parser(io.BytesIO(bytes_data))
                
                if new_df is not None:
                    st.success("✅ Smart Parser Success! Table updated.")
                    st.session_state.panel_11 = new_df
                    if st.button("Force Refresh View"): st.rerun()
                else:
                    st.error(f"❌ Scan Failed: {error_msg}")
                    # DEBUGGER
                    with st.expander("🕵️ Debug: See Raw File content"):
                        st.write("If the parser failed, check what Python actually sees below:")
                        st.dataframe(pd.read_excel(io.BytesIO(bytes_data), header=None).head(15))

            st.write("### Current Grid:")
            # Display current data
            st.session_state.panel_11 = st.data_editor(
                st.session_state.panel_11, 
                height=400, use_container_width=True, hide_index=True
            )
            
        with t2:
            st.session_state.panel_3=st.data_editor(st.session_state.panel_3, hide_index=True)
            
    elif pwd: st.error("Invalid.")

# --------- USER ---------
else:
    st.markdown("""<div class='hospital-header'><h1>Maternity & Children Hospital - Tabuk</h1><h4>Serology Workstation</h4></div>""", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mrn=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    st.divider()
    
    L,R=st.columns([1,2])
    with L:
        st.subheader("1. Control")
        if st.radio("AC",["Neg","Pos"],horizontal=True)=="Pos":
            st.error("DAT Required (WAIHA/DHTR Check)."); st.stop()
        for x in ["I","II","III"]:
            k=f"s{x}"
            st.session_state.inputs_s[k]=st.selectbox(x,["Neg","w+","1+","2+"],key=f"u_{x}")
        if st.button("Set Neg"): bulk("Neg")
        if st.button("Set Pos"): bulk("2+")
    
    with R:
        st.subheader("2. Panel")
        mp={}
        cols=st.columns(6)
        for i in range(1,12):
            k=f"c{i}"
            v=cols[(i-1)%6].selectbox(f"C{i}",["Neg","w+","1+","2+","3+"],key=f"p_{i}", index=["Neg","w+","1+","2+","3+"].index(st.session_state.inputs[k]))
            st.session_state.inputs[k]=v
            mp[i]=0 if v=="Neg" else 1
            
    st.divider()
    if st.checkbox("🔍 Analyze"):
        r11=[st.session_state.panel_11.iloc[i].to_dict() for i in range(11)]
        r3=[st.session_state.panel_3.iloc[i].to_dict() for i in range(3)]
        
        ruled=set()
        for ag in antigens_order:
            for idx,sc in mp.items():
                if sc==0 and can_rule_out(ag, r11[idx-1]): ruled.add(ag); break
        
        scr_map={"I":0,"II":1,"III":2}
        for k,v in st.session_state.inputs_s.items():
            if v=="Neg":
                sidx=scr_map[k[1:]]
                for ag in antigens_order:
                    if ag not in ruled and can_rule_out(ag, r3[sidx]): ruled.add(ag)
        
        match=[]
        for c in [x for x in antigens_order if x not in ruled]:
            mis=False
            for idx,sc in mp.items():
                if sc>0 and r11[idx-1].get(c,0)==0: mis=True
            if not mis: match.append(c)
            
        if not match: st.error("No Match/Inconclusive")
        else:
            allow=True
            for m in match:
                pas,p,n,met = check_r3(m,r11,st.session_state.inputs,r3,st.session_state.inputs_s,st.session_state.extra)
                st.markdown(f"<div class='status-{'pass' if pas else 'fail'}'><b>Anti-{m}:</b> {met} ({p}/{n})</div>", unsafe_allow_html=True)
                if not pas: allow=False
            
            if allow:
                if st.button("🖨️ Report"):
                    rpt=f"<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'>Pt:{nm} ({mrn})<hr>Result: Anti-{', '.join(match)}<br>Valid Rule of 3.<br>Clinical: Phenotype Negative Required.<br><br>Sig: ___________</div><div class='consultant-footer'><span style='color:darkred;font-weight:bold'>Dr. Haitham Ismail</span></div></div><script>window.print()</script>"
                    st.markdown(rpt, unsafe_allow_html=True)
            else:
                st.info("Rule Not Met. Add Extra Cells:")
                with st.expander("Add Cell"):
                    xc1,xc2=st.columns(2); id=xc1.text_input("ID"); rs=xc2.selectbox("R",["Neg","Pos"])
                    ph={}
                    cl=st.columns(len(match))
                    for i,m in enumerate(match):
                        r=cl[i].radio(m,["+","0"],key=f"e_{m}")
                        ph[m]=1 if r=="+" else 0
                    if st.button("Confirm"):
                        st.session_state.extra.append({"src":id,"score":1 if rs=="Pos" else 0,"pheno":ph,"s":1 if rs=="Pos" else 0})
                        st.rerun()
