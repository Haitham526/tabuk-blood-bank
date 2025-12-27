import streamlit as st
import pandas as pd
from datetime import date

# 1. SETUP
st.set_page_config(page_title="Tabuk Blood Bank", layout="wide", page_icon="🩸")

st.markdown("""
<style>
    @media print { 
        .stApp > header, .sidebar, footer, .no-print { display: none !important; } 
        .print-only { display: block !important; }
        .result-sheet { border: 2px solid #000; padding: 20px; font-family: 'Times New Roman'; font-size:14px;}
    }
    .print-only { display: none; }
    
    .status-ok { background: #d4edda; color: #155724; padding: 10px; border-left: 6px solid #198754; margin-bottom: 5px; }
    .status-no { background: #f8d7da; color: #721c24; padding: 10px; border-left: 6px solid #dc3545; margin-bottom: 5px; }
    div[data-testid="stDataEditor"] table { width: 100% !important; min-width: 100% !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div style='position:fixed;bottom:10px;right:10px;z-index:99' class='no-print'><small>Dr. Haitham Ismail</small></div>", unsafe_allow_html=True)

# 2. DEFINITIONS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# 3. STATE
if 'db_panel' not in st.session_state:
    st.session_state.db_panel = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'db_screen' not in st.session_state:
    st.session_state.db_screen = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'db_extra' not in st.session_state:
    st.session_state.db_extra = []

# 4. LOGIC
def parse_paste(txt, limit=11):
    try:
        lines = txt.strip().split('\n')
        data = []
        c_count = 0
        for line in lines:
            if c_count >= limit: break
            # التعامل مع Tab separation من الإكسيل
            cells = line.split('\t')
            
            clean_vals = []
            for c in cells:
                c_val = str(c).lower().strip()
                if any(x in c_val for x in ['+', '1', 'pos', 'w', 'yes']): 
                    clean_vals.append(1)
                else: 
                    clean_vals.append(0)
            
            # محاولة ضبط الأعمدة لتكون 26 عمود
            # نأخذ آخر 26 عمود في الصف لأن الإكسيل أحيانا بيضيف ال ID
            if len(clean_vals) > 26:
                clean_vals = clean_vals[-26:]
            
            # لو أقل نكمل باصفار
            while len(clean_vals) < 26: clean_vals.append(0)
            
            rid = f"C{c_count+1}" if limit==11 else f"S{c_count}"
            r_d = {"ID": rid}
            for i, ag in enumerate(AGS):
                r_d[ag] = clean_vals[i]
            
            data.append(r_d)
            c_count += 1
            
        return pd.DataFrame(data), f"Updated {c_count} rows"
    except Exception as e: return None, str(e)

def rule_check(c, p11, r11, p3, r3, ex):
    p, n = 0, 0
    # Panel
    for i in range(11):
        s=1 if r11[i]!="Neg" else 0
        h=p11.iloc[i].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    for i in range(3):
        s=1 if r3[i]!="Neg" else 0
        h=p3.iloc[i].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extra
    for x in ex:
        if x['res']==1 and x['ph'].get(c,0)==1: p+=1
        if x['res']==0 and x['ph'].get(c,0)==0: n+=1
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    return ok, p, n

def can_out(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr=PAIRS.get(ag)
        if pr and ph.get(pr,0)==1: return False
    return True

# 5. UI
try:
    with st.sidebar:
        st.title("Menu")
        mode = st.radio("Go To:", ["Workstation", "Admin Config"])
        if st.button("HARD RESET"):
            st.session_state.clear()
            st.rerun()

    # ---- ADMIN ----
    if mode == "Admin Config":
        st.header("Master Configuration (Copy/Paste)")
        if st.text_input("Password", type="password") == "admin123":
            
            t1, t2 = st.tabs(["Panel 11", "Screening"])
            
            with t1:
                st.info("انسخ الأرقام من ملف الإكسيل (26 عمود × 11 صف) والصقهم هنا:")
                paste_txt = st.text_area("Paste Excel Data (Panel)", height=150)
                
                if st.button("Process Panel Paste"):
                    if paste_txt:
                        df_new, m = parse_paste(paste_txt, 11)  # <<-- هنا كان الخطأ وتم اصلاحه
                        if df_new is not None:
                            st.session_state.db_panel = df_new
                            st.success(f"✅ {m}")
                            st.rerun()
                        else: st.error("Error parsing text.")
                
                st.write("**Current Data (Editable):**")
                e1 = st.data_editor(st.session_state.db_panel, hide_index=True)
                if st.button("Save P11 Changes"): 
                    st.session_state.db_panel=e1
                    st.success("Saved")
                
            with t2:
                st.write("Screening Paste (3 Rows):")
                paste_scr = st.text_area("Paste Screen Data", height=100)
                if st.button("Process Screen"):
                    if paste_scr:
                        dfs, ms = parse_paste(paste_scr, 3)
                        if dfs is not None: 
                            st.session_state.db_screen=dfs
                            st.success("Updated")
                            st.rerun()
                
                e2 = st.data_editor(st.session_state.db_screen, hide_index=True)
                if st.button("Save Screen"): 
                    st.session_state.db_screen=e2
                    st.success("Saved")

    # ---- USER ----
    else:
        st.markdown("<h2 style='color:#036;text-align:center'>Maternity & Children Hospital - Tabuk</h2>", unsafe_allow_html=True)
        
        c1,c2,c3,c4=st.columns(4)
        nm=c1.text_input("Pt"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
        st.divider()
        
        # FORM (SAFE INPUT)
        with st.form("main"):
            st.write("### 1. Reactions")
            L, R = st.columns([1, 2])
            
            with L:
                st.write("Controls")
                ac_res = st.radio("AC", ["Negative", "Positive"])
                s_inputs = []
                s_inputs.append(st.selectbox("Scn I", ["Neg","w+","1+","2+"]))
                s_inputs.append(st.selectbox("Scn II", ["Neg","w+","1+","2+"]))
                s_inputs.append(st.selectbox("Scn III", ["Neg","w+","1+","2+"]))
                
            with R:
                st.write("Panel Reactions")
                g1, g2 = st.columns(2)
                p_inputs = []
                # Explicit list filling
                with g1:
                   p_inputs.append(st.selectbox("C 1", ["Neg","w+","1+","2+","3+"]))
                   p_inputs.append(st.selectbox("C 2", ["Neg","w+","1+","2+","3+"]))
                   p_inputs.append(st.selectbox("C 3", ["Neg","w+","1+","2+","3+"]))
                   p_inputs.append(st.selectbox("C 4", ["Neg","w+","1+","2+","3+"]))
                   p_inputs.append(st.selectbox("C 5", ["Neg","w+","1+","2+","3+"]))
                   p_inputs.append(st.selectbox("C 6", ["Neg","w+","1+","2+","3+"]))
                with g2:
                   p_inputs.append(st.selectbox("C 7", ["Neg","w+","1+","2+","3+"]))
                   p_inputs.append(st.selectbox("C 8", ["Neg","w+","1+","2+","3+"]))
                   p_inputs.append(st.selectbox("C 9", ["Neg","w+","1+","2+","3+"]))
                   p_inputs.append(st.selectbox("C 10", ["Neg","w+","1+","2+","3+"]))
                   p_inputs.append(st.selectbox("C 11", ["Neg","w+","1+","2+","3+"]))
            
            st.write("---")
            run = st.form_submit_button("🚀 Run Analysis")
        
        if run:
            if ac_res == "Positive":
                st.error("🚨 STOP: Auto Control Positive.")
            else:
                ruled = set()
                r11 = [st.session_state.db_panel.iloc[i].to_dict() for i in range(11)]
                r3 = [st.session_state.db_screen.iloc[i].to_dict() for i in range(3)]
                
                # Exclusion
                for i, v in enumerate(p_inputs):
                    if v == "Neg":
                        for ag in AGS: 
                            if can_out(ag, r11[i]): ruled.add(ag)
                
                for i, v in enumerate(s_inputs):
                    if v == "Neg":
                        for ag in AGS:
                            if ag not in ruled and can_out(ag, r3[i]): ruled.add(ag)
                
                # Matching
                cands = [x for x in AGS if x not in ruled]
                matches = []
                for c in cands:
                    mis = False
                    for i, v in enumerate(p_inputs):
                        if v!="Neg" and r11[i].get(c,0)==0: mis = True
                    if not mis: matches.append(c)
                
                if not matches:
                    st.error("❌ No matches.")
                else:
                    st.success(f"Identified: Anti-{', '.join(matches)}")
                    final_ok = True
                    
                    for m in matches:
                        ok, p, n = rule_check(m, st.session_state.db_panel, p_inputs, st.session_state.db_screen, s_inputs, st.session_state.db_extra)
                        msg = "Rule of 3 Met" if ok else "Not Met"
                        style = "status-ok" if ok else "status-no"
                        st.markdown(f"<div class='{style}'><b>Anti-{m}:</b> {msg} ({p}P / {n}N)</div>", unsafe_allow_html=True)
                        if not ok: final_ok=False
                    
                    if final_ok:
                        html = f"""<div class='print-only'><center><h2>Maternity & Children Hospital - Tabuk</h2><h3>Serology Report</h3></center><div class='result-sheet'><b>Pt:</b> {nm}<br><b>Result:</b> Anti-{', '.join(matches)} Detected.<br>Probability Validated.<br><br><b>Signature:</b> ___________________</div><div style='text-align:center;position:fixed;bottom:0;width:100%'>Dr. Haitham Ismail</div></div><script>window.print()</script>"""
                        st.markdown(html, unsafe_allow_html=True)
                        st.balloons()
                    else:
                        st.warning("Use Extra Cells to Confirm.")

        with st.expander("➕ Add External Cell"):
            with st.form("add_ex"):
                eid=st.text_input("ID")
                ers=st.selectbox("R",["Neg","Pos"])
                st.write("Antigens (space separated e.g. D C s):")
                ags_txt = st.text_input("Antigens")
                if st.form_submit_button("Add"):
                    ph = {a:0 for a in AGS}
                    if ags_txt:
                        for t in ags_txt.split():
                            t = t.upper().strip()
                            if t in AGS: ph[t]=1
                    st.session_state.db_extra.append({"res":1 if ers=="Pos" else 0,"ph":ph,"s":1 if ers=="Pos" else 0})
                    st.success("Added! Re-Run Analysis.")
                    
except Exception as e:
    st.error(f"Error: {e}")
    if st.button("FIX / RESET"):
        st.session_state.clear()
        st.rerun()
