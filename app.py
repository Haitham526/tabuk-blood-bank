.import streamlit as st
import pandas as pd
import io

# 1. BASE CONFIG
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
    .status-fail { background: #f8d7da; color: #842029; padding: 10px; border-left: 6px solid #dc3545; margin-bottom: 5px; }
    div[data-testid="stDataEditor"] table { width: 100% !important; min-width: 100% !important; }
</style>
""", unsafe_allow_html=True)

# 2. DEFINITIONS
AGS = ["D","C","E","c","e","Cw","K","k","Kpa","Kpb","Jsa","Jsb","Fya","Fyb","Jka","Jkb","Lea","Leb","P1","M","N","S","s","Lua","Lub","Xga"]
DOSAGE = ["C","c","E","e","Fya","Fyb","Jka","Jkb","M","N","S","s"]
PAIRS = {'C':'c','c':'C','E':'e','e':'E','K':'k','k':'K','Fya':'Fyb','Fyb':'Fya','Jka':'Jkb','Jkb':'Jka','M':'N','N':'M','S':'s','s':'S'}

# 3. SAFETY INIT
if 'db_panel' not in st.session_state:
    st.session_state.db_panel = pd.DataFrame([{"ID": f"C{i+1}", **{a:0 for a in AGS}} for i in range(11)])
if 'db_screen' not in st.session_state:
    st.session_state.db_screen = pd.DataFrame([{"ID": f"S{i}", **{a:0 for a in AGS}} for i in ["I","II","III"]])
if 'db_extra' not in st.session_state:
    st.session_state.db_extra = []

# 4. FUNCTIONS
def process_paste(text, mode='p11'):
    try:
        # Excel copies data as Tab-separated
        # We expect only 0, 1, +, w, etc.
        rows = text.strip().split('\n')
        parsed_data = []
        
        limit = 11 if mode=='p11' else 3
        
        for i, row_str in enumerate(rows):
            if i >= limit: break
            # Split by Tab
            cols = row_str.split('\t')
            # Only take the first 26 columns (Antigens)
            # Users might copy ID column too, so let's handle that
            
            clean_vals = []
            for c in cols:
                # Basic cleanup
                v = c.lower().strip()
                if any(x in v for x in ['+', '1', 'w', 'pos']): clean_vals.append(1)
                else: clean_vals.append(0)
            
            # If user copied ID column, remove it (assuming numbers match count)
            if len(clean_vals) > 26: 
                clean_vals = clean_vals[-26:] # Take last 26 columns
            
            # Pad if missing
            while len(clean_vals) < 26: clean_vals.append(0)
            
            # Create Row Dict
            rid = f"C{i+1}" if mode=='p11' else f"S{i}"
            r_dict = {"ID": rid}
            for idx, ag in enumerate(AGS):
                r_dict[ag] = clean_vals[idx]
            
            parsed_data.append(r_dict)
            
        return pd.DataFrame(parsed_data)
    except Exception as e:
        return None

def rule_check(c, p11, r11, p3, r3, ext):
    p, n = 0, 0
    # Panel
    for i in range(1, 12):
        s = 1 if r11[i] != "Neg" else 0
        h = p11.iloc[i-1].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Screen
    for i, x in enumerate(["I","II","III"]):
        s = 1 if r3[f"s{x}"] != "Neg" else 0
        h = p3.iloc[i].get(c,0)
        if s==1 and h==1: p+=1
        if s==0 and h==0: n+=1
    # Extra
    for x in ext:
        if x['s']==1 and x['p'].get(c,0)==1: p+=1
        if x['s']==0 and x['p'].get(c,0)==0: n+=1
    ok = (p>=3 and n>=3) or (p>=2 and n>=3)
    t = "Standard" if (p>=3 and n>=3) else ("Modified" if ok else "Fail")
    return ok, p, n, t

def can_out(ag, ph):
    if ph.get(ag,0)==0: return False
    if ag in DOSAGE:
        pr=PAIRS.get(ag)
        if pr and ph.get(pr,0)==1: return False
    return True

# ========================================================
# 5. INTERFACE
# ========================================================
try:
    with st.sidebar:
        st.title("Menu")
        mode = st.radio("Go To:", ["Workstation", "Admin Config"])
        if st.button("HARD RESET"):
            st.session_state.clear()
            st.rerun()

    # ---- ADMIN ----
    if mode == "Admin Config":
        st.header("Master Configuration")
        if st.text_input("Password", type="password") == "admin123":
            
            t1, t2 = st.tabs(["Panel 11", "Screening"])
            
            with t1:
                st.info("💡 الحل السحري: اذهب لملف الإكسيل، ظلل الأرقام فقط (الـ 26 عمود)، انسخهم (Ctrl+C)، والصقهم هنا (Ctrl+V).")
                paste_area = st.text_area("1. Paste Excel Data Here:", height=150, help="Copy the grid of numbers from Excel and paste here.")
                
                if st.button("2. Process Paste (Panel)"):
                    if paste_area:
                        df_new = process_paste(paste_area, 'p11')
                        if df_new is not None:
                            st.session_state.db_panel = df_new
                            st.success("✅ تم لصق البيانات بنجاح! راجع الجدول بالأسفل.")
                        else: st.error("Error parsing text.")
                
                st.write("---")
                st.write("**Current Data (Editable):**")
                e1 = st.data_editor(st.session_state.db_panel, hide_index=True)
                if st.button("Save Changes (P11)"): st.session_state.db_panel=e1; st.success("Saved")
                
            with t2:
                st.write("Screening Paste Area:")
                paste_scr = st.text_area("Paste Screen 3 rows here:")
                if st.button("Process Screen"):
                    if paste_scr:
                        dfs = process_paste(paste_scr, 'p3')
                        if dfs is not None: st.session_state.db_screen=dfs; st.success("Updated")
                
                e2 = st.data_editor(st.session_state.db_screen, hide_index=True)
                if st.button("Save Screen"): st.session_state.db_screen=e2; st.success("Saved")

    # ---- USER ----
    else:
        st.markdown("<h2 style='color:#036;text-align:center'>Maternity & Children Hospital - Tabuk</h2>", unsafe_allow_html=True)
        c1,c2,c3,c4=st.columns(4)
        nm=c1.text_input("Pt"); mr=c2.text_input("MRN"); tc=c3.text_input("Tech"); dt=c4.date_input("Date")
        st.divider()
        
        # FORM (SAFE INPUT)
        input_panel = [] 
        input_screen = []
        
        with st.form("main"):
            colL, colR = st.columns([1, 2])
            with colL:
                st.subheader("1. Control")
                ac_res = st.radio("Auto Control", ["Negative", "Positive"], horizontal=True)
                s1 = st.selectbox("Scn I", ["Neg","w+","1+","2+"])
                s2 = st.selectbox("Scn II", ["Neg","w+","1+","2+"])
                s3 = st.selectbox("Scn III", ["Neg","w+","1+","2+"])
                input_screen = [s1, s2, s3]
            with colR:
                st.subheader("2. Panel")
                g1, g2 = st.columns(2)
                with g1:
                    input_panel.append(st.selectbox("C 1", ["Neg","w+","1+","2+","3+"]))
                    input_panel.append(st.selectbox("C 2", ["Neg","w+","1+","2+","3+"]))
                    input_panel.append(st.selectbox("C 3", ["Neg","w+","1+","2+","3+"]))
                    input_panel.append(st.selectbox("C 4", ["Neg","w+","1+","2+","3+"]))
                    input_panel.append(st.selectbox("C 5", ["Neg","w+","1+","2+","3+"]))
                    input_panel.append(st.selectbox("C 6", ["Neg","w+","1+","2+","3+"]))
                with g2:
                    input_panel.append(st.selectbox("C 7", ["Neg","w+","1+","2+","3+"]))
                    input_panel.append(st.selectbox("C 8", ["Neg","w+","1+","2+","3+"]))
                    input_panel.append(st.selectbox("C 9", ["Neg","w+","1+","2+","3+"]))
                    input_panel.append(st.selectbox("C 10", ["Neg","w+","1+","2+","3+"]))
                    input_panel.append(st.selectbox("C 11", ["Neg","w+","1+","2+","3+"]))
            
            st.write("---")
            run = st.form_submit_button("🚀 Run Analysis")
    
        if run:
            if ac_res == "Positive":
                st.error("🚨 STOP: Auto Control Positive.")
            else:
                ruled = set()
                r11 = [st.session_state.db_panel.iloc[i].to_dict() for i in range(11)]
                r3 = [st.session_state.db_screen.iloc[i].to_dict() for i in range(3)]
                
                # Exclude Panel
                for i, v in enumerate(input_panel):
                    if v == "Neg":
                        for ag in AGS: 
                            if can_out(ag, r11[i]): ruled.add(ag)
                # Exclude Screen
                for i, v in enumerate(input_screen):
                    if v == "Neg":
                        for ag in AGS:
                            if ag not in ruled and can_out(ag, r3[i]): ruled.add(ag)
                
                # Include
                cands = [x for x in AGS if x not in ruled]
                matches = []
                for c in cands:
                    miss = False
                    for i, v in enumerate(input_panel):
                        if v!="Neg" and r11[i].get(c,0)==0: miss=True
                    if not miss: matches.append(c)
                
                # Display
                if not matches: st.error("No matches.")
                else:
                    st.success(f"Identified: Anti-{', '.join(matches)}")
                    final_ok = True
                    # Check Logic
                    p_in_map = {i+1:v for i,v in enumerate(input_panel)}
                    s_in_map = {"sI":input_screen[0], "sII":input_screen[1], "sIII":input_screen[2]}
                    
                    for m in matches:
                        ok, p, n, txt = rule_check(m, st.session_state.db_panel, input_panel, st.session_state.db_screen, s_in_map, st.session_state.db_extra)
                        css = "status-ok" if ok else "status-fail"
                        st.markdown(f"<div class='{css}'><b>Anti-{m}:</b> {txt} ({p}P/{n}N)</div>",unsafe_allow_html=True)
                        if not ok: final_ok = False
                    
                    if final_ok:
                        html = f"""<div class='print-only'><center><h2>Maternity & Children Hospital - Tabuk</h2><h3>Serology Report</h3></center><div class='result-sheet'><b>Patient:</b> {nm} ({mr})<br><b>Tech:</b> {tc} | <b>Date:</b> {dt}<hr><b>Conclusion:</b> Anti-{', '.join(matches)} Detected.<br>Probability p<=0.05 Met.<br><br><b>Signature:</b> ___________________</div><div style='text-align:center;position:fixed;bottom:0;width:100%'>Dr. Haitham Ismail</div></div><script>window.print()</script>"""
                        st.markdown(html, unsafe_allow_html=True)
                        st.balloons()
                    else:
                        st.warning("Rule Not Met. Add Extra Cells below.")

        with st.expander("➕ Add External Cell"):
            with st.form("add_ex"):
                eid=st.text_input("ID"); ers=st.selectbox("R",["Neg","Pos"])
                st.write("Antigens present (space separated e.g. D C):")
                ags_txt = st.text_input("Antigens")
                if st.form_submit_button("Add"):
                    ph = {a:0 for a in AGS}
                    if ags_txt:
                        for t in ags_txt.split():
                            t = t.upper().strip()
                            if t in AGS: ph[t]=1
                    st.session_state.db_extra.append({"res":1 if ers=="Pos" else 0,"s":1 if ers=="Pos" else 0,"ph":ph,"p":ph})
                    st.success("Added! Run Analysis Again.")

except Exception as e: st.error(f"Error: {e}")
