import streamlit as st
import pandas as pd
import io

# ==========================================
# 1. SETUP
# ==========================================
st.set_page_config(page_title="MCH Tabuk - Serology", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { .stApp > header, .sidebar, footer, .no-print { display: none !important; } .print-only { display: block !important; } .results-box { border: 2px solid #333; padding: 20px; font-family: 'Times New Roman'; } .consultant-footer { position: fixed; bottom: 0; width: 100%; text-align: center; border-top: 1px solid #ccc; padding: 10px; } }
    .print-only { display: none; }
    .status-ok { background: #d1e7dd; padding: 8px; border-left: 5px solid green; margin: 5px 0; border-radius: 4px; }
    .status-no { background: #f8d7da; padding: 8px; border-left: 5px solid red; margin: 5px 0; border-radius: 4px; }
    div[data-testid="stDataEditor"] table { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='no-print' style='position:fixed;bottom:5px;right:10px;background:#fff;padding:5px;border:1px solid #ccc;z-index:99'>Dr. Haitham Ismail | Consultant</div>", unsafe_allow_html=True)

# DATA
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# STATE - INIT ONCE
if 'p11' not in st.session_state:
    st.session_state.p11 = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'p3' not in st.session_state:
    st.session_state.p3 = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'ext' not in st.session_state:
    st.session_state.ext = []

# ==========================================
# 2. LOGIC (PARSER THAT WORKED)
# ==========================================
def normalize(val):
    s = str(val).lower().strip()
    return 1 if any(x in s for x in ['+', '1', 'pos', 'yes', 'w']) else 0

def clean_txt(t): return str(t).upper().replace("(","").replace(")","").replace(" ","").strip()

def super_parser(file):
    try:
        xls = pd.ExcelFile(file)
        for sheet in xls.sheet_names:
            df = pd.read_excel(file, sheet_name=sheet, header=None)
            
            # Map
            col_map = {}
            head_row = -1
            
            for r in range(min(40, len(df))):
                temp = {}
                matches = 0
                for c in range(min(60, len(df.columns))):
                    raw = clean_txt(df.iloc[r, c])
                    det = None
                    # Strict Check
                    if raw in ["C","c","E","e","S","s","K","k"]: det=raw # Keep Case
                    elif raw in ["D","RHD"]: det="D"
                    else:
                        if raw in AGS: det=raw
                    
                    if det:
                        temp[det] = c
                        matches += 1
                
                if matches >= 3:
                    head_row = r
                    col_map = temp
                    break
            
            if head_row != -1:
                final = []
                count = 0
                curr = head_row + 1
                while count < 11 and curr < len(df):
                    is_valid = False
                    # Check around D column
                    center_d = col_map.get("D") or col_map.get("C")
                    if center_d is not None:
                        # WIDE CHECK (Center, Left, Right)
                        for off in [0, -1, 1]:
                            if 0 <= center_d+off < len(df.columns):
                                v_chk = str(df.iloc[curr, center_d+off]).lower()
                                if any(x in v_chk for x in ['+', '0', '1', 'w']): is_valid=True
                    
                    if is_valid:
                        rid = f"C{count+1}"
                        rd = {"ID": rid}
                        for ag in AGS:
                            v = 0
                            if ag in col_map:
                                c_idx = col_map[ag]
                                # Scan neighbors
                                scan_vals = []
                                for off in [0, -1, 1]:
                                    if 0 <= c_idx+off < len(df.columns):
                                        scan_vals.append(df.iloc[curr, c_idx+off])
                                
                                # If any is +/1, take it
                                if any(normalize(sv) for sv in scan_vals): v = 1
                            rd[ag] = int(v)
                        final.append(rd)
                        count += 1
                    curr += 1
                
                if count >= 1:
                    return pd.DataFrame(final), f"Success: {sheet} (Widened Scan)"
        
        return None, "Structure Not Found"
    except Exception as e: return None, str(e)

def can_out(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr=PAIRS.get(ag)
        if pr and ph.get(pr,0)==1: return False
    return True

def rule_check(c, p11, in_p, p3, in_s, ex):
    p, n = 0, 0
    # Panel
    for i in range(1, 12):
        s = 1 if in_p[i]!="Neg" else 0
        h = p11.iloc[i-1].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    scrs = ["I","II","III"]
    for i, l in enumerate(scrs):
        s = 1 if in_s[f"S-{l}"]!="Neg" else 0
        h = p3.iloc[i].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extra
    for x in ex:
        if x['s']==1 and x['ph'].get(c,0)==1: p+=1
        if x['s']==0 and x['ph'].get(c,0)==0: n+=1
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    t = "Standard Rule" if (p>=3 and n>=3) else ("Modified" if ok else "Fail")
    return ok, p, n, t

# ==========================================
# 3. INTERFACE (FORM - STATELESS INPUTS)
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2966/2966327.png", width=50)
    nav = st.radio("Menu", ["Workstation", "Supervisor"])
    if st.button("Full Reset"):
        st.session_state.clear()
        st.rerun()

# ---------- ADMIN ----------
if nav == "Supervisor":
    st.title("Admin Configuration")
    if st.text_input("Pwd", type="password")=="admin123":
        t1, t2 = st.tabs(["Panel 11", "Screening"])
        with t1:
            u1 = st.file_uploader("Upload Panel 11", type=["xlsx"])
            if u1:
                df1, m1 = super_parser(io.BytesIO(u1.getvalue()))
                if df1 is not None:
                    st.success(m1); st.session_state.p11 = df1
                else: st.error(m1)
            # EDIT
            e1 = st.data_editor(st.session_state.p11, hide_index=True)
            if st.button("Save P11"): st.session_state.p11=e1; st.success("OK")
        
        with t2:
            u2 = st.file_uploader("Upload Screen 3", type=["xlsx"])
            if u2:
                df2, m2 = super_parser(io.BytesIO(u2.getvalue()))
                if df2 is not None:
                    st.success(m2); st.session_state.p3 = df2
            # EDIT
            e2 = st.data_editor(st.session_state.p3, hide_index=True)
            if st.button("Save Scr"): st.session_state.p3=e2; st.success("OK")

# ---------- USER (STATELESS FORM) ----------
else:
    st.markdown("<div style='text-align:center;color:#036;border-bottom:4px solid #036'><h2>Maternity & Children Hospital - Tabuk</h2><h4>Serology Unit</h4></div>", unsafe_allow_html=True)
    
    # 1. INFO
    c1,c2,c3,c4 = st.columns(4)
    nm=c1.text_input("Name"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
    
    st.divider()
    
    # 2. ENTRY FORM (NO MEMORY KEY ERRORS)
    with st.form("main"):
        st.write("### Reactions")
        colL, colR = st.columns([1, 2])
        
        with colL:
            st.write("Controls / Screen")
            ac_in = st.radio("AC", ["Negative","Positive"])
            # Hardcoded Keys for INPUT Only (No session_state Binding on value)
            s1 = st.selectbox("S-I", ["Neg","w+","1+","2+"])
            s2 = st.selectbox("S-II", ["Neg","w+","1+","2+"])
            s3 = st.selectbox("S-III", ["Neg","w+","1+","2+"])
            
        with colR:
            st.write("Panel (11 Cells)")
            # PLAIN GRID
            g1, g2 = st.columns(2)
            c1_v = g1.selectbox("1", ["Neg","w+","1+","2+","3+"])
            c2_v = g1.selectbox("2", ["Neg","w+","1+","2+","3+"])
            c3_v = g1.selectbox("3", ["Neg","w+","1+","2+","3+"])
            c4_v = g1.selectbox("4", ["Neg","w+","1+","2+","3+"])
            c5_v = g1.selectbox("5", ["Neg","w+","1+","2+","3+"])
            c6_v = g1.selectbox("6", ["Neg","w+","1+","2+","3+"])
            
            c7_v = g2.selectbox("7", ["Neg","w+","1+","2+","3+"])
            c8_v = g2.selectbox("8", ["Neg","w+","1+","2+","3+"])
            c9_v = g2.selectbox("9", ["Neg","w+","1+","2+","3+"])
            c10_v = g2.selectbox("10", ["Neg","w+","1+","2+","3+"])
            c11_v = g2.selectbox("11", ["Neg","w+","1+","2+","3+"])
            
        run = st.form_submit_button("🚀 RUN ANALYSIS")
    
    # 3. ANALYSIS (Triggered ONLY on Submit)
    if run:
        if ac_in == "Positive":
            st.error("🚨 STOP: AC Positive. Perform DAT/Elution.")
        else:
            # Gather inputs manually
            inputs_p = {1:c1_v, 2:c2_v, 3:c3_v, 4:c4_v, 5:c5_v, 6:c6_v, 7:c7_v, 8:c8_v, 9:c9_v, 10:c10_v, 11:c11_v}
            inputs_s = {"S-I":s1, "S-II":s2, "S-III":s3}
            
            # Exclusion
            ruled = set()
            r11 = [st.session_state.p11.iloc[i].to_dict() for i in range(11)]
            r3  = [st.session_state.p3.iloc[i].to_dict() for i in range(3)]
            
            for ag in AGS:
                # Panel
                for i in range(1, 12):
                    if inputs_p[i] == "Neg":
                        if can_out(ag, r11[i-1]): ruled.add(ag); break
                # Screen
                scrs = ["I","II","III"]
                for i, k in enumerate(scrs):
                    if inputs_s[f"S-{k}"] == "Neg":
                        if ag not in ruled and can_out(ag, r3[i]): ruled.add(ag)
                        
            # Match
            cands = [x for x in AGS if x not in ruled]
            matches = []
            for c in cands:
                miss = False
                for i in range(1,12):
                    if inputs_p[i] != "Neg" and r11[i-1].get(c,0)==0: miss = True
                if not miss: matches.append(c)
                
            st.write("---")
            if not matches: st.error("Inconclusive.")
            else:
                ok_all = True
                for m in matches:
                    res, p, n, txt = rule_check(m, st.session_state.p11, inputs_p, st.session_state.p3, inputs_s, st.session_state.ext)
                    cls = "status-ok" if res else "status-no"
                    st.markdown(f"<div class='{cls}'><b>Anti-{m}:</b> {txt} ({p}P / {n}N)</div>",unsafe_allow_html=True)
                    if not res: ok_all = False
                
                if ok_all:
                    ht = f"""<div class='print-only'><br><center><h2>MCH Tabuk</h2></center><div class='results-box'>Pt: {nm} ({mr})<br>Res: Anti-{', '.join(matches)}<br>Valid Rule 3.<br><br>Sig:_________</div><div class='consultant-footer'>Dr. Haitham Ismail</div></div><script>window.print()</script>"""
                    st.markdown(ht, unsafe_allow_html=True)
                    st.balloons()
                else:
                    st.warning("⚠️ Confirmation needed. Add Extra Cells below.")

    # 4. EXTRA CELL ADDITION
    if st.session_state.ext:
        st.write("Added Cells:")
        st.dataframe(pd.DataFrame([{ "ID":x['src'], "Result":"Pos" if x['s']==1 else "Neg"} for x in st.session_state.ext]))

    with st.expander("➕ Add Cell"):
        with st.form("ext_form"):
            e1,e2 = st.columns(2)
            nid=e1.text_input("ID")
            nres=e2.selectbox("Res", ["Neg","Pos"])
            st.write("Type present antigens (e.g. D C s)")
            txt = st.text_input("Antigens space separated")
            add = st.form_submit_button("Add")
            
            if add:
                p_dict = {a:0 for a in AGS}
                for t in txt.split():
                    clean_t = t.strip().upper()
                    if clean_t in AGS: p_dict[clean_t]=1
                    elif clean_t=="D": p_dict["D"]=1
                    # case handle...
                    for aa in AGS: 
                        if aa.upper() == clean_t: p_dict[aa]=1
                        
                st.session_state.ext.append({"src":nid,"s":1 if nres=="Pos" else 0,"ph":p_dict})
                st.success("Added! Press 'RUN ANALYSIS' above.")
